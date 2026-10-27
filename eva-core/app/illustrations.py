"""Illustrer une recette, une page de wiki… : trouver ou créer l'image, puis la ranger comme photo du module.

Une demande comme « ajoute la recette de la paella avec une photo » ne doit pas finir en « je ne peux pas ajouter de
photo » : EVA sait dessiner (serveur d'images). La source peut être :
  - « generer » (ou vide avec un sujet) : EVA crée une photo du sujet avec le serveur d'images ;
  - « derniere » : la dernière image de la galerie (celle qu'EVA vient de créer ou de retoucher) ;
  - « img-….png » : une image précise de la galerie ;
  - un chemin du workspace (photo envoyée dans la conversation, ex. uploads/paella.jpg), dans les droits de la personne."""
from pathlib import Path

from . import acces, images, medias, profiles

_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_STYLE = {
    "recettes": "photo culinaire appétissante de {s}, plat servi joliment dressé, vue légèrement de dessus, lumière naturelle douce, haute qualité",
    "wiki": "illustration claire et soignée sur le thème : {s}",
}


class IllustrationError(RuntimeError):
    pass


def demande_generer(source: str) -> bool:
    s = (source or "").strip().lower()
    return s in ("", "generer", "générer", "genere", "génère", "auto", "oui", "true", "dessiner", "creer", "créer")


async def obtenir(source: str, sujet: str, module: str, workspace: Path) -> tuple[bytes, str, str]:
    """(octets, extension, d'où vient l'image). Lève IllustrationError avec une phrase claire si c'est impossible."""
    s = (source or "").strip()
    ws = Path(workspace)
    if demande_generer(s):
        cfg = await images.get_config()
        if not cfg["url"]:
            raise IllustrationError("Le serveur d'images n'est pas réglé (Paramètres › Images) : je ne peux pas dessiner la photo. "
                                    "Envoie-moi une photo dans la conversation et je l'ajoute.")
        prompt = _STYLE.get(module, "{s}").format(s=sujet.strip()[:300])
        final = await images.enhance(prompt) if cfg.get("enhance") else prompt
        try:
            png = await images.generate(final, cfg)
        except images.ImageError as exc:
            raise IllustrationError(f"Le serveur d'images n'a pas pu créer la photo : {exc}") from exc
        images.save(png, ws, prompt, final)                  # garde aussi une copie dans la galerie
        return png, ".png", "dessinée par EVA"
    if s.lower() in ("derniere", "dernière", "last", "cette image", "celle-ci"):
        dern = images.latest(ws, max_age=24 * 3600)
        if not dern:
            raise IllustrationError("Je ne trouve pas d'image récente dans la galerie.")
        return dern[1], ".png", f"galerie ({dern[0]})"
    if s.startswith("img-") and s.endswith(".png") and "/" not in s:
        p = ws / "generated" / s
        if not p.is_file():
            raise IllustrationError(f"Image « {s} » introuvable dans la galerie.")
        return p.read_bytes(), ".png", f"galerie ({s})"
    propre = acces.normaliser(ws, s)
    if propre is None or Path(propre).suffix.lower() not in _EXT:
        raise IllustrationError("Donne une image : « generer », « derniere », une image de la galerie (img-….png) ou une photo envoyée.")
    if not await acces.autorise(ws, propre, profiles.user_var.get() or "", profiles.role_var.get() or "admin"):
        raise IllustrationError("Cette photo n'est pas à toi.")
    p = ws / propre
    if not p.is_file():
        raise IllustrationError(f"Photo « {s} » introuvable.")
    ext = p.suffix.lower()
    return p.read_bytes(), ".jpg" if ext == ".jpeg" else ext, f"photo envoyée ({propre})"


def ranger(module: str, donnees: bytes, ext: str) -> str:
    """Enregistre l'image comme média du module (recettes, wiki) ; renvoie son nom de fichier."""
    nom, chemin, max_octets = medias.nouveau(module, f"image{ext}")
    if len(donnees) > max_octets:
        raise IllustrationError("Image trop grande.")
    chemin.write_bytes(donnees)
    return nom
