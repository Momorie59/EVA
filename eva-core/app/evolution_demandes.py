"""Demandes d'évolution : ce qu'on a demandé à EVA et qu'elle ne sait pas encore faire.

EVA les note elle-même (outil evolution_demander) au lieu de s'arrêter à « je ne peux pas » ; on les retrouve dans la page
Évolution, avec qui l'a demandé et quand, pour décider quoi ajouter ensuite."""
import json
import time
import uuid

from .db import get_pool

KV = "demandes_evolution"
MAX = 300


async def _charger() -> list[dict]:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    return ((json.loads(raw) if isinstance(raw, str) else raw) or {}).get("demandes", []) if raw else []


async def _ecrire(lst: list[dict]) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
                           KV, json.dumps({"demandes": lst[-MAX:]}))


async def ajouter(qui: str, texte: str, exemple: str = "") -> dict:
    texte = " ".join(str(texte or "").split())[:500]
    if len(texte) < 5:
        raise ValueError("Décris l'évolution souhaitée en une phrase.")
    lst = await _charger()
    proche = next((d for d in lst if d["statut"] == "a_faire" and d["texte"].lower() == texte.lower()), None)
    if proche:                                            # déjà demandée : on compte
        proche["fois"] = proche.get("fois", 1) + 1
        proche["derniere"] = int(time.time())
        await _ecrire(lst)
        return proche
    d = {"id": uuid.uuid4().hex[:8], "texte": texte, "exemple": str(exemple or "")[:300], "qui": qui or "", "cree": int(time.time()),
         "derniere": int(time.time()), "fois": 1, "statut": "a_faire"}
    lst.append(d)
    await _ecrire(lst)
    return d


async def lister() -> list[dict]:
    return sorted(await _charger(), key=lambda d: (d["statut"] != "a_faire", -d.get("derniere", d["cree"])))


async def changer(did: str, statut: str) -> list[dict]:
    if statut not in ("a_faire", "faite", "refusee", "supprimer"):
        raise ValueError("Statut inconnu.")
    lst = await _charger()
    if statut == "supprimer":
        lst = [d for d in lst if d["id"] != did]
    else:
        for d in lst:
            if d["id"] == did:
                d["statut"] = statut
    await _ecrire(lst)
    return await lister()
