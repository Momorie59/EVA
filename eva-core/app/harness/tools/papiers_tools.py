"""Outils « papiers » : EVA consulte et met à jour le Majordome administratif (échéances, contrats, garanties, impôts).

Lecture = AUTO. Toute modification (marquer, corriger) = CONFIRM : EVA prépare, montre, et n'agit qu'après accord.
Aucun outil ne résilie, ne paie ni n'envoie quoi que ce soit : ce n'est pas le rôle du majordome."""
from pathlib import Path
from typing import Any

from ... import papiers
from ..permissions import Permission
from .base import Tool


def _compact(e: dict) -> dict:
    return {
        "id": e.get("id"),
        "description": e.get("description"),
        "echeance": e.get("date_echeance"),
        "agir_avant": e.get("date_action"),
        "preavis_jours": e.get("preavis_jours"),
        "jours_restants": e.get("jours_restants"),
        "a_verifier": e.get("statut") == "a_valider",
        "document": e.get("titre"),
        "lien": e.get("lien_document"),
    }


class PapiersEcheancesTool(Tool):
    name = "papiers_echeances"
    description = ("Liste les échéances administratives à venir suivies par le majordome : renouvellements et préavis de "
                   "résiliation (assurances, abonnements, contrats), paiements, impôts (France et Italie), fins de garantie, "
                   "expirations de papiers. « agir_avant » = date limite pour agir (échéance moins préavis).")
    parameters = {"type": "object", "properties": {
        "jours": {"type": "integer", "description": "Horizon en jours (défaut 60)"}}, "required": []}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, jours: Any = 60, **_: Any) -> dict:
        try:
            jours = max(1, min(int(jours or 60), 730))
            rows = await papiers.echeances(jours)
        except (papiers.PapiersError, ValueError, TypeError) as exc:
            return {"error": str(exc)}
        out = {"horizon_jours": jours, "echeances": [_compact(e) for e in rows]}
        if not rows:
            out["info"] = (f"Aucune échéance suivie par le majordome dans les {jours} prochains jours "
                           "(soit rien n'arrive, soit les papiers concernés n'ont pas encore été déposés).")
        return out


class PapiersAVerifierTool(Tool):
    name = "papiers_a_verifier"
    description = ("Documents dont le majordome n'est pas sûr (dates incertaines, contrat sans date trouvée, erreur de lecture) "
                   "et qui attendent une vérification humaine.")
    parameters = {"type": "object", "properties": {}, "required": []}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, **_: Any) -> dict:
        try:
            docs = await papiers.a_valider()
        except papiers.PapiersError as exc:
            return {"error": str(exc)}
        return {"documents": [{
            "document_id": d.get("paperless_id"), "titre": d.get("titre"), "resume": d.get("resume"),
            "statut": d.get("statut"), "erreur": d.get("erreur"), "lien": d.get("lien_document"),
            "avertissements": d.get("avertissements", []),
            "echeances": [{"id": e.get("id"), "description": e.get("description"), "echeance": e.get("date_echeance"),
                           "preavis_jours": e.get("preavis_jours")} for e in d.get("echeances", []) if e.get("statut") == "a_valider"],
        } for d in docs]}


class PapiersQuestionTool(Tool):
    name = "papiers_question"
    description = ("Pose une question sur les papiers de la famille rangés dans Paperless (« quand expire la garantie du lave-linge ? », "
                   "« combien coûte l'assurance habitation ? », « quel est le préavis de la box ? »). Réponse appuyée sur les documents, avec leurs liens.")
    parameters = {"type": "object", "properties": {
        "question": {"type": "string", "description": "La question, en langage naturel"}}, "required": ["question"]}
    permission = Permission.AUTO

    async def execute(self, question: str = "", **_: Any) -> dict:
        if not str(question).strip():
            return {"error": "Question vide."}
        try:
            return await papiers.question(str(question)[:500])
        except papiers.PapiersError as exc:
            return {"error": str(exc)}


class PapiersMarquerTool(Tool):
    name = "papiers_marquer"
    description = ("Change le statut d'une échéance du majordome : « faite » (c'est réglé), « ignorer » (ne plus la suivre), "
                   "« valider » (l'extraction incertaine est correcte). Utilise l'id donné par papiers_echeances ou papiers_a_verifier.")
    parameters = {"type": "object", "properties": {
        "id": {"type": "integer", "description": "Identifiant de l'échéance"},
        "action": {"type": "string", "enum": ["faite", "ignorer", "valider"]}}, "required": ["id", "action"]}
    permission = Permission.CONFIRM

    async def execute(self, id: Any = None, action: str = "", **_: Any) -> dict:  # noqa: A002
        try:
            r = await papiers.marquer(int(id), str(action))
        except (papiers.PapiersError, ValueError, TypeError) as exc:
            return {"error": str(exc)}
        return {"id": r.get("id"), "description": r.get("description"), "nouveau_statut": r.get("statut")}


class PapiersCorrigerTool(Tool):
    name = "papiers_corriger"
    description = ("Corrige une échéance du majordome (date, préavis en jours, description). La correction est conservée même si "
                   "le document est réanalysé, et l'échéance devient active.")
    parameters = {"type": "object", "properties": {
        "id": {"type": "integer", "description": "Identifiant de l'échéance"},
        "date_echeance": {"type": "string", "description": "Nouvelle date, format AAAA-MM-JJ"},
        "preavis_jours": {"type": "integer", "description": "Préavis de résiliation en jours"},
        "description": {"type": "string"}}, "required": ["id"]}
    permission = Permission.CONFIRM

    async def execute(self, id: Any = None, date_echeance: str = "", preavis_jours: Any = None,  # noqa: A002
                      description: str = "", **_: Any) -> dict:
        champs: dict = {}
        if date_echeance:
            champs["date_echeance"] = str(date_echeance)[:10]
        if preavis_jours not in (None, ""):
            champs["preavis_jours"] = int(preavis_jours)
        if description:
            champs["description"] = str(description)[:300]
        if not champs:
            return {"error": "Rien à corriger : donne une date, un préavis ou une description."}
        try:
            return _compact(await papiers.corriger(int(id), champs))
        except (papiers.PapiersError, ValueError, TypeError) as exc:
            return {"error": str(exc)}


class PapiersDeposerTool(Tool):
    name = "papiers_deposer"
    description = ("Dépose un fichier joint par l'utilisateur (facture, contrat, avis d'impôt, attestation…) chez le majordome, "
                   "qui l'archive dans Paperless et en extrait les échéances. À utiliser quand on te demande de ranger ou "
                   "de suivre un papier. « fichier » = chemin donné dans le bloc des fichiers joints (uploads/…).")
    parameters = {"type": "object", "properties": {
        "fichier": {"type": "string", "description": "Chemin du fichier joint, ex. uploads/facture.pdf"}}, "required": ["fichier"]}
    permission = Permission.AUTO

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)

    async def execute(self, fichier: str = "", **_: Any) -> dict:
        from ...uploads import resolve_upload
        p = resolve_upload(str(fichier), self.workspace_root)
        if not p:
            return {"error": "Fichier introuvable parmi les fichiers joints (uploads/…)."}
        try:
            r = await papiers.deposer(p)
        except papiers.PapiersError as exc:
            return {"error": str(exc)}
        return {"depose": p.name, "info": "Analyse en cours chez le majordome (quelques minutes).", **r}


def all_tools(workspace_root: Path | None = None) -> list[Tool]:
    tools: list[Tool] = [PapiersEcheancesTool(), PapiersAVerifierTool(), PapiersQuestionTool(), PapiersMarquerTool(), PapiersCorrigerTool()]
    if workspace_root is not None:
        tools.append(PapiersDeposerTool(workspace_root))
    return tools
