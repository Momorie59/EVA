from pathlib import Path
from typing import Any

from ... import imageedit, images
from ..permissions import Permission
from .base import Tool


class ImageGenerateTool(Tool):
    name = "image_generate"
    description = ("Crée une image à partir d'une description (illustration, photo, logo, affiche…) sur le serveur d'images local et la range dans la galerie "
                   "(Paramètres › Génération d'images) et dans le dossier « generated » de l'espace de travail. Donne la description du sujet ; elle est traduite et enrichie automatiquement.")
    parameters = {"type": "object", "properties": {"prompt": {"type": "string", "description": "Ce qu'il faut dessiner"},
                                                  "enhance": {"type": "boolean", "description": "Traduire/enrichir la description (défaut : réglage du serveur)"}}, "required": ["prompt"]}
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.root = Path(workspace_root)

    async def execute(self, prompt: str = "", enhance: bool | None = None, **_: Any) -> dict:
        prompt = (prompt or "").strip()[:1000]
        if not prompt:
            return {"error": "Décris l'image à créer."}
        cfg = await images.get_config()
        if not cfg["url"]:
            return {"error": images.NOT_CONFIGURED}
        final = await images.enhance(prompt) if (cfg["enhance"] if enhance is None else enhance) else prompt
        try:
            png = await images.generate(final, cfg)
        except images.ImageError as exc:
            return {"error": str(exc)}
        p = images.save(png, self.root, prompt, final)
        return {"ok": True, "path": f"generated/{p.name}", "image": p.name, "prompt_used": final, "bytes": len(png)}


class ImageEditTool(Tool):
    name = "image_edit"
    description = ("Modifie une image existante : retouches classiques (noir et blanc, recadrage, rotation, luminosité, texte…) ou modification par l'IA "
                   "(changer le style, retirer ou remplacer un détail, changer une couleur). `image` = nom d'une image de la galerie (img-….png) ou chemin d'un fichier image "
                   "de l'espace de travail ; `instruction` = la demande en français. Le résultat est une NOUVELLE image dans la galerie (l'original n'est pas touché).")
    parameters = {"type": "object", "properties": {"image": {"type": "string", "description": "Nom img-….png ou chemin d'une image de l'espace de travail ; vide = la dernière image de la galerie"},
                                                  "instruction": {"type": "string", "description": "Ce qu'il faut changer, en français"}}, "required": ["instruction"]}
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.root = Path(workspace_root)

    def _source(self, image: str) -> bytes | None:
        image = (image or "").strip()
        if not image:
            got = images.latest(self.root, max_age=86400)
            return got[1] if got else None
        if images._NAME.match(Path(image).name):
            p = self.root / "generated" / Path(image).name
        else:
            p = (self.root / image).resolve()
            if self.root.resolve() not in p.parents:
                return None
        return p.read_bytes() if p.is_file() else None

    async def execute(self, instruction: str = "", image: str = "", **_: Any) -> dict:
        instruction = (instruction or "").strip()[:500]
        if not instruction:
            return {"error": "Dis ce qu'il faut changer sur l'image."}
        try:
            src = self._source(image)
        except OSError:
            src = None
        if not src:
            return {"error": "Image introuvable : donne le nom d'une image de la galerie ou un fichier image de l'espace de travail."}
        pl = imageedit.plan(instruction, has_attachment=True)
        if not pl:
            return {"error": "Je n'ai pas compris la modification demandée (ex. « mets en noir et blanc », « enlève le poteau », « transforme en aquarelle »)."}
        try:
            out, summary = await imageedit.run(src, pl, instruction)
        except images.ImageError as exc:
            return {"error": str(exc)}
        p = images.save(out, self.root, instruction, summary, kind="edit")
        return {"ok": True, "path": f"generated/{p.name}", "image": p.name, "summary": summary, "bytes": len(out)}


class VideoGenerateTool(Tool):
    name = "video_generate"
    description = ("EXPÉRIMENTAL : crée un très court clip animé (1 à 3 secondes) à partir d'une description, avec l'IA vidéo du serveur d'images. "
                   "Très lent sur une petite carte graphique (plusieurs minutes) : ne l'utilise que si la personne demande clairement une vidéo ou une animation. "
                   "Le clip est rangé dans le dossier « generated » de l'espace de travail.")
    parameters = {"type": "object", "properties": {"prompt": {"type": "string", "description": "Ce qui doit bouger, en anglais de préférence"},
                                                  "frames": {"type": "integer", "description": "Nombre d'images (9 à 49, défaut 25 ≈ 2 s)"}}, "required": ["prompt"]}
    permission = Permission.CONFIRM          # long et gourmand : on demande toujours

    def __init__(self, workspace_root: Path):
        self.root = Path(workspace_root)

    async def execute(self, prompt: str = "", frames: int = 25, **_: Any) -> dict:
        import base64
        import time

        import httpx
        prompt = (prompt or "").strip()[:1000]
        if not prompt:
            return {"error": "Décris la scène à animer."}
        cfg = await images.get_config()
        if not cfg["url"]:
            return {"error": images.NOT_CONFIGURED}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(1800.0, connect=10.0), headers=images._headers(cfg)) as c:
                r = await c.post(f"{cfg['url']}/eva/video", json={"prompt": prompt, "frames": int(frames or 25)})
        except httpx.HTTPError as exc:
            return {"error": f"Serveur d'images injoignable ({type(exc).__name__})."}
        if r.status_code != 200:
            try:
                detail = r.json().get("detail") or r.text
            except ValueError:
                detail = r.text
            return {"error": str(detail)[:400] if r.status_code != 404 else "Ce serveur d'images ne sait pas faire de vidéo : mets-le à jour (IMAGES.md) puis relance install-imagegen.sh --video."}
        data = r.json()
        d = self.root / "generated"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"clip-{int(time.time() * 1000)}.webp"
        p.write_bytes(base64.b64decode(data["webp_b64"]))
        return {"ok": True, "path": f"generated/{p.name}", "seconds": data.get("seconds"), "took_s": data.get("took_s"), "prompt_used": prompt}
