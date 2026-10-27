"""Apprentissage local : avis sur les réponses, statistiques par modèle/outil/skill,
suggestions d'amélioration, et proposition de révision d'un skill à partir de l'historique.

Rien n'est appliqué automatiquement : EVA propose, l'utilisateur valide."""
import json
from pathlib import Path

from . import router as model_router
from . import skills as skills_mod
from .config import settings
from .db import get_pool
from .ollama_client import OllamaError, chat_once

MIN_USES_FOR_OPTIMIZE = 3


async def set_feedback(message_id: int, rating: int, comment: str = "") -> bool:
    """rating 1 / -1 ; 0 retire l'avis. Retourne False si le message n'existe pas."""
    async with get_pool().acquire() as conn:
        msg = await conn.fetchrow("SELECT session_id, trace_id, role FROM messages WHERE id=$1", message_id)
        if not msg or msg["role"] != "assistant":
            return False
        if rating == 0:
            await conn.execute("DELETE FROM feedback WHERE message_id=$1", message_id)
            return True
        await conn.execute(
            """INSERT INTO feedback (message_id, session_id, trace_id, rating, comment)
               VALUES ($1,$2,$3,$4,$5)
               ON CONFLICT (message_id) DO UPDATE SET rating=$4, comment=$5, created_at=now()""",
            message_id, msg["session_id"], msg["trace_id"], rating, comment.strip()[:1000],
        )
    return True


def _steps(raw):
    return raw if isinstance(raw, list) else json.loads(raw)


async def report(days: int = 30) -> dict:
    async with get_pool().acquire() as conn:
        traces = await conn.fetch(
            """SELECT t.id, t.kind, t.label, t.model, t.duration_ms, t.prompt_tokens, t.completion_tokens,
                      t.steps, t.ok, f.rating
               FROM traces t LEFT JOIN feedback f ON f.trace_id = t.id
               WHERE t.started_at > now() - make_interval(days => $1)""", days)
        negatives = await conn.fetch(
            """SELECT f.message_id, f.comment, f.created_at, m.content AS reply, t.label, t.model, t.id AS trace_id
               FROM feedback f JOIN messages m ON m.id = f.message_id LEFT JOIN traces t ON t.id = f.trace_id
               WHERE f.rating = -1 ORDER BY f.created_at DESC LIMIT 10""")
        totals = await conn.fetchrow(
            "SELECT count(*) FILTER (WHERE rating=1) AS up, count(*) FILTER (WHERE rating=-1) AS down FROM feedback")
    models: dict[str, dict] = {}
    tools: dict[str, dict] = {}
    skills: dict[str, dict] = {}
    for t in traces:
        m = models.setdefault(t["model"], {"model": t["model"], "traces": 0, "ok": 0, "ms": 0, "tokens": 0, "up": 0, "down": 0})
        m["traces"] += 1; m["ok"] += 1 if t["ok"] else 0; m["ms"] += t["duration_ms"]
        m["tokens"] += t["prompt_tokens"] + t["completion_tokens"]
        m["up"] += 1 if t["rating"] == 1 else 0; m["down"] += 1 if t["rating"] == -1 else 0
        used_skills = set()
        for st in _steps(t["steps"]):
            if st.get("type") != "tool":
                continue
            e = tools.setdefault(st["name"], {"tool": st["name"], "calls": 0, "failures": 0})
            e["calls"] += 1; e["failures"] += 0 if st.get("ok", True) else 1
            if st["name"] == "skill_read" and isinstance(st.get("args"), dict) and st["args"].get("name"):
                used_skills.add(st["args"]["name"])
        for name in used_skills:
            k = skills.setdefault(name, {"skill": name, "uses": 0, "up": 0, "down": 0})
            k["uses"] += 1; k["up"] += 1 if t["rating"] == 1 else 0; k["down"] += 1 if t["rating"] == -1 else 0
    model_list = [{**m, "ok_rate": round(m["ok"] / m["traces"], 3), "avg_ms": int(m["ms"] / m["traces"])} for m in models.values()]
    tool_list = sorted(({**e, "failure_rate": round(e["failures"] / e["calls"], 3)} for e in tools.values()), key=lambda x: -x["calls"])
    skill_list = sorted(skills.values(), key=lambda x: -x["uses"])

    tips: list[str] = []
    for e in tool_list:
        if e["calls"] >= 5 and e["failure_rate"] >= 0.3:
            tips.append(f"L'outil « {e['tool']} » échoue souvent ({e['failures']}/{e['calls']}) : vérifie sa configuration ou précise-le dans un skill.")
    for m in model_list:
        if m["down"] >= 3 and m["down"] > m["up"]:
            tips.append(f"Le modèle « {m['model']} » reçoit plus d'avis négatifs que positifs ({m['down']} contre {m['up']}) : essaie un autre modèle pour cette catégorie dans Paramètres.")
        if m["traces"] >= 5 and m["ok_rate"] < 0.8:
            tips.append(f"Le modèle « {m['model']} » termine en erreur dans {round((1 - m['ok_rate']) * 100)} % des cas.")
    for k in skill_list:
        if k["down"] >= 2 and k["down"] > k["up"]:
            tips.append(f"Le skill « {k['skill']} » est associé à des avis négatifs : lance « Proposer une amélioration » dans la page Skills.")
    return {
        "days": days,
        "feedback": {"up": totals["up"], "down": totals["down"]},
        "models": sorted(model_list, key=lambda x: -x["traces"]),
        "tools": tool_list[:15],
        "skills": skill_list,
        "suggestions": tips,
        "recent_negative": [
            {"message_id": r["message_id"], "question": r["label"] or "", "reply": r["reply"][:500], "comment": r["comment"],
             "model": r["model"] or "", "trace_id": r["trace_id"], "at": r["created_at"].isoformat()}
            for r in negatives
        ],
    }


OPT_SYSTEM = (
    "Tu améliores des « skills » d'un assistant IA : des instructions en Markdown que l'assistant suit pour une tâche. "
    "Tu reçois le skill actuel et des exemples d'utilisation récents (demande, issue, avis de l'utilisateur). "
    "Propose une version améliorée : plus précise là où les exemples ont échoué ou déplu, sans changer l'objectif ni "
    "le nom. Réponds UNIQUEMENT par le fichier SKILL.md complet (en-tête --- name/description --- puis le corps), "
    "dans un bloc ```markdown, suivi d'une ligne « Justification : » en une ou deux phrases."
)


def _extract_proposal(text: str) -> tuple[str, str]:
    import re
    m = re.search(r"```(?:markdown|md)?\s*\n(.*?)\n```", text, re.S)
    raw = (m.group(1) if m else text).strip() + "\n"
    why = ""
    j = re.search(r"Justification\s*:\s*(.+)", text, re.S | re.I)
    if j:
        why = j.group(1).strip()[:600]
    return raw, why


async def optimize_skill(name: str, workspace: Path | None = None) -> dict:
    cur = skills_mod.get_skill(name, workspace)
    if not cur or not cur.get("valid"):
        raise skills_mod.SkillError("Skill introuvable ou invalide.")
    needle = json.dumps([{"type": "tool", "name": "skill_read", "args": {"name": name}}])
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """SELECT t.label, t.ok, t.steps, f.rating, f.comment, m.content AS reply
               FROM traces t LEFT JOIN feedback f ON f.trace_id = t.id
               LEFT JOIN messages m ON m.trace_id = t.id AND m.role='assistant'
               WHERE t.steps @> $1::jsonb ORDER BY t.id DESC LIMIT 12""", needle)
    if len(rows) < MIN_USES_FOR_OPTIMIZE:
        raise skills_mod.SkillError(
            f"Pas assez d'historique : {len(rows)} utilisation(s) enregistrée(s), il en faut au moins {MIN_USES_FOR_OPTIMIZE}."
        )
    examples = []
    for r in rows:
        verdict = {1: "👍 satisfait", -1: "👎 insatisfait"}.get(r["rating"], "pas d'avis")
        fails = [s["name"] for s in _steps(r["steps"]) if s.get("type") == "tool" and not s.get("ok", True)]
        examples.append(
            f"- Demande : {r['label'][:200]}\n  Issue : {'succès' if r['ok'] else 'erreur'}"
            + (f", outils en échec : {', '.join(fails)}" if fails else "")
            + f"\n  Avis : {verdict}" + (f" — {r['comment']}" if r["comment"] else "")
            + (f"\n  Réponse (extrait) : {(r['reply'] or '')[:300]}" if r["reply"] else "")
        )
    user = f"Skill actuel :\n```markdown\n{cur['raw']}\n```\n\nUtilisations récentes :\n" + "\n".join(examples)
    choice = await model_router.select(user)  # longue demande -> modèle de raisonnement s'il est réglé
    try:
        msg = await chat_once([{"role": "system", "content": OPT_SYSTEM}, {"role": "user", "content": user}], model=choice["model"])
    except OllamaError as exc:
        raise skills_mod.SkillError(str(exc)) from exc
    raw, why = _extract_proposal(msg.get("content", ""))
    try:
        parsed = skills_mod.parse_skill(raw)
    except skills_mod.SkillError as exc:
        raise skills_mod.SkillError(f"Le modèle n'a pas produit un SKILL.md valide ({exc}). Réessaie ou change de modèle.") from exc
    if parsed["name"] != name:
        raise skills_mod.SkillError("Le modèle a changé le nom du skill : proposition rejetée.")
    return {"name": name, "current": cur["raw"], "proposed": raw, "justification": why,
            "model": choice["model"], "examples": len(rows), "unchanged": raw.strip() == cur["raw"].strip()}
