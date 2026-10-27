"""Journal d'activité d'EVA (page Journal) : ce qu'elle a fait, conversations comprises, et ce qu'elle fait seule
(apprentissage, évolution de son code, tâches en fond, routines, satellites, redémarrages).

Deux sources fusionnées par date : la table `journal` (événements notés avec `noter`) et les outils utilisés
pendant les conversations (table `traces`, déjà enregistrée à chaque tour)."""
import json
import logging

from .db import get_pool

logger = logging.getLogger("eva-core.journal")

SCHEMA = """
CREATE TABLE IF NOT EXISTS journal (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    genre TEXT NOT NULL,
    texte TEXT NOT NULL,
    qui TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS journal_ts ON journal (ts DESC);
"""

GENRES = {"apprentissage", "evolution", "tache", "routine", "satellite", "systeme", "outil", "erreur"}


async def noter(genre: str, texte: str, qui: str = "") -> None:
    """Ajoute une ligne au journal. Ne lève jamais (le journal ne doit rien casser)."""
    try:
        async with get_pool().acquire() as conn:
            await conn.execute("INSERT INTO journal (genre, texte, qui) VALUES ($1,$2,$3)",
                               genre if genre in GENRES else "systeme", (texte or "")[:600], (qui or "")[:60])
            await conn.execute("DELETE FROM journal WHERE ts < now() - interval '60 days'")
    except Exception:  # noqa: BLE001
        logger.debug("Journal : ligne non notée", exc_info=True)


def _resume_args(args) -> str:
    if not isinstance(args, dict):
        return ""
    morceaux = [f"{k}={str(v)[:40]}" for k, v in list(args.items())[:3] if v not in (None, "", [], {})]
    return ", ".join(morceaux)


async def lister(limite: int = 200, genre: str = "") -> list[dict]:
    limite = max(10, min(1000, limite))
    async with get_pool().acquire() as conn:
        lignes = [{"ts": r["ts"].isoformat(), "genre": r["genre"], "texte": r["texte"], "qui": r["qui"]}
                  for r in await conn.fetch("SELECT ts, genre, texte, qui FROM journal ORDER BY ts DESC LIMIT $1", limite)]
        if genre in ("", "outil", "erreur"):
            traces = await conn.fetch("SELECT started_at, kind, label, steps, ok, error FROM traces ORDER BY started_at DESC LIMIT $1", limite)
            for t in traces:
                steps = t["steps"] if isinstance(t["steps"], list) else json.loads(t["steps"] or "[]")
                demande = (t["label"] or "")[:80]
                for s in steps:
                    if s.get("type") != "tool":
                        continue
                    a = _resume_args(s.get("args"))
                    lignes.append({"ts": t["started_at"].isoformat(), "genre": "outil" if s.get("ok", True) else "erreur",
                                   "texte": f"{s.get('name')}({a})" + ("" if s.get("ok", True) else f" — échec : {str(s.get('result'))[:120]}")
                                   + (f" · pour « {demande} »" if demande else ""), "qui": t["kind"]})
                if not t["ok"] and t["error"]:
                    lignes.append({"ts": t["started_at"].isoformat(), "genre": "erreur", "texte": f"Réponse interrompue : {t['error'][:200]}",
                                   "qui": t["kind"]})
    if genre:
        lignes = [x for x in lignes if x["genre"] == genre]
    lignes.sort(key=lambda x: x["ts"], reverse=True)
    return lignes[:limite]


async def noter_demarrage() -> None:
    """Au démarrage : quel code tourne, et ce qui est arrivé aux modifications d'EVA lors d'une mise à jour."""
    import os
    from pathlib import Path
    mode = os.getenv("EVA_CODE_MODE", "")
    await noter("systeme", "EVA a démarré" + {"live": " (avec ses propres modifications)", "base": " (code d'origine)"}.get(mode, ""))
    f = Path(os.getenv("EVA_SELF_DIR", "/eva-self")) / "obsolete.json"
    try:
        info = json.loads(f.read_text())
    except (OSError, ValueError):
        return
    if info.get("journal"):
        return
    morceaux = []
    if info.get("reportees"):
        morceaux.append(f"{len(info['reportees'])} modification(s) d'EVA reportée(s) sur la nouvelle version")
    if info.get("laissees"):
        morceaux.append("laissées de côté (ne s'appliquent plus) : " + ", ".join(info["laissees"][:5]))
    await noter("evolution", "Mise à jour d'EVA installée" + (" : " + " ; ".join(morceaux) if morceaux else ""))
    try:
        f.write_text(json.dumps({**info, "journal": True}))
    except OSError:
        pass
