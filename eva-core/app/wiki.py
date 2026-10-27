"""Wiki : pages de la famille (partagées) et pages personnelles (privées), en Markdown, avec historique des versions.

- Espace « famille » : toute personne qui a la fonctionnalité « wiki » lit, crée et modifie ; l'historique garde chaque version
  (qui, quand) et une version ancienne se restaure en un clic. Un invité ne fait que lire.
- Espace « perso » : chaque personne a ses pages, que personne d'autre ne voit (pas même l'administrateur).
- Liens entre pages : [[Titre d'une page]]. Images et vidéos : voir medias.py (dossier wiki/medias du NAS).
- EVA cherche et lit les pages pour répondre (outils wiki_chercher / wiki_lire) ; elle n'écrit que sur demande (wiki_ecrire)."""
import re
import unicodedata

from .db import get_pool

ESPACES = ("famille", "perso")
MAX_TITRE = 120
MAX_CONTENU = 200_000
MAX_VERSIONS = 200

SCHEMA = """
CREATE TABLE IF NOT EXISTS wiki_pages (
    id BIGSERIAL PRIMARY KEY,
    espace TEXT NOT NULL,                 -- famille | perso
    owner TEXT NOT NULL DEFAULT '',       -- perso : la personne ; famille : ''
    slug TEXT NOT NULL,
    titre TEXT NOT NULL,
    contenu TEXT NOT NULL DEFAULT '',
    tags TEXT[] NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (espace, owner, slug)
);
CREATE TABLE IF NOT EXISTS wiki_versions (
    id BIGSERIAL PRIMARY KEY,
    page_id BIGINT NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
    titre TEXT NOT NULL,
    contenu TEXT NOT NULL,
    auteur TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS wiki_versions_page ON wiki_versions (page_id, id DESC);
"""


class WikiError(Exception):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


def slugify(titre: str) -> str:
    t = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:80] or "page"


def _proprietaire(espace: str, qui: str) -> str:
    if espace not in ESPACES:
        raise WikiError("Espace inconnu (famille ou perso).")
    return (qui or "").lower() if espace == "perso" else ""


def _page(r, extrait: bool = False) -> dict:
    d = {"id": r["id"], "espace": r["espace"], "slug": r["slug"], "titre": r["titre"], "tags": list(r["tags"] or []),
         "created_by": r["created_by"], "updated_by": r["updated_by"],
         "created_at": r["created_at"].isoformat(), "updated_at": r["updated_at"].isoformat()}
    if extrait:
        t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", r["contenu"] or "")                  # images retirées de l'extrait
        t = re.sub(r"\[\[([^\]]+)\]\]|\[([^\]]+)\]\([^)]*\)", lambda m: m.group(1) or m.group(2), t)
        t = re.sub(r"^\s{0,3}(#{1,6}|[-*•]|\d+[.)]|>)\s+", "", t, flags=re.M)
        d["extrait"] = " ".join(re.sub(r"[*_`]", "", t).split())[:180]
    else:
        d["contenu"] = r["contenu"]
    return d


def _visible_sql(n: int) -> str:
    """Condition SQL : pages famille + pages perso de la personne ($n)."""
    return f"(espace='famille' OR (espace='perso' AND owner=${n}))"


async def lister(qui: str, espace: str | None = None, q: str = "", limite: int = 300) -> list[dict]:
    args: list = [(qui or "").lower()]
    cond = [_visible_sql(1)]
    if espace:
        args.append(espace)
        cond.append(f"espace=${len(args)}")
    if q.strip():
        args.append(f"%{q.strip()}%")
        cond.append(f"(titre ILIKE ${len(args)} OR contenu ILIKE ${len(args)} OR array_to_string(tags,' ') ILIKE ${len(args)})")
    args.append(limite)
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(f"SELECT * FROM wiki_pages WHERE {' AND '.join(cond)} ORDER BY espace, lower(titre) LIMIT ${len(args)}", *args)
    return [_page(r, extrait=True) for r in rows]


async def lire(qui: str, page_id: int) -> dict:
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow(f"SELECT * FROM wiki_pages WHERE id=$2 AND {_visible_sql(1)}", (qui or "").lower(), int(page_id))
        if r is None:
            raise WikiError("Page introuvable.", 404)
        n = await conn.fetchval("SELECT count(*) FROM wiki_versions WHERE page_id=$1", r["id"])
    return {**_page(r), "versions": int(n or 0)}


async def par_titre(qui: str, titre: str) -> dict | None:
    """Pour les liens [[Titre]] et EVA : page famille ou perso de ce titre (ou de ce slug)."""
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow(f"SELECT * FROM wiki_pages WHERE {_visible_sql(1)} AND (lower(titre)=lower($2) OR slug=$3) "
                                "ORDER BY espace='perso' DESC LIMIT 1", (qui or "").lower(), titre.strip(), slugify(titre))
    return _page(r) if r else None


def _propre(titre: str, contenu: str, tags) -> tuple[str, str, list[str]]:
    titre = " ".join((titre or "").split())
    if not titre:
        raise WikiError("Donne un titre à la page.")
    if len(titre) > MAX_TITRE:
        raise WikiError(f"Titre trop long ({MAX_TITRE} caractères maximum).")
    contenu = (contenu or "").replace("\r\n", "\n")
    if len(contenu) > MAX_CONTENU:
        raise WikiError("Page trop longue (200 000 caractères maximum) : découpe-la en plusieurs pages.")
    tags = [t.strip().lower()[:30] for t in (tags or []) if str(t).strip()][:12]
    return titre, contenu, tags


async def creer(qui: str, espace: str, titre: str, contenu: str = "", tags=None, role: str = "user") -> dict:
    if role == "guest":
        raise WikiError("Un invité ne fait que lire le wiki.", 403)
    owner = _proprietaire(espace, qui)
    titre, contenu, tags = _propre(titre, contenu, tags)
    base = slugify(titre)
    async with get_pool().acquire() as conn:
        slug, i = base, 2
        while await conn.fetchval("SELECT 1 FROM wiki_pages WHERE espace=$1 AND owner=$2 AND slug=$3", espace, owner, slug):
            slug, i = f"{base}-{i}", i + 1
        r = await conn.fetchrow("INSERT INTO wiki_pages (espace, owner, slug, titre, contenu, tags, created_by, updated_by) "
                                "VALUES ($1,$2,$3,$4,$5,$6,$7,$7) RETURNING *", espace, owner, slug, titre, contenu, tags, (qui or "").lower())
    return {**_page(r), "versions": 0}


async def modifier(qui: str, page_id: int, titre: str | None = None, contenu: str | None = None, tags=None,
                   base: str | None = None, role: str = "user") -> dict:
    """Garde la version précédente dans l'historique. `base` (updated_at lu par l'éditeur) : refuse d'écraser une
    modification faite entre-temps par quelqu'un d'autre."""
    if role == "guest":
        raise WikiError("Un invité ne fait que lire le wiki.", 403)
    actuelle = await lire(qui, page_id)
    if base and base != actuelle["updated_at"]:
        raise WikiError(f"{actuelle['updated_by'] or 'Quelqu’un'} a modifié cette page pendant que tu l'éditais : recharge-la avant d'enregistrer.", 409)
    t, c, g = _propre(titre if titre is not None else actuelle["titre"], contenu if contenu is not None else actuelle["contenu"],
                      tags if tags is not None else actuelle["tags"])
    if t == actuelle["titre"] and c == actuelle["contenu"] and g == actuelle["tags"]:
        return actuelle
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("INSERT INTO wiki_versions (page_id, titre, contenu, auteur) VALUES ($1,$2,$3,$4)",
                               actuelle["id"], actuelle["titre"], actuelle["contenu"], actuelle["updated_by"])
            await conn.execute("DELETE FROM wiki_versions WHERE page_id=$1 AND id NOT IN (SELECT id FROM wiki_versions WHERE page_id=$1 "
                               "ORDER BY id DESC LIMIT $2)", actuelle["id"], MAX_VERSIONS)
            await conn.execute("UPDATE wiki_pages SET titre=$2, contenu=$3, tags=$4, updated_by=$5, updated_at=now() WHERE id=$1",
                               actuelle["id"], t, c, g, (qui or "").lower())
    return await lire(qui, page_id)


async def supprimer(qui: str, page_id: int, role: str = "user") -> None:
    p = await lire(qui, page_id)
    if p["espace"] == "famille" and role not in ("admin",) and p["created_by"] != (qui or "").lower():
        raise WikiError("Seul l'auteur de la page ou l'administrateur peut la supprimer (tu peux la modifier).", 403)
    if role == "guest":
        raise WikiError("Un invité ne fait que lire le wiki.", 403)
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM wiki_pages WHERE id=$1", p["id"])


async def versions(qui: str, page_id: int) -> list[dict]:
    await lire(qui, page_id)
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT id, titre, auteur, created_at, length(contenu) AS taille FROM wiki_versions WHERE page_id=$1 ORDER BY id DESC", int(page_id))
    return [{"id": r["id"], "titre": r["titre"], "auteur": r["auteur"], "le": r["created_at"].isoformat(), "taille": r["taille"]} for r in rows]


async def version(qui: str, page_id: int, version_id: int) -> dict:
    await lire(qui, page_id)
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM wiki_versions WHERE id=$1 AND page_id=$2", int(version_id), int(page_id))
    if r is None:
        raise WikiError("Version introuvable.", 404)
    return {"id": r["id"], "titre": r["titre"], "contenu": r["contenu"], "auteur": r["auteur"], "le": r["created_at"].isoformat()}


async def restaurer(qui: str, page_id: int, version_id: int, role: str = "user") -> dict:
    v = await version(qui, page_id, version_id)
    return await modifier(qui, page_id, v["titre"], v["contenu"], role=role)


async def chercher(qui: str, q: str, limite: int = 5) -> list[dict]:
    """Recherche pour EVA : plein texte français (mots), puis repli sur la présence des mots."""
    q = (q or "").strip()
    if not q:
        return []
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            f"SELECT *, ts_rank(to_tsvector('french', titre || ' ' || contenu), plainto_tsquery('french', $2)) AS rang "
            f"FROM wiki_pages WHERE {_visible_sql(1)} AND to_tsvector('french', titre || ' ' || contenu) @@ plainto_tsquery('french', $2) "
            "ORDER BY rang DESC LIMIT $3", (qui or "").lower(), q, limite)
        if not rows:
            mots = [m for m in re.findall(r"\w{3,}", q.lower())][:6]
            if mots:
                cond = " OR ".join(f"(titre ILIKE ${i + 2} OR contenu ILIKE ${i + 2})" for i in range(len(mots)))
                rows = await conn.fetch(f"SELECT * FROM wiki_pages WHERE {_visible_sql(1)} AND ({cond}) LIMIT {int(limite)}",
                                        (qui or "").lower(), *[f"%{m}%" for m in mots])
    out = []
    for r in rows:
        p = _page(r)
        p["contenu"] = p["contenu"][:4000]
        out.append(p)
    return out


async def donnees_de(qui: str) -> dict:
    """Pour « Mes données » : pages perso de la personne et pages famille qu'elle a créées."""
    async with get_pool().acquire() as conn:
        perso = await conn.fetch("SELECT * FROM wiki_pages WHERE espace='perso' AND owner=$1 ORDER BY titre", (qui or "").lower())
        creees = await conn.fetch("SELECT * FROM wiki_pages WHERE espace='famille' AND created_by=$1 ORDER BY titre", (qui or "").lower())
    return {"perso": [_page(r) for r in perso], "famille_creees": [_page(r) for r in creees]}


async def effacer_perso(qui: str) -> int:
    async with get_pool().acquire() as conn:
        res = await conn.execute("DELETE FROM wiki_pages WHERE espace='perso' AND owner=$1", (qui or "").lower())
    return int(res.split()[-1]) if res else 0
