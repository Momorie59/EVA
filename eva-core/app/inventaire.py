"""Inventaire et prêts (module « inventaire ») : où est rangée chaque chose, et à qui on l'a prêtée (ou qui nous l'a prêtée).

Idée inspirée de JPJR (« Je prends, je rends », Les Frères Poulain), écrite pour EVA (aucun code repris).
- Un objet a un nom, un emplacement en chemin (« Garage › Établi › Tiroir 2 »), une quantité et des notes.
- Objets de la famille par défaut ; un objet peut être privé (seul son propriétaire le voit).
- Un prêt : l'objet (de l'inventaire ou non), la personne, le sens (prêté / emprunté), la date de retour prévue."""
import re
import unicodedata
from datetime import date, datetime

from .db import get_pool

SCHEMA = """
CREATE TABLE IF NOT EXISTS inventaire_objets (
    id BIGSERIAL PRIMARY KEY,
    nom TEXT NOT NULL,
    cle TEXT NOT NULL,
    emplacement TEXT NOT NULL DEFAULT '',
    quantite INT NOT NULL DEFAULT 1,
    notes TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '',
    prive BOOLEAN NOT NULL DEFAULT FALSE,
    maj TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS inventaire_objets_cle ON inventaire_objets (cle);
CREATE TABLE IF NOT EXISTS inventaire_prets (
    id BIGSERIAL PRIMARY KEY,
    objet_id BIGINT REFERENCES inventaire_objets(id) ON DELETE SET NULL,
    objet TEXT NOT NULL,
    personne TEXT NOT NULL,
    sens TEXT NOT NULL DEFAULT 'prete',
    depuis DATE NOT NULL DEFAULT CURRENT_DATE,
    retour_prevu DATE,
    rendu_le TIMESTAMPTZ,
    notes TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT ''
);
"""

SEP = " › "


class InventaireError(ValueError):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


def cle(texte: str) -> str:
    """« La Perceuse » → « perceuse » : minuscules, sans accents, sans article, singulier simple."""
    t = unicodedata.normalize("NFD", (texte or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    mots = [m for m in t.split() if m not in ("le", "la", "les", "l", "un", "une", "des", "du", "de", "d", "mon", "ma", "mes", "notre", "nos")]
    return " ".join(m[:-1] if len(m) > 3 and m.endswith(("s", "x")) else m for m in mots)


def chemin(emplacement: str) -> str:
    parts = [p.strip() for p in re.split(r"\s*(?:›|>|/|\\|,| dans (?:le |la |l')?| sur (?:le |la |l')?)\s*", emplacement or "") if p and p.strip()]
    return SEP.join(p[:1].upper() + p[1:] for p in parts)[:200]


def _visible(qui: str) -> tuple[str, list]:
    return "(NOT prive OR lower(owner)=lower($1))", [qui or ""]


def _objet(r) -> dict:
    return {"id": r["id"], "nom": r["nom"], "emplacement": r["emplacement"], "quantite": r["quantite"], "notes": r["notes"],
            "prive": r["prive"], "owner": r["owner"], "maj": r["maj"].isoformat()}


async def _prets_actifs(conn, ids: list[int]) -> dict[int, dict]:
    rows = await conn.fetch("SELECT * FROM inventaire_prets WHERE rendu_le IS NULL AND objet_id = ANY($1::bigint[])", ids)
    return {r["objet_id"]: _pret(r) for r in rows}


def _pret(r) -> dict:
    retard = bool(r["retour_prevu"] and r["retour_prevu"] < date.today() and r["rendu_le"] is None)
    return {"id": r["id"], "objet": r["objet"], "objet_id": r["objet_id"], "personne": r["personne"], "sens": r["sens"],
            "depuis": r["depuis"].isoformat(), "retour_prevu": r["retour_prevu"].isoformat() if r["retour_prevu"] else None,
            "rendu_le": r["rendu_le"].isoformat() if r["rendu_le"] else None, "en_retard": retard, "notes": r["notes"]}


async def lister(qui: str, q: str = "", lieu: str = "") -> list[dict]:
    cond, args = _visible(qui)
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(f"SELECT * FROM inventaire_objets WHERE {cond} ORDER BY emplacement, nom", *args)
        objets = [_objet(r) for r in rows]
        k = cle(q)
        if k:
            mots = k.split()
            objets = [o for o in objets if all(m in cle(o["nom"] + " " + o["notes"]) for m in mots)] or \
                     [o for o in objets if any(m in cle(o["nom"]) for m in mots)]
        if lieu:
            kl = cle(lieu)
            objets = [o for o in objets if kl in cle(o["emplacement"])]
        prets = await _prets_actifs(conn, [o["id"] for o in objets])
    for o in objets:
        o["pret"] = prets.get(o["id"])
    return objets


async def ou_est(qui: str, q: str) -> dict:
    trouves = await lister(qui, q)
    async with get_pool().acquire() as conn:          # prêté hors inventaire ?
        pr = [_pret(r) for r in await conn.fetch("SELECT * FROM inventaire_prets WHERE rendu_le IS NULL ORDER BY depuis DESC")]
    k = cle(q)
    prets_hors = [p for p in pr if p["objet_id"] is None and k and all(m in cle(p["objet"]) for m in k.split())]
    if not trouves and not prets_hors:
        return {"trouve": False, "phrase": f"Je ne trouve pas « {q} » dans l'inventaire."}
    phrases = []
    for o in trouves[:5]:
        p = o["pret"]
        if p and p["sens"] == "prete":
            phrases.append(f"{o['nom']} : prêté à {p['personne']} depuis le {_jj(p['depuis'])}" + (f" (retour prévu le {_jj(p['retour_prevu'])})" if p["retour_prevu"] else "")
                           + (f" ; sa place : {o['emplacement']}" if o["emplacement"] else ""))
        else:
            phrases.append(f"{o['nom']} : {o['emplacement'] or 'emplacement non noté'}" + (f" ({o['quantite']})" if o["quantite"] != 1 else ""))
    for p in prets_hors[:3]:
        phrases.append(f"{p['objet']} : {'prêté à' if p['sens'] == 'prete' else 'emprunté à'} {p['personne']} depuis le {_jj(p['depuis'])}")
    return {"trouve": True, "phrase": " ; ".join(phrases) + ".", "objets": trouves[:5]}


def _jj(iso: str | None) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso[:10])
    return f"{d.day}/{d.month:02d}"


async def ranger(qui: str, nom: str, emplacement: str = "", quantite: int | None = None, notes: str | None = None,
                 prive: bool | None = None, oid: int | None = None) -> dict:
    nom = " ".join((nom or "").split())[:120]
    if not nom and not oid:
        raise InventaireError("Quel objet ?")
    k = cle(nom)
    cond, args = _visible(qui)
    async with get_pool().acquire() as conn:
        if oid:
            r = await conn.fetchrow(f"SELECT * FROM inventaire_objets WHERE id=$2 AND {cond}", *args, oid)
        else:
            r = await conn.fetchrow(f"SELECT * FROM inventaire_objets WHERE cle=$2 AND {cond} ORDER BY id LIMIT 1", *args, k)
        if r:
            if r["prive"] and (r["owner"] or "").lower() != (qui or "").lower():
                raise InventaireError("Objet introuvable.", 404)
            r = await conn.fetchrow(
                "UPDATE inventaire_objets SET nom=$2, cle=$3, emplacement=$4, quantite=$5, notes=$6, prive=$7, maj=now() WHERE id=$1 RETURNING *",
                r["id"], nom or r["nom"], cle(nom or r["nom"]), chemin(emplacement) if emplacement else r["emplacement"],
                max(0, int(quantite)) if quantite is not None else r["quantite"], (notes if notes is not None else r["notes"])[:500],
                bool(prive) if prive is not None else r["prive"])
            return {**_objet(r), "nouveau": False}
        r = await conn.fetchrow(
            "INSERT INTO inventaire_objets (nom, cle, emplacement, quantite, notes, owner, prive) VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *",
            nom, k, chemin(emplacement), max(0, int(quantite if quantite is not None else 1)), (notes or "")[:500], qui or "", bool(prive))
    return {**_objet(r), "nouveau": True}


async def retirer(qui: str, oid: int) -> None:
    cond, args = _visible(qui)
    async with get_pool().acquire() as conn:
        res = await conn.execute(f"DELETE FROM inventaire_objets WHERE id=$2 AND {cond}", *args, oid)
    if res.endswith(" 0"):
        raise InventaireError("Objet introuvable.", 404)


async def trouver_un(qui: str, nom: str) -> dict | None:
    l = await lister(qui, nom)
    k = cle(nom)
    exact = [o for o in l if cle(o["nom"]) == k]
    return (exact or l or [None])[0]


async def preter(qui: str, objet: str, personne: str, sens: str = "prete", retour: str | None = None, notes: str = "") -> dict:
    personne = " ".join((personne or "").split())[:80]
    if not personne:
        raise InventaireError("À qui ?")
    if sens not in ("prete", "emprunte"):
        raise InventaireError("sens : prete ou emprunte.")
    retour_d = None
    if retour:
        try:
            retour_d = date.fromisoformat(retour[:10])
        except ValueError as exc:
            raise InventaireError("Date de retour au format AAAA-MM-JJ.") from exc
    o = await trouver_un(qui, objet) if sens == "prete" else None
    nom = o["nom"] if o else " ".join((objet or "").split())[:120]
    if not nom:
        raise InventaireError("Quel objet ?")
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow("INSERT INTO inventaire_prets (objet_id, objet, personne, sens, retour_prevu, notes, owner) "
                                "VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *", o["id"] if o else None, nom, personne, sens, retour_d, notes[:300], qui or "")
    return {**_pret(r), "dans_inventaire": bool(o)}


async def rendre(qui: str, objet: str = "", personne: str = "", pid: int | None = None) -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = [_pret(r) for r in await conn.fetch("SELECT * FROM inventaire_prets WHERE rendu_le IS NULL ORDER BY depuis")]
        if pid:
            cibles = [p for p in rows if p["id"] == pid]
        else:
            ko, kp = cle(objet), cle(personne)
            cibles = [p for p in rows if (not ko or all(m in cle(p["objet"]) for m in ko.split())) and (not kp or kp in cle(p["personne"]))]
            if not ko and not kp:
                cibles = []
        for p in cibles:
            await conn.execute("UPDATE inventaire_prets SET rendu_le=now() WHERE id=$1", p["id"])
    return cibles


async def prets(qui: str, tous: bool = False) -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT * FROM inventaire_prets " + ("" if tous else "WHERE rendu_le IS NULL ") +
                                "ORDER BY rendu_le IS NOT NULL, retour_prevu NULLS LAST, depuis LIMIT 200")
    return [_pret(r) for r in rows]


async def lieux(qui: str) -> list[str]:
    cond, args = _visible(qui)
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(f"SELECT DISTINCT emplacement FROM inventaire_objets WHERE {cond} AND emplacement<>'' ORDER BY 1", *args)
    return [r["emplacement"] for r in rows]


async def effacer_de(qui: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM inventaire_objets WHERE prive AND lower(owner)=lower($1)", qui or "")


def aujourdhui() -> str:
    return datetime.now().date().isoformat()
