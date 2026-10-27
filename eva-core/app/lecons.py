"""EVA apprend de ses ratés, sans qu'on touche à son code.

1. Pendant les conversations, elle note ses RATÉS : la personne la corrige (« non, je voulais mes recettes »), elle répond
   « je ne peux pas » alors qu'un outil existe peut-être, un outil a échoué, ou la réponse reçoit 👎.
2. La nuit (ou sur demande), pour chaque raté, un modèle (réglable : serveur IA, IA du marché ou IA gratuites) regarde la
   demande et la liste de TOUS les outils d'EVA, et dit quel outil aurait dû servir, avec une consigne courte. La leçon est
   VÉRIFIÉE : la demande est rejouée au banc d'essai avec la leçon (rien n'est exécuté) ; elle n'est gardée que si le modèle
   de tous les jours choisit alors le bon outil.
3. Une leçon s'applique toute seule aux demandes qui ressemblent : l'outil est proposé au modèle et une consigne lui rappelle
   quoi faire. Visible et annulable dans Apprentissage.
4. Rien ne convient (fonction absente) : demande d'évolution notée ; si on l'a autorisé, une tâche en fond prépare une
   proposition de modification du code (page Évolution), jamais appliquée sans accord."""
import asyncio
import json
import logging
import re
import time
import unicodedata

from .db import get_pool

logger = logging.getLogger("eva-core.lecons")
KV = "lecons_reglages"
DEFAUT = {"actif": True, "modele": "", "code": False, "heure": 3, "auto": False}
MAX_PAR_PASSE = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS rates (
    id BIGSERIAL PRIMARY KEY,
    cree TIMESTAMPTZ NOT NULL DEFAULT now(),
    qui TEXT NOT NULL DEFAULT '',
    session TEXT NOT NULL DEFAULT '',
    phrase TEXT NOT NULL,
    reponse TEXT NOT NULL DEFAULT '',
    outils TEXT[] NOT NULL DEFAULT '{}',
    genre TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'a_voir',
    resultat TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS rates_statut ON rates (statut, id);
CREATE TABLE IF NOT EXISTS lecons (
    id BIGSERIAL PRIMARY KEY,
    cree TIMESTAMPTZ NOT NULL DEFAULT now(),
    exemple TEXT NOT NULL,
    mots TEXT[] NOT NULL DEFAULT '{}',
    outil TEXT NOT NULL,
    consigne TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    actif BOOLEAN NOT NULL DEFAULT true,
    utilisee INT NOT NULL DEFAULT 0
);
"""

_INCAPABLE = re.compile(r"\b(je ne (?:peux|sais) pas|je n.ai pas (?:acc[èe]s|la possibilit[ée]|d.outil)|je ne suis pas (?:en mesure|capable)|"
                        r"impossible pour moi|pas (?:d.outil|la capacit[ée])|je n.ai pas les moyens|cela d[ée]passe mes)", re.I)
_CORRECTION = re.compile(r"^\W*(?:non\b|pas [çc]a|c.est pas [çc]a|ce n.est pas [çc]a|ce n.est pas ce que|je (?:t.ai|vous ai) demand[ée]|"
                         r"je voulais|j.ai dit|tu t.es tromp[ée]e?|mauvais|faux|ce n.est pas (?:la|le|les) bon)", re.I)
_VIDES = {"les", "des", "une", "un", "le", "la", "de", "du", "moi", "mes", "mon", "ma", "tes", "ton", "ta", "vos", "nos", "pour", "avec",
          "dans", "sur", "est", "que", "qui", "quoi", "eva", "stp", "svp", "peux", "tu", "vous", "fais", "fait", "faire", "donne", "dis",
          "plait", "merci", "bien", "tout", "toute", "toutes", "tous", "aussi", "encore", "cette", "ces", "cet", "son", "sa", "ses"}
_cache: list[dict] | None = None


def _fold(t: str) -> str:
    return unicodedata.normalize("NFKD", (t or "").lower()).encode("ascii", "ignore").decode()


def mots(texte: str) -> list[str]:
    """Mots porteurs de sens (sans accents, sans petits mots), « recettes » → « recette »."""
    out = []
    for m in re.findall(r"[a-z0-9]{3,}", _fold(texte)):
        if m in _VIDES:
            continue
        out.append(m[:-1] if len(m) > 4 and m.endswith("s") else m)
    return list(dict.fromkeys(out))[:12]


# ---------------------------------------------------------------- réglages
async def reglages() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    d = (json.loads(raw) if isinstance(raw, str) else raw) if raw else {}
    return {**DEFAUT, **{k: v for k, v in (d or {}).items() if k in DEFAUT}}


async def regler(**chg) -> dict:
    d = {**await reglages(), **{k: v for k, v in chg.items() if k in DEFAUT and v is not None}}
    d["heure"] = max(0, min(23, int(d["heure"])))
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(d))
    return d


# ---------------------------------------------------------------- 1. noter les ratés
async def noter(genre: str, phrase: str, reponse: str = "", outils: list[str] | None = None, qui: str = "", session: str = "") -> None:
    phrase = (phrase or "").strip()
    if len(phrase) < 3:
        return
    async with get_pool().acquire() as conn:
        deja = await conn.fetchval("SELECT 1 FROM rates WHERE phrase=$1 AND statut='a_voir'", phrase[:500])
        if deja:
            return
        await conn.execute("INSERT INTO rates (qui, session, phrase, reponse, outils, genre) VALUES ($1,$2,$3,$4,$5,$6)",
                           qui or "", session or "", phrase[:500], (reponse or "")[:1500], list(outils or [])[:10], genre)


async def observer(qui: str, session: str, demande: str, reponse: str, outils: list[str], erreurs: list[str], precedente: str = "") -> None:
    """Appelé après chaque tour de conversation : repère un éventuel raté (sans bloquer la conversation)."""
    try:
        if not (await reglages())["actif"]:
            return
        precedente = (precedente or "").split("\n\n[")[0].strip()
        demande = (demande or "").split("\n\n[")[0].strip()
        if precedente and _CORRECTION.match(demande or ""):
            await noter("correction", precedente, f"Correction de la personne : {demande}", outils, qui, session)
        elif reponse and _INCAPABLE.search(reponse[:600]):
            await noter("incapable", demande, reponse, outils, qui, session)
        elif erreurs:
            await noter("erreur_outil", demande, "; ".join(erreurs)[:1500], outils, qui, session)
    except Exception:  # noqa: BLE001 — apprendre ne doit jamais gêner la conversation
        logger.debug("observer", exc_info=True)


async def noter_avis_negatifs() -> int:
    """Les réponses notées 👎 deviennent des ratés à étudier (une fois chacune)."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT f.message_id, f.session_id, f.comment, m.content AS reponse, "
            "(SELECT u.content FROM messages u WHERE u.session_id=m.session_id AND u.role='user' AND u.id < m.id ORDER BY u.id DESC LIMIT 1) AS demande "
            "FROM feedback f JOIN messages m ON m.id=f.message_id WHERE f.rating < 0 AND f.created_at > now() - interval '30 days' "
            "AND NOT EXISTS (SELECT 1 FROM rates r WHERE r.genre='pouce_bas' AND r.resultat = 'msg:' || f.message_id::text)")
        n = 0
        for r in rows:
            if r["demande"]:
                await conn.execute("INSERT INTO rates (session, phrase, reponse, genre, resultat) VALUES ($1,$2,$3,'pouce_bas',$4)",
                                   r["session_id"], r["demande"][:500], ((r["comment"] + " — ") if r["comment"] else "") + (r["reponse"] or "")[:1200],
                                   f"msg:{r['message_id']}")
                n += 1
    return n


# ---------------------------------------------------------------- 3. appliquer les leçons
async def charger() -> list[dict]:
    global _cache
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT id, exemple, mots, outil, consigne FROM lecons WHERE actif ORDER BY id")
    _cache = [dict(r) for r in rows]
    return _cache


def pour(texte: str) -> list[dict]:
    """Leçons qui concernent cette demande : la plupart des mots de l'exemple s'y retrouvent."""
    if not _cache:
        return []
    m = set(mots(texte))
    if not m:
        return []
    out = []
    for l in _cache:
        lm = set(l["mots"] or [])
        if lm and len(lm & m) / len(lm) >= 0.6 and len(lm & m) >= min(2, len(lm)):
            out.append(l)
    return out[:3]


def note(lecons: list[dict]) -> str:
    if not lecons:
        return ""
    lignes = [f"- Pour une demande comme « {l['exemple']} » : utilise l'outil {l['outil']}. {l['consigne']}".strip() for l in lecons]
    return "\n\n[Leçons apprises par EVA sur ses erreurs passées — suis-les]\n" + "\n".join(lignes)


async def compter(lecons: list[dict]) -> None:
    if lecons:
        async with get_pool().acquire() as conn:
            await conn.execute("UPDATE lecons SET utilisee = utilisee + 1 WHERE id = ANY($1::bigint[])", [l["id"] for l in lecons])


# ---------------------------------------------------------------- 2. apprendre (la nuit, ou sur demande)
_CONSIGNE_JUGE = """Tu aides un assistant domestique (EVA) à apprendre de ses erreurs. On te donne une demande d'une personne,
ce qu'EVA a répondu ou fait, et la liste de TOUS les outils d'EVA (nom : description). Dis quel outil EVA aurait dû utiliser.
Réponds UNIQUEMENT par un objet JSON :
{"possible": true, "outil": "<nom exact d'un outil de la liste>", "exemple": "<la demande réécrite de façon générale, sans prénom ni donnée personnelle, en français, 3 à 10 mots>", "consigne": "<une phrase : comment utiliser l'outil pour ce genre de demande>"}
ou, si AUCUN outil ne permet de répondre :
{"possible": false, "manque": "<la fonction qu'il faudrait ajouter à EVA, en une phrase>"}
Si la réponse d'EVA était en fait correcte, réponds {"possible": true, "outil": "", "exemple": "", "consigne": ""}."""


def _json(texte: str) -> dict | None:
    t = re.sub(r"<think>.*?</think>", "", texte or "", flags=re.S)
    deb, fin = t.find("{"), t.rfind("}")
    if deb < 0 or fin <= deb:
        return None
    try:
        return json.loads(t[deb:fin + 1])
    except ValueError:
        return None


async def _juger(rate: dict, registry, modele: str) -> dict | None:
    from . import ollama_client
    outils = "\n".join(f"- {t.name} : {(t.description or '')[:180]}" for t in registry.tools.values()) if hasattr(registry, "tools") else \
        "\n".join(f"- {n} : {(registry.get(n).description or '')[:180]}" for n in registry.names())
    contenu = (f"Demande : {rate['phrase']}\nCe qu'EVA a fait : outils {', '.join(rate['outils']) or 'aucun'} ; réponse : {rate['reponse'][:800]}\n"
               f"Type de raté : {rate['genre']}\n\nOutils d'EVA :\n{outils}")
    rep = await asyncio.wait_for(ollama_client.chat_once([{"role": "system", "content": _CONSIGNE_JUGE},
                                                          {"role": "user", "content": contenu}], model=modele or None), 240)
    return _json(((rep.get("message") or rep).get("content") or ""))


async def _verifier(exemple: str, phrase: str, outil: str, consigne: str, registry) -> bool:
    """Rejoue la demande au banc d'essai, avec la leçon : le modèle de tous les jours choisit-il le bon outil ?"""
    from . import banc_essai, router
    global _cache
    sauve = _cache
    _cache = (sauve or []) + [{"id": 0, "exemple": exemple, "mots": mots(exemple), "outil": outil, "consigne": consigne}]
    try:
        modele = (await router.select(phrase))["model"]
        r = await banc_essai.essayer(phrase, {outil}, modele, registry)
        return r["verdict"] == "ok"
    finally:
        _cache = sauve


async def apprendre(registry, limite: int = MAX_PAR_PASSE) -> dict:
    """Une passe : étudie les ratés en attente, garde les leçons vérifiées. Renvoie un bilan."""
    reg = await reglages()
    await noter_avis_negatifs()
    async with get_pool().acquire() as conn:
        rates = [dict(r) for r in await conn.fetch("SELECT * FROM rates WHERE statut='a_voir' ORDER BY id LIMIT $1", limite)]
    bilan = {"etudies": 0, "lecons": 0, "deja_bon": 0, "manques": 0, "non_verifiees": 0, "erreurs": 0}
    noms = set(registry.names())
    for r in rates:
        bilan["etudies"] += 1
        statut, resultat = "vu", ""
        try:
            j = await _juger(r, registry, reg["modele"])
            if not j:
                statut, resultat = "erreur", "Réponse illisible du modèle"
                bilan["erreurs"] += 1
            elif j.get("possible") is False:
                from . import evolution_demandes
                manque = str(j.get("manque") or r["phrase"])[:200]
                await evolution_demandes.ajouter(r["qui"] or "", manque, r["phrase"][:200])
                statut, resultat = "manque", manque
                bilan["manques"] += 1
                if reg["code"] or reg["auto"]:
                    await _proposer_code(manque, r["phrase"], reg["modele"])
            elif not j.get("outil"):
                statut, resultat = "deja_bon", "La réponse était correcte."
                bilan["deja_bon"] += 1
            elif j["outil"] not in noms:
                statut, resultat = "erreur", f"Outil inconnu proposé : {j['outil']}"
                bilan["erreurs"] += 1
            else:
                exemple = str(j.get("exemple") or r["phrase"])[:150]
                consigne = str(j.get("consigne") or "")[:300]
                if await _verifier(exemple, r["phrase"], j["outil"], consigne, registry):
                    async with get_pool().acquire() as conn:
                        await conn.execute("INSERT INTO lecons (exemple, mots, outil, consigne, source) VALUES ($1,$2,$3,$4,$5)",
                                           exemple, mots(exemple), j["outil"], consigne, r["genre"])
                    statut, resultat = "lecon", f"{exemple} → {j['outil']}"
                    bilan["lecons"] += 1
                else:
                    statut, resultat = "non_verifiee", f"{exemple} → {j['outil']} (le modèle ne suit pas encore la leçon)"
                    bilan["non_verifiees"] += 1
                    if reg["code"] or reg["auto"]:
                        await _proposer_code(f"Faire choisir l'outil {j['outil']} pour « {exemple} »", r["phrase"], reg["modele"])
        except Exception as exc:  # noqa: BLE001
            statut, resultat = "erreur", f"{type(exc).__name__}: {exc}"[:300]
            bilan["erreurs"] += 1
        async with get_pool().acquire() as conn:
            await conn.execute("UPDATE rates SET statut=$2, resultat=$3 WHERE id=$1", r["id"], statut, resultat)
    await charger()
    await regler_dernier(bilan)
    if bilan["etudies"]:
        from . import journal
        await journal.noter("apprentissage", f"{bilan['etudies']} raté(s) étudié(s) : {bilan['lecons']} leçon(s) apprise(s), "
                            f"{bilan['manques']} fonction(s) manquante(s), {bilan['deja_bon']} réponse(s) déjà bonne(s)")
    return bilan


async def regler_dernier(bilan: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ('lecons_dernier', $1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb",
                           json.dumps({**bilan, "le": int(time.time())}))


async def _proposer_code(quoi: str, exemple: str, modele: str) -> None:
    """Prépare (en fond) une proposition de modification du code — page Évolution, jamais appliquée sans accord."""
    try:
        from . import self_mod, taches_fond
        if not self_mod.enabled():
            return
        await taches_fond.lancer(
            f"Amélioration d'EVA : {quoi}"[:100],
            "Tu améliores ton propre code pour corriger ce problème rencontré par la famille : " + quoi +
            f"\nExemple de demande : « {exemple} ».\nLis les fichiers utiles avec self_read (commence par app/harness/selection.py et le "
            "dossier app/harness/tools), puis propose UNE modification minimale avec self_propose (contenu complet des fichiers). "
            "Ne propose rien si tu n'es pas sûr : explique alors ce qu'il faudrait faire.",
            "", "admin", "fond-apprentissage", modele=modele)
    except Exception:  # noqa: BLE001
        logger.info("Proposition de code non lancée", exc_info=True)


# ---------------------------------------------------------------- consultation / gestion
async def etat() -> dict:
    async with get_pool().acquire() as conn:
        lecons = [dict(r) for r in await conn.fetch("SELECT id, cree, exemple, outil, consigne, source, actif, utilisee FROM lecons ORDER BY id DESC LIMIT 200")]
        rates = [dict(r) for r in await conn.fetch("SELECT id, cree, phrase, genre, statut, resultat FROM rates ORDER BY id DESC LIMIT 60")]
        attente = await conn.fetchval("SELECT count(*) FROM rates WHERE statut='a_voir'")
        dernier = await conn.fetchval("SELECT value FROM kv WHERE key='lecons_dernier'")
    for x in lecons + rates:
        x["cree"] = x["cree"].isoformat()
    from . import self_mod
    return {"lecons": lecons, "rates": rates, "en_attente": attente, "reglages": await reglages(), "en_cours": _en_cours,
            "dernier": (json.loads(dernier) if isinstance(dernier, str) else dernier) if dernier else None,
            "evolution": await _etat_auto(), "code_modifiable": self_mod.enabled()}


async def changer(lid: int, actif: bool | None = None, supprimer: bool = False) -> None:
    async with get_pool().acquire() as conn:
        if supprimer:
            await conn.execute("DELETE FROM lecons WHERE id=$1", lid)
        elif actif is not None:
            await conn.execute("UPDATE lecons SET actif=$2 WHERE id=$1", lid, actif)
    await charger()


async def effacer_de(qui: str) -> None:
    """« Mes données » : les ratés notés à partir des messages de la personne."""
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM rates WHERE lower(qui)=$1", (qui or "").lower())


_registre = None
_en_cours = False


def lier(registry) -> None:
    global _registre
    _registre = registry


# ---------------------------------------------------------------- 4. évolution toute seule (option « auto »)
KV_AUTO = "evolution_auto"
DELAI_REDEMARRAGE = 180


async def _etat_auto() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV_AUTO)
    return ((json.loads(raw) if isinstance(raw, str) else raw) or {}) if raw else {}


async def _sauver_auto(d: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV_AUTO, json.dumps(d))


async def _score(registry, modele: str) -> dict:
    from . import banc_essai
    from .config import settings
    return await banc_essai.lancer(modele or settings.ollama_model, registry)


async def evolution_auto(registry, maintenant=None) -> str:
    """EVA applique elle-même ses propositions de code, la nuit, une par nuit au plus, avec garde-fous :
    contrôles (syntaxe, démarrage) avant, banc d'essai avant/après, retour arrière automatique si EVA ne démarre plus
    ou répond moins bien. Les fichiers protégés (sécurité, permissions, ce mécanisme) restent intouchables.
    Renvoie ce qui a été fait (pour les tests et le journal)."""
    from datetime import datetime
    from . import self_mod
    reg = await reglages()
    if not reg["auto"] or not self_mod.enabled():
        return "inactif"
    e = await _etat_auto()
    if e.get("verifier"):                                        # une modification vient d'être appliquée : on vérifie
        if time.time() - e.get("applique_le", 0) < DELAI_REDEMARRAGE:
            return "attente"
        raison = ""
        if self_mod.status().get("boot_error"):
            raison = "EVA ne démarrait plus avec cette modification"
        else:
            try:
                apres = await _score(registry, reg["modele"])
                if apres["score"] < e.get("score_avant", 0):
                    raison = f"banc d'essai {apres['score']}/{apres['total']} au lieu de {e['score_avant']}/{apres['total']}"
            except Exception as exc:  # noqa: BLE001
                raison = f"banc d'essai impossible après la modification ({exc})"
        bilan = {"pid": e.get("pid"), "titre": e.get("titre", ""), "le": int(time.time())}
        if raison:
            try:
                await self_mod.revert(e["pid"])
                bilan.update(resultat="annulee", raison=raison)
            except Exception as exc:  # noqa: BLE001
                bilan.update(resultat="annulation_impossible", raison=f"{raison} ; annulation impossible : {exc}")
        else:
            bilan.update(resultat="gardee")
        await _sauver_auto({"verifier": False, "applique_le": e.get("applique_le", 0), "dernier": bilan})
        logger.info("Évolution automatique : %s", bilan)
        from . import journal
        await journal.noter("evolution", f"« {bilan['titre']} » " + ("gardée : EVA marche aussi bien ou mieux" if bilan["resultat"] == "gardee"
                            else f"annulée toute seule ({bilan.get('raison', '')})"))
        return bilan["resultat"]
    maintenant = maintenant or datetime.now()
    if (maintenant.hour - reg["heure"]) % 24 > 3:                # fenêtre de nuit : de l'heure réglée à +3 h
        return "hors_fenetre"
    if time.time() - e.get("applique_le", 0) < 20 * 3600:          # une par nuit au plus
        return "deja_fait"
    attente = [p for p in await self_mod.list_proposals() if p["status"] == "pending"]
    if not attente:
        return "rien"
    p = attente[-1]                                              # la plus ancienne
    try:
        avant = await _score(registry, reg["modele"])
    except Exception as exc:  # noqa: BLE001
        logger.info("Évolution automatique reportée : banc d'essai impossible (%s)", exc)
        return "banc_impossible"
    await _sauver_auto({"verifier": True, "pid": p["id"], "titre": p["title"], "score_avant": avant["score"],
                        "applique_le": int(time.time()), "dernier": e.get("dernier")})
    try:
        await self_mod.apply(p["id"])                            # contrôles + commit, puis EVA redémarre
    except Exception as exc:  # noqa: BLE001
        await _sauver_auto({"verifier": False, "applique_le": int(time.time()),
                            "dernier": {"pid": p["id"], "titre": p["title"], "le": int(time.time()), "resultat": "refusee", "raison": str(exc)[:300]}})
        from . import journal
        await journal.noter("evolution", f"« {p['title']} » refusée aux contrôles : {str(exc)[:200]}")
        return "refusee"
    from . import journal
    await journal.noter("evolution", f"« {p['title']} » appliquée toute seule (banc d'essai avant : {avant['score']}/{avant['total']}) : EVA redémarre puis vérifie")
    return "appliquee"


async def periodique() -> None:
    """Planificateur (toutes les 15 min) : une passe par nuit, à l'heure réglée, quand personne ne parle à EVA."""
    from datetime import datetime
    reg = await reglages()
    if not reg["actif"] or _registre is None:
        return
    try:
        await evolution_auto(_registre)
    except Exception:  # noqa: BLE001
        logger.warning("Évolution automatique : erreur", exc_info=True)
    maintenant = datetime.now()
    if maintenant.hour != reg["heure"]:
        return
    async with get_pool().acquire() as conn:
        dernier = await conn.fetchval("SELECT value FROM kv WHERE key='lecons_dernier'")
    d = (json.loads(dernier) if isinstance(dernier, str) else dernier) if dernier else {}
    if d and time.time() - d.get("le", 0) < 20 * 3600:
        return
    await apprendre(_registre)
