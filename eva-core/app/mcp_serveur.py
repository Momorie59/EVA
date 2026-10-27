"""EVA comme serveur MCP : d'autres assistants (Claude Desktop, Cursor, un autre EVA…) utilisent les outils d'EVA.

Transport « Streamable HTTP » (MCP 2025-06-18), sur POST /api/serveur-mcp, réponses JSON simples (pas de flux).
Chaque client reçoit un jeton créé par l'administrateur, rattaché à un compte EVA : les droits de ce compte
s'appliquent (fonctionnalités, modules), et seuls les outils cochés pour ce jeton sont visibles.
Les outils d'action (qui demandent d'habitude « Autoriser ? ») ne sont proposés que si l'administrateur les a cochés
expressément pour ce jeton : personne n'est là pour dire oui pendant l'appel. Chaque appel est noté dans le journal d'accès."""
import asyncio
import hashlib
import hmac
import json
import secrets
import time

from . import auth as auth_mod, features, profiles
from .db import get_pool

KV = "serveur_mcp"
VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
PREFIXE = "evamcp_"
DELAI_OUTIL = 120


async def _charger() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    d = (json.loads(raw) if isinstance(raw, str) else raw) or {}
    return {"jetons": d.get("jetons", {})}


async def _ecrire(d: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
                           KV, json.dumps(d))


def _empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def _registre():
    from .main import registry
    return registry


def outils_exposables() -> list[dict]:
    """Outils qu'un jeton peut recevoir : ni les outils MCP importés (pas de rebond), ni ceux réservés aux agents."""
    reg = _registre()
    out = []
    for n in reg.names():
        t = reg.get(n)
        if t is None or n.startswith("mcp_") or getattr(t, "agents_only", False):
            continue
        out.append({"nom": n, "description": t.description[:200], "action": t.permission.value != "auto",
                    "fonction": features.feature_of(n)})
    return sorted(out, key=lambda x: (x["action"], x["nom"]))


def _public(jid: str, j: dict) -> dict:
    return {"id": jid, "nom": j["nom"], "compte": j["compte"], "outils": j["outils"], "cree": j.get("cree"), "dernier": j.get("dernier"),
            "appels": j.get("appels", 0)}


async def lister() -> list[dict]:
    return [_public(k, v) for k, v in (await _charger())["jetons"].items()]


def _verifier(nom: str, compte: str, outils: list) -> tuple[str, str, list[str]]:
    nom = str(nom or "").strip()[:60]
    if not nom:
        raise ValueError("Donne un nom à ce client (ex. « Claude sur le portable »).")
    compte = str(compte or "").strip()
    if auth_mod.protected() and compte.lower() not in {u["user"].lower() for u in auth_mod.list_users()}:
        raise ValueError("Compte EVA inconnu.")
    connus = {o["nom"] for o in outils_exposables()}
    choix = sorted({str(o) for o in (outils or []) if str(o) in connus})
    if not choix:
        raise ValueError("Coche au moins un outil.")
    return nom, compte, choix


async def creer(nom: str, compte: str, outils: list) -> dict:
    nom, compte, choix = _verifier(nom, compte, outils)
    d = await _charger()
    jeton = PREFIXE + secrets.token_urlsafe(32)
    jid = secrets.token_hex(6)
    d["jetons"][jid] = {"nom": nom, "compte": compte, "outils": choix, "empreinte": _empreinte(jeton), "cree": int(time.time())}
    await _ecrire(d)
    return {**_public(jid, d["jetons"][jid]), "jeton": jeton}       # le jeton n'est montré qu'une fois


async def modifier(jid: str, outils: list) -> dict:
    d = await _charger()
    j = d["jetons"].get(jid)
    if not j:
        raise KeyError(jid)
    _n, _c, j["outils"] = _verifier(j["nom"], j["compte"], outils)
    await _ecrire(d)
    return _public(jid, j)


async def revoquer(jid: str) -> None:
    d = await _charger()
    d["jetons"].pop(jid, None)
    await _ecrire(d)


async def _qui(jeton: str | None) -> tuple[str, dict] | None:
    if not jeton or not jeton.startswith(PREFIXE):
        return None
    e = _empreinte(jeton)
    for jid, j in (await _charger())["jetons"].items():
        if hmac.compare_digest(j["empreinte"], e):
            return jid, j
    return None


async def _noter(jid: str) -> None:
    d = await _charger()
    if jid in d["jetons"]:
        d["jetons"][jid]["dernier"] = int(time.time())
        d["jetons"][jid]["appels"] = d["jetons"][jid].get("appels", 0) + 1
        await _ecrire(d)


async def _outils_du_jeton(j: dict) -> tuple[list, str, str]:
    """Outils réellement utilisables : cochés pour le jeton ET permis au compte (droits actuels, modules)."""
    u = next((x for x in auth_mod.list_users() if x["user"].lower() == j["compte"].lower()), None)
    if auth_mod.protected() and (u is None or u.get("disabled")):
        return [], "", ""
    role, user = (u["role"], u["user"]) if u else ("admin", "")
    feats = await features.effective(role, user)
    reg = features.FeatureRegistry(_registre(), feats)
    from . import modules
    coupes = {n for n in j["outils"] if modules.outil_coupe(n)}
    return [reg.get(n) for n in j["outils"] if reg.get(n) is not None and n not in coupes], role, user


def _erreur(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


async def traiter(jeton: str | None, corps, ip: str = "") -> tuple[int, object]:
    """Renvoie (statut HTTP, corps JSON ou None)."""
    qui = await _qui(jeton)
    if qui is None:
        await auth_mod.audit("denied", "", ip, "MCP", "jeton MCP invalide", 401)
        return 401, {"error": "Jeton MCP invalide ou révoqué."}
    jid, j = qui
    lot = corps if isinstance(corps, list) else [corps]
    reponses = []
    for msg in lot:
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
            if isinstance(msg, dict) and ("result" in msg or "error" in msg):
                continue                                    # réponse du client à une requête du serveur : on n'en envoie pas
            reponses.append(_erreur(msg.get("id") if isinstance(msg, dict) else None, -32600, "Requête JSON-RPC invalide."))
            continue
        if "id" not in msg:                                 # notification (initialized, cancelled…) : rien à répondre
            continue
        reponses.append(await _repondre(jid, j, msg, ip))
    if not reponses:
        return 202, None
    return 200, (reponses if isinstance(corps, list) else reponses[0])


async def _repondre(jid: str, j: dict, msg: dict, ip: str) -> dict:
    mid, methode, p = msg["id"], msg["method"], msg.get("params") or {}
    if methode == "initialize":
        v = p.get("protocolVersion")
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": v if v in VERSIONS else VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "eva", "title": "EVA, l'assistante de la maison", "version": "1.0"},
            "instructions": "Outils d'EVA (maison, listes, recettes, wiki…). Réponds en français à la personne."}}
    if methode == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if methode == "tools/list":
        outils, _r, _u = await _outils_du_jeton(j)
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": t.name, "description": t.description, "inputSchema": t.parameters or {"type": "object", "properties": {}},
             "annotations": {"readOnlyHint": t.permission.value == "auto"}} for t in outils]}}
    if methode == "tools/call":
        nom, args = p.get("name"), p.get("arguments") or {}
        if not isinstance(nom, str) or not isinstance(args, dict):
            return _erreur(mid, -32602, "Paramètres invalides : name et arguments attendus.")
        outils, role, user = await _outils_du_jeton(j)
        t = next((x for x in outils if x.name == nom), None)
        if t is None:
            await auth_mod.audit("denied", j["compte"], ip, f"MCP {nom}", f"outil non autorisé pour « {j['nom']} »", 403)
            return _erreur(mid, -32602, f"Outil inconnu ou non autorisé pour ce client : {nom}.")
        jetons_ctx = (profiles.user_var.set(user), profiles.role_var.set(role))
        try:
            res = await asyncio.wait_for(t.execute(**args), DELAI_OUTIL)
            echec = isinstance(res, dict) and "error" in res
        except TypeError as exc:
            res, echec = {"error": f"Arguments invalides : {exc}"}, True
        except asyncio.TimeoutError:
            res, echec = {"error": "L'outil a mis trop de temps."}, True
        except Exception as exc:  # noqa: BLE001 — l'erreur d'un outil ne doit pas couper le serveur
            res, echec = {"error": f"{type(exc).__name__} : {exc}"[:300]}, True
        finally:
            profiles.user_var.reset(jetons_ctx[0])
            profiles.role_var.reset(jetons_ctx[1])
        await _noter(jid)
        await auth_mod.audit("action", j["compte"], ip, f"MCP {nom}", f"client « {j['nom']} »{' — erreur' if echec else ''}", 200)
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, default=str)[:60000]}], "isError": echec}}
    return _erreur(mid, -32601, f"Méthode non prise en charge : {methode}.")
