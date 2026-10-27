"""Papiers : le majordome administratif, intégré à EVA.

Paperless-ngx (service à part) fait l'OCR et l'archivage ; EVA fait tout le reste ici : surveille les dossiers
de dépôt, envoie les fichiers à Paperless, analyse chaque document avec Ollama (échéances, préavis, garanties,
impôts FR/IT), suit les dates, prévient, répond. Les données sont dans workspace/papiers/papiers.db.

Activé dès que l'adresse et le jeton de Paperless sont connus (Paramètres › Papiers, ou EVA_PAPERLESS_URL /
EVA_PAPERLESS_TOKEN). Le moteur est synchrone (repris du majordome autonome, déjà testé) : on l'appelle dans
des threads pour ne jamais bloquer la boucle d'EVA."""
import asyncio
import copy
import logging
import re
import threading
import time
import unicodedata
from pathlib import Path

import httpx

from ..config import settings as eva
from . import depot
from .clients import OllamaClient, PaperlessClient
from .config import Reglages, charger, racine, serialiser, valider
from .db import DB
from .moteur import Majordome

log = logging.getLogger("eva-core.papiers")


class PapiersError(Exception):
    pass


# ---------------------------------------------------------------- moteur (un seul, reconstruit si les réglages changent)
_verrou = threading.RLock()
_moteur: Majordome | None = None
_db: DB | None = None
_etat: dict = {"dossiers": {}, "derniere_erreur": None, "dernier_passage": None, "paperless_total": None}
_reveil: asyncio.Event | None = None


def _base() -> DB:
    global _db
    with _verrou:
        if _db is None:
            d = Path(eva.workspace_root) / "papiers"
            d.mkdir(parents=True, exist_ok=True)
            _db = DB(str(d / "papiers.db"))
        return _db


def reglages() -> Reglages:
    return charger(_base().get_kv("reglages"))


def moteur() -> Majordome:
    global _moteur
    with _verrou:
        if _moteur is None:
            r = reglages()
            _moteur = Majordome(r, _base(), PaperlessClient(r.paperless_url, r.paperless_token, r.lien_public),
                                OllamaClient(r.ollama_url, r.ollama_model, r.ollama_num_ctx, 600))
        return _moteur


def _installer(m: Majordome | None) -> None:
    """Pour les tests : injecte un moteur (faux Paperless / faux Ollama), ou None pour revenir au réel."""
    global _moteur, _db
    with _verrou:
        _moteur = m
        if m is not None:
            _db = m.db


def active() -> bool:
    try:
        return moteur().s.actif()
    except Exception:  # noqa: BLE001 — une base illisible ne doit pas casser EVA
        log.exception("Papiers : réglages illisibles")
        return False


async def _appel(fn, *args, **kwargs):
    if not active():
        raise PapiersError("Les papiers ne sont pas configurés (Paramètres › Papiers : adresse et jeton de Paperless).")
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        raise PapiersError("Paperless refuse le jeton (Paramètres › Papiers)." if code in (401, 403)
                           else f"Erreur de Paperless ou d'Ollama ({code}).") from exc
    except httpx.HTTPError as exc:
        raise PapiersError(f"Paperless ou Ollama injoignable ({exc.__class__.__name__}).") from exc


# ---------------------------------------------------------------- lecture / actions (utilisées par les outils et l'API)
async def echeances(jours: int | None = 60, statuts=("active", "a_valider")) -> list[dict]:
    return await _appel(moteur().echeances, jours, tuple(statuts))


async def a_valider() -> list[dict]:
    return await _appel(moteur().documents_a_valider)


async def stats() -> dict:
    return await _appel(moteur().stats)


_ACTIONS = {"valider": "active", "faite": "faite", "ignorer": "ignoree"}


async def marquer(ech_id: int, action: str) -> dict:
    if action not in _ACTIONS:
        raise PapiersError("Action inconnue (valider, faite ou ignorer).")
    r = await _appel(moteur().changer_statut_echeance, int(ech_id), _ACTIONS[action])
    if not r:
        raise PapiersError("Élément introuvable dans les papiers.")
    return r


async def corriger(ech_id: int, champs: dict) -> dict:
    r = await _appel(moteur().modifier_echeance, int(ech_id), champs)
    if not r:
        raise PapiersError("Élément introuvable dans les papiers.")
    return r


async def ajouter(paperless_id: int, description: str, date_echeance: str, preavis_jours: int | None = None,
                  nature: str = "autre") -> int:
    try:
        return await _appel(moteur().ajouter_echeance, int(paperless_id), description, date_echeance, preavis_jours, nature)
    except ValueError as exc:
        raise PapiersError(str(exc)) from exc


async def valider_document(doc_id: int) -> None:
    await _appel(moteur().valider_document, int(doc_id))


async def retraiter(doc_id: int) -> dict:
    return await _appel(moteur().traiter_document, int(doc_id))


async def tout_reanalyser() -> int:
    await _appel(moteur().tout_reanalyser)
    reveiller()
    return (await stats())["a_refaire"]


async def question(texte: str) -> dict:
    return await _appel(moteur().question, texte)


async def resume(jours: int = 30) -> str:
    return await _appel(moteur().resume, jours)


async def alertes_du_jour() -> list[dict]:
    """Alertes dues aujourd'hui, chacune une seule fois (le moteur mémorise ce qui a déjà été annoncé)."""
    return await _appel(moteur().verifier_alertes)


# ---------------------------------------------------------------- dépôt de fichiers
FORMATS_DEPOT = depot.FORMATS


async def deposer_octets(nom: str, donnees: bytes) -> dict:
    nom = Path(nom).name
    if Path(nom).suffix.lower() not in FORMATS_DEPOT:
        raise PapiersError(f"Format non pris en charge pour les papiers ({Path(nom).suffix or 'sans extension'}).")
    if not donnees:
        raise PapiersError("Fichier vide.")
    if len(donnees) > depot.MAX_OCTETS:
        raise PapiersError("Fichier trop gros (60 Mo maximum).")
    tache = await _appel(moteur().paperless.deposer, nom, donnees)
    reveiller()
    return {"ok": True, "nom": nom, "tache": tache}


async def deposer(chemin: Path) -> dict:
    if chemin.suffix.lower() not in FORMATS_DEPOT:
        raise PapiersError(f"Format non pris en charge pour les papiers ({chemin.suffix or 'sans extension'}).")
    return await deposer_octets(chemin.name, await asyncio.to_thread(chemin.read_bytes))


# ---------------------------------------------------------------- réglages, dossiers, progression
def reglages_publics() -> dict:
    return moteur().s.publics()


async def maj_reglages(champs: dict) -> dict:
    global _moteur
    try:
        r, _faits = valider(copy.deepcopy(moteur().s), champs)
    except (ValueError, TypeError) as exc:
        raise PapiersError(str(exc)) from exc
    with _verrou:
        _base().set_kv("reglages", serialiser(r))
        _moteur = None                       # reconstruit avec les nouveaux réglages au prochain appel
    reveiller()
    return reglages_publics()


async def tester() -> dict:
    """État de chaque maillon, pour la page Papiers."""
    m = moteur()
    out = {"configure": m.s.actif(), "paperless": None, "ollama": None, "modele": None}
    if not m.s.actif():
        return out
    try:
        await asyncio.to_thread(m.paperless.ping)
        out["paperless"] = "ok"
    except httpx.HTTPStatusError as exc:
        out["paperless"] = "jeton refusé" if exc.response.status_code in (401, 403) else f"erreur {exc.response.status_code}"
    except httpx.HTTPError as exc:
        out["paperless"] = f"injoignable ({exc.__class__.__name__})"
    try:
        noms = await asyncio.to_thread(m.ollama.modeles)
        out["ollama"] = "ok"
        out["modele"] = m.s.ollama_model in noms or f"{m.s.ollama_model}:latest" in noms
        out["modeles_disponibles"] = sorted(n for n in noms if "embed" not in n)
    except httpx.HTTPError as exc:
        out["ollama"] = f"injoignable ({exc.__class__.__name__})"
    return out


async def parcourir(chemin: str = "") -> dict:
    try:
        return await asyncio.to_thread(depot.parcourir, Path(racine()), chemin)
    except (ValueError, OSError) as exc:
        raise PapiersError(str(exc)) from exc


async def creer_dossier(chemin: str) -> str:
    try:
        return await asyncio.to_thread(depot.creer, Path(racine()), chemin)
    except (ValueError, OSError) as exc:
        raise PapiersError(str(exc)) from exc


def _progression_sync() -> dict:
    m = moteur()
    db = m.db
    c = lambda sql, p=(): db.one(sql, p)["n"]  # noqa: E731
    analyses = c("SELECT COUNT(*) n FROM documents WHERE statut NOT IN ('erreur', 'a_refaire')")
    erreurs = c("SELECT COUNT(*) n FROM documents WHERE statut = 'erreur'")
    total = _etat.get("paperless_total")
    if m.s.actif():
        try:
            total = len(m.paperless.tous_les_ids())
            _etat["paperless_total"] = total
        except httpx.HTTPError:
            pass
    prets, problemes = depot.candidats(Path(racine()), m.s)
    a_envoyer = sum(1 for p, _d in prets if not db.one(
        "SELECT 1 FROM imports WHERE chemin=? AND (statut='envoye' OR tentatives>=?)", (str(p), m.s.max_retries)))
    return {
        "dans_les_dossiers": a_envoyer,                   # fichiers déposés, pas encore envoyés à Paperless
        "imports_envoyes": c("SELECT COUNT(*) n FROM imports WHERE statut='envoye'"),
        "imports_en_erreur": db.q("SELECT chemin, erreur, maj_le FROM imports WHERE statut='erreur' ORDER BY maj_le DESC LIMIT 20"),
        "dans_paperless": total,                          # documents lus par Paperless
        "analyses": analyses,
        "analyses_en_erreur": erreurs,
        "a_analyser": max(0, (total or 0) - analyses - erreurs) if total is not None else None,
        "problemes_dossiers": problemes,
        "dernier_passage": _etat.get("dernier_passage"),
        "derniere_erreur": _etat.get("derniere_erreur"),
    }


async def progression() -> dict:
    return await asyncio.to_thread(_progression_sync)


# ---------------------------------------------------------------- boucle de fond
def reveiller() -> None:
    if _reveil is not None:
        try:
            asyncio.get_running_loop().call_soon(_reveil.set)
        except RuntimeError:
            _reveil.set()


async def passage() -> dict:
    """Un passage : dossiers surveillés → Paperless, puis analyse de quelques documents (le serveur IA reste partagé)."""
    m = moteur()
    if not m.s.actif():
        return {"actif": False}
    bilan = await asyncio.to_thread(depot.scanner, m.db, m.paperless, Path(racine()), m.s)
    analyses = await asyncio.to_thread(m.sonder, m.s.analyses_par_passage)
    _etat["dernier_passage"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _etat["derniere_erreur"] = None
    return {"actif": True, **bilan, "analyses": analyses}


async def boucle(intervalle: float = 60.0) -> None:
    global _reveil
    _reveil = asyncio.Event()
    while True:
        try:
            r = await passage()
            if r.get("analyses"):
                log.info("Papiers : %d document(s) analysé(s)", r["analyses"])
        except httpx.HTTPError as exc:
            _etat["derniere_erreur"] = f"Paperless ou Ollama injoignable ({exc.__class__.__name__})"
        except Exception as exc:  # noqa: BLE001 — la boucle ne doit jamais s'arrêter
            log.exception("Papiers : erreur dans la boucle")
            _etat["derniere_erreur"] = str(exc)[:300]
        try:
            await asyncio.wait_for(_reveil.wait(), intervalle)
        except asyncio.TimeoutError:
            pass
        _reveil.clear()


# ---------------------------------------------------------------- réponses instantanées dans la conversation (sans le modèle)
# « Quelles sont mes échéances ? », « qu'est-ce que j'ai à payer ce mois-ci ? », « point papiers » : la réponse est une
# liste que le moteur formule déjà ; passer par le modèle prend de longues secondes pour un résultat identique.
def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower().replace("’", "'"))
                   if unicodedata.category(c) != "Mn")


_APERCU = re.compile(
    r"^\W*(?:eva\W+)?(?:(?:quelles?|quels?) sont |(?:donne|montre|liste|dis)[- ]moi |c'?est quoi |et )?(?:mes|les|nos) echeances\b"
    r"|\b(?:qu'?est[- ]ce (?:que|qu') ?(?:j'?ai|on a|nous avons) a (?:payer|regler|renouveler|faire)|qu'?est[- ]ce qui (?:arrive|tombe))"
    r"|\bpoint (?:papiers?|administratif)\b|\bj'?ai (?:des|quelque chose a) (?:echeances?|papiers?)\b"
    r"|\becheances? (?:a venir|du mois|de la semaine|ce mois|cette semaine|prochaines?)\b")
_DEPOT = re.compile(
    r"\b(?:range|ranger|rangez|depose|deposer|ajoute|ajouter|envoie|envoyer|mets|mettre|classe|classer|archive|archiver|garde|garder|donne|transmets)\w*\b"
    r".{0,40}\b(?:papiers?|majordome|paperless|administratif|a suivre|echeances?)\b"
    r"|^\W*(?:pour (?:le|les) (?:majordome|papiers?)|papiers?|a suivre|au majordome)\W*$")
_A_VERIFIER = re.compile(r"\b(?:papiers?|documents?) (?:a verifier|a valider|incertains?)\b")
# Question générale sur les papiers (« que disent mes papiers ? », « qu'est-ce que j'ai comme papiers ? ») :
# on interroge directement le moteur des papiers, sans laisser le modèle choisir (il partait sur docs_search).
_QUESTION = re.compile(r"\b(?:mes|nos|les|ses) papiers\b|\bpapiers? (?:administratifs?|de la famille)\b|\bpaperasse\b"
                       r"|\bmes (?:contrats|assurances|garanties|abonnements)\b")


def detect(text: str) -> dict | None:
    """Aperçu des échéances ou papiers à vérifier → {"kind", "jours"} ; une question précise n'est PAS captée."""
    if not active():
        return None
    t = _fold(text).strip()
    if len(t) > 120:
        return None
    if _A_VERIFIER.search(t):
        return {"kind": "a_verifier"}
    if not _APERCU.search(t):
        return {"kind": "question"} if _QUESTION.search(t) else None
    jours = 7 if "semaine" in t else 30 if "mois" in t else 60
    return {"kind": "apercu", "jours": jours}


def wants_deposit(text: str) -> bool:
    """« Range ça dans mes papiers », « ajoute au majordome », « papiers » avec un fichier joint."""
    return active() and bool(_DEPOT.search(_fold(text)))


async def deposer_fichiers(rels: list[str], workspace: Path) -> str:
    from ..uploads import resolve_upload
    ok, ko = [], []
    for rel in rels:
        p = resolve_upload(rel, workspace)
        if not p:
            ko.append(f"{Path(rel).name} (introuvable)")
            continue
        try:
            await deposer(p)
            ok.append(p.name)
        except PapiersError as exc:
            ko.append(f"{p.name} : {exc}")
    msg = ""
    if ok:
        msg = (f"C'est rangé : {', '.join(ok)} {'est parti' if len(ok) == 1 else 'sont partis'} dans tes papiers. "
               "Le temps de la lecture et de l'analyse, compte quelques minutes ; ensuite, demande-moi tes échéances, "
               "et je te préviendrai le matin quand une date approchera.")
    if ko:
        msg += (" " if msg else "") + "Pas pu déposer : " + " ; ".join(ko) + "."
    return msg


async def reponse_question(texte: str) -> str:
    """Question libre sur les papiers, posée directement au moteur (un seul passage du modèle)."""
    try:
        return (await question(texte[:500]))["reponse"]
    except PapiersError as exc:
        return f"Je n'arrive pas à consulter les papiers : {exc}"


async def reponse_directe(cmd: dict) -> str:
    try:
        st = await stats()
        if not st.get("documents"):
            return ("Aucun papier n'a encore été analysé. Si tu viens d'en déposer, laisse-moi quelques minutes "
                    "(page Papiers pour suivre l'avancement) ; sinon, joins un papier ici avec « range ça dans mes papiers ».")
        if cmd["kind"] == "a_verifier":
            docs = await a_valider()
            if not docs:
                return "Aucun papier à vérifier : tout ce que j'ai lu est clair."
            noms = ", ".join(f"« {d.get('titre') or 'document ' + str(d.get('paperless_id'))} »" for d in docs[:6])
            return (f"{len(docs)} papier{'s' if len(docs) > 1 else ''} à vérifier : {noms}"
                    + (" et d'autres" if len(docs) > 6 else "") + ". Tu peux les corriger dans la page Papiers ou me dire la bonne date.")
        return await resume(cmd["jours"])
    except PapiersError as exc:
        return f"Je n'arrive pas à consulter les papiers : {exc}"

