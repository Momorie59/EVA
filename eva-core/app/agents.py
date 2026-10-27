"""Agents : tâches autonomes à la demande ou planifiées, avec historique.

Un agent = une instruction + un calendrier. À l'exécution, EVA fait tourner
le même Harness que pour une conversation, mais SANS humain pour confirmer :
tout outil qui demande une confirmation est refusé automatiquement. Seules
les actions sans risque (permission AUTO) peuvent donc s'exécuter.
"""
import asyncio
import contextvars
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

from . import cron
from .config import settings
from .connections import connection_manager
from .db import get_pool
from .harness.loop import run_harness
from . import router as model_router
from .harness.registry import ToolRegistry
from .harness.tools import delegate as delegate_tool, roles as roles_tool
from .memory import save_message
from .sessions import ensure_session
from . import skills as skills_mod
from .traces import TraceRecorder

logger = logging.getLogger("eva-core.agents")

MAX_OUTPUT_CHARS = 20000

TEMPLATES: dict[str, dict] = {
    "morning_digest": {
        "name": "Briefing du matin",
        "description": "Météo, état du serveur et 3 actualités, résumés en quelques points.",
        "needs_instruction": False,
        "schedule_type": "cron",
        "schedule_value": "0 7 * * *",
        "prompt": (
            "Prépare mon briefing du matin, en français, court et en points : "
            "1) la météo du jour (weather_get), 2) l'état du serveur (system_stats) et des "
            "conteneurs Docker (docker_ps), 3) les 3 actualités les plus importantes du jour "
            "(web_search). 4) Si Google est connecté : mon agenda des prochaines 24 h (calendar_list) et les e-mails "
            "non lus récents (gmail_search avec is:unread newer_than:1d), en citant seulement expéditeur et objet ; mes agendas iCal "
            "du jour (agenda_ics, jours=1) ; si ces outils répondent par une erreur, ignore simplement cette partie. "
            "Termine par une phrase d'encouragement. 5) Comme Jarvis : crée aussi la version PDF soignée avec document_creer "
            "(format pdf, nom « Briefing du jour », une partie par rubrique). Si telegram_notify répond sans erreur, envoie le PDF "
            "(fichier = chemin du PDF) avec la version courte en légende ; sinon ignore. {instruction}"
        ),
    },
    "deep_research": {
        "name": "Recherche approfondie",
        "description": "Recherche multi-sources sur un sujet, avec synthèse et sources.",
        "needs_instruction": True,
        "schedule_type": "manual",
        "schedule_value": "",
        "prompt": (
            "Fais une recherche approfondie sur le sujet suivant : {instruction}\n"
            "Procède ainsi : web_search avec 2 requêtes différentes, puis web_fetch sur les 2 ou 3 "
            "sources les plus pertinentes, croise les informations et rends une synthèse structurée "
            "(contexte, points clés, désaccords éventuels). Termine par la liste des sources (URL)."
        ),
    },
    "research_monitor": {
        "name": "Veille sur un sujet",
        "description": "Cherche régulièrement les nouveautés sur un sujet et les consigne dans le workspace.",
        "needs_instruction": True,
        "schedule_type": "interval",
        "schedule_value": "21600",
        "prompt": (
            "Fais une veille sur : {instruction}\n"
            "Cherche les dernières nouveautés (web_search), résume uniquement ce qui est récent et "
            "important, puis ajoute ce résumé daté à la fin du fichier veilles/{slug}.md avec fs_append. "
            "Si rien de nouveau, réponds exactement « RAS »."
        ),
    },
    "system_monitor": {
        "name": "Veille système",
        "description": "Vérifie le CPU, la mémoire, le disque et les conteneurs ; ne te dérange qu'en cas de problème.",
        "needs_instruction": False,
        "schedule_type": "interval",
        "schedule_value": "900",
        "prompt": (
            "Vérifie la santé du serveur avec system_stats et docker_ps. S'il y a un problème "
            "(CPU, mémoire ou disque au-dessus de 85 %, ou un conteneur arrêté), décris-le en une "
            "ou deux phrases avec ce qu'il faut faire. Sinon réponds exactement « RAS ». {instruction}"
        ),
    },
    "orchestrator": {
        "name": "Orchestrateur",
        "description": "Décompose un objectif, délègue à des assistants spécialisés (chercheur, analyste, système, rédacteur) et synthétise.",
        "needs_instruction": True,
        "schedule_type": "manual",
        "schedule_value": "",
        "max_iterations": 10,
        "prompt": (
            "Objectif : {instruction}\n"
            "Tu es orchestratrice. Décompose l'objectif en 2 à 4 sous-tâches indépendantes et confie chacune "
            "à l'assistant adapté avec l'outil delegate (rôles : chercheur, analyste, systeme, redacteur). "
            "Donne à chaque assistant une tâche autonome et précise. Quand tu as leurs réponses, rédige la "
            "synthèse finale, structurée, en citant les sources reçues. N'invente aucune information."
        ),
    },
    "code_assistant": {
        "name": "Assistant code",
        "description": "Résout un problème en écrivant et exécutant du code Python dans un bac à sable isolé.",
        "needs_instruction": True,
        "schedule_type": "manual",
        "schedule_value": "",
        "max_iterations": 8,
        "prompt": (
            "Problème : {instruction}\n"
            "Résous-le en écrivant du code Python et en l'exécutant avec code_run (bac à sable sans réseau). "
            "Vérifie le résultat, corrige le code si une erreur apparaît, puis donne la réponse finale "
            "avec le code utilisé."
        ),
    },
    "custom": {
        "name": "Personnalisé",
        "description": "Ta propre instruction.",
        "needs_instruction": True,
        "schedule_type": "manual",
        "schedule_value": "",
        "prompt": "{instruction}",
    },
}

_run_lock = asyncio.Lock()  # un seul agent à la fois : le serveur IA n'a qu'une petite carte graphique
_tasks: set[asyncio.Task] = set()
_registry: ToolRegistry | None = None


def bind_registry(registry: ToolRegistry) -> None:
    global _registry
    _registry = registry


def _slug(text: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")
    return "-".join(p for p in out.split("-") if p)[:40] or "veille"


def build_prompt(template: str, instruction: str, name: str) -> str:
    tpl = TEMPLATES.get(template, TEMPLATES["custom"])
    return tpl["prompt"].format(instruction=instruction.strip(), slug=_slug(name))


def validate_schedule(schedule_type: str, value: str) -> str:
    """Retourne la valeur normalisée ou lève ValueError avec un message clair."""
    if schedule_type == "manual":
        return ""
    if schedule_type == "interval":
        if not value.strip().isdigit() or int(value) < 60:
            raise ValueError("Intervalle invalide : nombre de secondes, 60 minimum.")
        return str(int(value))
    if schedule_type == "cron":
        try:
            cron.parse(value)
        except cron.CronError as exc:
            raise ValueError(f"Expression cron invalide : {exc}") from exc
        return " ".join(value.split())
    raise ValueError("Type de planification inconnu (manual, interval ou cron).")


# ---------- Conception assistée : « décris ce que tu veux » → agent prêt à enregistrer ----------

_DESIGN_SYS = (
    "Tu conçois des agents autonomes pour l'assistant EVA. À partir de l'objectif de l'utilisateur, réponds par UN SEUL objet JSON : "
    '{"name": "nom court (3 à 5 mots)", "instruction": "consigne complète et autonome, à l\'impératif, avec les étapes et le format de sortie voulu", '
    '"schedule_type": "manual|interval|cron", "schedule_value": "…", "tools": ["outils utiles parmi la liste"]}. '
    "cron = 5 champs (minute heure jour mois jour_semaine) ; interval = secondes (60 minimum) ; manual si aucune récurrence. "
    "L'agent travaille seul (personne ne peut confirmer) : n'invente aucun outil, privilégie la recherche web, la météo, l'état du serveur, "
    "les documents et notes. Demande-lui de répondre « RAS » quand il n'y a rien de nouveau à signaler. Pas de texte hors JSON."
)
_DAYS = {"lundi": 1, "mardi": 2, "mercredi": 3, "jeudi": 4, "vendredi": 5, "samedi": 6, "dimanche": 0}


def guess_schedule(text: str) -> tuple[str, str]:
    """Repère une récurrence dans une phrase française : « chaque matin à 7h », « tous les lundis à 18h30 », « toutes les 2 heures »."""
    import re
    import unicodedata
    f = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    m = re.search(r"toutes? les (\d+) (minutes?|heures?)", f)
    if m:
        secs = int(m.group(1)) * (60 if m.group(2).startswith("min") else 3600)
        return ("interval", str(max(60, secs)))
    if re.search(r"toutes? les heures|chaque heure", f):
        return ("interval", "3600")
    hm = re.search(r"\b(?:a|vers)\s*(\d{1,2})\s*(?:h|:)\s*(\d{2})?", f)
    hour, minute = (int(hm.group(1)), int(hm.group(2) or 0)) if hm and int(hm.group(1)) < 24 else (None, 0)
    for d, n in _DAYS.items():
        if re.search(rf"(chaque|tous les) {d}s?\b", f):
            return ("cron", f"{minute} {hour if hour is not None else 8} * * {n}")
    if re.search(r"chaque matin|tous les matins", f):
        return ("cron", f"{minute} {hour if hour is not None else 7} * * *")
    if re.search(r"chaque soir|tous les soirs", f):
        return ("cron", f"{minute} {hour if hour is not None else 19} * * *")
    if re.search(r"chaque jour|tous les jours|quotidien|quotidienne", f):
        return ("cron", f"{minute} {hour if hour is not None else 8} * * *")
    if re.search(r"chaque semaine|hebdomadaire|toutes les semaines", f):
        return ("cron", f"{minute} {hour if hour is not None else 8} * * 1")
    return ("manual", "")


async def design(goal: str) -> dict:
    """Propose un agent complet pour un objectif en français. Le modèle rédige la consigne ; la récurrence est contrôlée par du code."""
    import re
    from . import ollama_client
    from .harness.selection import select_tool_names
    goal = (goal or "").strip()
    if len(goal) < 8:
        raise ValueError("Décris en une phrase ce que l'agent doit faire.")
    names = _registry.all_names() if _registry else []
    stype, svalue = guess_schedule(goal)
    draft = {"name": " ".join(goal.split()[:5]).capitalize()[:60], "instruction": goal, "schedule_type": stype, "schedule_value": svalue, "source": "regles"}
    try:
        choice = await model_router.select(goal)
        msg = await asyncio.wait_for(ollama_client.chat_once(
            [{"role": "system", "content": _DESIGN_SYS + " Outils : " + ", ".join(sorted(n for n in names if n in _AutoOnlyRegistry(_registry)._allowed))},
             {"role": "user", "content": goal}], model=choice["model"]), 60)
        raw = (msg.get("content") or "") if isinstance(msg, dict) else str(msg)
        j = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        if str(j.get("instruction", "")).strip():
            draft["instruction"] = str(j["instruction"]).strip()[:4000]
            draft["name"] = (str(j.get("name") or draft["name"]).strip() or draft["name"])[:60]
            draft["source"] = "modele"
            if stype == "manual" and j.get("schedule_type") in ("interval", "cron"):      # le code prime quand il a trouvé une récurrence
                try:
                    validate_schedule(j["schedule_type"], str(j.get("schedule_value", "")))
                    draft["schedule_type"], draft["schedule_value"] = j["schedule_type"], str(j["schedule_value"])
                except ValueError:
                    pass
    except Exception:  # noqa: BLE001 — modèle absent, JSON mal formé : on garde le brouillon par règles
        logger.info("Conception d'agent : repli sur les règles", exc_info=True)
    draft["tools"] = select_tool_names([draft["instruction"], goal], names)
    draft["tools"] = [t for t in draft["tools"] if _registry is None or t in _AutoOnlyRegistry(_registry)._allowed]
    return draft


def compute_next(schedule_type: str, value: str, after: datetime | None = None) -> datetime | None:
    after = after or datetime.now(timezone.utc)
    if schedule_type == "interval":
        return after + timedelta(seconds=int(value))
    if schedule_type == "cron":
        return cron.next_run(value, after, settings.timezone)
    return None


def _agent_dict(r) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "template": r["template"],
        "instruction": r["instruction"],
        "schedule_type": r["schedule_type"],
        "schedule_value": r["schedule_value"],
        "enabled": r["enabled"],
        "next_run_at": r["next_run_at"].isoformat() if r["next_run_at"] else None,
        "last_run_at": r["last_run_at"].isoformat() if r["last_run_at"] else None,
        "last_status": r.get("last_status"),
        "last_output": (r.get("last_output") or "")[:300] if "last_output" in r.keys() else None,
        "running": bool(r.get("running", False)),
    }


_LIST_SQL = """
SELECT a.*,
  (SELECT status FROM agent_runs r WHERE r.agent_id = a.id ORDER BY r.started_at DESC LIMIT 1) AS last_status,
  (SELECT output FROM agent_runs r WHERE r.agent_id = a.id ORDER BY r.started_at DESC LIMIT 1) AS last_output,
  EXISTS (SELECT 1 FROM agent_runs r WHERE r.agent_id = a.id AND r.status = 'running') AS running
FROM agents a
"""


async def list_agents() -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(_LIST_SQL + " ORDER BY a.created_at DESC")
    return [_agent_dict(dict_row(r)) for r in rows]


def dict_row(r):
    class _R(dict):
        pass

    d = _R(dict(r))
    return d


async def get_agent(agent_id: int) -> dict | None:
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow(_LIST_SQL + " WHERE a.id = $1", agent_id)
    return _agent_dict(dict_row(r)) if r else None


async def create_agent(name: str, template: str, instruction: str, schedule_type: str,
                       schedule_value: str, enabled: bool = True) -> dict:
    if template not in TEMPLATES:
        raise ValueError("Modèle d'agent inconnu.")
    if not name.strip():
        raise ValueError("Le nom est obligatoire.")
    if TEMPLATES[template]["needs_instruction"] and not instruction.strip():
        raise ValueError("Ce modèle demande une instruction (sujet).")
    value = validate_schedule(schedule_type, schedule_value)
    nxt = compute_next(schedule_type, value) if enabled else None
    async with get_pool().acquire() as conn:
        agent_id = await conn.fetchval(
            """INSERT INTO agents (name, template, instruction, schedule_type, schedule_value, enabled, next_run_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
            name.strip(), template, instruction.strip(), schedule_type, value, enabled, nxt,
        )
    return await get_agent(agent_id)


async def update_agent(agent_id: int, fields: dict) -> dict | None:
    current = await get_agent(agent_id)
    if not current:
        return None
    merged = {**current, **{k: v for k, v in fields.items() if v is not None}}
    value = validate_schedule(merged["schedule_type"], str(merged["schedule_value"]))
    if not merged["name"].strip():
        raise ValueError("Le nom est obligatoire.")
    nxt = compute_next(merged["schedule_type"], value) if merged["enabled"] else None
    async with get_pool().acquire() as conn:
        await conn.execute(
            """UPDATE agents SET name=$2, instruction=$3, schedule_type=$4, schedule_value=$5,
                                 enabled=$6, next_run_at=$7 WHERE id=$1""",
            agent_id, merged["name"].strip(), merged["instruction"].strip(),
            merged["schedule_type"], value, merged["enabled"], nxt,
        )
    return await get_agent(agent_id)


async def delete_agent(agent_id: int) -> bool:
    async with get_pool().acquire() as conn:
        res = await conn.execute("DELETE FROM agents WHERE id = $1", agent_id)
    return res.endswith("1")


async def list_runs(agent_id: int, limit: int = 30) -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, started_at, finished_at, status, left(output, 400) AS preview, trace_id
               FROM agent_runs WHERE agent_id = $1 ORDER BY started_at DESC LIMIT $2""",
            agent_id, limit,
        )
    return [
        {
            "id": r["id"],
            "started_at": r["started_at"].isoformat(),
            "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
            "status": r["status"],
            "preview": r["preview"],
            "trace_id": r["trace_id"],
        }
        for r in rows
    ]


async def get_run(run_id: int) -> dict | None:
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow(
            """SELECT r.*, a.name AS agent_name, t.steps, t.duration_ms, t.prompt_tokens, t.completion_tokens
               FROM agent_runs r JOIN agents a ON a.id = r.agent_id
               LEFT JOIN traces t ON t.id = r.trace_id WHERE r.id = $1""",
            run_id,
        )
    if not r:
        return None
    return {
        "id": r["id"],
        "agent_id": r["agent_id"],
        "agent_name": r["agent_name"],
        "started_at": r["started_at"].isoformat(),
        "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
        "status": r["status"],
        "output": r["output"],
        "steps": json.loads(r["steps"]) if r["steps"] else [],
        "duration_ms": r["duration_ms"],
        "prompt_tokens": r["prompt_tokens"],
        "completion_tokens": r["completion_tokens"],
    }


class AlreadyRunning(Exception):
    pass


async def start_run(agent_id: int, manual: bool) -> int:
    """Crée l'exécution et la lance en tâche de fond. Retourne l'id du run."""
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            if await conn.fetchval(
                "SELECT 1 FROM agent_runs WHERE agent_id=$1 AND status='running'", agent_id
            ):
                raise AlreadyRunning()
            run_id = await conn.fetchval(
                "INSERT INTO agent_runs (agent_id) VALUES ($1) RETURNING id", agent_id
            )
    task = asyncio.create_task(_execute(agent_id, run_id, manual))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return run_id


async def wait_for_runs() -> None:
    """Pour les tests : attend la fin des exécutions en cours."""
    if _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


class _AutoOnlyRegistry:
    """Vue du registre réservée aux agents : outils AUTO, outils « agent_safe »
    (bac à sable isolé) et outils réservés aux agents (delegate). Tout le reste est invisible."""

    def __init__(self, base: ToolRegistry, only: set[str] | None = None, allow_delegate: bool = True):
        from .harness.permissions import Permission

        self._base = base
        allowed = set()
        for n in base.all_names():
            t = base.get_any(n)
            if t.permission == Permission.AUTO or t.agent_safe:
                allowed.add(n)
        if not allow_delegate:
            allowed.discard("delegate")
        if only is not None:
            allowed &= only
        self._allowed = allowed

    def get(self, name):
        return self._base.get_any(name) if name in self._allowed else None

    def names(self):
        return sorted(self._allowed)

    def schemas(self):
        return [self._base.get_any(n).schema() for n in self.names()]


# ---------- Orchestration : sous-agents spécialisés ----------

MAX_DELEGATIONS = 5
SUB_ITERATIONS = 6
ROLE_TOOLS = {
    "chercheur": {"web_search", "web_fetch", "docs_search", "skill_list", "skill_read", "weather_get"},
    "analyste": {"code_run", "fs_list", "fs_read", "docs_search"},
    "systeme": {"system_stats", "docker_ps", "docker_logs", "git_status", "git_log", "git_diff", "fs_list", "fs_read"},
    "redacteur": {"fs_list", "fs_read", "docs_search"},
}
ROLE_PROMPTS = {
    "chercheur": "Tu es l'assistant chercheur : trouve des informations fiables avec tes outils et cite tes sources (URL).",
    "analyste": "Tu es l'assistant analyste : résous la tâche avec du code Python exécuté via code_run et donne le résultat vérifié.",
    "systeme": "Tu es l'assistant système : diagnostique le serveur avec tes outils et résume l'état et les actions utiles.",
    "redacteur": "Tu es l'assistant rédacteur : produis un texte clair et bien structuré à partir des éléments fournis.",
}

_orch: contextvars.ContextVar = contextvars.ContextVar("eva_orchestration", default=None)


async def run_subagent(role: str, task: str) -> dict:
    ctx = _orch.get()
    if ctx is None or _registry is None:
        return {"error": "Délégation possible uniquement pendant l'exécution d'un agent."}
    if ctx["count"] >= MAX_DELEGATIONS:
        return {"error": f"Limite de {MAX_DELEGATIONS} délégations atteinte : conclus avec ce que tu as."}
    ctx["count"] += 1
    system = (
        settings.system_prompt + "\n\n" + ROLE_PROMPTS[role]
        + " Tu travailles en autonomie : personne ne peut te répondre. Termine par une réponse finale concise."
    )
    history = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    choice = await model_router.select(task)
    chunks: list[str] = []
    errors: list[str] = []

    async def send_event(ev: dict) -> None:
        if ev.get("type") == "token":
            chunks.append(ev["text"])
        elif ev.get("type") == "error":
            errors.append(ev.get("message", "erreur"))

    async def deny(_t: str, _a: dict) -> bool:
        return False

    reg = _AutoOnlyRegistry(_registry, only=ROLE_TOOLS[role], allow_delegate=False)
    final = await run_harness(
        history, reg, send_event, deny, trace=ctx["trace"],
        model=choice["model"], tools_enabled=choice["tools"], max_iterations=SUB_ITERATIONS, unattended=True,
    )
    if final is None:
        return {"role": role, "error": errors[-1] if errors else "Le modèle n'a pas répondu."}
    return {"role": role, "model": choice["model"], "answer": (final or "".join(chunks)).strip()[:6000]}


delegate_tool.set_runner(run_subagent)


async def run_role(role: dict, task: str) -> dict:
    """Un rôle d'agent installé (dépôt ECC…) travaille seul, en lecture seule, et renvoie son analyse. Utilisable en conversation."""
    if _registry is None:
        return {"error": "Rôles indisponibles."}
    system = (
        settings.system_prompt + "\n\n" + role["body"][:6000]
        + "\n\nTu travailles en autonomie, en LECTURE SEULE (tu ne modifies rien) : personne ne peut te répondre. "
        "Réponds en français, de façon concise, et termine par ta réponse finale."
    )
    history = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    choice = await model_router.select(task)
    chunks: list[str] = []
    errors: list[str] = []

    async def send_event(ev: dict) -> None:
        if ev.get("type") == "token":
            chunks.append(ev["text"])
        elif ev.get("type") == "error":
            errors.append(ev.get("message", "erreur"))

    async def deny(_t: str, _a: dict) -> bool:
        return False

    reg = _AutoOnlyRegistry(_registry, only=set(role["tools"]), allow_delegate=False)
    final = await run_harness(history, reg, send_event, deny, model=choice["model"], tools_enabled=choice["tools"],
                              max_iterations=SUB_ITERATIONS, unattended=True)
    if final is None:
        return {"role": role["name"], "error": errors[-1] if errors else "Le modèle n'a pas répondu."}
    return {"role": role["name"], "model": choice["model"], "answer": (final or "".join(chunks)).strip()[:6000]}


roles_tool.set_runner(run_role)


async def _execute(agent_id: int, run_id: int, manual: bool) -> None:
    agent = await get_agent(agent_id)
    output, ok, error = "", True, ""
    trace_id = None
    try:
        async with _run_lock:
            if agent is None:
                raise RuntimeError("Agent supprimé pendant l'exécution.")
            if _registry is None:
                raise RuntimeError("Registre d'outils non initialisé.")
            session_id = f"agent:{agent_id}"
            await ensure_session(session_id)
            system = (
                skills_mod.system_prompt_with_skills(settings.system_prompt, Path(settings.workspace_root))
                + f"\n\nTu travailles en autonomie en tant qu'agent « {agent['name']} » : personne ne peut te "
                "répondre pendant l'exécution. Toute action qui demanderait une confirmation sera refusée "
                "automatiquement, ne la tente donc pas. Procède par étapes : vérifie ce que tu as trouvé avant de conclure, ne réponds jamais de mémoire à une "
                "question d'actualité (cherche), et termine par une réponse finale claire et concise qui répond à la consigne."
            )
            history = [
                {"role": "system", "content": system},
                {"role": "user", "content": build_prompt(agent["template"], agent["instruction"], agent["name"])},
            ]
            choice = await model_router.select(history[1]["content"])
            trace = TraceRecorder("agent", session_id=session_id, label=agent["name"], model=choice["model"])
            chunks: list[str] = []
            errors: list[str] = []

            async def send_event(ev: dict) -> None:
                if ev.get("type") == "token":
                    chunks.append(ev["text"])
                elif ev.get("type") == "error":
                    errors.append(ev.get("message", "erreur"))

            async def deny(_tool: str, _args: dict) -> bool:
                return False

            token = _orch.set({"count": 0, "trace": trace})
            try:
                from .harness.selection import SubsetRegistry, select_tool_names
                auto = _AutoOnlyRegistry(_registry)
                # outils proposés = ceux que la consigne appelle (un petit modèle choisit mieux parmi 10 outils que parmi 50)
                picked = [n for n in select_tool_names([history[1]["content"]], auto.names()) if n in auto._allowed]
                run_registry = SubsetRegistry(auto, picked) if picked else auto
                final = await run_harness(
                    history, run_registry, send_event, deny, trace=trace,
                    model=choice["model"], tools_enabled=choice["tools"],
                    max_iterations=TEMPLATES.get(agent["template"], {}).get("max_iterations", 8),
                    unattended=True,
                )
            finally:
                _orch.reset(token)
            if final is None:
                ok, error = False, (errors[-1] if errors else "Le modèle n'a pas répondu.")
            output = (final or "".join(chunks)).strip()
            trace_id = await trace.save(ok=ok, error=error)
    except Exception as exc:  # noqa: BLE001 — un agent ne doit jamais faire tomber EVA
        logger.exception("Erreur dans l'agent %s", agent_id)
        ok, error = False, str(exc)

    status = "ok" if ok else "error"
    final_text = (output or error or "(aucune réponse)")[:MAX_OUTPUT_CHARS]
    now = datetime.now(timezone.utc)
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE agent_runs SET status=$2, output=$3, finished_at=now(), trace_id=$4 WHERE id=$1",
            run_id, status, final_text if ok else f"Erreur : {final_text}", trace_id,
        )
        await conn.execute("UPDATE agents SET last_run_at=now() WHERE id=$1", agent_id)

    # Notification proactive pour les exécutions planifiées (pas quand l'utilisateur a lancé lui-même)
    if agent and not manual and ok and not final_text.strip().upper().startswith("RAS"):
        text = f"🤖 {agent['name']} :\n{final_text[:1200]}"
        await ensure_session("default")
        await save_message("default", "assistant", text)
        await connection_manager.broadcast_all({"type": "proactive", "text": text, "source": f"agent:{agent_id}"})
