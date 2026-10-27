"""Navigateur d'EVA (Chromium sans écran) : ouvrir, lire, capturer librement ; cliquer et remplir avec l'accord de la personne."""
from typing import Any

from ... import navigateur as nav
from ..permissions import Permission
from .base import Tool

_AIDE = " Chaque élément cliquable ou remplissable a un numéro « ref » : sers-t'en pour navigateur_cliquer et navigateur_remplir."


async def _sur(coro) -> dict:
    try:
        return await coro
    except nav.NavigateurError as exc:
        return {"error": str(exc)}


class NavigateurOuvrirTool(Tool):
    name = "navigateur_ouvrir"
    description = ("Ouvre une page dans le navigateur d'EVA (vrai navigateur, pages dynamiques comprises) et renvoie son texte "
                   "et ses éléments (liens, boutons, champs). Pour une simple lecture d'article, web_fetch suffit." + _AIDE)
    parameters = {"type": "object", "properties": {"url": {"type": "string", "description": "Adresse du site (https://…)"}}, "required": ["url"]}
    permission = Permission.AUTO

    async def execute(self, url: str = "", **_: Any) -> dict:
        return await _sur(nav.ouvrir(str(url or "")))


class NavigateurLireTool(Tool):
    name = "navigateur_lire"
    description = "Relit la page actuellement ouverte dans le navigateur d'EVA (texte et éléments numérotés)." + _AIDE
    parameters = {"type": "object", "properties": {}}
    permission = Permission.AUTO

    async def execute(self, **_: Any) -> dict:
        return await _sur(nav.lire())


class NavigateurCaptureTool(Tool):
    name = "navigateur_capture"
    description = "Fait une capture d'écran de la page ouverte dans le navigateur d'EVA, à montrer à la personne."
    parameters = {"type": "object", "properties": {"page_entiere": {"type": "boolean", "description": "Toute la page (défilement compris) au lieu de l'écran visible"}}}
    permission = Permission.AUTO

    async def execute(self, page_entiere: bool = False, **_: Any) -> dict:
        return await _sur(nav.capture(bool(page_entiere)))


class NavigateurCliquerTool(Tool):
    name = "navigateur_cliquer"
    description = "Clique sur un élément de la page ouverte (lien, bouton, case) par son numéro ref. Renvoie la page obtenue."
    parameters = {"type": "object", "properties": {"ref": {"type": "integer", "description": "Numéro de l'élément (lecture de page)"}}, "required": ["ref"]}
    permission = Permission.CONFIRM

    async def execute(self, ref: int = 0, **_: Any) -> dict:
        return await _sur(nav.cliquer(ref))


class NavigateurRemplirTool(Tool):
    name = "navigateur_remplir"
    description = ("Remplit un champ de la page ouverte (texte, liste déroulante, case à cocher) par son numéro ref ; valider=true envoie le formulaire. "
                   "Jamais de mot de passe, de code ni de carte bancaire : c'est refusé.")
    parameters = {"type": "object", "properties": {
        "ref": {"type": "integer", "description": "Numéro du champ"},
        "texte": {"type": "string", "description": "Valeur à saisir (ou option à choisir)"},
        "valider": {"type": "boolean", "description": "Envoyer le formulaire ensuite"}}, "required": ["ref", "texte"]}
    permission = Permission.CONFIRM

    async def execute(self, ref: int = 0, texte: str = "", valider: bool = False, **_: Any) -> dict:
        return await _sur(nav.remplir(ref, texte, bool(valider)))
