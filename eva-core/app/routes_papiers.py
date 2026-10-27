"""API de la page Papiers. Accès : administrateur ou fonctionnalité « Papiers » (contrôlé par le middleware) ;
réglages et dossiers réservés à l'administrateur pour les modifications."""
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from . import papiers


class Modif(BaseModel):
    date_echeance: str | None = None
    preavis_jours: int | None = None
    description: str | None = None


class Nouvelle(BaseModel):
    paperless_id: int
    description: str
    date_echeance: str
    preavis_jours: int | None = None
    nature: str = "autre"


class Question(BaseModel):
    texte: str


class Dossier(BaseModel):
    chemin: str


def _err(exc: papiers.PapiersError) -> HTTPException:
    txt = str(exc)
    code = 404 if "introuvable" in txt.lower() else 409 if "pas configurés" in txt else 502 if "injoignable" in txt else 400
    return HTTPException(code, txt)


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api/papiers")

    @r.get("/etat")
    async def etat():
        out = {"reglages": papiers.reglages_publics(), "actif": papiers.active()}
        if out["actif"]:
            try:
                out["stats"] = await papiers.stats()
            except papiers.PapiersError as exc:
                out["erreur"] = str(exc)
        out["progression"] = await papiers.progression()
        return out

    @r.get("/test")
    async def test():
        return await papiers.tester()

    @r.get("/echeances")
    async def echeances(jours: int | None = 90, statut: str = "active,a_valider"):
        try:
            return await papiers.echeances(jours, tuple(s for s in statut.split(",") if s))
        except papiers.PapiersError as exc:
            raise _err(exc)

    @r.post("/echeances")
    async def ajouter(e: Nouvelle):
        try:
            return {"id": await papiers.ajouter(e.paperless_id, e.description, e.date_echeance, e.preavis_jours, e.nature)}
        except papiers.PapiersError as exc:
            raise _err(exc)

    @r.patch("/echeances/{ech_id}")
    async def modifier(ech_id: int, m: Modif):
        try:
            return await papiers.corriger(ech_id, m.model_dump(exclude_unset=True))
        except papiers.PapiersError as exc:
            raise _err(exc)

    @r.post("/echeances/{ech_id}/{action}")
    async def marquer(ech_id: int, action: str):
        try:
            return await papiers.marquer(ech_id, action)
        except papiers.PapiersError as exc:
            raise _err(exc)

    @r.get("/a-verifier")
    async def a_verifier():
        try:
            return await papiers.a_valider()
        except papiers.PapiersError as exc:
            raise _err(exc)

    @r.post("/documents/{doc_id}/valider")
    async def valider(doc_id: int):
        try:
            await papiers.valider_document(doc_id)
            return {"ok": True}
        except papiers.PapiersError as exc:
            raise _err(exc)

    @r.post("/documents/{doc_id}/retraiter")
    async def retraiter(doc_id: int):
        try:
            return await papiers.retraiter(doc_id)
        except papiers.PapiersError as exc:
            raise _err(exc)

    @r.post("/deposer")
    async def deposer(request: Request, nom: str = Query(..., min_length=1, max_length=200)):
        """Un fichier par requête (corps brut) : l'interface envoie les fichiers un par un pour le dépôt en masse."""
        donnees = await request.body()
        try:
            return await papiers.deposer_octets(nom, donnees)
        except papiers.PapiersError as exc:
            raise _err(exc)

    @r.post("/reanalyser")
    async def reanalyser():
        """Réanalyse tous les papiers (après un changement de modèle). Réservé à l'administrateur."""
        try:
            return {"a_refaire": await papiers.tout_reanalyser()}
        except papiers.PapiersError as exc:
            raise _err(exc)

    @r.post("/question")
    async def question(q: Question):
        try:
            return await papiers.question(q.texte[:500])
        except papiers.PapiersError as exc:
            raise _err(exc)

    @r.post("/sonder")
    async def sonder():
        papiers.reveiller()
        return {"ok": True}

    @r.get("/reglages")
    async def lire_reglages():
        return papiers.reglages_publics()

    @r.put("/reglages")
    async def ecrire_reglages(champs: dict):
        try:
            return await papiers.maj_reglages(champs)
        except papiers.PapiersError as exc:
            raise _err(exc)

    @r.get("/dossiers")
    async def dossiers(chemin: str = ""):
        try:
            return await papiers.parcourir(chemin)
        except papiers.PapiersError as exc:
            raise _err(exc)

    @r.post("/dossiers")
    async def creer(d: Dossier):
        try:
            return {"chemin": await papiers.creer_dossier(d.chemin)}
        except papiers.PapiersError as exc:
            raise _err(exc)

    return r
