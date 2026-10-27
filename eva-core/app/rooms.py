"""Salon d'EVA : qui est connecté, discussion écrite, appels voix/vidéo à plusieurs (WebRTC maillé).
EVA CORE ne voit jamais l'audio ni la vidéo : il relaie seulement les messages de mise en relation (offre, réponse, candidats ICE)."""
import json
import time
import uuid
from collections import deque

from .db import get_pool

KV = "room_messages"
MAX_TEXT = 2000
MAX_HISTORY = 300
DM_KV = "room_dm"            # messages privés : {"a|b": [msg…]} (a et b en minuscules, triés)
DM_READ_KV = "room_dm_read"  # {utilisateur: {interlocuteur: horodatage du dernier message lu}}
MAX_DM = 200                 # messages gardés par conversation privée
MAX_CALL = 6                 # appel maillé : chacun envoie son flux à chacun, au-delà le réseau et le processeur souffrent


class Hub:
    def __init__(self) -> None:
        self.conns: dict[str, dict] = {}          # cid -> {ws, user, role, label, call: bool, video: bool}
        self._hist: deque | None = None
        self._rate: dict[str, deque] = {}
        self._dm: dict[str, list] | None = None
        self._reads: dict[str, dict] | None = None

    # ---- historique
    async def history(self) -> list[dict]:
        if self._hist is None:
            try:
                async with get_pool().acquire() as conn:
                    raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
                data = (json.loads(raw) if isinstance(raw, str) else raw) or []
            except Exception:  # noqa: BLE001 — base indisponible : le salon marche sans mémoire
                data = []
            self._hist = deque(data, maxlen=MAX_HISTORY)
        return list(self._hist)

    async def _remember(self, msg: dict) -> None:
        await self.history()
        self._hist.append(msg)
        try:
            async with get_pool().acquire() as conn:
                await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(list(self._hist)))
        except Exception:  # noqa: BLE001
            pass

    async def clear(self) -> None:
        self._hist = deque(maxlen=MAX_HISTORY)
        async with get_pool().acquire() as conn:
            await conn.execute("DELETE FROM kv WHERE key=$1", KV)

    # ---- messages privés (entre deux personnes, jamais visibles des autres, administrateur compris)
    async def _kv_get(self, key: str) -> dict:
        try:
            async with get_pool().acquire() as conn:
                raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", key)
            return (json.loads(raw) if isinstance(raw, str) else raw) or {}
        except Exception:  # noqa: BLE001 — base indisponible : le salon marche sans mémoire
            return {}

    async def _kv_put(self, key: str, value: dict) -> None:
        try:
            async with get_pool().acquire() as conn:
                await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", key, json.dumps(value))
        except Exception:  # noqa: BLE001
            pass

    async def _dm_load(self) -> None:
        if self._dm is None or self._reads is None:
            dm, reads = await self._kv_get(DM_KV), await self._kv_get(DM_READ_KV)      # deux connexions simultanées : on n'expose les deux ensemble
            if self._dm is None or self._reads is None:
                self._dm, self._reads = dm, reads

    @staticmethod
    def _pair(a: str, b: str) -> str:
        return "|".join(sorted([a.lower(), b.lower()]))

    async def dm_state(self, user: str) -> dict:
        """Conversations privées et marqueurs « lu » de cette personne, rangés par interlocuteur (en minuscules)."""
        await self._dm_load()
        me = user.lower()
        out: dict[str, list] = {}
        for key, msgs in self._dm.items():
            a, b = key.split("|")
            if me in (a, b):
                out[b if a == me else a] = msgs
        return {"dms": out, "reads": dict(self._reads.get(me, {}))}

    @staticmethod
    def resolve_user(name: str) -> str | None:
        """Nom exact d'un compte (ou d'une personne connectée sans compte, ex. l'administrateur par jeton)."""
        from . import auth
        low = name.strip().lower()
        u = auth._users.get(low)
        if u:
            return u["name"]
        for c in hub.conns.values():
            if c["user"].lower() == low:
                return c["user"]
        return None

    async def _send_user(self, user: str, event: dict) -> None:
        low = user.lower()
        for cid, c in list(self.conns.items()):
            if c["user"].lower() == low:
                await self._send(cid, event)

    async def _dm_handle(self, cid: str, c: dict, ev: dict) -> None:
        t = ev.get("type")
        other = self.resolve_user(str(ev.get("to") or ev.get("with") or ""))
        if t == "dm_read":
            if not other:
                return
            await self._dm_load()
            ts = time.time()
            self._reads.setdefault(c["user"].lower(), {})[other.lower()] = ts
            await self._kv_put(DM_READ_KV, self._reads)
            await self._send_user(c["user"], {"type": "dm_read", "with": other.lower(), "ts": ts})
            return
        if t == "dm_typing":
            if other:
                await self._send_user(other, {"type": "dm_typing", "user": c["user"]})
            return
        text = str(ev.get("text", "")).strip()[:MAX_TEXT]
        if not text:
            return
        if not other or other.lower() == c["user"].lower():
            await self._send(cid, {"type": "notice", "text": "Cette personne n'existe pas."})
            return
        if not self._allowed(cid):
            await self._send(cid, {"type": "notice", "text": "Doucement : trop de messages d'affilée."})
            return
        from . import auth, features as features_mod
        rec = auth._users.get(other.lower())
        if rec and rec["role"] != "admin" and "salon" not in await features_mod.effective(rec["role"], rec["name"]):
            await self._send(cid, {"type": "notice", "text": f"{other} n'a pas accès au Salon."})
            return
        await self._dm_load()
        msg = {"id": uuid.uuid4().hex[:10], "from": c["user"], "to": other, "text": text, "ts": time.time()}
        lst = self._dm.setdefault(self._pair(c["user"], other), [])
        lst.append(msg)
        del lst[:-MAX_DM]
        await self._kv_put(DM_KV, self._dm)
        await self._send_user(c["user"], {"type": "dm", "msg": msg})
        await self._send_user(other, {"type": "dm", "msg": msg})

    # ---- présence
    def users(self) -> list[dict]:
        seen: dict[str, dict] = {}
        for cid, c in self.conns.items():
            u = seen.setdefault(c["user"], {"user": c["user"], "label": c["label"], "online": True, "in_call": False, "video": False, "devices": 0})
            u["devices"] += 1
            if c["call"]:
                u["in_call"] = True
                u["video"] = u["video"] or c["video"]
        return sorted(seen.values(), key=lambda u: u["user"].lower())

    def participants(self) -> list[dict]:
        return [{"cid": cid, "user": c["user"], "video": c["video"]} for cid, c in self.conns.items() if c["call"]]

    async def _send(self, cid: str, event: dict) -> None:
        c = self.conns.get(cid)
        if c:
            try:
                await c["ws"].send_json(event)
            except Exception:  # noqa: BLE001 — connexion morte : le nettoyage se fait à la déconnexion
                pass

    async def broadcast(self, event: dict, skip: str = "") -> None:
        for cid in list(self.conns):
            if cid != skip:
                await self._send(cid, event)

    async def _state(self) -> None:
        await self.broadcast({"type": "presence", "users": self.users(), "call": self.participants()})

    # ---- connexion
    async def join(self, ws, user: str, role: str, label: str) -> str:
        cid = uuid.uuid4().hex[:10]
        self.conns[cid] = {"ws": ws, "user": user, "role": role, "label": label, "call": False, "video": False}
        await self._send(cid, {"type": "hello", "cid": cid, "me": user, "users": self.users(), "call": self.participants(), "history": await self.history(), "max_call": MAX_CALL, **await self.dm_state(user)})
        await self._state()
        return cid

    async def leave(self, cid: str) -> None:
        if self.conns.pop(cid, None) is not None:
            self._rate.pop(cid, None)
            await self._state()

    # ---- messages du client
    def _allowed(self, cid: str) -> bool:
        now = time.monotonic()
        q = self._rate.setdefault(cid, deque())
        while q and now - q[0] > 10:
            q.popleft()
        if len(q) >= 25:
            return False
        q.append(now)
        return True

    async def handle(self, cid: str, ev: dict) -> None:
        c = self.conns.get(cid)
        if not c or not isinstance(ev, dict):
            return
        t = ev.get("type")
        if t == "chat":
            text = str(ev.get("text", "")).strip()[:MAX_TEXT]
            if not text:
                return
            if not self._allowed(cid):
                await self._send(cid, {"type": "notice", "text": "Doucement : trop de messages d'affilée."})
                return
            msg = {"id": uuid.uuid4().hex[:10], "user": c["user"], "label": c["label"], "text": text, "ts": time.time()}
            await self._remember(msg)
            await self.broadcast({"type": "chat", "msg": msg})
        elif t in ("dm", "dm_read", "dm_typing"):
            await self._dm_handle(cid, c, ev)
        elif t == "typing":
            await self.broadcast({"type": "typing", "user": c["user"]}, skip=cid)
        elif t == "call_join":
            if not c["call"] and len(self.participants()) >= MAX_CALL:
                await self._send(cid, {"type": "notice", "text": f"L'appel est complet ({MAX_CALL} personnes au maximum)."})
                return
            before = [p for p in self.participants() if p["cid"] != cid]
            c["call"], c["video"] = True, bool(ev.get("video"))
            await self._send(cid, {"type": "call_joined", "peers": before})       # le nouvel arrivant appelle les présents
            await self._state()
        elif t == "call_leave":
            if c["call"]:
                c["call"] = c["video"] = False
                await self._state()
        elif t == "signal":
            to = str(ev.get("to", ""))
            peer = self.conns.get(to)
            if peer and peer["call"] and c["call"] and isinstance(ev.get("data"), dict):
                await self._send(to, {"type": "signal", "from": cid, "user": c["user"], "data": ev["data"]})


hub = Hub()


# ---- serveurs de mise en relation (STUN/TURN) : vide = réseau local seulement ; utile pour des amis hors de chez toi
ICE_KV = "room_ice"
ICE_RE = __import__("re").compile(r"^(stun|stuns|turn|turns):[A-Za-z0-9._:\-\[\]]{1,120}(\?transport=(udp|tcp))?$")


async def ice_get() -> list[dict]:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", ICE_KV)
    d = (json.loads(raw) if isinstance(raw, str) else raw) or {}
    return d.get("servers", [])


async def ice_set(servers: list[dict]) -> list[dict]:
    clean = []
    for s in servers[:6]:
        url = str(s.get("urls", "")).strip()
        if not ICE_RE.match(url):
            raise ValueError(f"Adresse invalide : {url or '(vide)'} (attendu stun:hote:port ou turn:hote:port).")
        item = {"urls": url}
        if str(s.get("username", "")).strip():
            item["username"] = str(s["username"]).strip()[:100]
            item["credential"] = str(s.get("credential", ""))[:200]
        clean.append(item)
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", ICE_KV, json.dumps({"servers": clean}))
    return clean
