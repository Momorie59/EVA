"""Modèles d'images : voir ce qui est installé, télécharger depuis Hugging Face (avec progression), supprimer.
Tout se pilote depuis EVA ; rien à faire en ligne de commande sur le serveur IA."""
import os
import re
import shutil
import threading
import time
from pathlib import Path

HF_HOME = Path(os.getenv("HF_HOME", "/models/hf"))
MODELS_DIR = Path(os.getenv("IMAGEGEN_MODELS_DIR", "/models"))
REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
EXTS = (".safetensors", ".ckpt")
PULLS: dict[str, dict] = {}
_lock = threading.Lock()


def repo_dir(repo: str) -> Path:
    return HF_HOME / "hub" / ("models--" + repo.replace("/", "--"))


def _size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def installed() -> list[dict]:
    """Modèles présents : dépôts téléchargés (cache Hugging Face) + fichiers .safetensors/.ckpt déposés dans le dossier des modèles."""
    out = []
    hub = HF_HOME / "hub"
    if hub.is_dir():
        for d in sorted(hub.glob("models--*")):
            snaps = d / "snapshots"
            if not snaps.is_dir() or not any(snaps.iterdir()):
                continue                                          # téléchargement interrompu : pas encore utilisable
            repo = d.name[len("models--"):].replace("--", "/", 1)
            out.append({"id": repo, "source": "hub", "size_gb": round(_size(d) / 2**30, 2)})
    try:
        for p in sorted(MODELS_DIR.glob("*")):
            if p.is_file() and p.suffix.lower() in EXTS:
                out.append({"id": p.name, "source": "fichier", "size_gb": round(p.stat().st_size / 2**30, 2)})
    except OSError:
        pass
    return out


def disk_free_gb() -> float:
    try:
        return round(shutil.disk_usage(HF_HOME if HF_HOME.exists() else MODELS_DIR if MODELS_DIR.exists() else "/").free / 2**30, 1)
    except OSError:
        return 0.0


def pick_files(names: list[str]) -> list[str]:
    """Fichiers à télécharger pour utiliser un dépôt « diffusers » : réglages + poids (en demi-précision quand le dossier en propose, sinon
    les poids normaux), sans vérificateur de sécurité, sans doublons (.bin, .ckpt, onnx, flax, gros fichier unique à la racine)."""
    fp16_dirs = {n.rsplit("/", 1)[0] for n in names if "/" in n and n.endswith(".fp16.safetensors")}
    keep = []
    for n in names:
        if n.startswith(("safety_checker/", "feature_extractor/")) and not n.endswith(".json"):
            continue
        if "/" not in n:
            if n == "model_index.json":
                keep.append(n)
            continue
        if n.endswith((".json", ".txt")):
            keep.append(n)
        elif n.endswith(".safetensors"):
            has_fp16 = ".fp16." in n
            if has_fp16 or (n.rsplit("/", 1)[0] not in fp16_dirs and "non_ema" not in n and "ema_only" not in n):
                keep.append(n)
    return keep


def start_pull(repo: str, token: str = "") -> dict:
    if not REPO_RE.match(repo):
        raise ValueError("Nom de modèle invalide (attendu « auteur/modèle »).")
    with _lock:
        cur = PULLS.get(repo)
        if cur and not cur["done"]:
            return cur
        PULLS[repo] = {"id": repo, "status": "préparation", "completed": 0, "total": 0, "done": False, "error": "", "started": time.time()}
        st = PULLS[repo]
    threading.Thread(target=_pull, args=(repo, token, st), daemon=True).start()
    return st


def _pull(repo: str, token: str, st: dict) -> None:
    try:
        from huggingface_hub import HfApi, snapshot_download
        info = HfApi(token=token or None).model_info(repo, files_metadata=True)
        sizes = {s.rfilename: (getattr(s, "size", 0) or 0) for s in (info.siblings or [])}
        keep = pick_files(list(sizes))
        if not any(n.endswith(".safetensors") for n in keep):
            raise ValueError("Ce dépôt n'est pas au format « diffusers » (pas de poids .safetensors par dossier). Pour un fichier unique, dépose-le dans le dossier des modèles.")
        st["total"] = sum(sizes[n] for n in keep)
        free = disk_free_gb()
        if st["total"] and free and st["total"] / 2**30 > free - 1:
            raise OSError(f"Place insuffisante : {st['total'] / 2**30:.1f} Go à télécharger, {free} Go libres.")
        st["status"] = "téléchargement"
        stop = threading.Event()

        def watch():
            while not stop.wait(1.0):
                st["completed"] = min(st["total"] or 1 << 60, _size(repo_dir(repo) / "blobs"))
        threading.Thread(target=watch, daemon=True).start()
        try:
            snapshot_download(repo, allow_patterns=keep, token=token or None)
        finally:
            stop.set()
        st.update(status="terminé", completed=st["total"], done=True)
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        if any(k in msg for k in ("401", "403", "GatedRepo", "gated")):
            msg = "Ce modèle demande un compte Hugging Face (accepter sa licence puis définir HF_TOKEN sur le serveur)."
        elif "404" in msg or "RepositoryNotFound" in msg:
            msg = "Modèle introuvable sur Hugging Face."
        elif any(k in msg for k in ("ConnectionError", "Connect", "Timeout", "Name or service")):
            msg = "Hugging Face est injoignable depuis le serveur IA (accès Internet ?)."
        st.update(error=msg[:300], done=True, status="échec")


def delete(model_id: str) -> bool:
    """Supprime un modèle téléchargé ou un fichier déposé. Refuse tout ce qui sort des dossiers de modèles."""
    if REPO_RE.match(model_id):
        d = repo_dir(model_id)
        if d.is_dir() and d.resolve().is_relative_to((HF_HOME / "hub").resolve()):
            shutil.rmtree(d)
            PULLS.pop(model_id, None)
            return True
        return False
    if "/" not in model_id and model_id.lower().endswith(EXTS):
        p = MODELS_DIR / model_id
        if p.is_file():
            p.unlink()
            return True
    return False
