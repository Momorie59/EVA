# Changelog — Projet EVA

Format libre, pensé pour se relire vite en reprenant le sujet. Le plus
récent en haut.

## 2026-10-28 — EVA évolue toute seule, journal d'activité, préparation du dépôt public
- **Évoluer toute seule** (Apprentissage › Corrections de son code) : la nuit, EVA applique au plus une de ses propositions de code qui a passé les contrôles, passe le banc d'essai avant et après, et revient en arrière toute seule si elle ne démarre plus ou répond moins bien. Fichiers de sécurité toujours intouchables.
- **Ses modifications survivent aux mises à jour** : au redémarrage sur une nouvelle version, elles sont rejouées sur le nouveau code (celles qui ne s'appliquent plus sont laissées de côté et notées).
- **Journal** refait : tout ce qu'EVA a fait (outils de toutes les conversations, erreurs, apprentissage, évolution, tâches en fond, routines, satellites, démarrages), filtrable. Avant, il ne montrait que la conversation ouverte.
- **Dépôt public** : licence AGPL-3.0, README et manuel d'installation pour tout le monde, `SECURITY.md`, lien « code source » dans le menu ; données personnelles retirées des exemples et des tests ; `EVA_PROPRIETAIRE` (prénom pour « l'assistante de… ») ; voix française téléchargée toute seule au premier démarrage ; AirLLM seulement sur demande (`--profile airllm`) ; clé de signature Android lue depuis l'environnement. INSTALL.md, REINSTALL.md et UPDATE.md fusionnés dans MANUEL-INSTALLATION.md.

## 2026-10-28 — Images : sélection multiple
- Images › Galerie › **☑ Sélectionner** : coche plusieurs images (ou « Tout sélectionner ») puis Supprimer, Garder / Ne plus garder ou Enregistrer d'un coup.

## 2026-10-28 — Satellite PC qui ne revenait pas après une mise à jour (satellite 1.7)
- Windows : après sa mise à jour automatique (ou « Redémarrer » depuis EVA), le satellite pouvait s'éteindre au lieu de redémarrer (relance `os.execv` incompatible avec la tâche planifiée). Il confie maintenant la relance à un petit programme détaché qui relance la tâche « EVA Satellite ».
- Gardien : la tâche planifiée vérifie toutes les 5 minutes que le satellite tourne et le relance sinon (ajouté tout seul aux installations existantes en administrateur). « EVA arrêter » est respecté jusqu'à « EVA démarrer » ou au prochain démarrage du PC ; les raccourcis du bureau sont mis à jour.
- Maison › Satellites : la carte prend toute la largeur (les boutons ne débordent plus) et un satellite hors ligne l'indique clairement, avec quoi faire.

## 2026-10-28 (nuit, suite) — EVA apprend seule, voix et écoute revues

- **Apprendre de ses erreurs** (Apprentissage) : EVA note ses ratés (correction de la personne, « je ne peux pas », outil en erreur, 👎). Chaque nuit (heure réglable) ou sur demande, une IA au choix (serveur local, IA du marché, IA gratuites) indique l'outil qui aurait dû servir ; la leçon n'est gardée que si le banc d'essai confirme que le modèle du jour la suit. Les leçons s'appliquent toutes seules aux demandes semblables (outil proposé + consigne), visibles, désactivables, supprimables. Fonction absente → demande d'évolution ; en option, proposition de correction du code (page Évolution, jamais appliquée sans accord). Ratés effacés avec « Mes données ».
- **Écoute** : la langue est d'abord détectée, puis la phrase est transcrite dans cette langue avec le prompt français (avant : transcription « auto » sans prompt, moins juste) ; une autre langue n'est retenue que si Whisper en est sûr à 80 %. **Satellites PC** : le petit modèle ne sert plus qu'à repérer « EVA », la demande est retranscrite avec le grand modèle ; volume du micro normalisé ; fin de phrase après 0,9 s de silence (au lieu de 0,7 s). Satellite 1.6.
- **Voix** : la voix suit la langue du TEXTE (une phrase française courte ne part plus avec une voix étrangère quand Whisper s'est trompé de langue — d'où l'« accent bizarre ») ; lecture préparée (21 h 45 → « 21 heures 45 », °C, %, €, unités, abréviations, émojis, Markdown) ; **voix neuronales Microsoft en option** (Paramètres › Voix › Moteur : bien plus naturelles, le texte lu part chez Microsoft ; Piper en secours).
- **Appli Android 3** : reconnaissance du téléphone (Google) et voix du téléphone par défaut, comme l'appli Momory ; voix et écoute d'EVA en option.
- **Choix de l'IA sur l'accueil** (premier onglet EVA), le même que dans Conversation ; il crée la conversation si besoin.
- **Plus de fenêtre météo** : ni fenêtre flottante, ni carte dans la conversation (à réactiver dans Paramètres › Apparence) ; et les confirmations s'affichent dans la page au lieu des fenêtres du navigateur.

## 2026-10-28 (nuit) — « Liste mes recettes »

- `recette_chercher` sans recherche (ou « toutes », « mes recettes ») liste tout le livre de recettes.
- Une demande qui vise un domaine d'EVA (recettes, wiki, carnets, rappels, listes, papiers, agenda, budget…) sans parler de fichier ne propose plus les outils de fichiers : EVA listait le dossier de travail au lieu des recettes.
- Banc d'essai : « Liste moi mes recettes » et « Crée-moi un coloriage de banane » ajoutés.

## 2026-10-28 (nuit) — Coloriages

- « Crée-moi un coloriage de banane », « une page à colorier de dinosaure », « un mandala » : reconnus comme des demandes d'image (EVA répondait qu'elle n'avait pas d'outil d'images). Un coloriage est dessiné au trait noir sur fond blanc, sans couleur ni ombre, prêt à imprimer. Aussi reconnus : bande dessinée, carte d'anniversaire, carte de vœux, invitation, étiquettes.

## 2026-10-28 (soir) — Piloter et diagnostiquer les satellites

- **🩺 Diagnostic** d'un satellite (Maison › Satellites) : connexion, niveau du micro / seuil, phrases entendues, comprises, « EVA » reconnu, dernière phrase, dernière erreur, journal ; **test haut-parleur + micro** (il parle, bipe, écoute 4 s, montre ce qu'il a compris). Le satellite écrit aussi `satellite.log` (Windows le lance sans fenêtre : ses messages étaient perdus) et note les phrases entendues sans « EVA ».
- Mot d'éveil plus tolérant (« Ava », « Èva »… tels que Whisper les écrit).
- **Piloter** : icône EVA à côté de l'horloge (Windows, Linux : Parler, Pause/Reprendre, Ouvrir EVA, Redémarrer, Arrêter), raccourcis « EVA démarrer » / « EVA arrêter » en plus de pause / reprise, et depuis EVA : 🎙 Parler, ↻ Redémarrer, ⏹ Arrêter.
- **Windows en administrateur** : le `.cmd` demande l'élévation lui-même, installe chez la personne (pas chez le compte administrateur) et lance le satellite à l'ouverture de session avec les droits les plus élevés (tâche planifiée « EVA Satellite ») ; désinstallation en conséquence.
- **Désinstaller d'une machine** : vrais boutons de téléchargement et « Copier la commande » (le texte n'était pas cliquable), bouton 🧹 permanent, et adresses en https (elles sortaient en http:// sur le port 8443).
- Appli Android 2 : Parler / Redémarrer / Arrêter depuis EVA. Satellite PC 1.5.1.

## 2026-10-28 (après-midi) — Satellite Android, désinstallation, pause

- **Appli satellite Android** (`eva-android/`, Kotlin + Compose, compilée par GitHub Actions, signée avec la clé du projet) : écoute « EVA… » en mains libres (option « seulement en charge »), bouton Parler (aussi dans la notification), voix d'EVA (ou celle du téléphone), réponses au fil de l'eau, accords à la voix, annonces, « fais sonner mon téléphone » (`telephone_sonner`, même en silencieux), pause depuis EVA, configuration par lien `evasat://config?…` ou QR code, certificat d'EVA reconnu, mise à jour proposée par l'appli. L'APK est servie par EVA (`/api/public/satellite/eva-satellite.apk`).
- **Désinstaller un satellite** : Supprimer dans Maison › Satellites ; allumé, il se désinstalle lui-même (démarrage automatique, dossier ; service système via sudo sans mot de passe sinon mis en sommeil) ; éteint, EVA donne la commande par système (`desinstaller-windows.cmd`, `desinstaller-mac.sh`, `desinstaller-linux.sh`, aussi copiés dans le dossier du satellite).
- **Pause / reprise de l'écoute** : depuis EVA (gardé à la reconnexion), raccourcis « EVA pause » / « EVA reprise » sur le bureau, « EVA, pause » à la voix, interrupteur Android. En pause, rien n'est écouté ni envoyé ; les annonces passent.
- **Durées d'installation** affichées dans l'assistant selon le système et les options.
- **Windows** : installateur embarqué dans le `.cmd` et téléchargements par Python (Windows PowerShell 5 refusait la connexion chiffrée d'EVA) ; `satellite.json` sans BOM.
- Satellite PC 1.4.1.

## 2026-10-28 — Satellite installable depuis EVA, routines, listes privées, TV

- **Installer un satellite depuis l'interface** (Maison › Satellites › Ajouter / Installer / Réinstaller) : système (Windows, Mac, Linux / Raspberry Pi, détecté d'office), usage (ordinateur ou enceinte de pièce), options. Windows : fichier `Installer-EVA-<nom>.cmd` à double-cliquer (Python 3.12 installé par winget s'il manque, compatible PowerShell 5) ; Mac : nouvel installateur `installer-mac.sh` (LaunchAgent, autorisations écran/accessibilité) ; Linux : apt, dnf, pacman, zypper. Chaque préparation crée une nouvelle clé (`/api/home/admin/satellites/{id}/installateur`).
- **Satellite 1.3 : mise à jour automatique** depuis EVA (au démarrage et toutes les 6 h ; fichier vérifié avant remplacement, ancienne version gardée, modules manquants installés, redémarrage). Version affichée dans la liste. **Souris et clavier sur Mac** (Quartz, écran Retina) en plus de Windows et Linux.
- **Recettes** : `recette_modifier` sait **remplacer un ingrédient partout** (liste et étapes, singulier/pluriel) : « remplace les moules par des crevettes » ; ajouter des ingrédients ou des étapes ; ne recrée plus la recette.
- **Banc d'essai des outils** (Évolution) : 44 phrases types envoyées au modèle choisi, outil choisi comparé à l'attendu, rien d'exécuté ; distingue « mauvais outil », « aucun outil » et « pas proposé par EVA ».
- **Corbeille des conversations** : une conversation supprimée reste 30 jours (🗑 dans l'historique : récupérer, effacer, vider), puis est effacée toute seule. Elle ne sert plus aux recherches ni au fil conducteur.
- **Voix par langue** (Paramètres › Voix) : une voix Piper par langue choisie dans le catalogue officiel, téléchargée à la demande, ▶ pour l'écouter.
- **Listes privées** (🔒) à côté des listes de la famille ; **courses rangées par rayon** du magasin ; partage vers le téléphone, copie, envoi Telegram, impression recto-verso.
- **Routines de la maison** (Maison › Routines, `routine_creer/lister/gerer`) : à une heure (jours choisis) ou sur un capteur Home Assistant → scène, appareil, annonce, message. Actions sensibles jamais lancées seules.
- **TV et enceintes Google** (`tv_diffuser`) : vidéo YouTube (lien ou recherche), lien direct (radio, mp3, vidéo, image), pause, lecture, suivant, muet, avancer, volume.
- `main.py` allégé : les tours avec image (vision, création, retouche) et les post-its passent dans `chat_medias.py`.

## 2026-10-27 (nuit) — EVA fait au lieu de dire « je ne peux pas »

- **Mode opérateur** (`pc_operateur`) : « prends la main et fais-le » sur le PC. Boucle regarder l'écran → décider → agir (clic, saisie, touches, ouvrir une appli ou un site), 12 étapes par défaut, étapes affichées dans la carte de plan, bouton Arrêter. Pause obligatoire avant toute action qui envoie, paie, commande, publie, supprime ou installe (reprise avec `accord_pour`, valable une fois) ; fenêtres de banque, impôts, santé et mots de passe refusées. Satellite 1.2 : textes visibles avec leur position, clic par coordonnées, saisie (Unicode sous Windows, xdotool sous Linux), raccourcis clavier.
- **Recettes avec photo** : EVA dessine la photo (serveur d'images), reprend la dernière image de la galerie ou une photo envoyée. Nouveaux `recette_modifier` (champs, photo, l'ancienne photo est effacée) et `recette_partager` (lien public).
- **Wiki** : illustration en tête de page. **Contenus** : changer le titre et les plateformes.
- **Rappels et minuteurs** (`rappel_creer/lister/annuler`) : dates en français (« dans 10 minutes », « demain à 8 h », « lundi prochain »), répétition jour / semaine / heure ; sonnent dans la conversation (carillon, notification, lecture à voix haute), sur Telegram et sur le satellite de la pièce. Sauvegardés et effacés avec « Mes données ».
- **Tâches automatiques depuis la conversation** : `agent_planifier`, `agent_lister`, `agent_gerer` (lancer, pause, reprise, suppression).
- **Agenda** : déplacer et supprimer un rendez-vous Google. **Carnets** : lister, lire, écrire. **Budget** : noter une dépense (compte Espèces), fixer un budget.
- **Demandes d'évolution** : quand EVA ne sait pas faire, elle le note (`evolution_demander`, compteur si redemandé) ; liste dans Évolution, à cocher « faite ». La consigne d'EVA lui demande de combiner ses outils avant de répondre « je ne peux pas ».
- **Choix du modèle** plus court : raccourcis Automatique / IA gratuites, filtres, ★ favoris, 🕘 récents, services repliés.

## 2026-10-27 (soir) — Manuels

- `MANUEL-UTILISATION.md` : se servir d'EVA (parler, accords, modèles et IA gratuites, pages, voix, maison, satellites et gestes, mémoire et vie privée, paramètres, téléphone, petits soucis).
- `MANUEL-INSTALLATION.md` : serveur IA, NAS, `.env`, premier lancement, mises à jour par archive ou git, accès (certificat, application, à distance), satellites et leurs options, dépannage.
- Liste des conversations : réessaie toute seule quand EVA redémarre (elle restait vide jusqu'au rechargement).

## 2026-10-27 (fin d'après-midi) — Rotation modèle par modèle

- La rotation des IA gratuites passe maintenant **modèle par modèle** (les quotas sont souvent comptés par modèle) : un service ajouté avec 10 modèles donne 10 essais au lieu d'un. Chaque modèle se coche / décoche et se déplace.
- Les IA gratuites ajoutées mais inutilisables restent visibles avec la raison : « clé manquante », « exclu : entraînement », « service désactivé ». Compteur « N modèles dans la rotation ».
- Quota du jour (« Daily … », « Retry after 87494 seconds ») : tout le service est mis de côté le temps annoncé ; limite par minute : seulement ce modèle.
- Message plus clair quand tout est épuisé (ajouter d'autres services ou réessayer plus tard), avec l'heure de reprise de chacun.

## 2026-10-27 (après-midi) — IA gratuites automatiques, nouvel affichage des modèles

- **IA gratuites (automatique)** : nouveau modèle dans le sélecteur. EVA essaie les IA gratuites ajoutées, dans l'ordre choisi, et passe toute seule à la suivante si l'une a atteint son quota (429 : jusqu'au délai annoncé, ou quelques heures pour un quota du jour), refuse la clé (1 h), n'a plus de crédits (24 h), a retiré le modèle (30 min) ou est en panne (2 min). Une réponse déjà commencée n'est jamais recommencée ailleurs.
- Paramètres › IA du marché › « IA gratuites automatiques » : ordre (↑ ↓), état de chacune (prête, a répondu à…, en pause jusqu'à… et pourquoi), exclusion par défaut des services qui entraînent leurs modèles avec tes messages, et option « les utiliser aussi quand mon serveur IA ne répond pas ».
- **Nouveau choix du modèle dans la conversation** : un bouton (modèle choisi, ou « Automatique » et le dernier modèle utilisé) ouvre une liste rangée par origine — 🖥️ mon serveur IA, 🆓 IA gratuites, ☁️ IA du marché, 🐢 AirLLM —, avec recherche, noms lisibles (« Qwen 2.5 7B » au lieu de « qwen2.5:7b ») et badges (⚡ en mémoire, 🛠 outils, 👁 images, 🌐 Internet, ⚠️ entraînement, 🐢 très lent).
- **Paramètres** : listes de modèles du choix automatique rangées par origine avec noms lisibles ; modèles installés présentés en lignes (nom lisible, nom technique, taille, badges, en mémoire) ; les IA en ligne n'y apparaissent plus avec un bouton « Supprimer ».
- Serveur IA éteint : les IA gratuites et du marché restent proposées dans le sélecteur.

## 2026-10-27 — IA gratuites (liste awesome-free-llm-apis)

- Paramètres › Intelligence › IA du marché › **IA gratuites** : 16 services à accès gratuit permanent (Gemini, Mistral, Groq, OpenRouter, NVIDIA, Cohere, Ollama Cloud, OVHcloud…) d'après la liste communautaire [awesome-free-llm-apis](https://github.com/mnfst/awesome-free-llm-apis) (licence CC0 ; copie livrée avec EVA, « Mettre la liste à jour » en un clic).
- « Ajouter » préremplit le fournisseur : adresse compatible OpenAI (corrigée pour Gemini, Cohere, Ollama Cloud, Cloudflare), modèles de texte, prix 0 ; lien vers la page où obtenir la clé gratuite. Certains services marchent **sans clé** (OVHcloud, LLM7, Kilo Code) : EVA n'envoie alors aucune clé.
- Avertissements : services qui peuvent entraîner leurs modèles avec tes messages (Mistral, OpenRouter, Kilo Code ; Gemini : pas en Europe), conditions (vérification d'identité, usage non commercial…).

## 2026-10-26 (fin de matinée) — AirLLM : un choix, plus un repli d'office

- AirLLM n'est plus utilisé automatiquement quand le serveur IA ne répond pas : seulement si on le choisit dans le sélecteur de modèle de la conversation. Le repli automatique reste possible, case à cocher dans Paramètres › Intelligence › AirLLM (décochée par défaut). Serveur IA éteint et case décochée : EVA dit simplement qu'il est injoignable.

## 2026-10-26 (matin) — Bouton « Arrêter », choix du modèle AirLLM, fin des réponses en boucle

- **Bouton « Arrêter »** (conversation et panneau de discussion) : coupe tout de suite la réponse en cours, y compris un calcul d'AirLLM (nouvelle route /stop du service, vérifiée à chaque mot) ; la réponse coupée reste affichée, marquée « réponse arrêtée ».
- **Réponses qui récitaient les documents en boucle (AirLLM)** : l'entrée trop longue était coupée PAR LA FIN — la question disparaissait et le modèle continuait le texte des documents joints. Désormais on retire les plus vieux échanges puis on raccourcit les consignes, la question et « assistant: » restent toujours ; longueur maximale portée de 512 (AirLLM par défaut) à 3072 jetons ; pénalité de répétition.
- **Choix du modèle AirLLM dans l'interface** (Paramètres › Intelligence › AirLLM, administrateurs) : liste conseillée avec tailles et avertissements (mémoire, disque), « autre modèle Hugging Face », modèles présents sur le disque avec suppression. Un dossier de couches par modèle ; téléchargements gardés sur le volume (HF_HOME=/models/hf).
- Passages de documents en double dans les souvenirs : une seule copie.

## 2026-10-26 — AirLLM réparé, et utilisable sans carte graphique

- **Panne** : « cannot import name 'GenerationMixin' » — pip installait transformers 5.x, qui exige torch 2.6 alors que l'image a torch 2.4 (torch était alors désactivé). Versions figées : airllm 2.11.0, transformers 4.44.2, optimum 1.23.3, accelerate 0.34.2, numpy < 2.1.
- **Sans carte graphique (le NAS)** : AirLLM tourne sur le processeur (nombres 32 bits, sans compression : la compression 4/8 bits exige une carte NVIDIA) ; le dossier des couches est créé s'il manque (sinon « No such file or directory »). /health indique le matériel utilisé.
- Vérifié : service AirLLM complet sur processeur avec un petit modèle Qwen2 (chargement, découpe en couches, réponse).

## 2026-10-25 — Vitesse de réponse, gestes et écran du PC, colis (le reste de Jarvis)

- **Parler sans attendre** (satellites) : nouvelle route `/api/satellite/demander_flux` : la réponse arrive phrase par phrase et le satellite dit la première pendant que la suite s'écrit ; la phrase suivante est synthétisée pendant que la précédente est jouée (plus de blanc entre les phrases). Les anciens satellites gardent l'ancienne route.
- **Jamais de silence** (`parole.py`, comme `docs/latency.md` de Jarvis) : un outil qui prend plus d'une seconde → phrase d'attente immédiate et variée (« Je regarde la météo. », « Je parcours votre courrier. » en majordome) ; au-delà de 7 s, une phrase de patience ; modèle lent à démarrer → « Voyons… ». Aussi dans l'interface quand on parle à EVA (jamais à l'écrit). Rien de tout ça n'est enregistré dans la conversation.
- **Satellites plus rapides** : mode léger comme l'interface vocale (une phrase de conversation se passe des ~4000 tokens d'outils), modèle rapide préféré, personnalité appliquée (majordome compris), modules éteints respectés.
- **Un seul satellite répond** (`/api/satellite/eveil`) : quand plusieurs entendent la même phrase, celui qui l'entend le mieux (parole / bruit de fond) répond ; les autres ne la transcrivent même pas (Whisper soulagé).
- **Filtre avant de parler** (`confidentialite.py`) : clés et jetons, mots de passe, cartes et IBAN masqués à l'oral ; dans une annonce, aussi mails et téléphones.
- **Suivi des colis** (`gmail_colis`) : « où en sont mes colis ? » d'après les mails d'expédition et de livraison (en route, point relais, livraison aujourd'hui, livré), publicités écartées.
- **Tableau au repos** dans la fenêtre flottante du PC : heure, météo, prochains rendez-vous, colis, musique en cours, post-its (droits du compte du satellite) ; clic = caché 30 min.
- **Écran du PC** : `pc_ecran_voir` (texte lu par OCR sur le PC + description par le modèle de vision ; la capture n'est pas gardée) et `pc_ecran_cliquer` (clic sur un texte visible, accord à chaque fois, jamais sur une fenêtre de banque, impôts ou santé).
- **Gestes de la main sur le PC** (MediaPipe, comme Jarvis) : main ouverte = lecture/pause, poing = EVA se tait, 2 doigts = onglets, 3 doigts = audio, index = souris, deux mains = zoom, pouce levé/baissé = oui/non à EVA. L'image ne quitte pas le PC.
- Installateurs du satellite : options `fenetre`, `tableau`, `ecran`, `gestes` (Linux : lancement dans la session graphique) ; satellite 1.1.
- Tests : 135 sur Postgres ; vérifiés en vrai : satellite contre EVA (première phrase dite à 1,8 s au lieu d'attendre la fin), lecture d'écran et clics réels sur un écran virtuel (OCR rapidocr), MediaPipe 1.1 chargé avec le modèle de la main, fenêtre au repos ↔ conversation.

## 2026-10-24 (tard) — Les cinq dernières fonctions de Jarvis

- **Cockpit finances** (module « Finances personnelles », Paramètres › Modules) : comptes, import des relevés CSV (formats des banques françaises) et OFX sans doublon, catégories devinées puis apprises à chaque correction, budgets par catégorie, tableau de bord (revenus, dépenses, reste du mois, soldes, 6 mois, plus grosses dépenses, dépassements). **Strictement privé** : chacun ne voit que ses comptes, pas même l'administrateur. EVA répond en lecture seule (« combien j'ai dépensé en restaurants ce mois-ci ? »).
- **Suivi de contenus** (module « Suivi de contenus ») : idée → script → tournage → montage → programmé → publié, plateformes (YouTube, Instagram, TikTok, Twitch…), date prévue, notes, lien ; privé ou partagé avec la famille ; tableau par étape et calendrier ; annonce Discord d'une publication, stats Instagram ; « note une idée de vidéo : … », « qu'est-ce que je publie cette semaine ? ».
- **Google Home, Nest et Chromecast en direct** : volume, pause, lecture, arrêt, ce qui joue ; ajout d'un clic depuis la détection réseau ; les annonces sont aussi dites par les enceintes Google de la pièce, avec la voix d'EVA (audio servi 5 minutes par eva-scanner, réseau privé seulement).
- **Fenêtre flottante sur le PC** (satellite, "fenetre": true) : ce que tu as dit et la réponse d'EVA, toujours au premier plan sans prendre le clavier, position ou 2e écran au choix ; **mode silencieux** (« EVA, mode silencieux » / « EVA, reparle »).
- **Lumières vidéo Godox** : via l'intégration Home Assistant « Godox BLE Mesh » (pas d'API officielle) ; EVA règle la température de couleur en kelvins (« lumière vidéo en 5600 K ») ou en %.
- Modules : mécanisme généralisé (adresses et outils d'un module éteint coupés partout).
- Tests : 123 sur Postgres ; parcours vérifiés dans le navigateur (import d'un relevé et tableau de bord, tableau et calendrier des contenus) et fenêtre flottante sur un écran virtuel.

## 2026-10-24 (nuit) — Le meilleur de Jarvis dans EVA

- **Mot d'éveil sur le satellite** (comme openWakeWord) : option « local » à l'installation ; détecteur sherpa-onnx sur le satellite, rien n'est envoyé au NAS avant « EVA », Whisper confirme ; sensibilité réglable. (L'ancien mode reste par défaut : à comparer chez toi.)
- **Spotify** : liaison sans secret (PKCE), « mets du Daft Punk », pause, suivant, volume, « mets la musique sur l'enceinte du salon » (Premium pour piloter la lecture) ; les chansons reconnues rejoignent la playlist « Reconnu par EVA ».
- **Annonces** : « annonce dans la cuisine / partout que le dîner est prêt » → satellites EVA **et** Echo Alexa (via Home Assistant, intégration Alexa Media Player).
- **Pilotage de l'ordinateur** où tourne un satellite : applis autorisées par le propriétaire du PC, site web, volume, muet, lecture/pause/suivant, verrouillage, extinction ou redémarrage (accord, dans 1 minute, annulable), état du PC, **reconnaissance de la musique jouée sur l'ordinateur** (son système). Nouvelle fonctionnalité « Ordinateurs » (adultes).
- **« Mon Chrome EVA »** (le vrai Chrome de Jarvis, version sûre) : Chrome visible avec un profil EVA (tes connexions y restent) ; onglets, ouvrir, lire, résumer, traduire ; cliquer et remplir avec accord à chaque fois ; banque, impôts, santé et organismes en lecture seule ; jamais de mot de passe. (Depuis Chrome 136, Google interdit de piloter le profil principal : d'où le profil dédié.)
- **Budget des IA du marché** : prix par million de jetons, plafond mensuel par fournisseur, dépense affichée ; une fois le plafond atteint, retour automatique au modèle local jusqu'au mois suivant (avec alerte).
- **Appels où EVA converse** : « appelle Maman et demande-lui si elle vient dimanche » — EVA se présente comme assistante automatique, écoute, répond (8 échanges au plus), puis résumé + transcription dans la conversation. Nécessite l'adresse publique HTTPS d'EVA (accès à distance) ; requêtes Twilio signées et vérifiées.
- **Agendas iCal** par personne (vacances scolaires, Outlook, iCloud, club…), événements récurrents compris ; utilisés aussi par le briefing.
- **Raccourcis du téléphone** : « Dis Siri, dis à EVA… » (jeton personnel, réponse lue par le téléphone ; seulement les actions sans accord, comme Jarvis).
- **Briefing du matin en PDF** envoyé sur Telegram (telegram_notify sait joindre un fichier).
- **Style « Majordome »** (pince-sans-rire, vouvoie) : « passe en mode majordome ».
- Tests : 119 sur Postgres (dont un vrai Chrome piloté par le satellite, une conversation téléphonique simulée avec signatures Twilio, un agenda .ics récurrent, le canal d'ordres des satellites).

## 2026-10-24 (soir) — EVA comme Claude : plan, questions, vrais fichiers, recherche avec sources, tâches en fond ; prudence de Jarvis

- **Vrais fichiers** (`documents.py`) : « fais-moi le compte rendu en Word / PDF / PowerPoint / Excel » → `document_creer`. Titres, listes, tableaux, gras, sauts de page ; une partie = une diapositive ; Excel avec en-têtes figés, filtres, nombres, montants en €, pourcentages, dates et formules. Chaque fichier est **rouvert et vérifié** avant d'être proposé (bulle de téléchargement 📝 📕 📊 📗). `document_modifier` : copie « (modifié) » d'un Word ou d'un Excel déposé (remplacer un texte, ajouter une partie, écrire des cellules, ajouter des lignes) — l'original n'est jamais touché.
- **Questions à choix** (`poser_question`) : quand une précision change vraiment le résultat (format, destinataire, période…), EVA affiche des boutons ; on clique, ou on écrit sa réponse. Sur Telegram, à la voix et sur les satellites, elle pose la question en texte.
- **Plan de travail visible** (`plan_taches`) : pour une tâche en plusieurs étapes, une carte 📋 montre les étapes cochées au fil du travail (gardée avec la conversation). **Vérification avant de conclure** : si EVA veut conclure avec des étapes non cochées, elle est relancée une fois pour les finir (ou dire pourquoi). Avec un plan, jusqu'à 16 tours d'outils au lieu de 4.
- **Recherche approfondie avec sources** (`recherche_approfondie`) : plusieurs requêtes en parallèle, deux pages au plus par site, meilleurs passages de chaque page ; la réponse cite [1], [2]… et se termine par la liste des sources.
- **Tâches en fond** (`tache_de_fond`, `taches_fond.py`) : « compare les pompes à chaleur en fond et préviens-moi » — EVA travaille seule (plan, recherche, fichiers), une tâche à la fois, sans poser de question ; ce qui demande un accord est listé au lieu d'être fait. Le compte rendu et les fichiers arrivent dans la conversation, avec une notification (Telegram si réglé). Pastille « ⚙️ tâche en fond » dans l'en-tête de la conversation, panneau avec plan, résultat et annulation. 3 tâches au plus par personne, 45 min au plus.
- **Prudence de Jarvis** : appeler, envoyer un e-mail, publier sur Discord, cliquer ou remplir sur un site, supprimer un fichier, commande SSH = accord demandé **à chaque fois** (plus de « Toujours autoriser » pour ces actions, anciens « toujours » ignorés). Les appels et SMS commencent par « ici EVA, l'assistante automatique de la maison, de la part de … ».
- **Présence → scènes** : Maison › Présence : une scène quand tout le monde part (tout éteindre…) et une quand quelqu'un rentre dans la maison vide ; jamais une scène qui touche un appareil sensible ; notification.
- Construction : les nouvelles dépendances (Word, Excel, PowerPoint, PDF) sont dans une couche à part, sans paquet Debian (police des PDF fournie par reportlab).
- Tests : 109 sur Postgres (question cliquée ou écrite, PDF téléchargé, plan relancé, tâche en fond complète, action critique jamais mémorisée) ; parcours complet vérifié dans le navigateur avec un modèle simulé.

## 2026-10-24 (suite) — Ce que Jarvis avait en plus : vitesse, Hue, présence, OBS, Discord, Instagram, appels, MCP, navigateur, satellites, musique

- **Profil de vitesse « Rapide »** (Paramètres › Modèles) : les demandes courantes passent par un petit modèle (`qwen3.5:4b` par défaut, téléchargeable d'un clic), le code, les analyses et la vision gardent le modèle principal. La « réflexion » des modèles qui pensent (qwen3, deepseek-r1…) est coupée pour répondre tout de suite (`EVA_REFLEXION=1` pour la garder).
- **Philips Hue sans Home Assistant** (`hue.py`) : Maison › Appareils › Philips Hue : appuyer sur le bouton du pont, « Appairer », cocher les lampes à ajouter. Allumer, éteindre, luminosité, couleur, blanc chaud/froid ; les scènes de l'appli Hue se lancent dans Maison › Scènes ou à la voix (« lance la scène Lecture du salon »). La clé du pont n'est jamais renvoyée à l'interface.
- **Présence à la maison** (`presence.py`, eva-scanner) : Maison › Présence : chaque personne coche son téléphone parmi les appareils vus sur le wifi (balayage toutes les 2 min). « Qui est à la maison ? » répond tout de suite, sans modèle. Absent = pas vu depuis 15 min. Conseil : désactiver l'adresse MAC aléatoire du téléphone pour le wifi de la maison.
- **Diffusion et appels** (`connecteurs.py`, Paramètres › Services connectés, administrateur) — lire est libre, agir demande l'accord :
  - **OBS Studio** (obs-websocket 5, inclus dans OBS ≥ 28) : état, lancer/couper le live ou l'enregistrement, pause, replay, changer de scène.
  - **Discord** par webhooks (aucun bot à héberger) : « annonce le live sur Discord » ; les mentions @everyone sont neutralisées.
  - **Instagram** (compte pro/créateur, jeton de 60 jours) : abonnés, j'aime et commentaires des dernières publications. EVA ne publie rien.
  - **Appels et SMS** (Twilio) : « appelle Maman pour lui dire que le dîner est prêt » — EVA appelle et lit le message (ou envoie un SMS), **uniquement** vers les contacts listés par l'administrateur, jamais un numéro dicté.
  - Nouvelle fonctionnalité « Diffusion » dans les droits (OBS, Discord, Instagram) ; les appels relèvent de « Messages ».
- **EVA comme serveur MCP** (`mcp_serveur.py`) : Claude Desktop, Cursor ou un autre assistant peuvent utiliser les outils d'EVA (`POST /api/serveur-mcp`, MCP 2025-06-18). Un jeton par client, rattaché à un compte EVA (ses droits et les modules s'appliquent), outils cochés un par un ; un outil d'action ne s'exécute sans accord que si l'administrateur l'a coché pour ce client. Chaque appel est noté dans le journal d'accès ; révocation immédiate. Configuration Claude Desktop prête à copier.
- **Navigateur d'EVA** (`navigateur.py`) : un Chromium sans écran dans son propre conteneur (`chromedp/headless-shell`, ~150 Mo, téléchargé au premier usage, arrêté après 10 min sans usage). EVA ouvre une page (sites dynamiques compris), la lit, fait une capture d'écran (montrée dans la conversation, effacée après 7 jours) ; **cliquer** et **remplir un formulaire** demandent l'accord. Jamais de mot de passe, de code ni de carte bancaire ; Internet seulement (ni le réseau de la maison ni le NAS, redirections comprises) ; aucune session gardée.
- **Satellites vocaux** (`satellites.py`, Maison › Satellites) : un micro + un haut-parleur par pièce (Raspberry Pi, vieux PC, Windows). Mot d'éveil « EVA » (« EVA » seul : un bip, puis 8 s pour parler), transcription par le Whisper d'EVA, réponse lue par sa voix. Chaque satellite connaît sa pièce (« allume la lumière » = celle de la pièce), agit avec les droits du compte choisi, et pose à voix haute les demandes d'accord (« Tu confirmes ? » → « oui » / « non »). Installateurs Linux/Raspberry (service au démarrage) et Windows ; certificat d'EVA vérifié ; supprimer le satellite coupe son accès.
- **« C'est quoi cette musique ? »** (`musique.py`) : 12 s d'écoute, empreinte Chromaprint (`fpcalc`, ajouté à l'image eva-core) comparée à AcoustID / MusicBrainz ; l'extrait n'est jamais conservé ni envoyé, seule l'empreinte part. Bouton 🎵 près du micro, phrase à voix haute, et sur les satellites. Clé AcoustID gratuite dans Services connectés.
- **Gestes** : pouce levé 👍 / baissé 👎 devant la caméra = « oui » / « non » à une demande d'accord (en plus des balayages, paume, V et poing déjà présents).
- Tests : 103 sur Postgres (dont un vrai Chromium piloté sur un site de test, un faux serveur OBS avec mot de passe, une vraie empreinte fpcalc) ; parcours vérifiés dans le navigateur (Hue, Présence, Services connectés, serveur MCP, Satellites, 🎵).

## 2026-10-24 — Wiki, livre de recettes, compilation automatique des conversations

- **Modules** (Paramètres › Modules, administrateur) : une case pour activer le **Wiki**, une pour le **Livre de recettes**. Coupé (par défaut) = absent du menu, des pages et des outils d'EVA ; les données restent sur le NAS. Allumé = droits habituels par personne (nouvelles fonctionnalités « wiki » et « recettes » ; les invités ont les recettes en lecture).
- **Wiki** (`wiki.py`) : espace **Famille** (tout le monde lit et complète, chaque version gardée avec auteur et date, restauration en un clic, refus d'écraser une modification faite entre-temps) et espace **Personnel** (privé, pas même l'administrateur). Markdown avec barre d'outils et aperçu, photos et vidéos, liens `[[Autre page]]` (proposition de créer la page si elle n'existe pas), recherche, impression. EVA lit le wiki pour répondre (`wiki_chercher`, `wiki_lire`) et n'écrit que sur demande, avec accord (`wiki_ecrire`).
- **Livre de recettes** (`recettes.py`) : photo, résumé, temps, difficulté, catégorie, étiquettes, ingrédients (une ligne « 200 g de farine », compris automatiquement), étapes avec photo et minuteur, vidéo envoyée sur le NAS ou lien YouTube, notes, recette privée. Belle mise en page (cartes, vue détaillée), quantités recalculées pour le nombre de personnes (« ½ citron », « 2 gousses d'ail », jamais « 312 ½ g »).
  - **Liste de courses** en un clic (quantités pour le nombre de personnes choisi), avec **impression** si une imprimante est réglée.
  - **Partage** : lien en lecture seule vers une jolie page (téléphone, impression), avec ajusteur de personnes ; lien révocable. Les amis doivent pouvoir joindre EVA depuis Internet (ACCES-A-DISTANCE.md).
  - **PDF** : une recette ou le **livre entier** (couverture, sommaire, une recette par page) via « Imprimer › Enregistrer en PDF ».
  - **Invités** : un compte « invité » ne voit que la conversation, les listes et le livre de recettes, en lecture.
  - EVA : `recette_chercher`, `recette_lire` (pour N personnes), `recette_courses` (« fais-moi la liste de courses des crêpes pour 6 »), `recette_creer` (« garde cette recette », avec accord).
- **Photos et vidéos** (`medias.py`) : rangées sur le NAS (`wiki/medias`, `recettes/medias`), nom aléatoire de 128 bits qui sert de clé ; jusqu'à 25 Mo par image, 800 Mo par vidéo ; une photo remplacée est effacée.
- **Compilation automatique** (`compilation.py`) : chaque nuit (3 h par défaut, quand personne ne parle à EVA depuis 10 min), le fil conducteur de chaque conversation est mis à jour — courtes comprises — et ce que chacun a dit de lui depuis la veille rejoint sa mémoire. Au début d'une nouvelle conversation, EVA reçoit le résumé des dernières conversations de la personne (14 jours). Paramètres › Intelligence › Compilation : heure, bilan, « Compiler maintenant ».
- Sauvegarde, « Mes données » (export, effacement) : wiki et recettes compris.
- Tests : 87 (dont wiki, recettes, compilation sur Postgres) ; parcours complets vérifiés dans un navigateur (création d'une recette avec photos, courses, partage vu sur téléphone, wiki avec image et lien, compte invité).

## 2026-10-23 (suite) — GitHub dans EVA, autorisations « toujours »

- **Étudier = lire** : quand la demande est d'étudier / analyser / regarder le code, EVA n'a plus que les outils de lecture pour ce tour (plus d'agent de code, de « Créer un projet », d'écriture ni de terminal) : fini la boucle d'outils inutiles.
- **« Analyse complète du code »** : l'agent de code (Aider) ne sert plus qu'à modifier ; une demande d'analyse reçoit l'aperçu réel du projet (répartition par type de fichier, plus gros fichiers, arborescence, fichiers clés). Sans projet cité, EVA prend l'unique projet existant, sinon demande lequel (elle n'invente plus de nom).
- **Mieux comprendre** (`langue.py`) : le langage SMS et les fautes fréquentes (« pkoi », « jai », « ya », « problme »…) sont corrigés avant que EVA décide quoi faire ; un message court qui dépend de ce qui précède (« oui », « fais-le », « et celui-là ? ») est réécrit en phrase complète par le petit modèle rapide et donné au modèle principal comme aide à la compréhension (jamais bloquant, 8 s maximum).
- **« Regarde / étudie le code (du projet) »** : dans une conversation d'un projet (ou en citant le projet), EVA reçoit l'arborescence réelle et le début des fichiers clés, et n'y mêle plus les souvenirs de documents sans rapport (les PDF qui la faisaient dévier).
- **Limites relevées** (par personne, jamais partagées) : 500 sujets appris (au lieu de 40) et 2000 souvenirs (au lieu de 300). Le prompt reste de 40 lignes de mémoire / 2 leçons.
- **Dépôts Git dans un projet** : « décharge eva dans le projet X » (ou dans une conversation rattachée à un projet) clone dans `projets/X/eva`. Page Projets : liste des conversations du projet, « Reprendre » et « Nouvelle conversation dans ce projet ».
- **Mémoire au-delà de 40 souvenirs** : le prompt garde ses 40 lignes, mais y met les 15 plus récents + ceux qui parlent du sujet du message (jusqu'à 300 souvenirs candidats) ; « Relire mes conversations » traite jusqu'à 150 blocs au lieu de 40.
- **Git/GitHub plus robuste** : messages d'échec clairs (jeton expiré, permission manquante, dépôt introuvable, version plus récente sur GitHub, copies divergentes, réseau), délai de clonage porté à 10 min, `safe.directory` posé, envoi de la branche courante même sans amont, refus d'enregistrer un `.env`, une clé privée ou un jeton, et refus d'un dossier de même nom venant d'un autre dépôt.
- **Accord une fois ou pour toujours** : chaque demande d'accord (outils d'EVA, envoi vers GitHub) propose « Autoriser cette fois » (aucune trace), « Toujours autoriser » (EVA ne redemande plus pour cet outil) ou « Refuser ». Les autorisations permanentes sont propres à chaque personne et se retirent dans Paramètres › Sécurité & données › Autorisations. Un refus n'enregistre rien. Les agents planifiés, sans personne pour répondre, n'en profitent pas.
- **GitHub** (Paramètres › Services connectés, administrateur) : jeton personnel gardé sur le NAS (jamais réaffiché, jamais dans une adresse de dépôt), liste de tes dépôts, clonage dans le dossier `depots`, état, historique, différences, commit, récupérer (pull, sans écraser), envoyer (push, avec confirmation une fois ou toujours), retirer la copie locale. EVA peut aussi lire et modifier ces dépôts avec ses outils Git.
- **Dans la conversation** : « es-tu connectée à mon git ? », « vérifie tous mes dépôts » → nouvel outil `github_info` (connexion, tous tes dépôts GitHub, copies locales avec branche et fichiers modifiés). Les outils Git expliquent où sont les dépôts quand le chemin n'en est pas un. Les questions simples (« tu es connectée à mon git ? », « lis mon git », « quels sont mes dépôts GitHub ») reçoivent une réponse directe, sans passer par le modèle (administrateur) ; « fais un commit… » ou « pousse… » restent des actions confirmées. **Citer un dépôt** (« lis le git EVA », « clone mon git salon ») : EVA le clone dans `depots/` s'il n'y est pas encore (lecture seule, rien n'est envoyé) puis résume : branche, derniers commits, fichiers à la racine, début du README. Le mot « git » n'est pas obligatoire quand la phrase cite un de tes dépôts (« clone eva », « extrait eva »).
- **Enregistrer, mettre à jour, envoyer par la conversation** : « enregistre eva : mon message » (commit), « mets à jour eva » (pull sans écraser), « envoie eva sur mon git » (push, avec la demande d'accord *cette fois / toujours*), « enregistre et envoie eva ». Sans nom de dépôt, EVA prend la seule copie qu'elle a ; « enregistre ce fichier » n'est pas pris pour du Git. Un échec est expliqué en clair au lieu de partir vers le modèle.

## 2026-10-23 — Mémoire retrouvée, agents depuis GitHub

- **« Que sais-tu sur moi ? »** est compris sous toutes ses formes (« sur » ou « de », avec ou sans trait d'union) et répond depuis la Mémoire, sans modèle.
- **Relire mes conversations** (bouton dans Mémoire, ou « relis mes conversations ») : EVA relit ce que la personne a dit d'elle autrefois et en garde les faits durables, visibles et modifiables. L'administrateur relit aussi les conversations sans propriétaire ; jamais celles des autres.
- **Skills › Parcourir un dépôt GitHub** liste aussi les fichiers `agents/nom.md` (ex. dépôt ECC, `affaan-m/ECC`) : cochés, ils s'installent comme des skills. Attention : EVA ne présente que 30 skills au modèle ; installe une sélection, pas les 71.
- **Pages coupées en bas** (toutes sauf l'accueil) : le bandeau d'aide au-dessus de la page prenait de la place sans que la page rétrécisse, le bas dépassait de l'écran. La page remplit maintenant l'espace restant (ordinateur, tablette, téléphone) ; vérifié sur les 17 pages à 3 tailles d'écran.
- **Page Skills rangée** : onglets Skills / Agents, recherche, groupes par dépôt (pliables), case « actif » par élément (désactivé = gardé mais EVA ne le propose plus), « tout activer / désactiver / supprimer » par dépôt. Les agents ne comptent plus dans les 30 skills présentés au modèle.
- **Vrais agents** : un agent installé depuis `agents/` est un *rôle* (`kind: agent`). Nouvel outil `role_run` (administrateur) : « fais relire ce fichier par le security-reviewer » → le rôle travaille seul, en **lecture seule** (fichiers, documents ; web si son rôle le prévoit), avec sa consigne d'origine, et renvoie son analyse. Les outils d'écriture et de commande (Write, Edit, Bash) sont ignorés.

## 2026-10-22 (nuit) — EVA apprend toute seule : règles validées et sujets du net

(Les souvenirs sur la personne restent gérés par la page Mémoire ci-dessous ; cette partie s'ajoute.)

- **Règles apprises** : EVA relit tes 👍/👎 (à la demande, ou automatiquement tous les 8 nouveaux avis) et **propose** des règles (« Réponds en une ou deux phrases »). Rien ne s'applique sans ton accord ; une règle appliquée se remet « à valider » ou s'efface d'un clic (retour en arrière).
- **Apprendre du net** : « apprends-moi comment… » ou Paramètres › Apprentissage : EVA cherche, lit quelques pages et écrit un résumé avec ses sources, en tâche de fond ; elle s'en sert ensuite quand le sujet revient.
- Paramètres › **Apprentissage** : voir, appliquer, refuser, effacer ; interrupteur général. Données sur le NAS, séparées par personne, aucune pour les invités.

## 2026-10-22 (soir, suite) — Souvenirs automatiques

- **EVA retient d'elle-même** ce que la personne dit d'elle (prénom, conjoint, enfants, dates importantes, lieu de vie, métier, goûts), sans « retiens que ». Extraction en fond après la réponse, avec le modèle déjà chargé, seulement quand la phrase parle de la personne. Chaque souvenir est marqué « proposé par EVA », annoncé dans la conversation (« 🧠 Retenu : … ») et modifiable dans la page Mémoire. Une précision met à jour le souvenir existant. Jamais de données sensibles (santé, argent, codes, religion, politique). Mémoire coupée : rien n'est gardé.
- **Appels d'outils écrits en texte** (qwen2.5 : `"{'name': 'docs_search', …}"`, syntaxe Python) : reconnus ; un appel inutilisable n'est jamais affiché, EVA redemande une vraie réponse. Un outil retiré pour ce message est refusé même si le modèle l'écrit.
- **Parler de soi** (« mon prénom est…, je suis né le… ») : aucun outil, EVA répond et retient.
- Tests : 69.

## 2026-10-22 (soir) — Vitesse et finitions

- **Pas de rechargement évitable** (`perf.py`) : sur 6 Go, le modèle rapide et le principal ne tiennent pas toujours ensemble. Une petite phrase ne fait plus charger le modèle rapide si le principal est déjà en mémoire (et inversement le fil conducteur prend le modèle déjà chargé).
- **Carte « Vitesse du serveur IA »** (Paramètres › Intelligence) : modèles en mémoire vidéo (et s'ils débordent), rechargements sur la dernière heure, vitesse de lecture/écriture, dernières réponses, conseil si les modèles se remplacent.
- **Réponses instantanées** (`instant.py`, sans modèle) : l'heure et la date, « ajoute du lait et des œufs à la liste de courses », « qu'est-ce qu'il y a sur la liste ? ». Les phrases plus complexes restent pour le modèle.
- **Contexte (num_ctx)** : gardé à 8192 — mesuré : consignes ~1 000 jetons + outils 1 500 à 3 900 jetons ; 4096 couperait les consignes sur les demandes d'action.
- **Interface** : liens cliquables (sources de la recherche web), italique, citations et séparateurs dans les réponses ; bouton « Copier » sur chaque réponse ; suggestions selon l'heure dans le panneau de l'accueil ; bouton Post-it sur une ligne ; les cartes météo/Docker se masquent si la source ne répond pas.
- Tests : 66.

## 2026-10-22 (fin d'après-midi) — Conversations : suppression en masse, projets, fil conducteur ; outils prudents

- **Prudence des outils** (passe complète sur les 87 outils) : après un « je m'appelle Paul » qui avait déclenché `papiers_corriger`.
  - Les messages précédents n'apportent plus que des outils de **consultation** ; un outil qui change quelque chose n'est proposé que si le message **actuel** l'évoque. Une simple conversation (« merci », « je m'appelle… ») n'a aucun outil d'action.
  - Un outil d'action non proposé pour ce tour est refusé même si le modèle connaît son nom.
  - La description de chaque outil d'action rappelle au modèle qu'il ne s'en sert que sur demande explicite.
  - Les récitations de format technique de qwen2.5 (`<tool_response>…`, « The output MUST strictly adhere… ») ne sont jamais affichées : EVA redemande une vraie réponse.
- **Prénom** : « je m'appelle X », « appelle-moi X » sont retenus instantanément (mémoire) ; « comment je m'appelle ? » répond tout de suite ; EVA connaît le nom du compte connecté.
- **Suppression en masse** : mode sélection dans la liste des conversations (☑), « Tout sélectionner », confirmation qui signale les conversations d'autres personnes ; API `POST /api/sessions/supprimer` (liste, toutes les miennes, ou toutes celles d'une personne pour l'administrateur).
- **Projets** : rattacher une ou plusieurs conversations à un projet (sélection ou en-tête de la conversation), filtre par projet, 📁 sur les conversations rattachées. EVA sait que la conversation fait partie du projet.
- **Fil conducteur** (`fil.py`) : EVA n'envoie plus tout l'historique au modèle (avant : 30 derniers messages + tout ce qui a été dit depuis l'ouverture, outils compris, sans limite). Le modèle rapide résume en fond les échanges anciens (objectif, décisions, faits, à faire) ; EVA reçoit ce fil + les 8 derniers messages. Rien n'est perdu (un message non résumé reste envoyé tel quel). Bouton « 📌 Fil » : voir, corriger, compiler maintenant. Fil du projet compilé dans `projets/<slug>/FIL.md` et donné aux conversations du projet. Réglages : `EVA_FIL_FENETRE`, `EVA_FIL_SEUIL`, `EVA_FIL_PLAFOND`.
- Tests : 61 (dont prudence des outils, fil, suppression, projets sur Postgres) ; parcours complet vérifié dans un navigateur.

## 2026-10-22 (après-midi) — Cloisonnement, quotas, mes données, mémoire, agent de code

- **Modèles** : `qwen2.5:7b` principal (meilleur en appels d'outils et en extraction de dates), `llama3.2:3b` rapide pour les phrases courtes (tient à côté sur 6 Go, pas de rechargement). Réglables dans `.env` (`OLLAMA_MODEL`, `EVA_MODELE_RAPIDE`) ; `mettre-a-jour.sh` les applique.
- **Cloisonnement des fichiers** (`acces.py`, `harness/cloisonnement.py`) : une personne non administratrice ne lit, ne liste et ne télécharge que ses projets, ses fichiers déposés, ses photos, ses fichiers livrés et ses images. Les papiers, sauvegardes, skills et fichiers des autres lui sont refusés, au téléchargement (`/api/files/download` → 403 journalisé) comme dans les outils d'EVA. Deux trous bouchés : n'importe quel fichier du workspace était téléchargeable, et les outils fichiers donnaient accès à `papiers.db` et aux sauvegardes.
- **Souvenirs de fichiers** : une personne retrouve ses propres documents et photos dans le rappel automatique (avant : aucun pour un non-administrateur), jamais ceux des autres. Les photos envoyées dans la conversation ont un propriétaire.
- **Quotas par personne** (`quotas.py`, carte « Quotas de messages ») : messages par heure et par jour, par profil (adulte 60/400, ado 40/200, enfant 30/150, invité 15/50) et par personne ; l'administrateur n'a pas de limite. Message clair quand la limite est atteinte.
- **Mes données** (`donnees.py`, carte dans Sécurité & données) : chacun voit ce qu'EVA garde sur lui, récupère tout dans un ZIP (conversations, avis, post-it, carnets, mémoire, réglages sans mot de passe, fichiers, images, projets) ou efface tout (confirmation « EFFACER »). L'administrateur peut le faire pour une personne et supprimer son compte. Les papiers de la famille ne sont pas concernés.
- **Mémoire structurée** (`memoire.py`, page Mémoire › « Ce qu'EVA retient de moi ») : préférences, faits, décisions, à chaque personne les siens. « Retiens que… », « oublie que… », « que sais-tu de moi ? » répondent instantanément ; outils `memoire_*` ; souvenirs actifs joints aux consignes d'EVA ; chacun peut corriger, désactiver, effacer ou couper sa mémoire. Incluse dans la sauvegarde (les anciennes sauvegardes se restaurent toujours).
- **Agent de code gratuit** (`code_agent.py`) : Aider (Apache-2.0) avec le modèle local, installé à la demande (Paramètres › Intelligence › Agent de code, ~650 Mo dans `workspace/.outils`, hors sauvegarde). Outil `code_agent` (confirmation demandée, fonctionnalité « Code & système ») sur un projet : chaque modification est un commit git, EVA rend les fichiers touchés, le diff et la commande pour tout annuler. Un travail à la fois, 15 min maximum, aucune commande shell exécutée.
- Dépôt d'un fichier abîmé (PDF tronqué…) : accepté sans erreur 500.
- **Tests** : 49 (dont 10 d'intégration sur un vrai Postgres et l'application complète : `EVA_TEST_PG=postgresql://… pytest`), un vrai passage d'Aider contre un faux Ollama (`EVA_TEST_AIDER=<venv>`). Non testé sur le NAS réel.

## 2026-10-22 (fin de matinée) — Papiers intégrés à EVA, traitement en masse, toutes les langues

- **Papiers dans EVA** (`eva-core/app/papiers/`, `PAPIERS.md`) : le moteur du majordome tourne maintenant dans eva-core ; plus de conteneur séparé. Paperless-ngx reste le moteur d'OCR et d'archivage, piloté par EVA. Données dans `workspace/papiers/papiers.db` (dans la sauvegarde).
- **Page Papiers** : avancement (dans les dossiers → lus par Paperless → analysés, avec estimation), échéances à venir, papiers à vérifier avec correction, **dépôt multiple par glisser-déposer**, réglages (Paperless avec test de connexion, modèle choisi dans la liste du serveur IA, rythme d'analyse, seuils, confiance).
- **Dossiers surveillés réglables** dans l'interface (navigateur des dossiers du NAS, création de dossier) : envoi par lots de 25 par minute, rangement dans `_importés` / suppression / fichier laissé ; fichiers en cours de copie attendus ; réessais limités.
- **Fonctionnalité « Papiers »** : administrateur seul par défaut, à ouvrir à la demande (jamais d'office à un ami) ; page, API, outils et réponses instantanées sont contrôlés.
- **Toutes les langues** : EVA répond dans la langue de la personne ; Whisper détecte la langue parlée (repli sur le français si une phrase est trop courte pour décider) ; la voix Piper de la langue est téléchargée automatiquement depuis le catalogue officiel la première fois (dès que Whisper l'entend), la voix choisie reste celle de sa langue. Voix du navigateur : suit la langue entendue.
- Tests : 32 (papiers) + 15 (langues). Non testé sur le NAS réel.

## 2026-10-22 (suite) — Papiers : réponses instantanées et dépôt depuis EVA

- « Quelles sont mes échéances ? », « qu'est-ce que j'ai à payer ce mois-ci ? », « point papiers », « des papiers à vérifier ? » : réponse directe du majordome, sans appel au modèle (≈ 0,1 s mesuré contre un vrai majordome, au lieu de deux passages du modèle). Les questions précises passent toujours par le modèle.
- Joindre un fichier avec « range ça dans mes papiers » (ou « papiers », « ajoute au majordome ») l'envoie directement au majordome, qui le transmet à Paperless (nouvelle route `POST /api/documents/deposer` du majordome). Outil `papiers_deposer` pour les autres formulations.
- `papiers_echeances` explique une liste vide au modèle (plus de réponse confuse quand rien n'est encore suivi).
- Tests : 28 (dont dépôt, détection, réponse directe) ; nécessite le majordome v4.

## 2026-10-22 — Papiers : EVA branchée sur le Majordome administratif, charte d'EVA

- **Papiers** (`PAPIERS.md`) : cinq outils `papiers_*` pour interroger le Majordome administratif (Paperless-ngx + extraction des échéances par Ollama) : échéances à venir avec la date où il faut agir (échéance moins préavis), extractions à vérifier, questions sur les documents, et, avec confirmation, marquer une échéance faite/ignorée/validée ou la corriger. Activés seulement si `EVA_MAJORDOME_URL` est renseignée ; proposés au modèle uniquement quand la demande parle d'échéances, contrats, assurances, impôts (France et Italie), garanties.
- **Point papiers du matin** (`PapiersWatchMonitor`) : une fois par jour à `EVA_PAPIERS_HEURE`, EVA annonce les échéances qui passent un seuil (J-30, J-7, J-1, jour J, retard), plus le résumé du mois le lundi ; relayé sur Telegram comme les autres alertes. Le majordome mémorise ce qui a été annoncé (aucun doublon, même après redémarrage) ; une panne n'est signalée qu'une fois par jour.
- **Routage** : une question d'échéance (« préavis », « expire », « à payer »…) va au majordome plutôt qu'à la recherche dans les documents d'EVA ; les réponses tirées des documents sont étiquetées non fiables (`guard.py`).
- **Charte** (`CHARTE.md`) : règles de conduite reprises du cahier des charges OMNIA et adaptées à un assistant familial local, avec pour chacune l'endroit du code qui l'applique. Ajout au prompt système : brouillon ≠ envoi, contenu ≠ ordre, jamais de résiliation/paiement/achat/envoi sans demande explicite et confirmation, réponse en italien si on écrit en italien (écrit seulement, la voix reste française).
- Tests : `eva-core/tests/test_papiers.py` (11 tests, majordome simulé) ; essai de bout en bout contre un vrai majordome alimenté par un faux Paperless/Ollama. Non testé avec de vrais documents.

## 2026-10-21 (fin d'après-midi) — Correction : mise à jour du serveur d'images

- Après « Mettre à jour le serveur d'images », la page attend maintenant que le serveur ait redémarré avec la bonne version, puis rafraîchit toute seule la carte des modèles et l'état du serveur (avant : un seul rafraîchissement trop tôt, la page restait périmée).

## 2026-10-21 (après-midi) — Vidéo par IA expérimentale (LTX-Video)

- Serveur d'images (version 3) : `POST /eva/video`, désactivé par défaut (`install-imagegen.sh --video`). Chargement le temps de la demande seulement, déchargement séquentiel pour une carte de 6 Go, sortie en WebP animé, erreur claire si la mémoire manque. `/health` indique l'état de la vidéo.
- Outil EVA `video_generate` (confirmation demandée, proposé seulement quand on parle de vidéo ou d'animation). Non testé sur une vraie carte : voir IMAGES.md.

## 2026-10-21 (soir, suite) — Installer le certificat en un clic

- Page publique `https://<NAS>:8443/api/https/install` (marche avant la connexion) : installateur Windows `.bat` en un double-clic (sans droits administrateur), certificat à télécharger pour Android, iPhone, Mac, aide Firefox. Lien ajouté sur l'écran de connexion et dans Paramètres › HTTPS. Une seule fois par appareil, sans domaine ni compte.

## 2026-10-21 (soir) — HTTPS sans avertissement

- `./eva-https.sh domain <nom>.duckdns.org <jeton>` : vrai certificat Let's Encrypt (validation DNS via DuckDNS, aucun port à ouvrir), reconnu par tous les navigateurs sans installer de certificat. Voir HTTPS-SANS-AVERTISSEMENT.md. L'accès par IP reste possible.

## 2026-10-21 (suite) — Partage des post-it et des projets entre utilisateurs

- **Post-it** : chaque post-it a un propriétaire. On ne voit que les siens et ceux qu'on a partagés avec soi (bouton 👥 sur le post-it : personnes au choix ou « Tout le monde »). La personne avec qui il est partagé peut le déplacer, le modifier et le valider ; seul le propriétaire le supprime ou change son partage. « Vider » ne touche jamais les post-it des autres. Les anciens post-it restent visibles de tous.
- **Projets** : chaque projet a un propriétaire et peut être partagé (bouton « Partager » sur la carte). Les personnes choisies ouvrent et modifient les fichiers ; seul le propriétaire supprime, restaure ou partage. Un projet non partagé est « introuvable » pour les autres ; l'administrateur voit tout. Les projets créés avant cette version (ou par EVA seule) restent visibles de tous.

## 2026-10-21 — EVA choisit seule comment répondre, recherche web fiable, outils audités

- **Choix automatique** (`intent.py`) : EVA décide seule entre répondre avec le modèle seul (bonjour, rédaction, explication générale), chercher sur le net (fait précis ou récent, personne, jeu, produit, « cherche… »), chercher dans TES documents (« mes factures », « dans le PDF »…) ou utiliser les outils d'action (maison, listes, fichiers…). En mode web, EVA lance elle-même la recherche, lit les 2 meilleures pages, et le modèle résume/explique avec les sources, en un seul passage du modèle (bien plus rapide qu'avant). `docs_search` n'est plus proposé pour une question générale.
- **web_search robuste** : plusieurs moteurs en cascade (SearXNG, DuckDuckGo, DuckDuckGo Lite, Bing), requête vide ou paramètre mal nommé corrigés, messages d'erreur clairs.
- **Appel d'outil écrit en texte** par le modèle (`{"name": "web_search", ...}`) : reconnu, exécuté et jamais affiché.
- **Arguments d'outils normalisés** (`harness/args.py`) : nombre écrit en texte, paramètre mal nommé, paramètre oublié → corrigé ou erreur précise que le modèle peut utiliser pour réessayer.
- **Audit des 77 outils** : aucun ne plante avec des arguments vides, inventés ou nuls (git_log/git_diff sur un dossier absent corrigés).

## 2026-10-18 (nuit, suite 2) — messages privés, carnets partagés, cloisonnement, onglet Conversation
- **Salon : messages privés** (façon Zoom) : clic sur une personne connectée → fenêtre de discussion en bas à droite, visible depuis tous les onglets (y compris pour les profils simples). Une fenêtre repliée montre une **pastille « 1 », « 2 »…** (messages non lus) ; la pastille apparaît aussi sur la ligne de la personne et sur le menu Salon. Le « lu » est gardé côté serveur (synchronisé entre appareils), l'historique privé aussi (200 messages par conversation, visible des deux personnes seulement, pas de l'administrateur). Refus propre si la personne n'existe pas ou n'a pas accès au Salon.
- **Carnets partagés (façon OneNote)** : nouvelle fonctionnalité « Carnets » (📓) : carnets → sections → pages (Markdown, aperçu, enregistrement automatique). Partage par personne, par groupe ou avec tout le monde, en **lecture seule** ou **modification** ; les changements des autres apparaissent tout seuls ; si deux personnes écrivent en même temps, EVA prévient au lieu d'écraser. L'administrateur voit tous les carnets, rangés par personne. Un carnet non partagé reste privé. Ouvert aux adultes et ados par défaut, pas aux enfants/invités (réglable par personne ou groupe).
- **Cloisonnement** : conversations et images étaient déjà séparées par utilisateur ; **fuite fermée** : la recherche dans les documents (et l'outil `docs_search` d'EVA) ne ressort plus les conversations ou fichiers d'un autre utilisateur (seulement les siennes et les dossiers partagés). L'administrateur voit tout. **Vue administrateur par dossiers** : conversations (menu de gauche) et galerie d'images rangées par utilisateur, dossiers repliables.
- **Onglet Conversation** : indicateur « EVA réfléchit… » (orbe animée, étape en cours — « Chercher sur le web… » —, étapes déjà faites, chronomètre, message de patience si ça dure), pastille d'état à côté du titre (Prête / réfléchit / utilise un outil / répond), écran d'accueil avec suggestions, bulles et bouton d'envoi redessinés.
- **EVA et les questions générales** : plus de recherche dans tes documents pour une salutation ou une question de culture générale ; elle cherche sur le web, lit les pages et résume en citant ses sources. Les extraits de documents peu pertinents (score < 0,6) ne sont plus montrés.
- Pas encore fait : partage des post-it à l'écran et des projets entre utilisateurs (les carnets servent à partager des notes ; les projets gardent leur partage réseau, voir PARTAGE-PROJETS.md).

## 2026-10-18 (nuit, suite) — visite guidée et aide
- **Visite guidée de première connexion** : 3 à 5 étapes adaptées au profil (administrateur, adulte, adolescent, enfant, invité) et aux fonctionnalités ouvertes ; elle se ferme avec ✕, « Passer » ou Échap, et n'apparaît qu'une fois par personne (enregistrée côté serveur).
- **Bouton « ? » en haut à droite** (toutes les interfaces) : aide de l'onglet en cours, liste des fonctionnalités de la personne, relance de la visite.

## 2026-10-18 (nuit) — Salon, correctif de sécurité du jeton, HTTPS à distance
- **SÉCURITÉ** : le jeton `EVA_AUTH_TOKEN` était copié dans le JavaScript de l'interface (argument de construction) : n'importe quel visiteur obtenait l'accès administrateur « (jeton) » sans se connecter. Il n'est plus jamais intégré. Sans compte, un écran demande le jeton une fois. **À faire : changer `EVA_AUTH_TOKEN` dans `.env` si EVA a été ouverte hors du réseau local.**
- **Salon** (menu « Au quotidien ») : qui est connecté, discussion écrite (historique gardé), appels voix et vidéo jusqu'à 6 personnes (WebRTC, sur le réseau, sans Internet), micro/caméra, appel qui continue quand on change d'onglet. Fonctionnalité « Salon » activable par personne ou par groupe (adultes par défaut). Serveurs STUN/TURN réglables pour des amis à distance. Image limitée à 640×480 et 700 kbit/s.
- **HTTPS** : EVA répondait vide (page blanche) sous un nom autre que l'IP du NAS. Maintenant les certificats sont faits à la demande pour l'IP, les noms locaux et les noms déclarés (carte HTTPS). Guide : ACCES-A-DISTANCE.md.

## 2026-10-18 (soir tard, suite) — avertissement « site non sécurisé »
- Carte HTTPS : bouton « Télécharger le certificat d'EVA » + mode d'emploi Windows/Android/iPhone/Mac. Une fois installé sur l'appareil, l'avertissement disparaît (le certificat est fabriqué par EVA, rien ne sort sur Internet).

## 2026-10-18 (soir tard) — suggestions Hugging Face, HTTPS depuis EVA
- **Choix automatique des modèles › Suggestions** : EVA interroge Hugging Face et propose, pour chaque rôle (défaut, rapide, code, raisonnement, vision), 3 modèles GGUF classés par popularité, fraîcheur et taille, qui tiennent sur la carte graphique (quantification adaptée, modèles « uncensored »/fusions écartés). On choisit, puis « Installer et utiliser la sélection » télécharge et attribue. Rien n'est installé sans accord. Résultat gardé 30 min.
- **HTTPS activable/désactivable depuis EVA** (Paramètres › Sécurité & données › Connexion sécurisée) : recharge Caddy via Docker, choix gardé et ré-appliqué au démarrage. `./eva-https.sh off|on` reste disponible.

## 2026-10-18 (nuit, correctif) — page blanche du Tableau de bord
- Le dashboard du serveur IA renvoie l'uptime sous forme d'objet : l'affichage plantait toute la page. Corrigé (texte lisible « allumé depuis … »), barre manquante de la carte de stats du chat ajoutée, et un filet de sécurité affiche une carte « Oups / Réessayer » au lieu d'une page blanche si un onglet plante.

## 2026-10-18 (nuit) — villes, fonctionnalités par personne/groupe, guides d'onglets
- **Villes** : liste de villes et ville par défaut modifiables (Paramètres › Services connectés › Villes) ; la météo, le briefing et les questions sans lieu utilisent la ville par défaut ; choix rapide par puces sur le Tableau de bord.
- **Fonctionnalités par personne et par groupe** (Paramètres › Sécurité & données › Fonctionnalités) : voix, internet, images, fichiers, maison, Google, messages, code & système. Chaque profil a une base ; on ajoute/retire par personne ou via des groupes créés (ex. « Famille ») auxquels on rattache des comptes. L'administrateur a toujours tout. Appliqué côté serveur (outils, routes, vérification vocale) et dans l'interface simplifiée (onglets, bouton micro).
- Changement : le profil « Adulte » n'a plus « Code & système » par défaut (à ajouter à la personne ou au groupe).
- **« Ce que tu peux faire ici »** : panneau repliable en haut de chaque onglet listant toutes ses fonctions.

## 2026-10-18 (soir) — Paramètres rangés, menu rangé, NIS2, profils, skills à cocher, agents, serveur IA

**Ajouté**
- **Paramètres refaits** : 7 catégories (Vue d'ensemble, IA, Images, Voix & personnes, Services, Sécurité & données, Apparence) avec recherche ; une seule catégorie affichée à la fois.
- **Menu de gauche rangé** par usage (Au quotidien / Atelier d'EVA / Suivi & avancé replié ; le Tableau de bord reste en haut) ; compatible avec les dispositions « icônes » et « en haut ».
- **Sécurité NIS2** (`NIS2.md`) : contrôle automatique des mesures de l'article 21 avec état et correctif (Paramètres › Sécurité & données), rapport Markdown téléchargeable, **registre d'incidents** avec échéances 24 h / 72 h / 1 mois, **double authentification TOTP** (compatible Google Authenticator, Aegis, 2FAS…), mots de passe de 12 caractères (`EVA_MIN_PASSWORD`), journal conservé 1 an (`EVA_AUDIT_DAYS`), **alerte Telegram** après des échecs de connexion répétés, en-têtes HTTP de sécurité. Aucune valeur juridique.
- **Profils** : Administrateur, Adulte, Adolescent, Enfant, Invité (`profiles.py`) — outils autorisés, ton et limites des réponses, filtre sur les images (négatif ajouté).
- **Skills : parcourir un dépôt GitHub** (Skills › « Parcourir un dépôt GitHub ») : liste exhaustive des SKILL.md (catégories, recherche, descriptions), cases à cocher, « Installer la sélection » ; l'en-tête YAML multi-lignes (`description: >-`) est maintenant compris.
- **Agents plus malins** : « Décris ce que tu veux » → EVA prépare l'agent (nom, consigne, récurrence reconnue en français, outils prévus) ; à l'exécution, seuls les outils utiles à la consigne sont proposés au modèle.
- **Serveur IA dans EVA** : statistiques du dashboard web (port 7842) dans le Tableau de bord avec le thème d'EVA (CPU, RAM, GPU, VRAM, disques, services, consommation + historique), réglage de l'adresse (Paramètres › Services), outil `ai_server_stats`. « Donne-moi les stats » affiche dans la conversation une carte avec le NAS d'EVA et le serveur IA (sans fenêtre flottante). Tableau de bord redessiné : bandeau « Tout va bien / À surveiller », jauges circulaires (NAS et serveur IA), disques, services en pastilles, courbe de consommation.

**Modifié**
- **Plus de fenêtres flottantes** (heure, actualités, météo, briefing, présentations, statistiques) par défaut : EVA répond dans la conversation ; option dans Paramètres › Apparence.
- « Actualités de <sujet> » n'est plus traitée comme les actualités générales du monde ; les questions d'actualité (« actuellement », « en ce moment »…) forcent une recherche web ciblée.

**Test** : suite serveur (369 tests), e2e navigateur (`e2e_v2.py` pour cette série).

## 2026-10-18 (suite) — Modifier les images, onglet Images, modèles d'images, interface standard, mémoire des fichiers, fichiers à télécharger

**Ajouté**
- **Modifier une image** : retouches classiques (Pillow : noir et blanc, sépia, luminosité, recadrage, rotation, texte…, `imageops.py`) et modification par l'IA (`imageedit.py`) : transformation de style (image→image) et **retirer/remplacer/recolorer un détail par le texte** (zone trouvée par CLIPSeg, inpainting) ; dans le chat (photo jointe, « mets-la… » après une image), route `POST /api/images/edit`, outil `image_edit`. Serveur eva-imagegen **version 2** : `/sdapi/v1/img2img` (+ masque), `/eva/edit`.
- **Onglet Images** (créer, envoyer une photo, modifier, galerie filtrée, garder, supprimer) et **purge automatique** (jours / nombre max / « Purger maintenant », images gardées épargnées, passage toutes les 6 h). Création et galerie retirées de Paramètres.
- **Modèles d'images depuis EVA** (Paramètres › Modèles d'images) : catalogue avec verdict selon la carte du serveur, téléchargement avec progression, utilisation, suppression, dépôt libre « auteur/modèle » ; **mise à jour du serveur d'images depuis EVA** (`/eva/update`, jeton obligatoire, contrôle de compilation, sauvegarde, redémarrage ; `docker-compose.override.yml` monte `eva-imagegen/app` dans EVA). `install-imagegen.sh` crée et affiche un jeton.
- **EVA répond à toutes les demandes d'images** : détection élargie (`wants_image`) et garde contre les refus du petit modèle de reformulation (la demande part telle quelle).
- **Interface standard** pour les comptes « utilisateur » (Conversation, Images, Listes) ; l'interface actuelle devient celle de l'administrateur. **Conversations et images privées par utilisateur** (colonne `sessions.owner`, propriétaire dans la fiche de chaque image) ; WebSocket refusé sur la conversation d'un autre.
- **EVA apprend de tes photos et documents** (`knowledge.py`) : photos de la conversation gardées avec description, images déposées décrites par le modèle vision, indexation immédiate, rappel automatique des passages pertinents dans la conversation (seuils `EVA_RECALL_MIN*`).
- **Fichiers à télécharger** : outil `file_deliver` (script `.sh` exécutable avec `#!/bin/bash`, `.py`, texte, ou ZIP de plusieurs fichiers) avec bouton Télécharger dans le chat, en plus de `zip_make`.

**Corrigé**
- `wants_image` : « montre-moi le dossier de photos » ne déclenche plus une création ; le type d'image (logo, affiche…) reste dans le sujet.
- Test e2e d'apprentissage : rouvre l'ancienne conversation (EVA s'ouvre sur une nouvelle).

**À valider chez toi (non testable ici)** : téléchargements réels depuis Hugging Face, vitesse des modèles SD 1.5 / inpainting sur la GTX 1060, premier téléchargement de CLIPSeg, mise à jour du serveur depuis EVA, qualité de rappel avec les vrais embeddings.

## 2026-10-18 — Branche `feature/image-generation` (génération d'images sur le serveur IA et dans EVA)

**Ajouté**
- **`eva-imagegen/`** : serveur d'images (Stable Diffusion via diffusers) pour le serveur IA (GTX 1060 6 Go) : modèle par défaut `sd-turbo` (4 étapes, 512 px), chargement à la demande, **déchargement au repos et déchargement d'Ollama avant de charger** (la carte est partagée), demi-précision, repli en pleine précision si image noire, SDXL par blocs, modèles `.safetensors` déposés dans `models/`. API Stable Diffusion WebUI (`/sdapi/v1/…`) **et** OpenAI (`/v1/images/generations`), `/health`, jeton facultatif. `docker-compose.yml` GPU fourni ; service `eva-imagegen` sur le NAS en option (profil `imagegen`, processeur, lent).
- **EVA** : « Détecter le serveur », état (carte, modèle, chargé/au repos), choix du modèle, étapes/taille automatiques, « à éviter », jeton ; **traduction + enrichissement de la description en anglais** par le petit modèle local (sauté avec AirLLM ou en cas d'erreur) ; « Créer une image maintenant » et **galerie** (miniatures, agrandir, supprimer) dans Paramètres › Génération d'images ; outil d'agent `image_generate` ; `EVA_IMAGEGEN_URL` préréglable. Voir `IMAGES.md`.

**Images dans la conversation** : l'image créée s'affiche maintenant directement sous la réponse d'EVA (clic = agrandir, bouton « Enregistrer »), comme dans ChatGPT, au lieu d'une fenêtre flottante ; elle revient quand on rouvre la conversation (repère `[[image:…]]` rangé avec la réponse, retiré avant d'être donné au modèle). Valable aussi quand l'outil `image_generate` est appelé par l'agent (affichage en direct).

**Corrigé après essai réel** : le script vérifie que Docker donne la carte (test dans l'image), installe le service avant de lancer le conteneur, contrôle la carte dans le conteneur et le redémarre si elle a été retirée ; clé/liste apt du toolkit en 644. EVA : le champ *Modèle* accepte aussi un nom du hub (liste + saisie libre). 10 tests du script.

**Adapté à ton installation (ia-local-automatique)** : `eva-imagegen/install-imagegen.sh` — Docker en réseau hôte (Ollama natif joignable en `127.0.0.1`), service systemd `eva-imagegen.service` après Docker et Ollama, règle ufw limitée au réseau local, modèles sur ton disque de données, vérifications (pilote ≥ 525, NVIDIA Container Toolkit, place), `--dry-run`, `--status`, `--uninstall`. Testé avec de faux docker/nvidia-smi/systemctl/ufw (8 tests).

**Corrigé**
- Une taille d'image invalide envoyée à l'API OpenAI du serveur déclenchait une génération en 512 px au lieu d'une erreur 400.

## 2026-10-16 — Branche `feature/maison-refonte` (détection et ajout des appareils, refonte complète) + HTTPS désactivable

**Corrigé (causes trouvées)**
- Depuis Docker, la détection ne voyait ni MAC, ni diffusions UDP, ni mDNS/SSDP → presque rien n'était reconnu. Nouveau service `eva-scanner` en réseau hôte.
- Tuya local : une ampoule recevait `turn_on(switch=1)` alors qu'elle s'allume sur le DP 20, et la version du protocole était figée à 3.3 → « ça ne répond pas ». Versions essayées une à une (3.3, 3.4, 3.5, 3.2, 3.1), DP déduit, `status()` préalable pour les lampes, diagnostics lisibles (914 clé/version, 901/905 réseau, une seule connexion locale par appareil).
- Recherche automatique désactivée par défaut et interface éclatée entre Réseau et Appareils.

**Ajouté**
- `eva-scanner/` : ARP, mDNS, SSDP, Tuya UDP (6666/6667, déchiffrement), WiZ, Yeelight, Kasa.
- Pilotes **Yeelight, WiZ, TP-Link Kasa**.
- `lan_discovery.py` : candidats fusionnés avec preuves, test avant ajout, ajout depuis ce que le serveur a trouvé, liaison avec un appareil Tuya importé du cloud, adresse IP réparée toute seule, recherche automatique (30 min, Telegram), diagnostics si le scanner est injoignable.
- Interface : Maison › Appareils › « Appareils trouvés sur ton réseau » (nom / pièce / type, Tester, Ajouter, Ignorer, clé Tuya). Ancien code de découverte et routes `/api/net/discover*`, `/api/net/auto*` supprimés (remplacés par `/api/home/discovery/*`).
- **HTTPS désactivable** : `sh eva-https.sh off|on|status` (`caddy/Caddyfile.http`, variable `EVA_CADDYFILE`).

## 2026-10-14 — Mise à jour 20 (nouvelle interface « Crépuscule », post-it)

**Corrigé**
- **Branche `feature/readme-reste-a-faire`** (le « reste à faire » du README) :
  - **Appli installable (PWA)** : manifeste, icônes, service worker (enveloppe de l'interface en cache : EVA s'ouvre même NAS injoignable, API/WebSocket/voix jamais mis en cache), carte Paramètres › Application (bouton d'installation, marche à suivre Android/iPhone/PC). HTTPS requis ; certificat Caddy à installer sur le téléphone (voir `INSTALL.md`). Vérifié en navigateur, y compris hors ligne.
  - **Whisper sur GPU** : `WHISPER_DEVICE=auto` (défaut) prend le GPU NVIDIA s'il est visible, sinon le processeur ; si les bibliothèques CUDA manquent (au chargement ou au premier calcul) il bascule seul sur le processeur et l'indique (`/api/health` › `whisper`). `eva-voice/Dockerfile.gpu` + `eva-voice/docker-compose.gpu.yml` pour le lancer sur le serveur IA.
  - **Isolation de `terminal_run`** : espaces de noms Linux (disque en lecture seule sauf workspace et /tmp, réseau coupé sauf `network=true`, processus invisibles, socket Docker masqué). Testée réellement. Si le noyau/Docker refuse (profil seccomp par défaut), repli sur les limites mémoire/CPU et le résultat dit « isolation limitée » ; `docker-compose.sandbox.yml` l'active. `EVA_TERMINAL_ISOLATION=off` pour la couper.
  - **Nouveaux monitors** : serveur IA local (alerte après 2 échecs, annonce le repli AirLLM, annonce le retour) et âge de la dernière sauvegarde (alerte au-delà de 8 jours, 1 fois par jour).
- **Branche `feature/cloud-providers` — IA du marché en option** : Paramètres › « IA du marché » permet de connecter OpenAI, Claude (Anthropic), Gemini, Mistral, Groq, DeepSeek, OpenRouter ou tout service compatible OpenAI (adresse + clé). Leurs modèles (`cloud:openai/gpt-4o-mini`…) apparaissent dans le sélecteur de la conversation et dans l'attribution du routeur, avec outils, images (si coché) et décompte des jetons. Option « repli » : quand le serveur IA local est indisponible, EVA utilise l'IA du marché (après AirLLM, ou avant si tu coches la préférence). EVA reste locale par défaut : rien ne part sur Internet sans ton choix explicite, et l'interface le rappelle. Les clés sont stockées dans la base d'EVA, jamais renvoyées par l'API ni écrites dans les erreurs ; modifications réservées à l'administrateur.
- **Branche `feature/airllm-fallback` — AirLLM par défaut sans serveur IA local** : si Ollama est éteint/injoignable ou n'a aucun modèle de discussion, EVA répond automatiquement avec AirLLM (le message « serveur IA local indisponible : repli sur AirLLM » s'affiche ; réponses lentes, sans outils). Dès que le serveur IA revient, EVA repasse dessus (vérifié toutes les 20 s). Le service `eva-airllm` est maintenant dans le `docker-compose.yml` principal (URL préréglée, rien à ajouter dans `.env`). Pas de repli pour la voix, les images, ni quand tu as choisi un modèle à la main. Désactivable : `EVA_AIRLLM_FALLBACK=0`. `docker-compose.airllm.yml` ne sert plus qu'à réserver un GPU NVIDIA.
- Déconnexion inopérante quand `EVA_AUTH_TOKEN` est défini : le jeton intégré à l'interface rouvrait l'accès aussitôt. La déconnexion verrouille maintenant l'appareil jusqu'à la prochaine connexion ; la désactivation du mot de passe précise si `EVA_AUTH_TOKEN` protège encore EVA.
- Connexion : le jeton de session partageait sa case du navigateur avec l'identifiant de conversation (`eva.session`) et était écrasé → EVA « hors ligne » (401/403). Clé dédiée `eva.auth` ; un jeton périmé ou un refus d'API/WebSocket ramène maintenant à l'écran de connexion.

**Ajouté**
- **Voyant « hors ligne » expliqué** : survol du voyant, bas de la barre latérale et Paramètres affichent la cause (serveur injoignable / WebSocket refusé / erreur serveur). Script `diagnostic.sh` : `cd /home/eva/eva && bash diagnostic.sh` rassemble état des conteneurs, santé, erreurs et configuration (secrets masqués).
- **Réponses courtes instantanées à l'écrit** : une courte phrase de conversation (« qui es-tu ? », « merci »…) passe en mode léger comme la voix — ni schémas d'outils ni catalogue de compétences (~4000 tokens en moins). Corrige le petit modèle qui appelait `skill_list` pour rien et affichait de faux résultats d'outils. Une demande d'outil, ou la suite d'une demande d'outil (« oui vas-y »), garde ses outils.
- **API publiques** (dépôt public-apis) : catalogue hors ligne de ~2000 API gratuites (dont ~1000 sans clé) consultable par EVA (`api_search`, recherche en français ou anglais) et appel GET sécurisé (`api_get` : réseau public seulement, redirections revérifiées, aucun secret accepté dans l'adresse, contenu marqué non fiable). Compétence « apis-publiques » avec des exemples prêts à l'emploi : pays, taux de change, jours fériés, Wikipédia, recettes, cocktails, livres, soleil, ISS. Pas encore de clés d'API enregistrées : les API à clé sont signalées, pas appelées.
- **Catalogue d'API publiques mis à jour automatiquement** : EVA relit le dépôt public-apis une fois par semaine (au premier lancement puis tous les 7 jours), garde la copie à jour en base, et t'annonce dans la discussion « N nouvelle(s) API ajoutée(s) : … » (Paramètres › API publiques : état, nouveautés, bouton « Mettre à jour maintenant »). Garde-fous : un README illisible ou vide ne remplace jamais le catalogue ; sans réseau, l'ancien reste.
- Le routeur n'envoie plus au tout petit modèle (rapide) une demande qui a besoin d'outils (« allume le salon », « ajoute du lait »…), à l'écrit comme à la voix : le modèle principal s'en charge.
- Démarrage d'EVA CORE plus rapide : le contrôle des droits du workspace ne réécrit plus tous les fichiers à chaque lancement. Pendant un redémarrage (mise à jour), le voyant orange est normal : le message dit « EVA redémarre ».
- **AirLLM en RAM** : les couches du modèle sont gardées en mémoire vive (budget automatique ou `AIRLLM_RAM_CACHE_GB`) + préchargement ; fichier de lancement dédié au serveur IA (`eva-airllm/docker-compose.yml`).
- **Widgets météo / heure** : ils disparaissent au bout de ~8 s (la souris posée dessus les retient ; 📌 pour les garder). Les diaporamas gardent 90 s.
- Corrigé : « présentation » avec un modèle léger — les diapos envoyées en texte JSON, même coupé, sont maintenant relues au lieu de l'erreur « Aucune diapositive valide ».
- **Compétence « devjarvis »** (Paramètres › Compétences) : méthode d'ingénieur logiciel prudent (explorer, planifier, modifier par petites touches, tester, compte rendu vérifié). Utilisation : « Avec devjarvis, ajoute … au projet X ».
- **Météo d'une autre ville** : « la météo à Lyon » (même en minuscules, avec ou sans accent) affiche bien Lyon et non la ville par défaut. Affichage plus rapide : lieux mémorisés, prévisions gardées 10 min, connexion réutilisée, ville par défaut préchargée au démarrage.
- **Nouvelle discussion à chaque ouverture** : EVA ne reprend plus la dernière discussion (donc plus le dernier projet) ; elle ne travaille dans un projet que si tu le demandes ou le nommes. L'historique reste dans la barre latérale.
- **Home Assistant refait proprement** : *Importer depuis Home Assistant* (Maison › Appareils) lit tes entités (lumières, prises, volets, chauffages, médias, scènes) avec leurs **zones** comme pièces, tu coches et renommes. Corrigé : les volets utilisent `open_cover`/`close_cover` (et non `turn_on`, inexistant), blanc chaud/froid en Kelvin, intensité pour lumière/ventilateur/volume, scènes, état « injoignable » explicite, vrai message d'erreur de Home Assistant. Portails, garages, portes, serrures et alarmes restent interdits.
- **Appareils non reconnus** : la découverte liste aussi les machines inconnues (« Autres appareils trouvés ») avec un indice (ex. puce Espressif = probable ampoule) ; bouton *Configurer…* pour dire ce que c'est (nom, pièce, type, pilote) et boutons **Tester** (état / allumer / éteindre) avant d'enregistrer. Nom et pièce modifiables sur chaque appareil reconnu. Le changement de pilote ne perd plus l'adresse IP.
- Corrigé : l'analyse réseau (résolution de noms) ne monopolise plus les ressources d'EVA ; la recherche automatique tourne en arrière-plan.
- **Recherche automatique en tâche de fond** (Maison › Réseau › « Recherche automatique », toutes les 1 à 168 h) : EVA repère seule les nouveaux appareils, les garde en attente (bannière « N appareils détectés » sur l'onglet Appareils) et prévient par Telegram si configuré. Rien n'est ajouté sans validation. Boutons « Rechercher maintenant » et « Chercher mes appareils » sur Appareils.
- **Découverte automatique des appareils** (Maison › Réseau › « Découvrir et ajouter ») et outil `net_discover` : reconnaissance Shelly/Tasmota/WLED/imprimantes IPP/Tuya/ordinateurs, liaison Tuya cloud→local par adresse MAC, ajout sur sélection.
- **Module Maison** (voir MAISON.md) : appareils par pièce (Tuya local/cloud avec import, Shelly, Tasmota, WLED, Wake-on-LAN, MQTT, Home Assistant), scènes, **listes** (courses, à faire…, à la voix), **impression à distance** (IPP : texte, listes, PDF, images, fichiers de projet), **analyse du réseau** (balayage, nmap en option) et **accès SSH/root** aux machines enregistrées avec empreinte mémorisée. 19 nouveaux outils d'EVA (`device_*`, `scene_run`, `list_*`, `print_*`, `printer_list`, `net_*`), tous soumis aux permissions : actions sensibles/impression/SSH/analyse = accord demandé ; serrures, alarmes, portails jamais pilotés. Commandes SSH, appareils commandés par EVA et analyses tracés dans le journal d'accès. Menus Maison et Listes ; réseau et gestion des appareils réservés aux administrateurs.
- **Plusieurs utilisateurs + journal d'accès (bastion)** : le premier compte est administrateur ; il ajoute des utilisateurs (rôle admin ou user), les désactive, réinitialise leur mot de passe, ferme leurs sessions (Paramètres › Utilisateurs). Un « user » discute et utilise projets/bac à sable mais ne peut pas modifier auto-évolution, sauvegardes, connecteurs, modèles, partage réseau. Garde-fou : toujours au moins un admin actif. Journal d'accès (Paramètres › Journal d'accès, 90 jours, filtres + export CSV) : connexions, échecs, refus (sans session ou droits insuffisants), actions qui modifient (POST/PUT/PATCH/DELETE), administration, ouverture du chat — jamais de mot de passe. L'ancien compte unique est migré automatiquement en administrateur. Les conversations et projets restent communs à tous les comptes.
- **Connexion par identifiant + mot de passe** (facultative, à activer dans Paramètres › Sécurité ; désactivée par défaut, donc aucun risque d'être bloqué dehors). Une fois activée, l'interface, l'API, le WebSocket et la voix exigent une session (30 jours, révocable). Mot de passe conservé haché (scrypt), sessions stockées sous forme d'empreinte, verrou temporaire après 5 essais ratés. Changer le mot de passe, déconnecter les autres appareils, se déconnecter, désactiver (avec le mot de passe). Le jeton `EVA_AUTH_TOKEN` continue de fonctionner pour les scripts. Le partage réseau des projets garde son propre mot de passe
- Projets — **Historique** : une version est enregistrée à chaque enregistrement, avant et après chaque intervention d'EVA dans un projet. On voit ce qui a changé (avant/après), on peut revenir à une version, et le bouton **« Annuler la dernière modification d'EVA »** remet le projet comme avant (rien n'est perdu : l'état précédent reste dans l'historique). Stocké hors du dossier du projet
- Projets — **Aperçu en direct** (onglet Aperçu) : pages HTML/CSS/JavaScript du projet affichées dans la page, rafraîchies à chaque modification ; l'aperçu est isolé (il ne peut pas accéder à EVA). Le PHP n'est pas exécuté
- Projets — **Corbeille** : un projet supprimé reste récupérable 30 jours (restaurer / supprimer définitivement) ; sa base de test, elle, est supprimée
- Projets : nouvelle page — créer, **supprimer** (avec confirmation), déposer des fichiers (glisser-déposer, .zip décompressé sur place), arborescence, éditeur intégré (Ctrl+S), renommer, télécharger en ZIP. Mise à jour **en direct** : ce qu'EVA écrit dans le projet apparaît tout seul ; si EVA modifie un fichier pendant que tu le modifies, tu choisis (recharger / garder ta version)
- Bac à sable de projet pour EVA : `sandbox_run` (Python, pytest…), `sandbox_install` (pip, avec confirmation car Internet) et `sandbox_db` (base PostgreSQL de test propre au projet, rôle limité qui ne voit pas la base d'EVA). Conteneur Docker jetable, sans droits, sans réseau par défaut (réseau interne vers la base seulement ; Internet uniquement sur confirmation). La même console et une console SQL sont disponibles dans la page Projets
- Partage réseau des projets (Windows / Mac / Linux) **activable depuis la page Projets** : bouton, mot de passe, port, adresse à utiliser affichée. EVA lance un serveur Samba dans un conteneur et le relance au redémarrage ; mode d'emploi : `PARTAGE-PROJETS.md`
- Compréhension : EVA n'envoyait aucune taille de mémoire à Ollama (2048-4096 jetons par défaut) → consignes, outils et fichiers joints étaient coupés en silence. Désormais 8192 par défaut, réglable avec la température dans Paramètres › « Compréhension »

**Corrigé**
- Listes déroulantes : le menu ouvert affichait du texte clair sur fond blanc (illisible) ; fond et texte adaptés au thème

**Ajouté**
- Mode développeur : quand la demande porte sur du code ou des fichiers déposés (« modifie le code du zip fourni… »), EVA applique une vraie méthode : explorer (`fs_tree`, `fs_grep`, `fs_read`), planifier en quelques puces, modifier par petites touches (`fs_edit`, annulable depuis le journal), vérifier (`dev_check` = syntaxe Python/JSON sans exécuter ; tests via `terminal_run` avec confirmation), puis livrer un ZIP (`zip_make`) avec un bouton Télécharger dans la conversation. Jusqu'à 14 étapes d'outils (4 auparavant), modèle « code » choisi d'office. Consigne de comportement générale renforcée (comprendre l'intention, ne jamais inventer un résultat)
- Dépôt de fichiers dans la conversation : bouton 📎 (page Conversation et tiroir de l'accueil) ou glisser-déposer n'importe où sur l'interface — PDF, Word, Excel, PowerPoint, texte/code, ZIP (décompressé en sécurité), photos (envoyées au modèle vision). EVA reçoit un aperçu et lit la suite avec `fs_read` (qui accepte maintenant un `offset` pour les longs fichiers) ; le texte extrait est gardé à côté (`uploads/<fichier>.txt`). Limite 200 Mo. Nouvelle dépendance `pypdf` (reconstruire eva-core)
- Création d'images (« EVA, crée une image d'un chien ») : la demande part directement vers un serveur d'images local (Stable Diffusion WebUI / Forge lancé avec `--api`, ou API compatible OpenAI), sans passer par le modèle de langage ; l'image s'affiche à l'écran et est gardée dans `workspace/generated/`. À régler dans Paramètres › Génération d'images (bouton Tester). Sans serveur d'images, EVA dit honnêtement qu'elle ne peut pas (avant, le modèle inventait une fausse présentation). Le modèle « vision » sert à comprendre les photos, pas à en créer
- Catalogue Hugging Face (Paramètres › Modèles) : recherche de modèles GGUF (tri téléchargés / tendance / aimés / récents), liste des quantifications avec leur taille, et alerte selon la puissance du serveur IA (✅ tient sur la carte graphique, ⚠️ lent car partagé avec le processeur, ⛔ trop gros, confirmation avant téléchargement). La puissance (mémoire vidéo et RAM du serveur IA, 6 Go / 16 Go par défaut) se règle dans la même carte. Téléchargement par Ollama via `hf.co/<dépôt>:<quantification>`. Exige un accès Internet depuis EVA CORE ; jeton facultatif `EVA_HF_TOKEN` pour les dépôts à accès restreint
- Post-it : affichés uniquement sur la page EVA ; le ✓ les valide et les range dans une corbeille (bouton Post-it › Corbeille) avec la date de traitement, restauration ou suppression définitive possibles ; « efface tous les post-it » les range dans la corbeille, « vide la corbeille » les supprime
- Lisibilité : texte des boutons choisi automatiquement selon la couleur d'accent, panneaux de verre teintés automatiquement quand le texte serait peu lisible, curseur « Lisibilité du texte secondaire » dans Personnaliser (la couleur du texte reste réglable)
- Reconnaissance des post-it élargie (« peux-tu me mettre un post-it pour… », « rappelle-moi sur un post-it de… », « je veux un post-it… », variantes de la reconnaissance vocale « postite », « poste it »…) ; « mets un post-it » seul : EVA demande quoi écrire, sans modèle
- Les commandes de post-it (créer, lister, effacer, masquer/afficher) sont exécutées directement, sans appel au modèle : réponse instantanée
- Bouton « Couper le son » toujours visible dans la barre du haut (arrête la lecture en cours, sinon active/coupe la voix d'EVA)
- Interface entièrement refaite (style Jarvis, verre dépoli, logo EVA au centre) : thème par défaut « Crépuscule »
- Bouton « Personnaliser » (palette dans la barre du haut, ou Paramètres › Apparence) : préréglages (Crépuscule, Aube, Glace, Océan, Hologramme, Nuit), 7 couleurs, flou/transparence/arrondi, position du menu (gauche, icônes, haut, masqué), du chat (droite, gauche, masqué) et des widgets (bas, côtés, masqués), densité, taille du logo et des anneaux, export/import JSON, réinitialisation. Sauvegardé dans le navigateur et sur le serveur (même rendu sur tous tes appareils)
- Post-it : EVA en crée à l'écran (« mets un post-it : appeler le garage »), les liste, les efface (« efface tous les post-it », « efface les post-it terminés »), les masque/affiche (« cache / affiche les post-it »). Bouton « + Post-it » pour en ajouter à la main ; on les déplace, édite, coche, change de couleur ; visibles sur toutes les pages. Outils `note_create/list/update/delete`, API `/api/notes`

## 2026-10-14 — Mise à jour 19 (AirLLM facultatif)

**Ajouté**
- Service `eva-airllm` (facultatif, désactivé par défaut) : fait tourner un très gros modèle (70B+) sur une petite carte graphique en chargeant les couches une à une depuis le disque (AirLLM, Apache-2.0). Très lent (minutes par réponse), sans outils ni streaming : pour de la réflexion ponctuelle, pas pour la conversation. Déclaré par `EVA_AIRLLM_URL` ; apparaît alors comme modèle « airllm » (choix par conversation, ou dans « Choix automatique »). Fichier à part `docker-compose.airllm.yml`, ton `docker-compose.yml` n'est pas touché.
- Zoom à deux mains ouvertes, boutons − / + / % et molette (présentations et carte de la mémoire)

## 2026-10-14 — Mise à jour 18 (gestes, annulation, carte, personnalités)

**Ajouté**
- Pilotage par gestes (Paramètres › Voix, désactivé par défaut) : MediaPipe embarqué (`eva-interface/public/vendor/mediapipe`, Apache-2.0, inspiré de holo-gestures), 100 % local ; balayage de la main ouverte = diapo suivante/précédente, paume immobile = épingler, signe de paix = effacer l'écran
- Gestes, suite (inspirés de holo-gestures) : curseur à l'écran qui suit pouce + index ; pincer pour déplacer un point de la carte, pincement bref pour ouvrir son contenu, zoom en écartant/rapprochant deux mains ouvertes (ou pincées), ou avec les boutons − / + / % et la molette (diapos et carte), poing fermé tenu ~1 s sur une présentation = EVA la résume à voix haute
- Journal des modifications d'EVA (Apprentissage) : chaque fichier/skill qu'elle écrit, ajoute ou supprime est enregistré avec son état avant/après ; bouton « Annuler » (refus si le fichier a changé depuis, sauf confirmation)
- Carte de la mémoire (Mémoire › Carte) : documents et conversations reliés par proximité de sens (embeddings)
- Personnalités (Paramètres) : équilibrée, concise, chaleureuse, professionnelle, pince-sans-rire, pédagogue ; aussi par la voix (« passe en mode concis »)
- Confirmation à la voix : après une demande vocale, une action sensible est posée à voix haute et « oui » / « non » suffit
- Outil de suppression de fichier proposé quand on le demande (avant : jamais sélectionné)

## 2026-10-14 — Mise à jour 17 (latence vocale)

**Ajouté**
- Mode vocal « léger » : pour une question simple dite à voix haute, prompt court (sans catalogue de skills) et aucun schéma d'outil envoyé au modèle → le 1er mot arrive plus vite. Les outils reviennent dès que la demande en a besoin (recherche, fichiers, météo, docker, mails…). Désactivable avec `EVA_VOICE_LEAN=0`.
- Option « moteur du navigateur » (Paramètres › Voix) pour l'écoute (Web Speech API) et pour la lecture (SpeechSynthesis), comme l'appli Android : pas d'envoi à Whisper ni attente de Piper. Désactivé par défaut (sous Chrome/Android, l'audio part chez Google ; reconnaissance par le timbre indisponible avec ce moteur).
- Préchauffage : dès le mot d'éveil ou l'appui sur le micro, le modèle rapide est chargé en mémoire (`POST /api/models/warm`) ; la voix démarre dès la 1re virgule ou ~60 caractères.
- Gestionnaire de modèles Ollama (Paramètres) : liste avec taille/capacités, téléchargement avec progression, suppression (modèles utilisés protégés), alerte si aucun modèle vision.
- Briefing : « EVA, mon briefing du matin / résume ma journée » → diaporama (heure, météo, gros titres, état du serveur) + briefing parlé.
- Alerte Docker (monitor) : conteneur arrêté / redémarré en boucle, puis retour à la normale, relayée aussi sur Telegram.
- Mesures de latence (écoute, 1er mot, réponse complète, début de la voix) affichées dans Paramètres › Voix ; événement `timing` côté serveur.

## 2026-10-14 — Mise à jour 16

**Ajouté**
- Météo fiable : détection de la demande côté serveur, outil lancé par EVA elle-même (même avec le modèle rapide du mode vocal), données injectées dans le tour
- Mini-rendu Markdown dans le chat (tableaux, listes, titres, gras)
- Écran de présentation en direct (`SceneStage`) : météo, heure, actualités (recherche web), diaporamas via le nouvel outil `present` ; navigation, épingle, fermeture auto 90 s, commande « EVA, efface » (traitée sans modèle)
- État du système (jauges) et conteneurs Docker (tableau) affichés sur l’écran de présentation
- Reconnaissance de la voix (sherpa-onnx, CAM++) et du visage (OpenCV YuNet + SFace), 100 % local : profils, enrôlement, test, seuils réglables, effacement ; jetons signés par le serveur ; option « voix inconnue = invité » (outils réduits)

- Interface téléphone : menu ☰ (toutes les pages accessibles : Paramètres, Agents, Conversation plein écran…), pages adaptées à l'écran étroit, écran de présentation en feuille du bas, hauteur `dvh` (barre d'adresse Android), zones de saisie plus grandes

- Visage vivant en direct (défi gauche/droite aléatoire, identité constante, retour au centre) ; un visage non vérifié ne lève plus les restrictions invité ; commande « EVA, c'est moi »
- Reconnaissance par la façon d'écrire (empreinte statistique de caractères, opt-in, ≥ 2 personnes, indice faible)

- Photos : bouton 🖼 (galerie/fichiers) et 📷 dans la page Conversation (utile sur téléphone) ; une question de suivi (« et sur la photo… ? ») renvoie la dernière photo au modèle vision au lieu de « je n'ai pas accès à l'image »

**Vérifié**
- 123 tests (dont suivi de photo) ; 121 tests (dont machine d'états du défi, photo immobile refusée), e2e défi complet navigateur ; style : deux styles (formel / SMS) bien séparés
- (ancien décompte) 116 tests, e2e navigateur (carte météo, écran, diaporama, retour automatique, enrôlement visage et voix avec caméra/micro simulés)
- Voix : voix de synthèse (espeak) bien séparées (soi 0,72-0,90 ; autres ≤ 0,67) — **non testé avec de vraies voix humaines**

---

## 2026-10-14 (nuit, 14 bis) — Bouton micro : plus de décodage côté serveur

Erreur chez le testeur sur le bouton micro : `open() got an unexpected keyword argument 'metadata_errors'` (PyAV trop ancien pour faster-whisper). Le navigateur convertit maintenant l'enregistrement en WAV 16 kHz avant l'envoi ; le serveur lit ce WAV directement, sans PyAV. En secours, un décodage PyAV maison (sans l'option fautive) remplace celui de faster-whisper. Test navigateur ajouté (envoi WAV, transcription → message).

## 2026-10-14 (nuit, 14) — Voix réactive et fiable

Retours : « ça marche une seule fois », analyse « hyper longue », réponse longue à venir.
- **« Une seule fois »** — causes corrigées : mot d'éveil plus tolérant (Éva, Ève, Ava, Eba, « Et va »… comparés sans accents), l'écoute ne se met plus en pause pendant la réflexion d'EVA (les phrases n'étaient perdues), une phrase captée pendant qu'une analyse tourne est mise en attente au lieu d'être jetée, délai maximal de 20 s sur la reconnaissance (plus de blocage silencieux), 0,5 s ignorées après la fin de la parole d'EVA (son propre écho n'est plus pris pour une commande). Test navigateur : 3 commandes de suite, avec variantes « Eva / Ève / Ava ».
- **Reconnaissance plus rapide** : l'écoute utilise un modèle Whisper léger (`WHISPER_FAST_MODEL_SIZE=base`, ≈3× plus rapide que `small`), préchargé au démarrage ; `small` reste pour le bouton micro. Silence de fin de phrase raccourci (0,65 s). Options Whisper allégées (sans horodatage, température 0).
- **Réponse plus rapide** : modèle gardé en mémoire 30 min (`EVA_KEEP_ALIVE`) ; en vocal, consigne « 1 à 3 phrases courtes, sans markdown » et, si un modèle « Rapide » est réglé dans Paramètres, c'est lui qui répond (sauf code/image). **La lecture démarre dès la première phrase** (ou la première virgule) au lieu d'attendre la fin de la réponse ; le code n'est jamais lu.
- Tests : 102 serveur + e2e dont 3 commandes vocales consécutives.

## 2026-10-14 (nuit, 13) — Écoute mains libres : voir ce qui se passe

Constat : « quand j'appelle Eva, elle ne répond pas » sans moyen de savoir où ça bloque. Au-dessus des boutons s'affichent maintenant un **indicateur de niveau du micro**, « Analyse… » pendant la reconnaissance, et « J'ai entendu : … » pour chaque phrase captée (même sans mot d'éveil). Seuil de détection de parole abaissé (micros d'ordinateur peu sensibles : 0,02 → 0,01 de niveau minimum, bruit de fond adaptatif plus bas).

## 2026-10-14 (nuit, 12 bis) — Correctif reconnaissance vocale

Erreur chez le testeur : `open() got an unexpected keyword argument 'metadata_errors'` — faster-whisper 1.2.1 appelle PyAV avec une option absente des anciennes versions de PyAV installées. Correctifs : `av>=14.0.0` dans eva-voice/requirements.txt, et les segments WAV de l'écoute mains libres sont décodés sans PyAV (lecture directe en tableau float32). Test ajouté. Seul eva-voice est concerné (reconstruction nécessaire).

## 2026-10-14 (nuit, 12) — Reconnaissance robuste, voix plus chaude

- **Reconnaissance (erreur 500)** : si les options avancées de Whisper (filtre de silence, prompt) échouent, nouvel essai en transcription simple ; l'erreur réelle est renvoyée à l'interface et au journal (`docker compose logs eva-voice`) au lieu d'un « 500 » muet.
- **Voix plus douce** : débit légèrement ralenti et synthèse lissée par défaut (`PIPER_LENGTH_SCALE=1.12`, `PIPER_NOISE_SCALE=0.5`, `PIPER_NOISE_W=0.6`, réglables dans `.env` côté eva-voice), choix de la voix et du débit dans Paramètres › Voix avec bouton « Écouter un échantillon ». Les modèles multi-locuteurs (ex. `fr_FR-upmc-medium` : jessica, pierre) sont listés par locuteur. Nouveau point d'accès `GET /voice/voices`.
- Limite : Piper reste une voix de synthèse légère ; pour mieux (voix clonée, plus expressive) il faudrait un moteur plus lourd sur le serveur IA (GPU).
- Tests : 97 au total.

## 2026-10-14 (nuit, 11 bis) — Correctif : démarrage d'EVA CORE

Après la mise à jour 11, EVA CORE ne démarrait plus (erreur 502 partout dans l'interface). Cause : la restauration de sauvegarde utilisait l'envoi de fichier multipart, qui exige le paquet `python-multipart`, absent de l'image Docker (présent seulement dans mon environnement de test). La restauration reçoit désormais le zip en corps brut : plus aucune dépendance. Nouveau test : l'application doit s'importer sans `python-multipart`. Audit des imports : tout le reste est dans requirements.txt.

## 2026-10-14 (nuit, 11) — Ouverture, sécurité, sauvegardes, diagnostic voix

- **Diagnostic voix** : bouton « Tester la voix » (Paramètres › Voix) qui contrôle HTTPS, service eva-voice, voix Piper, synthèse, micro et reconnaissance, et dit lequel casse. Les erreurs de voix s'affichent au-dessus des boutons (plus d'échec silencieux) ; l'écoute reprend après un clic quand le navigateur la suspend après un rechargement.
- **MCP** (`mcp.py`) : branche des serveurs MCP « streamable HTTP » (JSON ou SSE) ; leurs outils deviennent `mcp_<serveur>_<outil>`. Confirmation à chaque appel par défaut, serveur « de confiance » en option, résultats étiquetés non fiables, interdits aux agents. Carte « Outils externes (MCP) » dans Paramètres.
- **API compatible OpenAI** : `https://<NAS>:8443/api/v1` (`/models`, `/chat/completions`, streaming) avec le jeton EVA en « clé API ». Modèle `eva` = choix automatique du modèle + personnalité d'EVA ; autres noms transmis à Ollama. Ce n'est pas l'agent avec outils.
- **Alertes proactives sur Telegram** (monitors serveur, agents planifiés) avec anti-doublon 15 min et interrupteur dans la carte Telegram.
- **Sauvegarde / restauration** (`backup.py`) : zip des tables + workspace, sauvegarde quotidienne automatique (7 gardées dans workspace/backups), carte « Sauvegarde » (créer, télécharger, restaurer). Restauration transactionnelle, chemins d'archive vérifiés. La sauvegarde contient les jetons.
- **Défense contre l'injection de prompt** (`harness/guard.py`) : les résultats web, e-mails, agenda et MCP sont étiquetés non fiables ; les formulations d'injection typiques (FR/EN) déclenchent une alerte au modèle et un avertissement dans le chat.
- Tests : 89 tests serveur + e2e (cartes Paramètres, diagnostic voix, voix mains libres) ; tous les e2e précédents repassent.
- Non vérifié ici : un vrai serveur MCP, un vrai client OpenAI, la voix sur ton matériel.

## 2026-10-14 (nuit, 10) — Voix mains libres

- **Mot d'éveil** (« Eva », « Hey Éva », « dis Eva… ») : écoute continue dans le navigateur (détection de parole locale, segments envoyés à Whisper local `/voice/stt?mode=fast`). Seules les phrases commençant par le mot d'éveil sont prises en compte ; « Eva » seul → bip + 8 s d'écoute ; « Eva, <demande> » → envoyée directement. Mot d'éveil modifiable.
- Mise en pause pendant que EVA parle ou réfléchit (pas d'écho) ; après une réponse parlée, 6 s d'écoute de suivi sans redire « Eva ».
- **Lecture à voix haute** : texte nettoyé (sans code, liens, markdown), découpé en phrases, synthèse de la suivante pendant la lecture ; bouton haut-parleur (Toujours / seulement après une demande vocale) et bouton Stop. Carte « Voix » dans Paramètres.
- eva-voice : filtre de silence Whisper (VAD), prompt « Éva », mode rapide (beam 1) pour l'écoute.
- Pas de confirmation d'action par la voix (volontairement : une phrase entendue à la télé ne doit pas pouvoir autoriser une action).
- Tests : e2e navigateur avec micro simulé (2 scénarios) + tests unitaires des fonctions de voix ; tous les e2e précédents repassent.
- Non vérifié ici : vraie reconnaissance de « Eva » par Whisper, vraie voix Piper, latence sur le NAS.

## 2026-10-14 (nuit, 9) — Telegram, notifications, bouton ▶ partout

- **Canal Telegram** (`telegram.py`, `routes_telegram.py`, carte dans Paramètres) : long polling (aucun port ouvert), liste blanche d'identifiants (les inconnus reçoivent seulement leur propre identifiant), une conversation `telegram-<id>` par discussion, mêmes outils/routeur/traces que le web. Confirmation des actions sensibles par « oui » / « non » (2 min, sinon refus). `/start`, `/nouveau`.
- Outil **`telegram_notify`** (AUTO, utilisable par les agents) : prévient l'utilisateur sur ses propres discussions autorisées ; le Briefing du matin l'utilise s'il est configuré.
- Bouton ▶ Exécuter aussi dans le tiroir de l'accueil (MessageText).
- Tests : 5 nouveaux (60 au total) + e2e carte Telegram ; tous les e2e précédents repassent.
- Non vérifié ici : échange réel avec l'API Telegram (simulée dans les tests).

## 2026-10-14 (nuit, 8) — Bouton « Exécuter » (indépendant du modèle)

Constat : ni llama3.1 ni qwen2.5-coder n'appellent `code_run`, donc aucune carte de confirmation.
- Les blocs de code ```python des réponses affichent un bouton **▶ Exécuter dans le bac à sable** (+ Copier) ; la sortie s'affiche sous le bloc.
- Nouvel endpoint `POST /api/sandbox/run` {code} : même bac à sable Docker (sans réseau, lecture seule, 256 Mo, 30 s). Le clic de l'utilisateur vaut confirmation.
- Tests : endpoint + e2e navigateur (55 tests OK).

## 2026-10-14 (nuit, 7) — Retours de test : avis, choix des outils

Constats chez le testeur : les pouces n'enregistraient rien (cliqués dans le tiroir de l'accueil, qui n'en avait pas, et trop discrets sur la page Conversation) ; « calcule 6*7 avec du code » a reçu une réponse directe de llama3.1 sans appel à `code_run`, en 28 s et 2050 tokens.
- Pouces 👍/👎 aussi dans le tiroir de l'accueil, plus visibles, avec « Avis enregistré » ou l'erreur exacte (plus d'échec silencieux).
- **Sélection des outils par tour** (`harness/selection.py`) : un noyau d'outils toujours proposé (fichiers, docs, skills, web, système, météo) ; code_run, Gmail, agenda, Home Assistant, Docker, Git, terminal, projets, skills, auto-évolution seulement si la demande ou les deux précédentes les évoquent (ou citent l'outil par son nom). Moins de tokens, moins de confusion pour un modèle 8B. Le registre complet reste utilisé pour l'exécution et les permissions.
- Consigne système : pour un calcul, une conversion ou un traitement de données, appeler `code_run` plutôt que calculer de tête.
- À vérifier : que llama3.1 appelle bien code_run avec ces changements ; sinon utiliser le modèle « Code » (qwen2.5-coder) via le routeur.

## 2026-10-14 (nuit, 6) — Home Assistant

- Paramètres → Home Assistant : adresse + jeton d'accès longue durée (testés à l'enregistrement, jeton jamais renvoyé par l'API).
- Outils `ha_states`, `ha_get` (AUTO, lecture) et `ha_call` (CONFIRM, jamais pour un agent autonome).
- Interdits d'office (FORBIDDEN) : déverrouiller, désarmer/armer l'alarme, ouvrir/basculer un volet-garage-portail, arrêter/redémarrer Home Assistant, scripts, automatisations, commandes shell. Les entités `person` et `device_tracker` (positions) ne sont jamais exposées. L'entité visée ne peut pas être détournée via `data`.
- Non vérifié : contre un vrai Home Assistant (tests avec une fausse API).

## 2026-10-14 (nuit, 5) — Google : Gmail et Agenda

- Connexion OAuth « application de bureau » sans serveur public : identifiants saisis dans Paramètres, lien d'autorisation ouvert sur ton PC, adresse de redirection collée dans EVA (la page 127.0.0.1:8765 ne s'affiche pas, c'est voulu). Jeton de rafraîchissement stocké en base, jamais renvoyé par l'API.
- Outils : `gmail_search`, `gmail_read`, `calendar_list` (AUTO, lecture seule, utilisables par les agents) ; `gmail_send`, `calendar_create` (CONFIRM, jamais pour un agent autonome).
- Les e-mails sont traités comme contenu non fiable : le résultat de l'outil rappelle au modèle de ne suivre aucune instruction qu'ils contiennent. Un agent ne peut pas envoyer d'e-mail même si un message l'y pousse.
- Le briefing du matin ajoute l'agenda et les e-mails non lus si Google est connecté.
- Non vérifié : tout contre le vrai Google (les tests simulent les réponses de l'API). Il faut créer le client OAuth (aide dans Paramètres → Google).

## 2026-10-14 (nuit, 4) — Évolution : EVA propose des modifications de son code

- Outils `self_read` (lire son code) et `self_propose` (proposer des fichiers complets) : AUTO, car ils ne changent rien. Il n'existe AUCUN outil pour appliquer : seule la page **Évolution** / l'API (toi) applique, refuse ou annule.
- Avant application : syntaxe (`py_compile`) + import complet de `app.main` sur une copie temporaire. Application = écriture dans `/eva-self/live` (dépôt Git) + commit ; redémarrage ; annulation = `git revert`.
- `selfboot.py` (nouveau point d'entrée) : teste la copie modifiée au démarrage ; si elle est cassée, retour automatique au code de l'image et erreur affichée dans la page. Image reconstruite → ancienne copie archivée, code de base repris.
- Protégés (refus automatique) : permissions, boucle des outils, base des outils, registre, terminal, auth/main, config, db, ce mécanisme.
- Limites assumées : seul le backend (Python, skills, docs) est modifiable ; l'interface web non. Quelqu'un ayant accès à terminal_run en conversation (avec ton accord) pourrait appeler l'API d'application : garde un EVA_AUTH_TOKEN.
- **Correctif de build** : le Dockerfile ne copiait pas `skills/` ni `seed_docs/` (skills fournis et doc d'EVA absents après la mise à jour n°1). Corrigé.

## 2026-10-14 (nuit, 3) — Apprentissage local

- **Avis 👍/👎** sous chaque réponse d'EVA (commentaire facultatif sur 👎), conservés dans l'historique (table `feedback`, lien message → trace).
- **Page Apprentissage** : avis, modèles (réussite, durée, avis), outils (taux d'échec), skills utilisés, derniers avis négatifs, et suggestions par règles (outil qui échoue souvent, modèle mal noté, skill mal noté).
- **« Proposer une amélioration »** sur un skill : EVA relit l'historique d'utilisation (demandes, échecs, avis) et propose une version révisée du SKILL.md ; tu compares, modifies, puis appliques. Rien n'est jamais appliqué sans toi, le nom du skill ne peut pas changer, 3 utilisations minimum.
- Honnêteté : ce n'est pas de l'entraînement de modèle (pas de fine-tuning ni de DSPy). C'est une boucle d'amélioration des skills, des réglages de modèles et des suggestions, à partir de tes avis.

## 2026-10-14 (nuit, 2) — Routeur de modèle, orchestrateur, bac à sable de code

- **Choix automatique du modèle** (`router.py`) : règles déterministes (image → vision, code → code, demande longue/analytique → raisonnement, échange court → rapide, sinon défaut), réglables dans Paramètres, suggestions calculées depuis les modèles installés (jamais appliquées sans validation), choix manuel par conversation, repli sur le modèle par défaut si un modèle est absent. Un modèle sans capacité « tools » est utilisé sans outils. Le modèle choisi est affiché dans le chat et enregistré dans la trace. Réglages stockés en base (table `kv`), pas dans le workspace.
- **Agent Orchestrateur** : décompose l'objectif et confie des sous-tâches avec l'outil `delegate` à 4 rôles (chercheur, analyste, système, rédacteur), chacun avec un sous-ensemble d'outils sûrs. Limites : 5 délégations par exécution, pas de délégation imbriquée, `delegate` invisible en conversation. Les étapes des sous-agents apparaissent dans la trace de l'exécution.
- **Outil `code_run`** : Python exécuté dans un conteneur Docker jetable (sans réseau, sans volume, système de fichiers en lecture seule, capacités retirées, utilisateur non privilégié, 256 Mo, 64 processus, 30 s). En conversation : CONFIRM (tu relis le code). Dans un agent : autorisé car isolé. Agent « Assistant code » fourni. Image `python:3.12-slim` téléchargée au premier usage (EVA_SANDBOX_IMAGE pour la changer).
- Agents : 6 itérations d'outils par défaut (4 avant), 8–10 pour les modèles code/orchestrateur. Correction de `_AutoOnlyRegistry.get`, qui rendait n'importe quel outil accessible par son nom.
- Non vérifié : le vrai Docker (les tests utilisent un faux client qui contrôle les options d'isolation transmises) et le comportement de llama3.1 sur `delegate`.

## 2026-10-14 (nuit) — Reconstruction des fonctions d'OpenJarvis dans EVA

À la demande du testeur (« toutes les fonctionnalités d'OpenJarvis »), dans l'ordre :
1. **Conversations** : liste, recherche, renommer, supprimer, une WebSocket par conversation.
2. **Agents + planificateur** : modèles (briefing du matin, recherche approfondie, veille, veille système, libre), exécution à la demande, par intervalle, quotidienne ou cron. Les agents n'utilisent que des outils AUTO ; notification proactive ; historique d'exécutions avec trace.
3. **Skills** : `SKILL.md` dans `workspace/skills/<nom>/`, 5 skills fournis, catalogue injecté dans le prompt, outils `skill_list/read` (AUTO) et `skill_save/install` (CONFIRM), installation depuis GitHub (raw.githubusercontent.com uniquement), page Skills.
4. **Documents + mémoire sémantique** : indexation des fichiers texte du workspace (et de `/eva-docs` si monté) et des conversations, embeddings Ollama (`nomic-embed-text`) stockés dans Postgres, outil `docs_search` (AUTO), page Sources, réindexation toutes les 10 min. La doc d'EVA est copiée dans `workspace/eva/` au démarrage (sans écraser).
5. **Traces + coûts/énergie** : chaque tour et chaque exécution d'agent enregistre ses étapes ; page Traces avec bilan, équivalent cloud et énergie ESTIMÉS (EVA_GPU_WATTS, EVA_KWH_PRICE).
- Nouvelle dépendance : `tzdata`. Nouvelles variables : EVA_TIMEZONE, EVA_EMBED_MODEL, EVA_GPU_WATTS, EVA_KWH_PRICE, EVA_DOCS_PATHS.
- Vérifié : 22 tests pytest (Postgres réel + faux Ollama) et 4 parcours navigateur. NON vérifié : modèle llama3.1 réel avec outils, builds Docker, embeddings réels.

## 2026-10-14 (soir, 3) — Accueil : en-tête et cadrage corrigés

Capture du testeur (écran 1920×~910) : le haut de l'accueil était coupé (le
titre sortait de l'écran) et les anneaux HUD dépassaient en haut et en bas.
- En-tête de 104 px avec le nom **EVA** en grand, la mention « assistant
  personnel · local » et l'horloge, sous la barre du navigateur.
- Anneaux et logo dimensionnés sur la hauteur de la fenêtre (80 vh / 36 vh) :
  tout reste visible à toute taille d'écran.
- Panneaux gauche/droite décalés sous l'en-tête.
- Liste des conversations dans la barre latérale (nouveau, recherche,
  renommer en double-cliquant, supprimer).

## 2026-10-14 (soir, 2) — Avatar : le robot est supprimé, le logo reste seul

Retour du testeur : la représentation « robot » (buste, cou, épaules, sphère,
base holographique) le gênait fortement. Il veut son logo, celui de l'APK
Momory (`assets/logo.svg` du dépôt MomoryAndroid).

**Changé**
- Plus de 3D : `Avatar3D.jsx` supprimé, remplacé par `LogoCore.jsx`, qui
  redessine **exactement** le logo de l'APK en SVG (anneau central, point,
  3 points en orbite bleu/violet/jaune, orbite pointillée).
- L'état d'EVA ne recolore jamais le logo : il change l'animation (orbite
  plus rapide en réflexion/action, pulsation à l'écoute, halo coloré).
- Dépendances `three`, `@react-three/fiber`, `@react-three/drei` retirées :
  bundle JS divisé par ~4 (≈254 Ko), rendu fluide sur n'importe quel
  appareil, plus de dépendance WebGL.
- Logo de la barre latérale et favicon = le SVG de l'APK.

## 2026-10-14 (soir) — Interface « application bureau » (inspirée d'OpenJarvis)

Retour du testeur après le premier déploiement : l'interface n'était qu'une
colonne de téléphone de 480 px centrée sur le PC (règle CSS
`max-width: 480px` dès 720 px d'écran, mise volontairement). Il voulait une
vraie application plein écran, comme l'interface web d'OpenJarvis
(barre latérale, grandes pages, trace des outils, panneau système).

**Ajouté (≥ 960 px de large uniquement ; le mobile est inchangé)**
- Barre latérale : EVA (accueil), Conversation, Tableau de bord, Projets,
  Mémoire, Journal, Paramètres (+ pastille de confirmations en attente).
- Accueil : avatar + HUD plein écran (anneaux animés dont la vitesse
  dépend de l'état d'EVA, grille, horloge, panneaux gauche, conversation
  à droite).
- Pages : Conversation plein écran (outils utilisés affichés dans le fil,
  confirmations), Tableau de bord (CPU/RAM/disque avec jauges, conteneurs
  Docker, météo), Projets, Mémoire, Journal des actions, Paramètres
  (lecture seule : modèle, serveur Ollama, liste des 22 outils).
- Libellés français pour les 22 outils (au lieu de 3).

**Vérifié** : build OK ; captures d'écran à 1920×1080 (accueil, conversation,
tableau de bord) et 390×844 (mobile inchangé) avec données simulées.
**Non vérifié** : rendu sur ton écran réel / ton navigateur, pages avec de
vraies données (Docker, mémoire, projets), 3D sur ta carte graphique.

## 2026-10-14 — HTTPS via Caddy (micro/caméra sur mobile)

**Ajouté**
- Service `caddy` (reverse proxy, certificat interne auto-signé pour
  `EVA_HOST`) : `/ws/chat`, `/api/*` → eva-core ; `/voice/*` (préfixe
  retiré) → eva-voice ; le reste → eva-interface.
- `eva-interface/src/urls.js` : URL dérivées de la même origine
  (`wss://hôte/ws/chat`…), surchargeables par `VITE_EVA_*`.
- Proxy de dev Vite imitant les routes de Caddy.
- `.env` : `EVA_HOST` remplace `EVA_PUBLIC_*` (désormais optionnels).

**Changé**
- Ports 8000/8100/8080 liés à `127.0.0.1` ; seul le port 8443 (`EVA_HTTPS_PORT`) est exposé — surtout pas 80/443, déjà pris par l'interface OpenMediaVault (conflit / perte d'accès au NAS). Redirection HTTP→HTTPS désactivée (pas de port 80).
- `INSTALL.md` réécrit autour de Caddy (+ annexe « sans Caddy »).

**Bug trouvé au premier déploiement réel (2026-10-14)**
- `ERR_SSL_PROTOCOL_ERROR` en accédant par IP : sans SNI, Caddy retombe sur
  l'adresse locale de la connexion, qui est celle du conteneur derrière
  docker-proxy, pas l'IP du NAS. Corrigé par `default_sni {$EVA_HOST}`
  dans le Caddyfile (reproduit puis validé avec openssl, sans SNI).
- Port 8000 déjà pris par Portainer sur le NAS : les ports d'eva-core,
  eva-voice et eva-interface ne sont plus publiés (Caddy passe par le
  réseau interne Docker).

**Bug trouvé et corrigé**
- Un site `:443` sans hôte donnait une erreur TLS « internal error » en
  accédant par IP (pas de SNI) → site Caddy déclaré avec `{$EVA_HOST}`.

**Vérifié** : (session précédente) routage, retrait du préfixe `/voice`,
WSS avec query string testés sur un Caddy réel ; ici : YAML du compose
valide, `npm run build` OK.

**Non vérifié** (à constater chez toi) : builds Docker, téléchargement
Whisper/Piper, qualité réelle de llava, appel d'outils réel de
`stream_decide` avec ton modèle, acceptation du certificat sur téléphone.
Le Caddyfile n'a pas pu être re-validé dans cette session (binaire absent).

## 2026-09-28 — Permissions contextuelles, protection SSRF, vrai streaming

Suite à une relecture d'architecture (document externe partagé par
le testeur) : trois corrections priorisées avant tout nouveau refactoring plus
lourd (EventBus, mémoire structurée — pas encore faits).

**Ajouté**
- `Tool.permission_for(args)` : une permission peut maintenant dépendre
  des arguments de l'appel, pas seulement être statique par outil.
  `fs_write`/`fs_append` l'utilisent pour passer en CONFIRM sur un chemin
  sensible (`.env`, `docker-compose.yml`, `config(s)/`, `secret(s)/`,
  `.key`/`.pem`/`.crt`, noms contenant password/secret/credential/token).
- `web_fetch` : protection SSRF — résolution + vérification de l'IP avant
  connexion (bloque réseau privé, loopback, link-local dont les
  métadonnées cloud `169.254.169.254`), et revalidation de chaque
  redirection individuellement (`follow_redirects` désactivé, suivi
  manuel) pour empêcher un contournement par redirection.
- `ollama_client.stream_decide` remplace `chat_once` dans le Harness : la
  décision du modèle est maintenant streamée en direct. Une réponse sans
  outil arrive au client token par token au fur et à mesure qu'Ollama la
  génère, au lieu d'être générée entièrement puis rejouée artificiellement
  mot par mot (comme c'était le cas depuis le début).

**Vérifié réellement**
- Permissions contextuelles : 14 cas testés directement (chemins normaux
  restent AUTO, chemins sensibles passent CONFIRM), puis retestés à
  travers le vrai Harness (écriture refusée sur `docker-compose.yml` = non
  créé ; écriture sur un chemin normal = jamais de confirm_gate appelé).
- SSRF : IP privées/loopback/link-local bloquées (vérifié sur des IP
  brutes et par résolution DNS réelle sur des noms d'hôte, dont un test
  contre une vraie page publique qui passe correctement) ; redirection
  vers une IP interne bloquée *avant* d'être suivie (vérifié qu'aucune
  requête n'atteint l'IP interne) ; régression sur les cas déjà testés
  précédemment (page HTML réelle, fichier texte brut, URL invalide) — tous
  toujours corrects.
- Streaming réel : 5 scénarios retravaillés avec le nouveau mécanisme —
  réponse directe (4 événements token distincts, pas un seul bloc), appel
  d'outil puis réponse finale (outil réellement exécuté sur un vrai
  fichier, puis réponse streamée), confirmation refusée (fichier non
  supprimé), limite d'itérations atteinte (message de repli bien envoyé,
  pas silencieux), erreur Ollama en cours de stream (pas de crash). Puis
  testé de bout en bout via un vrai WebSocket contre l'app réelle (DB,
  monitors, 22 outils) : séquence d'états et mémoire persistée correctes.

---

## 2026-09-27 — Vision (caméra)

**Ajouté**
- `EVA_VISION_MODEL` (défaut `llava`) : modèle multimodal séparé du modèle
  à outils, utilisé uniquement pour les messages avec image.
- `ollama_client.stream_chat` accepte maintenant un `model` en paramètre.
- `main.py` : un message WebSocket avec `{"image": "<base64>"}` court-
  circuite l'Agent Harness (le tool-calling ne se prête pas bien à un
  modèle vision) et part directement vers `EVA_VISION_MODEL`. Seul un
  résumé texte est gardé dans l'historique/la mémoire — l'image elle-même
  n'est jamais réinjectée dans les appels suivants du modèle à outils.
- Frontend : `useCamera.js` (accès caméra, capture JPEG redimensionnée en
  base64), `CameraPanel.jsx` (aperçu + déclencheur), le bouton caméra du
  dock (jusque-là décoratif) ouvre maintenant vraiment la caméra. La photo
  capturée reste en attente (miniature) jusqu'à l'envoi du message.

**Vérifié réellement**
- Pipeline complet testé en process avec une vraie image (créée avec
  PIL, encodée en base64) via un client WebSocket réel contre l'appli
  réelle (montée avec son vrai cycle de vie — DB, monitors, 22 outils) :
  séquence d'états correcte (thinking → speaking → idle), bon modèle
  utilisé (`llava`, pas le modèle à outils), image transmise intacte
  (comparaison de longueur), légende par défaut appliquée quand aucun
  texte n'est fourni, erreur propre si le modèle vision est injoignable,
  message vide ignoré sans planter la connexion.
- Mémoire vérifiée en base : le résumé texte est bien sauvegardé
  (`"<légende> [a envoyé une photo]"` + la réponse), jamais l'image.
- App complète redémarrée après ces changements : 22 outils, 2 monitors,
  rien de cassé.

---

## 2026-09-26 — Non-root pour EVA CORE (referme le trou RLIMIT_NPROC)

**Ajouté**
- `eva-core/docker-entrypoint.sh` : au démarrage du conteneur, aligne un
  groupe sur le GID réel du socket Docker monté (variable d'un hôte à
  l'autre), corrige la propriété du volume workspace si besoin, puis passe
  de root à l'utilisateur `eva` (non-root) via `setpriv` avant d'exécuter
  la commande réelle.
- `Dockerfile` : crée l'utilisateur `eva`, installe `passwd`/`util-linux`
  (nécessaires à l'entrypoint), utilise ce script comme `ENTRYPOINT`.

**Corrections trouvées en testant, pas supposées**
- **Ma première mesure du fork-bomb était fausse** : mon test lançait des
  sous-shells en séquence, chacun terminé avant le suivant — jamais plus
  d'1-2 process simultanés, donc `RLIMIT_NPROC` (32) n'était jamais mis à
  l'épreuve, ni en root ni en non-root. Refait avec 60 process réellement
  concurrents (`sleep 3 &` en boucle) : en root, les 60 démarrent (confirme
  l'exemption `CAP_SYS_RESOURCE`) ; en non-root, ça échoue avec
  "Cannot fork" une fois la limite atteinte — la protection marche
  vraiment, il fallait juste tourner en non-root pour en profiter.
- **Bug réel trouvé en testant le passage en non-root** : `setpriv` ne
  change pas `$HOME`, qui restait à `/root`. asyncpg tente par défaut de
  lire `$HOME/.postgresql/postgresql.key` pour un éventuel certificat SSL
  → `PermissionError` sur `/root/.postgresql/postgresql.key` (illisible
  pour l'utilisateur non-root), et le démarrage de l'app plantait
  entièrement. Corrigé en export `HOME=/home/eva` avant `setpriv` dans
  l'entrypoint. Vérifié avant/après : le chemin résolu par asyncpg passe
  bien de `/root/...` à `/home/eva/...`, et l'app démarre et se connecte à
  Postgres correctement en non-root avec le vrai entrypoint.
- Vérifié aussi : le volume workspace, même créé par root au premier
  montage, est correctement re-chown vers `eva:eva` par l'entrypoint —
  testé avec un dossier délibérément root:root avant le premier démarrage.

---

## 2026-09-23 — Outils Git, monitor de seuils système

**Ajouté**
- `harness/tools/git_tools.py` : `git_status`, `git_log`, `git_diff`
  (AUTO) et `git_commit` (CONFIRM, fait `git add -A` puis commit) — tous
  scopés à un dépôt dans le workspace.
- `harness/monitors/system_threshold.py` : `SystemThresholdMonitor`,
  réutilise `system_stats` — signale un dépassement de seuil (CPU/RAM/
  disque, 90% par défaut, réglable) puis le retour à la normale, sans
  spammer tant que ça reste au-dessus.
- `eva-core/Dockerfile` : installe `git` (paquet système, nécessaire aux
  nouveaux outils — **oublié dans la première passe, corrigé ici**).

**Vérifié réellement**
- Outils Git testés sur un vrai dépôt (status, log, diff, commit qui
  fonctionne vraiment, commit sans rien à commiter, dépôt inexistant,
  tentative d'évasion du workspace) — 8 cas, tous corrects.
- Monitor de seuils testé : pas de notif à l'état normal, alerte au
  dépassement, **pas de répétition** tant que ça reste haut, notification
  de retour à la normale — les 4 cas se comportent exactement comme prévu.
- App complète redémarrée avec les 22 outils et les 2 monitors actifs en
  même temps, sans régression.

---

## 2026-09-22 (suite) — Actions Docker, durcissement de terminal_run

**Ajouté**
- `harness/tools/docker_tools.py` : `docker_restart`, `docker_stop`,
  `docker_start` (toutes CONFIRM) — EVA peut maintenant non seulement
  diagnostiquer un conteneur cassé mais le relancer, avec confirmation.
- `harness/tools/terminal.py` : limites de ressources réelles sur les
  commandes exécutées — mémoire (512 Mo), temps CPU, et le timeout tue
  maintenant tout l'arbre de processus (pas juste le shell parent).

**Vérifié réellement — deux bugs trouvés et corrigés pendant les tests**
- `docker_restart` avait été écrit mais oublié dans `registry.py` :
  premier test → "Outil inconnu". Corrigé, puis testé pour de vrai à
  travers tout le Harness (refus de confirmation → conteneur inchangé ;
  approbation → conteneur relancé).
- Limite mémoire testée : une tentative d'allouer 2 Go échoue bien
  (`MemoryError`) au lieu de réussir.
- **Bug plus subtil** : le timeout tuait seulement le process shell, pas
  ses enfants — testé avec une boucle Python infinie lancée depuis le
  shell : la commande a mis 8s à s'arrêter au lieu des 3s demandés (c'est
  en fait la limite CPU de secours, pas notre timeout, qui l'a arrêtée).
  Corrigé en lançant la commande dans son propre groupe de process
  (`os.setsid`) et en tuant tout le groupe (`os.killpg`) — retesté : 3.0s
  pile.
- **Limite honnêtement documentée, pas cachée** : `RLIMIT_NPROC` (anti
  fork-bomb) n'a aucun effet réel tant qu'EVA CORE tourne en root dans le
  conteneur (Linux exempte les processus avec `CAP_SYS_RESOURCE`) —
  vérifié en essayant de lancer 100 sous-process, aucun n'a été bloqué.
  Documenté dans le README plutôt que de prétendre que c'est réglé.

---

## 2026-09-22 — Outils Web (recherche + lecture de page)

**Ajouté**
- `harness/tools/web.py` : `web_search` (DuckDuckGo, endpoint HTML sans
  JavaScript, sans clé d'API) et `web_fetch` (lit le texte d'une page,
  HTML nettoyé des scripts/styles/nav ou texte brut).

**Vérifié réellement**
- `web_search` : parsing testé contre une fixture reproduisant la
  structure HTML réelle confirmée (DuckDuckGo non joignable depuis ce
  sandbox). **Bug trouvé et corrigé pendant le test** : le sélecteur
  initial matchait à la fois le conteneur `div.result` et son enfant
  `div.result__body`, doublant chaque résultat — corrigé, et testé aussi
  le filtrage des liens publicitaires sans URL réelle.
- `web_fetch` : testé contre de vraies pages en ligne (une page HTML
  GitHub, un fichier texte brut) — extraction du titre et du texte
  fonctionnelle sur les deux formats, rejet propre d'un schéma d'URL
  invalide.

---

## 2026-09-21 (suite) — Dashboard Projets/Mémoire

**Ajouté**
- `app/routes_dashboard.py` : `GET /api/dashboard/projects` (liste avec
  description extraite du README), `GET /api/dashboard/projects/{slug}`
  (contenu des 5 docs), `GET /api/dashboard/memory` (historique persistant)
- `app/main.py` : dépendance `require_auth` partagée — **correction** : les
  endpoints `/api/widgets/*` n'avaient en fait aucune vérification du
  jeton malgré `EVA_AUTH_TOKEN`, c'est corrigé et appliqué aussi au
  dashboard. `/api/health` reste volontairement ouvert (diagnostic).
- Frontend : `DashboardPanel.jsx`, une vue en overlay avec onglets
  Projets/Mémoire, branchée sur le bouton "Projets" du dock (qui ne
  faisait rien jusqu'ici).

**Vérifié réellement**
- Endpoints testés avec de vraies fixtures de projet (README + DECISIONS) :
  liste correcte, description extraite, contenu des docs, 404 propre sur
  projet inexistant
- `/api/dashboard/memory` testé : renvoie bien l'historique réel persisté
  en base
- Auth testée sur les 3 endpoints (dashboard + les 3 widgets) : 401 sans
  jeton, 200 avec le bon jeton ; `/api/health` reste accessible sans jeton

---

## 2026-09-21 — Terminal, monitoring système, widgets réels, file d'attente

**Ajouté**
- `app/broker.py` : `MessageBroker` — un seul lecteur WebSocket qui
  distribue les messages via une queue, pour que `confirm_gate()` et la
  boucle principale ne se marchent plus dessus. Un message envoyé pendant
  une confirmation en attente est maintenant traité juste après, plutôt
  que perdu.
- `harness/tools/terminal.py` : `terminal_run` — exécute une commande
  shell dans le workspace. Toujours CONFIRM, même en lecture seule (ce
  n'est pas un vrai sandbox, juste un `cwd` restreint).
- `harness/tools/system_stats.py` : `system_stats` (CPU/RAM/disque, via
  psutil) — la capacité "lire l'état du NAS" du brief initial.
- `GET /api/widgets/weather`, `/api/widgets/system`, `/api/widgets/docker`
  — endpoints REST directs (sans passer par le LLM) pour les widgets.
- Frontend : les 3 widgets (météo, docker, système) affichent maintenant
  de vraies données, avec polling (`useWidgetData`). Le widget "maison"
  devient un widget Docker en attendant l'outil Home Assistant.

**Vérifié réellement**
- `MessageBroker` : testé avec un faux WebSocket — un message reçu
  pendant une confirmation en attente est bien remis dans la file et
  récupéré ensuite, pas perdu.
- `terminal_run` : testé en vrai (`ls`, `cat`, `pwd` confirme le bon
  `cwd`, commande en échec, timeout qui tue le process).
- `system_stats` : testé en vrai, retourne les vraies stats de la machine.
- Endpoints widgets : testés en vrai sur le serveur démarré (`/system` ok,
  `/docker` échoue proprement sans daemon disponible ici).

---

## 2026-09-18 (suite) — Docs Markdown auto, comportement proactif, sécurité, nouveaux outils

**Ajouté**
- `harness/tools/project_docs.py` : `project_init`, `project_log_decision`,
  `project_log_change` — EVA tient elle-même README/OBJECTIFS/DECISIONS/
  CHANGELOG/TODO de ses projets, avec horodatage automatique. Le prompt
  système lui dit de les utiliser proactivement, sans qu'on le demande.
- `harness/tools/filesystem.py` : ajout de `fs_append` (AUTO) et `fs_delete`
  (CONFIRM). **Correction** : `fs_write` était par erreur en CONFIRM, remis
  en AUTO — le brief initial classe la création de fichier comme
  auto-autorisée, seule la suppression doit être confirmée.
- `harness/monitors/` : système de "Monitors" — tâches de fond qui
  vérifient périodiquement quelque chose et peuvent notifier sans qu'on
  demande. Premier monitor : `WorkspaceWatchMonitor` (signale les fichiers
  créés/modifiés/supprimés dans le workspace).
- `app/connections.py` : `ConnectionManager`, pour qu'une tâche de fond
  puisse pousser un message à un client WebSocket connecté sans requête
  préalable — le mécanisme qui rend le comportement proactif possible.
- Authentification optionnelle par jeton partagé (`EVA_AUTH_TOKEN`) : sur
  le WebSocket d'EVA CORE (`?token=...`) et sur `/stt`/`/tts` d'EVA VOICE
  (`Authorization: Bearer ...`). Avertissement au démarrage si absent.
- `harness/tools/weather.py` : `weather_get`, via Open-Meteo (gratuit, sans
  clé d'API) — géocodage + météo actuelle + prévisions.
- `harness/tools/docker_tools.py` : `docker_ps`, `docker_logs` (lecture
  seule, nécessite `/var/run/docker.sock` monté dans le conteneur).
- Frontend : bulle "proactive" gérée dans `useEvaCore`, jeton d'auth branché
  dans `useEvaCore`/`useVoice`.

**Vérifié réellement**
- `project_init`/`project_log_decision`/`project_log_change`/`fs_delete` :
  testés en vrai (non-écrasement, log daté, suppression, erreur propre sur
  projet inexistant)
- Monitor : testé avec le serveur réellement démarré — un client connecté
  reçoit une notification spontanée après un changement dans le workspace,
  sans avoir rien demandé
- Auth : testés les 3 cas réels (sans jeton / mauvais jeton / bon jeton)
  sur EVA CORE (WebSocket) et EVA VOICE (`/stt`, `/tts`)
- `weather_get` : logique de parsing testée contre le schéma réel de
  l'API Open-Meteo (confirmé via recherche web, domaine non joignable
  depuis ce sandbox — fonctionnera normalement en déploiement réel)
- `docker_ps`/`docker_logs` : testés avec un faux client Docker (pas de
  daemon dans ce sandbox) — la gestion d'erreur "Docker injoignable" est
  elle bien testée en conditions réelles (pas de socket ici)

---

## 2026-09-18 — Docker-compose complet + STT/TTS

**Ajouté**
- `eva-voice/` : service FastAPI séparé pour la voix
  - `POST /stt` (faster-whisper) — audio → texte
  - `POST /tts` (Piper) — texte → WAV
  - Chargement paresseux des modèles (le service démarre même sans modèle
    déjà téléchargé)
- `docker-compose.yml` racine : les 4 services ensemble (`eva-db`,
  `eva-core`, `eva-voice`, `eva-interface`) + volumes + healthchecks
- `eva-interface/Dockerfile` (multi-stage : build Vite → nginx) + `nginx.conf`
- Frontend : `useVoice.js` (enregistrement micro réel → `/stt`, lecture
  audio des réponses → `/tts`) ; ne parle à voix haute que si la question
  venait du micro (pas si on a tapé au clavier)

**Vérifié réellement**
- Endpoints `/stt` et `/tts` testés (upload multipart, réponse WAV,
  rejet texte vide) — modèles mockés, la plomberie HTTP est validée
- YAML du docker-compose validé (4 services, 2 volumes)

**Limite connue**
- Les modèles vocaux (voix Piper, modèle Whisper) doivent être téléchargés
  manuellement sur la machine réelle — pas testables depuis l'environnement
  où ce code a été écrit (pas d'accès à Hugging Face)

---

## 2026-09-18 — Agent Harness + Mémoire persistante

**Ajouté**
- `eva-core/app/harness/` : boucle d'agent (thinking → acting → observation
  → conclusion), avec :
  - `permissions.py` : niveaux AUTO / CONFIRM / FORBIDDEN
  - `tools/filesystem.py` : `fs_list`, `fs_read`, `fs_write`, sandboxés au
    workspace (`EVA_WORKSPACE`)
  - `registry.py` : catalogue d'outils, génère les schémas pour Ollama
  - `loop.py` : `run_harness()`, la boucle elle-même, avec pause de
    confirmation (`confirm_gate`) pour les outils sensibles
- `eva-core/app/db.py` + `memory.py` : Postgres, historique de conversation
  persistant par session (`?session=...` dans l'URL WebSocket)
- Frontend : bulles système pour les appels d'outils, bulle de confirmation
  avec boutons Autoriser/Refuser (`ChatDrawer`, `useEvaCore`)

**Vérifié réellement**
- Sandboxing filesystem : tentative d'évasion (`../../../etc/passwd`,
  chemin absolu) refusée
- Boucle complète testée avec un faux Ollama (mock) simulant une décision
  d'appeler `fs_list`, puis une conclusion
- Confirmation refusée → le fichier n'est PAS créé (testé en vrai)
- Mémoire testée avec un vrai Postgres local : sauvegarde + rechargement
  fonctionnent

---

## 2026-09-15 — EVA CORE + connexion Ollama

**Ajouté**
- `eva-core/` : FastAPI, `/ws/chat` (WebSocket streaming), `/api/health`
- `ollama_client.py` : appel streamé à Ollama (`/api/chat`)
- Frontend : `useEvaCore.js`, connexion réelle en remplacement de la
  simulation, indicateur de connexion dans la top bar

**Vérifié réellement**
- Serveur démarre, `/api/health` répond
- WebSocket testé de bout en bout, y compris le cas Ollama injoignable
  (erreur propre renvoyée, pas de crash)

---

## Avant — Interface V1

- Structure React/Vite/PWA : avatar 3D (`react-three-fiber`), chat,
  widgets météo/maison/système, dock micro/caméra
- Le logo fourni remplace entièrement la tête du buste (animé : rotation +
  anneau HUD pulsant), plutôt qu'un visage robotique générique
- Thème visuel "Jarvis" : buste holographique translucide, wireframe,
  cadre HUD, scanline, socle de projection
- Correction d'un bug de tri de transparence qui rendait le logo invisible
  derrière la tête holographique
