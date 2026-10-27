from typing import Any

from ... import lists
from ..permissions import Permission
from .base import Tool

_LIST = {"type": "string", "description": "Nom de la liste : « courses » (défaut), « à faire », ou une liste créée par l'utilisateur"}


async def _need(name: str, create: bool = False, prive: bool = False) -> dict:
    l = await lists.find(name, create, prive)
    if not l:
        names = ", ".join(x["name"] for x in await lists.all_lists())
        conseil = " Pour le livre de recettes, utilise recette_chercher (q vide = toutes les recettes)." if "recette" in (name or "").lower() else ""
        raise ValueError(f"Liste « {name} » introuvable. Listes : {names}.{conseil}")
    return l


class ListShowTool(Tool):
    name = "list_show"
    description = "Montre le contenu d'une liste (courses, à faire…). Sans nom : la liste de courses. Sans « list » et avec all=true : toutes les listes."
    parameters = {"type": "object", "properties": {"list": _LIST, "all": {"type": "boolean", "description": "Résumé de toutes les listes"}}, "required": []}
    permission = Permission.AUTO

    async def execute(self, list: str = "", all: bool = False, **_: Any) -> dict:  # noqa: A002
        try:
            if all:
                return {"lists": [{"name": l["name"], "open": l["open"], "done": l["done"]} for l in await lists.all_lists()]}
            l = await _need(list)
            return {"list": l["name"], "items": [{"text": i["text"], "done": i["done"]} for i in await lists.items(l["id"])]}
        except ValueError as exc:
            return {"error": str(exc)}


class ListAddTool(Tool):
    name = "list_add"
    description = ("Ajoute un ou plusieurs éléments à une liste (« ajoute du lait et des œufs à la liste de courses »). "
                   "Un élément par entrée, avec sa quantité si donnée (« 2 litres de lait »). Crée la liste si elle n'existe pas ; "
                   "prive=true pour une NOUVELLE liste que seule la personne verra (« ma liste privée d'idées cadeaux »).")
    parameters = {"type": "object", "properties": {"list": _LIST, "items": {"type": "array", "items": {"type": "string"}, "description": "Éléments à ajouter"},
                                                  "prive": {"type": "boolean", "description": "Nouvelle liste privée (visible seulement par la personne)"}}, "required": ["items"]}
    permission = Permission.AUTO

    async def execute(self, items: Any = None, list: str = "", prive: bool = False, **_: Any) -> dict:  # noqa: A002
        if isinstance(items, str):
            items = [x.strip() for x in items.replace(" et ", ",").split(",")]
        try:
            l = await _need(list, create=True, prive=bool(prive))
            return {"list": l["name"], **({"privee": True} if l.get("prive") else {}), **await lists.add(l["id"], list_or_empty(items), by="eva")}
        except ValueError as exc:
            return {"error": str(exc)}


def list_or_empty(x: Any) -> list[str]:
    return [str(i) for i in x] if isinstance(x, (list, tuple)) else []


class ListCheckTool(Tool):
    name = "list_check"
    description = "Coche (acheté / fait) ou décoche un élément d'une liste. done=false pour décocher."
    parameters = {"type": "object", "properties": {"list": _LIST, "item": {"type": "string"}, "done": {"type": "boolean"}}, "required": ["item"]}
    permission = Permission.AUTO

    async def execute(self, item: str = "", list: str = "", done: bool = True, **_: Any) -> dict:  # noqa: A002
        try:
            l = await _need(list)
            r = await lists.set_done(l["id"], item, bool(done))
            return {"list": l["name"], **r} if r["updated"] else {"error": f"Rien ne correspond à « {item} » dans {l['name']}."}
        except ValueError as exc:
            return {"error": str(exc)}


class ListRemoveTool(Tool):
    name = "list_remove"
    description = "Retire un élément d'une liste. clear_done=true : retire tous les éléments déjà cochés (item inutile)."
    parameters = {"type": "object", "properties": {"list": _LIST, "item": {"type": "string"}, "clear_done": {"type": "boolean"}}, "required": []}
    permission = Permission.AUTO

    async def execute(self, item: str = "", list: str = "", clear_done: bool = False, **_: Any) -> dict:  # noqa: A002
        try:
            l = await _need(list)
            if clear_done:
                return {"list": l["name"], "removed_count": await lists.clear_done(l["id"])}
            r = await lists.remove(l["id"], item)
            return {"list": l["name"], **r} if r["removed"] else {"error": f"Rien ne correspond à « {item} » dans {l['name']}."}
        except ValueError as exc:
            return {"error": str(exc)}
