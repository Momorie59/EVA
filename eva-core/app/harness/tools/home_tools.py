from typing import Any

from ... import devices
from ..permissions import Permission
from .base import Tool


class DeviceListTool(Tool):
    name = "device_list"
    description = "Liste les appareils de la maison (nom, pièce, type) et les scènes disponibles. À appeler pour savoir ce qui est pilotable."
    parameters = {"type": "object", "properties": {"room": {"type": "string", "description": "Filtrer par pièce"}}, "required": []}
    permission = Permission.AUTO

    async def execute(self, room: str = "", **_: Any) -> dict:
        await devices.reload()
        ds = devices.find("", room)
        return {"devices": [{"name": d["name"], "room": d["room"], "type": d["type"]} for d in ds],
                "scenes": [s["name"] for s in await devices.list_scenes()]}


class DeviceControlTool(Tool):
    name = "device_control"
    description = (
        "Pilote un appareil de la maison (lumière, prise, ventilateur, volet, ordinateur à réveiller…). action : on, off, toggle, brightness "
        "(value 0-100), color (value : rouge, vert, bleu, blanc chaud… ou #RRGGBB), temperature (value en °C), state (lire l'état). "
        "Indique « device » (nom approximatif accepté) OU « room » et/ou « type » pour agir sur plusieurs appareils à la fois "
        "(ex. room=salon, type=light, action=off). Serrures, alarmes et portails ne sont pas pilotables."
    )
    parameters = {"type": "object", "properties": {
        "device": {"type": "string", "description": "Nom de l'appareil (ex. « lampe du salon »)"},
        "room": {"type": "string", "description": "Pièce (ex. salon)"},
        "type": {"type": "string", "description": "light, switch, fan, climate, cover, media, computer"},
        "action": {"type": "string", "description": "on, off, toggle, brightness, color, temperature, state"},
        "value": {"type": "string", "description": "Valeur pour brightness / color / temperature"}}, "required": ["action"]}
    permission = Permission.AUTO

    def permission_for(self, args: dict) -> Permission:
        if str(args.get("action", "")) == "state":
            return Permission.AUTO
        return Permission.CONFIRM if devices.needs_confirm(args) else Permission.AUTO

    async def execute(self, action: str = "state", device: str = "", room: str = "", type: str = "", value: Any = None, **_: Any) -> dict:  # noqa: A002
        try:
            r = await devices.control(device, action, value, room, type)
            if action != "state":
                from ... import auth
                await auth.audit("device", "eva", "", f"{action} {device or room or type}", f"{value or ''} → " + ", ".join(f"{x['device']}={'ok' if x['ok'] else 'erreur'}" for x in r["results"])[:300], 0)
            return r
        except devices.DeviceError as exc:
            return {"error": str(exc)}


class SceneRunTool(Tool):
    name = "scene_run"
    description = "Lance une scène de la maison (ex. « soirée cinéma », « bonne nuit »). Les scènes sont créées dans Maison › Scènes."
    parameters = {"type": "object", "properties": {"scene": {"type": "string", "description": "Nom de la scène"}}, "required": ["scene"]}
    permission = Permission.AUTO

    def permission_for(self, args: dict) -> Permission:
        return Permission.CONFIRM if devices.scene_needs_confirm(str(args.get("scene", ""))) else Permission.AUTO

    async def execute(self, scene: str = "", **_: Any) -> dict:
        await devices.reload()
        s = await devices.find_scene(scene)
        if not s:
            return {"error": f"Scène « {scene} » introuvable. Scènes : {', '.join(x['name'] for x in await devices.list_scenes()) or 'aucune'}."}
        return await devices.run_scene(s)


class HueSceneTool(Tool):
    name = "device_hue_scene"
    description = ("Lance une scène Philips Hue créée dans l'appli Hue (« mets l'ambiance Lecture au salon », « scène Détente »). "
                   "scene : nom de la scène ; piece : pièce si plusieurs scènes portent le même nom.")
    parameters = {"type": "object", "properties": {"scene": {"type": "string"}, "piece": {"type": "string"}}, "required": ["scene"]}
    permission = Permission.AUTO

    async def execute(self, scene: str = "", piece: str = "", **_: Any) -> dict:
        from ... import hue
        from ...lists import norm
        trouvees = []
        for ip in await hue.ponts():
            try:
                trouvees += [{**s, "ip": ip} for s in await hue.scenes(ip)]
            except hue.HueError as exc:
                return {"error": str(exc)}
        if not trouvees:
            return {"error": "Aucune scène Hue (pont pas appairé, ou aucune scène créée dans l'appli Hue)."}
        cible = [s for s in trouvees if norm(scene) in norm(s["nom"]) or norm(s["nom"]) in norm(scene)]
        if piece:
            cible = [s for s in cible if norm(piece) in norm(s["piece"])] or cible
        if not cible:
            return {"error": f"Pas de scène « {scene} ».", "scenes": sorted({f"{s['nom']} ({s['piece']})" for s in trouvees})[:30]}
        s = cible[0]
        try:
            await hue.lancer_scene(s["ip"], s["id"], s["groupe"])
        except hue.HueError as exc:
            return {"error": str(exc)}
        return {"ok": True, "scene": s["nom"], "piece": s["piece"]}


class PresenceTool(Tool):
    name = "device_presence"
    description = "Dit qui est à la maison en ce moment, d'après les téléphones connectés au wifi (« qui est là ? », « Julie est rentrée ? »)."
    parameters = {"type": "object", "properties": {}, "required": []}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, **_: Any) -> dict:
        from ... import presence
        e = await presence.etat()
        return {**e, "resume": presence.phrase(e)}
