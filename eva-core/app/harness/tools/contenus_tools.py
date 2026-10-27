"""Suivi de contenus : noter une idée, voir ce qui est prévu, faire avancer un contenu."""
from typing import Any

from ... import contenus, profiles
from ..permissions import Permission
from .base import Tool


async def _sur(coro) -> dict:
    try:
        return await coro
    except contenus.ContenuError as exc:
        return {"error": str(exc)}


class ContenuIdeeTool(Tool):
    name = "contenu_idee"
    description = ("Note une idée de contenu (vidéo, publication, live…) dans le suivi de contenus : titre, plateformes, notes, date prévue (AAAA-MM-JJ) "
                   "si elle est donnée. « Note une idée de vidéo : … ».")
    parameters = {"type": "object", "properties": {
        "titre": {"type": "string"}, "plateformes": {"type": "array", "items": {"type": "string", "enum": contenus.PLATEFORMES}},
        "notes": {"type": "string"}, "date_prevue": {"type": "string"}}, "required": ["titre"]}
    permission = Permission.AUTO

    async def execute(self, titre: str = "", plateformes: list | None = None, notes: str = "", date_prevue: str = "", **_: Any) -> dict:
        r = await _sur(contenus.creer(profiles.user_var.get() or "", {"titre": titre, "plateformes": plateformes or [], "notes": notes,
                                                                        "date_prevue": date_prevue or None}))
        return r if "error" in r else {"ok": True, "id": r["id"], "titre": r["titre"], "etat": "Idée"}


class ContenuListerTool(Tool):
    name = "contenu_lister"
    description = "Où en sont les contenus : nombre par étape, ce qui est prévu dans les 7 jours, ce qui est en retard, dernières idées."
    parameters = {"type": "object", "properties": {}}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, **_: Any) -> dict:
        return await _sur(contenus.resume(profiles.user_var.get() or ""))


class ContenuAvancerTool(Tool):
    name = "contenu_avancer"
    description = ("Fait avancer ou modifie un contenu (id donné par contenu_lister) : etat = idee, script, tournage, montage, programme ou publie ; "
                   "date_prevue (AAAA-MM-JJ), titre, plateformes, lien une fois publié, notes à ajouter (plan, script, idées de miniature…).")
    parameters = {"type": "object", "properties": {
        "id": {"type": "integer"}, "etat": {"type": "string", "enum": contenus.ETATS}, "date_prevue": {"type": "string"},
        "titre": {"type": "string", "description": "Nouveau titre"},
        "plateformes": {"type": "array", "items": {"type": "string", "enum": contenus.PLATEFORMES}},
        "lien": {"type": "string"}, "notes": {"type": "string", "description": "Ajoutées à la fin des notes existantes"}}, "required": ["id"]}
    permission = Permission.AUTO

    async def execute(self, id: int = 0, etat: str = "", date_prevue: str = "", lien: str = "", notes: str = "", titre: str = "",  # noqa: A002
                      plateformes: list | None = None, **_: Any) -> dict:
        qui = profiles.user_var.get() or ""
        champs: dict = {}
        if titre:
            champs["titre"] = titre
        if plateformes:
            champs["plateformes"] = plateformes
        if etat:
            champs["etat"] = etat
        if date_prevue:
            champs["date_prevue"] = date_prevue
        if lien:
            champs["lien"] = lien
        if notes:
            avant = await _sur(contenus.lire(qui, id))
            if "error" in avant:
                return avant
            champs["notes"] = (avant["notes"] + "\n" + notes).strip()
        r = await _sur(contenus.modifier(qui, id, champs))
        return r if "error" in r else {"ok": True, "titre": r["titre"], "etat": contenus.NOMS_ETATS[r["etat"]], "date_prevue": r["date_prevue"]}
