from pathlib import Path
from typing import Any

from ... import lists, printing
from ..permissions import Permission
from .base import Tool
from .filesystem import WorkspaceError, _resolve_in_workspace

_P = {"type": "string", "description": "Nom de l'imprimante (défaut : l'imprimante par défaut)"}


class PrinterListTool(Tool):
    name = "printer_list"
    description = "Liste les imprimantes enregistrées (nom, par défaut ou non)."
    parameters = {"type": "object", "properties": {}, "required": []}
    permission = Permission.AUTO

    async def execute(self, **_: Any) -> dict:
        return {"printers": [{"name": p["name"], "default": p["is_default"]} for p in await printing.list_printers()]}


class PrintTextTool(Tool):
    name = "print_text"
    description = "Imprime un texte (note, recette, résumé…) sur l'imprimante. Toujours soumis à l'accord de l'utilisateur."
    parameters = {"type": "object", "properties": {"text": {"type": "string"}, "title": {"type": "string"}, "printer": _P,
                                                  "copies": {"type": "integer"}, "duplex": {"type": "boolean", "description": "Recto-verso"}}, "required": ["text"]}
    permission = Permission.CONFIRM

    async def execute(self, text: str = "", title: str = "", printer: str = "", copies: int = 1, duplex: bool = False, **_: Any) -> dict:
        try:
            return await printing.print_text(text, title, printer, copies, duplex)
        except printing.PrintError as exc:
            return {"error": str(exc)}


class PrintFileTool(Tool):
    name = "print_file"
    description = "Imprime un fichier du workspace (PDF, image, fichier texte). Toujours soumis à l'accord de l'utilisateur."
    parameters = {"type": "object", "properties": {"path": {"type": "string", "description": "Chemin dans le workspace"}, "printer": _P,
                                                  "copies": {"type": "integer"}, "duplex": {"type": "boolean"}}, "required": ["path"]}
    permission = Permission.CONFIRM

    def __init__(self, workspace_root: Path):
        self.root = workspace_root

    async def execute(self, path: str = "", printer: str = "", copies: int = 1, duplex: bool = False, **_: Any) -> dict:
        try:
            p = _resolve_in_workspace(self.root, path)
            if not p.is_file():
                return {"error": f"Fichier introuvable : {path}"}
            return await printing.print_path(p, printer, copies, duplex)
        except (WorkspaceError, printing.PrintError) as exc:
            return {"error": str(exc)}


class PrintListTool(Tool):
    name = "print_list"
    description = "Imprime une liste (courses, à faire…) avec ses cases à cocher. Sans nom : la liste de courses. Toujours soumis à l'accord de l'utilisateur."
    parameters = {"type": "object", "properties": {"list": {"type": "string"}, "printer": _P, "include_done": {"type": "boolean"}}, "required": []}
    permission = Permission.CONFIRM

    async def execute(self, list: str = "", printer: str = "", include_done: bool = False, **_: Any) -> dict:  # noqa: A002
        try:
            l = await lists.find(list)
            if not l:
                return {"error": f"Liste « {list} » introuvable."}
            title, body = await lists.as_text(l["id"], include_done)
            return await printing.print_text(body, title, printer)
        except printing.PrintError as exc:
            return {"error": str(exc)}
