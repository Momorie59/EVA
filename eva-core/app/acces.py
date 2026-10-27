"""Cloisonnement des fichiers du workspace entre les personnes.

L'administrateur voit tout. Une autre personne ne voit que :
- les projets qu'elle peut ouvrir (projets/<slug>, voir project_acl : les siens, ceux partagés avec elle) ;
- ses propres fichiers déposés (uploads/) et livrés par EVA (exports/) ;
- ses propres images (generated/).
Tout le reste (papiers de la famille, sauvegardes, skills, fichiers des autres…) lui est refusé : au téléchargement
(/api/files/download) comme dans les outils fichiers d'EVA quand c'est elle qui parle.

Le propriétaire d'un fichier déposé ou livré est noté dans « .proprietaires.json » du dossier concerné ;
un fichier sans propriétaire (déposé avant cette règle) reste réservé à l'administrateur."""
import json
import threading
from pathlib import Path, PurePosixPath

from . import project_acl

FICHIER = ".proprietaires.json"
DOSSIERS_PERSONNELS = ("uploads", "exports")
SOUS_PHOTOS = "photos"
_verrou = threading.Lock()


def _carte(workspace: Path, dossier: str) -> Path:
    return Path(workspace) / dossier / FICHIER


def _lire(workspace: Path, dossier: str) -> dict:
    try:
        return json.loads(_carte(workspace, dossier).read_text())
    except (OSError, ValueError):
        return {}


def enregistrer(workspace: Path, rel: str, proprietaire: str | None) -> None:
    """Note le propriétaire d'un fichier de uploads/ ou exports/ (chemin relatif au workspace)."""
    if not proprietaire:
        return
    parts = PurePosixPath(rel).parts
    if len(parts) < 2 or parts[0] not in DOSSIERS_PERSONNELS:
        return
    dossier, nom = parts[0], parts[1]
    if parts[1] == SOUS_PHOTOS and len(parts) >= 3:
        dossier, nom = f"{parts[0]}/{SOUS_PHOTOS}", parts[2]
    with _verrou:
        carte = _lire(workspace, dossier)
        carte[nom] = proprietaire.lower()
        f = _carte(workspace, dossier)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(carte, ensure_ascii=False, indent=0))
        tmp.replace(f)


def oublier(workspace: Path, dossier: str, noms: list[str]) -> None:
    with _verrou:
        carte = _lire(workspace, dossier)
        for n in noms:
            carte.pop(n, None)
        f = _carte(workspace, dossier)
        if f.parent.is_dir():
            f.write_text(json.dumps(carte, ensure_ascii=False, indent=0))


def proprietaire(workspace: Path, dossier: str, nom: str) -> str | None:
    """Propriétaire d'une entrée de uploads/ ou exports/. Les fichiers dérivés d'un dépôt
    (« facture.pdf.txt », dossier « archive_extrait ») suivent le fichier d'origine."""
    carte = _lire(workspace, dossier)
    if nom in carte:
        return carte[nom]
    if nom.endswith(".txt") and nom[:-4] in carte:
        return carte[nom[:-4]]
    if nom.endswith("_extrait"):
        souche = nom[:-len("_extrait")]
        for n, p in carte.items():
            if PurePosixPath(n).stem == souche:
                return p
    return None


def fichiers_de(workspace: Path, dossier: str, personne: str) -> list[str]:
    return sorted(n for n, p in _lire(workspace, dossier).items() if p == personne.lower())


def source_visible(workspace: Path, source: str, personne: str) -> bool:
    """Un passage indexé (doc_chunks.source, chemin relatif au workspace) appartient-il à cette personne ?
    Seuls ses fichiers déposés, ses photos et ses fichiers livrés comptent ; « facture.pdf.txt » suit « facture.pdf »."""
    parts = PurePosixPath(source).parts
    if len(parts) < 2 or parts[0] not in DOSSIERS_PERSONNELS or not personne:
        return False
    if parts[1] == SOUS_PHOTOS:
        return len(parts) == 3 and proprietaire(workspace, f"{parts[0]}/{SOUS_PHOTOS}", parts[2]) == personne.lower()
    return proprietaire(workspace, parts[0], parts[1]) == personne.lower()


def normaliser(workspace: Path, rel: str) -> str | None:
    """Chemin relatif propre (sans « .. »), ou None s'il sort du workspace."""
    base = Path(workspace).resolve()
    p = (base / (rel or ".")).resolve()
    if p != base and base not in p.parents:
        return None
    return "" if p == base else p.relative_to(base).as_posix()


async def autorise(workspace: Path, rel: str, personne: str, role: str, ecriture: bool = False) -> bool:
    """Cette personne peut-elle lire (ou modifier) ce chemin du workspace ?"""
    if role == "admin" or not personne:
        return True
    propre = normaliser(workspace, rel)
    if propre is None or propre == "":
        return False                                   # la racine du workspace : réservée à l'administrateur
    parts = PurePosixPath(propre).parts
    haut = parts[0]
    if haut == "projets":
        if len(parts) == 1:
            return not ecriture                        # lister les projets : la liste est filtrée ensuite
        return project_acl.can_open((await project_acl.load()).get(parts[1]), personne, role)
    if haut in DOSSIERS_PERSONNELS:
        if len(parts) == 1 or (parts[1] == SOUS_PHOTOS and len(parts) == 2):
            return not ecriture
        if parts[1] == SOUS_PHOTOS:                      # photos envoyées dans la conversation (uploads/photos/…)
            return proprietaire(workspace, f"{haut}/{SOUS_PHOTOS}", parts[2]) == personne.lower()
        return proprietaire(workspace, haut, parts[1]) == personne.lower()
    if haut == "generated":
        if len(parts) != 2:
            return False
        meta = Path(workspace) / "generated" / (PurePosixPath(parts[1]).stem + ".json")
        try:
            return json.loads(meta.read_text()).get("owner", "") == personne
        except (OSError, ValueError):
            return False
    return False


async def filtrer_liste(workspace: Path, rel: str, entrees: list[dict], personne: str, role: str) -> list[dict]:
    """Retire d'un listage de dossier ce que la personne ne peut pas ouvrir."""
    if role == "admin" or not personne:
        return entrees
    propre = normaliser(workspace, rel) or ""
    out = []
    for e in entrees:
        enfant = f"{propre}/{e.get('name')}" if propre else str(e.get("name"))
        if await autorise(workspace, enfant, personne, role):
            out.append(e)
    return out
