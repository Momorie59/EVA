"""Compilation automatique des conversations, chaque nuit, quand le serveur IA est libre.

1. Le fil conducteur de chaque conversation qui a des échanges pas encore résumés — courtes comprises — est mis à jour
   (le fil du projet de rattachement est recompilé dans la foulée, voir fil.py).
2. Ce que chaque personne a dit d'elle depuis la dernière nuit est relu : les faits durables rejoignent sa mémoire
   (mêmes règles que les souvenirs automatiques : visibles, modifiables, rien de sensible, rien si sa mémoire est coupée).

« Libre » = personne n'a écrit à EVA depuis 10 minutes ; sinon on réessaie un peu plus tard, jusqu'à 6 h.
Paramètres › Intelligence › Compilation : heure, dernier bilan, « Compiler maintenant »."""
import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from . import fil, memoire
from .db import get_pool

logger = logging.getLogger("eva-core")

KV = "compilation"
HEURE = int(os.getenv("EVA_COMPIL_HEURE", "3"))
HEURE_MAX = 6                       # au-delà, on attend la nuit suivante
CALME_MIN = 10                      # minutes sans message avant de commencer
INACTIVE_MIN = 30                   # une conversation en cours n'est pas compilée
MAX_CONVERSATIONS = 200
_en_cours: dict = {"actif": False, "etape": "", "faites": 0, "total": 0}


async def _kv() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    return (json.loads(raw) if isinstance(raw, str) else raw) or {}


async def _kv_set(d: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
                           KV, json.dumps(d, default=str))


async def etat() -> dict:
    d = await _kv()
    async with get_pool().acquire() as conn:
        attente = await conn.fetchval(
            "SELECT count(*) FROM sessions s WHERE s.id NOT LIKE 'agent:%' AND EXISTS (SELECT 1 FROM messages m WHERE m.session_id=s.id "
            "AND m.role IN ('user','assistant') AND m.id > coalesce(s.resume_upto,0))")
    return {"heure": d.get("heure", HEURE), "actif": d.get("actif", True), "dernier": d.get("dernier"),
            "en_attente": int(attente or 0), "en_cours": dict(_en_cours)}


async def regler(heure: int | None = None, actif: bool | None = None) -> dict:
    d = await _kv()
    if heure is not None:
        if not 0 <= int(heure) <= 23:
            raise ValueError("Heure entre 0 et 23.")
        d["heure"] = int(heure)
    if actif is not None:
        d["actif"] = bool(actif)
    await _kv_set(d)
    return await etat()


async def _calme() -> bool:
    async with get_pool().acquire() as conn:
        n = await conn.fetchval("SELECT count(*) FROM messages WHERE role='user' AND created_at > now() - make_interval(mins => $1)", CALME_MIN)
    return not n


async def compiler(workspace: Path, force: bool = False) -> dict:
    """Une passe complète. force=True : aussi les conversations actives il y a moins de 30 min (bouton « Compiler maintenant »)."""
    if _en_cours["actif"]:
        return {"deja": True, **_en_cours}
    debut = time.monotonic()
    _en_cours.update(actif=True, etape="conversations", faites=0, total=0)
    bilan = {"conversations": 0, "souvenirs": 0, "erreurs": 0}
    try:
        d = await _kv()
        async with get_pool().acquire() as conn:
            sids = [r["id"] for r in await conn.fetch(
                "SELECT s.id FROM sessions s WHERE s.id NOT LIKE 'agent:%' AND s.supprime_le IS NULL AND (s.updated_at < now() - make_interval(mins => $1) OR $2) "
                "AND EXISTS (SELECT 1 FROM messages m WHERE m.session_id=s.id AND m.role IN ('user','assistant') AND m.id > coalesce(s.resume_upto,0)) "
                "ORDER BY s.updated_at DESC LIMIT $3", INACTIVE_MIN, force, MAX_CONVERSATIONS)]
            dernier_id = int(d.get("dernier_message", 0))
            rows = await conn.fetch(
                "SELECT m.id, m.content, s.owner FROM messages m JOIN sessions s ON s.id=m.session_id "
                "WHERE m.role='user' AND m.id > $1 AND s.id NOT LIKE 'agent:%' AND s.supprime_le IS NULL ORDER BY m.id LIMIT 3000", dernier_id)
        _en_cours["total"] = len(sids)
        for sid in sids:
            try:
                await fil.mettre_a_jour(sid, workspace, force=True)
                bilan["conversations"] += 1
            except Exception:  # noqa: BLE001 — une conversation en échec n'arrête pas les autres
                bilan["erreurs"] += 1
                logger.warning("Compilation : fil non mis à jour (%s)", sid, exc_info=True)
            _en_cours["faites"] += 1

        _en_cours.update(etape="mémoire", faites=0)
        par_personne: dict[str, list[str]] = {}
        for r in rows:
            if memoire.parle_de_soi(r["content"]):
                par_personne.setdefault(r["owner"] or "", []).append(r["content"])
        modele = await fil._modele()
        for qui, msgs in par_personne.items():
            if not await memoire.active(qui):
                continue
            for bloc in memoire.blocs(msgs):
                try:
                    bilan["souvenirs"] += len(await memoire.extraire(qui, bloc, modele))
                except Exception:  # noqa: BLE001
                    bilan["erreurs"] += 1
                _en_cours["faites"] += 1
        if rows:
            d["dernier_message"] = rows[-1]["id"]
        d["dernier"] = {"le": datetime.now().isoformat(timespec="minutes"), "duree_s": int(time.monotonic() - debut), **bilan}
        await _kv_set(d)
        logger.info("Compilation des conversations : %s", bilan)
        return d["dernier"]
    finally:
        _en_cours.update(actif=False, etape="")


_taches: set = set()


def lancer(workspace: Path, force: bool = True) -> bool:
    if _en_cours["actif"]:
        return False
    t = asyncio.create_task(compiler(workspace, force))
    _taches.add(t)
    t.add_done_callback(_taches.discard)
    return True


def fenetre(heure: int) -> set[int]:
    """Heures où la passe peut démarrer : de l'heure réglée jusqu'à 6 h (au moins 3 h de marge si l'heure est plus tardive)."""
    if heure < HEURE_MAX:
        return set(range(heure, HEURE_MAX))
    return {(heure + i) % 24 for i in range(3)}


def periodique(workspace: Path):
    """Tâche du planificateur (toutes les 15 min) : une seule passe par nuit, à partir de l'heure réglée, serveur IA libre."""
    async def run() -> None:
        d = await _kv()
        if not d.get("actif", True):
            return
        maintenant = datetime.now()
        heure = d.get("heure", HEURE)
        if maintenant.hour not in fenetre(heure):
            return
        if (d.get("dernier") or {}).get("le", "")[:10] == maintenant.date().isoformat():
            return                                          # déjà faite cette nuit
        if not await _calme():
            return                                          # quelqu'un parle à EVA : on réessaiera dans 15 min
        await compiler(workspace)
    return run
