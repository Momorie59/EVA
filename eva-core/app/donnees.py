"""Les données d'une personne : ce qu'EVA garde sur elle, l'export complet (un ZIP) et l'effacement.

Ce qui appartient à une personne :
- ses conversations (messages, avis, traces, passages indexés pour la recherche) ;
- ses post-it, ses carnets (et sa place dans les carnets partagés par d'autres) ;
- ses projets (projets/<slug> dont elle est propriétaire) ;
- ses fichiers déposés, ses photos envoyées, les fichiers qu'EVA lui a livrés, ses images créées ;
- sa mémoire (ce qu'EVA retient d'elle) ;
- ses réglages : fonctionnalités, quota, et en option son compte.
Les papiers de la famille (Paperless, majordome) ne sont jamais à une personne non administratrice : ils ne sont pas concernés."""
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from . import acces, auth, features, project_acl, quotas
from .db import get_pool

NB_PREFIX = "nb:"
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")


def _cle(personne: str) -> str:
    return (personne or "").strip().lower()


def _json(v):
    return json.loads(v) if isinstance(v, str) else v


# ------------------------------------------------------------------ inventaire
async def _sessions(conn, qui: str) -> list[str]:
    return [r["id"] for r in await conn.fetch("SELECT id FROM sessions WHERE lower(owner)=$1", qui)]


async def _carnets(conn) -> list[dict]:
    return [_json(r["value"]) for r in await conn.fetch("SELECT value FROM kv WHERE key LIKE $1", NB_PREFIX + "%")]


def _fichiers(ws: Path, qui: str) -> list[str]:
    """Chemins relatifs (au workspace) des fichiers de la personne, fichiers dérivés compris (« .txt », dossiers « _extrait »)."""
    out = []
    for dossier in (*acces.DOSSIERS_PERSONNELS, f"uploads/{acces.SOUS_PHOTOS}"):
        base = ws / dossier
        if not base.is_dir():
            continue
        for e in sorted(base.iterdir()):
            if e.name == acces.FICHIER or (dossier == "uploads" and e.name == acces.SOUS_PHOTOS):
                continue
            if acces.proprietaire(ws, dossier, e.name) == qui:
                out.append(f"{dossier}/{e.name}")
    return out


def _images(ws: Path, qui: str) -> list[str]:
    d = ws / "generated"
    out = []
    if d.is_dir():
        for meta in d.glob("*.json"):
            try:
                if str(_json(meta.read_text()).get("owner", "")).lower() == qui:
                    out += [f"generated/{p.name}" for p in d.glob(meta.stem + ".*")]
            except (OSError, ValueError):
                continue
    return sorted(out)


async def _projets(qui: str) -> list[str]:
    return sorted(s for s, m in (await project_acl.load()).items() if str((m or {}).get("owner", "")).lower() == qui)


async def _memoire(conn, qui: str) -> list[dict]:
    rows = await conn.fetch("SELECT id, kind, texte, actif, created_at, updated_at FROM memoire WHERE lower(owner)=$1 ORDER BY id", qui)
    return [{**dict(r), "created_at": r["created_at"].isoformat(), "updated_at": r["updated_at"].isoformat()} for r in rows]


async def inventaire(ws: Path, personne: str) -> dict:
    qui = _cle(personne)
    async with get_pool().acquire() as conn:
        sids = await _sessions(conn, qui)
        msgs = await conn.fetchval("SELECT count(*) FROM messages WHERE session_id = ANY($1::text[])", sids)
        notes = await conn.fetchval("SELECT count(*) FROM notes WHERE lower(owner)=$1", qui)
        carnets = [n for n in await _carnets(conn) if str(n.get("owner", "")).lower() == qui]
        memoire = await conn.fetchval("SELECT count(*) FROM memoire WHERE lower(owner)=$1", qui)
    return {"personne": qui, "conversations": len(sids), "messages": int(msgs or 0), "post_it": int(notes or 0),
            "carnets": len(carnets), "projets": await _projets(qui), "fichiers": len(_fichiers(ws, qui)),
            "images": len([p for p in _images(ws, qui) if p.endswith(IMG_EXT)]), "souvenirs": int(memoire or 0)}


# ------------------------------------------------------------------ export
async def exporter(ws: Path, personne: str) -> str:
    """Construit « exports/mes-donnees-<personne>-<date>.zip » (à elle seule) et renvoie son chemin relatif."""
    qui = _cle(personne)                                   # "" : EVA sans mot de passe (une seule personne)
    async with get_pool().acquire() as conn:
        sids = await _sessions(conn, qui)
        sessions = [dict(r) for r in await conn.fetch("SELECT id, title, model, created_at, updated_at, coalesce(project,'') AS project, coalesce(resume,'') AS resume FROM sessions WHERE id = ANY($1::text[]) ORDER BY created_at", sids)]
        msgs = await conn.fetch("SELECT id, session_id, role, content, created_at FROM messages WHERE session_id = ANY($1::text[]) ORDER BY id", sids)
        avis = await conn.fetch("SELECT message_id, session_id, rating, comment, created_at FROM feedback WHERE session_id = ANY($1::text[])", sids)
        notes = await conn.fetch("SELECT id, text, color, done, shared, created_at, updated_at FROM notes WHERE lower(owner)=$1 ORDER BY id", qui)
        carnets = [n for n in await _carnets(conn) if str(n.get("owner", "")).lower() == qui]
        memoire = await _memoire(conn, qui)
    par_session: dict[str, list] = {}
    for m in msgs:
        par_session.setdefault(m["session_id"], []).append({"id": m["id"], "role": m["role"], "texte": m["content"], "date": m["created_at"].isoformat()})
    conversations = [{"id": s["id"], "titre": s["title"], "modele": s["model"], "debut": s["created_at"].isoformat(),
                      "fin": s["updated_at"].isoformat(), "projet": s["project"], "fil_conducteur": s["resume"],
                      "messages": par_session.get(s["id"], [])} for s in sessions]
    compte = next((u for u in auth.list_users() if u["user"].lower() == qui), {"user": qui})
    reglages = {"compte": compte, "fonctionnalites": sorted(await features.effective(compte.get("role", "user"), qui)),
                "quota": await quotas.limites(qui, compte.get("role", "user"))}

    d = ws / "exports"
    d.mkdir(parents=True, exist_ok=True)
    nom = f"mes-donnees-{qui or 'eva'}-{datetime.now():%Y%m%d-%H%M%S}.zip"
    cible = d / nom
    j = lambda o: json.dumps(o, ensure_ascii=False, indent=1, default=str)   # noqa: E731
    with zipfile.ZipFile(cible, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("LISEZMOI.txt", f"Données de « {qui or 'EVA'} » gardées par EVA, exportées le {datetime.now():%d/%m/%Y à %H:%M}.\n\n"
                   "conversations.json : toutes tes conversations, message par message\n"
                   "avis.json : tes 👍/👎 sur les réponses\npost-it.json, carnets.json : tes notes\n"
                   "memoire.json : ce qu'EVA retient de toi (préférences, faits, décisions)\n"
                   "reglages.json : ton compte (sans mot de passe), tes fonctionnalités et ton quota\n"
                   "fichiers/ : tes fichiers déposés, photos envoyées et fichiers livrés par EVA\n"
                   "images/ : les images créées pour toi\nprojets/ : tes projets\n")
        z.writestr("conversations.json", j(conversations))
        z.writestr("avis.json", j([dict(a) for a in avis]))
        z.writestr("post-it.json", j([{**dict(n), "shared": _json(n["shared"])} for n in notes]))
        z.writestr("carnets.json", j(carnets))
        z.writestr("memoire.json", j(memoire))
        try:
            from . import wiki
            z.writestr("wiki.json", j(await wiki.donnees_de(qui)))          # pages perso + pages famille créées
            from . import recettes
            z.writestr("recettes.json", j(await recettes.donnees_de(qui)))
            from . import finances
            z.writestr("finances.json", j(await finances.exporter(qui)))
            from . import contenus
            z.writestr("contenus.json", j(await contenus.exporter(qui)))
        except Exception:  # noqa: BLE001 — tables du wiki absentes (ancienne base) : rien à exporter
            pass
        z.writestr("reglages.json", j(reglages))
        for rel in _fichiers(ws, qui):
            if rel.startswith("exports/mes-donnees-"):
                continue                                   # pas d'export dans l'export
            _ajouter(z, ws / rel, "fichiers/" + rel)
        for rel in _images(ws, qui):
            _ajouter(z, ws / rel, "images/" + Path(rel).name)
        for slug in await _projets(qui):
            _ajouter(z, ws / "projets" / slug, f"projets/{slug}")
    rel = f"exports/{nom}"
    acces.enregistrer(ws, rel, qui)
    await auth.audit("export", qui, "", "données personnelles", rel, 200)
    return rel


def _ajouter(z: zipfile.ZipFile, src: Path, arc: str) -> None:
    if src.is_file():
        z.write(src, arc)
    elif src.is_dir():
        for f in sorted(src.rglob("*")):
            if f.is_file() and ".git" not in f.relative_to(src).parts:
                z.write(f, f"{arc}/{f.relative_to(src).as_posix()}")


# ------------------------------------------------------------------ effacement
async def effacer(ws: Path, personne: str, compte: bool = False, acteur: str = "") -> dict:
    """Efface tout ce qui appartient à la personne. Avec compte=True, supprime aussi son compte (réservé à l'administrateur)."""
    qui = _cle(personne)
    if not qui:
        raise ValueError("Personne inconnue.")
    bilan = await inventaire(ws, qui)
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            sids = await _sessions(conn, qui)
            sources = [f"conversation:{s}" for s in sids]
            await conn.execute("DELETE FROM feedback WHERE session_id = ANY($1::text[])", sids)
            await conn.execute("DELETE FROM traces WHERE session_id = ANY($1::text[])", sids)
            await conn.execute("DELETE FROM doc_chunks WHERE kind='message' AND source = ANY($1::text[])", sources)
            await conn.execute("DELETE FROM messages WHERE session_id = ANY($1::text[])", sids)
            await conn.execute("DELETE FROM sessions WHERE id = ANY($1::text[])", sids)
            await conn.execute("DELETE FROM notes WHERE lower(owner)=$1", qui)
            await conn.execute("DELETE FROM memoire WHERE lower(owner)=$1", qui)
            await conn.execute("DELETE FROM wiki_pages WHERE espace='perso' AND owner=$1", qui)   # le wiki famille reste à la famille
            for nb in await _carnets(conn):
                if str(nb.get("owner", "")).lower() == qui:
                    await conn.execute("DELETE FROM kv WHERE key=$1", NB_PREFIX + nb["id"])
                elif any(s.get("kind") == "user" and str(s.get("name", "")).lower() == qui for s in nb.get("shares", [])):
                    nb["shares"] = [s for s in nb["shares"] if not (s.get("kind") == "user" and str(s.get("name", "")).lower() == qui)]
                    await conn.execute("UPDATE kv SET value=$2::jsonb WHERE key=$1", NB_PREFIX + nb["id"], json.dumps(nb))

    fichiers = _fichiers(ws, qui)
    for rel in fichiers + _images(ws, qui):
        p = ws / rel
        shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    par_dossier: dict[str, list[str]] = {}
    for rel in fichiers:
        dossier, nom = rel.rsplit("/", 1)
        par_dossier.setdefault(dossier, []).append(nom)
    for dossier, noms in par_dossier.items():
        acces.oublier(ws, dossier, noms)
    async with get_pool().acquire() as conn:                # passages indexés de ces fichiers
        await conn.execute("DELETE FROM doc_chunks WHERE kind='file' AND source = ANY($1::text[])",
                           fichiers + [f + ".txt" for f in fichiers])

    try:                                                    # ses finances (comptes, opérations, règles, budgets)
        from . import contenus, finances
        await finances.effacer(qui)
        await contenus.effacer(qui)
        from . import rappels
        await rappels.effacer_de(qui)
        from . import lecons
        await lecons.effacer_de(qui)
        from . import miroir
        await miroir.oublier(qui)
        from . import inventaire as inventaire_objets
        await inventaire_objets.effacer_de(qui)             # ses objets privés                           # empreintes de son visage (mode miroir)
    except Exception:  # noqa: BLE001
        pass
    try:                                                    # ses recettes et leurs photos/vidéos
        from . import medias, recettes
        medias.supprimer(await recettes.effacer_de(qui))
    except Exception:  # noqa: BLE001 — table absente (module jamais utilisé)
        pass

    acl = await project_acl.load()
    for slug in bilan["projets"]:
        shutil.rmtree(ws / "projets" / slug, ignore_errors=True)
        acl.pop(slug, None)
    for meta in acl.values():                               # retirée des projets partagés par d'autres
        if isinstance(meta, dict) and qui in [str(x).lower() for x in meta.get("shared", [])]:
            meta["shared"] = [x for x in meta["shared"] if str(x).lower() != qui]
    await project_acl.save(acl)

    q = await quotas.charger()
    if q["personnes"].pop(qui, None) is not None:
        await quotas.enregistrer(q["profils"], q["personnes"])
    if compte:
        await features.user_forget(qui)
        await auth.delete_user(qui, actor=acteur)
    await auth.audit("erase", acteur or qui, "", f"données de {qui}" + (" + compte" if compte else ""), json.dumps(bilan, default=str), 200)
    return bilan
