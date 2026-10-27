"""Suivi de contenus (comme le « content hub » de Jarvis) — module activable.

Chaque contenu (vidéo, publication, live, épisode…) avance : idée → script → tournage → montage → programmé → publié, avec ses
plateformes, sa date prévue, ses notes et son lien une fois en ligne. Privé à son auteur, sauf s'il le partage (chaîne de la
famille : tous ceux qui ont le module le voient et le complètent). EVA note les idées au vol, dit ce qui est prévu cette
semaine, et annonce une publication sur Discord quand on le lui demande."""
import re
from datetime import date

from .db import get_pool

SCHEMA = """
CREATE TABLE IF NOT EXISTS contenus (
    id SERIAL PRIMARY KEY,
    qui TEXT NOT NULL,
    titre TEXT NOT NULL,
    etat TEXT NOT NULL DEFAULT 'idee',
    plateformes TEXT[] NOT NULL DEFAULT '{}',
    date_prevue DATE,
    date_publiee DATE,
    notes TEXT NOT NULL DEFAULT '',
    lien TEXT NOT NULL DEFAULT '',
    partage BOOLEAN NOT NULL DEFAULT FALSE,
    cree TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS contenus_qui ON contenus(qui);
"""
ETATS = ["idee", "script", "tournage", "montage", "programme", "publie"]
NOMS_ETATS = {"idee": "Idée", "script": "Script", "tournage": "Tournage", "montage": "Montage", "programme": "Programmé", "publie": "Publié"}
PLATEFORMES = ["youtube", "instagram", "tiktok", "twitch", "facebook", "x", "linkedin", "blog", "podcast", "autre"]


class ContenuError(RuntimeError):
    pass


def _ligne(r) -> dict:
    d = dict(r)
    for k in ("date_prevue", "date_publiee"):
        d[k] = d[k].isoformat() if d[k] else None
    for k in ("cree", "modifie"):
        d[k] = d[k].isoformat() if d.get(k) else None
    d["plateformes"] = list(d.get("plateformes") or [])
    return d


def _date(v) -> date | None:
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError as exc:
        raise ContenuError("Date attendue au format AAAA-MM-JJ.") from exc


def _propre(champs: dict) -> dict:
    out = {}
    if "titre" in champs:
        t = " ".join(str(champs["titre"] or "").split())[:200]
        if not t:
            raise ContenuError("Donne un titre (ou une phrase qui résume l'idée).")
        out["titre"] = t
    if "etat" in champs:
        if champs["etat"] not in ETATS:
            raise ContenuError(f"État inconnu : {', '.join(ETATS)}.")
        out["etat"] = champs["etat"]
    if "plateformes" in champs:
        out["plateformes"] = [p for p in dict.fromkeys(str(x).lower().strip() for x in (champs["plateformes"] or [])) if p in PLATEFORMES]
    for k in ("date_prevue", "date_publiee"):
        if k in champs:
            out[k] = _date(champs[k])
    if "notes" in champs:
        out["notes"] = str(champs["notes"] or "")[:20000]
    if "lien" in champs:
        lien = str(champs["lien"] or "").strip()
        if lien and not re.match(r"^https?://\S+$", lien):
            raise ContenuError("Lien invalide (https://…).")
        out["lien"] = lien
    if "partage" in champs:
        out["partage"] = bool(champs["partage"])
    return out


def _visible(qui: str) -> str:
    return "(qui=$1 OR partage)"


async def lister(qui: str, etat: str = "", debut: str = "", fin: str = "") -> list[dict]:
    q, args = [_visible(qui)], [qui]
    if etat:
        args.append(etat)
        q.append(f"etat=${len(args)}")
    if debut:
        args.append(_date(debut))
        q.append(f"COALESCE(date_publiee, date_prevue) >= ${len(args)}")
    if fin:
        args.append(_date(fin))
        q.append(f"COALESCE(date_publiee, date_prevue) <= ${len(args)}")
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(f"SELECT * FROM contenus WHERE {' AND '.join(q)} ORDER BY COALESCE(date_publiee, date_prevue) NULLS LAST, modifie DESC LIMIT 500", *args)
    return [_ligne(r) for r in rows]


async def lire(qui: str, cid: int) -> dict:
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow(f"SELECT * FROM contenus WHERE id=$2 AND {_visible(qui)}", qui, int(cid))
    if not r:
        raise ContenuError("Contenu introuvable.")
    return _ligne(r)


async def creer(qui: str, champs: dict) -> dict:
    c = _propre({"etat": "idee", **champs})
    if "titre" not in c:
        raise ContenuError("Donne un titre.")
    cols = ["qui"] + list(c)
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow(f"INSERT INTO contenus ({', '.join(cols)}) VALUES ({', '.join(f'${i}' for i in range(1, len(cols) + 1))}) RETURNING *",
                                qui, *c.values())
    return _ligne(r)


async def modifier(qui: str, cid: int, champs: dict) -> dict:
    avant = await lire(qui, cid)
    c = _propre(champs)
    if "partage" in c and avant["qui"].lower() != (qui or "").lower():
        raise ContenuError("Seul son auteur peut partager ou reprendre un contenu.")
    if c.get("etat") == "publie" and not avant["date_publiee"] and "date_publiee" not in c:
        c["date_publiee"] = date.today()
    if not c:
        return avant
    sets = ", ".join(f"{k}=${i}" for i, k in enumerate(c, start=3))
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow(f"UPDATE contenus SET {sets}, modifie=now() WHERE id=$2 AND {_visible(qui)} RETURNING *", qui, int(cid), *c.values())
    return _ligne(r)


async def supprimer(qui: str, cid: int) -> None:
    async with get_pool().acquire() as conn:
        n = await conn.execute("DELETE FROM contenus WHERE id=$1 AND qui=$2", int(cid), qui)
    if n.endswith(" 0"):
        raise ContenuError("Seul son auteur peut supprimer ce contenu.")


async def resume(qui: str) -> dict:
    """Pour EVA : combien par étape, ce qui est prévu dans les 7 jours, ce qui est en retard."""
    tous = await lister(qui)
    today = date.today()
    prevus = [c for c in tous if c["etat"] != "publie" and c["date_prevue"] and 0 <= (date.fromisoformat(c["date_prevue"]) - today).days <= 7]
    retard = [c for c in tous if c["etat"] != "publie" and c["date_prevue"] and date.fromisoformat(c["date_prevue"]) < today]
    court = lambda c: {"id": c["id"], "titre": c["titre"], "etat": NOMS_ETATS[c["etat"]], "date": c["date_prevue"], "plateformes": c["plateformes"]}  # noqa: E731
    return {"par_etape": {NOMS_ETATS[e]: sum(1 for c in tous if c["etat"] == e) for e in ETATS},
            "cette_semaine": [court(c) for c in prevus], "en_retard": [court(c) for c in retard],
            "dernieres_idees": [c["titre"] for c in tous if c["etat"] == "idee"][-8:]}


def message_annonce(c: dict) -> str:
    plat = ", ".join(p.capitalize() for p in c["plateformes"]) if c["plateformes"] else ""
    return f"🎬 Nouveau : **{c['titre']}**" + (f" ({plat})" if plat else "") + (f"\n{c['lien']}" if c["lien"] else "")


async def exporter(qui: str) -> list[dict]:
    async with get_pool().acquire() as conn:
        return [_ligne(r) for r in await conn.fetch("SELECT * FROM contenus WHERE qui=$1 ORDER BY id", qui)]


async def effacer(qui: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM contenus WHERE qui=$1", qui)
