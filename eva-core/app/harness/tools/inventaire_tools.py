"""Inventaire et prêts (module « inventaire », app/inventaire.py)."""
from typing import Any

from ... import inventaire, profiles
from ..permissions import Permission
from .base import Tool


def _qui() -> str:
    return profiles.user_var.get() or ""


class OuTool(Tool):
    name = "inventaire_ou"
    description = ("Où est rangé un objet de la maison, et s'il est prêté : « où est la perceuse ? », « où j'ai mis les piles ? », "
                   "« on a encore des ampoules ? ». lieu = lister ce qu'il y a dans un endroit (« qu'y a-t-il dans le garage ? »).")
    parameters = {"type": "object", "properties": {"objet": {"type": "string"}, "lieu": {"type": "string"}}}
    permission = Permission.AUTO

    async def execute(self, objet: str = "", lieu: str = "", **_: Any) -> dict:
        if lieu and not objet:
            l = await inventaire.lister(_qui(), "", lieu)
            return {"lieu": lieu, "objets": [f"{o['nom']} ({o['emplacement']})" for o in l[:30]], "nombre": len(l)}
        if not objet:
            return {"error": "Quel objet ?"}
        return await inventaire.ou_est(_qui(), objet)


class RangerTool(Tool):
    name = "inventaire_ranger"
    description = ("Note où un objet est rangé (l'ajoute à l'inventaire ou le déplace) : « la perceuse est dans le garage, sur l'établi », "
                   "« range les piles dans le tiroir de la cuisine », « on a 6 ampoules dans le cellier ». emplacement = du plus grand au "
                   "plus petit (« Garage › Établi › Tiroir 2 »). prive = seul moi le vois.")
    parameters = {"type": "object", "properties": {
        "objet": {"type": "string"}, "emplacement": {"type": "string"}, "quantite": {"type": "integer"},
        "notes": {"type": "string"}, "prive": {"type": "boolean"}}, "required": ["objet"]}
    permission = Permission.AUTO

    async def execute(self, objet: str = "", emplacement: str = "", quantite: int | None = None, notes: str | None = None,
                      prive: bool | None = None, **_: Any) -> dict:
        try:
            o = await inventaire.ranger(_qui(), objet, emplacement, quantite, notes, prive)
        except inventaire.InventaireError as e:
            return {"error": str(e)}
        return {"ok": True, "objet": o["nom"], "emplacement": o["emplacement"], "quantite": o["quantite"], "nouveau": o["nouveau"]}


class PreterTool(Tool):
    name = "inventaire_preter"
    description = ("Note un prêt : « j'ai prêté la tondeuse à Paul jusqu'au 15 juin » (sens=prete), « Marie m'a prêté sa scie » "
                   "(sens=emprunte). retour = date AAAA-MM-JJ facultative.")
    parameters = {"type": "object", "properties": {
        "objet": {"type": "string"}, "personne": {"type": "string"}, "sens": {"type": "string", "enum": ["prete", "emprunte"]},
        "retour": {"type": "string"}}, "required": ["objet", "personne"]}
    permission = Permission.AUTO

    async def execute(self, objet: str = "", personne: str = "", sens: str = "prete", retour: str = "", **_: Any) -> dict:
        try:
            p = await inventaire.preter(_qui(), objet, personne, sens or "prete", retour or None)
        except inventaire.InventaireError as e:
            return {"error": str(e)}
        return {"ok": True, **{k: p[k] for k in ("objet", "personne", "sens", "retour_prevu", "dans_inventaire")}}


class RenduTool(Tool):
    name = "inventaire_rendu"
    description = "Note qu'un objet prêté ou emprunté est rendu : « Paul m'a rendu la tondeuse », « j'ai rendu la scie à Marie »."
    parameters = {"type": "object", "properties": {"objet": {"type": "string"}, "personne": {"type": "string"}}}
    permission = Permission.AUTO

    async def execute(self, objet: str = "", personne: str = "", **_: Any) -> dict:
        r = await inventaire.rendre(_qui(), objet, personne)
        if not r:
            return {"error": "Je ne trouve pas ce prêt en cours."}
        return {"ok": True, "rendus": [f"{p['objet']} ({p['personne']})" for p in r]}


class PretsTool(Tool):
    name = "inventaire_prets"
    description = "Prêts en cours (prêtés et empruntés), en retard d'abord : « qu'est-ce que j'ai prêté ? », « qui a ma perceuse ? »."
    parameters = {"type": "object", "properties": {}}
    permission = Permission.AUTO

    async def execute(self, **_: Any) -> dict:
        l = await inventaire.prets(_qui())
        return {"prets": [f"{p['objet']} {'prêté à' if p['sens'] == 'prete' else 'emprunté à'} {p['personne']} depuis le {p['depuis']}"
                          + (f", retour prévu le {p['retour_prevu']}" if p["retour_prevu"] else "") + (" (EN RETARD)" if p["en_retard"] else "")
                          for p in l] or ["Aucun prêt en cours."]}


def all_tools() -> list[Tool]:
    return [OuTool(), RangerTool(), PreterTool(), RenduTool(), PretsTool()]
