"""Modèles d'images : catalogue conseillé selon la puissance du serveur IA, et pilotage du serveur d'images (liste, téléchargement,
suppression, mise à jour de son code) depuis EVA — rien à faire en ligne de commande sur le serveur IA."""
import base64
import os
from pathlib import Path

import httpx

from . import hf_catalog, images

# Dépôts au format « diffusers » (téléchargeables tels quels). `vram` = mémoire de carte conseillée en demi-précision.
CATALOG = [
    {"id": "stabilityai/sd-turbo", "title": "SD Turbo", "size_gb": 2.6, "vram": 3.0, "speed": "très rapide", "quality": "correcte",
     "about": "Le modèle par défaut : 1 à 4 étapes, quelques secondes même sur une petite carte. Images 512×512."},
    {"id": "Lykon/dreamshaper-8", "title": "DreamShaper 8", "size_gb": 2.1, "vram": 4.0, "speed": "moyen", "quality": "très bonne",
     "about": "Polyvalent (illustrations, portraits, fantasy) et très bien pour retoucher des images. Bon compromis sur 6 Go."},
    {"id": "dreamlike-art/dreamlike-photoreal-2.0", "title": "Dreamlike Photoreal 2.0", "size_gb": 2.1, "vram": 4.0, "speed": "moyen", "quality": "réaliste",
     "about": "Orienté photo réaliste (personnes, paysages, objets)."},
    {"id": "stable-diffusion-v1-5/stable-diffusion-v1-5", "title": "Stable Diffusion 1.5", "size_gb": 2.1, "vram": 4.0, "speed": "moyen", "quality": "bonne",
     "about": "La référence SD 1.5 : base de très nombreux modèles, polyvalent."},
    {"id": "stabilityai/sdxl-turbo", "title": "SDXL Turbo", "size_gb": 6.9, "vram": 8.0, "speed": "rapide", "quality": "très bonne",
     "about": "SDXL en 1 à 4 étapes : plus détaillé que SD Turbo. Demande une carte de 8 Go ou plus."},
    {"id": "stabilityai/stable-diffusion-xl-base-1.0", "title": "SDXL 1.0", "size_gb": 6.9, "vram": 10.0, "speed": "lent", "quality": "excellente",
     "about": "Très bonne qualité, 1024×1024. Pour une carte de 10 Go ou plus."},
]
BEST_FIRST = ["dreamlike-art/dreamlike-photoreal-2.0", "Lykon/dreamshaper-8"]
UPDATE_DIR = Path(os.getenv("EVA_IMAGEGEN_SRC", "/imagegen-src"))
UPDATABLE = ("__init__.py", "engine.py", "main.py", "models.py")


def verdict(entry: dict, hw: dict) -> dict:
    vram = float(hw.get("vram_gb", 0) or 0)
    need = entry["vram"]
    if vram >= need:
        return {"level": "ok", "label": "Convient à ta carte", "detail": f"{need:g} Go conseillés, tu as {vram:g} Go."}
    if vram >= need * 0.7:
        return {"level": "slow", "label": "Possible mais lent", "detail": f"{need:g} Go conseillés, tu as {vram:g} Go : risque de lenteur ou de manque de mémoire."}
    return {"level": "no", "label": "Trop gros pour ta carte", "detail": f"{need:g} Go conseillés, tu as {vram:g} Go."}


def recommended(hw: dict) -> str:
    """Le meilleur choix pour réaliser des images qui tient sur la carte."""
    ok = [e for e in CATALOG if e["vram"] <= float(hw.get("vram_gb", 0) or 0)]
    if not ok:
        return CATALOG[0]["id"]
    for rid in BEST_FIRST:
        if any(e["id"] == rid for e in ok):
            if max(e["vram"] for e in ok) >= 8:
                break
            return rid
    return max(ok, key=lambda e: (e["vram"], e["size_gb"]))["id"]


class ServerError(Exception):
    pass


async def _call(cfg: dict, method: str, path: str, json_body: dict | None = None, timeout: float = 20.0):
    if not cfg["url"]:
        raise ServerError(images.NOT_CONFIGURED)
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=images._headers(cfg)) as c:
            r = await c.request(method, cfg["url"] + path, json=json_body)
    except httpx.HTTPError as exc:
        raise ServerError(f"Serveur d'images injoignable ({type(exc).__name__}).") from exc
    if r.status_code in (404, 405):
        raise ServerError(images.NEEDS_UPDATE)
    if r.status_code != 200:
        raise ServerError(images._http_error(r))
    try:
        return r.json()
    except ValueError as exc:
        raise ServerError("Réponse inattendue du serveur d'images.") from exc


async def overview() -> dict:
    cfg = await images.get_config()
    hw = await hf_catalog.get_hardware()
    server = {"up": False, "configured": bool(cfg["url"]), "needs_update": False}
    inst: dict[str, dict] = {}
    extra: list[dict] = []
    try:
        data = await _call(cfg, "GET", "/eva/installed")
        server.update(up=True, version=data.get("version"), device=data.get("device"), gpu=data.get("gpu", {}), disk_free_gb=data.get("disk_free_gb"),
                      active=data.get("active"), default=data.get("default"))
        inst = {m["id"]: m for m in data.get("models", [])}
        pulls = {p["id"]: p for p in (await _call(cfg, "GET", "/eva/pulls")).get("pulls", [])}
    except ServerError as exc:
        pulls = {}
        server["error"] = str(exc)
        server["needs_update"] = str(exc) == images.NEEDS_UPDATE
        server["up"] = (await images.status(cfg)).get("up", False)
    gpu = server.get("gpu") or {}
    if gpu.get("vram_total_mb"):
        hw = {**hw, "vram_gb": round(float(gpu["vram_total_mb"]) / 1024, 1)}               # la vraie carte du serveur d'images prime sur le réglage manuel
    shown = set()
    items = []
    for e in CATALOG:
        shown.add(e["id"])
        items.append({**e, "verdict": verdict(e, hw), "installed": e["id"] in inst,
                      "pull": pulls.get(e["id"])})
    for mid, m in inst.items():
        if mid not in shown:
            items.append({"id": mid, "title": mid, "size_gb": m.get("size_gb", 0), "vram": 0, "speed": "", "quality": "", "about": "Modèle déjà présent sur le serveur.",
                          "verdict": {"level": "ok", "label": "Installé", "detail": ""}, "installed": True, "pull": pulls.get(mid), "custom": True})
    for pid, p in pulls.items():
        if pid not in shown and pid not in inst:
            items.append({"id": pid, "title": pid, "size_gb": round(p.get("total", 0) / 2**30, 2), "vram": 0, "speed": "", "quality": "", "about": "Téléchargement demandé.",
                          "verdict": {"level": "ok", "label": "", "detail": ""}, "installed": False, "pull": p, "custom": True})
    return {"server": server, "hardware": hw, "recommended": recommended(hw), "active": cfg["model"] or server.get("default") or "", "items": items}


async def pull(model_id: str) -> dict:
    return await _call(await images.get_config(), "POST", "/eva/pull", {"id": model_id}, 30)


async def delete(model_id: str) -> dict:
    cfg = await images.get_config()
    out = await _call(cfg, "POST", "/eva/delete", {"id": model_id}, 60)
    if cfg["model"] == model_id:                                    # le modèle supprimé n'est plus utilisable : retour au modèle par défaut
        await images.set_config(cfg["url"], cfg["kind"], "", cfg["steps"], cfg["size"], None, cfg["enhance"], None)
    return out


async def use(model_id: str) -> dict:
    cfg = await images.get_config()
    return await images.set_config(cfg["url"], cfg["kind"], model_id.strip(), cfg["steps"], cfg["size"], None, cfg["enhance"], None)


def bundle() -> tuple[dict[str, str], int | None]:
    """Code du serveur d'images livré avec EVA (dossier monté en lecture seule) → {fichier: base64}, version."""
    files: dict[str, str] = {}
    version = None
    for name in UPDATABLE:
        p = UPDATE_DIR / name
        if p.is_file():
            raw = p.read_bytes()
            files[name] = base64.b64encode(raw).decode()
            if name == "__init__.py":
                import re
                m = re.search(rb"VERSION\s*=\s*(\d+)", raw)
                version = int(m.group(1)) if m else None
    return files, version


async def update_server() -> dict:
    cfg = await images.get_config()
    if not cfg.get("token"):
        raise ServerError("Pour mettre à jour le serveur d'images depuis EVA, colle son jeton dans Paramètres › Génération d'images (affiché à la fin de l'installation).")
    files, version = bundle()
    if len(files) < len(UPDATABLE):
        raise ServerError("Le code du serveur d'images n'est pas disponible dans EVA (dossier eva-imagegen/app manquant sur le NAS).")
    out = await _call(cfg, "POST", "/eva/update", {"files": files}, 60)
    return {**out, "expected": version}
