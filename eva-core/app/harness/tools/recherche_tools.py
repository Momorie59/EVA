"""Recherche approfondie : plusieurs requêtes, les meilleures pages lues, extraits numérotés à citer [1], [2]…"""
import asyncio
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse

from ..permissions import Permission
from .base import Tool
from .web import WebFetchTool, WebSearchTool

MAX_SOURCES = 6
EXTRAIT = 1400
_VIDES = set("le la les un une des de du et ou en au aux a à pour par sur dans avec est sont que qui quoi quel quelle quels quelles "
             "comment pourquoi combien ce cette ces son sa ses leur leurs plus moins the of and to in for is on what how".split())


def _mots(t: str) -> set[str]:
    t = "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")
    return {m for m in re.findall(r"[a-z0-9]{3,}", t) if m not in _VIDES}


def meilleurs_passages(texte: str, question: str, limite: int = EXTRAIT) -> str:
    """Les paragraphes qui parlent le plus de la question, dans l'ordre de la page."""
    cles = _mots(question)
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[A-ZÉÈÀ])", texte or "") if len(p.strip()) > 60]
    if not paras:
        return (texte or "")[:limite]
    notes = sorted(range(len(paras)), key=lambda i: -(len(_mots(paras[i]) & cles) + (0.5 if re.search(r"\d", paras[i]) else 0)))
    choisis, total = [], 0
    for i in notes:
        if total + len(paras[i]) > limite and choisis:
            continue
        choisis.append(i)
        total += len(paras[i])
        if total >= limite:
            break
    return "\n".join(re.sub(r"\s+", " ", paras[i])[:limite] for i in sorted(choisis))[:limite]


class RechercheApprofondieTool(Tool):
    name = "recherche_approfondie"
    description = (
        "Recherche web SÉRIEUSE pour une question qui demande des faits fiables, récents ou chiffrés (prix, comparatif, règle en vigueur, "
        "actualité, fiche technique…) : lance plusieurs requêtes, lit les meilleures pages et renvoie des extraits numérotés. "
        "Réponds ensuite en citant [1], [2]… après chaque fait, et termine par « Sources : » avec la liste numérotée (titre — lien)."
    )
    parameters = {"type": "object", "properties": {
        "question": {"type": "string", "description": "La question complète"},
        "requetes": {"type": "array", "items": {"type": "string"}, "description": "2 à 4 requêtes de recherche variées (mots-clés, en français et/ou en anglais)"}},
        "required": ["question"]}
    permission = Permission.AUTO
    agent_safe = True

    def __init__(self):
        self._cherche, self._lit = WebSearchTool(), WebFetchTool()

    async def execute(self, question: str = "", requetes: list | None = None, **_: Any) -> dict:
        question = str(question or "").strip()
        if not question:
            return {"error": "Donne la question."}
        reqs = [str(r).strip() for r in (requetes or []) if str(r).strip()][:4] or [question]
        resultats = await asyncio.gather(*(self._cherche.execute(query=r, max_results=6) for r in reqs))
        if all("error" in r for r in resultats):
            return {"error": resultats[0]["error"]}
        candidats, vus, domaines = [], set(), {}
        for rang in range(6):                               # on alterne entre les requêtes : des sources variées
            for r in resultats:
                lst = r.get("results") or []
                if rang < len(lst):
                    x = lst[rang]
                    u = urlparse(x.get("url", ""))
                    cle = (u.netloc.lower().removeprefix("www."), u.path.rstrip("/"))
                    if cle in vus or domaines.get(cle[0], 0) >= 2:
                        continue
                    vus.add(cle)
                    domaines[cle[0]] = domaines.get(cle[0], 0) + 1
                    candidats.append(x)
        candidats = candidats[:MAX_SOURCES + 3]

        async def lire(x):
            try:
                return x, await asyncio.wait_for(self._lit.execute(url=x["url"], _max=30000), 15)
            except asyncio.TimeoutError:
                return x, {"error": "trop lent"}
        pages = await asyncio.gather(*(lire(x) for x in candidats))
        sources = []
        for x, p in pages:
            if len(sources) >= MAX_SOURCES:
                break
            texte = p.get("text", "") if isinstance(p, dict) and "error" not in p else ""
            extrait = meilleurs_passages(texte, question) if len(texte.strip()) > 80 else (x.get("snippet") or "")
            if not extrait.strip():
                continue
            sources.append({"n": len(sources) + 1, "titre": (p.get("title") if isinstance(p, dict) else "") or x.get("title", ""),
                            "url": (p.get("url") if isinstance(p, dict) else "") or x["url"], "extrait": extrait,
                            "lu": bool(texte)})
        if not sources:
            return {"error": "Aucune page lisible trouvée : reformule ou essaie d'autres mots-clés."}
        return {"question": question, "requetes": reqs, "sources": sources,
                "consigne": ("Réponds avec ces sources seulement : cite [n] après chaque fait ; si elles se contredisent ou datent, dis-le ; "
                             "termine par « Sources : » puis une ligne par source utilisée : [n] titre — url.")}
