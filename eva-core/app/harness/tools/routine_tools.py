"""Routines de la maison depuis la conversation : « tous les soirs à 22 h, lance la scène Bonne nuit »."""
from typing import Any

from ... import profiles, routines
from ..permissions import Permission
from .base import Tool


class RoutineCreerTool(Tool):
    name = "routine_creer"
    description = ("Crée une ROUTINE de la maison qui se lance toute seule : à une heure (heure=« 22:00 », jours=« tous les jours » / "
                   "« en semaine » / « le week-end » / « lundi et jeudi ») ou quand un capteur Home Assistant passe une condition "
                   "(capteur=« sensor.salon_temperature », condition=« > », valeur=« 26 » ; porte : binary_sensor.… = on ; nuit : sun.sun = below_horizon). "
                   "Actions : scene, appareil (+ action_appareil on/off/brightness…, valeur), annonce (+ piece), message (notification). "
                   "Pour une demande de texte ou de rapport régulier, utilise plutôt agent_planifier.")
    parameters = {"type": "object", "properties": {
        "nom": {"type": "string"},
        "heure": {"type": "string", "description": "HH:MM pour une routine horaire"},
        "jours": {"type": "string", "description": "tous les jours, en semaine, le week-end, ou les jours cités"},
        "capteur": {"type": "string", "description": "Entité Home Assistant pour une routine sur capteur"},
        "condition": {"type": "string", "enum": list(routines.CONDITIONS)},
        "valeur": {"type": "string"},
        "scene": {"type": "string"}, "appareil": {"type": "string"},
        "action_appareil": {"type": "string", "description": "on, off, toggle, brightness, color, temperature"},
        "valeur_appareil": {"type": "string"},
        "annonce": {"type": "string"}, "piece": {"type": "string"},
        "message": {"type": "string", "description": "Message de notification à envoyer"}}, "required": ["nom"]}
    permission = Permission.CONFIRM

    async def execute(self, nom: str = "", heure: str = "", jours: str = "", capteur: str = "", condition: str = "=", valeur: str = "on",
                      scene: str = "", appareil: str = "", action_appareil: str = "on", valeur_appareil: str = "", annonce: str = "",
                      piece: str = "", message: str = "", **_: Any) -> dict:
        decl = {"type": "capteur", "entite": capteur, "condition": condition, "valeur": valeur} if capteur else \
            {"type": "heure", "heure": heure, "jours": jours}
        actions = []
        if scene:
            actions.append({"type": "scene", "scene": scene})
        if appareil:
            actions.append({"type": "appareil", "appareil": appareil, "action": action_appareil or "on", "valeur": valeur_appareil})
        if annonce:
            actions.append({"type": "annonce", "texte": annonce, "piece": piece})
        if message:
            actions.append({"type": "notifier", "texte": message})
        try:
            r = await routines.creer({"nom": nom, "declencheur": decl, "actions": actions}, profiles.user_var.get() or "")
        except routines.RoutineError as exc:
            return {"error": str(exc)}
        return {"ok": True, "id": r["id"], "routine": routines.decrire(r), "info": "Visible et modifiable dans Maison › Routines."}


class RoutineListerTool(Tool):
    name = "routine_lister"
    description = "Liste les routines de la maison (heure ou capteur → actions), actives ou en pause."
    parameters = {"type": "object", "properties": {}, "required": []}
    permission = Permission.AUTO

    async def execute(self, **_: Any) -> dict:
        return {"routines": [{"id": r["id"], "nom": r["nom"], "actif": r["actif"], "quoi": routines.decrire(r)} for r in await routines.lister()]}


class RoutineGererTool(Tool):
    name = "routine_gerer"
    description = "Met en pause, réactive, lance tout de suite ou supprime une routine (id ou nom)."
    parameters = {"type": "object", "properties": {"routine": {"type": "string"},
                                                  "action": {"type": "string", "enum": ["pause", "activer", "lancer", "supprimer"]}},
                  "required": ["routine", "action"]}
    permission = Permission.CONFIRM

    async def execute(self, routine: str = "", action: str = "", **_: Any) -> dict:
        q = str(routine or "").strip().lower()
        lst = await routines.lister()
        r = next((x for x in lst if x["id"] == q), None) or next((x for x in lst if q and q in x["nom"].lower()), None)
        if not r:
            return {"error": f"Routine « {routine} » introuvable.", "routines": [x["nom"] for x in lst]}
        if action == "supprimer":
            await routines.supprimer(r["id"])
            return {"ok": True, "info": f"Routine « {r['nom']} » supprimée."}
        if action == "lancer":
            return {"ok": True, "fait": await routines.executer(r, "à la demande")}
        if action in ("pause", "activer"):
            await routines.modifier(r["id"], {"actif": action == "activer"})
            return {"ok": True, "info": f"Routine « {r['nom']} » {'réactivée' if action == 'activer' else 'en pause'}."}
        return {"error": "Action : pause, activer, lancer ou supprimer."}


def all_tools() -> list[Tool]:
    return [RoutineCreerTool(), RoutineListerTool(), RoutineGererTool()]
