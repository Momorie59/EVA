"""Connexion à EVA par identifiant + mot de passe — facultative, à activer dans Paramètres › Sécurité.

Tant qu'aucun compte n'est créé, EVA reste ouverte comme avant (réseau local de confiance) : aucun risque de se retrouver bloqué dehors.
Le premier compte créé est administrateur ; il peut ensuite ajouter d'autres utilisateurs (rôle « admin » ou « user »).
Une fois un compte créé, toute l'API, le WebSocket et la voix exigent une session. Les mots de passe sont conservés hachés (scrypt) ;
les sessions sont des jetons aléatoires dont seule l'empreinte est stockée, valables 30 jours et révocables.
Le jeton EVA_AUTH_TOKEN (variable d'environnement) continue de fonctionner pour les scripts : il compte comme administrateur « (jeton) ».
Un journal d'accès (table audit_log, 90 jours) garde la trace des connexions, échecs, refus et actions qui modifient quelque chose."""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time

from .config import settings
from .db import get_pool

logger = logging.getLogger("eva-core")

SESSION_DAYS = 30
USER_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")
MIN_PASSWORD = max(8, int(os.getenv("EVA_MIN_PASSWORD", "12") or 12))      # NIS2 : mots de passe robustes (12 par défaut ; 8 minimum absolu)
MAX_FAILS = 5
LOCK_SECONDS = 60

AUDIT_DAYS = max(30, int(os.getenv("EVA_AUDIT_DAYS", "365") or 365))             # NIS2 : traçabilité (1 an par défaut)
from .profiles import ROLES      # admin | user (adulte) | teen | child | guest
_users: dict[str, dict] = {}            # nom en minuscules → {"name", "salt", "hash", "role", "disabled", "created"}
_fails: dict[str, list[float]] = {}
_valid_cache: dict[str, tuple[float, str]] = {}   # empreinte → (fin de validité du cache 15 s, nom d'utilisateur)
_DUMMY_SALT = bytes(16)
denied_seen: dict[str, float] = {}      # limitation du journal : une ligne « refus » par minute et par adresse
ws_seen: dict[str, float] = {}


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _hash(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32).hex()


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def load() -> None:
    """Relit les comptes ; migre l'ancien compte unique (kv « auth_account ») en administrateur."""
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key='auth_account'")
        if raw:
            old = json.loads(raw) if isinstance(raw, str) else raw
            if old and old.get("hash") and not await conn.fetchval("SELECT 1 FROM auth_users LIMIT 1"):
                await conn.execute(
                    "INSERT INTO auth_users (name, display, salt, hash, role) VALUES ($1,$2,$3,$4,'admin') ON CONFLICT DO NOTHING",
                    old["user"].lower(), old["user"], old["salt"], old["hash"])
                await conn.execute("UPDATE auth_sessions SET username=$1 WHERE username=''", old["user"].lower())
            await conn.execute("DELETE FROM kv WHERE key='auth_account'")
        rows = await conn.fetch("SELECT name, display, salt, hash, role, disabled, created, COALESCE(totp, '') AS totp FROM auth_users")
        await conn.execute("DELETE FROM audit_log WHERE ts < now() - ($1 || ' days')::interval", str(AUDIT_DAYS))
    _users.clear()
    for r in rows:
        _users[r["name"]] = {"name": r["display"], "salt": r["salt"], "hash": r["hash"], "role": r["role"],
                             "disabled": r["disabled"], "created": r["created"].isoformat(), "totp": r["totp"]}
    _valid_cache.clear()


def login_required() -> bool:
    return bool(_users)


def protected() -> bool:
    """Vrai si l'accès demande une preuve : compte créé ou jeton d'environnement défini."""
    return bool(_users) or bool(settings.auth_token)


def _admins_left(excluding: str | None = None) -> int:
    return sum(1 for k, u in _users.items() if u["role"] == "admin" and not u["disabled"] and k != excluding)


async def identify(token: str | None) -> dict | None:
    """Qui est derrière ce jeton ? {"user", "role"} ou None si accès refusé. Accès libre : administrateur anonyme."""
    if not protected():
        return {"user": "", "role": "admin"}
    if not token:
        return None
    if settings.auth_token and hmac.compare_digest(token, settings.auth_token):
        return {"user": "(jeton)", "role": "admin"}
    if not _users:
        return None
    d = _digest(token)
    now = time.time()
    hit = _valid_cache.get(d)
    name = hit[1] if hit and hit[0] > now else None
    if name is None:
        async with get_pool().acquire() as conn:
            name = await conn.fetchval("SELECT username FROM auth_sessions WHERE token_hash=$1 AND expires > now()", d)
        if not name:
            return None
        _valid_cache[d] = (now + 15, name)
    u = _users.get(name)
    if not u or u["disabled"]:
        return None
    return {"user": u["name"], "role": u["role"]}


async def check(token: str | None) -> bool:
    """Le jeton donne-t-il accès ? (jeton d'environnement ou session valide)"""
    return await identify(token) is not None


def bearer(header: str | None) -> str | None:
    if header and header.startswith("Bearer "):
        return header[7:].strip() or None
    return None


def _valid_new_credentials(user: str, password: str) -> None:
    if not USER_RE.match(user or ""):
        raise AuthError("Identifiant : 3 à 32 caractères (lettres, chiffres, . _ -).")
    if len(password or "") < MIN_PASSWORD:
        raise AuthError(f"Mot de passe : {MIN_PASSWORD} caractères minimum.")
    if (password or "").lower() == (user or "").lower():
        raise AuthError("Le mot de passe ne doit pas être identique à l'identifiant.")


# ---------- journal d'accès ----------

async def audit(kind: str, user: str = "", ip: str = "", action: str = "", detail: str = "", status: int = 0) -> None:
    """Écrit une ligne du journal. Ne doit jamais faire échouer la requête qui l'appelle."""
    try:
        async with get_pool().acquire() as conn:
            await conn.execute("INSERT INTO audit_log (username, ip, kind, action, detail, status) VALUES ($1,$2,$3,$4,$5,$6)",
                               (user or "")[:64], (ip or "")[:64], kind[:16], action[:200], detail[:400], int(status))
    except Exception:  # noqa: BLE001
        logger.warning("Journal d'accès : écriture impossible", exc_info=True)


async def audit_list(user: str = "", kind: str = "", q: str = "", limit: int = 200, before: int = 0) -> list[dict]:
    cond, args = ["true"], []
    def add(sql, val):
        args.append(val); cond.append(sql.replace("?", f"${len(args)}"))
    if user: add("lower(username) = lower(?)", user)
    if kind: add("kind = ?", kind)
    if q: add("(action ILIKE ? OR detail ILIKE ? OR ip ILIKE ?)", f"%{q}%")
    if before: add("id < ?", before)
    limit = max(1, min(int(limit or 200), 1000))
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(f"SELECT id, ts, username, ip, kind, action, detail, status FROM audit_log WHERE {' AND '.join(cond)} ORDER BY id DESC LIMIT {limit}", *args)
    return [{**dict(r), "ts": r["ts"].isoformat()} for r in rows]


# ---------- comptes ----------

def public_user(u: dict) -> dict:
    return {"user": u["name"], "role": u["role"], "disabled": u["disabled"], "created": u["created"], "mfa": bool(u.get("totp"))}


async def _insert_user(user: str, password: str, role: str) -> None:
    _valid_new_credentials(user, password)
    if role not in ROLES:
        raise AuthError("Rôle inconnu.")
    key = user.lower()
    if key in _users:
        raise AuthError("Cet identifiant existe déjà.", 409)
    salt = secrets.token_bytes(16)
    h = await asyncio.to_thread(_hash, password, salt)
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO auth_users (name, display, salt, hash, role) VALUES ($1,$2,$3,$4,$5)", key, user, salt.hex(), h, role)
    _users[key] = {"name": user, "salt": salt.hex(), "hash": h, "role": role, "disabled": False, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "totp": ""}


async def _new_session(user: str, agent: str) -> dict:
    token = secrets.token_urlsafe(32)
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM auth_sessions WHERE expires < now()")
        await conn.execute("INSERT INTO auth_sessions (token_hash, expires, agent, username) VALUES ($1, now() + ($2 || ' days')::interval, $3, $4)",
                           _digest(token), str(SESSION_DAYS), agent[:120], user.lower())
    return {"token": token, "days": SESSION_DAYS}


async def setup(user: str, password: str, agent: str = "") -> dict:
    """Crée le premier compte (administrateur) et ouvre sa session."""
    if _users:
        raise AuthError("Un compte existe déjà.", 409)
    await _insert_user(user, password, "admin")
    return {**await _new_session(user, agent), "role": "admin"}


async def add_user(user: str, password: str, role: str = "user") -> dict:
    await _insert_user(user, password, role)
    return public_user(_users[user.lower()])


def list_users() -> list[dict]:
    return [public_user(u) for u in sorted(_users.values(), key=lambda u: u["name"].lower())]


async def _revoke_user_sessions(key: str, keep: str | None = None) -> int:
    async with get_pool().acquire() as conn:
        if keep:
            n = await conn.fetchval("WITH d AS (DELETE FROM auth_sessions WHERE username=$1 AND token_hash <> $2 RETURNING 1) SELECT count(*) FROM d", key, _digest(keep))
        else:
            n = await conn.fetchval("WITH d AS (DELETE FROM auth_sessions WHERE username=$1 RETURNING 1) SELECT count(*) FROM d", key)
    _valid_cache.clear()
    return int(n or 0)


async def update_user(user: str, role: str | None = None, disabled: bool | None = None, password: str | None = None) -> dict:
    key = (user or "").lower()
    u = _users.get(key)
    if not u:
        raise AuthError("Utilisateur introuvable.", 404)
    new_role = role if role is not None else u["role"]
    new_disabled = u["disabled"] if disabled is None else bool(disabled)
    if new_role not in ROLES:
        raise AuthError("Rôle inconnu.")
    if u["role"] == "admin" and not u["disabled"] and (new_role != "admin" or new_disabled) and _admins_left(excluding=key) == 0:
        raise AuthError("Il faut garder au moins un administrateur actif.", 409)
    salt_hex, hash_hex = u["salt"], u["hash"]
    if password is not None:
        _valid_new_credentials(u["name"], password)
        salt = secrets.token_bytes(16)
        salt_hex, hash_hex = salt.hex(), await asyncio.to_thread(_hash, password, salt)
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE auth_users SET role=$2, disabled=$3, salt=$4, hash=$5 WHERE name=$1", key, new_role, new_disabled, salt_hex, hash_hex)
    u.update(role=new_role, disabled=new_disabled, salt=salt_hex, hash=hash_hex)
    if password is not None or new_disabled:
        await _revoke_user_sessions(key)
    return public_user(u)


async def delete_user(user: str, actor: str = "") -> None:
    key = (user or "").lower()
    u = _users.get(key)
    if not u:
        raise AuthError("Utilisateur introuvable.", 404)
    if key == (actor or "").lower():
        raise AuthError("Tu ne peux pas supprimer ton propre compte (désactive la connexion ou demande à un autre administrateur).", 409)
    if u["role"] == "admin" and not u["disabled"] and _admins_left(excluding=key) == 0:
        raise AuthError("Il faut garder au moins un administrateur actif.", 409)
    await _revoke_user_sessions(key)
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM auth_users WHERE name=$1", key)
    _users.pop(key, None)


# ---------- connexion / sessions ----------

def _throttle(key: str) -> None:
    now = time.time()
    recent = [t for t in _fails.get(key, []) if now - t < LOCK_SECONDS * 10]
    _fails[key] = recent
    if len(recent) >= MAX_FAILS and now - recent[-1] < LOCK_SECONDS:
        raise AuthError(f"Trop d'essais. Réessaie dans {int(LOCK_SECONDS - (now - recent[-1])) + 1} secondes.", 429)


async def _verify_user_password(u: dict | None, password: str) -> bool:
    # même durée de calcul que le compte existe ou non : on ne révèle pas quels identifiants existent
    salt = bytes.fromhex(u["salt"]) if u else _DUMMY_SALT
    h = await asyncio.to_thread(_hash, password or "", salt)
    return bool(u) and hmac.compare_digest(h, u["hash"])


async def _verify_password(user: str, password: str, key: str) -> dict:
    u = _users.get((user or "").lower())
    if u is None:
        raise AuthError("Cette action demande un compte (pas le jeton d'environnement).", 400)
    _throttle(key)
    if not await _verify_user_password(u, password):
        _fails.setdefault(key, []).append(time.time())
        raise AuthError("Mot de passe incorrect.", 401)
    _fails.pop(key, None)
    return u


async def login(user: str, password: str, ip: str = "", agent: str = "", code: str = "") -> dict:
    if not _users:
        raise AuthError("La connexion n'est pas activée.", 400)
    key = f"{ip}|{(user or '').lower()}"
    _throttle(key)
    u = _users.get((user or "").lower())
    ok = await _verify_user_password(u, password)
    if not ok or u["disabled"]:
        _fails.setdefault(key, []).append(time.time())
        reason = "compte désactivé" if ok else ("mot de passe incorrect" if u else "identifiant inconnu")
        await audit("login_fail", (user or "")[:64], ip, "Connexion refusée", reason, 401)
        await _alert_if_bruteforce(key, user, ip)
        raise AuthError("Identifiant ou mot de passe incorrect.", 401)
    if u.get("totp"):                                   # second facteur (NIS2 : authentification multifacteur)
        if not (code or "").strip():
            raise AuthError("mfa_required", 401)         # mot de passe juste : on demande seulement le code, sans compter d'échec
        if not verify_totp(u["name"].lower(), u["totp"], code):
            _fails.setdefault(key, []).append(time.time())
            await audit("login_fail", u["name"], ip, "Connexion refusée", "code à deux facteurs invalide", 401)
            await _alert_if_bruteforce(key, user, ip)
            raise AuthError("Code à deux facteurs invalide.", 401)
    _fails.pop(key, None)
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE auth_users SET last_login=now() WHERE name=$1", (user or "").lower())
    await audit("login", u["name"], ip, "Connexion", agent[:120], 200)
    return {**await _new_session(u["name"], agent), "user": u["name"], "role": u["role"]}


# ---------- alerte d'incident : essais de connexion répétés ----------

_alerted: dict[str, float] = {}


async def _alert_if_bruteforce(key: str, user: str, ip: str) -> None:
    """Après MAX_FAILS échecs : une ligne « alerte » au journal et un message Telegram (au plus un par 10 min et par clé)."""
    if len(_fails.get(key, [])) < MAX_FAILS or time.time() - _alerted.get(key, 0) < 600:
        return
    _alerted[key] = time.time()
    await audit("alert", (user or "")[:64], ip, "Essais de connexion répétés", f"{MAX_FAILS} échecs de suite — verrouillage {LOCK_SECONDS} s", 429)
    try:
        from . import telegram
        await telegram.notify(f"⚠️ EVA : {MAX_FAILS} échecs de connexion de suite pour « {(user or '')[:32]} » depuis {ip or 'adresse inconnue'}. Si ce n'est pas toi, change les mots de passe.")
    except Exception:  # noqa: BLE001 — Telegram n'est pas obligatoire
        pass


# ---------- double authentification (TOTP, RFC 6238) — compatible Google Authenticator, Aegis, 2FAS, FreeOTP… ----------

_pending_totp: dict[str, str] = {}
_last_step: dict[str, int] = {}


def _totp_code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(key, step.to_bytes(8, "big"), "sha1").digest()
    o = mac[-1] & 15
    return f"{(int.from_bytes(mac[o:o + 4], 'big') & 0x7FFFFFFF) % 1_000_000:06d}"


def verify_totp(name: str, secret: str, code: str, now: float | None = None) -> bool:
    code = re.sub(r"\s", "", code or "")
    if not re.fullmatch(r"\d{6}", code):
        return False
    cur = int((now if now is not None else time.time()) // 30)
    for st in (cur, cur - 1, cur + 1):
        if hmac.compare_digest(_totp_code(secret, st), code):
            if _last_step.get(name, -1) >= st:           # un code ne sert qu'une fois
                return False
            _last_step[name] = st
            return True
    return False


async def mfa_begin(user: str) -> dict:
    u = _users.get((user or "").lower())
    if u is None:
        raise AuthError("Cette action demande un compte (pas le jeton d'environnement).", 400)
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    _pending_totp[u["name"].lower()] = secret
    from urllib.parse import quote
    return {"secret": secret, "uri": f"otpauth://totp/EVA:{quote(u['name'])}?secret={secret}&issuer=EVA&digits=6&period=30"}


async def mfa_enable(user: str, code: str) -> None:
    key = (user or "").lower()
    secret = _pending_totp.get(key)
    if not secret:
        raise AuthError("Commence par « Activer la double authentification ».", 400)
    if not verify_totp(key, secret, code):
        raise AuthError("Code invalide : vérifie l'heure du téléphone et réessaie.", 400)
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE auth_users SET totp=$1 WHERE name=$2", secret, key)
    _users[key]["totp"] = secret
    _pending_totp.pop(key, None)


async def mfa_disable(user: str, password: str, ip: str = "") -> None:
    u = await _verify_password(user, password, f"{ip}|{(user or '').lower()}")
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE auth_users SET totp='' WHERE name=$1", u["name"].lower())
    u["totp"] = ""


async def logout(token: str | None) -> None:
    if token:
        async with get_pool().acquire() as conn:
            await conn.execute("DELETE FROM auth_sessions WHERE token_hash=$1", _digest(token))
        _valid_cache.pop(_digest(token), None)


async def logout_all(user: str, keep: str | None = None) -> int:
    """Déconnecte les autres appareils de cet utilisateur."""
    return await _revoke_user_sessions((user or "").lower(), keep)


async def sessions_list() -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT token_hash, username, created, expires, agent FROM auth_sessions WHERE expires > now() ORDER BY created DESC")
    return [{"id": r["token_hash"], "user": (_users.get(r["username"]) or {}).get("name", r["username"]), "created": r["created"].isoformat(),
             "expires": r["expires"].isoformat(), "agent": r["agent"]} for r in rows]


async def revoke_session(sid: str) -> bool:
    async with get_pool().acquire() as conn:
        n = await conn.fetchval("WITH d AS (DELETE FROM auth_sessions WHERE token_hash=$1 RETURNING 1) SELECT count(*) FROM d", sid)
    _valid_cache.clear()
    return bool(n)


async def change_password(user: str, current: str, new: str, keep: str | None, ip: str = "") -> int:
    """Change son propre mot de passe ; les autres appareils sont déconnectés, celui-ci reste connecté."""
    u = await _verify_password(user, current, f"{ip}|pw|{user.lower()}")
    _valid_new_credentials(u["name"], new)
    salt = secrets.token_bytes(16)
    h = await asyncio.to_thread(_hash, new, salt)
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE auth_users SET salt=$2, hash=$3 WHERE name=$1", u["name"].lower(), salt.hex(), h)
    u.update(salt=salt.hex(), hash=h)
    return await _revoke_user_sessions(u["name"].lower(), keep)


async def disable(user: str, password: str, ip: str = "") -> None:
    """Désactive la connexion pour tout le monde : supprime tous les comptes et sessions (le journal est conservé)."""
    u = await _verify_password(user, password, f"{ip}|off")
    if u["role"] != "admin":
        raise AuthError("Réservé à un administrateur.", 403)
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM auth_sessions")
        await conn.execute("DELETE FROM auth_users")
    _users.clear()
    _valid_cache.clear()
