"""Finances personnelles : EVA ne voit QUE les comptes de la personne qui lui parle ; elle peut noter une dépense ou fixer un budget
(avec son accord), jamais toucher aux comptes des autres."""
from typing import Any

from ... import finances, profiles
from ..permissions import Permission
from .base import Tool


class FinancesResumeTool(Tool):
    name = "finances_resume"
    description = ("Finances de la personne pour un mois (AAAA-MM, défaut : ce mois-ci) : revenus, dépenses, dépenses par catégorie avec "
                   "budget et dépassements, évolution sur 6 mois, plus grosses dépenses, soldes des comptes. Lecture seule.")
    parameters = {"type": "object", "properties": {"mois": {"type": "string", "description": "AAAA-MM"}}}
    permission = Permission.AUTO

    async def execute(self, mois: str = "", **_: Any) -> dict:
        try:
            return await finances.tableau(profiles.user_var.get() or "", mois or None)
        except finances.FinancesError as exc:
            return {"error": str(exc)}


class FinancesOperationsTool(Tool):
    name = "finances_operations"
    description = "Opérations bancaires de la personne : par mois, catégorie (ex. Restaurants) ou mot du libellé (ex. Amazon). Lecture seule."
    parameters = {"type": "object", "properties": {
        "mois": {"type": "string", "description": "AAAA-MM"}, "categorie": {"type": "string", "enum": finances.CATEGORIES + [""]},
        "recherche": {"type": "string"}}}
    permission = Permission.AUTO

    async def execute(self, mois: str = "", categorie: str = "", recherche: str = "", **_: Any) -> dict:
        try:
            ops = await finances.operations(profiles.user_var.get() or "", mois or None, str(categorie or ""), str(recherche or ""), 80)
        except finances.FinancesError as exc:
            return {"error": str(exc)}
        return {"operations": ops, "total": round(sum(o["montant"] for o in ops), 2), "nombre": len(ops)}


class FinancesNoterTool(Tool):
    name = "finances_noter"
    description = ("Ajoute une opération à la main dans les finances de la personne (paiement en espèces, remboursement d'un ami, "
                   "dépense non encore sur le relevé) : montant NÉGATIF pour une dépense (« j'ai payé 12 € au marché » → -12), positif pour "
                   "une rentrée. Sans compte précisé : compte « Espèces ».")
    parameters = {"type": "object", "properties": {
        "libelle": {"type": "string"}, "montant": {"type": "number"}, "jour": {"type": "string", "description": "AAAA-MM-JJ, défaut aujourd'hui"},
        "compte": {"type": "string"}, "categorie": {"type": "string", "enum": finances.CATEGORIES + [""]}}, "required": ["libelle", "montant"]}
    permission = Permission.CONFIRM

    async def execute(self, libelle: str = "", montant: float = 0, jour: str = "", compte: str = "", categorie: str = "", **_: Any) -> dict:
        try:
            return {"ok": True, **await finances.noter(profiles.user_var.get() or "", libelle, montant, jour, compte, categorie)}
        except finances.FinancesError as exc:
            return {"error": str(exc)}


class FinancesBudgetTool(Tool):
    name = "finances_budget"
    description = "Fixe (ou retire, montant 0) le budget mensuel d'une catégorie : « mets un budget de 300 € pour l'alimentation »."
    parameters = {"type": "object", "properties": {"categorie": {"type": "string", "enum": finances.CATEGORIES}, "montant": {"type": "number"}},
                  "required": ["categorie", "montant"]}
    permission = Permission.CONFIRM

    async def execute(self, categorie: str = "", montant: float = 0, **_: Any) -> dict:
        try:
            r = await finances.regler_budget(profiles.user_var.get() or "", categorie, montant)
        except finances.FinancesError as exc:
            return {"error": str(exc)}
        return {"ok": True, "budgets": r}
