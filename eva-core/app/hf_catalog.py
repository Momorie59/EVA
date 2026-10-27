"""Catalogue Hugging Face : recherche de modèles GGUF (téléchargeables par Ollama via « hf.co/<dépôt>:<quantification> »)
et estimation de ce que le serveur IA peut faire tourner (mémoire de la carte graphique + RAM)."""
import json
import os
import re

import httpx

from .db import get_pool

HF_BASE = os.getenv("EVA_HF_BASE", "https://huggingface.co").rstrip("/")
HF_TOKEN = os.getenv("EVA_HF_TOKEN", "")
DEFAULT_VRAM = float(os.getenv("EVA_GPU_VRAM_GB", "6"))   # GTX 1060 6 Go par défaut
DEFAULT_RAM = float(os.getenv("EVA_AI_RAM_GB", "16"))

SORTS = {"downloads": "downloads", "likes": "likes", "trending": "trendingScore", "recent": "lastModified"}
REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
QUANT_RE = re.compile(r"(?<![A-Za-z0-9])((?:IQ|Q)\d(?:_[A-Z0-9]+)*|BF16|FP16|F16|FP32|F32)(?![A-Za-z0-9])", re.I)
PARAM_RE = re.compile(r"(?<![A-Za-z0-9.])(\d+(?:\.\d+)?)\s?[bB](?![A-Za-z])")


class HFError(Exception):
    pass


async def _get(path: str, params: dict | None = None):
    headers = {"User-Agent": "EVA-local-assistant"}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=20.0, headers=headers, follow_redirects=True) as c:
            r = await c.get(f"{HF_BASE}{path}", params=params)
    except httpx.HTTPError as exc:
        raise HFError("Hugging Face est injoignable depuis EVA CORE (accès Internet du NAS ?).") from exc
    if r.status_code == 404:
        raise HFError("Dépôt introuvable sur Hugging Face.")
    if r.status_code != 200:
        raise HFError(f"Hugging Face a répondu {r.status_code}.")
    return r.json()


async def get_hardware() -> dict:
    hw = {"vram_gb": DEFAULT_VRAM, "ram_gb": DEFAULT_RAM}
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key='ai_hardware'")
    if raw:
        data = json.loads(raw) if isinstance(raw, str) else raw
        for k in hw:
            if isinstance(data.get(k), (int, float)) and 0 <= data[k] <= 2048:
                hw[k] = float(data[k])
    return hw


async def set_hardware(vram_gb: float, ram_gb: float) -> dict:
    if not (0 <= vram_gb <= 512 and 0 <= ram_gb <= 2048):
        raise ValueError("Valeurs hors limites.")
    hw = {"vram_gb": float(vram_gb), "ram_gb": float(ram_gb)}
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ('ai_hardware', $1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb", json.dumps(hw))
    return hw


def assess(size_gb: float, hw: dict) -> dict:
    """Verdict pour un fichier de modèle de `size_gb` Go : tient sur la carte, partagé carte/processeur (lent), ou trop gros."""
    need = round(size_gb * 1.1 + 0.6, 1)   # poids + cache de contexte et tampons
    vram, ram = hw["vram_gb"], hw["ram_gb"]
    if need <= vram:
        return {"level": "gpu", "need_gb": need, "label": "Tient sur la carte graphique", "detail": f"≈ {need} Go pour {vram:g} Go de mémoire vidéo : rapide."}
    if need <= vram + ram * 0.7:
        return {"level": "mixed", "need_gb": need, "label": "Lent : partagé avec le processeur",
                "detail": f"≈ {need} Go pour {vram:g} Go de mémoire vidéo : une partie du modèle passera dans la RAM ({ram:g} Go), la réponse sera nettement plus lente."}
    return {"level": "no", "need_gb": need, "label": "Trop gros pour ce serveur",
            "detail": f"≈ {need} Go nécessaires, le serveur n'offre que {vram:g} Go de mémoire vidéo + {ram:g} Go de RAM : le téléchargement est déconseillé."}


def guess_params_b(name: str, total: int | None) -> float | None:
    if total:
        return round(total / 1e9, 1)
    m = PARAM_RE.search(name)
    return float(m.group(1)) if m else None


async def search(q: str, sort: str = "downloads", limit: int = 20) -> list[dict]:
    params = {"filter": "gguf", "sort": SORTS.get(sort, "downloads"), "direction": "-1", "limit": str(max(1, min(limit, 40))),
              "expand[]": ["downloads", "likes", "gguf", "lastModified", "pipeline_tag"]}
    if q.strip():
        params["search"] = q.strip()[:80]
    data = await _get("/api/models", params)
    hw = await get_hardware()
    out = []
    for m in data if isinstance(data, list) else []:
        rid = m.get("id") or m.get("modelId") or ""
        if not REPO_RE.match(rid):
            continue
        g = m.get("gguf") or {}
        pb = guess_params_b(rid.split("/")[1], g.get("total"))
        entry = {"repo": rid, "downloads": m.get("downloads", 0), "likes": m.get("likes", 0), "params_b": pb,
                 "context": g.get("context_length"), "updated": m.get("lastModified"), "task": m.get("pipeline_tag")}
        if pb:   # estimation rapide avec une quantification 4 bits (~0,6 Go par milliard de paramètres)
            entry["q4_estimate"] = assess(pb * 0.6, hw)
        out.append(entry)
    return out


async def files(repo: str) -> dict:
    """Quantifications disponibles d'un dépôt, avec taille et verdict matériel."""
    if not REPO_RE.match(repo):
        raise HFError("Nom de dépôt invalide (attendu auteur/modèle).")
    tree = await _get(f"/api/models/{repo}/tree/main", {"recursive": "true"})
    hw = await get_hardware()
    groups: dict[str, dict] = {}
    for f in tree if isinstance(tree, list) else []:
        path = f.get("path", "")
        if f.get("type") != "file" or not path.lower().endswith(".gguf") or "mmproj" in path.lower():
            continue
        m = QUANT_RE.search(path.rsplit("/", 1)[-1])
        if not m:
            continue
        quant = m.group(1).upper().replace("FP", "F")
        size = (f.get("lfs") or {}).get("size") or f.get("size") or 0
        g = groups.setdefault(quant, {"quant": quant, "bytes": 0, "parts": 0})
        g["bytes"] += size
        g["parts"] += 1
    items = []
    for g in groups.values():
        gb = round(g["bytes"] / 1e9, 2)
        items.append({"quant": g["quant"], "size_gb": gb, "parts": g["parts"], "ollama": f"hf.co/{repo}:{g['quant']}", **assess(gb, hw)})
    items.sort(key=lambda i: i["size_gb"])
    return {"repo": repo, "hardware": hw, "files": items}


# ---------------------------------------------------------------- recommandations par rôle (« Suggestions » du choix automatique)
TRUSTED = ("unsloth", "bartowski", "lmstudio-community", "ggml-org", "qwen", "google", "microsoft", "mistralai", "ibm-granite", "huggingfacetb",
           "meta-llama", "deepseek-ai", "zai-org", "nvidia", "allenai")
BAD_WORDS = ("uncensored", "abliterated", "nsfw", "erp", "roleplay", "-rp", "lora", "merge", "base", "embed", "reranker", "whisper", "tts", "guard", "draft")
ROLE_SPECS = {
    "default": {"label": "Modèle par défaut", "queries": ["instruct", "qwen instruct", "gemma it", "mistral instruct"], "min_b": 3.0, "max_b": 15.0, "need": ()},
    "fast": {"label": "Rapide", "queries": ["small instruct", "qwen 3b instruct", "gemma 2b it", "llama 3.2 instruct"], "min_b": 0.8, "max_b": 4.5, "need": ()},
    "code": {"label": "Code", "queries": ["coder instruct", "code instruct"], "min_b": 1.5, "max_b": 15.0, "need": ("coder", "code")},
    "reasoning": {"label": "Raisonnement", "queries": ["reasoning", "thinking", "qwen3 instruct"], "min_b": 3.0, "max_b": 15.0, "need": ()},
    "vision": {"label": "Vision", "queries": ["vision instruct", "vl instruct"], "min_b": 2.0, "max_b": 15.0, "need": ("vl", "vision", "llava", "gemma-3", "minicpm", "smolvlm")},
}
PREFERRED_QUANTS = ("Q4_K_M", "Q4_K_S", "Q5_K_M", "Q4_0", "Q5_K_S", "Q6_K", "Q8_0", "IQ4_XS", "Q3_K_M")


def _score(m: dict) -> float:
    import math
    from datetime import datetime, timezone
    s = math.log10(max(1, m.get("downloads") or 1)) * 2 + math.log10(max(1, m.get("likes") or 1))
    owner = m["repo"].split("/")[0].lower()
    if owner in TRUSTED:
        s += 1.5
    try:   # un modèle récent vaut mieux qu'un vieux modèle très téléchargé
        age = (datetime.now(timezone.utc) - datetime.fromisoformat((m.get("updated") or "").replace("Z", "+00:00"))).days
        s += 1.5 if age < 90 else 0.8 if age < 240 else 0.0 if age < 540 else -1.0
    except ValueError:
        pass
    pb = m.get("params_b") or 0
    return s + min(pb, 14) * 0.12            # à qualité de popularité égale, le plus gros qui tient est meilleur


def _quant_pick(files_: list[dict]) -> dict | None:
    """La meilleure quantification qui tient sur la carte : Q4_K_M en priorité, sinon la plus grosse qui tient."""
    fit = [f for f in files_ if f["level"] == "gpu"]
    for q in PREFERRED_QUANTS:
        for f in fit:
            if f["quant"] == q:
                return f
    return max(fit, key=lambda f: f["size_gb"]) if fit else None


async def recommend(per_role: int = 3) -> dict:
    """Pour chaque rôle, cherche sur Hugging Face les meilleurs modèles GGUF qui tiennent sur le serveur IA (carte graphique d'abord)."""
    import asyncio
    hw = await get_hardware()

    async def one(role: str, spec: dict):
        seen: dict[str, dict] = {}
        for q in spec["queries"]:
            for sort in ("trending", "downloads"):
                try:
                    for m in await search(q, sort, limit=20):
                        seen.setdefault(m["repo"], m)
                except HFError:
                    continue
        cands = []
        for m in seen.values():
            name = m["repo"].split("/")[1].lower()
            pb = m.get("params_b")
            if not pb or not (spec["min_b"] <= pb <= spec["max_b"]) or any(w in name for w in BAD_WORDS):
                continue
            if spec["need"] and not any(w in name for w in spec["need"]):
                continue
            if not spec["need"] and any(w in name for w in ("coder", "-vl", "vision", "llava")):
                continue
            if not any(w in name for w in ("instruct", "-it", "chat", "coder", "thinking", "reason", "vl", "gguf")):
                continue
            est = m.get("q4_estimate")
            if est and est["level"] == "no":
                continue
            cands.append((_score(m) - (2.5 if est and est["level"] == "mixed" else 0), m))
        cands.sort(key=lambda t: -t[0])
        picks = []
        for sc, m in cands[:per_role + 4]:
            try:
                f = await files(m["repo"])
            except HFError:
                continue
            q = _quant_pick(f["files"]) or next((x for x in f["files"] if x["level"] == "mixed"), None)
            if not q:
                continue
            picks.append({"repo": m["repo"], "ollama": q["ollama"], "quant": q["quant"], "size_gb": q["size_gb"], "level": q["level"], "verdict": q["label"],
                          "detail": q["detail"], "params_b": m["params_b"], "downloads": m["downloads"], "likes": m["likes"], "updated": m.get("updated"),
                          "context": m.get("context"), "score": round(sc, 2)})
            if len(picks) >= per_role:
                break
        return {"role": role, "label": spec["label"], "choices": picks}

    roles = await asyncio.gather(*[one(r, s) for r, s in ROLE_SPECS.items()])
    return {"hardware": hw, "roles": list(roles)}
