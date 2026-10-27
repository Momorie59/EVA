"""Outils « mémoire » : EVA retient, relit et oublie ce que la personne qui parle lui confie.

Chaque souvenir est à la personne qui parle (jamais visible des autres). L'appel s'affiche dans la conversation et le
souvenir apparaît dans la page Mémoire, où la personne peut le corriger ou l'effacer : EVA ne retient rien en douce."""
from typing import Any

from ... import memoire, profiles
from ..permissions import Permission
from .base import Tool


def _qui() -> str:
    return profiles.user_var.get() or ""


class MemoireRetenirTool(Tool):
    name = "memoire_retenir"
    description = ("Retient durablement une information que la personne te demande de garder (préférence, fait la concernant, "
                   "décision prise). Seulement quand elle le demande ou le confirme, jamais une donnée sensible (santé, argent, "
                   "codes, mots de passe). Une phrase courte, à la 1re personne de la personne (« je préfère… »).")
    parameters = {"type": "object", "properties": {
        "texte": {"type": "string", "description": "Le souvenir, une phrase courte"},
        "sorte": {"type": "string", "enum": list(memoire.SORTES), "description": "preference, fait ou decision"}},
        "required": ["texte"]}
    permission = Permission.AUTO

    async def execute(self, texte: str = "", sorte: str | None = None, **_: Any) -> dict:
        if not await memoire.active(_qui()):
            return {"error": "La mémoire est coupée pour cette personne : ne rien retenir (elle peut la rallumer dans la page Mémoire)."}
        try:
            return {"retenu": await memoire.ajouter(_qui(), texte, sorte, source="eva")}
        except memoire.MemoireError as e:
            return {"error": str(e)}


class MemoireListerTool(Tool):
    name = "memoire_lister"
    description = "Liste ce que tu as retenu de la personne qui te parle (id, sorte, texte, actif)."
    parameters = {"type": "object", "properties": {}, "required": []}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, **_: Any) -> dict:
        return {"souvenirs": [{k: s[k] for k in ("id", "kind", "texte", "actif")} for s in await memoire.lister(_qui())]}


class MemoireOublierTool(Tool):
    name = "memoire_oublier"
    description = "Efface un souvenir de la personne qui te parle (id donné par memoire_lister), quand elle te le demande."
    parameters = {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}
    permission = Permission.AUTO

    async def execute(self, id: Any = None, **_: Any) -> dict:   # noqa: A002
        try:
            await memoire.supprimer(_qui(), int(id))
        except (memoire.MemoireError, TypeError, ValueError) as e:
            return {"error": str(e) or "Souvenir introuvable."}
        return {"oublie": int(id)}


def all_tools() -> list[Tool]:
    return [MemoireRetenirTool(), MemoireListerTool(), MemoireOublierTool()]
