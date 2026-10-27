"""Raccourcis iPhone (et Android / Tasker) : dicter une idée, une note ou une commande à EVA depuis le téléphone (comme Jarvis).

Chaque personne crée son jeton (Paramètres › Services connectés › Raccourcis du téléphone). Le raccourci envoie la phrase dictée
à POST /api/raccourci et lit la réponse. Comme chez Jarvis, seules les actions SANS demande d'accord sont faites ainsi
(listes, post-it, météo, agenda, questions, lumières non sensibles…) ; le reste est à confirmer dans l'application."""
import hashlib
import hmac
import json
import secrets
import time

from . import auth as auth_mod
from .db import get_pool

KV = "raccourcis"
PREFIXE = "evarac_"
_registre = None
_workspace = None


def lier(registry, workspace_root) -> None:
    global _registre, _workspace
    _registre, _workspace = registry, workspace_root


async def _tout() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    return (json.loads(raw) if isinstance(raw, str) else raw) or {}


async def _ecrire(d: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(d))


def _empreinte(j: str) -> str:
    return hashlib.sha256(j.encode()).hexdigest()


async def lister(qui: str) -> list[dict]:
    return [{"id": k, "nom": v["nom"], "cree": v.get("cree"), "dernier": v.get("dernier")}
            for k, v in (await _tout()).items() if v["qui"].lower() == (qui or "").lower()]


async def creer(qui: str, nom: str) -> dict:
    d = await _tout()
    if len([v for v in d.values() if v["qui"].lower() == (qui or "").lower()]) >= 5:
        raise ValueError("5 jetons au plus par personne : retire-en un.")
    jeton = PREFIXE + secrets.token_urlsafe(30)
    rid = secrets.token_hex(4)
    d[rid] = {"qui": qui or "", "nom": (" ".join(str(nom or "").split()) or "Mon téléphone")[:40], "empreinte": _empreinte(jeton), "cree": int(time.time())}
    await _ecrire(d)
    return {"id": rid, "nom": d[rid]["nom"], "jeton": jeton}


async def retirer(qui: str, rid: str) -> bool:
    d = await _tout()
    if rid in d and d[rid]["qui"].lower() == (qui or "").lower():
        d.pop(rid)
        await _ecrire(d)
        return True
    return False


async def qui(jeton: str | None) -> dict | None:
    if not jeton or not jeton.startswith(PREFIXE):
        return None
    e = _empreinte(jeton)
    d = await _tout()
    for rid, v in d.items():
        if hmac.compare_digest(v["empreinte"], e):
            u = next((x for x in auth_mod.list_users() if x["user"].lower() == v["qui"].lower()), None)
            if auth_mod.protected() and (u is None or u.get("disabled")):
                return None
            if time.time() - v.get("dernier", 0) > 60:
                v["dernier"] = int(time.time())
                await _ecrire(d)
            return {"id": rid, "user": u["user"] if u else "", "role": u["role"] if u else "admin"}
    return None


async def demander(personne: dict, texte: str) -> str:
    from . import features, instant, profiles, router as model_router, skills as skills_mod
    from .config import settings
    from .harness import contexte
    from .harness.loop import run_harness
    from .harness.selection import SubsetRegistry, select_tool_names
    from .memory import load_recent, save_message
    from .sessions import ensure_session, touch_session
    texte = str(texte or "").strip()[:1500]
    if not texte:
        return "Je n'ai rien reçu."
    session = f"raccourci-{(personne['user'] or 'admin').lower()}"
    ctx = (profiles.user_var.set(personne["user"]), profiles.role_var.set(personne["role"]), contexte.session.set(session))
    refus: list[str] = []
    try:
        await ensure_session(session, "Raccourcis du téléphone")
        k = instant.detect(texte)
        if k:
            rep = await instant.repondre(k, settings.timezone, personne["user"])
            if rep and rep[0]:
                await save_message(session, "user", texte)
                await save_message(session, "assistant", rep[0])
                return rep[0]
        past = await load_recent(session)
        system = skills_mod.system_prompt_with_skills(settings.system_prompt, _workspace) + (
            "\n\nLa personne t'écrit depuis un raccourci de son téléphone : la réponse sera lue à voix haute ou affichée en notification. "
            "Réponds en une à trois phrases, sans tableau ni lien. Une idée ou une note dictée : range-la (post-it, liste) et confirme.")
        history = [{"role": "system", "content": system}] + past[-10:] + [{"role": "user", "content": texte}]
        await save_message(session, "user", texte)
        base = features.FeatureRegistry(_registre, await features.effective(personne["role"], personne["user"]))
        if personne["role"] != "admin":
            from .harness.cloisonnement import RegistreCloisonne
            base = RegistreCloisonne(base, _workspace, personne["user"], personne["role"])
        reg = SubsetRegistry(base, [n for n in select_tool_names([texte], base.names()) if n not in ("poser_question", "tache_de_fond")])
        choix = await model_router.select(texte, prefer_fast=True)

        async def evt(_ev: dict) -> None:
            return None

        async def refuse(outil: str, _a: dict) -> bool:
            refus.append(outil)
            return False
        final = await run_harness(history, reg, evt, refuse, model=choix["model"], tools_enabled=choix["tools"])
        final = (final or "Désolée, je n'ai pas pu répondre.").strip()
        if refus:
            final += " (Ce qui demande ton accord n'est pas fait depuis le téléphone : ouvre EVA pour le confirmer.)"
        await save_message(session, "assistant", final)
        await touch_session(session)
        return final
    finally:
        profiles.user_var.reset(ctx[0])
        profiles.role_var.reset(ctx[1])
        contexte.session.reset(ctx[2])
