"""Longues tâches en fond : « fais cette recherche et prépare le document, préviens-moi quand c'est fini ».

EVA confie la tâche à une copie d'elle-même qui travaille seule (une tâche à la fois pour ne pas saturer le serveur IA),
avec les droits de la personne et son propre plan de travail. Personne n'étant là pour répondre, toute action qui demande
un accord est refusée : la tâche le signale dans son compte rendu. À la fin, le résultat (et les fichiers produits) arrive
dans la conversation d'origine, et une notification part (Telegram si réglé)."""
import asyncio
import json
import logging
import secrets
import time

from .db import get_pool

logger = logging.getLogger("eva-core.taches_fond")

KV = "taches_fond"
GARDER = 60
MAX_TOURS = 16
DELAI_MAX_S = 45 * 60

_registre = None
_workspace = None
_file: asyncio.Semaphore | None = None
_taches: dict[str, asyncio.Task] = {}


def lier(registry, workspace_root) -> None:
    global _registre, _workspace
    _registre, _workspace = registry, workspace_root


async def _tout() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    return (json.loads(raw) if isinstance(raw, str) else raw) or {}


async def _maj(tid: str, **champs) -> dict:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1 FOR UPDATE", KV)
            d = (json.loads(raw) if isinstance(raw, str) else raw) or {}
            if tid in d or "titre" in champs:
                d.setdefault(tid, {}).update(champs)
            fini = sorted((k for k, v in d.items() if v.get("etat") not in ("en_attente", "en_cours")), key=lambda k: d[k].get("debut", 0))
            for k in fini[:max(0, len(d) - GARDER)]:
                d.pop(k, None)
            await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(d))
    return d.get(tid, {})


async def lister(qui: str, admin: bool = False) -> list[dict]:
    from . import plans
    out = []
    for tid, t in (await _tout()).items():
        if admin or t.get("qui", "").lower() == (qui or "").lower():
            p = await plans.lire(f"fond-{tid}")
            out.append({"id": tid, **{k: t.get(k) for k in ("titre", "etat", "debut", "fin", "resultat", "fichiers", "session", "qui", "refus")},
                        "plan": p})
    return sorted(out, key=lambda x: -(x.get("debut") or 0))


async def lancer(titre: str, consigne: str, qui: str, role: str, session: str, modele: str = "") -> dict:
    global _file
    if _registre is None:
        raise RuntimeError("Tâches en fond non initialisées.")
    consigne = str(consigne or "").strip()[:4000]
    if not consigne:
        raise ValueError("Décris la tâche à faire.")
    en_cours = [t for t in (await _tout()).values() if t.get("qui", "").lower() == (qui or "").lower() and t.get("etat") in ("en_attente", "en_cours")]
    if len(en_cours) >= 3:
        raise ValueError("Tu as déjà 3 tâches en fond en cours : attends qu'une se termine.")
    tid = secrets.token_hex(4)
    await _maj(tid, titre=(titre or consigne)[:100], consigne=consigne, qui=qui or "", role=role or "admin", session=session,
               etat="en_attente", debut=int(time.time()), fichiers=[], refus=[], modele=modele or "")
    _file = _file or asyncio.Semaphore(1)
    _taches[tid] = asyncio.create_task(_executer(tid))
    return {"id": tid, "titre": (titre or consigne)[:100]}


async def annuler(tid: str, qui: str, admin: bool = False) -> bool:
    t = (await _tout()).get(tid)
    if not t or not (admin or t.get("qui", "").lower() == (qui or "").lower()):
        return False
    tache = _taches.get(tid)
    if tache and not tache.done():
        tache.cancel()
    await _maj(tid, etat="annule", fin=int(time.time()))
    return True


async def _executer(tid: str) -> None:
    from . import features, profiles, router as model_router, skills as skills_mod
    from .config import settings
    from .connections import connection_manager
    from .harness import contexte
    from .harness.loop import run_harness
    from .harness.selection import SubsetRegistry, select_tool_names
    from .memory import save_message
    t = (await _tout()).get(tid, {})
    fichiers: list[dict] = []
    refus: list[str] = []
    try:
        async with _file:
            if (await _tout()).get(tid, {}).get("etat") == "annule":
                return
            await _maj(tid, etat="en_cours", debut_travail=int(time.time()))
            ctx = (profiles.user_var.set(t["qui"]), profiles.role_var.set(t["role"]), contexte.session.set(f"fond-{tid}"),
                   contexte.demander.set(None), contexte.envoyer.set(None))
            try:
                feats = await features.effective(t["role"], t["qui"])
                base = features.FeatureRegistry(_registre, feats)
                if t["role"] != "admin":
                    from .harness.cloisonnement import RegistreCloisonne
                    base = RegistreCloisonne(base, _workspace, t["qui"], t["role"])
                noms = [n for n in select_tool_names([t["consigne"]], base.names()) if n not in ("tache_de_fond", "poser_question")]
                for n in ("plan_taches", "recherche_approfondie", "web_search", "web_fetch", "document_creer", "fs_read", "fs_list"):
                    if base.get(n) is not None and n not in noms:
                        noms.append(n)
                reg = SubsetRegistry(base, noms)
                system = skills_mod.system_prompt_with_skills(settings.system_prompt, _workspace) + (
                    "\n\nTu fais une TÂCHE EN FOND : personne ne peut te répondre pendant que tu travailles. Commence par un plan "
                    "(plan_taches), fais chaque étape, coche-la, vérifie à la fin. Ne pose aucune question : choisis l'option la plus "
                    "raisonnable et dis laquelle. Les actions qui demandent un accord seront refusées : note-les pour la personne. "
                    "Termine par un compte rendu clair (ce qui est fait, résultats, fichiers créés, ce qui reste à décider).")
                history = [{"role": "system", "content": system}, {"role": "user", "content": t["consigne"]}]
                choix = await model_router.select(t["consigne"], force_cat="reasoning")
                if t.get("modele"):                               # modèle imposé (ex. apprentissage : IA du marché choisie)
                    choix = {**choix, "model": t["modele"]}

                async def evt(ev: dict) -> None:
                    if ev.get("type") == "tool_result" and isinstance(ev.get("result"), dict) and ev["result"].get("download"):
                        fichiers.append({"path": ev["result"]["path"], "size_bytes": ev["result"].get("size_bytes"), "name": ev.get("name")})

                async def refuse(outil: str, args: dict) -> bool:
                    refus.append(outil)
                    return False

                final = await asyncio.wait_for(run_harness(history, reg, evt, refuse, model=choix["model"], tools_enabled=choix["tools"],
                                                           max_iterations=MAX_TOURS, unattended=True), DELAI_MAX_S)
            finally:
                for var, tok in zip((profiles.user_var, profiles.role_var, contexte.session, contexte.demander, contexte.envoyer), ctx):
                    var.reset(tok)
        if final is None:
            raise RuntimeError("le modèle n'a pas répondu")
        texte = final.strip()
        if refus:
            texte += "\n\n⚠️ Actions non faites (elles demandent ton accord) : " + ", ".join(sorted(set(refus))) + "."
        if fichiers:
            texte += "\n\n📎 Fichiers : " + ", ".join(f["path"] for f in fichiers)
        await _maj(tid, etat="fini", fin=int(time.time()), resultat=texte[:12000], fichiers=fichiers, refus=sorted(set(refus)))
        message = f"✅ **Tâche en fond terminée : {t['titre']}**\n\n{texte}"
        from . import journal
        await journal.noter("tache", f"Tâche en fond terminée : {t['titre']}", t.get("qui", ""))
    except asyncio.CancelledError:
        await _maj(tid, etat="annule", fin=int(time.time()))
        return
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tâche en fond %s en échec", tid, exc_info=True)
        err = "trop longue (45 min)" if isinstance(exc, asyncio.TimeoutError) else str(exc)[:200]
        await _maj(tid, etat="erreur", fin=int(time.time()), resultat=f"Échec : {err}")
        message = f"❌ **Tâche en fond interrompue : {t.get('titre', '')}** — {err}"
        from . import journal
        await journal.noter("erreur", f"Tâche en fond interrompue : {t.get('titre', '')} — {err}", t.get("qui", ""))
    finally:
        _taches.pop(tid, None)
    try:
        if t.get("session"):
            await save_message(t["session"], "assistant", message)
            await connection_manager._deliver(t["session"], {"type": "proactive", "text": message})
            for f in fichiers:
                await connection_manager._deliver(t["session"], {"type": "tool_result", "name": f["name"],
                                                                 "result": {"path": f["path"], "size_bytes": f["size_bytes"], "download": True}})
        await connection_manager._hooks({"type": "proactive", "text": message.split("\n\n")[0].replace("**", "")})
    except Exception:  # noqa: BLE001
        logger.warning("Compte rendu de tâche en fond non livré", exc_info=True)
