# EVA — l'assistante IA locale de la famille

EVA est une assistante personnelle **qui tourne chez toi** : sur un NAS ou un mini-PC pour l'application, et sur une
machine avec carte graphique pour l'IA (Ollama). Tes conversations, tes documents et ta maison restent sur ton réseau.
On lui parle par écrit ou à la voix, depuis le navigateur, le téléphone ou un **satellite** (micro et haut-parleur
dans une pièce, ton PC, un téléphone Android).

> **État du projet** : utilisé au quotidien par une famille, en évolution rapide. Interface et documentation en
> français. Les fonctions qui dépendent de matériel ou de comptes que nous n'avons pas pu tester sont signalées dans
> [`TODO.md`](TODO.md). Retours et contributions bienvenus (voir plus bas).

## Ce qu'elle sait faire

- **Converser et agir** : plus de 80 outils (fichiers, web, météo, listes, agenda, maison…) avec permissions
  (automatique / sur accord / interdit), confirmation des actions sensibles, choix automatique du modèle.
- **Voix** : reconnaissance Whisper et voix Piper en local (voix Microsoft en option), mot d'éveil « EVA »,
  une centaine de langues.
- **Satellites** : installés depuis l'interface pour Windows, Mac, Linux / Raspberry Pi et Android ; pause,
  diagnostic, mise à jour et désinstallation à distance. Sur un PC, EVA peut lire l'écran et cliquer, avec ton accord.
- **Maison** : appareils (Tuya, Shelly, Hue, WiZ, Yeelight, Tasmota, WLED, MQTT, Home Assistant…), scènes, routines,
  présence, imprimantes, Chromecast.
- **Famille** : comptes adulte / adolescent / enfant / invité, données séparées par personne, salon (messages,
  appels), carnets partagés, listes de courses, livre de recettes, wiki, papiers et échéances (Paperless).
- **Images** : création et retouche (serveur Stable Diffusion sur la machine IA).
- **Mémoire et apprentissage** : « retiens que… », résumé des conversations la nuit, leçons tirées de ses erreurs,
  et, si tu le permets, **évolution de son propre code** (contrôlée, annulée toute seule si elle marche moins bien).
- **IA en ligne en option** : OpenAI, Claude, Gemini, Mistral, Groq, OpenRouter… en plus ou en secours du serveur local.
- **Sécurité** : HTTPS local, double authentification, journal d'accès, quotas, contrôle NIS2, code exécuté en bac à sable.

## Ce qu'il faut

| Machine | Rôle | Minimum conseillé |
|---|---|---|
| NAS ou mini-PC Linux avec Docker | EVA : interface, cœur, base, voix | 4 cœurs, 8 Go de RAM, 30 Go libres |
| Machine avec carte NVIDIA | Ollama (modèles de langage), images | 6 Go de mémoire vidéo (GTX 1060) |

Une seule machine suffit si elle a la carte graphique. Sans carte graphique, EVA marche avec un petit modèle
(lent) ou avec une IA en ligne.

## Installation rapide

```bash
git clone https://github.com/Momorie59/EVA.git eva && cd eva
cp .env.example .env
nano .env        # OLLAMA_HOST (adresse du serveur IA), EVA_HOST (adresse de cette machine), POSTGRES_PASSWORD
docker compose up -d --build
```

Puis ouvre `https://<adresse-de-la-machine>:8443`, accepte le certificat local et crée le compte administrateur
(Paramètres › Sécurité & données). La voix française se télécharge toute seule au premier démarrage.

Le pas-à-pas complet (serveur IA, modèles, premier lancement, mises à jour, dépannage) est dans
**[`MANUEL-INSTALLATION.md`](MANUEL-INSTALLATION.md)**. Pour s'en servir : **[`MANUEL-UTILISATION.md`](MANUEL-UTILISATION.md)**.

EVA n'utilise que le port **8443** (les ports 80 et 443 restent libres pour l'interface d'un NAS comme OpenMediaVault).

## Organisation du dépôt

| Dossier | Contenu |
|---|---|
| `eva-core/` | le cœur (FastAPI, Python) : conversations, outils, mémoire, maison, satellites |
| `eva-interface/` | l'interface web (React, application installable) |
| `eva-voice/` | voix : Whisper (comprendre) et Piper / Microsoft (parler) |
| `eva-scanner/` | détection des appareils et des téléphones sur le réseau |
| `eva-android/` | l'appli satellite Android (Kotlin, compilée par GitHub Actions) |
| `eva-imagegen/` | serveur d'images, à installer sur la machine IA |
| `eva-airllm/` | facultatif : très gros modèles sur petite carte graphique (très lent) |
| `caddy/` | la porte d'entrée HTTPS |
| `plugins/` | tes plugins (outils ajoutés sans toucher au code), avec un exemple |

Autres guides : [`MAISON.md`](MAISON.md), [`PAPIERS.md`](PAPIERS.md), [`IMAGES.md`](IMAGES.md),
[`ACCES-A-DISTANCE.md`](ACCES-A-DISTANCE.md), [`HTTPS-SANS-AVERTISSEMENT.md`](HTTPS-SANS-AVERTISSEMENT.md),
[`NIS2.md`](NIS2.md), [`PLUGINS.md`](PLUGINS.md) (ajouter des outils sans toucher au code), [`CHARTE.md`](CHARTE.md) (règles de conduite d'EVA), [`CHANGELOG.md`](CHANGELOG.md).

## Développer

L'architecture (schéma) est décrite dans [`eva-core/README.md`](eva-core/README.md). Les tests tournent à chaque envoi sur GitHub (Actions › Tests).

```bash
# Cœur
cd eva-core && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# Tests (une base PostgreSQL de test est nécessaire)
EVA_TEST_PG=postgresql://eva@127.0.0.1:5432/postgres python -m pytest tests -q

# Interface
cd eva-interface && npm install && npm run dev
```

## Contribuer

Les tickets (bugs, idées) et les demandes de fusion sont les bienvenus. Merci de décrire le matériel concerné
(NAS, carte graphique, appareils) et de joindre le journal (`docker logs eva-core --tail 80`) sans données
personnelles. Pour une faille de sécurité : voir [`SECURITY.md`](SECURITY.md).

## Licence

EVA est un logiciel libre sous licence **GNU AGPL-3.0** ([`LICENSE`](LICENSE)) : tu peux l'utiliser, l'étudier,
la modifier et la redistribuer ; si tu proposes une version modifiée à d'autres personnes (y compris par le réseau),
tu dois leur donner accès à son code source.
