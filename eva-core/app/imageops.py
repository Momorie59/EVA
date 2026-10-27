"""Retouches classiques d'une image, sans IA et sans carte graphique : comprendre la demande en français (« mets-la en noir et blanc et
recadre-la en carré ») puis l'appliquer avec Pillow. Tout est local et instantané."""
import io
import re
import textwrap
import unicodedata

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


class OpsError(Exception):
    pass


def _f(text: str) -> str:
    """Minuscules sans accents (les signes utiles — % ° / : & — sont conservés)."""
    t = unicodedata.normalize("NFKD", (text or "").replace("°", " deg ")).encode("ascii", "ignore").decode().lower()
    return t.replace("’", "'")


def _amount(f: str, small: float, normal: float, big: float) -> float:
    if re.search(r"\b(beaucoup|tres|nettement|fortement|bien)\b", f):
        return big
    if re.search(r"\b(un peu|legerement|doucement|un poil|a peine)\b", f):
        return small
    return normal


_RATIOS = (("carre", (1, 1)), ("portrait", (3, 4)), ("paysage", (16, 9)), ("panoram", (21, 9)))


def parse(text: str) -> list[dict]:
    """Liste d'opérations demandées dans le texte (vide si aucune retouche classique n'est reconnue)."""
    f = _f(text)
    ops: list[dict] = []
    # --- géométrie
    if re.search(r"\b(?:recadr\w*|rogn\w*)\b", f):
        m = re.search(r"\b(\d{1,2})\s*(?:[:/x]|sur)\s*(\d{1,2})\b", f)
        ratio = (int(m.group(1)), int(m.group(2))) if m and int(m.group(1)) and int(m.group(2)) else next((r for k, r in _RATIOS if k in f), (1, 1))
        ops.append({"op": "crop", "ratio": ratio})
    if re.search(r"\b(?:pivot\w*|tourn\w*|rotation|rotate)\b", f) or re.search(r"\ba l'envers\b|\bdemi-tour\b", f):
        m = re.search(r"(-?\d{1,3})\s*deg", f)
        if re.search(r"\ba l'envers\b|\bdemi-tour\b|\b180\b", f):
            deg = 180
        elif m:
            deg = int(m.group(1))
        elif re.search(r"\bgauche\b|anti-?horaire", f):
            deg = -90
        else:
            deg = 90
        if re.search(r"\bgauche\b", f) and m and deg > 0:
            deg = -deg
        deg %= 360
        deg = deg - 360 if deg > 180 else deg
        if deg:
            ops.append({"op": "rotate", "deg": deg})
    if re.search(r"\b(?:miroir|symetri\w*)\b|retourn\w*\b.{0,25}\b(?:horizontalement|de gauche a droite)|inverse\w*\s+(?:gauche|droite)", f):
        ops.append({"op": "flip", "dir": "h"})
    elif re.search(r"retourn\w*\b.{0,25}\bverticalement|\btete en bas\b", f):
        ops.append({"op": "flip", "dir": "v"})
    if re.search(r"\b(?:redimension\w*|reduis\w*|reduire|retreci\w*|agrandi\w*|miniaturi\w*|rapetiss\w*|taille)\b", f):
        m = re.search(r"(\d{2,5})\s*(?:px|pixels?)", f)
        p = re.search(r"(\d{1,3})\s*%", f)
        if m:
            ops.append({"op": "resize", "width": int(m.group(1))})
        elif p:
            ops.append({"op": "resize", "percent": int(p.group(1))})
        elif re.search(r"\b(?:agrandi\w*)\b", f):
            ops.append({"op": "resize", "percent": 200})
        elif re.search(r"\b(?:reduis\w*|reduire|retreci\w*|miniaturi\w*|rapetiss\w*)\b", f):
            ops.append({"op": "resize", "percent": 50})
    # --- couleurs et lumière
    if re.search(r"\b(?:noir et blanc|noir & blanc|n&b|nb|niveaux? de gris|monochrome|en gris|grise?s?)\b", f):
        ops.append({"op": "gray"})
    if re.search(r"\bsepia\b", f):
        ops.append({"op": "sepia"})
    if re.search(r"\b(?:plus (?:lumineu\w+|clair\w*)|eclairci\w*|eclaircir|plus de lumiere|luminosite (?:plus )?(?:forte|elevee)|moins sombre)\b", f):
        ops.append({"op": "brightness", "f": 1 + _amount(f, 0.15, 0.3, 0.5)})
    elif re.search(r"\b(?:assombri\w*|plus sombre|plus fonce\w*|moins lumineu\w+|moins clair\w*|baisse la luminosite)\b", f):
        ops.append({"op": "brightness", "f": 1 - _amount(f, 0.12, 0.25, 0.4)})
    if re.search(r"\b(?:plus de contraste|plus contraste\w*|contraste (?:plus )?(?:fort|eleve|marque)|augmente le contraste)\b", f):
        ops.append({"op": "contrast", "f": 1 + _amount(f, 0.15, 0.3, 0.5)})
    elif re.search(r"\b(?:moins de contraste|contraste (?:plus )?(?:doux|faible)|baisse le contraste)\b", f):
        ops.append({"op": "contrast", "f": 1 - _amount(f, 0.12, 0.25, 0.4)})
    if re.search(r"\b(?:plus de couleurs?|plus colore\w*|plus vi[fv]\w*|couleurs? plus (?:vives?|intenses?|riches?)|satur\w+)\b", f) and not re.search(r"\bdesatur", f):
        ops.append({"op": "saturation", "f": 1 + _amount(f, 0.2, 0.4, 0.7)})
    elif re.search(r"\b(?:desatur\w*|moins de couleurs?|ternis\w*|couleurs? plus (?:douces?|pales?|ternes?)|pastel)\b", f):
        ops.append({"op": "saturation", "f": 1 - _amount(f, 0.2, 0.4, 0.6)})
    if re.search(r"\b(?:plus net\w*|nettete|affine\w*|accentue\w*|sharpen)\b", f):
        ops.append({"op": "sharpen"})
    if re.search(r"\b(?:flou\w*|floute\w*|adoucis\w*|blur)\b", f) and not re.search(r"\b(?:plus net\w*|moins flou|sans flou)\b", f):
        ops.append({"op": "blur", "r": _amount(f, 1.5, 3, 6)})
    # --- texte à écrire sur l'image (la citation est reprise telle qu'écrite, avec ses accents)
    m = re.search(r"(?:[eé]cris|inscris|ajoute|mets|met|rajoute|ins[eè]re|l[eé]gende)\b[^«\"“]{0,40}[«\"“]\s*(.+?)\s*[»\"”]", text or "", re.I)
    if m and m.group(1).strip():
        pos = "top" if re.search(r"\ben haut\b|\bau[- ]dessus\b", f) else "center" if re.search(r"\bau (?:milieu|centre)\b|\bcentre\b", f) else "bottom"
        ops.append({"op": "text", "text": m.group(1).strip()[:200], "pos": pos})
    # --- « améliore la photo » seul : retouche automatique douce
    if not ops and re.search(r"\b(?:ameliore\w*|retouche\w*|optimise\w*|corrige\w*)\b", f) and re.search(r"\b(?:photo|image|cliche|portrait)\b", f):
        ops.append({"op": "enhance"})
    return ops


def _font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                                          # très vieux Pillow : police fixe minuscule
        return ImageFont.load_default()


def _draw_text(img: Image.Image, text: str, pos: str) -> Image.Image:
    img = img.convert("RGB")
    w, h = img.size
    size = max(14, min(h // 9, w // 8))
    font = _font(size)
    d = ImageDraw.Draw(img)
    per_line = max(6, int(w / (size * 0.58)))
    lines = textwrap.wrap(text, per_line) or [text]
    line_h = int(size * 1.2)
    total = line_h * len(lines)
    y = int(h * 0.04) if pos == "top" else (h - total) // 2 if pos == "center" else h - total - int(h * 0.05)
    for ln in lines:
        tw = d.textlength(ln, font=font)
        d.text(((w - tw) / 2, y), ln, font=font, fill="white", stroke_width=max(1, size // 14), stroke_fill="black")
        y += line_h
    return img


ORDER = ("rotate", "flip", "crop", "resize", "enhance", "gray", "sepia", "brightness", "contrast", "saturation", "sharpen", "blur", "text")


def _crop(img: Image.Image, ratio: tuple[int, int]) -> Image.Image:
    rw, rh = ratio
    w, h = img.size
    if w * rh > h * rw:                                        # trop large : on coupe sur les côtés
        nw = h * rw // rh
        x = (w - nw) // 2
        return img.crop((x, 0, x + nw, h))
    nh = w * rh // rw
    y = (h - nh) // 2
    return img.crop((0, y, w, y + nh))


def apply(png: bytes | Image.Image, ops: list[dict], max_side: int = 4096) -> bytes:
    """Applique les opérations (dans un ordre fixe : géométrie, couleurs, texte) ; renvoie un PNG."""
    try:
        img = png if isinstance(png, Image.Image) else Image.open(io.BytesIO(png))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise OpsError("Image illisible.") from exc
    for op in sorted(ops, key=lambda o: ORDER.index(o["op"]) if o["op"] in ORDER else 99):
        k = op["op"]
        if k == "rotate":
            img = img.rotate(-op["deg"], expand=True, resample=Image.BICUBIC)       # deg > 0 = vers la droite (sens horaire)
        elif k == "flip":
            img = ImageOps.mirror(img) if op["dir"] == "h" else ImageOps.flip(img)
        elif k == "crop":
            img = _crop(img, tuple(op["ratio"]))
        elif k == "resize":
            w, h = img.size
            nw = int(op["width"]) if op.get("width") else int(w * op["percent"] / 100)
            nw = max(16, min(nw, max_side))
            img = img.resize((nw, max(16, int(h * nw / w))), Image.LANCZOS)
        elif k == "enhance":
            img = ImageOps.autocontrast(img, cutoff=1)
            img = ImageEnhance.Color(img).enhance(1.1)
            img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=3))
        elif k == "gray":
            img = ImageOps.grayscale(img).convert("RGB")
        elif k == "sepia":
            g = ImageOps.grayscale(img)
            img = ImageOps.colorize(g, black="#1a0f05", white="#f4e4c8", mid="#8a6a45")
        elif k == "brightness":
            img = ImageEnhance.Brightness(img).enhance(max(0.2, min(op["f"], 2.5)))
        elif k == "contrast":
            img = ImageEnhance.Contrast(img).enhance(max(0.2, min(op["f"], 2.5)))
        elif k == "saturation":
            img = ImageEnhance.Color(img).enhance(max(0.0, min(op["f"], 3.0)))
        elif k == "sharpen":
            img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=2))
        elif k == "blur":
            img = img.filter(ImageFilter.GaussianBlur(op.get("r", 3)))
        elif k == "text":
            img = _draw_text(img, op["text"], op.get("pos", "bottom"))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def describe(ops: list[dict]) -> str:
    """Résumé en français de ce qui a été fait."""
    out = []
    for op in sorted(ops, key=lambda o: ORDER.index(o["op"]) if o["op"] in ORDER else 99):
        k = op["op"]
        out.append({
            "rotate": lambda: "pivotée de %d°" % op["deg"] if abs(op["deg"]) != 180 else "retournée (180°)",
            "flip": lambda: "retournée en miroir" if op["dir"] == "h" else "retournée à l'envers",
            "crop": lambda: "recadrée en carré" if tuple(op["ratio"]) == (1, 1) else "recadrée en %d:%d" % tuple(op["ratio"]),
            "resize": lambda: "redimensionnée (%s)" % (f"{op['width']} px de large" if op.get("width") else f"{op['percent']} %"),
            "enhance": lambda: "retouchée automatiquement (contraste, couleurs, netteté)",
            "gray": lambda: "en noir et blanc", "sepia": lambda: "en sépia",
            "brightness": lambda: "plus lumineuse" if op["f"] > 1 else "plus sombre",
            "contrast": lambda: "plus contrastée" if op["f"] > 1 else "moins contrastée",
            "saturation": lambda: "aux couleurs plus vives" if op["f"] > 1 else "aux couleurs plus douces",
            "sharpen": lambda: "plus nette", "blur": lambda: "floutée",
            "text": lambda: f"avec le texte « {op['text']} »",
        }.get(k, lambda: k)())
    return ", ".join(out)
