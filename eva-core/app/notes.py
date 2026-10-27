"""Post-it : pense-bêtes affichés à l'écran, créés par l'utilisateur ou par EVA (outils ou commande vocale)."""
import json
import logging
import re
import unicodedata

from .connections import connection_manager
from .db import get_pool
from .profiles import user_var

logger = logging.getLogger("eva-core.notes")

COLORS = ("jaune", "rose", "rouge", "bleu", "vert", "orange", "violet")
_COLOR_WORDS = {"jaune": "jaune", "rose": "rose", "bleu": "bleu", "bleue": "bleu", "vert": "vert", "verte": "vert",
                "orange": "orange", "violet": "violet", "violette": "violet", "mauve": "violet", "rouge": "rouge"}
MAX_TEXT = 600
MAX_NOTES = 60


def normalize_color(value: str | None) -> str:
    return _COLOR_WORDS.get((value or "").strip().lower(), "jaune")


def _me() -> str:
    return (user_var.get() or "").lower()


# Visible : à moi, partagé avec moi (ou avec tous), ou ancien post-it sans propriétaire. Sans connexion (me == "") : tout.
_VISIBLE = "($1 = '' OR owner IS NULL OR lower(owner) = $1 OR shared ? $1 OR shared ? '*')"


def _can_see(r, me: str) -> bool:
    shared = r["shared"] if isinstance(r["shared"], list) else json.loads(r["shared"] or "[]")
    low = [str(s).lower() for s in shared]
    return not me or r["owner"] is None or r["owner"].lower() == me or me in low or "*" in low


def _row(r) -> dict:
    me = _me()
    shared = r["shared"] if isinstance(r["shared"], list) else json.loads(r["shared"] or "[]")
    return {"owner": r["owner"], "shared": shared, "mine": (not me) or r["owner"] is None or r["owner"].lower() == me,"id": r["id"], "text": r["text"], "color": r["color"], "x": r["x"], "y": r["y"], "done": r["done"],
            "done_at": r["done_at"].isoformat() if r["done_at"] else None,
            "created_by": r["created_by"], "created_at": r["created_at"].isoformat(), "updated_at": r["updated_at"].isoformat()}


async def _changed() -> None:
    try:
        await connection_manager.broadcast_all({"type": "notes_changed"})
    except Exception:  # noqa: BLE001 — l'affichage se rafraîchit aussi tout seul, jamais bloquant
        logger.warning("Diffusion notes_changed en échec", exc_info=True)


async def list_notes(include_done: bool = True) -> list[dict]:
    """Tous les post-it (les validés forment la « corbeille » avec leur date de traitement) ; include_done=False : ceux à l'écran."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT * FROM notes WHERE " + _VISIBLE + ("" if include_done else " AND NOT done") + " ORDER BY id", _me())
    return [_row(r) for r in rows]


async def create(text: str, color: str | None = None, x: float | None = None, y: float | None = None, by: str = "user") -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("Le post-it est vide.")
    text = text[:MAX_TEXT]
    async with get_pool().acquire() as conn:
        n = await conn.fetchval("SELECT count(*) FROM notes WHERE NOT done AND " + _VISIBLE, _me())
        if n >= MAX_NOTES:
            raise ValueError(f"Trop de post-it ({MAX_NOTES} maximum) : supprime ou termine d'abord les anciens.")
        # Grille décalée (4 colonnes, 2 rangées) : les nouveaux post-it ne se chevauchent pas.
        slot = n % 8
        if x is None:
            x = 0.20 + (slot % 4) * 0.125
        if y is None:
            y = 0.14 + (slot // 4) * 0.24 + (slot % 2) * 0.035
        row = await conn.fetchrow(
            "INSERT INTO notes (text, color, x, y, created_by, owner) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *",
            text, normalize_color(color), min(max(float(x), 0.0), 0.95), min(max(float(y), 0.0), 0.9), by, user_var.get() or None)
    await _changed()
    return _row(row)


async def update(note_id: int, **fields) -> dict | None:
    sets, vals = [], []
    me = _me()
    async with get_pool().acquire() as conn:
        cur = await conn.fetchrow("SELECT * FROM notes WHERE id=$1", note_id)
    if cur is None or not _can_see(cur, me):
        return None
    mine = (not me) or cur["owner"] is None or cur["owner"].lower() == me
    if fields.get("shared") is not None:
        if not mine:
            raise ValueError("Seule la personne qui a collé ce post-it peut changer son partage.")
        names = sorted({str(s).strip() for s in fields["shared"] if str(s).strip()})[:50]
        vals.append(json.dumps(["*"] if "*" in names else names))
        sets.append(f"shared=${len(vals)}::jsonb")
    for key in ("text", "color", "x", "y", "done"):
        if key not in fields or fields[key] is None:
            continue
        v = fields[key]
        if key == "text":
            v = str(v).strip()[:MAX_TEXT]
            if not v:
                raise ValueError("Le post-it est vide.")
        elif key == "color":
            v = normalize_color(v)
        elif key in ("x", "y"):
            v = min(max(float(v), 0.0), 0.95)
        else:
            v = bool(v)
        vals.append(v)
        sets.append(f"{key}=${len(vals)}")
        if key == "done":  # date de traitement : posée à la validation, retirée à la restauration
            sets.append("done_at=now()" if v else "done_at=NULL")
    if not sets:
        return None
    vals.append(note_id)
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(f"UPDATE notes SET {', '.join(sets)}, updated_at=now() WHERE id=${len(vals)} RETURNING *", *vals)
    if row:
        await _changed()
    return _row(row) if row else None


async def delete(note_id: int) -> bool:
    async with get_pool().acquire() as conn:
        res = await conn.execute("DELETE FROM notes WHERE id=$1 AND ($2 = '' OR owner IS NULL OR lower(owner) = $2)", note_id, _me())
    ok = res.endswith("1")
    if ok:
        await _changed()
    return ok


async def clear(done_only: bool = False) -> int:
    """done_only=True : vide la corbeille (suppression définitive). Sinon : range tous les post-it à l'écran dans la corbeille."""
    async with get_pool().acquire() as conn:
        mine = "($1 = '' OR owner IS NULL OR lower(owner) = $1)"          # on ne vide jamais les post-it des autres
        res = await conn.execute(f"DELETE FROM notes WHERE done AND {mine}" if done_only
                                 else f"UPDATE notes SET done=TRUE, done_at=now(), updated_at=now() WHERE NOT done AND {mine}", _me())
    n = int(res.split()[-1])
    if n:
        await _changed()
    return n


# --- Commandes vocales / écrites : « mets un post-it rouge : appeler Paul » -------------------------------------------

def _fold_keep(s: str) -> str:
    """Minuscules sans accents, apostrophes et tirets en espaces — MÊME longueur que l'original (pour retrouver le texte)."""
    out = []
    for ch in s:
        d = "".join(c for c in unicodedata.normalize("NFD", ch.lower()) if unicodedata.category(c) != "Mn")
        out.append(d if len(d) == 1 else (ch.lower() if len(d) != 1 else d))
    return "".join(out).replace("'", " ").replace("’", " ").replace("-", " ")


_NOTE = r"(?:poste? ?h?it(?:es?|s)?|pense ?betes?)"   # tolère les variantes de transcription vocale (« poste it », « post hit », « postite »…)
_VERB_CREATE = (r"(?:mets|met|mettre|ajoute|ajouter|cree|creer|fais|fait|faire|colle|coller|pose|poser|ecris|ecrire|note|noter|"
                r"rajoute|rajouter|genere|generer|rappelle|rappeler|inscris|inscrire|garde|prepare)")
_CREATE = re.compile(r"\b" + _VERB_CREATE + r"\b[^.:!?\n]{0,30}?\b" + _NOTE + r"\b")
_CREATE2 = re.compile(r"^\s*(?:eva[ ,]*)?(?:(?:je veux|je voudrais|j ai besoin d|il me faut)\s+)?(?:(?:un|une)\s+)?" + _NOTE + r"\b")
_CLEAR = re.compile(r"\b(?:efface|effacer|supprime|supprimer|enleve|enlever|retire|retirer|vide|vider|nettoie|nettoyer|jette|jeter)\b[^.:!?\n]{0,25}?\b" + _NOTE + r"\b")
_HIDE = re.compile(r"\b(?:cache|cacher|masque|masquer|ferme|fermer)\b[^.:!?\n]{0,15}?\b" + _NOTE + r"\b")
_SHOW = re.compile(r"\b(?:montre|montrer|affiche|afficher|ouvre|ouvrir|remets?|reaffiche)\b[^.:!?\n]{0,15}?\b" + _NOTE + r"\b")
_LIST = re.compile(r"\b(?:lis|lire|liste|quels?|quelles?|qu est ce que j ai|c est quoi|j ai quoi|il y a quoi|combien)\b[^.:!?\n]{0,25}?\b" + _NOTE + r"\b")
_COLOR_RE = re.compile(r"\b(jaune|rose|bleue?|verte?|orange|violette?|mauve|rouge)\b")
_LEAD = re.compile(r"^[\s,:;.\-–]*(?:(?:de |d |pour |que |qui dit |avec |sur |disant |ecrit |ecrire |moi |mon |ma |:)\s*)*", re.I)


def detect(text: str) -> dict | None:
    """Reconnaît une commande de post-it. Retourne {"action": create|clear_all|clear_done|show|hide|list, ...} ou None."""
    folded = _fold_keep(text)
    if len(folded) != len(text):  # sécurité : on ne tente rien si l'alignement a été perdu
        return None
    if re.search(r"\b(?:vide|vider|nettoie|nettoyer)\b[^.:!?\n]{0,15}?\bcorbeille\b", folded) and re.search(r"\b(?:post|pense|corbeille)", folded):
        return {"action": "clear_done"}
    if _CLEAR.search(folded):
        done_only = bool(re.search(r"\b(fait|faits|faite|faites|termine|termines|finis|coches?)\b", folded))
        if done_only:
            return {"action": "clear_done"}
        if re.search(r"\b(tous|toutes|tout|les post|mes post|des post|ces post)\b", folded) or re.search(r"\b(post ?its?)\b\s*$", folded):
            return {"action": "clear_all"}
        return None
    if _HIDE.search(folded):
        return {"action": "hide"}
    if _SHOW.search(folded):
        return {"action": "show"}
    if _LIST.search(folded):
        return {"action": "list"}
    m = _CREATE.search(folded) or _CREATE2.search(folded)
    if not m:
        return None
    rest_f, rest = folded[m.end():], text[m.end():]
    color = None
    cm = _COLOR_RE.match(rest_f.strip())
    head = re.match(r"\s*(?:en |de couleur |couleur )?(jaune|rose|bleue?|verte?|orange|violette?|mauve|rouge)\b", rest_f)
    if head:
        color = head.group(1)
        rest_f, rest = rest_f[head.end():], rest[head.end():]
    elif cm:
        color = cm.group(1)
    lead = _LEAD.match(rest_f)
    body = rest[lead.end():].strip(" \t\n\"'«»")
    if color is None:  # « … en rouge » à la fin
        tail = re.search(r"\ben (jaune|rose|bleue?|verte?|orange|violette?|mauve|rouge)\s*[.!]*\s*$", rest_f)
        if tail:
            color = tail.group(1)
            body = text[m.end() + lead.end(): m.end() + tail.start()].strip(" \t\n\"'«»,;.")
    body = body.strip()
    if not body:
        return {"action": "ask"}   # « mets un post-it » sans contenu : EVA demande quoi écrire
    return {"action": "create", "text": body[:MAX_TEXT], "color": normalize_color(color)}
