# Maison : appareils, listes, impression, réseau

Tout se règle dans l'interface (menus **Maison** et **Listes**) et se commande à la voix ou au texte :
« éteins les lumières du salon », « ajoute du lait à la liste de courses », « imprime la liste », « lance la scène cinéma »,
« analyse le réseau ».

## Appareils par pièce (Maison › Appareils)
Chaque appareil a un nom, une pièce, un type et un pilote :

| Pilote | Pour | Notes |
|---|---|---|
| **Tuya / Smart Life** | prises, ampoules, ventilateurs, volets Tuya | cloud (sans adresse IP) ou **local** (adresse IP + clé locale) ; import automatique depuis ton compte Tuya IoT |
| **Shelly** (gen 1 et 2), **Tasmota**, **WLED** | prises, relais, bandeaux LED | HTTP local, adresse IP |
| **Wake-on-LAN** | allumer un PC / serveur | adresse MAC ; l'état se lit avec l'IP ; ne sait pas éteindre |
| **MQTT** | tout ce qui parle MQTT (Zigbee2MQTT…) | serveur, topics, messages ON/OFF |
| **Home Assistant** | appareils déjà gérés par HA | entité `light.salon`… (HA se configure dans Paramètres) |

Actions : allumer, éteindre, basculer, luminosité (0-100), couleur (rouge, vert, bleu, blanc chaud… ou `#RRGGBB`), température, état.
EVA retrouve l'appareil par son nom approximatif, ses « autres noms » ou la pièce (« toutes les lumières du salon »).

**Garde-fous** : serrures, alarmes, portails et portes ne peuvent pas être enregistrés. Volets, ordinateurs et tout appareil marqué
« demander confirmation » exigent ton accord avant qu'EVA les commande ; au-delà de 6 appareils d'un coup aussi.
Les clés locales et mots de passe ne sont jamais renvoyés au navigateur.

### Importer Tuya
1. Compte gratuit sur iot.tuya.com → *Cloud › Development › Create* (« Smart Home »), lier l'appli Smart Life (code QR).
2. Copier **Access ID**, **Access Secret** et l'**ID d'un appareil** (appli : appareil › ⋯ › Informations).
3. Maison › Appareils › *Importer mes appareils Tuya* : enregistrer, « Récupérer », cocher, choisir la pièce.
Les appareils marchent d'abord via le cloud Tuya ; pour le **mode local** (plus rapide, sans Internet), ouvre l'appareil (Modifier) et
mets son adresse IP (l'onglet Réseau repère les appareils Tuya, port 6668). La clé locale a déjà été importée.

## Scènes (Maison › Scènes)
Une scène = une suite d'actions (« soirée cinéma » : plafonnier éteint, lampe à 20 %, TV allumée). Lancement : bouton, ou « lance la scène cinéma ».

## Listes (menu Listes)
« Courses » et « À faire » existent d'office, d'autres listes se créent à la voix ou à la main. Un même article n'est pas ajouté deux fois ;
on coche, on retire, on imprime. Les listes se mettent à jour toutes seules à l'écran quand EVA les modifie.

## Impression (Maison › Imprimantes)
EVA imprime en **IPP** (AirPrint / « IPP Everywhere », port 631) **depuis le NAS** : tu peux donc lui demander d'imprimer d'où que tu sois.
Ajoute l'imprimante par son adresse (`ipp://192.168.1.50:631/ipp/print`) ou avec « Chercher sur le réseau ». Formats : PDF, images (converties en JPEG),
fichiers texte (convertis en PDF), listes, texte libre. Chaque impression demande ton accord quand elle vient d'EVA (papier et encre).
Imprimante sans IPP (très ancienne, USB seule) : branche-la sur un Raspberry Pi/serveur CUPS qui la partage en IPP.

## Détection et ajout des appareils (Maison › Appareils › « Appareils trouvés sur ton réseau »)
Refonte complète : l'ancienne détection ne voyait presque rien depuis Docker (pas de MAC, pas de diffusion UDP, ni mDNS/SSDP) et pilotait mal les ampoules Tuya.

**Comment ça marche**
- Le service **`eva-scanner`** tourne en *réseau hôte* (port 8300 du NAS) et écoute vraiment le réseau : ARP, mDNS (Chromecast, AirPlay, imprimantes, Hue…), SSDP, et les diffusions
  **Tuya** (UDP 6666/6667, version du protocole et identifiant), **WiZ**, **Yeelight**, **TP-Link Kasa**. EVA complète par des empreintes HTTP (Shelly, WLED, Tasmota, pont Hue) et IPP (imprimantes).
- Tout est fusionné en **un candidat par appareil physique**, avec les *preuves* affichées (« Diffusion Tuya reçue, protocole 3.4, id … »), le pilote et le type proposés.
- Si `eva-scanner` ne répond pas, EVA fait un balayage réduit depuis son conteneur et **le dit clairement** avec la commande de réparation (`docker compose up -d --build eva-scanner`, règle `ufw allow from 172.16.0.0/12 to any port 8300 proto tcp` si le pare-feu du NAS est actif).
- **Chaque ajout est testé** avant d'être enregistré (état lu sur l'appareil) ; si le test échoue, le message dit pourquoi et propose « Ajouter quand même ». Le serveur ajoute **ce qu'il a lui-même trouvé** (clé du candidat), jamais ce que le navigateur enverrait.
- **Recherche automatique** (activée par défaut, toutes les 30 min, réglable) : nouveaux appareils signalés dans l'interface et par Telegram si configuré. Rien n'est ajouté sans ton clic. *Ignorer* masque un appareil (réafficher possible).
- **Adresse IP qui change** : EVA reconnaît l'appareil par son identité (id Tuya, MAC…) et met l'adresse à jour toute seule ; bouton de réparation par appareil (`POST /api/home/devices/{id}/repair-ip`).

**Appareils reconnus**
| Famille | Reconnaissance | Pilotage |
|---|---|---|
| Tuya / Smart Life | diffusion UDP (id, version) | local, après essai des versions 3.3 → 3.1 / 3.4 / 3.5 ; clé locale prise dans ton compte Tuya cloud (ou collée) ; **bon DP** déduit (ampoule : 20, prise : 1) ; erreurs expliquées (clé refusée, appareil injoignable, une seule connexion locale à la fois) |
| Yeelight | diffusion SSDP | local (activer « Contrôle LAN » dans l'appli Yeelight) |
| WiZ | UDP 38899 | local |
| TP-Link Kasa | UDP 9999 | local (prises et ampoules) |
| Shelly (gen 1/2), Tasmota, WLED | empreinte HTTP | local |
| Imprimantes | mDNS / IPP | ajoutées dans Imprimantes |
| Ordinateurs | ports ouverts + MAC | Wake-on-LAN |
| Philips Hue, Chromecast/AirPlay, Home Assistant | mDNS | reconnus seulement : à passer par Home Assistant |

Un appareil Tuya déjà importé du cloud est **passé en mode local** sans doublon. Les prises/relais, ordinateurs et volets sont créés avec « demander confirmation ».

## Réseau (Maison › Réseau, administrateurs)
- **Analyser le réseau** : appareils présents, noms, constructeur, ports ouverts. Adresses privées uniquement, 1024 adresses au plus.
  L'analyse *approfondie* ajoute adresses MAC, constructeurs et système via nmap dans un conteneur : `docker pull instrumentisto/nmap` une fois sur le NAS.
- **Machines accessibles (SSH)** : enregistre une machine avec **tes** identifiants (mot de passe ou clé privée, souvent `root`).
  EVA peut alors l'**inspecter** (lecture seule : système, disques, mémoire, ports, processus, connexions, services en échec, conteneurs)
  ou y **exécuter une commande**. Chaque commande demandée par EVA exige ton accord et est tracée dans Paramètres › Journal d'accès.
  L'empreinte de la machine est mémorisée à la première connexion ; si elle change, EVA refuse (usurpation possible) jusqu'à ce que tu l'oublies.
- **Pas inclus, volontairement** : deviner des mots de passe, exploiter des failles, viser autre chose que ton réseau local.

## Philips Hue, sans Home Assistant (Maison › Appareils › Philips Hue)

1. Repère l'adresse IP du pont (appli Hue › Paramètres › Ponts Hue, ou onglet Réseau).
2. Appuie sur le **bouton rond du pont**, puis clique sur « Appairer » dans les 30 secondes.
3. « Voir les lampes » → coche celles à ajouter, choisis la pièce → « Ajouter ».

Les lampes se pilotent comme les autres appareils (allumer, luminosité, couleur, blanc chaud/froid). Les scènes créées dans l'appli Hue apparaissent dans Maison › Scènes et se lancent à la voix (« lance la scène Lecture du salon »).

## Présence (Maison › Présence)

EVA regarde quels téléphones sont sur le wifi (balayage par eva-scanner toutes les 2 minutes). Ajoute chaque personne, coche son téléphone parmi les appareils vus (« Scanner maintenant » si la liste est vide). « Qui est à la maison ? » répond tout de suite. Absent = pas vu depuis 15 minutes.
Sur le téléphone, désactive l'**adresse MAC privée / aléatoire** pour le wifi de la maison (iPhone : Réglages › Wi-Fi › (i) › Adresse privée ; Android : Wi-Fi › réseau › Confidentialité › MAC de l'appareil), sinon l'adresse change.

## Satellites vocaux (Maison › Satellites, administrateurs)

Un micro + un haut-parleur dans une pièce (Raspberry Pi 3/4/5 avec micro USB, vieux PC, portable Windows) : « EVA, allume la lumière » sans ouvrir l'application.

1. « Ajouter un satellite » : nom, pièce (« la lumière » = celle de cette pièce), compte dont les droits s'appliquent. Le jeton n'est montré qu'une fois.
2. Copie la commande affichée sur la machine du satellite (Linux/Raspberry : installe un service qui démarre tout seul ; Windows : démarre à l'ouverture de session).
3. Parle : « EVA, quelle heure est-il ? ». « EVA » seul : un bip, puis 8 secondes pour parler. Une action sensible est demandée à voix haute : réponds « oui » ou « non ».

Mode d'emploi détaillé : `https://ADRESSE-DU-NAS:8443/api/public/satellite/LISEZMOI.txt`. Supprimer le satellite coupe son accès immédiatement.

Comme Jarvis :
- **Réponse plus rapide** : le satellite parle dès la première phrase prête (la suite est préparée pendant qu'il parle) ; si une recherche traîne, EVA dit tout de suite « Je regarde la météo. » ; une simple conversation se passe des outils (réponse en ~1 s de moins).
- **Un seul satellite répond** quand plusieurs entendent la même phrase : celui qui t'entend le mieux.
- **Rien de secret à voix haute** : clés, mots de passe, numéros de carte et IBAN sont masqués à l'oral ; dans une annonce, aussi les adresses mail et les numéros de téléphone.
- **Sur un PC** (options d'installation `fenetre`, `tableau`, `ecran`, `gestes`) : tableau au repos dans la fenêtre flottante (heure, météo, agenda, colis, musique, post-its) ; EVA regarde l'écran (« qu'est-ce qu'il y a sur mon écran ? ») et clique sur un bouton visible avec ton accord (« clique sur Envoyer ») ; gestes devant la webcam (pause, volume, onglets, souris, zoom, pouce levé = oui). Mettre à jour un satellite = relancer sa commande d'installation.

## Google Home, Nest et Chromecast en direct (comme Jarvis)

Les enceintes et TV Google trouvées par la détection réseau (Maison › Appareils › « Appareils trouvés ») s'ajoutent d'un clic
(pilote « Google Home / Chromecast ») : « monte le son de l'enceinte de la cuisine à 40 », « mets en pause la TV », « arrête
la musique du salon », « qu'est-ce qui joue dans la cuisine ? ». Les annonces (« annonce dans la cuisine que… ») sont aussi
dites par les enceintes Google de la pièce, avec la voix d'EVA (eva-scanner doit être à jour). Les thermostats Nest restent
pilotés via Home Assistant (intégration Nest).

## Lumières vidéo Godox (comme Jarvis)

Les lumières Godox (TL60, SL, ML, LED…) se pilotent en Bluetooth Mesh chiffré, sans API officielle. Le chemin fiable passe par
Home Assistant : installe l'intégration communautaire **Godox BLE Mesh** (HACS, dépôt `SegulaLabs/ha-godox-ble-mesh`) sur une
machine proche des lumières (Bluetooth), importe les clés depuis l'appli Godox comme expliqué dans son guide, puis dans EVA :
Maison › Appareils › Importer depuis Home Assistant. Ensuite : « allume la lumière vidéo », « lumière vidéo à 40 % »,
« lumière vidéo en 5600 K » (ou 3200 K), et dans tes scènes (« mode tournage »).

## Droits
Les **utilisateurs** « user » commandent les appareils, scènes, listes et imprimantes ; ajouter/modifier/supprimer un appareil, une scène, une imprimante,
et tout le menu Réseau sont réservés aux **administrateurs**.

## Limites connues
- Non testé sur de vrais appareils (tests avec de faux appareils et un vrai serveur SSH de test) : Tuya, Shelly, Tasmota, WLED, MQTT, imprimante réelle.
- Wake-on-LAN : EVA tourne dans un conteneur ; la diffusion peut ne pas atteindre le réseau local. Renseigne l'adresse de diffusion (ex. `192.168.1.255`) ; sinon réveil via Home Assistant.
- La détection réelle (réseau hôte, UDP, mDNS) n'a pu être testée qu'avec des relevés simulés et de faux appareils : à valider chez toi. Les appareils Tuya éteints n'émettent rien : rallume-les puis relance la recherche. Hue est reconnu mais se pilote via Home Assistant.


## Home Assistant

Maison › Appareils › *Importer depuis Home Assistant* : saisis l'adresse (ex. `http://192.168.1.20:8123`) et un jeton d'accès longue durée (Home Assistant › ton profil › Sécurité). EVA liste les entités commandables avec leur zone (= pièce) ; tu coches, renommes, ajoutes. Les commandes passent par les services de Home Assistant (`light.turn_on`, `cover.open_cover`, `climate.set_temperature`, `scene.turn_on`…). Volets : seuls les types volet/store/rideau sont commandables ; portails, garages, portes, serrures et alarmes ne sont jamais proposés ni commandés.
