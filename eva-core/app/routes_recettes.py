"""Livre de recettes (module activable) : recettes, partage par lien, liste de courses, page publique imprimable."""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import auth as auth_mod, medias, recettes


class Courses(BaseModel):
    personnes: int | None = None
    liste: str = "Courses"
    imprimer: bool = False
    imprimante: str = ""


class Partage(BaseModel):
    actif: bool = True


async def _moi(request: Request) -> tuple[str, str]:
    if not auth_mod.protected():
        return "", "admin"
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    return me["user"] or "", me["role"]


def _err(e: recettes.RecetteError) -> HTTPException:
    return HTTPException(e.status, str(e))


def make_routers() -> tuple[APIRouter, APIRouter]:
    r = APIRouter(prefix="/api/recettes")
    public = APIRouter(prefix="/api/public/recettes")

    @r.get("")
    async def lister(request: Request, q: str = Query("", max_length=200), categorie: str = Query("", max_length=40)):
        qui, role = await _moi(request)
        return {"recettes": await recettes.lister(qui, q, categorie), "categories": recettes.CATEGORIES,
                "difficultes": recettes.DIFFICULTES, "peut_ecrire": role != "guest"}

    @r.post("")
    async def creer(request: Request, body: dict):
        qui, role = await _moi(request)
        try:
            return await recettes.creer(qui, body or {}, role)
        except recettes.RecetteError as e:
            raise _err(e) from e

    @r.post("/analyser")
    async def analyser(body: dict):
        """Une ligne d'ingrédient tapée ou collée (« 200 g de farine ») → quantité, unité, nom."""
        return {"ingredients": [recettes.analyser_ligne(t) for t in str((body or {}).get("texte", "")).splitlines() if t.strip()][:recettes.MAX_INGREDIENTS]}

    @r.get("/{rid}")
    async def lire(request: Request, rid: int, personnes: int | None = Query(None, ge=1, le=100)):
        qui, role = await _moi(request)
        try:
            rec = await recettes.lire(qui, rid)
        except recettes.RecetteError as e:
            raise _err(e) from e
        n = personnes or rec["personnes"]
        rec["lignes"] = [recettes.ligne(i) for i in recettes.mise_a_echelle(rec["ingredients"], rec["personnes"], n)]
        rec["pour"] = n
        rec["peut_modifier"] = role == "admin" or (role != "guest" and rec["owner"] == (qui or "").lower())
        return rec

    @r.put("/{rid}")
    async def modifier(request: Request, rid: int, body: dict):
        qui, role = await _moi(request)
        try:
            avant = await recettes.lire(qui, rid)
            apres = await recettes.modifier(qui, rid, body or {}, role)
        except recettes.RecetteError as e:
            raise _err(e) from e
        medias.supprimer(set(recettes.medias_de(avant)) - set(recettes.medias_de(apres)))   # photos remplacées : effacées du NAS
        return apres

    @r.delete("/{rid}")
    async def supprimer(request: Request, rid: int):
        qui, role = await _moi(request)
        try:
            medias.supprimer(await recettes.supprimer(qui, rid, role))
        except recettes.RecetteError as e:
            raise _err(e) from e
        return {"ok": True}

    @r.post("/{rid}/partage")
    async def partager(request: Request, rid: int, body: Partage):
        qui, role = await _moi(request)
        try:
            rec = await recettes.partager(qui, rid, role, body.actif)
        except recettes.RecetteError as e:
            raise _err(e) from e
        return {"partage": rec["partage"], "url": f"/api/public/recettes/{rec['partage']}" if rec["partage"] else ""}

    @r.post("/{rid}/courses")
    async def courses(request: Request, rid: int, body: Courses):
        qui, _ = await _moi(request)
        try:
            res = await recettes.vers_courses(qui, rid, body.personnes, body.liste or "Courses")
        except recettes.RecetteError as e:
            raise _err(e) from e
        if body.imprimer:
            from . import lists, printing
            try:
                titre, texte = await lists.as_text(res["liste_id"], False)
                res["impression"] = await printing.print_text(texte, titre, body.imprimante)
            except printing.PrintError as e:
                res["impression_erreur"] = str(e)
        return res

    @public.get("/{jeton}", response_class=HTMLResponse)
    async def page(jeton: str):
        try:
            rec = await recettes.par_jeton(jeton)
        except recettes.RecetteError as e:
            return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>Recette</title><p style='font:18px system-ui;padding:40px'>{e}</p>", status_code=404)
        return HTMLResponse(recettes.page_html(rec), headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex",
                                                              "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; media-src 'self'; "
                                                              "frame-src https://www.youtube-nocookie.com; style-src 'unsafe-inline'; script-src 'unsafe-inline'"})

    return r, public
