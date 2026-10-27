# À faire — Projet EVA

Pas d'ordre imposé sauf mention contraire. Coché = fait et vérifié (voir
CHANGELOG.md pour le détail).

## À valider chez toi (non testable ici)
- [ ] Profil « Rapide » avec `qwen3.5:4b` réel (vitesse sur la GTX 1060, qualité des appels d'outils)
- [ ] Pont Hue réel (appairage, couleurs, scènes) ; présence avec les vrais téléphones (MAC aléatoire désactivée)
- [ ] OBS, Discord, Instagram, Twilio avec de vrais comptes (testés contre des serveurs simulés)
- [ ] Navigateur : premier lancement du conteneur `chromedp/headless-shell` par Docker sur le NAS (testé avec un Chromium local)
- [ ] Satellite sur un vrai Raspberry Pi (micro USB, enceinte, sensibilité du micro, service au démarrage) et sur Windows
- [ ] Reconnaissance musicale avec une vraie clé AcoustID et une vraie chanson ; gestes pouce levé/baissé avec la vraie caméra
- [ ] Éveil local du satellite avec une vraie voix (« Éva » prononcé à la française : à comparer avec le mode Whisper) ; Spotify, Alexa via Home Assistant, Chrome EVA et pilotage du PC sur ton vrai PC ; appel conversationnel réel (accès à distance + Twilio)
- [ ] Satellite 1.1 sur ton PC : premier mot entendu plus tôt, phrases d'attente (trop ? pas assez ?), deux satellites dans la même pièce (un seul répond), gestes devant ta vraie webcam (sensibilité, faux départs), « clique sur … » avec la mise à l'échelle Windows (125/150 %), tableau au repos ; colis avec ta vraie boîte Gmail
- [ ] Relevés de TA banque (format CSV/OFX réel), enceintes Google réelles (annonces), fenêtre flottante sur ton PC Windows, Godox via Home Assistant
- [ ] « EVA comme Claude » avec le vrai modèle : usage spontané de `plan_taches`, `poser_question`, `document_creer` par qwen2.5:7b (qualité des documents produits)
- [ ] Claude Desktop branché sur EVA (serveur MCP) via `mcp-remote` et le certificat d'EVA
- [ ] Wiki et recettes sur le NAS : envoi de vraies photos et vidéos depuis le téléphone, impression de la liste de courses, lien de partage ouvert par un ami (accès à distance)
- [ ] Compilation de nuit avec le vrai modèle (durée, qualité des fils)
- [ ] Papiers intégrés : vrais documents, dépôt en masse (centaines de fichiers), dossiers surveillés et droits (uid 1000), point papiers du matin, confirmation de `papiers_marquer` dans l'interface (voir PAPIERS.md)
- [ ] Langues : détection Whisper réelle (italien, anglais…), téléchargement automatique des voix Piper depuis Hugging Face, qualité de la voix italienne
- [ ] `docker compose up -d --build` : builds et premier démarrage réels
- [ ] Bac à sable de projets avec le vrai Docker (python:3.12-slim), partage Samba, Home Assistant réel
- [ ] Images : valider eva-imagegen v2 sur la GTX 1060 réelle (vitesse sd-turbo / SD 1.5, mémoire avec Ollama, déchargement, modification par zone avec CLIPSeg, téléchargements de modèles, mise à jour depuis EVA)
- [ ] Mémoire des fichiers : qualité du rappel avec `nomic-embed-text` réel (ajuster `EVA_RECALL_MIN`)
- [ ] Maison : détection réseau réelle (eva-scanner en réseau hôte), Yeelight/WiZ/Kasa réels, Tuya réel (import cloud + local), Shelly/Tasmota/WLED/MQTT, imprimante IPP réelle, Wake-on-LAN depuis le conteneur
- [ ] Réseau : analyse approfondie (`docker pull instrumentisto/nmap`), accès SSH root à tes machines
- [ ] Quotas, cloisonnement, « Mes données » et mémoire avec de vrais comptes (ami, enfant) ; agent de code installé sur le NAS et essayé avec `qwen2.5:7b` (qualité des modifications)
- [ ] `qwen2.5:7b` : échéances retrouvées après « Réanalyser tous les papiers »
- [ ] Carte « Vitesse du serveur IA » : rechargements réels sur la GTX 1060 (choisir le modèle rapide en conséquence)
- [ ] Souvenirs automatiques et fil conducteur avec le vrai modèle (qualité des résumés et des faits retenus)
- [ ] Mise à jour 26 : appli Android sur ton téléphone (lien / QR, mains libres, voix d'EVA, sonnerie, pause, mise à jour proposée) ; désinstallation à distance d'un satellite Windows et Linux ; raccourcis pause / reprise
- [ ] Mise à jour 24 : installation d'un satellite depuis l'interface sur ton PC Windows (fichier .cmd, Python via winget), sur un Mac et sur le Raspberry Pi ; mise à jour automatique du satellite à la version suivante ; routines avec tes vrais capteurs Home Assistant ; TV/Chromecast réelle (YouTube) ; voix italienne choisie
- [ ] Mise à jour 23 : mode opérateur sur ton vrai PC Windows (satellite 1.2, option -Ecran ; mise à l'échelle 125/150 %, saisie dans Chrome/bloc-notes, pause avant « Envoyer »), qualité des décisions avec qwen2.5:7b
- [ ] Photo de recette dessinée par eva-imagegen réel ; rappels qui sonnent sur le satellite et Telegram ; « chaque matin à 7 h 30… » créé depuis la conversation ; déplacer un vrai rendez-vous Google
- [ ] `llama3.1:8b` renvoie bien des `tool_calls` (nombreux outils : la sélection par tour limite l'encombrement) ; qualité de llava

## Reporté (à lancer seulement sur demande)
- [ ] Regrouper les conteneurs Docker
- [ ] Mot d'éveil openWakeWord côté serveur, streaming audio continu (Whisper GPU et appli installable : faits)
- [ ] Carte « profil utilisateur », intégration GitHub, modèles de projet, quota disque
- [ ] Voix : essais des langues et des voix (reporté à ta demande)
- [ ] PHP / Node / MariaDB dans le bac à sable de projets

## Prochain chantier
- [ ] Lancer le banc d'essai (Évolution) avec qwen2.5:7b, llama3.1:8b et une IA gratuite : corriger les phrases « mauvais outil »

## Idées
- [ ] Journal des outils exécutés par EVA dans le journal d'accès (aujourd'hui : appareils et SSH), alertes sur échecs de connexion répétés
- [ ] Courses : additionner les quantités (« 1 l de lait » + « 2 l de lait ») ; choix du bac de l'imprimante
- [ ] Afficher une image ou une recette sur la TV (Chromecast)
- [ ] EventBus, continuer à découper `main.py` (démarrage, tour de conversation)

## Fait
- [x] Appli satellite Android ; désinstallation des satellites (à distance et par commande) ; pause / reprise ; durées d'installation
- [x] Satellite installable depuis l'interface (Windows, Mac, Linux) et mis à jour tout seul ; remplacer un ingrédient d'une recette ; banc d'essai des outils ; corbeille des conversations ; voix par langue ; listes privées et rayons ; routines (heure, capteurs) ; TV/Chromecast ; main.py allégé
- [x] EVA fait au lieu de dire « je ne peux pas » : mode opérateur sur le PC, photos de recettes, rappels/minuteurs, tâches auto depuis la conversation, agenda (déplacer/supprimer), carnets, budget, demandes d'évolution ; sélecteur de modèles compact ; manuels
- [x] Le reste de Jarvis : parler sans attendre (phrase par phrase), phrases d'attente, un seul satellite répond, filtre avant de parler, colis, tableau au repos, écran du PC (voir, cliquer), gestes de la main sur le PC
- [x] Dernières fonctions de Jarvis : cockpit finances (privé), suivi de contenus, Google Home/Chromecast en direct, fenêtre flottante sur le PC, Godox via Home Assistant
- [x] Le meilleur de Jarvis : éveil local sur satellite, Spotify, annonces (satellites + Alexa), pilotage du PC, « mon Chrome EVA », budget cloud, appels conversationnels, agendas iCal, raccourcis téléphone, briefing PDF, style majordome
- [x] « EVA comme Claude » : plan visible + vérification, questions à choix, vrais fichiers Word/PDF/PowerPoint/Excel (création et modification), recherche approfondie avec sources, tâches en fond ; prudence de Jarvis (actions critiques), appels qui se présentent, scènes de départ/arrivée
- [x] Ce que Jarvis avait en plus : profil rapide, Hue direct, présence, OBS, Discord, Instagram, appels/SMS, EVA serveur MCP, navigateur piloté, satellites vocaux, reconnaissance musicale, gestes oui/non
- [x] Modules Wiki et Livre de recettes (partage, PDF, liste de courses, invités), compilation automatique des conversations la nuit
- [x] Prudence des outils, suppression en masse, projets et fil conducteur des conversations, souvenirs automatiques, mesures de vitesse, réponses instantanées
- [x] Cloisonnement des fichiers entre personnes, quotas de messages, « Mes données » (export, effacement), mémoire structurée, agent de code (Aider)
- [x] HTTPS via Caddy (EVA_HOST)
- [x] Interface V1 (avatar 3D, logo animé, thème Jarvis)
- [x] EVA CORE + connexion Ollama (streaming)
- [x] Agent Harness (outils filesystem, permissions, confirmation)
- [x] Mémoire persistante (Postgres)
- [x] Docker-compose complet (4 services)
- [x] STT/TTS (eva-voice) — code fait, modèles à télécharger chez toi
- [x] Gestion Markdown automatique des projets
- [x] Comportement proactif — premier monitor (workspace)
- [x] Authentification par jeton partagé
- [x] Multi-utilisateurs (admin/user) + journal d'accès type bastion
- [ ] Idée : conversations/projets privés par utilisateur, journal des outils exécutés par EVA, alertes sur échecs répétés
- [x] Connexion identifiant + mot de passe (facultative) ; correctif jeton écrasé par l'id de conversation (clé `eva.auth`)
- [x] Outils météo et Docker en lecture seule
- [x] Outil terminal (`terminal_run`, toujours CONFIRM)
- [x] Monitoring système (`system_stats`, CPU/RAM/disque)
- [x] Widgets branchés sur de vraies données (météo, docker, système)
- [x] File d'attente pour les messages reçus pendant une confirmation
- [x] Vue "Projets"/"Mémoire" du dashboard, branchée sur de vraies données
- [x] Outils Web (`web_search`, `web_fetch`, via DuckDuckGo sans clé d'API)
- [x] Actions Docker (`docker_restart`, `docker_stop`, `docker_start`, CONFIRM)
- [x] Limites de ressources réelles sur `terminal_run` (mémoire, CPU,
      kill de tout l'arbre de processus au timeout)
- [x] Outils Git (`git_status`, `git_log`, `git_diff`, `git_commit`)
- [x] Monitor de seuils système (`SystemThresholdMonitor`, CPU/RAM/disque)
- [x] Faire tourner EVA CORE en non-root (referme le trou `RLIMIT_NPROC`,
      vérifié : fork-bomb bloqué en non-root, passe intégralement en root)
- [x] Vision (caméra) : `EVA_VISION_MODEL`, `CameraPanel`, court-circuite
      le Harness pour les messages avec image
- [x] Permissions contextuelles (`permission_for`) sur `fs_write`/`fs_append`
      (chemins sensibles : .env, docker-compose.yml, config/, secrets/...)
- [x] Protection SSRF sur `web_fetch` (IP privées/loopback/link-local
      bloquées, redirections revalidées une par une)
- [x] Vrai streaming de la réponse finale du Harness (`stream_decide`,
      plus de fausse frappe mot par mot)

## Prochaines briques possibles (suite à la relecture d'architecture)

- [ ] EventBus (découpler les monitors/futures intégrations du WebSocket
      — à faire avant Home Assistant/agenda/email)
- [ ] Mémoire structurée (préférences/faits/décisions interrogeables,
      distincte de l'historique de conversation brut)
- [ ] `STATUS.md`/`ARCHITECTURE.md`/`EVIDENCE.md` à la racine (cosmétique,
      basse priorité)
- [ ] Réduire `main.py` : la logique (vision, confirm_gate, boucle
      principale) grossit dans un seul fichier — à décomposer avant que
      ça devienne un vrai problème

## Prochaines briques possibles (reste du brief initial)

**Plus d'outils pour le Harness**
- [ ] `Home Assistant` : lire/contrôler la maison (remplacerait le widget
      Docker par un vrai widget maison)
- [ ] `agenda`, `email`

**Comportement proactif — aller plus loin**
- [ ] D'autres monitors : agenda du lendemain, mails importants (une fois
      les outils correspondants prêts)
- [ ] Personnalité du prompt système : plus proactive, pince-sans-rire

**Solidité / sécurité**
- [ ] Streaming audio continu (VAD) plutôt qu'un blob complet à la fin de
      l'enregistrement
- [ ] `docker_ps`/`docker_logs`/`terminal_run` : à tester en conditions
      réelles sur le NAS (pas de daemon Docker dans l'environnement où ce
      code a été écrit)
- [ ] `weather_get` : à tester en conditions réelles (Open-Meteo non
      joignable depuis ce sandbox, mais parsing validé contre le vrai schéma)
- [ ] `web_search` : à tester en conditions réelles (DuckDuckGo non
      joignable depuis ce sandbox, mais parsing validé contre une fixture
      fidèle à la structure réelle — `web_fetch`, lui, a été testé contre
      de vraies pages)
- [ ] Réfléchir à un vrai sandbox pour `terminal_run` (mémoire/CPU/nombre
      de process sont réellement bornés maintenant ; reste : vraie
      isolation filesystem/réseau, ex: bubblewrap ou une VM légère)

- [ ] Vision (`EVA_VISION_MODEL`) : pipeline testé en process (vraie image,
      vrai WebSocket, app réelle) mais avec un modèle vision mocké — pas
      de vrai modèle multimodal disponible dans ce sandbox pour tester
      la qualité des réponses elles-mêmes

**Interface**
- [ ] (rien de bloquant listé pour l'instant — voir les outils ci-dessus
      pour ce qui alimenterait de nouveaux widgets, ex: Home Assistant)

**À valider chez toi (série NIS2 / profils / skills / serveur IA)**
- [ ] Lister un vrai dépôt de skills (ex. `orchestra-research/AI-research-SKILLs`) : testé avec des réponses GitHub simulées ; la limite anonyme de l'API GitHub est de 60 requêtes/heure.
- [ ] Double authentification avec ton application TOTP, et l'alerte Telegram après 5 échecs.
- [ ] Statistiques du serveur IA : adresse du dashboard (Paramètres › Services) si ce n'est pas `http://<IP d'Ollama>:7842`.
- [ ] Profils enfant / adolescent : la qualité du filtrage dépend du modèle local ; ce n'est pas un contrôle parental certifié.
- [ ] Génération d'images « qui dérive » : en attente d'un exemple de séquence et de la sortie de `/health`.
