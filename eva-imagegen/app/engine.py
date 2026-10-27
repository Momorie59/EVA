"""Moteur de génération d'images (diffusers) — conçu pour une carte de 6 Go.

- chargement à la demande, déchargement après un temps d'inactivité (la mémoire de la carte revient à Ollama) ;
- avant de charger, demande à Ollama de décharger ses modèles (même carte, même mémoire) ;
- demi-précision sur GPU, attention découpée, VAE découpé ; SDXL : déchargement vers le processeur ;
- modèles « Turbo » : 1 à 4 étapes, sans guidage (très rapide) ; modèles classiques : 20 étapes, guidage 7 ;
- modèles supplémentaires : dépose un fichier .safetensors / .ckpt dans /models (ex. un modèle réaliste ou anime).
Une seule image à la fois (file d'attente)."""
import gc
import io
import math
import os
import random
import re
import threading
import time
from pathlib import Path
from typing import Any

MODEL = os.getenv("IMAGEGEN_MODEL", "stabilityai/sd-turbo")
MODELS_DIR = Path(os.getenv("IMAGEGEN_MODELS_DIR", "/models"))
IDLE_UNLOAD = float(os.getenv("IMAGEGEN_IDLE_UNLOAD", "90"))
OLLAMA_URL = os.getenv("IMAGEGEN_OLLAMA_URL", "").rstrip("/")
MAX_PIXELS = int(os.getenv("IMAGEGEN_MAX_PIXELS", str(1024 * 1024)))
MAX_BATCH = int(os.getenv("IMAGEGEN_MAX_BATCH", "2"))
DEVICE_PREF = os.getenv("IMAGEGEN_DEVICE", "auto")
EXTS = (".safetensors", ".ckpt")
CLIPSEG = os.getenv("IMAGEGEN_CLIPSEG", "CIDAS/clipseg-rd64-refined")        # trouve « le poteau » sur une photo à partir d'un mot (≈ 600 Mo, 1re modification seulement)
MAX_EDIT_SIDE = int(os.getenv("IMAGEGEN_MAX_EDIT_SIDE", "768"))


class ImageGenError(RuntimeError):
    pass


def profile(model: str) -> dict:
    """Réglages adaptés au modèle : (étapes, guidage, taille, XL ?)."""
    name = model.lower()
    xl = "xl" in name or "sdxl" in name
    if "turbo" in name or "lightning" in name or "lcm" in name:
        return {"steps": 2 if xl else 4, "max_steps": 8, "cfg": 0.0 if "turbo" in name else 1.5, "size": 512, "xl": xl, "turbo": True}
    return {"steps": 20, "max_steps": 60, "cfg": 7.0, "size": 1024 if xl else 512, "xl": xl, "turbo": False}


def list_models() -> list[dict]:
    """Modèles utilisables : celui par défaut (téléchargé à la demande) + les fichiers déposés dans /models."""
    out = [{"title": MODEL, "model_name": MODEL, "source": "hub"}]
    try:
        for p in sorted(MODELS_DIR.glob("*")):
            if p.suffix.lower() in EXTS:
                out.append({"title": p.name, "model_name": p.stem, "source": "fichier"})
    except OSError:
        pass
    return out


def resolve(name: str) -> str:
    """Nom demandé → identifiant du hub ou chemin du fichier ; refuse tout ce qui sort de /models."""
    name = (name or "").strip()
    if not name or name == MODEL:
        return MODEL
    for m in list_models():
        if name in (m["title"], m["model_name"]):
            return MODEL if m["source"] == "hub" else str(MODELS_DIR / m["title"])
    if re.fullmatch(r"[\w.\-]+/[\w.\-]+", name):                # identifiant « auteur/modèle » du hub
        return name
    raise ImageGenError(f"Modèle inconnu : {name}")


def _gpu() -> dict:
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            return {"name": torch.cuda.get_device_name(0), "vram_total_mb": total // 2**20, "vram_free_mb": free // 2**20}
    except Exception:  # noqa: BLE001
        pass
    return {}


def free_ollama() -> str:
    """Demande à Ollama de décharger ses modèles de la carte (keep_alive=0) pour libérer la mémoire."""
    if not OLLAMA_URL:
        return ""
    import httpx
    try:
        with httpx.Client(timeout=5) as c:
            ps = c.get(f"{OLLAMA_URL}/api/ps").json().get("models", [])
            for m in ps:
                c.post(f"{OLLAMA_URL}/api/generate", json={"model": m.get("name") or m.get("model"), "keep_alive": 0})
            return f"{len(ps)} modèle(s) Ollama déchargé(s)" if ps else ""
    except Exception as exc:  # noqa: BLE001 — Ollama absent : on continue
        return f"Ollama non joint ({type(exc).__name__})"


def load_pipeline(spec: str, device: str, dtype_name: str):
    """Charge le modèle (remplaçable dans les tests)."""
    import torch
    import diffusers
    dtype = torch.float16 if dtype_name == "fp16" else torch.float32
    kind = profile(spec)
    kw: dict[str, Any] = {"torch_dtype": dtype, "safety_checker": None, "requires_safety_checker": False}
    if spec.lower().endswith(EXTS):
        cls = diffusers.StableDiffusionXLPipeline if (kind["xl"] or Path(spec).stat().st_size > 5 * 2**30) else diffusers.StableDiffusionPipeline
        if cls is diffusers.StableDiffusionXLPipeline:
            kw.pop("safety_checker"); kw.pop("requires_safety_checker")
        pipe = cls.from_single_file(spec, **kw)
    else:
        if kind["xl"]:
            kw.pop("safety_checker"); kw.pop("requires_safety_checker")
            if dtype == torch.float16:
                kw["variant"] = "fp16"
        elif dtype == torch.float16:
            kw["variant"] = "fp16"
        try:
            pipe = diffusers.AutoPipelineForText2Image.from_pretrained(spec, **kw)
        except (OSError, ValueError):
            kw.pop("variant", None)                               # certains dépôts n'ont pas de variante fp16
            pipe = diffusers.AutoPipelineForText2Image.from_pretrained(spec, **kw)
    return pipe


def load_clipseg():
    """Charge le détecteur de zones par le texte (sur le processeur : ne prend rien à la carte). Remplaçable dans les tests."""
    from transformers import CLIPSegForImageSegmentation, CLIPSegProcessor
    return CLIPSegProcessor.from_pretrained(CLIPSEG), CLIPSegForImageSegmentation.from_pretrained(CLIPSEG).eval()


def mask_from_logits(logits, size: tuple[int, int], grow: int = 10, threshold: float = 0.35):
    """Sortie du détecteur → masque noir/blanc à la taille de l'image, un peu élargi (les bords de l'objet sont inclus)."""
    import torch
    from PIL import Image, ImageFilter
    prob = torch.sigmoid(logits.float()).reshape(1, 1, *logits.shape[-2:])
    prob = torch.nn.functional.interpolate(prob, size=(size[1], size[0]), mode="bilinear", align_corners=False)[0, 0]
    top = float(prob.max())
    if top < 0.2:                                              # rien de reconnaissable
        return Image.new("L", size, 0), 0.0
    m = Image.fromarray(((prob >= max(threshold, top * 0.5)).numpy() * 255).astype("uint8"), "L")
    if grow > 0:
        m = m.filter(ImageFilter.MaxFilter(2 * grow + 1))
    pct = sum(m.histogram()[255:]) / max(1, size[0] * size[1])
    return m, pct


class Engine:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.pipe = None
        self.spec = ""
        self.device = "cpu"
        self.dtype = "fp32"
        self.last_use = 0.0
        self.busy = False
        self.loading = False
        self.last_error = ""
        self.count = 0
        self.current = MODEL
        self.notes: list[str] = []
        self.edit_pipes: dict[str, Any] = {}
        self.clipseg = None

    # -- choix du matériel
    def _target(self) -> tuple[str, str]:
        try:
            import torch
            if DEVICE_PREF in ("auto", "cuda") and torch.cuda.is_available():
                return "cuda", "fp16"
        except Exception:  # noqa: BLE001
            pass
        return "cpu", "fp32"

    def status(self) -> dict:
        d, _ = self._target()
        return {"ok": True, "device": d, "gpu": _gpu() if d == "cuda" else {}, "model": self.current, "loaded": self.pipe is not None, "busy": self.busy,
                "loading": self.loading, "generated": self.count, "idle_unload_s": IDLE_UNLOAD, "last_error": self.last_error,
                "defaults": {k: v for k, v in profile(self.current).items() if k in ("steps", "cfg", "size", "turbo", "max_steps")}, "notes": self.notes[-3:]}

    def unload(self) -> bool:
        with self.lock:
            return self._unload()

    def _unload(self, keep_zone_finder: bool = False) -> bool:
        had = self.pipe is not None
        self.pipe = None
        self.edit_pipes = {}
        if not keep_zone_finder:
            self.clipseg = None
        self.spec = ""
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass
        return had

    def idle_check(self) -> None:
        """Appelé périodiquement : décharge le modèle s'il dort depuis trop longtemps."""
        if self.pipe is not None and not self.busy and IDLE_UNLOAD > 0 and time.time() - self.last_use > IDLE_UNLOAD and self.lock.acquire(blocking=False):
            try:
                if not self.busy and time.time() - self.last_use > IDLE_UNLOAD:
                    self._unload()
                    self.notes.append("modèle déchargé (repos) : mémoire rendue à Ollama")
            finally:
                self.lock.release()

    def _ensure(self, spec: str) -> None:
        if self.pipe is not None and self.spec == spec:
            return
        self.loading = True
        try:
            self._unload(keep_zone_finder=True)             # le détecteur de zones vient peut-être d'être chargé pour cette demande
            note = free_ollama()
            if note:
                self.notes.append(note)
            device, dtype = self._target()
            pipe = load_pipeline(spec, device, dtype)
            kind = profile(spec)
            if device == "cuda":
                total = (_gpu().get("vram_total_mb") or 0)
                if kind["xl"] and total < 12000:
                    pipe.enable_model_cpu_offload()                # XL ne tient pas dans 6 Go : les blocs passent un à un sur la carte
                else:
                    pipe.to("cuda")
            else:
                pipe.to("cpu")
            for fn in ("enable_attention_slicing", "enable_vae_slicing"):
                try:
                    getattr(pipe, fn)()
                except Exception:  # noqa: BLE001
                    pass
            if hasattr(pipe, "set_progress_bar_config"):
                pipe.set_progress_bar_config(disable=True)
            self.pipe, self.spec, self.device, self.dtype = pipe, spec, device, dtype
        finally:
            self.loading = False

    def generate(self, prompt: str, negative: str = "", width: int = 0, height: int = 0, steps: int = 0, cfg: float | None = None,
                 seed: int = -1, n: int = 1, model: str = "") -> tuple[list[bytes], dict]:
        prompt = (prompt or "").strip()
        if not prompt:
            raise ImageGenError("Description vide.")
        spec = resolve(model or self.current)
        prof = profile(spec)
        w = int(width or prof["size"]); h = int(height or prof["size"])
        w, h = max(64, min(w, 2048)) // 8 * 8, max(64, min(h, 2048)) // 8 * 8
        while w * h > MAX_PIXELS:                                  # trop grand pour la mémoire : on réduit en gardant les proportions
            w, h = max(64, int(w * 0.9) // 8 * 8), max(64, int(h * 0.9) // 8 * 8)
        steps = prof["steps"] if not steps or steps <= 0 else min(int(steps), prof["max_steps"])
        guidance = prof["cfg"] if cfg is None or (prof["turbo"] and cfg > 2.5) else float(cfg)
        n = max(1, min(int(n or 1), MAX_BATCH))
        seed = int(seed) if seed is not None and int(seed) >= 0 else random.randint(0, 2**31 - 1)
        with self.lock:
            self.busy = True
            t0 = time.time()
            try:
                self.current = spec
                self._ensure(spec)
                import torch
                images: list[bytes] = []
                for i in range(n):
                    gen = torch.Generator(device="cpu").manual_seed(seed + i)
                    kw = {"prompt": prompt, "width": w, "height": h, "num_inference_steps": steps, "guidance_scale": guidance, "generator": gen}
                    if negative and guidance > 1.0:
                        kw["negative_prompt"] = negative
                    out = self.pipe(**kw).images[0]
                    if _is_black(out) and self.device == "cuda" and self.dtype == "fp16":
                        self.notes.append("image noire (dépassement en demi-précision) : nouvel essai en pleine précision")
                        self.pipe.to(torch.float32) if hasattr(self.pipe, "to") else None
                        self.dtype = "fp32"
                        out = self.pipe(**kw).images[0]
                    buf = io.BytesIO()
                    out.save(buf, format="PNG")
                    images.append(buf.getvalue())
                self.count += len(images)
                self.last_error = ""
                info = {"seed": seed, "model": spec, "width": w, "height": h, "steps": steps, "cfg_scale": guidance, "took": round(time.time() - t0, 2),
                        "device": self.device, "prompt": prompt, "negative_prompt": negative}
                return images, info
            except ImageGenError:
                raise
            except Exception as exc:  # noqa: BLE001 — mémoire saturée, modèle introuvable, hors ligne…
                self.last_error = f"{type(exc).__name__}: {exc}"[:300]
                self._unload()
                if "out of memory" in str(exc).lower():
                    raise ImageGenError("Mémoire de la carte saturée : réduis la taille de l'image ou ferme ce qui l'utilise (Ollama libère la sienne tout seul).") from exc
                raise ImageGenError(self.last_error) from exc
            finally:
                self.busy = False
                self.last_use = time.time()

    # -- modification d'une image existante (image → image, et retouche d'une zone)
    def _edit_pipe(self, kind: str):
        if kind not in self.edit_pipes:
            import diffusers
            cls = diffusers.AutoPipelineForInpainting if kind == "inpaint" else diffusers.AutoPipelineForImage2Image
            p = cls.from_pipe(self.pipe)                       # partage les composants : aucune mémoire de carte en plus
            if hasattr(p, "set_progress_bar_config"):
                p.set_progress_bar_config(disable=True)
            self.edit_pipes[kind] = p
        return self.edit_pipes[kind]

    def _find_zone(self, img, target: str, grow: int):
        if self.clipseg is None:
            self.clipseg = load_clipseg()
        import torch
        proc, model = self.clipseg
        with torch.no_grad():
            inputs = proc(text=[target], images=[img], return_tensors="pt", padding=True)
            logits = model(**inputs).logits
        mask, pct = mask_from_logits(logits, img.size, grow)
        if pct <= 0.002:
            raise ImageGenError(f"Je n'ai pas trouvé « {target} » sur l'image.")
        return mask, pct

    def edit(self, image: bytes, prompt: str = "", negative: str = "", strength: float | None = None, steps: int = 0, cfg: float | None = None,
             seed: int = -1, model: str = "", target: str = "", mask: bytes | None = None, grow: int = 10) -> tuple[list[bytes], dict]:
        """Sans zone : transforme toute l'image (strength = part laissée à l'IA, 0.3 léger … 0.9 très libre).
        Avec `target` (un mot : « le poteau ») ou un `mask` : ne refait que cette zone, le reste de l'image est conservé tel quel."""
        from PIL import Image, ImageFilter
        prompt = (prompt or "").strip()
        if not prompt:
            raise ImageGenError("Dis ce que tu veux obtenir.")
        try:
            src = Image.open(io.BytesIO(image)).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            raise ImageGenError("Image illisible.") from exc
        w, h = src.size
        scale = min(1.0, MAX_EDIT_SIDE / max(w, h), math.sqrt(MAX_PIXELS / (w * h)))
        w, h = max(16, int(w * scale) // 8 * 8), max(16, int(h * scale) // 8 * 8)
        src = src.resize((w, h), Image.LANCZOS)
        spec = resolve(model or self.current)
        prof = profile(spec)
        mode = "inpaint" if (target or mask) else "img2img"
        t0 = time.time()
        pct = 1.0
        zone = None
        if mask:
            try:
                zone = Image.open(io.BytesIO(mask)).convert("L").resize((w, h), Image.NEAREST).point(lambda v: 255 if v > 127 else 0)
            except Exception as exc:  # noqa: BLE001
                raise ImageGenError("Masque illisible.") from exc
            pct = sum(zone.histogram()[255:]) / (w * h)
            if pct <= 0.002:
                raise ImageGenError("Le masque est vide.")
        elif target:
            with self.lock:                                    # détecteur sur le processeur ; sous verrou pour ne pas se marcher dessus
                zone, pct = self._find_zone(src, target.strip()[:80], int(grow))
        st = float(strength) if strength is not None else (1.0 if mode == "inpaint" else 0.6)
        st = max(0.05, min(st, 1.0))
        base = prof["steps"] if not steps or steps <= 0 else min(int(steps), prof["max_steps"])
        n_steps = max(base, math.ceil(1.0 / st))               # le pipeline fait int(étapes × force) étapes : au moins une
        guidance = prof["cfg"] if cfg is None or (prof["turbo"] and cfg > 2.5) else float(cfg)
        seed = int(seed) if seed is not None and int(seed) >= 0 else random.randint(0, 2**31 - 1)
        with self.lock:
            self.busy = True
            try:
                self.current = spec
                self._ensure(spec)
                import torch
                pipe = self._edit_pipe(mode)
                gen = torch.Generator(device="cpu").manual_seed(seed)
                kw: dict[str, Any] = {"prompt": prompt, "image": src, "strength": st, "num_inference_steps": n_steps, "guidance_scale": guidance, "generator": gen}
                if negative and guidance > 1.0:
                    kw["negative_prompt"] = negative
                if mode == "inpaint":
                    kw.update(mask_image=zone, width=w, height=h)
                out = pipe(**kw).images[0]
                if _is_black(out) and self.device == "cuda" and self.dtype == "fp16":
                    self.notes.append("image noire (dépassement en demi-précision) : nouvel essai en pleine précision")
                    self.pipe.to(torch.float32); self.edit_pipes = {}; self.dtype = "fp32"
                    out = self._edit_pipe(mode)(**kw).images[0]
                out = out.convert("RGB").resize((w, h))
                if mode == "inpaint":                          # hors de la zone : les pixels d'origine, intacts ; bords adoucis
                    out = Image.composite(out, src, zone.filter(ImageFilter.GaussianBlur(3)))
                buf = io.BytesIO(); out.save(buf, format="PNG")
                self.count += 1
                self.last_error = ""
                return [buf.getvalue()], {"mode": mode, "seed": seed, "model": spec, "width": w, "height": h, "steps": n_steps, "strength": st, "cfg_scale": guidance,
                                         "took": round(time.time() - t0, 2), "device": self.device, "prompt": prompt, "target": target, "zone_pct": round(pct, 3)}
            except ImageGenError:
                raise
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {exc}"[:300]
                self._unload()
                if "out of memory" in str(exc).lower():
                    raise ImageGenError("Mémoire de la carte saturée : essaie une image plus petite.") from exc
                raise ImageGenError(self.last_error) from exc
            finally:
                self.busy = False
                self.last_use = time.time()

    def set_model(self, name: str) -> str:
        spec = resolve(name)
        with self.lock:
            if spec != self.spec:
                self._unload()
            self.current = spec
        return spec


def _is_black(img) -> bool:
    try:
        ex = img.convert("L").getextrema()
        return ex[1] <= 2
    except Exception:  # noqa: BLE001
        return False


engine = Engine()


# ====================================================================== Vidéo par IA (expérimental)
# Ce bloc vit dans engine.py pour que la mise à jour à distance (4 fichiers autorisés) l'apporte aussi aux serveurs déjà installés.
# Clips vidéo par IA (LTX-Video) — EXPÉRIMENTAL, désactivé par défaut (IMAGEGEN_VIDEO=1 pour l'activer).
# 
# Honnêteté : LTX-Video est pensé pour des cartes de 12 Go et plus. Sur une carte de 6 Go, chaque pièce du modèle passe tour à tour par la carte
# (déchargement séquentiel) : compte plusieurs minutes pour un clip de 1 à 2 secondes en petite taille, et le résultat reste modeste.
# Le modèle n'est chargé que pour la demande, puis tout est libéré (la mémoire revient à Ollama). Sortie : WebP animé (pas de dépendance en plus).
import io


VIDEO_ENABLED = os.getenv("IMAGEGEN_VIDEO", "0") == "1"
VIDEO_MODEL = os.getenv("IMAGEGEN_VIDEO_MODEL", "Lightricks/LTX-Video")
MAX_FRAMES = int(os.getenv("IMAGEGEN_VIDEO_MAX_FRAMES", "49"))
MAX_SIDE = int(os.getenv("IMAGEGEN_VIDEO_MAX_SIDE", "576"))
FPS = 12
DISABLED_MSG = ("La vidéo par IA est désactivée sur ce serveur (expérimental, très lent sur une carte de 6 Go). "
                "Pour l'essayer : relance install-imagegen.sh avec --video.")


def video_status() -> dict:
    return {"enabled": VIDEO_ENABLED, "model": VIDEO_MODEL, "max_frames": MAX_FRAMES, "fps": FPS}


def load_video_pipeline(spec: str):
    """Charge LTX-Video (remplaçable dans les tests)."""
    import torch
    from diffusers import LTXPipeline
    pipe = LTXPipeline.from_pretrained(spec, torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16)
    if torch.cuda.is_available():
        pipe.enable_sequential_cpu_offload()              # une pièce à la fois sur la carte : lent, mais ça tient
    for fn in ("enable_vae_tiling", "enable_vae_slicing"):
        try:
            getattr(pipe, fn)()
        except Exception:  # noqa: BLE001
            pass
    return pipe


def to_webp(frames: list, fps: int = FPS) -> bytes:
    buf = io.BytesIO()
    frames[0].save(buf, format="WEBP", save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0, quality=80, method=4)
    return buf.getvalue()


def valid_frames(n: int) -> int:
    """LTX veut 8k+1 images."""
    n = max(9, min(int(n or 25), MAX_FRAMES))
    return (n - 1) // 8 * 8 + 1


def generate_video(prompt: str, frames: int = 25, steps: int = 20, width: int = 512, height: int = 320, seed: int = -1) -> tuple[bytes, dict]:
    if not VIDEO_ENABLED:
        raise ImageGenError(DISABLED_MSG)
    prompt = (prompt or "").strip()
    if not prompt:
        raise ImageGenError("Description vide.")
    frames = valid_frames(frames)
    steps = max(4, min(int(steps or 20), 40))
    w = max(64, min(int(width or 512), MAX_SIDE)) // 32 * 32
    h = max(64, min(int(height or 320), MAX_SIDE)) // 32 * 32
    seed = int(seed) if seed is not None and int(seed) >= 0 else random.randint(0, 2**31 - 1)
    t0 = time.time()
    with engine.lock:                                         # la carte sert à un seul travail à la fois (images ou vidéo)
        engine.busy = True
        try:
            engine._unload()
            note = free_ollama()
            if note:
                engine.notes.append(note)
            pipe = load_video_pipeline(VIDEO_MODEL)
            try:
                import torch
                gen = torch.Generator("cpu").manual_seed(seed)
                out: Any = pipe(prompt=prompt, negative_prompt="worst quality, inconsistent motion, blurry, jittery, distorted", width=w, height=h,
                                num_frames=frames, num_inference_steps=steps, generator=gen, output_type="pil")
                clip = out.frames[0]
            except Exception as exc:  # noqa: BLE001 — manque de mémoire, etc. : message clair, jamais un plantage du serveur
                engine.last_error = f"{type(exc).__name__}: {exc}"[:300]
                raise ImageGenError(f"La vidéo a échoué ({type(exc).__name__}) : probablement trop gourmande pour cette carte. Essaie moins d'images ou une taille plus petite.") from exc
            finally:
                del pipe
                gc.collect()
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:  # noqa: BLE001
                    pass
            data = to_webp(list(clip))
        finally:
            engine.busy = False
            engine.last_use = time.time()
    return data, {"frames": frames, "fps": FPS, "seconds": round(frames / FPS, 1), "width": w, "height": h, "steps": steps, "seed": seed,
                  "model": VIDEO_MODEL, "took_s": round(time.time() - t0, 1)}
