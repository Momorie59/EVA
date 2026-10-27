"""Vrais fichiers : créer un Word, un PDF, un PowerPoint ou un Excel ; modifier un Word ou un Excel déposé (copie)."""
import asyncio
from pathlib import Path
from typing import Any

from ... import documents as docs
from ..permissions import Permission
from .base import Tool
from .filesystem import WorkspaceError, _resolve_in_workspace


def _livraison(ws: Path, chemin: Path) -> dict:
    v = docs.verifier(chemin)
    if not v.get("ok"):
        chemin.unlink(missing_ok=True)
        return {"error": v.get("erreur") or "Le fichier produit est illisible : je recommence autrement."}
    rel = chemin.relative_to(ws).as_posix()
    return {"path": rel, "nom": chemin.name, "size_bytes": chemin.stat().st_size, "download": f"/api/files/download?path={rel}",
            "verification": v, "consigne": "Le fichier est prêt et vérifié : dis-le en une phrase (le bouton de téléchargement s'affiche tout seul)."}


class DocumentCreerTool(Tool):
    name = "document_creer"
    description = (
        "Crée un VRAI fichier à télécharger : Word (docx), PDF (pdf), PowerPoint (pptx) ou Excel (xlsx). "
        "contenu = Markdown : # titre, ## parties (= une diapositive en PowerPoint), listes - ou 1., tableaux | a | b |, **gras**, "
        "--- = saut de page. Pour Excel : feuilles = [{nom, lignes: [[en-têtes…], [valeurs…]]}] (formules =SOMME… acceptées en anglais, ex. =SUM(B2:B9)), "
        "ou des tableaux Markdown. Écris le contenu complet et soigné, jamais de « à compléter »."
    )
    parameters = {"type": "object", "properties": {
        "format": {"type": "string", "enum": ["docx", "pdf", "pptx", "xlsx"]},
        "nom": {"type": "string", "description": "Nom du fichier sans extension (ex. Budget vacances)"},
        "titre": {"type": "string", "description": "Titre affiché dans le document"},
        "contenu": {"type": "string", "description": "Contenu en Markdown"},
        "feuilles": {"type": "array", "items": {"type": "object"}, "description": "Excel seulement : [{nom, lignes}]"}},
        "required": ["format", "nom"]}
    permission = Permission.AUTO
    agent_safe = True

    def __init__(self, workspace_root: Path):
        self.ws = workspace_root

    async def execute(self, format: str = "", nom: str = "", titre: str = "", contenu: str = "", feuilles: list | None = None, **_: Any) -> dict:
        try:
            chemin = await asyncio.to_thread(docs.creer, self.ws / "exports", format, nom, titre, contenu, feuilles)
        except docs.DocumentError as exc:
            return {"error": str(exc)}
        return _livraison(self.ws, chemin)


class DocumentModifierTool(Tool):
    name = "document_modifier"
    description = (
        "Modifie un Word (.docx) ou un Excel (.xlsx) déposé ou existant : remplacer des textes, ajouter des parties (Markdown) à la fin, "
        "écrire des cellules ({cellule: 'B4', valeur}) ou ajouter des lignes. Crée une copie « (modifié) » à télécharger : l'original n'est jamais touché."
    )
    parameters = {"type": "object", "properties": {
        "path": {"type": "string", "description": "Chemin du fichier (ex. uploads/contrat.docx)"},
        "remplacements": {"type": "array", "items": {"type": "object", "properties": {"chercher": {"type": "string"}, "remplacer": {"type": "string"}}}},
        "ajout": {"type": "string", "description": "Word : Markdown ajouté à la fin"},
        "cellules": {"type": "array", "items": {"type": "object"}, "description": "Excel : [{cellule, valeur, feuille?}]"},
        "lignes": {"type": "array", "items": {"type": "array"}, "description": "Excel : lignes ajoutées en bas"},
        "feuille": {"type": "string", "description": "Excel : feuille visée"}},
        "required": ["path"]}
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.ws = workspace_root

    async def execute(self, path: str = "", remplacements: list | None = None, ajout: str = "", cellules: list | None = None,
                      lignes: list | None = None, feuille: str = "", **_: Any) -> dict:
        try:
            src = _resolve_in_workspace(self.ws, path)
        except WorkspaceError as exc:
            return {"error": str(exc)}
        if not src.is_file():
            return {"error": f"Fichier introuvable : {path}"}
        try:
            chemin = await asyncio.to_thread(docs.modifier, src, self.ws / "exports", remplacements, ajout, cellules, lignes, feuille)
        except docs.DocumentError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — fichier abîmé, protégé par mot de passe…
            return {"error": f"Impossible d'ouvrir ce fichier : {exc}"[:200]}
        return _livraison(self.ws, chemin)
