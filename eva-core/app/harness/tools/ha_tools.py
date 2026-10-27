from typing import Any

from ... import homeassistant as ha
from ..permissions import Permission
from .base import Tool


async def _wrap(coro) -> dict:
    try:
        return await coro
    except ha.HAError as exc:
        return {"error": str(exc)}


class HaStatesTool(Tool):
    name = "ha_states"
    description = "Liste les entités Home Assistant (lumières, capteurs, prises, climat…) avec leur état. Filtre possible par domaine (light, sensor, switch…) ou mot-clé."
    parameters = {"type": "object", "properties": {
        "domain": {"type": "string", "description": "Domaine, ex. light, sensor, switch, climate"},
        "search": {"type": "string", "description": "Mot-clé dans l'identifiant ou le nom"}}, "required": []}
    permission = Permission.AUTO

    async def execute(self, domain: str = "", search: str = "", **_: Any) -> dict:
        return await _wrap(ha.list_states(domain, search))


class HaGetTool(Tool):
    name = "ha_get"
    description = "Donne l'état détaillé d'une entité Home Assistant (ex. light.salon, sensor.temperature_salon)."
    parameters = {"type": "object", "properties": {"entity_id": {"type": "string"}}, "required": ["entity_id"]}
    permission = Permission.AUTO

    async def execute(self, entity_id: str = "", **_: Any) -> dict:
        return await _wrap(ha.get_state(entity_id))


class HaCallTool(Tool):
    name = "ha_call"
    description = (
        "Commande un appareil Home Assistant en appelant un service (ex. domain=light, service=turn_on, entity_id=light.salon, "
        "data={\"brightness_pct\": 50}). Toujours soumis à l'accord de l'utilisateur ; déverrouiller, désarmer, ouvrir un "
        "garage ou un portail sont interdits."
    )
    parameters = {"type": "object", "properties": {
        "domain": {"type": "string"}, "service": {"type": "string"}, "entity_id": {"type": "string"},
        "data": {"type": "object", "description": "Paramètres facultatifs du service"}}, "required": ["domain", "service", "entity_id"]}
    permission = Permission.CONFIRM

    def permission_for(self, args: dict) -> Permission:
        try:
            ha.check_service(str(args.get("domain", "")), str(args.get("service", "")))
        except ha.HAError:
            return Permission.FORBIDDEN
        return Permission.CONFIRM

    async def execute(self, domain: str = "", service: str = "", entity_id: str = "", data: Any = None, **_: Any) -> dict:
        return await _wrap(ha.call_service(domain, service, entity_id, data if isinstance(data, dict) else None))
