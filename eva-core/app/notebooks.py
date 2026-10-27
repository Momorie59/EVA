"""Carnets partagés, façon OneNote : un carnet contient des sections, une section contient des pages.
Chaque carnet appartient à une personne, qui le partage avec d'autres personnes, des groupes ou tout le monde, en lecture seule ou en modification.
L'administrateur voit et gère tous les carnets. Stockage : une ligne `kv` par carnet (clé « nb:<id> »)."""
import asyncio
import json
import time
import uuid

from .db import get_pool

PREFIX = "nb:"
MAX_NOTEBOOKS_PER_USER = 40
MAX_SECTIONS = 30
MAX_PAGES = 300           # par carnet
MAX_TEXT = 60000
COLORS = ("jaune", "rose", "bleu", "vert", "orange", "violet")
_lock = asyncio.Lock()    # une écriture à la fois : deux personnes qui modifient en même temps ne s'écrasent pas


class NotebookError(Exception):
    def __init__(self, msg: str, status: int = 400, extra: dict | None = None):
        super().__init__(msg)
        self.status, self.extra = status, extra or {}


def _id() -> str:
    return uuid.uuid4().hex[:10]


def _now() -> float:
    return round(time.time(), 3)


# ---- droits
def perm(nb: dict, who: dict) -> str | None:
    """« owner » (propriétaire ou administrateur), « edit », « read » ou None."""
    if who["role"] == "admin" or nb["owner"].lower() == who["user"].lower():
        return "owner"
    best = None
    for s in nb.get("shares", []):
        hit = s["kind"] == "all" or (s["kind"] == "user" and s["name"].lower() == who["user"].lower()) or (s["kind"] == "group" and s["name"] in who.get("groups", []))
        if hit:
            if s.get("edit"):
                return "edit"
            best = "read"
    return best


def _need(nb: dict | None, who: dict, level: str) -> str:
    p = perm(nb, who) if nb else None
    if p is None:
        raise NotebookError("Carnet introuvable.", 404)
    order = {"read": 0, "edit": 1, "owner": 2}
    if order[p] < order[level]:
        raise NotebookError("Tu peux lire ce carnet, pas le modifier." if level == "edit" else "Seul le propriétaire peut faire cela.", 403)
    return p


# ---- stockage
async def _all() -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT value FROM kv WHERE key LIKE $1", PREFIX + "%")
    return [json.loads(r["value"]) if isinstance(r["value"], str) else r["value"] for r in rows]


async def _get(nid: str) -> dict | None:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", PREFIX + nid)
    return (json.loads(raw) if isinstance(raw, str) else raw) if raw else None


async def _put(nb: dict) -> None:
    nb["updated"] = _now()
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", PREFIX + nb["id"], json.dumps(nb))


def _summary(nb: dict, who: dict) -> dict:
    pages = sum(len(s["pages"]) for s in nb["sections"])
    return {"id": nb["id"], "title": nb["title"], "icon": nb["icon"], "color": nb["color"], "owner": nb["owner"], "perm": perm(nb, who),
            "sections": len(nb["sections"]), "pages": pages, "updated": nb["updated"],
            "shared": bool(nb["shares"]), "shares": nb["shares"] if perm(nb, who) == "owner" else []}


def _clean(s: str, n: int, default: str = "") -> str:
    s = " ".join((s or "").split())[:n]
    return s or default


# ---- carnets
async def list_for(who: dict) -> list[dict]:
    out = [_summary(nb, who) for nb in await _all() if perm(nb, who)]
    return sorted(out, key=lambda n: n["updated"], reverse=True)


async def get_for(nid: str, who: dict) -> dict:
    nb = await _get(nid)
    _need(nb, who, "read")
    return {**_summary(nb, who), "tree": nb["sections"]}


async def create(who: dict, title: str, icon: str = "📓", color: str = "jaune") -> dict:
    title = _clean(title, 80, "Nouveau carnet")
    async with _lock:
        mine = [n for n in await _all() if n["owner"].lower() == who["user"].lower()]
        if len(mine) >= MAX_NOTEBOOKS_PER_USER:
            raise NotebookError(f"{MAX_NOTEBOOKS_PER_USER} carnets au maximum : supprime-en un avant d'en créer un autre.")
        sid = _id()
        nb = {"id": _id(), "title": title, "icon": (icon or "📓")[:4], "color": color if color in COLORS else "jaune", "owner": who["user"] or "admin",
              "shares": [], "sections": [{"id": sid, "title": "Section 1", "pages": [{"id": _id(), "title": "Page sans titre", "text": "", "by": who["user"] or "admin", "updated": _now()}]}]}
        await _put(nb)
    return await get_for(nb["id"], who)


async def update(nid: str, who: dict, title: str | None = None, icon: str | None = None, color: str | None = None) -> dict:
    async with _lock:
        nb = await _get(nid)
        _need(nb, who, "owner")
        if title is not None:
            nb["title"] = _clean(title, 80, nb["title"])
        if icon:
            nb["icon"] = icon[:4]
        if color in COLORS:
            nb["color"] = color
        await _put(nb)
    return _summary(nb, who)


async def delete(nid: str, who: dict) -> None:
    async with _lock:
        _need(await _get(nid), who, "owner")
        async with get_pool().acquire() as conn:
            await conn.execute("DELETE FROM kv WHERE key=$1", PREFIX + nid)


async def set_shares(nid: str, who: dict, shares: list[dict], groups: dict[str, str], users: set[str]) -> list[dict]:
    """groups : {id: libellé} existants ; users : noms (minuscules) des comptes existants."""
    clean: list[dict] = []
    for s in shares[:30]:
        kind, name, edit = str(s.get("kind", "")), str(s.get("name", "")).strip(), bool(s.get("edit"))
        if kind == "all":
            clean = [c for c in clean if c["kind"] != "all"] + [{"kind": "all", "name": "", "edit": edit}]
        elif kind == "user" and name.lower() in users:
            clean.append({"kind": "user", "name": name, "edit": edit})
        elif kind == "group" and name in groups:
            clean.append({"kind": "group", "name": name, "edit": edit})
        else:
            raise NotebookError(f"Partage impossible : « {name or kind} » n'existe pas.")
    async with _lock:
        nb = await _get(nid)
        _need(nb, who, "owner")
        nb["shares"] = [c for c in clean if not (c["kind"] == "user" and c["name"].lower() == nb["owner"].lower())]
        await _put(nb)
    return nb["shares"]


# ---- sections et pages
def _section(nb: dict, sid: str) -> dict:
    for s in nb["sections"]:
        if s["id"] == sid:
            return s
    raise NotebookError("Section introuvable.", 404)


def _page(nb: dict, pid: str) -> tuple[dict, dict]:
    for s in nb["sections"]:
        for p in s["pages"]:
            if p["id"] == pid:
                return s, p
    raise NotebookError("Page introuvable.", 404)


async def add_section(nid: str, who: dict, title: str) -> dict:
    async with _lock:
        nb = await _get(nid)
        _need(nb, who, "edit")
        if len(nb["sections"]) >= MAX_SECTIONS:
            raise NotebookError(f"{MAX_SECTIONS} sections au maximum.")
        sec = {"id": _id(), "title": _clean(title, 60, f"Section {len(nb['sections']) + 1}"), "pages": [{"id": _id(), "title": "Page sans titre", "text": "", "by": who["user"] or "admin", "updated": _now()}]}
        nb["sections"].append(sec)
        await _put(nb)
    return sec


async def rename_section(nid: str, sid: str, who: dict, title: str) -> None:
    async with _lock:
        nb = await _get(nid)
        _need(nb, who, "edit")
        s = _section(nb, sid)
        s["title"] = _clean(title, 60, s["title"])
        await _put(nb)


async def delete_section(nid: str, sid: str, who: dict) -> None:
    async with _lock:
        nb = await _get(nid)
        _need(nb, who, "edit")
        if len(nb["sections"]) <= 1:
            raise NotebookError("Un carnet garde au moins une section.")
        _section(nb, sid)
        nb["sections"] = [s for s in nb["sections"] if s["id"] != sid]
        await _put(nb)


async def add_page(nid: str, sid: str, who: dict, title: str = "", text: str = "") -> dict:
    async with _lock:
        nb = await _get(nid)
        _need(nb, who, "edit")
        if sum(len(s["pages"]) for s in nb["sections"]) >= MAX_PAGES:
            raise NotebookError(f"{MAX_PAGES} pages au maximum dans un carnet.")
        page = {"id": _id(), "title": _clean(title, 100, "Page sans titre"), "text": (text or "")[:MAX_TEXT], "by": who["user"] or "admin", "updated": _now()}
        _section(nb, sid)["pages"].append(page)
        await _put(nb)
    return page


async def save_page(nid: str, pid: str, who: dict, title: str | None, text: str | None, base: float | None = None, move_to: str | None = None) -> dict:
    """base = horodatage de la page tel que l'éditeur l'a chargée : si quelqu'un d'autre l'a modifiée depuis, on refuse plutôt que d'écraser."""
    async with _lock:
        nb = await _get(nid)
        _need(nb, who, "edit")
        sec, page = _page(nb, pid)
        me = who["user"] or "admin"
        if base is not None and abs(page["updated"] - base) > 0.0005 and page["by"].lower() != me.lower():
            raise NotebookError("Quelqu'un d'autre vient de modifier cette page.", 409, {"page": page})
        if title is not None:
            page["title"] = _clean(title, 100, "Page sans titre")
        if text is not None:
            page["text"] = text[:MAX_TEXT]
        if move_to and move_to != sec["id"]:
            dest = _section(nb, move_to)
            sec["pages"] = [p for p in sec["pages"] if p["id"] != pid]
            dest["pages"].append(page)
        page["by"], page["updated"] = me, _now()
        await _put(nb)
    return page


async def delete_page(nid: str, pid: str, who: dict) -> None:
    async with _lock:
        nb = await _get(nid)
        _need(nb, who, "edit")
        sec, _ = _page(nb, pid)
        sec["pages"] = [p for p in sec["pages"] if p["id"] != pid]
        if not sec["pages"]:
            sec["pages"].append({"id": _id(), "title": "Page sans titre", "text": "", "by": who["user"] or "admin", "updated": _now()})
        await _put(nb)
