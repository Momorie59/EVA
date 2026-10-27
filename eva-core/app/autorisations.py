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


# ---------------------------------------------------------------- phrase de demande d'accord (unique)
# Une seule façon de dire ce qu'EVA s'apprête à faire : interface web, Telegram, satellites et téléphone l'utilisent.
_VERBES = {
    "fs_write": "écrire le fichier", "fs_append": "ajouter au fichier", "fs_delete": "supprimer", "terminal_run": "lancer la commande",
    "docker_restart": "redémarrer le conteneur", "docker_stop": "arrêter le conteneur", "docker_start": "démarrer le conteneur",
    "git_commit": "enregistrer dans git", "gmail_send": "envoyer un e-mail à", "calendar_create": "ajouter à l'agenda",
    "calendar_modifier": "modifier dans l'agenda", "calendar_supprimer": "supprimer de l'agenda", "appel_telephone": "appeler",
    "discord_envoyer": "envoyer sur Discord", "navigateur_cliquer": "cliquer sur", "navigateur_remplir": "remplir",
    "pc_ecran_cliquer": "cliquer sur ton écran :", "pc_operateur": "prendre la main sur l'ordinateur pour",
    "print_text": "imprimer", "print_file": "imprimer", "print_list": "imprimer la liste", "papiers_marquer": "marquer le papier",
    "papiers_corriger": "corriger le papier", "carnet_ecrire": "écrire dans le carnet", "wiki_ecrire": "écrire la page wiki",
    "recette_creer": "ajouter la recette", "recette_partager": "partager la recette", "routine_gerer": "modifier la routine",
    "agent_planifier": "planifier l'agent", "agent_gerer": "modifier l'agent", "code_agent": "modifier le code du projet",
    "obs_action": "piloter OBS :", "ha_call": "piloter Home Assistant :", "finances_noter": "noter la dépense",
    "finances_budget": "régler le budget", "net_scan": "analyser le réseau", "net_ssh": "se connecter en SSH à",
    "net_http": "interroger", "net_inspect": "inspecter", "net_discover": "chercher les appareils du réseau",
    "sandbox_install": "installer dans le bac à sable :", "skill_install": "installer la compétence", "video_generate": "créer une vidéo :",
    "home_control": "piloter", "scene_run": "lancer la scène", "device_control": "piloter", "device_hue_scene": "lancer la scène Hue",
    "telegram_notify": "envoyer un message Telegram :", "pc_commande": "piloter l'ordinateur :", "chrome_pc": "agir dans ton Chrome :",
}
_CLES = ("path", "command", "to", "titre", "title", "nom", "name", "device", "appareil", "scene", "numero", "texte", "text", "url", "q", "tache")


def phrase_accord(outil: str, args: dict | None, oral: bool = False) -> str:
    """« EVA veut supprimer « notes.txt ». » — courte, lisible, sans JSON ; la même partout.
    oral=True (satellites, téléphone) : « Je voudrais supprimer « notes.txt ». Tu confirmes ? »"""
    args = args if isinstance(args, dict) else {}
    verbe = _VERBES.get(outil, f"utiliser « {outil} »")
    details = []
    for k in _CLES:
        v = args.get(k)
        if isinstance(v, (str, int, float)) and str(v).strip():
            t = " ".join(str(v).split())
            details.append(f"« {t[:80]}{'…' if len(t) > 80 else ''} »")
        if len(details) >= 2:
            break
    if not details:
        autres = [f"{k} = {str(v)[:40]}" for k, v in args.items() if isinstance(v, (str, int, float, bool)) and str(v).strip()][:2]
        details = [f"({', '.join(autres)})"] if autres else []
    fin = (f" {' '.join(details)}" if details else "")
    return f"Je voudrais {verbe}{fin}. Tu confirmes ?" if oral else f"EVA veut {verbe}{fin}."
