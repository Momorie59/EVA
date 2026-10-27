from typing import Any

from ..permissions import Permission
from .base import Tool

MAX_SLIDES = 12


def _s(v: Any, n: int) -> str:
    return str(v).strip()[:n] if v is not None else ""


def _coerce_slides(slides: Any) -> Any:
    """Les petits modèles envoient souvent les diapos comme TEXTE JSON (parfois coupé) : on le relit, on le répare."""
    import json
    if isinstance(slides, dict):
        slides = slides.get("slides", [slides])
    if not isinstance(slides, str):
        return slides
    txt = slides.strip()
    for tail in ("", "]", "}]", "\"}]", "\"]}]"):
        try:
            data = json.loads(txt + tail)
        except ValueError:
            continue
        if isinstance(data, dict):
            data = data.get("slides", [data])
        if isinstance(data, list):
            return data
    # dernier recours : récupérer les objets {...} complets
    out, depth, start = [], 0, None
    for i, ch in enumerate(txt):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    out.append(json.loads(txt[start:i + 1]))
                except ValueError:
                    pass
    return out


def normalize_scene(title: Any, slides: Any) -> dict:
    """Valide et borne une présentation décrite par le modèle (on n'affiche jamais de HTML brut)."""
    out = []
    for raw in (lambda v: v if isinstance(v, list) else [])(_coerce_slides(slides))[:MAX_SLIDES]:
        if not isinstance(raw, dict):
            continue
        sl: dict = {"title": _s(raw.get("title"), 90), "subtitle": _s(raw.get("subtitle"), 160)}
        bullets = raw.get("bullets")
        if isinstance(bullets, list):
            sl["bullets"] = [_s(b, 220) for b in bullets[:8] if _s(b, 220)]
        tbl = raw.get("table")
        if isinstance(tbl, dict) and isinstance(tbl.get("headers"), list) and isinstance(tbl.get("rows"), list):
            heads = [_s(h, 40) for h in tbl["headers"][:7]]
            rows = [[_s(c, 80) for c in r[: len(heads)]] for r in tbl["rows"][:14] if isinstance(r, list)]
            sl["table"] = {"headers": heads, "rows": rows}
        stat = raw.get("stat")
        if isinstance(stat, dict) and stat.get("value") is not None:
            sl["stat"] = {"value": _s(stat.get("value"), 24), "label": _s(stat.get("label"), 60)}
        if raw.get("note"):
            sl["note"] = _s(raw.get("note"), 200)
        if raw.get("emoji"):
            sl["emoji"] = _s(raw.get("emoji"), 4)
        if any(sl.get(k) for k in ("title", "bullets", "table", "stat", "subtitle")):
            out.append(sl)
    return {"kind": "slides", "title": _s(title, 90) or "Présentation", "slides": out}


class PresentTool(Tool):
    name = "present"
    description = (
        "Affiche une présentation visuelle EN DIRECT dans l'interface (diaporama de cartes). À utiliser pour toute "
        "demande de présentation, diaporama, PowerPoint, résumé visuel, actualités, comparaison, plan ou tableau : "
        "l'utilisateur voit les diapositives à l'écran. Chaque diapo peut avoir un titre, des puces, un tableau, "
        "un chiffre clé. Après l'appel, ne recopie pas le contenu : dis juste une phrase."
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Titre de la présentation"},
            "slides": {
                "type": "array",
                "description": "Diapositives (12 max)",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "subtitle": {"type": "string"},
                        "emoji": {"type": "string", "description": "Un emoji illustrant la diapo"},
                        "bullets": {"type": "array", "items": {"type": "string"}},
                        "table": {
                            "type": "object",
                            "properties": {
                                "headers": {"type": "array", "items": {"type": "string"}},
                                "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                            },
                        },
                        "stat": {
                            "type": "object",
                            "properties": {"value": {"type": "string"}, "label": {"type": "string"}},
                        },
                        "note": {"type": "string"},
                    },
                },
            },
        },
        "required": ["title", "slides"],
    }
    permission = Permission.AUTO

    async def execute(self, title: str = "", slides: Any = None, **_: Any) -> dict:
        scene = normalize_scene(title, slides)
        if not scene["slides"]:
            return {"error": "Aucune diapositive valide : donne au moins une diapo avec un titre et des puces."}
        return {"displayed": True, "slides": len(scene["slides"]), "scene": scene}
