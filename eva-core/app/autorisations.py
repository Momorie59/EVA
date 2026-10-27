"""Autorisations durables : quand la personne dit « toujours autoriser » pour un outil, EVA ne le redemande plus.

Une autorisation est propre à une personne et à un outil ; elle se retire à tout moment (Paramètres › Sécurité & données).
« Autoriser cette fois » ne laisse aucune trace. Les agents planifiés, sans personne pour répondre, ne s'en servent pas."""
import json

from .db import get_pool

KV = "autorisations"
# Actions critiques (comme le niveau 3 de Jarvis) : accord demandé à CHAQUE fois, jamais « toujours » — appeler, écrire à quelqu'un,
# agir sur un site (réservation, achat), supprimer, commandes à distance.
CRITIQUES = frozenset({"appel_telephone", "gmail_send", "discord_envoyer", "navigateur_cliquer", "navigateur_remplir", "fs_delete", "net_ssh", "chrome_pc", "pc_commande", "pc_ecran_cliquer", "pc_operateur"})


def critique(outil: str) -> bool:
    return outil in CRITIQUES


def _qui(p: str | None) -> str:
    return (p or "").strip().lower()


async def _load() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    return (json.loads(raw) if isinstance(raw, str) else raw) or {}


async def _edit(fn) -> None:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1 FOR UPDATE", KV)
            d = (json.loads(raw) if isinstance(raw, str) else raw) or {}
            fn(d)
            await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(d))


async def allowed(personne: str, outil: str) -> bool:
    if critique(outil):
        return False
    try:
        return outil in (await _load()).get(_qui(personne), [])
    except Exception:  # noqa: BLE001 — sans base, on redemande
        return False


async def allow(personne: str, outil: str) -> None:
    if critique(outil):
        return                                            # jamais mémorisé, même si on le demande
    def go(d):
        cur = set(d.get(_qui(personne), []))
        cur.add(outil)
        d[_qui(personne)] = sorted(cur)
    await _edit(go)


async def revoke(personne: str, outil: str | None = None) -> None:
    def go(d):
        if outil is None:
            d.pop(_qui(personne), None)
        else:
            d[_qui(personne)] = [t for t in d.get(_qui(personne), []) if t != outil]
    await _edit(go)


async def lister(personne: str) -> list[str]:
    return [t for t in (await _load()).get(_qui(personne), []) if not critique(t)]
