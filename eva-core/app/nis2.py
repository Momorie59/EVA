"""Contrôle de sécurité aligné sur NIS2 (directive (UE) 2022/2555, art. 21 §2 a–j et art. 23).

⚠ EVA est un assistant domestique/PME, pas une « entité essentielle ou importante » certifiée : ce module n'apporte AUCUNE conformité juridique.
Il vérifie automatiquement les réglages techniques qu'EVA maîtrise, dit ce qui manque et comment le corriger, et tient le registre d'incidents
avec les échéances de notification (alerte précoce 24 h, notification 72 h, rapport final 1 mois)."""
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from . import auth, backup, cloud_ai, telegram
from .config import settings
from .db import get_pool

OK, WARN, FAIL = "ok", "warn", "fail"
INC_KEY = "nis2_incidents"
SEVERITIES = ("faible", "moyen", "élevé", "critique")

# art. 21 §2 : lettre → intitulé
MEASURES = {
    "a": "Analyse des risques et sécurité des systèmes d'information",
    "b": "Gestion des incidents",
    "c": "Continuité d'activité, sauvegardes, reprise",
    "d": "Sécurité de la chaîne d'approvisionnement",
    "e": "Sécurité de l'acquisition, du développement et de la maintenance (vulnérabilités)",
    "f": "Évaluation de l'efficacité des mesures",
    "g": "Hygiène informatique de base et formation",
    "h": "Cryptographie et chiffrement",
    "i": "Sécurité des ressources humaines, contrôle d'accès, gestion des actifs",
    "j": "Authentification multifacteur et communications sécurisées",
}


def _c(measure: str, cid: str, title: str, status: str, detail: str, fix: str = "") -> dict:
    return {"measure": measure, "id": cid, "title": title, "status": status, "detail": detail, "fix": fix if status != OK else ""}


async def _incidents_raw() -> list[dict]:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", INC_KEY)
    return (json.loads(raw) if isinstance(raw, str) else raw) or []


async def _save_incidents(items: list[dict]) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", INC_KEY, json.dumps(items))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _deadlines(detected: str) -> dict:
    t = datetime.fromisoformat(detected)
    return {"early_warning": (t + timedelta(hours=24)).isoformat(timespec="minutes"),
            "notification": (t + timedelta(hours=72)).isoformat(timespec="minutes"),
            "final_report": (t + timedelta(days=30)).isoformat(timespec="minutes")}


def _view(i: dict) -> dict:
    d = _deadlines(i["detected"])
    now = _now()
    steps = []
    for k, label in (("early_warning", "Alerte précoce (24 h)"), ("notification", "Notification (72 h)"), ("final_report", "Rapport final (1 mois)")):
        done = i.get("done", {}).get(k)
        late = (not done) and now > datetime.fromisoformat(d[k]) and i["status"] != "clos"
        steps.append({"key": k, "label": label, "due": d[k], "done": done or "", "late": late})
    return {**i, "steps": steps}


async def incidents() -> list[dict]:
    return [_view(i) for i in sorted(await _incidents_raw(), key=lambda x: x["detected"], reverse=True)]


async def incident_add(title: str, severity: str, description: str = "", detected: str = "", user: str = "") -> dict:
    title = (title or "").strip()[:160]
    if not title:
        raise ValueError("Donne un titre à l'incident.")
    if severity not in SEVERITIES:
        raise ValueError("Gravité : " + ", ".join(SEVERITIES) + ".")
    try:
        det = datetime.fromisoformat(detected).astimezone(timezone.utc).isoformat(timespec="minutes") if detected else _now().isoformat(timespec="minutes")
    except ValueError as exc:
        raise ValueError("Date de détection invalide.") from exc
    inc = {"id": "inc-" + secrets.token_hex(4), "title": title, "severity": severity, "description": (description or "")[:2000], "detected": det,
           "status": "ouvert", "done": {}, "by": user, "actions": ""}
    items = await _incidents_raw()
    items.append(inc)
    await _save_incidents(items[-500:])
    return _view(inc)


async def incident_update(iid: str, patch: dict) -> dict:
    items = await _incidents_raw()
    for i in items:
        if i["id"] == iid:
            if patch.get("status") in ("ouvert", "clos"):
                i["status"] = patch["status"]
            if "actions" in patch:
                i["actions"] = str(patch["actions"])[:2000]
            for k in (patch.get("mark") or []):
                if k in ("early_warning", "notification", "final_report"):
                    i.setdefault("done", {})[k] = _now().isoformat(timespec="minutes")
            for k in (patch.get("unmark") or []):
                i.get("done", {}).pop(k, None)
            await _save_incidents(items)
            return _view(i)
    raise KeyError(iid)


async def incident_delete(iid: str) -> None:
    items = [i for i in await _incidents_raw() if i["id"] != iid]
    await _save_incidents(items)


async def audit(https: bool | None = None) -> dict:
    """Passe en revue la configuration réelle d'EVA. `https` : la requête actuelle est-elle arrivée en HTTPS (via Caddy) ?"""
    checks: list[dict] = []
    users = auth.list_users()
    active = [u for u in users if not u["disabled"]]
    admins = [u for u in active if u["role"] == "admin"]
    login = auth.login_required()

    # i — contrôle d'accès
    checks.append(_c("i", "login", "Connexion obligatoire", OK if login else FAIL,
                     f"{len(active)} compte(s) actif(s), dont {len(admins)} administrateur(s)." if login else "Toute personne du réseau peut utiliser EVA sans mot de passe.",
                     "Paramètres › Sécurité › Activer la connexion."))
    checks.append(_c("i", "roles", "Moindre privilège (rôles admin / utilisateur)", OK if login and len(active) >= 2 and len(admins) < len(active) else WARN,
                     "Les comptes simples n'accèdent ni aux réglages, ni au réseau, ni aux données des autres." if login else "Aucun compte : pas de séparation des droits.",
                     "Crée un compte « utilisateur » pour les usages courants et garde l'administrateur pour la configuration."))
    checks.append(_c("i", "password", "Politique de mot de passe", OK if auth.MIN_PASSWORD >= 12 else WARN,
                     f"{auth.MIN_PASSWORD} caractères minimum, hachage scrypt, verrouillage après {auth.MAX_FAILS} échecs.",
                     "Fixe EVA_MIN_PASSWORD=12 (ou plus) dans .env."))
    checks.append(_c("i", "env-token", "Jeton d'environnement (scripts)", OK if not settings.auth_token or len(settings.auth_token) >= 24 else WARN,
                     "Pas de jeton d'environnement." if not settings.auth_token else f"Jeton de {len(settings.auth_token)} caractères.",
                     "Utilise un jeton aléatoire d'au moins 24 caractères (openssl rand -hex 24)."))
    # j — MFA
    adm_no_mfa = [u["user"] for u in admins if not u.get("mfa")]
    checks.append(_c("j", "mfa", "Double authentification des administrateurs", OK if login and admins and not adm_no_mfa else (WARN if login else FAIL),
                     "Tous les administrateurs ont la double authentification." if login and admins and not adm_no_mfa else
                     ("Sans double authentification : " + ", ".join(adm_no_mfa) if login else "Pas de compte."),
                     "Paramètres › Sécurité › Double authentification (application d'authentification TOTP)."))
    # h — chiffrement
    if https is None:
        checks.append(_c("h", "https", "Chiffrement des échanges (HTTPS)", WARN, "Non vérifiable depuis cet appel.", "Ouvre EVA en https://…:8443."))
    else:
        checks.append(_c("h", "https", "Chiffrement des échanges (HTTPS)", OK if https else FAIL,
                         "Cette page est servie en HTTPS." if https else "Cette page circule en clair (HTTP) : mots de passe et conversations lisibles sur le réseau.",
                         "Utilise l'adresse https://<NAS>:8443 (Caddy)."))
    checks.append(_c("h", "headers", "En-têtes de sécurité HTTP", OK, "nosniff, anti-framing, politique de référent et permissions activés par EVA."))
    checks.append(_c("h", "secrets", "Secrets hors du dépôt Git", OK,
                     "Les clés (Telegram, cloud, jetons) sont stockées dans la base locale ; .env et Caddyfile sont ignorés par le zip de mise à jour.", ""))
    # b — incidents
    tg = await telegram.status()
    checks.append(_c("b", "journal", "Journal d'accès et d'actions", OK if auth.AUDIT_DAYS >= 180 else WARN,
                     f"Connexions, échecs, refus et actions sensibles conservés {auth.AUDIT_DAYS} jours (Paramètres › Sécurité › Journal).",
                     "Fixe EVA_AUDIT_DAYS=365 dans .env."))
    checks.append(_c("b", "alerts", "Alertes en cas d'attaque", OK if tg["configured"] and tg["allowed"] and tg["alerts"] else WARN,
                     "Telegram prévient après des échecs de connexion répétés." if tg["configured"] and tg["allowed"] and tg["alerts"] else "Aucune notification : une attaque ne serait vue qu'en ouvrant le journal.",
                     "Paramètres › Telegram : renseigne le bot, ton identifiant et active les alertes."))
    inc = await incidents()
    late = [i for i in inc if any(s["late"] for s in i["steps"])]
    checks.append(_c("b", "register", "Registre des incidents", WARN if late else OK,
                     f"{len(inc)} incident(s) enregistré(s)" + (f", {len(late)} avec une échéance dépassée." if late else "."),
                     "Complète les notifications en retard dans le registre ci-dessous."))
    # c — continuité
    bl = backup.listing()
    last = datetime.fromisoformat(bl[0]["created"]) if bl else None
    age = (datetime.now() - last).days if last else None
    checks.append(_c("c", "backup", "Sauvegardes régulières", OK if age is not None and age <= 2 else (WARN if bl else FAIL),
                     f"Dernière sauvegarde il y a {age} jour(s), {len(bl)} conservée(s)." if bl else "Aucune sauvegarde.",
                     "Paramètres › Sécurité › Sauvegarde : crée-en une et copie-la HORS du NAS."))
    checks.append(_c("c", "offsite", "Copie hors site", WARN, "EVA ne peut pas vérifier qu'une copie existe hors du NAS (règle 3-2-1).",
                     "Télécharge régulièrement la sauvegarde sur un disque externe ou un autre ordinateur."))
    # d — chaîne d'approvisionnement
    cl = await cloud_ai.load()
    used = [p for p, v in cl["providers"].items() if v.get("api_key")]
    checks.append(_c("d", "cloud", "Dépendance à des services tiers", OK if not used else WARN,
                     "100 % local : aucune donnée n'est envoyée à un fournisseur cloud." if not used else "Fournisseurs cloud configurés : " + ", ".join(used) + " (tes demandes peuvent leur être envoyées).",
                     "Supprime les clés cloud inutiles (Paramètres › IA)."))
    checks.append(_c("d", "mcp", "Extensions externes (MCP, skills)", WARN, "Les skills et serveurs MCP installés depuis Internet sont du code tiers.",
                     "N'installe que des sources que tu connais ; relis le contenu d'un skill avant de l'activer."))
    # e — vulnérabilités
    checks.append(_c("e", "scanner", "Analyse de vulnérabilités du réseau", OK if settings.scanner_token else WARN,
                     "Le service eva-scanner est disponible (outils réseau)." if settings.scanner_token else "Service d'analyse non configuré.", "Voir docker-compose (eva-scanner)."))
    checks.append(_c("e", "updates", "Mises à jour", WARN, "EVA ne met pas à jour le système du NAS ni Docker.",
                     "Mets à jour OpenMediaVault (apt), les images Docker (docker compose pull) et EVA (zip) au moins une fois par mois."))
    # f — efficacité
    checks.append(_c("f", "selfaudit", "Auto-évaluation", OK, "Ce contrôle peut être relancé à tout moment et exporté (rapport)."))
    # g — hygiène
    checks.append(_c("g", "ports", "Surface exposée", OK, "Seul Caddy (8443) est exposé ; les services internes ne publient pas de port.",
                     "Ne redirige jamais le port d'EVA vers Internet sans connexion + double authentification."))
    order = {FAIL: 0, WARN: 1, OK: 2}
    score = round(100 * sum({OK: 1, WARN: 0.5, FAIL: 0}[c["status"]] for c in checks) / len(checks))
    return {"generated": _now().isoformat(timespec="seconds"), "score": score, "measures": MEASURES,
            "counts": {k: sum(1 for c in checks if c["status"] == k) for k in (OK, WARN, FAIL)},
            "checks": sorted(checks, key=lambda c: (order[c["status"]], c["measure"]))}


async def report_markdown(https: bool | None = None) -> str:
    a = await audit(https)
    icon = {OK: "✅", WARN: "⚠️", FAIL: "❌"}
    out = [f"# Rapport de sécurité EVA — alignement NIS2", "", f"Généré le {a['generated']} · score {a['score']} %", "",
           "> Ce rapport décrit l'état technique d'EVA au regard des mesures de l'article 21 de la directive NIS2. Il ne vaut pas attestation de conformité.", ""]
    for letter, label in MEASURES.items():
        rows = [c for c in a["checks"] if c["measure"] == letter]
        if not rows:
            continue
        out.append(f"## {letter}) {label}")
        for c in rows:
            out.append(f"- {icon[c['status']]} **{c['title']}** — {c['detail']}" + (f"\n  - À faire : {c['fix']}" if c["fix"] else ""))
        out.append("")
    inc = await incidents()
    out.append("## Registre des incidents")
    if not inc:
        out.append("Aucun incident enregistré.")
    for i in inc:
        out.append(f"- **{i['title']}** ({i['severity']}, {i['status']}) — détecté le {i['detected']}")
        for s in i["steps"]:
            out.append(f"  - {s['label']} : " + (f"fait le {s['done']}" if s["done"] else f"avant le {s['due']}" + (" — EN RETARD" if s["late"] else "")))
    return "\n".join(out) + "\n"
