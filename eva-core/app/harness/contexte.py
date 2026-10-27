"""Contexte du tour en cours, pour les outils qui parlent à l'interface (question à choix, plan de travail).

Posé par la conversation web (main.py) ; absent pour Telegram, les satellites, les agents : l'outil se replie alors sur du texte."""
from contextvars import ContextVar
from typing import Awaitable, Callable

# demander(question, choix, multiple) → liste des réponses choisies (ou texte libre), None si personne ne répond
demander: ContextVar[Callable[..., Awaitable[list[str] | None]] | None] = ContextVar("eva_demander", default=None)
# envoyer(événement) : événement WebSocket vers l'interface
envoyer: ContextVar[Callable[[dict], Awaitable[None]] | None] = ContextVar("eva_envoyer", default=None)
# conversation en cours
session: ContextVar[str] = ContextVar("eva_session", default="")
