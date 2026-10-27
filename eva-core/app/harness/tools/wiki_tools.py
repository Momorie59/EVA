"""Outils « wiki » : EVA cherche et lit le wiki (pages famille + pages perso de la personne qui parle) pour répondre,
et n'écrit une page que si la personne le demande (création ou mise à jour, historique gardé)."""
from typing import Any

from ... import modules, profiles, wiki
from ..permissions import Permission
from .base import Tool


def _qui() -> tuple[str, str]:
    return profiles.user_var.get() or "", profiles.role_var.get() or "admin"


def _coupe() -> dict | None:
    return None if modules.actif("wiki") else {"error": "Le wiki n'est pas activé (Paramètres › Modules)."}


class WikiChercherTool(Tool):
    name = "wiki_chercher"
    description = ("Cherche dans le wiki de la famille et les pages personnelles de la personne (modes d'emploi, procédures, "
                   "contacts, codes, infos de la maison…). À utiliser quand la question porte sur quelque chose que la famille a noté.")
    parameters = {"type": "object", "properties": {"q": {"type": "string", "description": "Mots à chercher"}}, "required": ["q"]}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, q: str = "", **_: Any) -> dict:
        if (c := _coupe()):
            return c
        pages = await wiki.chercher(_qui()[0], q)
        if not pages:
            return {"pages": [], "info": "Rien dans le wiki sur ce sujet."}
        return {"pages": [{"id": p["id"], "titre": p["titre"], "espace": p["espace"], "contenu": p["contenu"][:2500]} for p in pages]}


class WikiLireTool(Tool):
    name = "wiki_lire"
    description = "Lit une page du wiki par son titre (ou son id donné par wiki_chercher)."
    parameters = {"type": "object", "properties": {"titre": {"type": "string"}, "id": {"type": "integer"}}, "required": []}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, titre: str = "", id: Any = None, **_: Any) -> dict:   # noqa: A002
        if (c := _coupe()):
            return c
        qui = _qui()[0]
        try:
            p = await wiki.lire(qui, int(id)) if id not in (None, "") else await wiki.par_titre(qui, titre)
        except (wiki.WikiError, ValueError, TypeError):
            p = None
        if not p:
            return {"error": f"Pas de page « {titre or id} » dans le wiki."}
        return {"id": p["id"], "titre": p["titre"], "espace": p["espace"], "contenu": p["contenu"][:12000], "modifie_par": p["updated_by"]}


class WikiEcrireTool(Tool):
    name = "wiki_ecrire"
    description = ("Crée ou met à jour une page du wiki (Markdown). espace « famille » (partagée) ou « perso » (privée). "
                   "Si la page existe déjà, son contenu est remplacé (l'ancienne version reste dans l'historique) : pour compléter, "
                   "lis-la d'abord et renvoie le texte complet.")
    parameters = {"type": "object", "properties": {
        "titre": {"type": "string"}, "contenu": {"type": "string", "description": "Texte complet de la page, en Markdown"},
        "espace": {"type": "string", "enum": ["famille", "perso"]},
        "image": {"type": "string", "description": "Illustration en haut de la page : « generer » (EVA la dessine), « derniere » (dernière image "
                                                   "de la galerie), img-….png, ou chemin d'une photo envoyée. Vide = aucune."}}, "required": ["titre", "contenu"]}
    permission = Permission.CONFIRM

    async def execute(self, titre: str = "", contenu: str = "", espace: str = "famille", image: str = "", **_: Any) -> dict:
        if (c := _coupe()):
            return c
        qui, role = _qui()
        note_image = ""
        if image and image.strip().lower() not in ("non", "aucune", "sans"):
            from pathlib import Path
            from ... import illustrations, medias
            try:
                donnees, ext, origine = await illustrations.obtenir(image, titre, "wiki", Path(medias._racine))
                nom = illustrations.ranger("wiki", donnees, ext)
                contenu = f"![{titre}](/api/public/medias/{nom})\n\n{contenu}"
                note_image = f"Illustration ajoutée ({origine})."
            except (illustrations.IllustrationError, medias.MediaError) as e:
                note_image = f"Page enregistrée sans illustration : {e}"
        try:
            existante = await wiki.par_titre(qui, titre)
            if existante and existante["espace"] == (espace or "famille"):
                p = await wiki.modifier(qui, existante["id"], contenu=contenu, role=role)
                return {"modifiee": {"id": p["id"], "titre": p["titre"]}, **({"image": note_image} if note_image else {})}
            p = await wiki.creer(qui, espace or "famille", titre, contenu, role=role)
            return {"creee": {"id": p["id"], "titre": p["titre"], "espace": p["espace"]}, **({"image": note_image} if note_image else {})}
        except wiki.WikiError as e:
            return {"error": str(e)}


def all_tools() -> list[Tool]:
    return [WikiChercherTool(), WikiLireTool(), WikiEcrireTool()]
