"""Plan de travail d'une conversation : la liste des étapes qu'EVA s'est fixée, visible et cochée au fur et à mesure.

Gardé par conversation (kv « plan:<session> ») ; l'interface l'affiche comme une carte qui se met à jour. Avant de conclure,
EVA est relancée une fois si des étapes ne sont pas faites (voir harness/loop.py)."""
import json

from .db import get_pool

ETATS = ("a_faire", "en_cours", "fait", "abandonne")


def _cle(session: str) -> str:
    return f"plan:{session}"


async def lire(session: str) -> dict | None:
    if not session:
        return None
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", _cle(session))
    return (json.loads(raw) if isinstance(raw, str) else raw) or None


async def ecrire(session: str, plan: dict | None) -> None:
    async with get_pool().acquire() as conn:
        if plan is None:
            await conn.execute("DELETE FROM kv WHERE key=$1", _cle(session))
        else:
            await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb",
                               _cle(session), json.dumps(plan))


def restantes(plan: dict | None) -> list[str]:
    return [e["titre"] for e in (plan or {}).get("etapes", []) if e.get("etat") in ("a_faire", "en_cours")]


async def mettre_a_jour(session: str, titre: str = "", etapes: list | None = None, maj: list | None = None, effacer: bool = False) -> dict | None:
    if effacer:
        await ecrire(session, None)
        return None
    plan = await lire(session) or {"titre": "", "etapes": []}
    if etapes:
        anciens = {e["titre"]: e["etat"] for e in plan.get("etapes", [])}
        plan = {"titre": (titre or plan.get("titre") or "Plan")[:120],
                "etapes": [{"titre": str(t)[:160], "etat": anciens.get(str(t)[:160], "a_faire")} for t in etapes if str(t).strip()][:25]}
    elif titre:
        plan["titre"] = titre[:120]
    for m in maj or []:
        if not isinstance(m, dict):
            continue
        etat = str(m.get("etat", "fait"))
        if etat not in ETATS:
            etat = "fait"
        try:
            n = int(m.get("n", m.get("etape", 0)))
        except (TypeError, ValueError):
            n = 0
        if 1 <= n <= len(plan["etapes"]):
            plan["etapes"][n - 1]["etat"] = etat
            if etat == "en_cours":                         # une seule étape en cours à la fois
                for k, e in enumerate(plan["etapes"]):
                    if k != n - 1 and e["etat"] == "en_cours":
                        e["etat"] = "a_faire"
    if not plan["etapes"]:
        raise ValueError("Donne la liste des étapes du plan.")
    await ecrire(session, plan)
    return plan
