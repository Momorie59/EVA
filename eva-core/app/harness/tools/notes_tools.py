from typing import Any

from ... import notes
from ..permissions import Permission
from .base import Tool

_COLORS = ", ".join(notes.COLORS)


class NoteCreateTool(Tool):
    name = "note_create"
    description = ("Colle un post-it à l'écran de l'utilisateur (pense-bête visible sur l'interface). "
                   "À utiliser pour « note / mets un post-it / n'oublie pas » : texte court et clair.")
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Contenu du post-it (court)"},
            "color": {"type": "string", "description": f"Couleur : {_COLORS} (défaut jaune)"},
        },
        "required": ["text"],
    }
    permission = Permission.AUTO

    async def execute(self, text: str = "", color: str = "jaune", **_: Any) -> dict:
        try:
            n = await notes.create(text, color, by="eva")
        except ValueError as exc:
            return {"error": str(exc)}
        return {"created": n}


class NoteListTool(Tool):
    name = "note_list"
    description = "Liste les post-it actuellement affichés à l'écran (id, texte, couleur, fait ou non)."
    parameters = {"type": "object", "properties": {}}
    permission = Permission.AUTO

    async def execute(self, **_: Any) -> dict:
        return {"notes": [{"id": n["id"], "text": n["text"], "color": n["color"], "done": n["done"]} for n in await notes.list_notes(False)]}


class NoteUpdateTool(Tool):
    name = "note_update"
    description = "Modifie un post-it (texte, couleur) ou le marque comme fait. Utilise note_list pour connaître l'id."
    parameters = {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "text": {"type": "string"},
            "color": {"type": "string", "description": _COLORS},
            "done": {"type": "boolean"},
        },
        "required": ["id"],
    }
    permission = Permission.AUTO

    async def execute(self, id: int = 0, text: str | None = None, color: str | None = None, done: bool | None = None, **_: Any) -> dict:
        try:
            n = await notes.update(int(id), text=text, color=color, done=done)
        except (ValueError, TypeError) as exc:
            return {"error": str(exc)}
        return {"updated": n} if n else {"error": f"Post-it {id} introuvable."}


class NoteDeleteTool(Tool):
    name = "note_delete"
    description = "Retire un post-it de l'écran. Utilise note_list pour connaître l'id."
    parameters = {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}
    permission = Permission.AUTO

    async def execute(self, id: int = 0, **_: Any) -> dict:
        try:
            ok = await notes.delete(int(id))
        except (ValueError, TypeError) as exc:
            return {"error": str(exc)}
        return {"deleted": id} if ok else {"error": f"Post-it {id} introuvable."}
