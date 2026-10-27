"""Satellites vocaux : un petit micro + haut-parleur par pièce (Raspberry Pi, vieux PC, portable) qui écoute « EVA… ».

Le satellite fait comme l'interface web : il repère la parole, la fait transcrire par Whisper (/voice/stt), et ne réagit
qu'au mot d'éveil. Il envoie ensuite la phrase à EVA (POST /api/satellite/demander) et lit la réponse (/voice/tts).
Chaque satellite a son jeton (créé dans Maison › Satellites), sa pièce (« la lumière » = celle de la pièce) et un compte
EVA dont les droits s'appliquent. Une action qui demande l'accord est posée à voix haute : « oui » ou « non »."""
import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time

from . import auth as auth_mod, confidentialite, features, parole, profiles
from .db import get_pool

logger = logging.getLogger("eva-core.satellites")

KV = "satellites"
PREFIXE = "evasat_"
DELAI_ACCORD = 60
DELAI_TOUR = 240
OUI = {"oui", "ouais", "vas-y", "vas y", "d'accord", "ok", "okay", "confirme", "je confirme", "oui vas-y", "go", "bien sûr", "oui oui"}

_registre = None
_workspace = None
_tours: dict[str, "Tour"] = {}
_verrous: dict[str, asyncio.Lock] = {}
_ordres: dict[str, asyncio.Queue] = {}          # satellite → ordres en attente (annonce, commande du PC…)
_reponses: dict[str, asyncio.Future] = {}       # id d'ordre → réponse du satellite
_infos: dict[str, dict] = {}                    # satellite → {capacites, systeme, applis, vu}


def lier(registry, workspace_root) -> None:
    global _registre, _workspace
    _registre, _workspace = registry, workspace_root


async def _charger() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    return ((json.loads(raw) if isinstance(raw, str) else raw) or {}).get("satellites", {}) if raw else {}


async def _ecrire(d: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
                           KV, json.dumps({"satellites": d}))


def _empreinte(j: str) -> str:
    return hashlib.sha256(j.encode()).hexdigest()


def _public(sid: str, s: dict) -> dict:
    i = _infos.get(sid, {})
    return {"id": sid, "nom": s["nom"], "piece": s.get("piece", ""), "compte": s.get("compte", ""), "cree": s.get("cree"),
            "dernier": s.get("dernier"), "en_ligne": bool(s.get("dernier")) and time.time() - s["dernier"] < 180,
            "capacites": i.get("capacites", []), "systeme": i.get("systeme", ""), "applis": i.get("applis", []),
            "version": i.get("version", ""), "a_l_ecoute": time.time() - i.get("vu", 0) < 60,
            "pause": bool(s.get("pause")), "pause_locale": bool(i.get("en_pause"))}


def noter_infos(sid: str, infos: dict, nom: str = "") -> None:
    avant = _infos.get(sid) or {}
    version = str(infos.get("version", ""))[:24]
    if not avant.get("vu") or avant.get("version") != version:
        try:
            from . import journal
            asyncio.get_running_loop().create_task(journal.noter(
                "satellite", f"Satellite « {nom or sid} » connecté ({infos.get('systeme') or '?'}, version {version or '?'})"
                + (f" — mis à jour depuis la {avant['version']}" if avant.get("version") and avant.get("version") != version else "")))
        except RuntimeError:
            pass
    _infos[sid] = {"capacites": [str(x)[:30] for x in (infos.get("capacites") or [])][:20], "systeme": str(infos.get("systeme", ""))[:40],
                   "applis": [str(x)[:40] for x in (infos.get("applis") or [])][:40], "version": str(infos.get("version", ""))[:24],
                   "en_pause": bool(infos.get("en_pause")),
                   "vu": time.time()}


async def attendre_ordres(sid: str, delai: float = 25) -> list[dict]:
    """Appel « long » du satellite : rend les ordres dès qu'il y en a (ou rien au bout de `delai`)."""
    _infos.setdefault(sid, {})["vu"] = time.time()
    q = _ordres.setdefault(sid, asyncio.Queue())
    try:
        premier = await asyncio.wait_for(q.get(), delai)
    except asyncio.TimeoutError:
        return []
    lot = [premier]
    while not q.empty() and len(lot) < 10:
        lot.append(q.get_nowait())
    _infos.setdefault(sid, {})["vu"] = time.time()
    return lot


def recevoir_resultat(oid: str, resultat: dict) -> bool:
    f = _reponses.pop(oid, None)
    if f and not f.done():
        f.set_result(resultat)
        return True
    return False


async def trouver(nom: str) -> list[tuple[str, dict]]:
    """Satellites désignés par leur nom ou leur pièce ; « partout » / « tous » = tous."""
    tous = list((await _charger()).items())
    n = (nom or "").strip().lower()
    if n in ("", "partout", "tous", "toute la maison", "toutes les pièces"):
        return tous
    return [(k, v) for k, v in tous if n in (v["nom"].lower(), v.get("piece", "").lower())] or \
        [(k, v) for k, v in tous if n in v["nom"].lower() or (v.get("piece") and n in v["piece"].lower())]


def ecoute(sid: str) -> bool:
    """Le satellite attend-il des ordres en ce moment (vu il y a moins d'une minute) ?"""
    return time.time() - _infos.get(sid, {}).get("vu", 0) <= 60


async def ordonner(sid: str, ordre: dict, delai: float = 20) -> dict:
    if time.time() - _infos.get(sid, {}).get("vu", 0) > 60:
        return {"error": "Ce satellite n'écoute pas les ordres en ce moment (éteint, ou programme du satellite trop ancien : relance l'installateur)."}
    oid = secrets.token_hex(6)
    f = asyncio.get_running_loop().create_future()
    _reponses[oid] = f
    await _ordres.setdefault(sid, asyncio.Queue()).put({"id": oid, **ordre})
    try:
        return await asyncio.wait_for(f, delai)
    except asyncio.TimeoutError:
        _reponses.pop(oid, None)
        return {"error": "Le satellite n'a pas répondu à temps."}


async def lister() -> list[dict]:
    return [_public(k, v) for k, v in (await _charger()).items()]


async def creer(nom: str, piece: str, compte: str) -> dict:
    nom = str(nom or "").strip()[:40]
    if not nom:
        raise ValueError("Donne un nom au satellite (ex. « Cuisine »).")
    compte = str(compte or "").strip()
    if auth_mod.protected() and compte.lower() not in {u["user"].lower() for u in auth_mod.list_users()}:
        raise ValueError("Compte EVA inconnu.")
    d = await _charger()
    jeton = PREFIXE + secrets.token_urlsafe(32)
    sid = secrets.token_hex(5)
    d[sid] = {"nom": nom, "piece": str(piece or "").strip()[:40], "compte": compte, "empreinte": _empreinte(jeton), "cree": int(time.time())}
    await _ecrire(d)
    return {**_public(sid, d[sid]), "jeton": jeton}


async def regler_pause(sid: str, pause: bool) -> dict:
    """Écoute coupée (pause) ou rétablie depuis EVA ; gardé, donc appliqué aussi quand le satellite se reconnecte."""
    d = await _charger()
    if sid not in d:
        raise ValueError("Satellite introuvable.")
    d[sid]["pause"] = bool(pause)
    await _ecrire(d)
    if ecoute(sid):
        await ordonner(sid, {"type": "ecoute", "actif": not pause}, delai=10)
    return _public(sid, d[sid])


async def renouveler(sid: str) -> dict:
    """Nouveau jeton pour (ré)installer un satellite : l'ancien cesse de marcher."""
    d = await _charger()
    if sid not in d:
        raise ValueError("Satellite introuvable.")
    jeton = PREFIXE + secrets.token_urlsafe(32)
    d[sid]["empreinte"] = _empreinte(jeton)
    await _ecrire(d)
    return {**_public(sid, d[sid]), "jeton": jeton}


async def supprimer(sid: str) -> None:
    d = await _charger()
    d.pop(sid, None)
    await _ecrire(d)


async def qui(jeton: str | None) -> tuple[str, dict] | None:
    if not jeton or not jeton.startswith(PREFIXE):
        return None
    e = _empreinte(jeton)
    for sid, s in (await _charger()).items():
        if hmac.compare_digest(s["empreinte"], e):
            return sid, s
    return None


async def signe_de_vie(sid: str) -> None:
    d = await _charger()
    if sid in d and time.time() - d[sid].get("dernier", 0) > 30:
        d[sid]["dernier"] = int(time.time())
        await _ecrire(d)


def est_oui(texte: str) -> bool:
    t = (texte or "").lower().strip(" .!?,").replace("’", "'")
    return t in OUI or t.startswith(("oui", "vas-y", "d'accord", "ok ", "confirme"))


# ---------------------------------------------------------------- un seul satellite répond (comme l'arbitrage de Jarvis)

FENETRE_EVEIL = 0.4            # les satellites qui ont entendu la même phrase se signalent dans ce délai
RETARD_EVEIL = 2.5             # un signalement plus tardif, pendant qu'un autre satellite répond, est écarté
_manche: dict | None = None


def _a_l_ecoute() -> int:
    return sum(1 for i in _infos.values() if time.time() - i.get("vu", 0) < 90)


async def eveil(sid: str, score: float, suite: bool = False) -> bool:
    """Un satellite a entendu une phrase : a-t-il le droit d'y répondre ? Celui qui l'entend le plus fort (rapport parole/bruit)
    gagne ; les autres se taisent. « suite » : la phrase poursuit une conversation de ce satellite (il garde la main)."""
    global _manche
    now = time.monotonic()
    m = _manche
    if m and m["close"] is not None and now - m["close"] < RETARD_EVEIL and m["gagnant"] != sid and not suite:
        return False                                     # même phrase entendue en retard ailleurs
    if suite or _a_l_ecoute() < 2:
        _manche = {"debut": now, "close": now, "gagnant": sid, "candidats": {sid: score}, "fini": None}
        return True
    if m is None or m["close"] is not None:
        m = _manche = {"debut": now, "close": None, "gagnant": None, "candidats": {}, "fini": asyncio.Event()}
        m["candidats"][sid] = float(score or 0)

        async def clore():
            await asyncio.sleep(FENETRE_EVEIL)
            m["gagnant"] = max(m["candidats"].items(), key=lambda kv: kv[1])[0]
            m["close"] = time.monotonic()
            m["fini"].set()
        asyncio.get_running_loop().create_task(clore())
    else:
        m["candidats"][sid] = max(float(score or 0), m["candidats"].get(sid, 0))
    await m["fini"].wait()
    return m["gagnant"] == sid


# ---------------------------------------------------------------- un tour de conversation

class Tour:
    """Conversation en cours. La file reçoit, dans l'ordre : des phrases d'attente (« attente »), les phrases de la réponse au fil
    de l'eau (« dire »), puis soit une question (accord), soit la fin (« reponse »)."""

    def __init__(self, flux: bool = False):
        self.flux = flux
        self.sortie: asyncio.Queue = asyncio.Queue()
        self.accord: asyncio.Future | None = None
        self.tache: asyncio.Task | None = None

    async def brut(self) -> dict:
        try:
            return await asyncio.wait_for(self.sortie.get(), DELAI_TOUR)
        except asyncio.TimeoutError:
            return {"reponse": "Désolée, je n'ai pas réussi à répondre à temps."}

    async def suivant(self) -> dict:
        """Ancien satellite (sans flux) : seulement la question ou la réponse complète."""
        while True:
            m = await self.brut()
            if "question" in m or "reponse" in m:
                return m


_NOMS = {"device_control": "piloter un appareil", "scene_run": "lancer une scène", "device_hue_scene": "lancer une scène Hue",
         "obs_action": "piloter OBS", "discord_envoyer": "publier sur Discord", "appel_telephone": "appeler",
         "telegram_notify": "envoyer un message Telegram", "gmail_send": "envoyer un e-mail", "calendar_create": "ajouter à l'agenda",
         "navigateur_cliquer": "cliquer sur la page", "navigateur_remplir": "remplir un champ", "pc_ecran_cliquer": "cliquer sur ton écran", "pc_operateur": "prendre la main sur ton ordinateur",
         "pc_commande": "piloter l'ordinateur", "chrome_pc": "agir dans ton Chrome"}


def _phrase_accord(outil: str, args: dict) -> str:
    valeurs = ", ".join(str(v) for v in (args or {}).values() if isinstance(v, (str, int, float)) and str(v).strip())[:160]
    quoi = _NOMS.get(outil, outil.replace("_", " "))
    return confidentialite.caviarder(f"J'ai besoin de ton accord pour {quoi}{f' : {valeurs}' if valeurs else ''}. Tu confirmes ?")


def consigne_piece(piece: str) -> str:
    return (f"La personne te parle à voix haute depuis le satellite de la pièce « {piece} ». Sans autre précision, "
            f"« la lumière », « la prise »… désignent ceux de cette pièce. Réponds en une ou deux phrases courtes, "
            f"faciles à entendre : ni liste, ni tableau, ni lien, ni emoji. Ne dis jamais à voix haute un mot de passe, "
            f"une clé, un numéro de carte ou d'IBAN.")


async def _derouler(tour: Tour, sid: str, s: dict, texte: str) -> None:
    from . import instant, personality, router as model_router, skills as skills_mod
    from .config import settings
    from .harness.loop import run_harness
    from .harness.selection import SubsetRegistry, select_tool_names, voice_needs_tools
    from .memory import load_recent, save_message
    from .sessions import ensure_session, touch_session
    from .traces import TraceRecorder
    session_id = f"satellite-{sid}"
    u = next((x for x in auth_mod.list_users() if x["user"].lower() == s.get("compte", "").lower()), None)
    role, user = (u["role"], u["user"]) if u else ("admin", "")
    ctx = (profiles.user_var.set(user), profiles.role_var.set(role))
    from .harness import contexte as contexte_mod
    ctx_session = contexte_mod.session.set(session_id)        # un rappel demandé ici sonnera sur ce satellite
    accuseur = None
    try:
        await ensure_session(session_id, f"Satellite {s['nom']}")
        k = instant.detect(texte)
        if k:                                           # heure, date, qui est là… : réponse immédiate, sans modèle
            rep = await instant.repondre(k, settings.timezone, user)
            if rep and rep[0]:
                await save_message(session_id, "user", texte)
                await save_message(session_id, "assistant", rep[0])
                await tour.sortie.put({"reponse": confidentialite.caviarder(rep[0]) if not tour.flux else rep[0],
                                       **({"dire_aussi": True} if tour.flux else {})})
                return
        past = await load_recent(session_id)
        piece = s.get("piece") or s["nom"]
        feats = await features.effective(role, user)
        base = features.FeatureRegistry(_registre, feats)
        from . import modules as modules_mod
        noms = [n for n in base.names() if not modules_mod.outil_coupe(n)]
        recent = [texte] + [m["content"] for m in reversed(past) if m["role"] == "user"][:2]
        # Comme l'interface en mode vocal : une phrase de conversation n'a pas besoin des ~4000 tokens d'outils et de compétences.
        from . import weather_intent
        leger = settings.voice_lean and not voice_needs_tools([texte], noms) \
            and not weather_intent.detect(texte, settings.default_city)
        if leger:
            system = settings.voice_system_prompt + f"\nFuseau horaire : {settings.timezone}."
        else:
            system = skills_mod.system_prompt_with_skills(settings.system_prompt, _workspace)
        system += "\n\n" + consigne_piece(piece)
        try:
            perso = await personality.get()
            style = personality.prompt_for(perso)
        except Exception:  # noqa: BLE001
            perso, style = "normal", ""
        if style:
            system += "\n\n" + style
        history = [{"role": "system", "content": system}] + past + [{"role": "user", "content": texte}]
        await save_message(session_id, "user", texte)
        reg = SubsetRegistry(base, [n for n in select_tool_names(recent, noms)])
        choix = await model_router.select(texte, prefer_fast=True)
        trace = TraceRecorder("chat", session_id=session_id, label=texte, model=choix["model"])
        erreurs: list[str] = []
        decoupe = parole.Decoupeur()

        async def dire_attente(t: str) -> None:
            await tour.sortie.put({"attente": t})
        if tour.flux:
            accuseur = parole.Accuseur(dire_attente, perso)

        async def evt(ev: dict) -> None:
            if ev.get("type") == "error":
                erreurs.append(ev.get("message", "erreur"))
            if accuseur:
                await accuseur.observer(ev)
            if tour.flux and ev.get("type") == "token":
                for ph in decoupe.ajouter(ev.get("text", "")):
                    await tour.sortie.put({"dire": confidentialite.caviarder(ph)})

        async def accord(outil: str, args: dict) -> bool:
            if accuseur:
                accuseur.fermer()
            tour.accord = asyncio.get_running_loop().create_future()
            await tour.sortie.put({"question": _phrase_accord(outil, args), "attente": True})
            try:
                return bool(await asyncio.wait_for(tour.accord, DELAI_ACCORD))
            except asyncio.TimeoutError:
                return False
            finally:
                tour.accord = None

        final = await run_harness(history, reg, evt, accord, trace=trace, model=choix["model"],
                                  tools_enabled=bool(choix["tools"] and not leger))
        if accuseur:
            accuseur.fermer()
        if final is None:
            await trace.save(ok=False, error="Erreur du modèle")
            await tour.sortie.put({"reponse": "Désolée, je n'arrive pas à joindre mon cerveau pour l'instant.", "erreur": erreurs[-1:] or "",
                                   **({"dire_aussi": True} if tour.flux else {})})
            return
        tid = await trace.save(ok=True)
        await save_message(session_id, "assistant", final, trace_id=tid)
        await touch_session(session_id)
        if tour.flux:
            reste = decoupe.fin()
            if reste:
                await tour.sortie.put({"dire": confidentialite.caviarder(reste)})
            await tour.sortie.put({"reponse": final})                   # déjà dite phrase par phrase : pour la fenêtre du PC
        else:
            await tour.sortie.put({"reponse": confidentialite.caviarder(final)})
    except Exception as exc:  # noqa: BLE001 — le satellite doit toujours recevoir quelque chose
        logger.exception("Tour de satellite en échec")
        await tour.sortie.put({"reponse": "Désolée, une erreur s'est produite.", "erreur": str(exc)[:200], "dire_aussi": True})
    finally:
        if accuseur:
            accuseur.fermer()
        profiles.user_var.reset(ctx[0])
        profiles.role_var.reset(ctx[1])
        contexte_mod.session.reset(ctx_session)


def _lancer(sid: str, s: dict, texte: str, flux: bool) -> Tour | None:
    texte = str(texte or "").strip()[:1000]
    if not texte:
        return None
    ancien = _tours.get(sid)
    if ancien and ancien.tache and not ancien.tache.done():
        if ancien.accord and not ancien.accord.done():
            ancien.accord.set_result(False)              # nouvelle demande pendant une question : on refuse l'ancienne
        ancien.tache.cancel()
    tour = Tour(flux)
    _tours[sid] = tour
    tour.tache = asyncio.create_task(_derouler(tour, sid, s, texte))
    return tour


async def demander(sid: str, s: dict, texte: str) -> dict:
    tour = _lancer(sid, s, texte, False)
    if tour is None:
        return {"reponse": "Je n'ai rien entendu."}
    return await tour.suivant()


async def flux(tour: Tour):
    """Événements du tour pour un satellite récent, jusqu'à la question ou la fin (une ligne JSON chacun)."""
    while True:
        m = await tour.brut()
        yield json.dumps(m, ensure_ascii=False) + "\n"
        if "question" in m or "reponse" in m:
            return


async def demander_flux(sid: str, s: dict, texte: str):
    tour = _lancer(sid, s, texte, True)
    if tour is None:
        yield json.dumps({"reponse": "Je n'ai rien entendu.", "dire_aussi": True}, ensure_ascii=False) + "\n"
        return
    async for ligne in flux(tour):
        yield ligne


def _accorder(sid: str, texte: str) -> tuple[Tour | None, bool]:
    tour = _tours.get(sid)
    if not tour or not tour.accord or tour.accord.done():
        return None, False
    oui = est_oui(texte)
    tour.accord.set_result(oui)
    return tour, oui


async def repondre(sid: str, texte: str) -> dict:
    tour, oui = _accorder(sid, texte)
    if tour is None:
        return {"reponse": "Il n'y avait rien à confirmer."}
    rep = await tour.suivant()
    if not oui and "reponse" in rep and not rep.get("question"):
        rep["reponse"] = rep["reponse"] or "D'accord, je ne fais rien."
    return rep


async def repondre_flux(sid: str, texte: str):
    tour, _oui = _accorder(sid, texte)
    if tour is None:
        yield json.dumps({"reponse": "Il n'y avait rien à confirmer.", "dire_aussi": True}, ensure_ascii=False) + "\n"
        return
    async for ligne in flux(tour):
        yield ligne
