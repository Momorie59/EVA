# Ouvrir EVA à des amis, chez eux

EVA reste 100 % locale : rien n'est envoyé à un service extérieur. Pour que des amis s'y connectent depuis chez eux, il faut seulement un chemin réseau jusqu'à ton NAS. Voici les options, de la plus sûre à la moins sûre.

## 1. Un VPN privé (recommandé) : Tailscale ou WireGuard
- Rien n'est ouvert sur Internet : seuls les appareils invités peuvent voir le NAS.
- Les appels voix/vidéo du Salon passent en direct entre les appareils : aucun serveur supplémentaire.
- Installe Tailscale sur le NAS et sur les appareils de tes amis (ou partage le NAS avec leur compte Tailscale), puis ils ouvrent `https://<nom-ou-IP-Tailscale-du-NAS>:8443/`.
- Dans EVA › Paramètres › Sécurité & données › Connexion sécurisée, ajoute ce nom dans « Accéder à EVA sous un nom de domaine » si tu l'utilises, et fais installer le certificat d'EVA à tes amis (bouton de téléchargement dans la même carte).

## 2. Redirection de port sur ta box (à éviter sans précautions)
- Ouvre un seul port (celui d'EVA, 8443) vers le NAS. N'ouvre jamais 80/443 (OMV) ni 8000/9443.
- Obligatoire avant : connexion par comptes (un compte par personne), double authentification pour les administrateurs, mots de passe de 12 caractères minimum (déjà imposé), HTTPS actif, nom déclaré dans la carte HTTPS.
- Donne à tes amis le profil « Invité » ou « Adulte » selon la confiance, et ajuste par personne dans Paramètres › Sécurité & données › Fonctionnalités. Évite « Code & système » pour les amis.
- Pour les appels à travers Internet, ajoute un serveur de mise en relation dans la page Salon (STUN simple ; TURN pour les réseaux stricts, par exemple un conteneur `coturn`).

## Ce qui protège EVA
- Le jeton `EVA_AUTH_TOKEN` n'est plus jamais copié dans l'interface (ancienne version : il l'était, donc n'importe quel visiteur obtenait l'accès administrateur). **Si tu as ouvert EVA hors de chez toi avant cette mise à jour, change `EVA_AUTH_TOKEN` dans `.env` et relance `docker compose up -d --build`.** Regarde aussi le journal d'accès (Paramètres › Sécurité & données) : les connexions « (jeton) » sont celles qui passaient par ce jeton.
- Connexion par compte, journal d'accès, alerte Telegram contre la force brute, profils et fonctionnalités par personne, NIS2 (voir NIS2.md).

## Certificat et page blanche
EVA fabrique son propre certificat. Il n'est valable que pour les noms qu'elle accepte : l'adresse du NAS, les noms de ton réseau local (`.local`, `.lan`) et ceux que tu déclares dans la carte HTTPS. Un nom non déclaré donne une erreur de connexion sécurisée ou une page blanche.
