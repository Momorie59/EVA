"""Réglages des papiers, modifiables dans EVA (page Papiers › Réglages) et conservés dans papiers.db.

Les valeurs par défaut viennent du .env d'EVA (EVA_PAPERLESS_URL, EVA_PAPERLESS_TOKEN…) : un réglage enregistré
dans l'interface l'emporte. Le jeton Paperless n'est jamais renvoyé par l'API (seulement « défini / non défini »)."""
import json
import os
from dataclasses import asdict, dataclass, field

from ..config import settings as eva

APRES_IMPORT = ("deplacer", "supprimer", "laisser")
SOUS_DOSSIER_IMPORTES = "_importés"


def _env(nom: str, defaut: str = "") -> str:
    return (os.getenv(nom) or defaut).strip()


@dataclass
class Reglages:
    paperless_url: str = field(default_factory=lambda: _env("EVA_PAPERLESS_URL").rstrip("/"))
    paperless_public_url: str = field(default_factory=lambda: _env("EVA_PAPERLESS_PUBLIC_URL").rstrip("/"))
    paperless_token: str = field(default_factory=lambda: _env("EVA_PAPERLESS_TOKEN"))
    ollama_model: str = field(default_factory=lambda: _env("EVA_PAPIERS_MODELE") or eva.ollama_model)
    ollama_num_ctx: int = 8192
    confidence_threshold: float = 0.7
    alert_days: list = field(default_factory=lambda: [30, 7, 1, 0])
    dossiers: list = field(default_factory=lambda: [d for d in _env("EVA_PAPIERS_DOSSIERS").split(",") if d.strip()])
    apres_import: str = "deplacer"
    analyses_par_passage: int = 3
    # Non modifiables depuis l'interface
    max_chars: int = 12000
    max_retries: int = 3

    @property
    def timezone(self) -> str:
        return eva.timezone

    @property
    def ollama_url(self) -> str:
        return eva.ollama_host.rstrip("/")

    @property
    def lien_public(self) -> str:
        return self.paperless_public_url or self.paperless_url

    def actif(self) -> bool:
        return bool(self.paperless_url and self.paperless_token)

    def publics(self) -> dict:
        d = asdict(self)
        d["paperless_token"] = bool(self.paperless_token)      # jamais le jeton lui-même
        d.pop("max_chars")
        d.pop("max_retries")
        d["racine"] = racine()
        d["racine_nas"] = _env("EVA_PAPIERS_RACINE_NAS")          # le même dossier, vu depuis le NAS (pour l'affichage)
        return d


MODIFIABLES = {"paperless_url", "paperless_public_url", "paperless_token", "ollama_model", "ollama_num_ctx",
               "confidence_threshold", "alert_days", "dossiers", "apres_import", "analyses_par_passage"}


def racine() -> str:
    """Dossier du NAS visible par EVA (monté dans le conteneur) : les dossiers surveillés sont choisis dedans."""
    return _env("EVA_PAPIERS_RACINE", "/papiers").rstrip("/") or "/"


def charger(brut: str | None) -> Reglages:
    r = Reglages()
    if brut:
        try:
            for k, v in json.loads(brut).items():
                if k in MODIFIABLES:
                    setattr(r, k, v)
        except (ValueError, TypeError):
            pass
    return r


def valider(r: Reglages, champs: dict) -> tuple[Reglages, dict]:
    """Applique les champs modifiés, contrôlés un par un. Renvoie (réglages, champs enregistrés)."""
    out: dict = {}
    for k, v in champs.items():
        if k not in MODIFIABLES:
            continue
        if k in ("paperless_url", "paperless_public_url"):
            v = str(v or "").strip().rstrip("/")
            if v and not v.startswith(("http://", "https://")):
                raise ValueError(f"{k} : l'adresse doit commencer par http:// ou https://")
        elif k == "paperless_token":
            v = str(v or "").strip()
            if not v:
                continue                                    # champ laissé vide = on garde le jeton actuel
        elif k == "ollama_model":
            v = str(v or "").strip()
            if not v:
                raise ValueError("Choisis un modèle.")
        elif k == "ollama_num_ctx":
            v = int(v)
            if not 2048 <= v <= 32768:
                raise ValueError("Contexte entre 2048 et 32768.")
        elif k == "confidence_threshold":
            v = float(v)
            if not 0 <= v <= 1:
                raise ValueError("Seuil de confiance entre 0 et 1.")
        elif k == "alert_days":
            v = sorted({int(x) for x in (v if isinstance(v, list) else str(v).split(",")) if str(x).strip() != ""}, reverse=True)
            if not v or any(x < 0 or x > 365 for x in v):
                raise ValueError("Seuils d'alerte entre 0 et 365 jours.")
        elif k == "dossiers":
            v = [str(x).strip().strip("/") for x in (v or []) if str(x).strip().strip("/")]
            if any(".." in x.split("/") for x in v):
                raise ValueError("Chemin de dossier invalide.")
        elif k == "apres_import":
            if v not in APRES_IMPORT:
                raise ValueError("Après import : deplacer, supprimer ou laisser.")
        elif k == "analyses_par_passage":
            v = int(v)
            if not 1 <= v <= 20:
                raise ValueError("Analyses par passage entre 1 et 20.")
        setattr(r, k, v)
        out[k] = v
    return r, out


def serialiser(r: Reglages) -> str:
    d = asdict(r)
    return json.dumps({k: d[k] for k in MODIFIABLES}, ensure_ascii=False)
