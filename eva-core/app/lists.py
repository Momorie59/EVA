"""Listes (courses, tâches…) — comme Alexa ou Google Assistant : « ajoute du lait à la liste de courses ».

Deux listes existent d'office : « Courses » et « À faire ». On retrouve une liste par son nom, sans accents ni
majuscules, avec quelques synonymes (« liste de courses », « shopping », « tâches »…). Un même article n'est pas ajouté deux fois."""
import re
import unicodedata

from .db import get_pool
from .profiles import user_var

DEFAULTS = (("Courses", "shopping"), ("À faire", "todo"))
SYNONYMS = {
    "courses": "Courses", "liste de courses": "Courses", "la liste de courses": "Courses", "shopping": "Courses", "epicerie": "Courses",
    "supermarche": "Courses", "marche": "Courses", "provisions": "Courses",
    "a faire": "À faire", "todo": "À faire", "to do": "À faire", "taches": "À faire", "tache": "À faire", "liste de taches": "À faire",
    "pense bete": "À faire", "tâches": "À faire",
}
MAX_TEXT = 200
MAX_ITEMS_PER_CALL = 40


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").replace("œ", "oe").replace("Œ", "oe").replace("æ", "ae")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


async def ensure_defaults() -> None:
    async with get_pool().acquire() as conn:
        for name, kind in DEFAULTS:
            await conn.execute("INSERT INTO lists (name, kind) VALUES ($1,$2) ON CONFLICT DO NOTHING", name, kind)


def _qui(qui: str | None) -> str:
    return (user_var.get() if qui is None else qui or "").strip().lower()


async def all_lists(qui: str | None = None) -> list[dict]:
    """Listes de la famille + listes privées de la personne (jamais celles des autres)."""
    await ensure_defaults()
    moi = _qui(qui)
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT l.id, l.name, l.kind, l.owner <> '' AS prive, count(i.id) FILTER (WHERE NOT i.done) AS open, "
            "count(i.id) FILTER (WHERE i.done) AS done FROM lists l LEFT JOIN list_items i ON i.list_id = l.id "
            "WHERE l.owner = '' OR ($1 <> '' AND lower(l.owner) = $1) GROUP BY l.id ORDER BY (l.owner <> ''), l.id", moi)
    return [dict(r) for r in rows]


async def visible(list_id: int, qui: str | None = None) -> bool:
    return any(l["id"] == list_id for l in await all_lists(qui))


async def find(name: str, create: bool = False, prive: bool = False, qui: str | None = None) -> dict | None:
    """Retrouve une liste par son nom (tolérant), privée de la personne d'abord. Avec create=True, une liste inconnue est créée."""
    lists = sorted(await all_lists(qui), key=lambda l: not l.get("prive"))
    key = norm(name or "") or "courses"
    target = norm(SYNONYMS.get(key, "")) or key
    for l in lists:
        if norm(l["name"]) == target:
            return l
    cands = [l for l in lists if target in norm(l["name"]) or norm(l["name"]) in target]
    if len(cands) == 1:
        return cands[0]
    if create and name.strip():
        return await create_list(name, prive, qui)
    return None


async def create_list(name: str, prive: bool = False, qui: str | None = None) -> dict:
    name = " ".join((name or "").split())[:60]
    if not name:
        raise ValueError("Nom de liste vide.")
    owner = _qui(qui) if prive else ""
    if prive and not owner:
        raise ValueError("Une liste privée a besoin d'un compte (connexion).")
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("INSERT INTO lists (name, kind, owner) VALUES ($1,'custom',$2) ON CONFLICT DO NOTHING RETURNING id, name, kind",
                                  name, owner)
        if row is None:
            row = await conn.fetchrow("SELECT id, name, kind FROM lists WHERE lower(name)=lower($1) AND lower(owner)=$2", name, owner)
    return {**dict(row), "open": 0, "done": 0, "prive": bool(owner)}


async def delete_list(list_id: int) -> bool:
    async with get_pool().acquire() as conn:
        kind = await conn.fetchval("SELECT kind FROM lists WHERE id=$1", list_id)
        if kind in ("shopping", "todo"):
            raise ValueError("Les listes « Courses » et « À faire » ne peuvent pas être supprimées (tu peux les vider).")
        return (await conn.execute("DELETE FROM lists WHERE id=$1", list_id)).endswith("1")


def _clean(text: str) -> str:
    return " ".join((text or "").split())[:MAX_TEXT]


async def items(list_id: int, include_done: bool = True) -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT id, text, done, by, created, done_at FROM list_items WHERE list_id=$1 " + ("" if include_done else "AND NOT done ")
                                + "ORDER BY done, id", list_id)
    from .rayons import rayon
    return [{**dict(r), "created": r["created"].isoformat(), "done_at": r["done_at"].isoformat() if r["done_at"] else None,
             "rayon": rayon(r["text"])} for r in rows]


async def add(list_id: int, texts: list[str], by: str = "") -> dict:
    texts = [_clean(t) for t in texts if _clean(t)][:MAX_ITEMS_PER_CALL]
    if not texts:
        raise ValueError("Rien à ajouter.")
    added, already = [], []
    async with get_pool().acquire() as conn:
        existing = {norm(r["text"]): r["id"] for r in await conn.fetch("SELECT id, text FROM list_items WHERE list_id=$1 AND NOT done", list_id)}
        for t in texts:
            if norm(t) in existing:
                already.append(t)
                continue
            await conn.execute("INSERT INTO list_items (list_id, text, by) VALUES ($1,$2,$3)", list_id, t, by)
            existing[norm(t)] = 0
            added.append(t)
    return {"added": added, "already_there": already}


async def _match(conn, list_id: int, query: str) -> list[dict]:
    q = norm(query)
    rows = await conn.fetch("SELECT id, text, done FROM list_items WHERE list_id=$1 ORDER BY id", list_id)
    exact = [r for r in rows if norm(r["text"]) == q]
    if exact:
        return [dict(r) for r in exact]
    return [dict(r) for r in rows if q and (q in norm(r["text"]) or norm(r["text"]) in q)]


async def set_done(list_id: int, query: str, done: bool = True) -> dict:
    async with get_pool().acquire() as conn:
        hits = [h for h in await _match(conn, list_id, query) if h["done"] != done]
        for h in hits:
            await conn.execute("UPDATE list_items SET done=$2, done_at=CASE WHEN $2 THEN now() ELSE NULL END WHERE id=$1", h["id"], done)
    return {"updated": [h["text"] for h in hits]}


async def remove(list_id: int, query: str) -> dict:
    async with get_pool().acquire() as conn:
        hits = await _match(conn, list_id, query)
        for h in hits:
            await conn.execute("DELETE FROM list_items WHERE id=$1", h["id"])
    return {"removed": [h["text"] for h in hits]}


async def item_update(item_id: int, text: str | None = None, done: bool | None = None, list_id: int | None = None) -> bool:
    """`list_id` : l'élément doit appartenir à cette liste (contrôle d'accès des listes privées)."""
    async with get_pool().acquire() as conn:
        ok = await conn.fetchval("SELECT 1 FROM list_items WHERE id=$1 AND ($2::int IS NULL OR list_id=$2)", item_id, list_id)
        if not ok:
            return False
        if text is not None:
            t = _clean(text)
            if not t:
                raise ValueError("Texte vide.")
            await conn.execute("UPDATE list_items SET text=$2 WHERE id=$1", item_id, t)
        if done is not None:
            await conn.execute("UPDATE list_items SET done=$2, done_at=CASE WHEN $2 THEN now() ELSE NULL END WHERE id=$1", item_id, done)
        return True


async def item_delete(item_id: int, list_id: int | None = None) -> bool:
    async with get_pool().acquire() as conn:
        return (await conn.execute("DELETE FROM list_items WHERE id=$1 AND ($2::int IS NULL OR list_id=$2)", item_id, list_id)).endswith("1")


async def clear_done(list_id: int) -> int:
    async with get_pool().acquire() as conn:
        return int((await conn.execute("DELETE FROM list_items WHERE list_id=$1 AND done", list_id)).split()[-1])


async def clear_all(list_id: int) -> int:
    async with get_pool().acquire() as conn:
        return int((await conn.execute("DELETE FROM list_items WHERE list_id=$1", list_id)).split()[-1])


async def as_text(list_id: int, include_done: bool = False, par_rayon: bool | None = None) -> tuple[str, str]:
    """Texte de la liste ; la liste de courses est rangée par rayon du magasin (par_rayon=None : automatique)."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("SELECT name, kind FROM lists WHERE id=$1", list_id)
    its = await items(list_id, include_done)
    if par_rayon is None:
        par_rayon = bool(row) and row["kind"] == "shopping"
    ligne = lambda i: f"{'[x]' if i['done'] else '[ ]'} {i['text']}"   # noqa: E731
    if par_rayon and its:
        from .rayons import ORDRE
        blocs = []
        for r in ORDRE:
            dans = [i for i in its if i["rayon"] == r]
            if dans:
                blocs.append(f"— {r} —\n" + "\n".join(ligne(i) for i in dans))
        body = "\n\n".join(blocs)
    else:
        body = "\n".join(ligne(i) for i in its) or "(liste vide)"
    return (row["name"] if row else None) or "Liste", body
