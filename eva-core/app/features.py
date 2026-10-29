"""Fonctionnalités activables par personne ou par groupe.

Droits d'une personne = base de son profil  +  fonctionnalités de ses groupes  +  ajouts individuels  −  retraits individuels.
L'administrateur a toujours tout. La voix n'est pas un outil : elle ouvre le micro et la synthèse vocale dans l'interface.
Les outils non listés ici (météo, listes, notes, documents…) restent accessibles à tout le monde."""
import json
import re

from .db import get_pool

KV = "access"

FEATURES: dict[str, dict] = {
    "voice": {"label": "Voix", "icon": "🎙️", "hint": "Parler à EVA et l'entendre répondre."},
    "web": {"label": "Internet", "icon": "🌐", "hint": "Recherches sur le web et lecture de pages."},
    "images": {"label": "Images", "icon": "🖼️", "hint": "Créer et modifier des images."},
    "files": {"label": "Fichiers", "icon": "📁", "hint": "Documents, projets, archives, impression, téléchargements."},
    "home": {"label": "Maison", "icon": "🏠", "hint": "Lumières, prises, scènes, Home Assistant."},
    "google": {"label": "Google", "icon": "📅", "hint": "Agenda et e-mails."},
    "notify": {"label": "Messages", "icon": "💬", "hint": "Notifications Telegram, appels et SMS aux contacts de la liste."},
    "pc": {"label": "Ordinateurs", "icon": "🖥️", "hint": "Piloter les ordinateurs où tourne un satellite EVA (applis, volume, verrouillage, extinction)."},
    "musique": {"label": "Musique", "icon": "🎵", "hint": "Écouter et piloter Spotify, reconnaître une chanson."},
    "diffusion": {"label": "Diffusion", "icon": "📡", "hint": "OBS (live, enregistrement), publier sur Discord, statistiques Instagram."},
    "salon": {"label": "Salon", "icon": "👥", "hint": "Voir qui est connecté, discuter à l'écrit, à la voix et en vidéo."},
    "carnets": {"label": "Carnets", "icon": "📓", "hint": "Carnets de notes avec sections et pages, à partager avec d'autres personnes ou des groupes."},
    "papiers": {"label": "Papiers", "icon": "🗂️", "hint": "Papiers de la famille : échéances, contrats, impôts, garanties. À réserver aux personnes de confiance."},
    "wiki": {"label": "Wiki", "icon": "📚", "hint": "Lire et modifier le wiki de la famille, et avoir ses pages personnelles (si le module est activé)."},
    "finances": {"label": "Finances", "icon": "💶", "hint": "Ses propres comptes et budgets (si le module est activé). Toujours privé."},
    "contenus": {"label": "Contenus", "icon": "🎬", "hint": "Suivi de ses vidéos et publications (si le module est activé)."},
    "inventaire": {"label": "Inventaire", "icon": "📦", "hint": "Où sont rangées les affaires de la maison et à qui on les a prêtées (si le module est activé)."},
    "recettes": {"label": "Recettes", "icon": "🍲", "hint": "Livre de recettes de la famille (si le module est activé). Un invité ne fait que les lire."},
    "code": {"label": "Code & système", "icon": "🛠️", "hint": "Terminal, code, Docker, réseau, extensions : réservé aux personnes de confiance."},
}
ALL = frozenset(FEATURES)
PROFILE_BASE: dict[str, frozenset] = {
    "admin": ALL,
    # Le Salon est réservé aux adultes par défaut ; à ouvrir aux ados/enfants par personne ou par groupe.
    # Les papiers de la famille ne s'ouvrent qu'à la demande (le conjoint, par exemple), jamais d'office à un ami.
    "user": ALL - {"code", "papiers"},
    "teen": frozenset({"voice", "web", "images", "carnets", "wiki", "recettes", "musique", "contenus", "inventaire"}),
    "child": frozenset({"voice", "images", "recettes", "musique"}),
    "guest": frozenset({"web", "recettes"}),
}

_INFO = {"weather_get", "present", "poser_question", "plan_taches", "tache_de_fond", "agenda_ics", "system_stats", "ai_server_stats", "docs_search", "api_search", "api_get", "skill_list", "skill_read"}
_INFO_PREFIX = ("list_", "note_", "rappel_", "evolution_", "pratique_")
_PREFIX = [("web", ("web_search", "web_fetch", "navigateur_", "recherche_approfondie")), ("images", ("image_",)), ("home", ("ha_", "device_", "scene_run", "routine_", "tv_")),
           ("google", ("gmail_", "calendar_")), ("notify", ("telegram_", "appel_")), ("diffusion", ("obs_", "discord_", "instagram_")), ("musique", ("spotify_",)), ("pc", ("pc_", "chrome_pc", "telephone_")), ("home", ("annonce",)),
           ("files", ("fs_", "file_deliver", "zip_make", "project_", "print_", "document_")), ("papiers", ("papiers_",)), ("wiki", ("wiki_",)), ("recettes", ("recette_",)), ("inventaire", ("inventaire_",)), ("finances", ("finances_",)), ("contenus", ("contenu_",)), ("carnets", ("carnet_",)), ("code", ("fs_delete",))]


def feature_of(tool: str) -> str | None:
    """Fonctionnalité qui commande cet outil ; None = libre pour tous. Un outil inconnu est rangé dans « code » (prudence)."""
    if tool in _INFO or tool.startswith(_INFO_PREFIX):
        return None
    if tool == "fs_delete":
        return "code"
    for feat, pre in _PREFIX:
        if tool.startswith(pre) or tool in pre:
            return feat
    return "code"


async def _load() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    d = (json.loads(raw) if isinstance(raw, str) else raw) or {}
    return {"groups": d.get("groups", {}), "users": d.get("users", {})}


async def _store(d: dict) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(d))


def _feats(items) -> list[str]:
    return sorted({f for f in (items or []) if f in FEATURES})


def compute(role: str, user: str, data: dict) -> frozenset:
    from . import modules                                  # module coupé (wiki, recettes) : personne ne l'a, pas même l'administrateur
    if role == "admin":
        return ALL - modules.coupes()
    out = set(PROFILE_BASE.get(role, PROFILE_BASE["user"]))
    u = data["users"].get((user or "").lower(), {})
    for gid in u.get("groups", []):
        out |= set(data["groups"].get(gid, {}).get("features", []))
    out |= set(u.get("extra", []))
    out -= set(u.get("blocked", []))
    return frozenset(out & ALL) - modules.coupes()


async def effective(role: str, user: str) -> frozenset:
    if role == "admin":
        from . import modules
        return ALL - modules.coupes()
    return compute(role, user, await _load())


def tool_allowed(feats, tool: str) -> bool:
    f = feature_of(tool)
    return f is None or f in feats


class FeatureRegistry:
    """Registre filtré selon les fonctionnalités de la personne : l'outil n'est ni annoncé ni exécutable."""

    def __init__(self, base, feats):
        self._base, self._feats = base, feats

    def get(self, name):
        return self._base.get(name) if tool_allowed(self._feats, name) else None

    def names(self):
        return [n for n in self._base.names() if tool_allowed(self._feats, n)]

    def schemas(self):
        return [self._base.get(n).schema() for n in self.names() if self._base.get(n)]


# ---------- gestion (administrateur) ----------

def catalog() -> list[dict]:
    return [{"id": k, **v} for k, v in FEATURES.items()]


async def overview(users: list[dict]) -> dict:
    d = await _load()
    groups = [{"id": g, "label": v.get("label", g), "features": _feats(v.get("features"))} for g, v in d["groups"].items()]
    out = []
    for u in users:
        acc = d["users"].get(u["user"].lower(), {})
        out.append({"user": u["user"], "role": u["role"], "groups": [g for g in acc.get("groups", []) if g in d["groups"]],
                    "extra": _feats(acc.get("extra")), "blocked": _feats(acc.get("blocked")),
                    "effective": sorted(compute(u["role"], u["user"], d)), "base": sorted(PROFILE_BASE.get(u["role"], PROFILE_BASE["user"]))})
    return {"features": catalog(), "groups": groups, "users": out, "profiles": {k: sorted(v) for k, v in PROFILE_BASE.items()}}


def _gid(label: str) -> str:
    g = re.sub(r"[^a-z0-9]+", "-", label.lower().strip()).strip("-")[:30]
    if not g:
        raise ValueError("Donne un nom au groupe.")
    return g


async def group_save(label: str, features: list[str], gid: str = "") -> dict:
    label = " ".join((label or "").split())[:40]
    d = await _load()
    gid = gid or _gid(label)
    if gid not in d["groups"] and len(d["groups"]) >= 20:
        raise ValueError("20 groupes au maximum.")
    d["groups"][gid] = {"label": label or gid, "features": _feats(features)}
    await _store(d)
    return {"id": gid, **d["groups"][gid]}


async def group_delete(gid: str) -> None:
    d = await _load()
    d["groups"].pop(gid, None)
    for u in d["users"].values():
        u["groups"] = [g for g in u.get("groups", []) if g != gid]
    await _store(d)


async def user_save(user: str, groups: list[str], extra: list[str], blocked: list[str]) -> dict:
    d = await _load()
    key = user.lower()
    d["users"][key] = {"groups": [g for g in groups if g in d["groups"]], "extra": _feats(extra), "blocked": _feats(blocked)}
    await _store(d)
    return d["users"][key]


async def user_forget(user: str) -> None:
    d = await _load()
    if d["users"].pop(user.lower(), None) is not None:
        await _store(d)
