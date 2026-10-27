"""Dossiers surveillés : EVA envoie à Paperless chaque fichier déposé, un par un, puis le range (ou le supprime).

Fait pour le traitement en masse : on peut copier des centaines de fichiers d'un coup, EVA les envoie par lots
(MAX_ENVOIS par passage) pour ne pas noyer Paperless, et la page Papiers montre la progression."""
import logging
import time
from pathlib import Path

from .config import SOUS_DOSSIER_IMPORTES, Reglages
from .db import DB, now_iso

log = logging.getLogger("eva-core.papiers.depot")

FORMATS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".gif", ".txt", ".eml",
           ".doc", ".docx", ".odt", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp", ".rtf"}
STABLE_SECONDES = 20          # un fichier modifié il y a moins longtemps est peut-être encore en cours de copie
MAX_ENVOIS = 25               # par passage (toutes les minutes)
MAX_OCTETS = 60 * 1024 * 1024


def dossier_sur(racine: Path, relatif: str) -> Path | None:
    """Chemin réel d'un dossier surveillé, jamais en dehors de la racine montée."""
    base = racine.resolve()
    d = (base / relatif).resolve()
    return d if (d == base or base in d.parents) else None


def _ignorer(p: Path, d: Path) -> bool:
    rel = p.relative_to(d).parts
    return (SOUS_DOSSIER_IMPORTES in rel or any(x.startswith(".") for x in rel)
            or p.name.startswith(("~$", ".~")) or p.suffix.lower() in (".part", ".tmp", ".crdownload")
            or p.suffix.lower() not in FORMATS)


def candidats(racine: Path, reg: Reglages, maintenant: float | None = None) -> tuple[list[tuple[Path, Path]], list[str]]:
    """(fichiers prêts à envoyer [(fichier, dossier surveillé)], problèmes de dossiers)."""
    maintenant = maintenant or time.time()
    prets, problemes = [], []
    for rel in reg.dossiers:
        d = dossier_sur(racine, rel)
        if d is None:
            problemes.append(f"« {rel} » sort du dossier autorisé.")
            continue
        if not d.is_dir():
            problemes.append(f"« {rel} » n'existe pas (ou n'est pas visible par EVA).")
            continue
        for p in sorted(d.rglob("*")):
            try:
                if not p.is_file() or _ignorer(p, d):
                    continue
                if maintenant - p.stat().st_mtime < STABLE_SECONDES:
                    continue
            except OSError:
                continue
            prets.append((p, d))
    return prets, problemes


def _destination(p: Path, d: Path) -> Path:
    cible = d / SOUS_DOSSIER_IMPORTES / p.relative_to(d)
    if cible.exists():
        cible = cible.with_name(f"{cible.stem}-{int(time.time())}{cible.suffix}")
    return cible


def scanner(db: DB, paperless, racine: Path, reg: Reglages, maintenant: float | None = None) -> dict:
    """Un passage : envoie au plus MAX_ENVOIS fichiers à Paperless. Renvoie un bilan pour la page Papiers."""
    prets, problemes = candidats(racine, reg, maintenant)
    envoyes, erreurs, en_attente = 0, 0, 0
    for p, d in prets:
        cle = str(p)
        st = p.stat()
        deja = db.one("SELECT * FROM imports WHERE chemin=?", (cle,))
        if deja and deja["taille"] == st.st_size and deja["mtime"] == st.st_mtime:
            if deja["statut"] == "envoye" or (deja["statut"] == "erreur" and deja["tentatives"] >= reg.max_retries):
                continue                                   # déjà envoyé (mode « laisser ») ou abandonné
        if envoyes + erreurs >= MAX_ENVOIS:
            en_attente += 1
            continue
        tentatives = (deja["tentatives"] if deja else 0) + 1
        try:
            if st.st_size > MAX_OCTETS:
                raise ValueError("fichier trop gros (60 Mo maximum)")
            if st.st_size == 0:
                raise ValueError("fichier vide")
            tache = paperless.deposer(p.name, p.read_bytes())
        except Exception as e:  # noqa: BLE001 — un fichier en échec ne bloque pas les autres
            erreurs += 1
            log.warning("Import de %s impossible : %s", p, e)
            db.x("""INSERT INTO imports(chemin, taille, mtime, statut, erreur, tentatives, maj_le) VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(chemin) DO UPDATE SET taille=excluded.taille, mtime=excluded.mtime, statut='erreur',
                    erreur=excluded.erreur, tentatives=excluded.tentatives, maj_le=excluded.maj_le""",
                 (cle, st.st_size, st.st_mtime, "erreur", str(e)[:300], tentatives, now_iso()))
            continue
        devenu = ""
        try:
            if reg.apres_import == "deplacer":
                cible = _destination(p, d)
                cible.parent.mkdir(parents=True, exist_ok=True)
                p.rename(cible)
                devenu = str(cible)
            elif reg.apres_import == "supprimer":
                p.unlink()
        except OSError as e:
            log.warning("Fichier %s envoyé mais non rangé : %s", p, e)
        db.x("""INSERT INTO imports(chemin, taille, mtime, statut, erreur, tentatives, tache, devenu, maj_le)
                VALUES(?,?,?,'envoye',NULL,?,?,?,?) ON CONFLICT(chemin) DO UPDATE SET taille=excluded.taille,
                mtime=excluded.mtime, statut='envoye', erreur=NULL, tentatives=excluded.tentatives, tache=excluded.tache,
                devenu=excluded.devenu, maj_le=excluded.maj_le""",
             (cle, st.st_size, st.st_mtime, tentatives, str(tache)[:100], devenu, now_iso()))
        envoyes += 1
    if envoyes or erreurs:
        log.info("Dossiers surveillés : %d fichier(s) envoyé(s) à Paperless, %d en erreur, %d en attente", envoyes, erreurs, en_attente)
    return {"envoyes": envoyes, "erreurs": erreurs, "en_attente": en_attente, "problemes": problemes}


def parcourir(racine: Path, relatif: str = "") -> dict:
    """Sous-dossiers d'un dossier de la racine, pour choisir les dossiers surveillés dans l'interface."""
    d = dossier_sur(racine, relatif)
    if d is None or not d.is_dir():
        raise ValueError("Dossier introuvable.")
    base = racine.resolve()
    sous = []
    for x in sorted(d.iterdir(), key=lambda q: q.name.lower()):
        try:
            if x.is_dir() and not x.name.startswith(".") and x.name != SOUS_DOSSIER_IMPORTES:
                sous.append(x.name)
        except OSError:
            continue
    rel = "" if d == base else d.relative_to(base).as_posix()
    parent = None if not rel else ("" if Path(rel).parent == Path(".") else Path(rel).parent.as_posix())
    return {"racine": str(base), "chemin": rel, "parent": parent,
            "dossiers": sous[:500]}


def creer(racine: Path, relatif: str) -> str:
    d = dossier_sur(racine, relatif)
    if d is None:
        raise ValueError("Chemin invalide.")
    d.mkdir(parents=True, exist_ok=True)
    return d.relative_to(racine.resolve()).as_posix()
