"""Conversation sans WebSocket : pour les réseaux (bureau, hôtel, 4G d'entreprise) dont le proxy bloque les WebSocket.

Le navigateur parle à EVA en HTTP ordinaire : il envoie ses messages (POST) et récupère les événements par
« long polling » (GET qui attend jusqu'à 25 s). Côté EVA, un faux WebSocket (`PseudoWS`) se branche sur
exactement la même conversation que /ws/chat : mêmes outils, mêmes accords, mêmes droits."""
import asyncio
import json
import os
import secrets
import time
from types import SimpleNamespace

from fastapi import WebSocketDisconnect

ATTENTE_S = float(os.getenv("EVA_CHAT_HTTP_ATTENTE", "25"))   # durée d'un « long polling »
OUBLI_S = 90             # sans nouvelle du navigateur depuis ce délai : conversation fermée
GARDE = 500              # événements gardés en mémoire pour un navigateur qui se reconnecte


class PseudoWS:
    """Ce dont chat_ws a besoin d'un WebSocket (accept, close, send_json, receive_text, query_params, headers, client)."""

    def __init__(self, query: dict, headers, hote: str):
        self.query_params = dict(query)
        self.headers = headers
        self.client = SimpleNamespace(host=hote, port=0)
        self._entree: asyncio.Queue = asyncio.Queue()
        self._sortie: list[tuple[int, dict]] = []
        self._n = 0
        self._signal = asyncio.Event()
        self.ferme = False
        self.code = None
        self.vu = time.monotonic()
        self.tache: asyncio.Task | None = None
        self.pret = asyncio.Event()            # chat_ws a passé ses contrôles (session, droits) et lit les messages

    def _reveiller(self) -> None:
        self._signal.set()
        self._signal = asyncio.Event()

    async def accept(self) -> None:
        return None

    async def close(self, code: int = 1000) -> None:
        self.ferme, self.code = True, code
        self._reveiller()

    async def send_json(self, data: dict) -> None:
        if self.ferme:
            raise RuntimeError("connexion fermée")
        self._n += 1
        self._sortie.append((self._n, data))
        del self._sortie[:-GARDE]
        self._reveiller()

    async def receive_text(self) -> str:
        self.pret.set()
        item = await self._entree.get()
        if item is None:
            raise WebSocketDisconnect(1000)
        return item

    def envoyer(self, payload: dict) -> None:
        self.vu = time.monotonic()
        self._entree.put_nowait(json.dumps(payload))

    async def recevoir(self, apres: int) -> dict:
        self.vu = time.monotonic()
        fin = time.monotonic() + ATTENTE_S
        while not self.ferme and not any(n > apres for n, _ in self._sortie):
            reste = fin - time.monotonic()
            if reste <= 0:
                break
            try:
                await asyncio.wait_for(self._signal.wait(), reste)
            except asyncio.TimeoutError:
                break
        self.vu = time.monotonic()
        evts = [{"n": n, "data": d} for n, d in self._sortie if n > apres]
        return {"evenements": evts, "ferme": self.ferme and not evts, "code": self.code}

    def deconnecter(self) -> None:
        if not self.ferme:
            self._entree.put_nowait(None)
            self.ferme = True
            self._reveiller()


_ouvertes: dict[str, PseudoWS] = {}


async def ouvrir(chat_ws, query: dict, headers, hote: str) -> tuple[str, PseudoWS]:
    ws = PseudoWS(query, headers, hote)
    cid = secrets.token_urlsafe(16)
    _ouvertes[cid] = ws
    ws.tache = asyncio.create_task(chat_ws(ws))
    attente = asyncio.create_task(ws.pret.wait())
    await asyncio.wait({attente, ws.tache}, timeout=10, return_when=asyncio.FIRST_COMPLETED)   # contrôles faits, ou refus
    attente.cancel()
    return cid, ws


def trouver(cid: str) -> PseudoWS | None:
    return _ouvertes.get(cid)


def fermer(cid: str) -> None:
    ws = _ouvertes.pop(cid, None)
    if ws:
        ws.deconnecter()


async def menage() -> None:
    """Planificateur : ferme les conversations HTTP abandonnées (onglet fermé, ordinateur en veille)."""
    for cid, ws in list(_ouvertes.items()):
        if time.monotonic() - ws.vu > OUBLI_S or (ws.tache and ws.tache.done()):
            fermer(cid)
