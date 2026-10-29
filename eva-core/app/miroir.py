"""Mode miroir : un écran (nu ou derrière un miroir sans tain) qui reconnaît la famille, s'allume quand quelqu'un se
présente et affiche ses informations. Écrit pour EVA (aucun code repris d'un autre projet).

- Détection et reconnaissance des visages SUR LE NAS, avec OpenCV (déjà installé) et deux petits modèles libres de
  l'OpenCV Zoo : YuNet (détection, MIT) et SFace (empreinte du visage, Apache-2.0), téléchargés une fois (≈ 39 Mo)
  et vérifiés par leur empreinte SHA-256.
- Aucune image n'est gardée : l'écran envoie une petite photo toutes les secondes et demie, EVA la regarde et l'oublie.
  Seules les « empreintes » (128 nombres par photo apprise) des personnes qui l'ont accepté sont gardées en base, et
  chacun peut effacer les siennes.
- Plusieurs personnes devant le miroir, ou une personne inconnue : mode discret (rien de personnel affiché)."""
import asyncio
import base64
import hashlib
import logging
import os
from pathlib import Path

from .db import get_pool

logger = logging.getLogger("eva-core.miroir")

SCHEMA = """
CREATE TABLE IF NOT EXISTS miroir_visages (
    id BIGSERIAL PRIMARY KEY,
    qui TEXT NOT NULL,
    emb BYTEA NOT NULL,
    cree TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS miroir_visages_qui ON miroir_visages (lower(qui));
"""

_BASE = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
MODELES = {
    "detection": ("face_detection_yunet/face_detection_yunet_2023mar.onnx",
                  "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "empreinte": ("face_recognition_sface/face_recognition_sface_2021dec.onnx",
                  "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}
SEUIL = float(os.getenv("EVA_MIROIR_SEUIL", "0.42"))     # similarité cosinus SFace : ≥ 0,363 = même personne (on prend de la marge)
SCORE_VISAGE = 0.8                                       # confiance minimale de la détection
TAILLE_MIN = 40                                          # pixels : visage trop petit (loin) ignoré
PHOTOS_MIN = 3

_dossier: Path | None = None
_detecteur = None
_reconnaisseur = None
_telechargement: dict = {"en_cours": False, "erreur": ""}
_empreintes: dict[str, list] = {}                        # qui → [vecteurs normalisés], rechargé à chaque changement


class MiroirError(ValueError):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


def lier(workspace: Path) -> None:
    global _dossier
    _dossier = Path(workspace) / ".modeles" / "visages"


def _chemin(cle: str) -> Path:
    return (_dossier or Path("/tmp/eva-visages")) / Path(MODELES[cle][0]).name


def prets() -> bool:
    return all(_chemin(k).is_file() for k in MODELES)


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


async def telecharger() -> None:
    """Télécharge les deux modèles (une fois). Un fichier dont l'empreinte ne correspond pas est refusé."""
    import httpx
    if _telechargement["en_cours"]:
        return
    _telechargement.update(en_cours=True, erreur="")
    try:
        for cle, (chemin, sha) in MODELES.items():
            cible = _chemin(cle)
            if cible.is_file() and await asyncio.to_thread(_sha, cible) == sha:
                continue
            cible.parent.mkdir(parents=True, exist_ok=True)
            tmp = cible.with_suffix(".part")
            async with httpx.AsyncClient(timeout=300, follow_redirects=True) as c:
                async with c.stream("GET", _BASE + chemin) as r:
                    r.raise_for_status()
                    with tmp.open("wb") as f:
                        async for bloc in r.aiter_bytes(1 << 16):
                            f.write(bloc)
            if await asyncio.to_thread(_sha, tmp) != sha:
                tmp.unlink(missing_ok=True)
                raise MiroirError(f"Modèle {cle} abîmé (empreinte inattendue) : réessaie.")
            tmp.replace(cible)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Modèles du miroir non téléchargés : %s", exc)
        _telechargement["erreur"] = str(exc)[:300]
    finally:
        _telechargement["en_cours"] = False


def _charger_modeles():
    global _detecteur, _reconnaisseur
    import cv2
    if _detecteur is None:
        _detecteur = cv2.FaceDetectorYN.create(str(_chemin("detection")), "", (320, 320), SCORE_VISAGE, 0.3, 20)
        _reconnaisseur = cv2.FaceRecognizerSF.create(str(_chemin("empreinte")), "")
    return _detecteur, _reconnaisseur


def _image(b64: str):
    import cv2
    import numpy as np
    if "," in b64[:80]:
        b64 = b64.split(",", 1)[1]
    try:
        brut = base64.b64decode(b64, validate=False)
    except ValueError as exc:
        raise MiroirError("Image illisible.") from exc
    if len(brut) > 3_000_000:
        raise MiroirError("Image trop grande (3 Mo maximum).")
    img = cv2.imdecode(np.frombuffer(brut, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise MiroirError("Image illisible.")
    h, w = img.shape[:2]
    if max(h, w) > 640:                                  # la détection n'a pas besoin de plus
        f = 640 / max(h, w)
        img = cv2.resize(img, (int(w * f), int(h * f)))
    return img


def _visages(img) -> list:
    det, _ = _charger_modeles()
    h, w = img.shape[:2]
    det.setInputSize((w, h))
    _, faces = det.detect(img)
    if faces is None:
        return []
    return [f for f in faces if f[2] >= TAILLE_MIN and f[3] >= TAILLE_MIN]


def _empreinte(img, face):
    import numpy as np
    _, rec = _charger_modeles()
    v = rec.feature(rec.alignCrop(img, face)).flatten().astype(np.float32)
    return v / (np.linalg.norm(v) or 1.0)


def analyser(b64: str) -> list:
    """Empreintes de tous les visages de l'image (bloquant : à lancer dans un thread)."""
    if not prets():
        raise MiroirError("Les modèles de reconnaissance ne sont pas encore téléchargés (Maison › Miroir).", 409)
    img = _image(b64)
    return [_empreinte(img, f) for f in _visages(img)]


async def recharger() -> None:
    import numpy as np
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT qui, emb FROM miroir_visages")
    d: dict[str, list] = {}
    for r in rows:
        d.setdefault(r["qui"], []).append(np.frombuffer(r["emb"], dtype=np.float32))
    _empreintes.clear()
    _empreintes.update(d)


def identifier(empreintes: list) -> dict:
    """Pour chaque visage : la personne la plus ressemblante au-dessus du seuil, sinon inconnu."""
    import numpy as np
    personnes, inconnus = [], 0
    for v in empreintes:
        meilleur, score = None, -1.0
        for qui, liste in _empreintes.items():
            s = float(max(np.dot(v, e) for e in liste))
            if s > score:
                meilleur, score = qui, s
        if meilleur and score >= SEUIL and meilleur not in [p["qui"] for p in personnes]:
            personnes.append({"qui": meilleur, "score": round(score, 3)})
        else:
            inconnus += 1
    return {"visages": len(empreintes), "personnes": personnes, "inconnus": inconnus,
            "discret": len(empreintes) > 1 or inconnus > 0}


async def regarder(b64: str) -> dict:
    return identifier(await asyncio.to_thread(analyser, b64))


async def apprendre(qui: str, images: list[str]) -> dict:
    """Enregistre le visage de `qui` à partir de quelques photos (un seul visage par photo, le plus grand)."""
    qui = (qui or "").strip()
    if not qui:
        raise MiroirError("Pour qui ?")
    vecteurs = []
    for b64 in (images or [])[:10]:
        img = await asyncio.to_thread(_image, b64)
        faces = await asyncio.to_thread(_visages, img)
        if len(faces) != 1:
            continue                                        # personne ou plusieurs visages : photo ignorée
        vecteurs.append(await asyncio.to_thread(_empreinte, img, faces[0]))
    if len(vecteurs) < PHOTOS_MIN:
        raise MiroirError(f"Visage vu sur {len(vecteurs)} photo(s) seulement : mets-toi seul(e) face à la caméra, bien éclairé(e), et recommence.")
    async with get_pool().acquire() as conn:
        for v in vecteurs:
            await conn.execute("INSERT INTO miroir_visages (qui, emb) VALUES ($1, $2)", qui, v.tobytes())
    await recharger()
    return {"qui": qui, "photos": len(vecteurs), "total": len(_empreintes.get(qui, []))}


async def oublier(qui: str) -> int:
    async with get_pool().acquire() as conn:
        n = await conn.fetchval("WITH d AS (DELETE FROM miroir_visages WHERE lower(qui)=lower($1) RETURNING 1) SELECT count(*) FROM d", qui)
    await recharger()
    return n


async def etat() -> dict:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT qui, count(*) AS n, max(cree) AS maj FROM miroir_visages GROUP BY qui ORDER BY qui")
    return {"modeles_prets": prets(), "telechargement": dict(_telechargement), "taille_mo": 39,
            "personnes": [{"qui": r["qui"], "photos": r["n"], "maj": r["maj"].isoformat()} for r in rows]}


async def cartes(qui: str | None, role: str) -> dict:
    """Tuiles du miroir : celles de la personne reconnue (mêmes que le tableau du satellite), sinon la météo seule."""
    from . import tableau
    if qui:
        return await tableau.composer(f"miroir:{qui.lower()}", role, qui)
    m = await tableau._meteo()
    return {"tuiles": [m] if m else []}
