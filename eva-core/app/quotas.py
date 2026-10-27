"""Quotas par personne : le serveur IA (une seule carte graphique) reste disponible pour toute la maison.

Une personne non administratrice a un nombre maximal de messages par heure et par jour, selon son profil.
L'administrateur n'a aucune limite. 0 = illimité. Réglable dans Paramètres › Utilisateurs (par profil et par personne).
On compte les messages de la personne dans ses conversations (rôle « user »)."""
import json

from .db import get_pool

KV = "quotas"
DEFAUTS: dict[str, dict] = {
    "user": {"heure": 60, "jour": 400},
    "teen": {"heure": 40, "jour": 200},
    "child": {"heure": 30, "jour": 150},
    "guest": {"heure": 15, "jour": 50},
}


async def charger() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    d = (json.loads(raw) if isinstance(raw, str) else raw) or {}
    profils = {p: {**v, **(d.get("profils", {}).get(p) or {})} for p, v in DEFAUTS.items()}
    return {"profils": profils, "personnes": d.get("personnes", {})}


def _propre(q: dict) -> dict:
    out = {}
    for k in ("heure", "jour"):
        if k in q and q[k] is not None:
            v = int(q[k])
            if v < 0 or v > 100000:
                raise ValueError("Quota entre 0 (illimité) et 100000.")
            out[k] = v
    return out


async def enregistrer(profils: dict | None = None, personnes: dict | None = None) -> dict:
    d = await charger()
    brut = {"profils": {p: _propre(v) for p, v in (profils if profils is not None else d["profils"]).items() if p in DEFAUTS},
            "personnes": {n.lower(): _propre(v) for n, v in (personnes if personnes is not None else d["personnes"]).items() if v}}
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
                           KV, json.dumps(brut))
    return await charger()


async def limites(personne: str, role: str) -> dict:
    if role == "admin":
        return {"heure": 0, "jour": 0}
    d = await charger()
    base = dict(d["profils"].get(role) or d["profils"]["user"])
    base.update(d["personnes"].get((personne or "").lower(), {}))
    return base


async def usage(personne: str) -> dict:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """SELECT count(*) FILTER (WHERE m.created_at > now() - interval '1 hour') AS heure,
                      count(*) FILTER (WHERE m.created_at > now() - interval '1 day')  AS jour
               FROM messages m JOIN sessions s ON s.id = m.session_id
               WHERE s.owner = $1 AND m.role = 'user' AND m.created_at > now() - interval '1 day'""",
            personne)
    return {"heure": row["heure"], "jour": row["jour"]}


async def depasse(personne: str, role: str) -> str | None:
    """Message à afficher si la personne a atteint sa limite, sinon None."""
    if role == "admin" or not personne:
        return None
    lim = await limites(personne, role)
    u = await usage(personne)
    if lim["heure"] and u["heure"] >= lim["heure"]:
        return (f"Tu as atteint ta limite de {lim['heure']} messages par heure : le serveur IA est partagé avec toute la maison. "
                "Réessaie un peu plus tard.")
    if lim["jour"] and u["jour"] >= lim["jour"]:
        return f"Tu as atteint ta limite de {lim['jour']} messages pour aujourd'hui. On se retrouve demain !"
    return None
