"""Services de diffusion et d'appel : OBS (stream/enregistrement), Discord (webhooks), Instagram (statistiques),
Twilio (appel vocal ou SMS vers un numéro de la liste).

Réglages dans Paramètres › Services connectés (administrateur), stockés dans kv « connecteurs ». Les secrets ne
sont jamais renvoyés à l'interface (on dit seulement qu'ils sont enregistrés). Toute action visible de l'extérieur
(lancer un live, publier sur Discord, appeler quelqu'un) passe par un outil qui demande l'accord de la personne."""
import base64
import hashlib
import json
import re
import uuid
from xml.sax.saxutils import escape

import httpx

from .db import get_pool

KV = "connecteurs"
SERVICES = ("obs", "discord", "instagram", "twilio", "acoustid")
SECRETS = {"obs": ("password",), "instagram": ("token",), "twilio": ("token",), "acoustid": ("cle",)}


class ConnecteurError(RuntimeError):
    pass


async def _tout() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    return (json.loads(raw) if isinstance(raw, str) else raw) or {}


async def config(service: str) -> dict:
    return (await _tout()).get(service) or {}


async def _ecrire(d: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
                           KV, json.dumps(d))


def _public(service: str, c: dict) -> dict:
    out = {k: v for k, v in c.items() if k not in SECRETS.get(service, ())}
    for k in SECRETS.get(service, ()):
        out[k + "_enregistre"] = bool(c.get(k))
    if service == "discord":                                  # l'URL d'un webhook suffit pour y écrire : on n'en montre que la fin
        out["salons"] = {n: "…" + u[-6:] for n, u in (c.get("salons") or {}).items()}
    return out


async def etat() -> dict:
    d = await _tout()
    return {s: {"configure": bool(d.get(s)), **_public(s, d.get(s) or {})} for s in SERVICES}


_NUM = re.compile(r"^\+[1-9]\d{6,14}$")
_WEBHOOK = re.compile(r"^https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$")


def _numero(n: str) -> str:
    n = re.sub(r"[\s.\-()]", "", str(n or ""))
    if n.startswith("00"):
        n = "+" + n[2:]
    elif n.startswith("0") and len(n) == 10:                  # numéro français écrit 06…
        n = "+33" + n[1:]
    if not _NUM.match(n):
        raise ConnecteurError(f"Numéro invalide : {n or '(vide)'} (format international, ex. +33612345678).")
    return n


async def enregistrer(service: str, body: dict) -> dict:
    if service not in SERVICES:
        raise ConnecteurError("Service inconnu.")
    d = await _tout()
    ancien = d.get(service) or {}
    b = {k: v for k, v in (body or {}).items() if v is not None}
    if service == "obs":
        hote = str(b.get("hote", ancien.get("hote", ""))).strip()
        if not re.fullmatch(r"[\w.\-]+", hote):
            raise ConnecteurError("Adresse de l'ordinateur OBS invalide (ex. 192.168.1.30).")
        port = int(b.get("port") or ancien.get("port") or 4455)
        c = {"hote": hote, "port": port, "password": str(b.get("password") or ancien.get("password", ""))}
    elif service == "discord":
        salons = dict(ancien.get("salons") or {})
        for nom, url in (b.get("salons") or {}).items():
            nom = str(nom).strip()[:40]
            if url is None or url == "":
                salons.pop(nom, None)
            elif str(url).startswith("…"):                      # inchangé (valeur masquée renvoyée par l'interface)
                continue
            elif not _WEBHOOK.match(str(url).strip()):
                raise ConnecteurError(f"« {nom} » : ce n'est pas une adresse de webhook Discord (https://discord.com/api/webhooks/…).")
            else:
                salons[nom] = str(url).strip()
        for nom in b.get("retirer") or []:
            salons.pop(str(nom), None)
        c = {"salons": salons}
    elif service == "instagram":
        c = {"token": str(b.get("token") or ancien.get("token", "")).strip(), "compte_id": str(b.get("compte_id", ancien.get("compte_id", ""))).strip()}
        if not c["token"]:
            raise ConnecteurError("Jeton d'accès Instagram manquant.")
        if c["compte_id"] and not c["compte_id"].isdigit():
            raise ConnecteurError("L'identifiant du compte Instagram est un nombre.")
    elif service == "acoustid":
        c = {"cle": str(b.get("cle") or ancien.get("cle", "")).strip()}
        if not re.fullmatch(r"[\w-]{6,64}", c["cle"]):
            raise ConnecteurError("Clé AcoustID invalide (« API key » de ton application sur acoustid.org).")
    else:
        sid = str(b.get("sid", ancien.get("sid", ""))).strip()
        if not re.fullmatch(r"AC[0-9a-f]{32}", sid):
            raise ConnecteurError("Account SID Twilio invalide (commence par AC, 34 caractères).")
        contacts = {}
        for nom, num in (b.get("contacts", ancien.get("contacts")) or {}).items():
            if str(nom).strip():
                contacts[str(nom).strip()[:40]] = _numero(num)
        publique = str(b.get("adresse_publique", ancien.get("adresse_publique", "")) or "").strip().rstrip("/")
        if publique and not re.fullmatch(r"https://[\w.\-]+(:\d+)?", publique):
            raise ConnecteurError("Adresse publique d'EVA : https://nom-de-domaine (sans chemin), celle de l'accès à distance.")
        c = {"sid": sid, "token": str(b.get("token") or ancien.get("token", "")).strip(), "de": _numero(b.get("de", ancien.get("de", ""))),
             "contacts": contacts, "adresse_publique": publique}
        if not c["token"]:
            raise ConnecteurError("Auth Token Twilio manquant.")
    d[service] = c
    await _ecrire(d)
    return _public(service, c)


async def oublier(service: str) -> None:
    d = await _tout()
    d.pop(service, None)
    await _ecrire(d)


# ---------------------------------------------------------------- OBS (obs-websocket 5, inclus dans OBS ≥ 28)

def _obs_auth(password: str, salt: str, challenge: str) -> str:
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


async def _obs_connect(c: dict):
    import websockets
    try:
        return await websockets.connect(f"ws://{c['hote']}:{c.get('port', 4455)}", open_timeout=5, max_size=2**22)
    except (OSError, TimeoutError, websockets.exceptions.WebSocketException) as exc:
        raise ConnecteurError(f"OBS ne répond pas sur {c['hote']}:{c.get('port', 4455)} : OBS est-il ouvert, avec le serveur WebSocket activé (Outils › Paramètres du serveur WebSocket) ?") from exc


async def obs_requetes(reqs: list[tuple[str, dict | None]], c: dict | None = None) -> list[dict]:
    """Ouvre une connexion, s'identifie, envoie les requêtes dans l'ordre, renvoie leurs réponses."""
    c = c or await config("obs")
    if not c:
        raise ConnecteurError("OBS n'est pas encore relié (Paramètres › Services connectés).")
    ws = await _obs_connect(c)
    try:
        hello = json.loads(await ws.recv())
        ident = {"rpcVersion": 1, "eventSubscriptions": 0}
        a = (hello.get("d") or {}).get("authentication")
        if a:
            if not c.get("password"):
                raise ConnecteurError("OBS demande un mot de passe : renseigne-le dans Services connectés.")
            ident["authentication"] = _obs_auth(c["password"], a["salt"], a["challenge"])
        await ws.send(json.dumps({"op": 1, "d": ident}))
        rep = json.loads(await ws.recv())
        if rep.get("op") != 2:
            raise ConnecteurError("OBS a refusé la connexion : vérifie le mot de passe.")
        out = []
        for typ, data in reqs:
            rid = uuid.uuid4().hex
            await ws.send(json.dumps({"op": 6, "d": {"requestType": typ, "requestId": rid, **({"requestData": data} if data else {})}}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("op") == 7 and m["d"].get("requestId") == rid:
                    break
            st = m["d"].get("requestStatus") or {}
            if not st.get("result"):
                raise ConnecteurError(f"OBS : {st.get('comment') or typ + ' refusé'} (code {st.get('code')}).")
            out.append(m["d"].get("responseData") or {})
        return out
    except Exception as exc:
        if isinstance(exc, ConnecteurError):
            raise
        raise ConnecteurError(f"Échange avec OBS interrompu ({type(exc).__name__}). Si OBS a fermé la connexion, vérifie le mot de passe.") from exc
    finally:
        await ws.close()


async def obs_etat() -> dict:
    s, r, sc = await obs_requetes([("GetStreamStatus", None), ("GetRecordStatus", None), ("GetSceneList", None)])
    return {"en_direct": bool(s.get("outputActive")), "duree_direct": s.get("outputTimecode", ""),
            "enregistre": bool(r.get("outputActive")), "duree_enregistrement": r.get("outputTimecode", ""),
            "scene": sc.get("currentProgramSceneName", ""), "scenes": [x.get("sceneName") for x in reversed(sc.get("scenes") or [])]}


OBS_ACTIONS = {"demarrer_live": "StartStream", "arreter_live": "StopStream", "demarrer_enregistrement": "StartRecord",
               "arreter_enregistrement": "StopRecord", "pause_enregistrement": "PauseRecord", "reprendre_enregistrement": "ResumeRecord",
               "demarrer_replay": "StartReplayBuffer", "sauver_replay": "SaveReplayBuffer", "scene": "SetCurrentProgramScene"}


async def obs_action(action: str, scene: str = "") -> dict:
    if action not in OBS_ACTIONS:
        raise ConnecteurError(f"Action OBS inconnue : {action}.")
    if action == "scene":
        noms = (await obs_etat())["scenes"]
        choix = next((n for n in noms if n.lower() == scene.strip().lower()), None) or next((n for n in noms if scene.strip().lower() in n.lower()), None)
        if not scene.strip() or not choix:
            raise ConnecteurError(f"Scène introuvable. Scènes OBS : {', '.join(noms) or 'aucune'}.")
        await obs_requetes([("SetCurrentProgramScene", {"sceneName": choix})])
        return {"ok": True, "scene": choix}
    await obs_requetes([(OBS_ACTIONS[action], None)])
    return {"ok": True, "action": action}


# ---------------------------------------------------------------- Discord (webhooks : aucun bot à héberger)

async def _http(method: str, url: str, **kw) -> httpx.Response:
    """Seul point d'accès réseau des services web (remplaçable dans les tests)."""
    try:
        async with httpx.AsyncClient(timeout=15) as cl:
            return await cl.request(method, url, **kw)
    except httpx.HTTPError as exc:
        raise ConnecteurError(f"Service injoignable ({type(exc).__name__}).") from exc


async def discord_envoyer(salon: str, message: str) -> dict:
    salons = (await config("discord")).get("salons") or {}
    if not salons:
        raise ConnecteurError("Aucun salon Discord relié (Paramètres › Services connectés).")
    nom = next((n for n in salons if n.lower() == (salon or "").strip().lower()), None) or (next(iter(salons)) if len(salons) == 1 and not salon else None)
    if not nom:
        raise ConnecteurError(f"Salon Discord inconnu. Salons reliés : {', '.join(salons)}.")
    message = str(message or "").strip()
    if not message:
        raise ConnecteurError("Message vide.")
    r = await _http("POST", salons[nom], json={"content": message[:2000], "username": "EVA", "allowed_mentions": {"parse": []}})
    if r.status_code >= 300:
        raise ConnecteurError(f"Discord a refusé le message ({r.status_code}).")
    return {"ok": True, "salon": nom}


# ---------------------------------------------------------------- Instagram (API Graph, compte pro ou créateur)

async def instagram_stats(nb: int = 5) -> dict:
    c = await config("instagram")
    if not c:
        raise ConnecteurError("Instagram n'est pas relié (Paramètres › Services connectés).")
    base, moi = ("https://graph.facebook.com/v21.0", c["compte_id"]) if c.get("compte_id") else ("https://graph.instagram.com/v21.0", "me")
    r = await _http("GET", f"{base}/{moi}", params={"fields": "username,followers_count,follows_count,media_count", "access_token": c["token"]})
    p = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 300 or "error" in p:
        raise ConnecteurError(f"Instagram : {(p.get('error') or {}).get('message', r.status_code)} (jeton expiré ? il dure 60 jours).")
    m = await _http("GET", f"{base}/{moi}/media", params={"fields": "caption,like_count,comments_count,timestamp,permalink,media_type",
                                                          "limit": max(1, min(int(nb or 5), 20)), "access_token": c["token"]})
    medias = (m.json() or {}).get("data", []) if m.status_code < 300 else []
    return {"compte": p.get("username", ""), "abonnes": p.get("followers_count"), "abonnements": p.get("follows_count"),
            "publications": p.get("media_count"),
            "dernieres": [{"date": (x.get("timestamp") or "")[:10], "legende": (x.get("caption") or "")[:120], "j_aime": x.get("like_count"),
                           "commentaires": x.get("comments_count"), "lien": x.get("permalink", "")} for x in medias]}


# ---------------------------------------------------------------- Twilio (appel avec message lu, ou SMS)

def _contact(c: dict, qui: str) -> tuple[str, str]:
    contacts = c.get("contacts") or {}
    nom = next((n for n in contacts if n.lower() == (qui or "").strip().lower()), None)
    if not nom:                                               # jamais un numéro libre : seulement la liste validée par l'administrateur
        raise ConnecteurError(f"« {qui} » n'est pas dans les contacts d'appel. Contacts : {', '.join(contacts) or 'aucun'} (Paramètres › Services connectés).")
    return nom, contacts[nom]


async def twilio(qui: str, message: str, sms: bool = False) -> dict:
    c = await config("twilio")
    if not c:
        raise ConnecteurError("Les appels ne sont pas configurés (Twilio, Paramètres › Services connectés).")
    nom, num = _contact(c, qui)
    message = re.sub(r"\s+", " ", str(message or "")).strip()
    if not message:
        raise ConnecteurError("Message vide.")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{c['sid']}/{'Messages' if sms else 'Calls'}.json"
    data = {"To": num, "From": c["de"]}
    from . import profiles
    de_la_part = (profiles.user_var.get() or "").strip()
    # Comme Jarvis : l'appel dit tout de suite qu'il vient d'un assistant automatique, jamais d'une personne.
    if sms:
        data["Body"] = f"[EVA, assistante automatique{' de ' + de_la_part if de_la_part else ''}] {message}"[:640]
    else:
        intro = escape(f"Bonjour, ici EVA, l'assistante automatique de la maison{', de la part de ' + de_la_part if de_la_part else ''}. Voici le message.")
        txt = escape(message[:500])
        data["Twiml"] = (f'<Response><Say language="fr-FR">{intro}</Say><Pause length="1"/><Say language="fr-FR">{txt}</Say><Pause length="1"/>'
                         f'<Say language="fr-FR">Je répète. {txt}</Say></Response>')
    r = await _http("POST", url, data=data, auth=(c["sid"], c["token"]))
    if r.status_code >= 300:
        try:
            msg = r.json().get("message", "")
        except ValueError:
            msg = ""
        raise ConnecteurError(f"Twilio a refusé : {msg or r.status_code}.")
    return {"ok": True, "contact": nom, "type": "SMS" if sms else "appel"}


async def tester(service: str) -> dict:
    if service == "obs":
        return await obs_etat()
    if service == "instagram":
        s = await instagram_stats(1)
        return {"compte": s["compte"], "abonnes": s["abonnes"]}
    if service == "twilio":
        c = await config("twilio")
        r = await _http("GET", f"https://api.twilio.com/2010-04-01/Accounts/{c.get('sid', '')}.json", auth=(c.get("sid", ""), c.get("token", "")))
        if r.status_code >= 300:
            raise ConnecteurError("Twilio refuse ces identifiants.")
        return {"compte": r.json().get("friendly_name", "")}
    if service == "acoustid":
        from . import musique
        try:
            await musique.chercher(30, "AQAAAA")
        except musique.MusiqueError as exc:
            if "refusée" in str(exc):
                raise ConnecteurError(str(exc)) from exc
        return {"ok": True}
    if service == "discord":
        return {"salons": list(((await config("discord")).get("salons") or {}))}
    raise ConnecteurError("Service inconnu.")
