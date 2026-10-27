"""Service AirLLM (facultatif) : fait tourner un très gros modèle (70B et plus) sur une petite carte graphique,
en chargeant une couche à la fois depuis le disque. TRÈS lent (minutes par réponse) : à réserver aux tâches de
réflexion lente, jamais à la conversation en direct. Une seule requête à la fois.

API compatible OpenAI (sans streaming) : POST /v1/chat/completions, GET /health.
Choix du modèle depuis l'interface d'EVA : GET/PUT /config (gardé dans /models/eva-config.json), DELETE /modeles/{nom}."""
import asyncio
import gc
import json
import os
import re
import shutil
import time

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

MODELE_ENV = os.getenv("AIRLLM_MODEL", "Qwen/Qwen2.5-72B-Instruct")
CONFIG = os.getenv("AIRLLM_CONFIG", "/models/eva-config.json")
HF_CACHE = os.getenv("HF_HUB_CACHE", os.path.join(os.getenv("HF_HOME", os.path.expanduser("~/.cache/huggingface")), "hub"))
NOM_MODELE = re.compile(r"^[A-Za-z0-9][\w.-]{0,63}/[\w.-]{1,96}$")
# Suggestions (architectures prises en charge par AirLLM : Qwen2, Llama, Mistral…). taille_go = poids en 16 bits à télécharger.
CATALOGUE = [
    {"id": "Qwen/Qwen2.5-0.5B-Instruct", "taille_go": 1.0, "note": "minuscule : rapide même sans carte graphique, réponses simples"},
    {"id": "Qwen/Qwen2.5-1.5B-Instruct", "taille_go": 3.1, "note": "conseillé sans carte graphique (tient en mémoire vive)"},
    {"id": "Qwen/Qwen2.5-3B-Instruct", "taille_go": 6.2, "note": "meilleur, plus lent sans carte graphique"},
    {"id": "Qwen/Qwen2.5-7B-Instruct", "taille_go": 15.2, "note": "bon niveau ; sans carte graphique : très lent (lu sur le disque)"},
    {"id": "Qwen/Qwen2.5-14B-Instruct", "taille_go": 29.5, "note": "carte graphique conseillée"},
    {"id": "Qwen/Qwen2.5-32B-Instruct", "taille_go": 65.5, "note": "carte graphique nécessaire"},
    {"id": "Qwen/Qwen2.5-72B-Instruct", "taille_go": 145.0, "note": "le plus fort ; carte graphique nécessaire, des minutes par réponse"},
    {"id": "mistralai/Mistral-7B-Instruct-v0.3", "taille_go": 14.5, "note": "alternative à Qwen 7B"},
]


def modele() -> str:
    """Modèle choisi dans l'interface d'EVA, sinon celui de .env (AIRLLM_MODEL)."""
    try:
        with open(CONFIG, encoding="utf-8") as f:
            m = json.load(f).get("model", "")
        if NOM_MODELE.match(m or ""):
            return m
    except (OSError, ValueError):
        pass
    return MODELE_ENV


def _slug(m: str) -> str:
    return m.replace("/", "--")


def dossier_couches(m: str | None = None) -> str:
    """Couches découpées, un dossier PAR modèle (AirLLM réutiliserait sinon les couches d'un autre modèle)."""
    return os.path.join(SHARDS, _slug(m or modele()))
COMPRESSION = os.getenv("AIRLLM_COMPRESSION", "4bit")          # 4bit | 8bit | none
MAX_NEW_TOKENS = int(os.getenv("AIRLLM_MAX_NEW_TOKENS", "256"))
SHARDS = os.getenv("AIRLLM_SHARDS_DIR", "/models/shards")
MAX_INPUT_TOKENS = int(os.getenv("AIRLLM_MAX_INPUT_TOKENS", "2048"))

RAM_CACHE = os.getenv("AIRLLM_RAM_CACHE", "1") not in ("0", "false", "no")       # garder les couches en mémoire vive
RAM_CACHE_GB = float(os.getenv("AIRLLM_RAM_CACHE_GB", "0"))                      # 0 = automatique (80 % de la RAM libre)

app = FastAPI(title="eva-airllm")
_state = {"materiel": "", "model": None, "loading": False, "busy": False, "last_ms": None, "error": "", "ram_cached_gb": 0.0, "ram_budget_gb": 0.0}


def _ram_budget_bytes() -> int:
    if RAM_CACHE_GB > 0:
        return int(RAM_CACHE_GB * 1e9)
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                return int(int(line.split()[1]) * 1024 * 0.8)
    except OSError:
        pass
    return 0


def warm_ram_cache(root: str | None = None, budget: int | None = None) -> int:
    """Relit les couches du modèle une fois : le système les garde alors en mémoire vive (cache disque) et chaque
    mot suivant les lit à la vitesse de la RAM au lieu du disque. S'arrête quand le budget de RAM est atteint
    (modèle plus gros que la RAM : on garde ce qui tient, le reste vient du disque)."""
    root = root or dossier_couches()
    budget = _ram_budget_bytes() if budget is None else budget
    done = 0
    for dirpath, _d, files in os.walk(root):
        for name in sorted(files):
            path = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(path)
                if done + size > budget:
                    continue
                fd = os.open(path, os.O_RDONLY)
                try:
                    if hasattr(os, "posix_fadvise"):
                        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_WILLNEED)
                    while os.read(fd, 16 * 1024 * 1024):
                        pass
                finally:
                    os.close(fd)
                done += size
            except OSError:
                continue
    return done


def _warm_state() -> None:
    _state["ram_budget_gb"] = round(_ram_budget_bytes() / 1e9, 1)
    _state["ram_cached_gb"] = round(warm_ram_cache() / 1e9, 1)


@app.on_event("startup")
async def _startup_warm():
    if RAM_CACHE and os.path.isdir(dossier_couches()):     # couches déjà découpées lors d'un précédent lancement
        asyncio.get_event_loop().run_in_executor(None, _warm_state)
_lock = asyncio.Lock()


class Msg(BaseModel):
    role: str
    content: str


class ChatBody(BaseModel):
    messages: list[Msg]
    max_tokens: int | None = None


def _gpu() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001
        return False


def options_chargement(gpu: bool) -> dict:
    """Réglages d'AirLLM selon le matériel. Sans carte graphique NVIDIA (le NAS) : processeur, nombres en 32 bits, sans
    compression (la compression 4/8 bits d'AirLLM passe par bitsandbytes, qui exige CUDA)."""
    os.makedirs(dossier_couches(), exist_ok=True)          # AirLLM y range les couches découpées ; il ne crée pas le dossier
    # max_seq_len : 512 par défaut chez AirLLM, trop court pour les consignes d'EVA (la question était alors perdue)
    kwargs = {"layer_shards_saving_path": dossier_couches(), "max_seq_len": MAX_INPUT_TOKENS + 1024}
    if gpu:
        if COMPRESSION in ("4bit", "8bit"):
            kwargs["compression"] = COMPRESSION
        kwargs["prefetching"] = True                        # charge la couche suivante pendant le calcul de la précédente
    else:
        import torch
        kwargs["device"] = "cpu"
        kwargs["dtype"] = torch.float32
        kwargs["prefetching"] = False
    if os.getenv("HF_TOKEN"):
        kwargs["hf_token"] = os.getenv("HF_TOKEN")
    return kwargs


def _load():
    from airllm import AutoModel                               # import tardif : le conteneur démarre vite
    gpu = _gpu()
    _state["materiel"] = "GPU NVIDIA" if gpu else "processeur (sans carte graphique : très lent)"
    kwargs = options_chargement(gpu)
    try:
        m = AutoModel.from_pretrained(modele(), **kwargs)
    except TypeError:
        kwargs.pop("prefetching", None)
        m = AutoModel.from_pretrained(modele(), **kwargs)
    if RAM_CACHE:
        _warm_state()
    return m


def _texte(tok, messages: list[dict]) -> str:
    if getattr(tok, "chat_template", None) and hasattr(tok, "apply_chat_template"):
        return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"


def ajuster(tok, messages: list[dict], limite: int) -> list[int]:
    """Jetons d'entrée qui tiennent dans `limite` SANS perdre la fin (la question et « assistant: ») : on retire d'abord
    les plus anciens échanges, puis on raccourcit les consignes. (Couper la fin faisait réciter au modèle le texte des
    documents joints au lieu de répondre.)"""
    msgs = [dict(m) for m in messages]
    n = lambda ms: len(tok(_texte(tok, ms), add_special_tokens=False)["input_ids"])  # noqa: E731
    while n(msgs) > limite and len(msgs) > 2:
        del msgs[1 if msgs[0]["role"] == "system" else 0]
    while n(msgs) > limite and any(len(m["content"]) > 400 for m in msgs[:-1]):
        i = max(range(len(msgs) - 1), key=lambda k: len(msgs[k]["content"]))
        msgs[i]["content"] = msgs[i]["content"][: len(msgs[i]["content"]) * 2 // 3] + " […]"
    ids = tok(_texte(tok, msgs), add_special_tokens=False)["input_ids"]
    return ids[-limite:]                                   # dernier recours : on garde la FIN


_arret = {"demande": False}


def _criteres():
    """S'arrête dès que « Arrêter » est demandé dans EVA (vérifié à chaque mot produit)."""
    try:
        from transformers import StoppingCriteria, StoppingCriteriaList
    except ImportError:
        return None

    class Arret(StoppingCriteria):
        def __call__(self, input_ids, scores, **kwargs):
            return _arret["demande"]
    return StoppingCriteriaList([Arret()])


def _generate(model, messages: list[dict], max_new: int) -> str:
    import torch
    _arret["demande"] = False
    tok = model.tokenizer
    ids = ajuster(tok, messages, MAX_INPUT_TOKENS)
    inp = torch.tensor([ids])
    if _gpu():
        inp = inp.cuda()
    crit = _criteres()
    out = model.generate(inp, max_new_tokens=max_new, use_cache=True, return_dict_in_generate=True, repetition_penalty=1.15,
                         **({"stopping_criteria": crit} if crit else {}))
    seq = out.sequences[0] if hasattr(out, "sequences") else out[0]
    return tok.decode(seq[inp.shape[1]:], skip_special_tokens=True).strip()


@app.post("/stop")
async def arreter():
    """Bouton « Arrêter » d'EVA : la réponse en cours s'arrête au mot suivant."""
    _arret["demande"] = True
    return {"ok": True, "en_cours": _state["busy"]}


@app.get("/health")
async def health():
    return {"ok": True, "model": modele(), "compression": COMPRESSION if _gpu() else "aucune (processeur)", "materiel": _state["materiel"], "loaded": _state["model"] is not None,
            "loading": _state["loading"], "busy": _state["busy"], "last_ms": _state["last_ms"], "error": _state["error"],
            "ram_cache": RAM_CACHE, "ram_cached_gb": _state["ram_cached_gb"], "ram_budget_gb": _state["ram_budget_gb"]}


@app.post("/v1/chat/completions")
async def chat(body: ChatBody, request: Request):
    if _lock.locked():
        raise HTTPException(status_code=429, detail="AirLLM traite déjà une demande (une seule à la fois).")
    async with _lock:
        _state["busy"] = True
        t0 = time.monotonic()
        try:
            if _state["model"] is None:
                _state["loading"] = True
                _state["model"] = await asyncio.to_thread(_load)   # 1re fois : découpe du modèle en couches sur le disque (long)
                _state["loading"] = False
            msgs = [m.model_dump() for m in body.messages]
            text = await asyncio.to_thread(_generate, _state["model"], msgs, min(body.max_tokens or MAX_NEW_TOKENS, 1024))
            _state["error"] = ""
        except Exception as exc:  # noqa: BLE001
            _state["loading"] = False
            _state["error"] = f"{type(exc).__name__}: {exc}"[:300]
            raise HTTPException(status_code=500, detail=_state["error"]) from exc
        finally:
            _state["busy"] = False
            _state["last_ms"] = int((time.monotonic() - t0) * 1000)
    return {"object": "chat.completion", "model": modele(),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]}


# ---------------------------------------------------------------- choix du modèle (interface d'EVA)

def _taille(chemin: str) -> int:
    total = 0
    for d, _s, fichiers in os.walk(chemin):
        for f in fichiers:
            try:
                total += os.path.getsize(os.path.join(d, f))
            except OSError:
                pass
    return total


def _ram_go() -> float:
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1e6, 1)
    except OSError:
        pass
    return 0.0


def modeles_presents() -> list[dict]:
    """Modèles déjà sur le disque (téléchargés et/ou découpés), avec la place prise."""
    noms: dict[str, int] = {}
    if os.path.isdir(HF_CACHE):
        for d in os.listdir(HF_CACHE):
            if d.startswith("models--"):
                m = d[len("models--"):].replace("--", "/", 1)
                noms[m] = noms.get(m, 0) + _taille(os.path.join(HF_CACHE, d))
    if os.path.isdir(SHARDS):
        for d in os.listdir(SHARDS):
            if "--" in d:
                m = d.replace("--", "/", 1)
                noms[m] = noms.get(m, 0) + _taille(os.path.join(SHARDS, d))
    return [{"id": m, "taille_go": round(t / 1e9, 1)} for m, t in sorted(noms.items())]


@app.get("/config")
async def lire_config():
    libre = shutil.disk_usage(SHARDS if os.path.isdir(SHARDS) else "/").free
    return {"model": modele(), "depuis_env": modele() == MODELE_ENV and not os.path.isfile(CONFIG), "catalogue": CATALOGUE,
            "presents": modeles_presents(), "gpu": _gpu(), "ram_go": _ram_go(), "disque_libre_go": round(libre / 1e9, 1),
            "loaded": _state["model"] is not None, "busy": _state["busy"] or _state["loading"]}


class ChoixModele(BaseModel):
    model: str


@app.put("/config")
async def changer_modele(body: ChoixModele):
    m = body.model.strip()
    if not NOM_MODELE.match(m):
        raise HTTPException(status_code=400, detail="Nom de modèle Hugging Face attendu, de la forme « auteur/modèle » (ex. Qwen/Qwen2.5-1.5B-Instruct).")
    if _lock.locked():
        raise HTTPException(status_code=409, detail="AirLLM est en train de répondre : réessaie quand il a fini.")
    os.makedirs(os.path.dirname(CONFIG) or ".", exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump({"model": m}, f)
    if _state["model"] is not None:                          # on décharge l'ancien : le nouveau se chargera à la prochaine question
        _state["model"] = None
        gc.collect()
    _state["error"] = ""
    return await lire_config()


@app.delete("/modeles/{auteur}/{nom}")
async def supprimer_modele(auteur: str, nom: str):
    m = f"{auteur}/{nom}"
    if not NOM_MODELE.match(m):
        raise HTTPException(status_code=400, detail="Nom de modèle invalide.")
    if m == modele():
        raise HTTPException(status_code=409, detail="C'est le modèle utilisé : choisis-en un autre avant de le supprimer.")
    for chemin in (os.path.join(HF_CACHE, "models--" + _slug(m)), os.path.join(SHARDS, _slug(m))):
        if os.path.isdir(chemin):
            shutil.rmtree(chemin, ignore_errors=True)
    return await lire_config()
