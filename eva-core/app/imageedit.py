"""Modifier une image qui existe déjà (photo jointe, image créée plus tôt, fichier de la galerie).
1. Comprendre la demande en français : retouches classiques (noir et blanc, recadrage… → imageops) et/ou modification par l'IA
   (transformer le style, retirer ou changer un détail → serveur d'images).
2. L'exécuter. Aucune permission d'un modèle de langage n'est demandée : le petit modèle ne sert qu'à traduire les mots en anglais."""
import asyncio
import re

from . import imageops, images
from .imageops import _f

IMG_WORD = re.compile(r"\b(?:images?|photos?|dessins?|illustrations?|portraits?|cliche|picture|selfie|capture)\b")
_IMG_ONLY = re.compile(r"^(?:images?|photos?|dessins?|illustrations?|portraits?|cliche|picture|selfie|capture|tout|ca|cela|elle|il|celle[- ]?ci|celui[- ]?ci)$")
_PRONOUN = re.compile(r"^(?:la|le|les|l'|ce|cet|cette|ces)$")
HOME = re.compile(r"\b(?:lumieres?|lampes?|ampoules?|volume|son|musique|radio|tele|tv|chauffage|clim\w*|temperature|thermostat|prises?|volets?|alarme|ventilateur|salon|cuisine|chambre|bureau|garage|jardin|scenes?)\b")
PRON = re.compile(r"\b(?:rends|rend|fais|mets|met|change|modifie|transforme|retouche|refais|corrige|redessine|passe|enleve|supprime|retire|efface)[ -](?:la|le|les)\b")
STRONG = {"crop", "rotate", "flip", "resize", "sepia", "gray", "text"}
_COLOR = re.compile(r"\b(?:rouge|bleu|bleue|vert|verte|jaune|orange|rose|violet|violette|noir|noire|blanc|blanche|gris|grise|marron|dore|doree|argente|turquoise|beige|bordeaux|fonce|clair)\b")
_STYLE = re.compile(r"\b(?:aquarelle|dessin|peinture|manga|anime|cartoon|bd|croquis|pixel|huile|crayon|pastel|style|sculpture|lego|bande dessinee|caricature|fusain|vitrail)\b")
_SCENE = re.compile(r"\b(?:nuit|jour|hiver|ete|automne|printemps|neige|pluie|coucher|lever|brouillard|soleil|ciel|orage|nuage\w*)\b")
_REAL = re.compile(r"\b(?:realiste|photorealiste|plus beau|plus belle|qualite|hd|detail\w*|net)\b")
_VERB_REMOVE = r"(?:enleve|enlever|supprime|supprimer|retire|retirer|efface|effacer|gomme|gommer|elimine|eliminer|fais disparaitre|fait disparaitre)"


def _clean_target(t: str) -> str:
    t = re.sub(r"\s+(?:et|puis|ensuite|mais)\s+.*$", "", t.strip())
    t = re.sub(r"\s+(?:de|sur|dans|a partir de|depuis|d')\s*(?:cette|la|l'|ma|mon|les|une?)?\s*(?:images?|photos?|dessins?|illustrations?|portraits?|cliche|picture|selfie)\b.*$", "", t)
    t = re.sub(r"^(?:(?:le|la|les|un|une|ce|cet|cette|ces|du|de la|des|mon|ma|mes)\s+|l')", "", t.strip())
    return t.strip(" .,;!?'")


def _target_ok(t: str) -> bool:
    return bool(t) and not _IMG_ONLY.match(t) and not _PRONOUN.match(t) and len(t) <= 60


def _strength(f: str) -> float:
    s = 0.7 if _STYLE.search(f) else 0.6 if _SCENE.search(f) else 0.4 if _REAL.search(f) else 0.55
    if re.search(r"\b(?:un peu|legerement|doucement)\b", f):
        s -= 0.15
    if re.search(r"\b(?:completement|totalement|compl[eè]tement|radicalement)\b", f):
        s += 0.2
    return round(max(0.25, min(s, 0.9)), 2)


def parse_ai(f: str) -> dict | None:
    """Modification par l'IA demandée dans le texte (déjà sans accents), ou None."""
    m = re.search(r"\b" + _VERB_REMOVE + r"\b\s+(?P<t>[^.;!?]+)", f)
    if m:
        t = _clean_target(m.group("t"))
        if _target_ok(t):
            return {"mode": "zone", "kind": "remove", "target": t, "what": ""}
    m = re.search(r"\bremplace\w*\s+(?P<t>.+?)\s+par\s+(?P<w>[^.;!?]+)", f)
    if m:
        t, w = _clean_target(m.group("t")), _clean_target(m.group("w"))
        if _target_ok(t) and w:
            return {"mode": "zone", "kind": "replace", "target": t, "what": w}
    m = re.search(r"\b(?:change\w*|mets|met|rends|rend|colorie\w*|peins|passe|transforme\w*)\s+(?:la couleur\s+(?:de |du |des |d')?)?(?P<t>[^.;!?]+?)\s+en\s+(?P<w>[^.;!?]+)", f)
    if m:
        t, w = _clean_target(m.group("t")), m.group("w").strip(" .,;!?'")
        if _target_ok(t) and w and not _STYLE.search(w) and not imageops.parse(w):
            return {"mode": "zone", "kind": "color" if _COLOR.search(w) else "replace", "target": t, "what": w}
    m = re.search(r"\bajoute\w*\s+(?P<w>[^.;!?]+)", f)
    if m and not re.search(r"[«\"“]", f):
        return {"mode": "transform", "kind": "add", "what": m.group("w").strip(), "strength": 0.5}
    m = re.search(r"\b(?:transforme\w*|convertis\w*|stylise\w*|redessine\w*|refais|repeins|rends|rend|fais|mets|met|passe|change\w*|modifie\w*|retouche\w*)\b(?P<r>[^.;!?]*)", f)
    if m:
        what = re.sub(r"\b(?:la|le|les|l'|cette|cet|ces|image|images|photo|photos|dessin|illustration|portrait|moi)\b", " ", m.group("r"))
        what = re.sub(r"(?<![a-z])(?:style|de|du|d|a|en|dans|au|avec)(?![a-z])", " ", what)
        what = re.sub(r"\s+", " ", what).strip(" .,;!?'-")
        if len(what) >= 3 and not re.match(r"(?:un|une|des)\b", what) and not imageops.parse(f):
            return {"mode": "transform", "kind": "style", "what": what, "strength": _strength(f)}
    return None


def plan(text: str, has_attachment: bool = False, have_recent: bool = False, fresh: bool = False) -> dict | None:
    """Demande de modification d'image ? → {"ops": [...], "ai": {...}|None} ; None si ce n'en est pas une.
    Pour ne pas confondre avec une conversation normale (« mets la lumière en bleu »), il faut une image en jeu : photo jointe, mot « image/photo… »,
    ou un « mets-la… » juste après une image créée."""
    f = _f(text)
    ops = imageops.parse(text)
    ai = parse_ai(f)
    if not ops and not ai:
        return None
    home = bool(HOME.search(f))
    img_word = bool(IMG_WORD.search(f))
    pron = fresh and bool(PRON.search(f)) and not home
    strong = have_recent and not home and any(o["op"] in STRONG for o in ops)
    if not (has_attachment or img_word or pron or strong):
        return None
    if ai and ai["mode"] == "zone" and not (has_attachment or have_recent or img_word):
        return None
    return {"ops": ops, "ai": ai}


_TGT_SYS = ("Translate the French noun phrase into a short English noun phrase (1 to 4 words) naming something visible in a photo. "
            "Answer with the English phrase only, nothing else.")
_RES_SYS = ("You help edit pictures with Stable Diffusion. The user wrote a French instruction describing a change to an existing picture. "
            "Write ONE English prompt (8 to 30 words) describing the DESIRED RESULT picture: style, colors, lighting, mood. "
            "Do not use words like transform or change. Answer with the prompt only.")


async def _noun(fr: str) -> str:
    return (await images.ask_small(_TGT_SYS, fr, 25)) or fr


async def build_ai(plan_ai: dict, text: str) -> dict:
    """Prépare les paramètres envoyés au serveur d'images (prompt et zone en anglais) + une phrase de résumé en français."""
    k = plan_ai["mode"], plan_ai["kind"]
    if k == ("zone", "remove"):
        tgt = await _noun(plan_ai["target"])
        return {"prompt": "empty background, seamless natural continuation of the surroundings, photo", "target": tgt, "strength": 1.0,
                "summary": f"« {plan_ai['target']} » retiré"}
    if k == ("zone", "replace"):
        tgt, what = await asyncio.gather(_noun(plan_ai["target"]), _noun(plan_ai["what"]))
        return {"prompt": f"{what}, photo, natural lighting, highly detailed", "target": tgt, "strength": 1.0,
                "summary": f"« {plan_ai['target']} » remplacé par {plan_ai['what']}"}
    if k == ("zone", "color"):
        tgt, what = await asyncio.gather(_noun(plan_ai["target"]), _noun(plan_ai["what"]))
        return {"prompt": f"{what} {tgt}, photo, natural lighting, highly detailed", "target": tgt, "strength": 0.95,
                "summary": f"{plan_ai['target']} en {plan_ai['what']}"}
    result = await images.ask_small(_RES_SYS, text, 40) or text
    return {"prompt": result, "target": "", "strength": plan_ai.get("strength", 0.55),
            "summary": ("ajout : " if plan_ai["kind"] == "add" else "transformée : ") + plan_ai["what"]}


async def run(png: bytes, pl: dict, text: str, cfg: dict | None = None) -> tuple[bytes, str]:
    """Exécute le plan sur l'image : IA d'abord, retouches classiques ensuite. Renvoie (PNG, résumé en français)."""
    cfg = cfg or await images.get_config()
    parts: list[str] = []
    cur = png
    if pl.get("ai"):
        if not cfg["url"]:
            raise images.ImageError(images.NOT_CONFIGURED)
        spec = await build_ai(pl["ai"], text)
        cur = await images.edit_remote(cur, spec["prompt"], cfg, target=spec["target"], strength=spec["strength"])
        parts.append(spec["summary"])
    if pl.get("ops"):
        try:
            cur = await asyncio.to_thread(imageops.apply, cur, pl["ops"])
        except imageops.OpsError as exc:
            raise images.ImageError(str(exc)) from exc
        parts.append(imageops.describe(pl["ops"]))
    return cur, ", ".join(parts)
