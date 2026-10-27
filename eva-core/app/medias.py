"""Photos et vidéos du wiki et du livre de recettes, rangées sur le NAS (workspace/<module>/medias).

Chaque fichier reçoit un nom aléatoire de 128 bits : son adresse sert de clé (comme un lien de partage). C'est ce qui permet
d'afficher les photos dans une page, dans une recette partagée avec un ami ou dans le PDF, sans mot de passe dans l'adresse.
Un fichier n'est jamais listé : on ne le voit que si on a la page qui le cite."""
import re
import uuid
from pathlib import Path

DOSSIERS = {"wiki": "wiki/medias", "recettes": "recettes/medias", "captures": "navigateur/captures"}
IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEOS = {".mp4", ".webm", ".mov", ".m4v"}
AUTRES = {".pdf"}
MAX_IMAGE_MO = 25
MAX_VIDEO_MO = 800
_NOM = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{2,5}$")


class MediaError(Exception):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


def nouveau(module: str, nom: str) -> tuple[str, Path, int]:
    """(nom de fichier, chemin, taille max en octets) pour un envoi ; refuse les formats inconnus."""
    if module not in DOSSIERS:
        raise MediaError("Module inconnu.")
    ext = Path(nom or "").suffix.lower()
    if ext == ".jpe":
        ext = ".jpg"
    if ext not in IMAGES | VIDEOS | AUTRES:
        raise MediaError("Format non pris en charge : images (jpg, png, webp, gif), vidéos (mp4, webm, mov) ou PDF.")
    d = Path(_racine) / DOSSIERS[module]
    d.mkdir(parents=True, exist_ok=True)
    fichier = f"{uuid.uuid4().hex}{ext}"
    max_mo = MAX_VIDEO_MO if ext in VIDEOS else MAX_IMAGE_MO
    return fichier, d / fichier, max_mo * 1024 * 1024


def chemin(fichier: str) -> tuple[str, Path]:
    """(module, chemin) d'un média existant, ou MediaError 404."""
    if not _NOM.match(fichier or ""):
        raise MediaError("Fichier introuvable.", 404)
    for module, dossier in DOSSIERS.items():
        p = Path(_racine) / dossier / fichier
        if p.is_file():
            return module, p
    raise MediaError("Fichier introuvable.", 404)


def genre(fichier: str) -> str:
    ext = Path(fichier).suffix.lower()
    return "image" if ext in IMAGES else "video" if ext in VIDEOS else "fichier"


def supprimer(fichiers) -> None:
    for f in fichiers or []:
        try:
            chemin(f)[1].unlink(missing_ok=True)
        except MediaError:
            pass


_racine = "."


def initialiser(workspace: Path) -> None:
    global _racine
    _racine = str(workspace)
