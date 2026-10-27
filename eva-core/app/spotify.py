"""Spotify : écouter, piloter la lecture et ranger les morceaux reconnus dans une playlist (comme Jarvis).

Liaison (Paramètres › Services connectés, administrateur) : on crée une appli gratuite sur developer.spotify.com, on y colle
l'adresse de retour affichée par EVA, puis on recopie le « Client ID » dans EVA et on clique « Relier » (connexion Spotify,
méthode PKCE : aucun secret stocké). Le pilotage de la lecture demande un compte Spotify Premium ; la recherche et les
playlists marchent avec tous les comptes. Un seul compte Spotify pour la maison."""
import base64
import hashlib
import json
import re
import secrets
import time
from urllib.parse import urlencode

import httpx

from .db import get_pool

KV = "spotify"
API = "https://api.spotify.com/v1"
COMPTES = "https://accounts.spotify.com"
SCOPES = ("user-read-playback-state user-modify-playback-state user-read-currently-playing "
          "playlist-read-private playlist-modify-private playlist-modify-public")
PLAYLIST_RECONNUS = "Reconnu par EVA"
_attente: dict[str, dict] = {}            # state → {verifier, redirect, ts}


class SpotifyError(RuntimeError):
    pass


async def _conf() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    return (json.loads(raw) if isinstance(raw, str) else raw) or {}


async def _ecrire(d: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(d))


async def etat() -> dict:
    c = await _conf()
    return {"client_id": c.get("client_id", ""), "relie": bool(c.get("refresh")), "compte": c.get("compte", ""),
            "premium": c.get("premium"), "playlist_auto": bool(c.get("playlist_auto", True))}


async def regler(client_id: str | None = None, playlist_auto: bool | None = None) -> dict:
    c = await _conf()
    if client_id is not None:
        cid = client_id.strip()
        if cid and not re.fullmatch(r"[0-9a-f]{32}", cid):
            raise SpotifyError("Client ID invalide : 32 caractères (chiffres et lettres a à f), copié depuis developer.spotify.com.")
        if cid != c.get("client_id"):
            c = {"client_id": cid, "playlist_auto": c.get("playlist_auto", True)}        # autre appli : il faut relier à nouveau
    if playlist_auto is not None:
        c["playlist_auto"] = bool(playlist_auto)
    await _ecrire(c)
    return await etat()


async def oublier() -> None:
    c = await _conf()
    await _ecrire({"client_id": c.get("client_id", ""), "playlist_auto": c.get("playlist_auto", True)})


def lien_connexion(client_id: str, redirect: str) -> str:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)
    for k in [k for k, v in _attente.items() if time.time() - v["ts"] > 900]:
        _attente.pop(k, None)
    _attente[state] = {"verifier": verifier, "redirect": redirect, "ts": time.time()}
    return f"{COMPTES}/authorize?" + urlencode({"client_id": client_id, "response_type": "code", "redirect_uri": redirect, "scope": SCOPES,
                                                "state": state, "code_challenge_method": "S256", "code_challenge": challenge})


async def _jeton(donnees: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.post(f"{COMPTES}/api/token", data=donnees)
    except httpx.HTTPError as exc:
        raise SpotifyError(f"Spotify injoignable ({type(exc).__name__}).") from exc
    d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 300:
        raise SpotifyError(f"Spotify a refusé : {d.get('error_description') or d.get('error') or r.status_code}.")
    return d


async def finir_connexion(code: str, state: str) -> dict:
    a = _attente.pop(state or "", None)
    if not a:
        raise SpotifyError("Lien expiré : recommence « Relier » depuis EVA.")
    c = await _conf()
    d = await _jeton({"grant_type": "authorization_code", "code": code, "redirect_uri": a["redirect"], "client_id": c.get("client_id", ""),
                      "code_verifier": a["verifier"]})
    c.update(acces=d["access_token"], refresh=d.get("refresh_token", c.get("refresh")), expire=time.time() + int(d.get("expires_in", 3600)) - 60)
    await _ecrire(c)
    moi = await _api("GET", "/me")
    c = await _conf()
    c.update(compte=moi.get("display_name") or moi.get("id", ""), compte_id=moi.get("id", ""), premium=moi.get("product") == "premium")
    await _ecrire(c)
    return await etat()


async def _acces() -> str:
    c = await _conf()
    if not c.get("refresh"):
        raise SpotifyError("Spotify n'est pas relié (Paramètres › Services connectés › Spotify).")
    if c.get("acces") and time.time() < c.get("expire", 0):
        return c["acces"]
    d = await _jeton({"grant_type": "refresh_token", "refresh_token": c["refresh"], "client_id": c["client_id"]})
    c.update(acces=d["access_token"], refresh=d.get("refresh_token") or c["refresh"], expire=time.time() + int(d.get("expires_in", 3600)) - 60)
    await _ecrire(c)
    return c["acces"]


async def _http(method: str, url: str, **kw) -> httpx.Response:
    """Seul point d'accès réseau vers l'API (remplaçable dans les tests)."""
    try:
        async with httpx.AsyncClient(timeout=15) as cl:
            return await cl.request(method, url, **kw)
    except httpx.HTTPError as exc:
        raise SpotifyError(f"Spotify injoignable ({type(exc).__name__}).") from exc


async def _api(method: str, chemin: str, **kw) -> dict:
    r = await _http(method, API + chemin, headers={"Authorization": f"Bearer {await _acces()}"}, **kw)
    if r.status_code == 204 or not r.content:
        return {}
    try:
        d = r.json()
    except ValueError:
        d = {}
    if r.status_code >= 300:
        msg = (d.get("error") or {}).get("message", "") if isinstance(d.get("error"), dict) else str(d.get("error", ""))
        if r.status_code == 404 and "/me/player" in chemin:
            raise SpotifyError("Aucun appareil Spotify actif : ouvre Spotify sur le téléphone, l'ordinateur ou l'enceinte, puis réessaie.")
        if r.status_code == 403 and "/me/player" in chemin:
            raise SpotifyError("Spotify n'autorise le pilotage de la lecture qu'avec un compte Premium.")
        raise SpotifyError(f"Spotify : {msg or r.status_code}.")
    return d


def _morceau(t: dict) -> dict:
    return {"titre": t.get("name", ""), "artiste": ", ".join(a.get("name", "") for a in t.get("artists") or []),
            "album": (t.get("album") or {}).get("name", ""), "uri": t.get("uri", "")}


async def en_cours() -> dict:
    d = await _api("GET", "/me/player")
    if not d:
        return {"lecture": False, "texte": "Rien ne joue sur Spotify en ce moment."}
    t = _morceau(d.get("item") or {})
    return {"lecture": bool(d.get("is_playing")), "appareil": (d.get("device") or {}).get("name", ""),
            "volume": (d.get("device") or {}).get("volume_percent"), **t}


async def appareils() -> list[dict]:
    d = await _api("GET", "/me/player/devices")
    return [{"id": x["id"], "nom": x.get("name", ""), "type": x.get("type", ""), "actif": x.get("is_active", False)} for x in d.get("devices", [])]


async def _appareil(nom: str) -> str | None:
    if not nom:
        return None
    lst = await appareils()
    x = next((a for a in lst if a["nom"].lower() == nom.lower()), None) or next((a for a in lst if nom.lower() in a["nom"].lower()), None)
    if not x:
        raise SpotifyError(f"Appareil Spotify « {nom} » introuvable. Appareils : {', '.join(a['nom'] for a in lst) or 'aucun (ouvre Spotify quelque part)'}.")
    return x["id"]


async def chercher(q: str, types: str = "track,artist,playlist,album", n: int = 5) -> dict:
    d = await _api("GET", "/search", params={"q": q, "type": types, "limit": n, "market": "FR"})
    return {"morceaux": [_morceau(t) for t in (d.get("tracks") or {}).get("items", []) if t],
            "artistes": [{"nom": a.get("name"), "uri": a.get("uri")} for a in (d.get("artists") or {}).get("items", []) if a],
            "playlists": [{"nom": p.get("name"), "uri": p.get("uri")} for p in (d.get("playlists") or {}).get("items", []) if p],
            "albums": [{"nom": a.get("name"), "artiste": ", ".join(x.get("name", "") for x in a.get("artists") or []), "uri": a.get("uri")}
                       for a in (d.get("albums") or {}).get("items", []) if a]}


async def jouer(recherche: str = "", genre: str = "", appareil: str = "") -> dict:
    """« mets du Daft Punk » (artiste), « joue Bohemian Rhapsody » (morceau), « mets la playlist chill » (playlist)."""
    dev = await _appareil(appareil)
    params = {"device_id": dev} if dev else None
    if not recherche.strip():
        await _api("PUT", "/me/player/play", params=params)
        return {"ok": True, "texte": "Lecture reprise."}
    types = {"artiste": "artist", "morceau": "track", "playlist": "playlist", "album": "album"}.get(genre, "track,artist,playlist,album")
    r = await chercher(recherche, types, 5)
    if genre == "playlist" and r["playlists"]:
        corps, quoi = {"context_uri": r["playlists"][0]["uri"]}, f"la playlist « {r['playlists'][0]['nom']} »"
    elif genre == "album" and r["albums"]:
        corps, quoi = {"context_uri": r["albums"][0]["uri"]}, f"l'album « {r['albums'][0]['nom']} »"
    elif r["artistes"] and (genre == "artiste" or (not genre and r["artistes"][0]["nom"].lower() == recherche.strip().lower())):
        corps, quoi = {"context_uri": r["artistes"][0]["uri"]}, r["artistes"][0]["nom"]
    elif r["morceaux"]:
        m = r["morceaux"][0]
        corps, quoi = {"uris": [m["uri"]]}, f"« {m['titre']} » de {m['artiste']}"
    elif r["playlists"]:
        corps, quoi = {"context_uri": r["playlists"][0]["uri"]}, f"la playlist « {r['playlists'][0]['nom']} »"
    else:
        raise SpotifyError(f"Rien trouvé sur Spotify pour « {recherche} ».")
    await _api("PUT", "/me/player/play", params=params, json=corps)
    return {"ok": True, "texte": f"Je mets {quoi}."}


async def commande(action: str, valeur=None, appareil: str = "") -> dict:
    dev = await _appareil(appareil)
    params = {"device_id": dev} if dev else {}
    if action == "pause":
        await _api("PUT", "/me/player/pause", params=params)
    elif action in ("suivant", "precedent"):
        await _api("POST", f"/me/player/{'next' if action == 'suivant' else 'previous'}", params=params)
    elif action == "volume":
        try:
            v = max(0, min(100, int(str(valeur).strip("% "))))
        except (TypeError, ValueError) as exc:
            raise SpotifyError("Volume : un nombre de 0 à 100.") from exc
        await _api("PUT", "/me/player/volume", params={**params, "volume_percent": v})
    elif action == "aleatoire":
        await _api("PUT", "/me/player/shuffle", params={**params, "state": "true" if valeur in (True, "true", "oui", 1, "1") else "false"})
    elif action == "transferer":
        if not dev:
            raise SpotifyError("Dis vers quel appareil transférer la lecture.")
        await _api("PUT", "/me/player", json={"device_ids": [dev], "play": True})
    else:
        raise SpotifyError(f"Action inconnue : {action}.")
    return {"ok": True}


async def ajouter_reconnu(titre: str, artiste: str) -> dict | None:
    """Morceau reconnu par « c'est quoi cette musique ? » → playlist « Reconnu par EVA » (si l'option est active)."""
    c = await _conf()
    if not c.get("refresh") or not c.get("playlist_auto", True):
        return None
    r = await chercher(f"track:{titre} artist:{artiste}" if artiste else titre, "track", 1)
    if not r["morceaux"]:
        return None
    m = r["morceaux"][0]
    pid = c.get("playlist_id")
    if pid:
        try:
            existants = await _api("GET", f"/playlists/{pid}/tracks", params={"fields": "items(track(uri))", "limit": 100})
            if any((x.get("track") or {}).get("uri") == m["uri"] for x in existants.get("items", [])):
                return {"ajoute": False, "deja": True, **m}
        except SpotifyError:
            pid = None
    if not pid:
        p = await _api("POST", f"/users/{c.get('compte_id', '')}/playlists",
                       json={"name": PLAYLIST_RECONNUS, "public": False, "description": "Morceaux reconnus par EVA (« c'est quoi cette musique ? »)."})
        pid = p.get("id")
        c = await _conf()
        c["playlist_id"] = pid
        await _ecrire(c)
    await _api("POST", f"/playlists/{pid}/tracks", json={"uris": [m["uri"]]})
    return {"ajoute": True, **m}
