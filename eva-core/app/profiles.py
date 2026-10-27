"""Profils d'utilisateur : administrateur, adulte (« user »), adolescent, enfant, invité.
Chaque profil règle (1) le ton et les limites des réponses, (2) un filtre pour les images ; les fonctionnalités accessibles viennent de features.py.
« user » garde le nom historique des comptes déjà créés (= adulte)."""
import contextvars

PROFILES: dict[str, dict] = {
    "admin": {"label": "Administrateur", "hint": "Accès complet, réglages, autres comptes.", "prompt": "", "image_block": ""},
    "user": {"label": "Adulte", "hint": "Utilise EVA normalement, sans les réglages ni le réseau.", "prompt": "", "image_block": ""},
    "teen": {
        "label": "Adolescent",
        "hint": "Comme un adulte, sans terminal, réseau, Docker ni installation ; contenus adaptés à son âge.",
        "prompt": ("Tu parles à un adolescent. Reste bienveillante et claire, explique sans condescendance. Refuse poliment les contenus sexuels, "
                   "violents ou dangereux (drogues, armes, automutilation, jeux d'argent) et propose une alternative ; en cas de détresse, "
                   "encourage à en parler à un adulte de confiance. N'aide pas à contourner un contrôle parental."),
        "image_block": "nsfw, nudity, sexual, gore, blood, violence, weapon, drugs",
    },
    "child": {
        "label": "Enfant",
        "hint": "Réponses simples et rassurantes, pas d'Internet libre, pas de fichiers ni de réglages : jeux, histoires, devoirs, dessins.",
        "prompt": ("Tu parles à un enfant (6 à 12 ans). Utilise des mots simples, des phrases courtes, un ton chaleureux et encourageant. "
                   "Aide pour les devoirs en guidant (explique la méthode plutôt que de donner seulement la réponse), raconte des histoires, fais des jeux et des devinettes. "
                   "Ne parle jamais de sexualité, de violence, de drogues, d'armes ni de sujets effrayants : réponds gentiment que tu ne peux pas en parler et propose "
                   "d'en discuter avec un parent. Ne demande jamais et ne retiens jamais d'informations personnelles (nom de famille, adresse, école, téléphone) ; "
                   "si l'enfant en donne, dis-lui de ne pas les partager en ligne. N'aide pas à contourner les règles de la maison."),
        "image_block": "nsfw, nudity, sexual, gore, blood, violence, weapon, scary, horror, drugs, realistic person",
    },
    "guest": {
        "label": "Invité",
        "hint": "Accès minimal : questions simples, météo, recherche ; rien de personnel.",
        "prompt": "Tu parles à un invité de la maison : reste générale, ne divulgue aucune information personnelle sur les habitants ni sur la maison.",
        "image_block": "nsfw, nudity, sexual, gore, violence",
    },
}
ROLES = tuple(PROFILES)


def label(role: str) -> str:
    return PROFILES.get(role, PROFILES["user"])["label"]


def system_note(role: str) -> str:
    p = PROFILES.get(role)
    return f"[Profil de la personne : {p['label']}] {p['prompt']}" if p and p["prompt"] else ""


def image_block(role: str) -> str:
    return (PROFILES.get(role) or {}).get("image_block", "")


user_var: contextvars.ContextVar[str] = contextvars.ContextVar("eva_user", default="")
role_var: contextvars.ContextVar[str] = contextvars.ContextVar("eva_role", default="admin")
