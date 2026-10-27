"""Outils « agents » : EVA crée depuis la conversation une tâche automatique récurrente (« chaque matin à 7 h, envoie-moi la
météo et mes rendez-vous », « tous les lundis, fais le point sur mes colis »), les liste, les lance et les supprime."""
from typing import Any

from ..permissions import Permission
from .base import Tool


def _quand(a: dict) -> str:
    t, v = a["schedule_type"], a["schedule_value"]
    if t == "interval":
        s = int(v)
        return f"toutes les {s // 3600} h" if s % 3600 == 0 else f"toutes les {s // 60} min"
    if t == "cron":
        return f"planifié ({v})"
    return "à la demande"


class AgentPlanifierTool(Tool):
    name = "agent_planifier"
    description = ("Crée une tâche automatique qui revient toute seule (agent) : « chaque matin à 7 h envoie-moi la météo et mes rendez-vous », "
                   "« tous les lundis à 18 h résume mes colis », « toutes les 2 heures surveille le prix de… ». objectif = la demande "
                   "complète AVEC la récurrence. Pour un rappel simple (« rappelle-moi… »), utilise plutôt rappel_creer.")
    parameters = {"type": "object", "properties": {"objectif": {"type": "string"}}, "required": ["objectif"]}
    permission = Permission.CONFIRM

    async def execute(self, objectif: str = "", **_: Any) -> dict:
        from ... import agents                              # import tardif : agents dépend du harness
        try:
            d = await agents.design(objectif)
            a = await agents.create_agent(d["name"], "custom", d["instruction"], d["schedule_type"], d["schedule_value"])
        except ValueError as e:
            return {"error": str(e)}
        return {"ok": True, "id": a["id"], "nom": a["name"], "quand": _quand(a), "prochain": a["next_run_at"],
                "info": "Visible et modifiable dans la page Agents. Le résultat arrive dans les notifications (et sur Telegram si réglé)."}


class AgentListerTool(Tool):
    name = "agent_lister"
    description = "Liste les tâches automatiques (agents) : nom, quand, dernier résultat."
    parameters = {"type": "object", "properties": {}}
    permission = Permission.AUTO

    async def execute(self, **_: Any) -> dict:
        from ... import agents                              # import tardif : agents dépend du harness
        return {"agents": [{"id": a["id"], "nom": a["name"], "actif": a["enabled"], "quand": _quand(a), "prochain": a["next_run_at"],
                            "dernier_resultat": (a.get("last_output") or "")[:200]} for a in await agents.list_agents()]}


class AgentGererTool(Tool):
    name = "agent_gerer"
    description = "Agit sur une tâche automatique (id donné par agent_lister) : lancer maintenant, mettre en pause, reprendre ou supprimer."
    parameters = {"type": "object", "properties": {"id": {"type": "integer"},
                                                  "action": {"type": "string", "enum": ["lancer", "pause", "reprendre", "supprimer"]}},
                  "required": ["id", "action"]}
    permission = Permission.CONFIRM

    async def execute(self, id: int = 0, action: str = "", **_: Any) -> dict:  # noqa: A002
        from ... import agents                              # import tardif : agents dépend du harness
        a = await agents.get_agent(int(id or 0))
        if not a:
            return {"error": "Agent introuvable (agent_lister)."}
        if action == "lancer":
            try:
                await agents.start_run(a["id"], manual=True)
            except agents.AlreadyRunning:
                return {"error": "Il tourne déjà."}
            return {"ok": True, "info": f"« {a['name']} » est lancé ; le résultat arrive dans les notifications."}
        if action in ("pause", "reprendre"):
            await agents.update_agent(a["id"], {"enabled": action == "reprendre"})
            return {"ok": True, "info": f"« {a['name']} » {'en pause' if action == 'pause' else 'reprend'}."}
        if action == "supprimer":
            await agents.delete_agent(a["id"])
            return {"ok": True, "info": f"« {a['name']} » supprimé."}
        return {"error": "Action inconnue."}


def all_tools() -> list[Tool]:
    return [AgentPlanifierTool(), AgentListerTool(), AgentGererTool()]
