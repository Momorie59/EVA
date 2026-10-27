"""Rend les arguments d'outil écrits par le modèle conformes au schéma de l'outil.

Les petits modèles locaux se trompent souvent : mauvais nom de paramètre (« q » au lieu de « query »), nombre écrit entre guillemets,
paramètre oublié. On corrige ce qui est évident, et sinon on renvoie une erreur précise que le modèle peut utiliser pour réessayer
(au lieu de « missing 1 required positional argument »)."""
import json
from typing import Any

_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}


def _coerce(value: Any, typ: str | None) -> Any:
    if typ == "string":
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
    elif typ in ("integer", "number") and isinstance(value, str):
        try:
            f = float(value.strip().replace(",", "."))
            return int(f) if typ == "integer" or f.is_integer() else f
        except ValueError:
            return value
    elif typ == "integer" and isinstance(value, float) and value.is_integer():
        return int(value)
    elif typ == "boolean" and isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "vrai", "oui", "1"):
            return True
        if low in ("false", "faux", "non", "0"):
            return False
    elif typ in ("array", "object") and isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, _TYPES[typ]):
                return parsed
        except json.JSONDecodeError:
            if typ == "array" and value.strip():
                return [x.strip() for x in value.split(",") if x.strip()]
    elif typ == "array" and not isinstance(value, list) and value is not None:
        return [value]
    return value


def normalize(schema: dict, args: Any) -> tuple[dict, str | None]:
    """Retourne (arguments corrigés, message d'erreur ou None)."""
    if not isinstance(args, dict):
        args = {}
    props: dict = (schema or {}).get("properties", {}) or {}
    required: list = list((schema or {}).get("required", []) or [])
    out = {k: v for k, v in args.items() if v is not None}
    unknown = [k for k in out if k not in props]
    missing = [r for r in required if r not in out]
    # un seul paramètre manque et un seul est inconnu : le modèle s'est trompé de nom (q, search, text…)
    if len(missing) == 1 and unknown:
        want = props.get(missing[0], {}).get("type")
        pick = next((u for u in unknown if want and isinstance(out[u], _TYPES.get(want, object))), unknown[0] if len(unknown) == 1 else None)
        if pick is not None:
            out[missing[0]] = out.pop(pick)
            missing = []
    for k in list(out):
        if k not in props:
            out.pop(k)                    # paramètre inventé : on l'ignore
        else:
            out[k] = _coerce(out[k], props[k].get("type"))
    missing = [r for r in required if r not in out or out[r] in ("", None)]
    if missing:
        expected = ", ".join(f"{k} ({v.get('type', 'texte')}{', obligatoire' if k in required else ''})" for k, v in props.items())
        return out, f"Paramètre obligatoire manquant ou vide : {', '.join(missing)}. Paramètres attendus : {expected}."
    for k, v in out.items():
        t = props[k].get("type")
        if t in _TYPES and not isinstance(v, _TYPES[t]) or (t == "integer" and isinstance(v, bool)):
            return out, f"Paramètre « {k} » invalide : attendu {t}, reçu {type(v).__name__}."
    return out, None
