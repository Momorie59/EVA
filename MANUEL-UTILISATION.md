# EVA — Manuel d'utilisation

EVA est l'assistante de la maison. Elle tourne chez toi : ton NAS et ton serveur IA. Tant que tu ne choisis pas toi-même une IA en ligne, rien ne part sur Internet. Tu peux lui parler par écrit ou à voix haute. Elle pilote la maison, gère tes listes, tes papiers et tes agendas, crée de vrais fichiers, cherche sur le web et se souvient de ce qui compte pour toi.

Adresse : **`https://192.168.1.10:8443`** (sur téléphone, installe-la comme une application : voir §11). Pour installer ou mettre à jour EVA : `MANUEL-INSTALLATION.md`.

---

## 1. Premiers pas

**L'écran** : la barre de gauche liste les pages (Conversation, Maison, Listes…) et tes conversations. En bas, le dock donne le micro 🎙️, l'écoute mains libres, la caméra 📷 et la reconnaissance de musique 🎵.

**Parler à EVA**, au choix :

- **Écrire** dans la page *Conversation*.
- **Appuyer sur le micro**, parler, relâcher.
- **Mains libres** : active l'écoute, puis dis « **EVA**, … » sans toucher à rien.
- **Satellite** dans une pièce : « EVA, allume la lumière » (voir §8).

**Une nouvelle conversation à chaque fois** : EVA repart d'une page blanche, mais elle garde ses souvenirs (§9). Les anciennes conversations restent à gauche : clic droit ou ⋯ pour les renommer, les supprimer ou les rattacher à un projet.

**Arrêter une réponse** : pendant qu'EVA répond, le bouton « Envoyer » devient **■ Arrêter** (rouge).

**Quand EVA demande ton accord** (envoyer un e-mail, appeler, éteindre un appareil sensible, cliquer sur ton écran…) :

- **Une fois** : l'action est faite cette fois-ci seulement.
- **Toujours** : EVA ne te redemandera plus pour cette action.
- **Refuser** : rien n'est fait.

Pour les actions les plus sensibles, EVA redemande à chaque fois.

---

## 2. Ce que tu peux lui demander (exemples)

| Domaine | Exemples |
|---|---|
| Questions, rédaction | « Explique-moi… », « Rédige une lettre de résiliation », « Résume ce PDF » (trombone 📎) |
| Recherche web | « Compare les pompes à chaleur air-eau, avec les sources » |
| Vrais fichiers | « Fais-moi le compte rendu en Word / PDF / PowerPoint / Excel » |
| Tâches longues | « Prépare un comparatif en fond et préviens-moi » |
| Maison | « Allume le salon », « Mode film », « Qui est à la maison ? », « Monte le son de l'enceinte de la cuisine » |
| Listes | « Ajoute du lait à la liste de courses », « Qu'est-ce qu'il reste à faire ? », « Crée-moi une liste privée d'idées cadeaux » |
| Rappels, minuteurs | « Rappelle-moi de sortir le gâteau dans 10 minutes », « Tous les jours à 8 h, rappelle-moi le café », « Annule le rappel du café » |
| Tâches automatiques | « Chaque matin à 7 h 30, donne-moi la météo et mes rendez-vous », « Mets en pause la tâche du matin » |
| Recettes | « Ajoute la recette de la paella avec une photo » (EVA la dessine), « Remplace les moules par des crevettes » (ingrédients **et** étapes), « Passe-la à 6 personnes », « Donne-moi un lien pour la partager » |
| Carnets, wiki | « Note dans le carnet Vacances, section Bretagne : crème solaire », « Crée une page wiki sur le potager, avec une illustration » |
| Budget | « Note 12,50 € au marché », « Fixe un budget de 300 € pour l'alimentation » |
| Agenda, mails | « Qu'est-ce que j'ai demain ? », « Déplace le dentiste à 15 h », « Supprime le rendez-vous de jeudi », « Ai-je des mails importants ? », « Où en sont mes colis ? » |
| Papiers | « Quand finit mon contrat d'assurance ? », « Quelles échéances ce mois-ci ? » |
| Musique | « Mets du Daft Punk », « C'est quoi cette musique ? » |
| Images | « Dessine un chalet sous la neige », « Crée un coloriage de banane » (trait noir, prêt à imprimer), « Fais une carte d'anniversaire », photo + « enlève la personne à gauche » |
| Annonces | « Annonce dans la cuisine que le dîner est prêt », « Annonce partout… » |
| Ordinateur | « Ouvre Spotify sur le PC », « Baisse le son », « Qu'est-ce qu'il y a sur mon écran ? », « Clique sur Envoyer » |
| Routines | « Tous les soirs à 22 h, lance la scène Bonne nuit », « Si la température du salon dépasse 26 °C, allume le ventilateur », « Quand la porte du garage s'ouvre, préviens-moi » |
| TV, enceintes Google | « Mets la dernière vidéo de Cyprien sur la TV du salon », « Lance cette radio sur l'enceinte de la cuisine », « Pause sur la TV », « Monte le son de la TV » |
| Prendre la main | « Prends la main : ouvre le bloc-notes et écris la liste de courses », « Va sur YouTube et mets la dernière vidéo de… » (voir §8) |

Quand EVA ne sait pas encore faire quelque chose, elle te le dit **et note la demande** : tu les retrouves dans *Évolution › Demandes d'évolution* (avec le nombre de fois où elle a été faite), pour savoir quoi ajouter ensuite.

Quand une précision change vraiment le résultat (format, destinataire…), EVA te pose une **question à choix**. Clique sur une réponse ou tape la tienne.

Pour une tâche en plusieurs étapes, une **carte de plan** 📋 montre les étapes cochées au fur et à mesure.

---

## 3. Choisir le modèle d'IA

En haut de la page *Conversation*, le bouton **✨ Automatique** ouvre le choix du modèle :

- en haut, deux raccourcis : **✨ Automatique** (EVA choisit) et **🔁 IA gratuites** (passe de l'une à l'autre) ;
- une **recherche** et des filtres : Tous, 🖥️ Chez moi, 🆓 Gratuits, ☁️ Payants, 👁 Images ;
- **★** à droite d'un modèle le met en **favori** (toujours en haut) ; tes 3 derniers choix apparaissent dans **🕘 Récents** ;
- les services en ligne sont **repliés** (▸ Groq — 12 modèles) : clique pour les ouvrir.

Les modèles sont rangés par origine :

- 🖥️ **Mon serveur IA** : sur ton serveur, rien ne sort de la maison. C'est le choix par défaut.
- 🆓 **IA gratuites** : services en ligne gratuits, avec des limites (voir §4).
- ☁️ **IA du marché** : OpenAI, Claude, Gemini… payantes selon l'usage. Un budget mensuel est possible.
- 🐢 **AirLLM** : un très gros modèle, très lent (plusieurs minutes par réponse). Seulement si tu le choisis.

Les badges de chaque modèle :

| Badge | Signification |
|---|---|
| ⚡ en mémoire | Répond tout de suite, sans temps de chargement |
| 🛠 outils | Peut piloter la maison, l'agenda, la recherche… |
| 👁 images | Comprend les photos |
| 🌐 Internet | Tes messages partent chez ce service |
| ⚠️ entraînement | Ce service peut entraîner ses modèles avec tes messages |

**Automatique** : EVA choisit elle-même selon la demande (un petit modèle rapide pour bavarder, le gros pour le code ou les analyses). Ces réglages se trouvent dans Paramètres › Intelligence.

---

## 4. IA gratuites (Groq, Gemini, NVIDIA, OVHcloud…)

Paramètres › Intelligence › IA du marché › **IA gratuites** :

1. **Ajouter** à côté d'un service : tout est prérempli (adresse, modèles, prix à 0).
2. **« Obtenir ma clé »** : crée un compte gratuit sur leur site, sans carte bancaire, puis colle la clé dans EVA. OVHcloud, LLM7 et Kilo Code marchent même sans clé.
3. Dans la conversation, choisis **« IA gratuites — automatique »** : EVA passe toute seule d'un service à l'autre quand l'un a atteint son quota ou est en panne.

Dans **« IA gratuites automatiques »**, tu peux :

- cocher ou décocher chaque modèle ;
- changer l'ordre avec ↑ ↓ ;
- voir ceux qui sont en pause et jusqu'à quand.

Par défaut, les services qui entraînent leurs modèles avec tes messages sont exclus.

Plus tu ajoutes de services avec leur clé gratuite, moins EVA tombe à court. Conseillés : Groq, Google Gemini (pas d'entraînement en Europe), NVIDIA NIM.

**Prudence** : pour tes papiers, ta santé ou ta banque, reste sur 🖥️ Mon serveur IA.

---

## 5. Les pages

| Page | À quoi elle sert |
|---|---|
| **EVA** (accueil) | L'avatar, les post-it, la météo et les widgets. « Mets un post-it : appeler le garage » |
| **Conversation** | Discuter, joindre des fichiers, choisir le modèle, suivre le plan et les tâches en fond. 🗑 dans l'historique : la **corbeille** (une conversation supprimée s'y garde 30 jours) |
| **Tableau de bord** | État du NAS, du serveur IA, de Docker, de la météo |
| **Projets** | Dossiers de travail : EVA y range fichiers et décisions. Partage possible avec d'autres comptes |
| **Maison** | Appareils, scènes, **routines**, présence, imprimantes, réseau, **satellites** (installation depuis la page) |
| **Listes** | Courses, tâches… remplies à la voix. Listes **🔒 privées** (toi seul les vois). Courses **rangées par rayon** du magasin ; 📱 Partager vers le téléphone, Copier, Telegram, impression recto-verso |
| **Carnets** | Notes en sections et pages, à partager |
| **Salon** | Qui est connecté, discussion écrite, appel voix ou vidéo entre les comptes |
| **Images** | Créer, retoucher, galerie (☑ Sélectionner : supprimer, garder ou enregistrer plusieurs images d'un coup) |
| **Papiers** | Tes documents administratifs, leurs échéances et les rappels |
| **Wiki**, **Recettes** | Modules à activer : savoir de la famille, livre de recettes avec liste de courses |
| **Finances** | Module privé : comptes, relevés CSV ou OFX, budgets. Chacun ne voit que les siens |
| **Contenus** | Module : vidéos et publications, de l'idée à la publication |
| **Mémoire** | Ce qu'EVA a retenu de toi. Corrige ou oublie ce que tu veux |
| **Agents** | Tâches automatiques planifiées (briefing du matin…) |
| **Skills**, **Sources** | Savoir-faire installés et documents indexés |
| **Traces** | Ce qu'EVA a fait, étape par étape, conversation par conversation |
| **Journal** | Tout ce qu'EVA a fait, filtrable : outils utilisés, erreurs, apprentissage, évolution de son code, tâches en fond, routines, satellites, redémarrages |
| **Apprentissage** | **EVA apprend de ses erreurs** : elle note ses ratés et en tire chaque nuit des leçons vérifiées, appliquées toutes seules (désactivables). Choix de l'IA qui étudie, heure. **Corrections de son code** : non, proposées (tu acceptes), ou **« Évoluer toute seule »** : la nuit, elle applique au plus une correction par nuit, compare son banc d'essai avant/après et revient en arrière toute seule si elle marche moins bien ; ses modifications sont reportées sur chaque nouvelle version |
| **Apprentissage**, **Évolution** | EVA propose des améliorations d'après tes avis 👍 👎. Rien ne s'applique sans ton accord. Dans Évolution : les **demandes d'évolution** et le **banc d'essai des outils** (quel outil chaque modèle choisit pour 44 phrases types, sans rien exécuter) |
| **Paramètres** | Tous les réglages (§10) |

Un module éteint (Wiki, Recettes, Finances, Contenus) disparaît du menu. Pour en activer un : Paramètres › Modules.

---

## 6. La voix

- **Micro** : appuie, parle, relâche. La réponse est lue à voix haute dès la première phrase prête.
- **Mains libres** : active l'écoute, puis dis « **EVA** » au début de ta phrase.
- **Voix, micro, mot d'éveil, reconnaissance des personnes** : Paramètres › Voix & personnes. Le diagnostic du micro te dit ce qu'EVA a compris.
- **Langues** : EVA comprend la langue parlée et répond dans la même. Les voix des autres langues se téléchargent toutes seules.
- **Moteur de la voix** : Paramètres › Voix › « Moteur » : Piper (sur ton serveur, rien ne sort) ou **voix Microsoft** (bien plus naturelles ; le texte lu part chez Microsoft). Vaut pour tous les écrans et satellites.
- **Écoute** : si le micro du navigateur comprend mal, « Reconnaissance de ma voix » › Navigateur (rapide et juste, mais l'audio part chez Google). L'appli Android utilise la reconnaissance du téléphone par défaut.
- **Voix par langue** : Paramètres › Voix, « Voix par langue ». Choisis la voix du français, de l'italien, de l'anglais… (▶ pour l'écouter). Une voix pas encore installée se télécharge une fois.
- **Personnalité** : « passe en mode majordome », « sois plus concise », « mode normal ».

---

## 7. La maison

Tout se règle dans la page *Maison*. Le détail est dans `MAISON.md`.

- **Appareils** : Tuya, Shelly, Hue, Yeelight, WiZ, Home Assistant, Google Home ou Chromecast, imprimantes… La détection réseau les trouve, puis tu les ajoutes d'un clic.
- **Scènes** : « mode film », « tout éteindre ». Une scène peut se lancer automatiquement quand tout le monde part ou quand quelqu'un rentre.
- **Présence** : les téléphones vus sur le wifi. Désactive l'**adresse MAC aléatoire** du wifi de la maison sur chaque téléphone.
- **Appareils sensibles** : EVA demande ton accord avant de les toucher.

**Routines** (Maison › Routines, ou en parlant à EVA) : à une heure et des jours choisis, ou quand un capteur de Home Assistant change (température, mouvement, porte, `sun.sun` = nuit), EVA lance une scène, pilote un appareil, fait une annonce ou te prévient. Un capteur ne redéclenche qu'après être revenu à la normale. Ce qui est sensible (volets, ordinateurs) n'est jamais lancé tout seul : EVA te prévient à la place. Bouton **Essayer** pour tester.

---

## 8. Satellites : EVA dans chaque pièce et sur ton PC

Un satellite, c'est un micro et un haut-parleur (Raspberry Pi, vieux PC, ton PC Windows, Mac ou Linux, ou un **téléphone Android** avec l'appli EVA Satellite) qui écoute « **EVA…** ». **Installation depuis EVA** : Maison › Satellites › Ajouter (ou Installer) → choisis le système et les options → Windows : double-clic sur le fichier téléchargé ; Mac / Linux : une commande à coller. Il se met ensuite **à jour tout seul**. Détails : `MANUEL-INSTALLATION.md` §7.

- **Dans une pièce** : « EVA, allume la lumière » allume celle de cette pièce. « EVA » tout seul déclenche un bip : tu as alors 8 secondes pour parler.
- **Action sensible** : EVA demande « Tu confirmes ? ». Réponds « oui » ou « non ».
- **Plusieurs satellites** : seul celui qui t'entend le mieux répond.
- **Sur ton PC**, selon les options installées :
  - **fenêtre flottante** avec ce que tu dis et la réponse. « EVA, mode silencieux » : elle écrit sans parler ; « EVA, reparle » pour revenir.
  - **tableau au repos** : heure, météo, rendez-vous, colis, musique, post-its. Un clic le cache 30 minutes.
  - **écran** : « qu'est-ce qu'il y a sur mon écran ? », « lis-moi ce message d'erreur », « clique sur Envoyer ». Toujours avec ton accord, et jamais sur la banque, les impôts ou la santé.
  - **mode opérateur** (« prends la main… ») : EVA fait la tâche à ta place — elle lit l'écran, clique, écrit, appuie sur les touches, ouvre une appli ou un site. Tu donnes ton accord une fois au départ ; chaque étape s'affiche dans la carte 📋 ; le bouton **Arrêter** coupe tout. Elle **s'arrête avant d'envoyer, payer, commander, publier ou supprimer** et te demande « je clique sur Envoyer ? ». Elle refuse les fenêtres de banque, d'impôts, de santé et de mots de passe. Il faut l'option écran du satellite à jour (relance l'installateur).
  - **gestes** devant la webcam (voir le tableau ci-dessous). L'image ne quitte jamais le PC.

| Geste | Effet |
|---|---|
| Main ouverte immobile | Lecture / pause |
| Poing | EVA se tait |
| 2 doigts | Mode onglets : main à gauche ou à droite pour changer d'onglet, en haut ou en bas pour défiler |
| 3 doigts | Mode audio : en haut ou en bas pour le volume, à gauche ou à droite pour la piste |
| Index | Mode souris |
| Deux mains | Zoom |
| Pouce levé ou baissé | « Oui » ou « non » quand EVA te demande ton accord |

- **Annonces** : « annonce dans la cuisine… » passe par les satellites, les enceintes Google et les Echo (Alexa via Home Assistant).
- **Pause** : ⏸ dans Maison › Satellites, l'icône EVA à côté de l'horloge, les raccourcis « EVA pause » / « EVA reprise » sur le bureau, ou « EVA, pause ». En pause, il n'écoute plus rien (les annonces passent toujours).
- **Démarrer / arrêter / redémarrer** : raccourcis « EVA démarrer » / « EVA arrêter », icône EVA (clic droit), ou ↻ / ⏹ dans Maison › Satellites.
- **Il ne réagit pas à « EVA »** : 🩺 Diagnostic dans Maison › Satellites, puis « Tester le haut-parleur et le micro ».
- **Téléphone perdu** : « EVA, où est mon téléphone ? » le fait sonner fort, même en silencieux (appli Android).
- **Désinstaller** : Supprimer dans Maison › Satellites ; allumé, il se désinstalle tout seul (sinon EVA donne la commande).

---

## 9. Mémoire et vie privée

- EVA **retient** ce que tu lui dis de durable : « je m'appelle… », « ma fille fait du judo le mercredi ». Page *Mémoire* : voir, corriger, oublier.
- **« Mes données »** (Paramètres › Sécurité & données) : télécharge ou efface tout ce qui te concerne.
- **Chacun ses affaires** : conversations, fichiers, finances et mémoire sont privés par compte. Ce qu'on partage, on le partage exprès (projets, carnets, contenus).
- **À voix haute**, EVA ne dit jamais une clé, un mot de passe, un numéro de carte ni un IBAN. Dans une annonce pour toute la maison, elle ne dit pas non plus les adresses mail ni les numéros de téléphone.

---

## 10. Les Paramètres en bref

| Section | Contenu |
|---|---|
| **Intelligence** | Modèles installés, choix automatique (profil Rapide ou Équilibré), personnalité, IA du marché et **IA gratuites**, AirLLM, budget |
| **Apprentissage** | Règles proposées d'après tes avis |
| **Images** | Serveur et modèles d'images |
| **Voix & personnes** | Voix, micro, mot d'éveil, reconnaissance des personnes |
| **Services connectés** | Google (Gmail, Agenda), agendas iCal, Home Assistant, Telegram, Spotify, OBS, Discord, Instagram, appels (Twilio), raccourcis du téléphone, outils MCP |
| **Sécurité & données** | Connexion, double authentification, utilisateurs et profils, droits par personne, journal d'accès, sauvegarde et restauration, « Mes données », HTTPS |
| **Modules** | Wiki, Recettes, Finances, Contenus |
| **Apparence & application** | Thème, couleurs, disposition, installation sur téléphone ou ordinateur |

La recherche en haut des Paramètres trouve un réglage par mot-clé : « airllm », « voix », « sauvegarde »…

---

## 11. Sur le téléphone

1. Ouvre `https://192.168.1.10:8443` et installe le certificat une fois : `https://192.168.1.10:8443/api/https/install`.
2. Va dans Paramètres › Apparence & application › **Installer** : EVA arrive sur l'écran d'accueil, en plein écran.
3. **Raccourcis** : « Dis Siri, dis à EVA… » (Paramètres › Services connectés › Raccourcis).

---

## 12. Petits soucis

| Ce que tu vois | Ce qu'il faut faire |
|---|---|
| « Erreur 502 » juste après une mise à jour | EVA redémarre : attends 1 à 2 minutes, puis **Ctrl+F5** |
| Plus de conversations à gauche | **Ctrl+F5**. Rien n'est perdu : elles sont dans la base |
| « Serveur IA injoignable » | Le serveur IA est-il allumé ? En attendant, choisis « IA gratuites — automatique » |
| « Aucune IA gratuite disponible » | Toutes ont atteint leur quota : ajoute d'autres services avec leur clé gratuite, ou attends l'heure indiquée |
| Une réponse tourne en boucle | **■ Arrêter**, puis ouvre une nouvelle conversation |
| EVA ne m'entend pas | Paramètres › Voix & personnes › Diagnostic du micro. En HTTP, le micro est bloqué : utilise HTTPS |
| Une photo n'est pas comprise | Il faut un modèle « 👁 images » (llava) : Paramètres › Intelligence › Modèles installés |

Le reste se règle sur le NAS : voir `MANUEL-INSTALLATION.md` §8.
