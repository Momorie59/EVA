"""Livre de recettes de la famille (module activable).

Une recette : photo, résumé, nombre de personnes, temps, difficulté, ingrédients (quantité, unité, nom), étapes (texte,
photo facultative), vidéo (fichier envoyé sur le NAS ou lien YouTube), notes, étiquettes.
- Livre partagé : toute personne qui a la fonctionnalité « recettes » lit les recettes non privées ; l'auteur ou
  l'administrateur les modifie ; un invité ne fait que lire.
- Quantités recalculées pour le nombre de personnes voulu ; ingrédients envoyés à la liste de courses en un clic.
- Partage : lien en lecture seule (belle page, imprimable en PDF), révocable ; le livre entier s'imprime depuis EVA."""
import html
import json
import re
import secrets
from fractions import Fraction

from .db import get_pool

CATEGORIES = ["Apéritif", "Entrée", "Plat", "Accompagnement", "Dessert", "Goûter", "Boisson", "Sauce", "Autre"]
DIFFICULTES = ["Facile", "Moyen", "Difficile"]
MAX_INGREDIENTS = 60
MAX_ETAPES = 40

SCHEMA = """
CREATE TABLE IF NOT EXISTS recettes (
    id BIGSERIAL PRIMARY KEY,
    owner TEXT NOT NULL DEFAULT '',
    titre TEXT NOT NULL,
    resume TEXT NOT NULL DEFAULT '',
    personnes INT NOT NULL DEFAULT 4,
    prep_min INT NOT NULL DEFAULT 0,
    cuisson_min INT NOT NULL DEFAULT 0,
    repos_min INT NOT NULL DEFAULT 0,
    difficulte TEXT NOT NULL DEFAULT 'Facile',
    categorie TEXT NOT NULL DEFAULT 'Plat',
    tags TEXT[] NOT NULL DEFAULT '{}',
    ingredients JSONB NOT NULL DEFAULT '[]'::jsonb,
    etapes JSONB NOT NULL DEFAULT '[]'::jsonb,
    photo TEXT NOT NULL DEFAULT '',
    video TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    prive BOOLEAN NOT NULL DEFAULT FALSE,
    partage TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS recettes_titre ON recettes (lower(titre));
"""


class RecetteError(Exception):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


# ------------------------------------------------------------------ quantités
_UNITES_SANS_DE = {"", "pièce", "pièces"}
_VOYELLE = re.compile(r"^[aeiouyhâàéèêëîïôöûüœæ]", re.I)


def nombre(texte) -> float | None:
    """« 200 », « 1,5 », « 1/2 », « ½ », « 1 1/2 » → nombre ; vide → None."""
    if texte is None or texte == "":
        return None
    if isinstance(texte, (int, float)):
        return float(texte)
    t = str(texte).strip().replace(",", ".").replace("½", " 1/2").replace("¼", " 1/4").replace("¾", " 3/4").replace("⅓", " 1/3")
    try:
        return float(sum(Fraction(p) for p in t.split()))
    except (ValueError, ZeroDivisionError):
        return None


def joli(q: float | None) -> str:
    """Quantité lisible en français : 1,5 / ½ / 250 / 0,33 → ⅓."""
    if q is None:
        return ""
    if q < 10:                                   # ½ citron, 1 ½ pincée… mais jamais « 312 ½ g »
        for v, s in ((0.25, "¼"), (0.5, "½"), (0.75, "¾"), (1 / 3, "⅓"), (2 / 3, "⅔")):
            entier = int(q)
            if abs(q - entier - v) < 0.02:
                return (f"{entier} " if entier else "") + s
    if q >= 10:
        q = round(q)
    elif q >= 1:
        q = round(q * 2) / 2 if abs(q * 2 - round(q * 2)) < 0.1 else round(q, 1)
    else:
        q = round(q, 2)
    return (f"{q:.2f}".rstrip("0").rstrip(".") if q != int(q) else str(int(q))).replace(".", ",")


def mise_a_echelle(ingredients: list[dict], base: int, personnes: int) -> list[dict]:
    k = personnes / base if base and personnes else 1
    return [{**i, "quantite": (i["quantite"] * k if isinstance(i.get("quantite"), (int, float)) else i.get("quantite"))} for i in ingredients]


_PLURIEL = {"gousse", "pincée", "tranche", "feuille", "brin", "sachet", "boîte", "boite", "pot", "verre", "tasse", "pièce", "morceau",
            "cuillère à soupe", "cuillère à café"}


def accorder(unite: str, q: float | None) -> str:
    """« gousse » → « gousses » au-delà de 1 (« 2 gousses d'ail »)."""
    u = unite.strip()
    if q is None or q <= 1.0001 or u.lower() not in _PLURIEL:
        return u
    if u.lower() == "morceau":
        return u + "x"
    if u.lower().startswith("cuillère"):
        return u.replace("cuillère", "cuillères", 1)
    return u + "s"


def ligne(i: dict) -> str:
    """{200, g, farine} → « 200 g de farine » ; {3, '', œufs} → « 3 œufs » ; {None, '', sel} → « sel »."""
    q, nom = joli(i.get("quantite")), (i.get("nom") or "").strip()
    u = accorder(i.get("unite") or "", i.get("quantite") if isinstance(i.get("quantite"), (int, float)) else None)
    if not q:
        return nom
    if u.lower() in _UNITES_SANS_DE:
        return f"{q} {u} {nom}".replace("  ", " ").strip() if u else f"{q} {nom}"
    de = "d'" if _VOYELLE.match(nom) else "de "
    return f"{q} {u} {de}{nom}"


def analyser_ligne(texte: str) -> dict:
    """« 200 g de farine » → {200, g, farine} ; « 3 œufs » → {3, '', œufs} ; « sel, poivre » → {None, '', sel, poivre}."""
    t = " ".join((texte or "").split())
    m = re.match(r"^(?P<q>[\d.,/½¼¾⅓]+(?:\s+\d+/\d+)?)\s*(?P<u>kg|g|mg|l|cl|ml|dl|c\.\s?à\s?s\.?|c\.\s?à\s?c\.?|cuill[eè]res? à (?:soupe|café)|"
                 r"tasses?|verres?|pinc[ée]es?|gousses?|tranches?|feuilles?|brins?|sachets?|bo[iî]tes?|pots?|morceaux?|pi[eè]ces?)?(?![a-zà-ÿ])\.?\s*(?:d'|de\s+|des\s+)?(?P<nom>.*)$", t, re.I)
    if m and m.group("q") and nombre(m.group("q")) is not None:
        return {"quantite": nombre(m.group("q")), "unite": (m.group("u") or "").strip(), "nom": m.group("nom").strip() or t}
    return {"quantite": None, "unite": "", "nom": t}


# ------------------------------------------------------------------ nettoyage
def _youtube(url: str) -> str:
    m = re.search(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})", url or "")
    return f"yt:{m.group(1)}" if m else ""


def _media_ok(f: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{32}\.[a-z0-9]{2,5}", f or ""))


def _propre(d: dict) -> dict:
    titre = " ".join(str(d.get("titre") or "").split())[:150]
    if not titre:
        raise RecetteError("Donne un nom à la recette.")
    ingredients = []
    for i in (d.get("ingredients") or [])[:MAX_INGREDIENTS]:
        if isinstance(i, str):
            i = analyser_ligne(i)
        nom = " ".join(str(i.get("nom") or "").split())[:120]
        if nom:
            ingredients.append({"quantite": nombre(i.get("quantite")), "unite": str(i.get("unite") or "").strip()[:20], "nom": nom,
                                "groupe": str(i.get("groupe") or "").strip()[:60]})
    etapes = []
    for e in (d.get("etapes") or [])[:MAX_ETAPES]:
        if isinstance(e, str):
            e = {"texte": e}
        texte = str(e.get("texte") or "").strip()[:3000]
        photo = e.get("photo") if _media_ok(e.get("photo")) else ""
        if texte or photo:
            etapes.append({"texte": texte, "photo": photo, "minuteur_min": max(0, int(nombre(e.get("minuteur_min")) or 0))})
    video = str(d.get("video") or "").strip()
    video = video if _media_ok(video) or video.startswith("yt:") else _youtube(video)
    ent = lambda k, lo=0, hi=100000: max(lo, min(hi, int(nombre(d.get(k)) or 0)))   # noqa: E731
    return {
        "titre": titre, "resume": str(d.get("resume") or "").strip()[:1000],
        "personnes": max(1, min(100, int(nombre(d.get("personnes")) or 4))),
        "prep_min": ent("prep_min"), "cuisson_min": ent("cuisson_min"), "repos_min": ent("repos_min"),
        "difficulte": d.get("difficulte") if d.get("difficulte") in DIFFICULTES else "Facile",
        "categorie": d.get("categorie") if d.get("categorie") in CATEGORIES else "Plat",
        "tags": [str(t).strip().lower()[:30] for t in (d.get("tags") or []) if str(t).strip()][:12],
        "ingredients": ingredients, "etapes": etapes,
        "photo": d.get("photo") if _media_ok(d.get("photo")) else "", "video": video,
        "notes": str(d.get("notes") or "").strip()[:4000], "prive": bool(d.get("prive", False)),
    }


def _rec(r, complet: bool = True) -> dict:
    d = {"id": r["id"], "owner": r["owner"], "titre": r["titre"], "resume": r["resume"], "personnes": r["personnes"],
         "prep_min": r["prep_min"], "cuisson_min": r["cuisson_min"], "repos_min": r["repos_min"], "difficulte": r["difficulte"],
         "categorie": r["categorie"], "tags": list(r["tags"] or []), "photo": r["photo"], "prive": r["prive"],
         "partage": r["partage"] or "", "updated_at": r["updated_at"].isoformat(), "created_at": r["created_at"].isoformat()}
    if complet:
        d.update(ingredients=_json(r["ingredients"]), etapes=_json(r["etapes"]), video=r["video"], notes=r["notes"])
    return d


def _json(v):
    return json.loads(v) if isinstance(v, str) else (v or [])


def _visible(n: int) -> str:
    return f"(NOT prive OR owner=${n})"


# ------------------------------------------------------------------ lecture / écriture
async def lister(qui: str, q: str = "", categorie: str = "", limite: int = 500) -> list[dict]:
    args: list = [(qui or "").lower()]
    cond = [_visible(1)]
    if q.strip():
        args.append(f"%{q.strip()}%")
        n = len(args)
        cond.append(f"(titre ILIKE ${n} OR resume ILIKE ${n} OR array_to_string(tags,' ') ILIKE ${n} OR ingredients::text ILIKE ${n})")
    if categorie:
        args.append(categorie)
        cond.append(f"categorie=${len(args)}")
    args.append(limite)
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(f"SELECT * FROM recettes WHERE {' AND '.join(cond)} ORDER BY lower(titre) LIMIT ${len(args)}", *args)
    return [_rec(r, complet=False) for r in rows]


async def lire(qui: str, rid: int) -> dict:
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow(f"SELECT * FROM recettes WHERE id=$2 AND {_visible(1)}", (qui or "").lower(), int(rid))
    if r is None:
        raise RecetteError("Recette introuvable.", 404)
    return _rec(r)


async def par_titre(qui: str, titre: str) -> dict | None:
    t = (titre or "").strip()
    if not t:
        return None
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow(f"SELECT * FROM recettes WHERE {_visible(1)} AND lower(titre)=lower($2)", (qui or "").lower(), t)
        if r is None:
            r = await conn.fetchrow(f"SELECT * FROM recettes WHERE {_visible(1)} AND titre ILIKE $2 ORDER BY length(titre) LIMIT 1",
                                    (qui or "").lower(), f"%{t}%")
    return _rec(r) if r else None


def _peut_modifier(rec: dict, qui: str, role: str) -> None:
    if role == "guest":
        raise RecetteError("Un invité ne fait que lire les recettes.", 403)
    if role != "admin" and rec["owner"] != (qui or "").lower():
        raise RecetteError("Seul l'auteur de la recette (ou l'administrateur) peut la modifier.", 403)


async def creer(qui: str, d: dict, role: str = "user") -> dict:
    if role == "guest":
        raise RecetteError("Un invité ne fait que lire les recettes.", 403)
    p = _propre(d)
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow(
            "INSERT INTO recettes (owner, titre, resume, personnes, prep_min, cuisson_min, repos_min, difficulte, categorie, tags, "
            "ingredients, etapes, photo, video, notes, prive) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12::jsonb,$13,$14,$15,$16) RETURNING *",
            (qui or "").lower(), p["titre"], p["resume"], p["personnes"], p["prep_min"], p["cuisson_min"], p["repos_min"], p["difficulte"],
            p["categorie"], p["tags"], json.dumps(p["ingredients"]), json.dumps(p["etapes"]), p["photo"], p["video"], p["notes"], p["prive"])
    return _rec(r)


async def modifier(qui: str, rid: int, d: dict, role: str = "user") -> dict:
    rec = await lire(qui, rid)
    _peut_modifier(rec, qui, role)
    p = _propre({**rec, **d})
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow(
            "UPDATE recettes SET titre=$2, resume=$3, personnes=$4, prep_min=$5, cuisson_min=$6, repos_min=$7, difficulte=$8, categorie=$9, "
            "tags=$10, ingredients=$11::jsonb, etapes=$12::jsonb, photo=$13, video=$14, notes=$15, prive=$16, updated_at=now() WHERE id=$1 RETURNING *",
            rec["id"], p["titre"], p["resume"], p["personnes"], p["prep_min"], p["cuisson_min"], p["repos_min"], p["difficulte"], p["categorie"],
            p["tags"], json.dumps(p["ingredients"]), json.dumps(p["etapes"]), p["photo"], p["video"], p["notes"], p["prive"])
    return _rec(r)


def medias_de(rec: dict) -> list[str]:
    out = [rec.get("photo"), *(e.get("photo") for e in rec.get("etapes", []))]
    if _media_ok(rec.get("video", "")):
        out.append(rec["video"])
    return [f for f in out if f]


async def supprimer(qui: str, rid: int, role: str = "user") -> list[str]:
    rec = await lire(qui, rid)
    _peut_modifier(rec, qui, role)
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM recettes WHERE id=$1", rec["id"])
    return medias_de(rec)


async def partager(qui: str, rid: int, role: str = "user", actif: bool = True) -> dict:
    rec = await lire(qui, rid)
    _peut_modifier(rec, qui, role)
    jeton = secrets.token_urlsafe(18) if actif else None
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow("UPDATE recettes SET partage=$2 WHERE id=$1 RETURNING *", rec["id"], jeton)
    return _rec(r)


async def par_jeton(jeton: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,40}", jeton or ""):
        raise RecetteError("Lien de partage invalide ou retiré.", 404)
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM recettes WHERE partage=$1", jeton)
    if r is None:
        raise RecetteError("Lien de partage invalide ou retiré.", 404)
    return _rec(r)


async def vers_courses(qui: str, rid: int, personnes: int | None = None, liste: str = "Courses") -> dict:
    """Ajoute les ingrédients (quantités pour `personnes`) à la liste de courses. Renvoie la liste et ce qui a été ajouté."""
    from . import lists
    rec = await lire(qui, rid)
    n = max(1, min(100, int(personnes or rec["personnes"])))
    lignes = [ligne(i) for i in mise_a_echelle(rec["ingredients"], rec["personnes"], n)]
    if not lignes:
        raise RecetteError("Cette recette n'a pas encore d'ingrédients.")
    lst = await lists.find(liste, create=True)
    r = await lists.add(lst["id"], lignes, by=(qui or "eva"))
    return {"liste": lst["name"], "liste_id": lst["id"], "personnes": n, "ajoutes": r.get("added", []), "deja": r.get("already_there", [])}


_TOUT = re.compile(r"^\W*(?:toutes?|tous|tout|mes|les|la liste|liste|livre|toutes? (?:mes|les) recettes?|mes recettes?|les recettes?|recettes?|\*)\W*$", re.I)


async def chercher(qui: str, q: str, limite: int = 5) -> list[dict]:
    q = (q or "").strip()
    if not q or _TOUT.match(q):                         # « liste mes recettes » : tout le livre
        return await lister(qui, "", limite=200)
    out = await lister(qui, q, limite=limite)
    if not out:
        mots = [m for m in re.findall(r"\w{3,}", q.lower()) if m not in {"recette", "recettes", "avec", "pour", "les", "des"}][:5]
        vus = {}
        for m in mots:
            for r in await lister(qui, m, limite=limite):
                vus.setdefault(r["id"], r)
        out = list(vus.values())[:limite]
    return out


async def effacer_de(qui: str) -> list[str]:
    """Pour « Mes données » : supprime les recettes de la personne, renvoie leurs médias à effacer."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("DELETE FROM recettes WHERE owner=$1 RETURNING *", (qui or "").lower())
    out = []
    for r in rows:
        out += medias_de(_rec(r))
    return out


async def donnees_de(qui: str) -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT * FROM recettes WHERE owner=$1 ORDER BY titre", (qui or "").lower())
    return [_rec(r) for r in rows]


# ------------------------------------------------------------------ page partagée (HTML autonome, imprimable)
def _duree(m: int) -> str:
    if not m:
        return ""
    return f"{m // 60} h {m % 60:02d}" if m >= 60 else f"{m} min"


def page_html(rec: dict) -> str:
    e = html.escape
    media = lambda f: f"/api/public/medias/{f}"                                  # noqa: E731
    temps = [(lbl, _duree(rec[k])) for lbl, k in (("Préparation", "prep_min"), ("Cuisson", "cuisson_min"), ("Repos", "repos_min")) if rec[k]]
    ingredients = "".join(
        f'<li data-q="{i["quantite"] if isinstance(i.get("quantite"), (int, float)) else ""}" data-u="{e(i.get("unite") or "")}" data-n="{e(i["nom"])}">{e(ligne(i))}</li>'
        for i in rec["ingredients"])
    etapes = "".join(
        f'<li><p>{e(s["texte"]).replace(chr(10), "<br>")}</p>' + (f'<img src="{media(s["photo"])}" alt="" loading="lazy">' if s.get("photo") else "")
        + (f'<span class="minuteur">⏱ {s["minuteur_min"]} min</span>' if s.get("minuteur_min") else "") + "</li>"
        for s in rec["etapes"])
    video = ""
    if rec.get("video", "").startswith("yt:"):
        video = (f'<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/{e(rec["video"][3:])}" title="Vidéo" '
                 'allow="accelerometer; encrypted-media; picture-in-picture" allowfullscreen loading="lazy"></iframe></div>')
    elif rec.get("video"):
        video = f'<div class="video"><video src="{media(rec["video"])}" controls preload="metadata"></video></div>'
    photo = f'<img class="couverture" src="{media(rec["photo"])}" alt="">' if rec.get("photo") else '<div class="couverture vide">🍲</div>'
    chips = "".join(f"<span>{e(t)}</span>" for t in [rec["categorie"], rec["difficulte"], *[f"{l} {v}" for l, v in temps]])
    notes = f'<section class="notes"><h2>Le petit plus</h2><p>{e(rec["notes"]).replace(chr(10), "<br>")}</p></section>' if rec.get("notes") else ""
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(rec["titre"])} — recette</title>
<meta property="og:title" content="{e(rec["titre"])}"><meta property="og:description" content="{e(rec["resume"][:200])}">
{f'<meta property="og:image" content="{media(rec["photo"])}">' if rec.get("photo") else ""}
<style>
:root{{--fond:#fbf7f1;--encre:#2b2420;--doux:#7a6a5d;--accent:#c8553d;--carte:#fff}}
@media (prefers-color-scheme:dark){{:root{{--fond:#1d1916;--encre:#f3ebe3;--doux:#b9a99b;--accent:#e9765d;--carte:#28221e}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--fond);color:var(--encre);font:16px/1.6 Georgia,"Times New Roman",serif}}
main{{max-width:880px;margin:0 auto;padding:0 16px 96px}}
.couverture{{width:100%;max-height:420px;object-fit:cover;border-radius:0 0 22px 22px;display:block}}
.couverture.vide{{height:160px;display:grid;place-items:center;font-size:64px;background:linear-gradient(135deg,#f2d7c0,#e9b48f)}}
h1{{font-size:clamp(28px,6vw,44px);line-height:1.15;margin:22px 0 8px}}
.resume{{font-size:18px;color:var(--doux);font-style:italic;margin:0 0 14px}}
.chips{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px}}.chips span{{padding:4px 12px;border-radius:99px;background:var(--carte);border:1px solid rgba(0,0,0,.08);font:13px system-ui,sans-serif}}
.grille{{display:grid;grid-template-columns:minmax(220px,1fr) 2fr;gap:28px;align-items:start}}
.ingredients{{background:var(--carte);border-radius:16px;padding:18px 20px;box-shadow:0 6px 24px rgba(0,0,0,.06);position:sticky;top:12px}}
h2{{font-size:20px;margin:0 0 10px;color:var(--accent)}}
.portions{{display:flex;align-items:center;gap:8px;font:14px system-ui,sans-serif;margin-bottom:10px}}
.portions button{{width:30px;height:30px;border-radius:50%;border:1px solid var(--accent);background:none;color:var(--accent);font-size:18px;cursor:pointer}}
.ingredients ul{{padding-left:18px;margin:0}}.ingredients li{{margin:4px 0}}
.etapes ol{{counter-reset:e;list-style:none;padding:0;margin:0}}.etapes li{{counter-increment:e;position:relative;padding:0 0 18px 48px}}
.etapes li::before{{content:counter(e);position:absolute;left:0;top:0;width:34px;height:34px;border-radius:50%;background:var(--accent);color:#fff;display:grid;place-items:center;font:600 15px system-ui,sans-serif}}
.etapes p{{margin:4px 0 8px}}.etapes img{{max-width:100%;border-radius:12px;margin:4px 0}}
.minuteur{{font:13px system-ui,sans-serif;color:var(--doux)}}
.video{{margin:26px 0;aspect-ratio:16/9}}.video iframe,.video video{{width:100%;height:100%;border:0;border-radius:14px;background:#000}}
.notes{{margin-top:22px;padding:16px 20px;border-left:4px solid var(--accent);background:var(--carte);border-radius:0 12px 12px 0}}
footer{{margin-top:36px;text-align:center;color:var(--doux);font:13px system-ui,sans-serif}}
.imprimer{{position:fixed;right:16px;bottom:16px;padding:10px 16px;border-radius:99px;border:0;background:var(--accent);color:#fff;font:600 14px system-ui,sans-serif;cursor:pointer;box-shadow:0 6px 18px rgba(0,0,0,.2)}}
@media (max-width:700px){{.grille{{grid-template-columns:1fr}}.ingredients{{position:static}}}}
@media print{{body{{background:#fff;color:#000}}.imprimer,.portions button,.video{{display:none}}.couverture{{max-height:260px;border-radius:12px}}
.ingredients{{box-shadow:none;border:1px solid #ddd;position:static}}.etapes li{{break-inside:avoid}}}}
</style></head><body><main>
{photo}
<h1>{e(rec["titre"])}</h1>
{f'<p class="resume">{e(rec["resume"])}</p>' if rec.get("resume") else ""}
<div class="chips">{chips}</div>
<div class="grille">
<section class="ingredients"><h2>Ingrédients</h2>
<div class="portions"><button type="button" onclick="portions(-1)" aria-label="Moins de personnes">−</button>
<span>Pour <b id="n">{rec["personnes"]}</b> personne(s)</span><button type="button" onclick="portions(1)" aria-label="Plus de personnes">+</button></div>
<ul id="ing">{ingredients}</ul></section>
<section class="etapes"><h2>Préparation</h2><ol>{etapes}</ol></section>
</div>
{video}{notes}
<footer>Recette partagée depuis EVA</footer>
</main>
<button class="imprimer" onclick="window.print()">Imprimer / PDF</button>
<script>
const base={rec["personnes"]};let n=base;
const F=[[.25,"¼"],[.5,"½"],[.75,"¾"],[1/3,"⅓"],[2/3,"⅔"]];
function joli(q){{const e=Math.floor(q);if(q<10){{for(const[v,s]of F){{if(Math.abs(q-e-v)<.02)return(e?e+" ":"")+s}}}}
q=q>=10?Math.round(q):q>=1?Math.round(q*10)/10:Math.round(q*100)/100;return String(q).replace(".",",")}}
const SANS=new Set(["","pièce","pièces"]);
function portions(d){{n=Math.max(1,n+d);document.getElementById("n").textContent=n;
document.querySelectorAll("#ing li").forEach(li=>{{const q=parseFloat(li.dataset.q);if(isNaN(q))return;const u=li.dataset.u,nom=li.dataset.n;
const qq=q*n/base,v=joli(qq),P=new Set(["gousse","pincée","tranche","feuille","brin","sachet","boîte","pot","verre","tasse","pièce"]);
const uu=qq>1.0001&&P.has(u.toLowerCase())?u+"s":u.toLowerCase()==="morceau"&&qq>1.0001?u+"x":u;li.textContent=SANS.has(u.toLowerCase())?(uu?v+" "+uu+" "+nom:v+" "+nom):v+" "+uu+" "+(/^[aeiouyhâàéèêëîïôöûüœæ]/i.test(nom)?"d'":"de ")+nom}})}}
</script></body></html>"""
