"""Plugins : des outils ajoutés à EVA sans toucher à son code (voir PLUGINS.md).

- Un plugin est un dossier `plugins/<nom>/plugin.py` à la racine d'EVA, monté en LECTURE SEULE dans eva-core
  (/eva-plugins). EVA ne peut donc jamais écrire ni modifier un plugin elle-même.
- Rien n'est chargé tant que l'administrateur n'a pas activé le plugin (Paramètres › Modules › Plugins).
- Le plugin déclare : NOM, DESCRIPTION, MOTS (mots qui font proposer ses outils au modèle), API (version de
  plugin_api visée) et une fonction `outils(contexte) -> list[Tool]`. Les noms d'outils commencent par `<nom>_`.
- Un plugin cassé est ignoré (erreur visible dans Paramètres), il n'empêche jamais EVA de démarrer."""
import importlib.util
import json
import logging
import os
import re
import sys
from pathlib import Path

from . import plugin_api
from .db import get_pool

logger = logging.getLogger("eva-core.plugins")
KV = "plugins_actifs"
_NOM = re.compile(r"^[a-z][a-z0-9_]{1,30}$")

_registre = None
_workspace: Path | None = None
_etat: dict[str, dict] = {}            # nom → {description, actif, outils, erreur}
MOTS: dict[str, re.Pattern] = {}       # nom d'outil → mots qui le font proposer (utilisé par harness/selection.py)


def dossier() -> Path:
    return Path(os.getenv("EVA_PLUGINS_DIR", "/eva-plugins"))


def lier(registre, workspace: Path) -> None:
    global _registre, _workspace
    _registre, _workspace = registre, Path(workspace)


async def actifs() -> dict[str, bool]:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    d = (json.loads(raw) if isinstance(raw, str) else raw) if raw else {}
    return {k: bool(v) for k, v in (d or {}).items()}


async def regler(changements: dict) -> list[dict]:
    d = {**await actifs(), **{k: bool(v) for k, v in (changements or {}).items() if isinstance(k, str) and _NOM.match(k)}}
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(d))
    return await charger()


def _importer(nom: str, fichier: Path):
    spec = importlib.util.spec_from_file_location(f"eva_plugin_{nom}", fichier)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def charger() -> list[dict]:
    """(Re)lit le dossier des plugins et branche les outils des plugins activés."""
    global MOTS
    _etat.clear()
    outils, mots = [], {}
    on = await actifs()
    base = dossier()
    dossiers = sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    for d in dossiers:
        nom = d.name.replace("-", "_").lower()
        if not _NOM.match(nom) or not (d / "plugin.py").is_file():
            continue
        e = _etat[nom] = {"nom": nom, "dossier": d.name, "description": "", "actif": on.get(nom, False), "outils": [], "erreur": ""}
        try:
            m = _importer(nom, d / "plugin.py")
            e["description"] = str(getattr(m, "DESCRIPTION", ""))[:300]
            if int(getattr(m, "API", 1)) > plugin_api.API_VERSION:
                raise ValueError(f"demande l'API {getattr(m, 'API')} : mets EVA à jour")
            if not e["actif"]:
                continue
            liste = list(m.outils({"workspace": _workspace, "dossier": d}) or [])
            motif = [str(x) for x in getattr(m, "MOTS", []) if str(x).strip()]
            existants = set(_registre.all_names()) if _registre else set()
            for t in liste:
                if not isinstance(t, plugin_api.Tool):
                    raise TypeError("outils() doit renvoyer des objets Tool (from app.plugin_api import Tool)")
                if not t.name.startswith(nom + "_") or t.name in existants:
                    raise ValueError(f"l'outil « {t.name} » doit commencer par « {nom}_ » et ne pas exister déjà")
                outils.append(t)
                e["outils"].append(t.name)
                mots[t.name] = re.compile("|".join(map(re.escape, motif + [nom.replace("_", " ")])), re.I)
        except Exception as exc:  # noqa: BLE001 — un plugin cassé ne casse pas EVA
            logger.warning("Plugin %s ignoré : %s", nom, exc)
            e["erreur"] = f"{type(exc).__name__} : {exc}"[:300]
            outils = [t for t in outils if not t.name.startswith(nom + "_")]
            e["outils"] = []
    MOTS = mots
    if _registre is not None:
        _registre.set_plugins(outils)
    return liste_etat()


def liste_etat() -> list[dict]:
    return list(_etat.values())
