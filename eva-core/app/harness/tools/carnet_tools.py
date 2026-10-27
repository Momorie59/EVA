"""Outils « carnets » : EVA lit et écrit dans les carnets (sections et pages, comme OneNote) avec les droits de la personne :
« note dans mon carnet Vacances la liste des choses à emporter », « qu'est-ce que j'ai écrit dans le carnet Travaux ? »."""
import unicodedata
from typing import Any

from ... import features as features_mod, notebooks as nbk, profiles
from ..permissions import Permission
from .base import Tool


def _plat(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn").strip()


async def _qui() -> dict:
    user, role = profiles.user_var.get() or "", profiles.role_var.get() or "admin"
    groupes = []
    if role != "admin" and user:
        groupes = (await features_mod._load())["users"].get(user.lower(), {}).get("groups", [])
    return {"user": user, "role": role, "groups": groupes}


def _choisir(liste: list[dict], nom: str, cle: str = "title") -> dict | None:
    n = _plat(nom)
    if not n:
        return None
    return next((x for x in liste if _plat(x[cle]) == n), None) or next((x for x in liste if n in _plat(x[cle])), None)


class CarnetListerTool(Tool):
    name = "carnet_lister"
    description = "Liste les carnets de notes accessibles (les siens et ceux partagés) avec leurs sections et pages."
    parameters = {"type": "object", "properties": {}}
    permission = Permission.AUTO

    async def execute(self, **_: Any) -> dict:
        who = await _qui()
        out = []
        for c in await nbk.list_for(who):
            d = await nbk.get_for(c["id"], who)
            out.append({"carnet": c["title"], "droit": c["perm"], "sections": [{"section": s["title"], "pages": [p["title"] for p in s["pages"]]} for s in d["tree"]]})
        return {"carnets": out}


class CarnetLireTool(Tool):
    name = "carnet_lire"
    description = "Lit une page (ou toutes les pages d'une section) d'un carnet de notes."
    parameters = {"type": "object", "properties": {"carnet": {"type": "string"}, "section": {"type": "string"}, "page": {"type": "string"}},
                  "required": ["carnet"]}
    permission = Permission.AUTO

    async def execute(self, carnet: str = "", section: str = "", page: str = "", **_: Any) -> dict:
        who = await _qui()
        c = _choisir(await nbk.list_for(who), carnet)
        if not c:
            return {"error": f"Carnet « {carnet} » introuvable (carnet_lister)."}
        d = await nbk.get_for(c["id"], who)
        sections = [s for s in d["tree"] if not section or _choisir([s], section)]
        pages = [{"section": s["title"], "page": p["title"], "texte": p["text"][:6000]} for s in sections for p in s["pages"]
                 if not page or _choisir([p], page)]
        if not pages:
            return {"error": "Aucune page ne correspond."}
        return {"carnet": c["title"], "pages": pages[:20]}


class CarnetEcrireTool(Tool):
    name = "carnet_ecrire"
    description = ("Écrit dans un carnet de notes : ajoute une page, ou complète / remplace une page existante. Crée le carnet ou la section "
                   "s'ils n'existent pas. mode « ajouter » (à la fin de la page, défaut) ou « remplacer ».")
    parameters = {"type": "object", "properties": {
        "carnet": {"type": "string"}, "section": {"type": "string"}, "page": {"type": "string", "description": "Titre de la page"},
        "texte": {"type": "string"}, "mode": {"type": "string", "enum": ["ajouter", "remplacer"]}}, "required": ["carnet", "page", "texte"]}
    permission = Permission.CONFIRM

    async def execute(self, carnet: str = "", section: str = "", page: str = "", texte: str = "", mode: str = "ajouter", **_: Any) -> dict:
        who = await _qui()
        try:
            c = _choisir(await nbk.list_for(who), carnet)
            cree = []
            if not c:
                c = await nbk.create(who, carnet)
                cree.append("carnet")
            d = await nbk.get_for(c["id"], who)
            s = _choisir(d["tree"], section) if section else d["tree"][0]
            if not s:
                s = await nbk.add_section(c["id"], who, section)
                cree.append("section")
            p = _choisir(s["pages"], page)
            if p is None and len(s["pages"]) == 1 and not s["pages"][0]["text"].strip() and s["pages"][0]["title"] == "Page sans titre":
                p = s["pages"][0]                           # page vide d'un carnet tout neuf : on l'utilise
            if p is None:
                p = await nbk.add_page(c["id"], s["id"], who, page, texte)
                cree.append("page")
            else:
                nouveau = texte if mode == "remplacer" or not p["text"].strip() else p["text"].rstrip() + "\n\n" + texte
                p = await nbk.save_page(c["id"], p["id"], who, page if p["title"] == "Page sans titre" else None, nouveau)
        except nbk.NotebookError as e:
            return {"error": str(e)}
        return {"ok": True, "carnet": c["title"], "section": s["title"], "page": p["title"], "cree": cree or None}


def all_tools() -> list[Tool]:
    return [CarnetListerTool(), CarnetLireTool(), CarnetEcrireTool()]
