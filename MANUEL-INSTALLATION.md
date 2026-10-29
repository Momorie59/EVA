# EVA — Manuel d'installation

Ce manuel installe EVA de zéro, la met à jour et la dépanne. Pour se servir d'EVA au quotidien : `MANUEL-UTILISATION.md`.

---

## 1. Vue d'ensemble

EVA tourne sur **deux machines** de ton réseau local (une seule si elle a la carte graphique), plus des **satellites** facultatifs. Les adresses ci-dessous sont des exemples : remplace-les par les tiennes.

| Machine | Rôle | Exemple |
|---|---|---|
| **NAS ou mini-PC Linux** (avec Docker) | EVA elle-même : interface web, cœur, base de données, voix, détection réseau | mini-PC 4 cœurs / 8 Go, `192.168.1.10` |
| **Serveur IA** (carte graphique NVIDIA) | Les modèles de langage (Ollama) et, en option, le serveur d'images | PC avec GTX 1060 (6 Go) ou mieux, `192.168.1.20` |
| **Satellites** (facultatif) | Un micro et un haut-parleur par pièce, ou un PC piloté par EVA | Raspberry Pi, vieux PC, ton PC, un téléphone Android |

Sur le NAS, EVA est faite de plusieurs conteneurs Docker :

| Conteneur | Rôle |
|---|---|
| `eva-core` | le cœur : conversations, outils, mémoire, maison… |
| `eva-interface` | l'interface web |
| `eva-db` | la base de données (conversations, réglages, comptes) |
| `eva-voice` | la voix : Whisper (comprendre) et Piper (parler) |
| `eva-scanner` | la détection des appareils et des téléphones sur le réseau |
| `eva-caddy` | la porte d'entrée HTTPS, port **8443** |
| `eva-airllm` | facultatif : très gros modèles, très lents (`docker compose --profile airllm up -d --build`) |

EVA n'ouvre que le port **8443** : les ports 80 et 443 restent libres pour l'interface du NAS (OpenMediaVault, Synology…) ou un autre site.

---

## 2. Préparer le serveur IA

### 2.1 Installer la pile IA

Installe les pilotes NVIDIA de ta distribution, puis Ollama :

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Sur Debian / Ubuntu / Pop!_OS, le script [`ia-local-automatique`](https://github.com/Momorie59/ia-local-automatique) installe tout d'un coup (pilotes, Ollama, Open WebUI, Qdrant) et ajoute un tableau de bord sur `http://<IP-serveur-IA>:7842`, qu'EVA sait afficher.

### 2.2 Vérifier qu'Ollama écoute sur le réseau

```bash
ss -tlnp | grep 11434
```

Tu dois voir `0.0.0.0:11434`. Si tu vois `127.0.0.1:11434`, ajoute `Environment="OLLAMA_HOST=0.0.0.0"` dans `/etc/systemd/system/ollama.service.d/override.conf`, puis :

```bash
sudo systemctl daemon-reload && sudo systemctl restart ollama
```

### 2.3 Télécharger les modèles

Tu peux aussi le faire plus tard depuis EVA (Paramètres › Intelligence › Modèles installés).

```bash
ollama pull qwen2.5:7b          # modèle principal (outils)
ollama pull llama3.2:3b         # modèle rapide (petites phrases, voix)
ollama pull llava               # vision (photos)
ollama pull nomic-embed-text    # recherche dans les documents
```

### 2.4 Serveur d'images (facultatif)

Il sert à dessiner et à retoucher des images. Installe-le sur le serveur IA :

```bash
cd ~
git clone --depth 1 --filter=blob:none --sparse https://github.com/Momorie59/EVA.git eva-src
cd eva-src && git sparse-checkout set eva-imagegen
cd eva-imagegen
sudo bash install-imagegen.sh
```

Le script affiche un **jeton : note-le**. Il se colle plus tard dans EVA (voir §4).

---

## 3. Installer EVA sur le NAS

### 3.1 Récupérer EVA

Choisis un dossier pour EVA (ici `/home/eva`, à adapter), puis, avec git (le plus simple) :

```bash
apt install -y git
cd /home/eva
git clone https://github.com/Momorie59/EVA.git eva
cd eva
```

Sans git : télécharge l'archive du dépôt depuis GitHub (Code › Download ZIP), dépose-la dans `/home/eva`, puis :

```bash
cd /home/eva && python3 -c "import zipfile;zipfile.ZipFile('EVA-main.zip').extractall('.')" && mv EVA-main eva && cd eva
```

### 3.2 Régler `.env`

```bash
cp .env.example .env
nano .env
```

Les lignes à adapter :

```ini
OLLAMA_HOST=http://192.168.1.20:11434     # IP du serveur IA
OLLAMA_MODEL=qwen2.5:7b
EVA_MODELE_RAPIDE=llama3.2:3b
EVA_VISION_MODEL=llava
POSTGRES_PASSWORD=un-vrai-mot-de-passe
EVA_HOST=192.168.1.10                    # IP du NAS, telle que tu la tapes dans le navigateur
EVA_HTTPS_PORT=8443
EVA_DEFAULT_CITY=Paris                    # ville de la météo
EVA_PROPRIETAIRE=Amélie                   # facultatif : « l'assistante d'Amélie » (vide = « de la famille »)
EVA_TIMEZONE=Europe/Paris
```

Génère les deux jetons et colle-les dans `.env` :

```bash
echo "EVA_AUTH_TOKEN=$(openssl rand -hex 32)"
echo "EVA_SCANNER_TOKEN=$(openssl rand -hex 24)"
```

`.env` n'est **jamais** sur GitHub ni dans une mise à jour. Garde-en une copie à part.

### 3.3 Voix d'EVA (Piper)

Rien à faire : la voix française se télécharge toute seule au premier démarrage d'`eva-voice`, et celles des autres langues la première fois qu'elles servent. Sans accès à internet, dépose-la à la main :

```bash
pip install piper-tts --break-system-packages
python3 -m piper.download_voices --download-dir ./eva-voice/models fr_FR-siwis-medium
```

### 3.4 Lancer

```bash
cd /home/eva/eva
docker compose up -d --build
```

Le premier démarrage est long : les images se construisent, puis le modèle Whisper se télécharge au premier message vocal.

**Si la construction reste bloquée sur un téléchargement** (`apt-get` ou `pip` qui n'avance plus alors que le NAS ne travaille pas) : Ctrl+C, puis construis eva-core avec le réseau du NAS, et relance :

```bash
cd /home/eva/eva && P=$(docker compose config --format json | python3 -c "import sys,json;print(json.load(sys.stdin)['name'])") && docker build --network=host -t "$P-eva-core" ./eva-core && docker compose up -d --build
```

### 3.5 Vérifier

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
curl -k https://localhost:8443/api/health
```

Tous les conteneurs doivent être `Up`, et la seconde commande doit répondre `{"status":"ok", …}`.

---

## 4. Premier lancement

1. Ouvre **`https://192.168.1.10:8443`**. Le navigateur prévient d'un certificat inconnu : c'est normal, EVA fabrique le sien. Choisis « Avancé › Continuer », ou installe le certificat une fois pour toutes (§6.2).
2. **Crée ton compte administrateur** : Paramètres › Sécurité & données › Connexion. À faire tout de suite, avant de donner l'adresse à quelqu'un.
3. **Serveur IA** : Paramètres › Intelligence. Les modèles d'Ollama doivent apparaître. Sinon, vérifie `OLLAMA_HOST` (§2.2).
4. **Serveur d'images** (si installé) : Paramètres › Images › Détecter le serveur. Colle le jeton du §2.4, enregistre, puis télécharge le modèle conseillé.
5. **Sauvegarde ancienne** (réinstallation) : Paramètres › Sécurité & données › Sauvegarde › Restaurer.
6. **Comptes de la famille** : Paramètres › Sécurité & données › Utilisateurs. Choisis un profil par personne : adulte, adolescent, enfant ou invité.

---

## 5. Mettre EVA à jour

Ce qui change à chaque version : `CHANGELOG.md`.

**Ce qui n'est jamais touché :** tes conversations, réglages, comptes, fichiers, papiers et images (volumes Docker), et ton `.env`.

⚠️ **Ne lance jamais `docker compose down -v`** : le `-v` efface tous les volumes, donc toutes tes données.

**Avec git** (installation faite avec `git clone`) :

```bash
cd /home/eva/eva && git pull && docker compose up -d --build
```

**Avec une archive** `eva-maj-N.zip` (seulement les fichiers modifiés) : dépose-la dans `/home/eva`, puis lance ces deux commandes une par une.

**1. Extraire :**

```bash
cd /home/eva/eva && python3 -c "import zipfile;zipfile.ZipFile('/home/eva/eva-maj-N.zip').extractall('.')"
```

**2. Reconstruire et relancer :**

```bash
cd /home/eva/eva && P=$(docker compose config --format json | python3 -c "import sys,json;print(json.load(sys.stdin)['name'])") && docker build --network=host -t "$P-eva-core" ./eva-core && docker compose build eva-interface && docker compose up -d eva-core eva-interface
```

**3. Attends une à deux minutes**, puis recharge la page avec **Ctrl+F5**. Au démarrage, EVA vérifie son propre code : pendant ce temps, la page affiche « Erreur 502 », c'est normal.

Selon les fichiers que contient l'archive, reconstruis aussi :

| L'archive contient | Commande en plus |
|---|---|
| `eva-voice/…` | `docker compose up -d --build eva-voice` |
| `eva-scanner/…` | `docker compose up -d --build eva-scanner` |
| `eva-airllm/…` | `docker build --network=host -t "$P-eva-airllm" ./eva-airllm && docker compose up -d eva-airllm` |

**Ce qu'EVA a modifié elle-même** (page Évolution, ou « Évoluer toute seule ») est rejoué automatiquement sur la nouvelle version au redémarrage ; une modification qui ne s'applique plus proprement est laissée de côté et signalée dans Évolution.

**Ménage** une fois la mise à jour installée et vérifiée :

```bash
rm -f /home/eva/eva-maj-*.zip && docker image prune -f && docker builder prune -f
```

---

## 6. Accès depuis tes appareils

### 6.1 Installer EVA comme une application (téléphone, PC)

Paramètres › Apparence & application › Installer. Il faut une connexion HTTPS que l'appareil accepte vraiment (§6.2).

### 6.2 Plus d'avertissement de certificat

- **Sans nom de domaine** : ouvre `https://192.168.1.10:8443/api/https/install` sur chaque appareil. La page propose un installateur Windows en un clic, et les étapes pour Android, iPhone et Mac.
- **Avec un vrai certificat** (DuckDNS, gratuit, sans ouvrir de port) : voir `HTTPS-SANS-AVERTISSEMENT.md`.

### 6.3 Depuis l'extérieur, ou pour des amis

Le plus sûr est un VPN privé (Tailscale ou WireGuard). Ne redirige jamais les ports 80 ou 443 de ta box. Voir `ACCES-A-DISTANCE.md`.

### 6.4 HTTP sans chiffrement (réseau de confiance seulement)

```bash
cd /home/eva/eva && sh eva-https.sh off      # retour : sh eva-https.sh on
```

Sans HTTPS, le micro, la caméra et l'installation en application ne marchent pas.

---

## 7. Satellites (micro et haut-parleur par pièce, PC piloté)

**Le plus simple : depuis EVA.** Maison › Satellites › **Ajouter un satellite** (nom, pièce, compte), ou **Installer / Réinstaller** sur un satellite existant. Choisis :

1. le système : 🪟 Windows, 🍎 Mac, 🐧 Linux / Raspberry Pi ou 🤖 Android (celui de l'appareil sur lequel tu es est proposé d'office) ;
2. à quoi il sert : **ton ordinateur** (micro, écran, prise en main) ou **une enceinte dans une pièce** ;
3. les options (tableau ci-dessous).

Puis :

- **Windows** : un fichier `Installer-EVA-<nom>.cmd` se télécharge. Copie-le sur l'ordinateur à équiper et **double-clique** dessus. Si Windows affiche « Windows a protégé votre ordinateur » : *Informations complémentaires* › *Exécuter quand même*. Windows demande ensuite l'**autorisation administrateur** : réponds *Oui*. Le satellite est alors lancé à chaque ouverture de session **avec les droits administrateur** (tâche planifiée « EVA Satellite »), ce qui lui permet aussi d'agir sur les fenêtres ouvertes en administrateur. Python 3.12 est installé tout seul s'il manque (winget). Sur Linux, l'installateur demande le mot de passe administrateur (sudo) pour les paquets et le service.
- **Mac** : ouvre le *Terminal* (Cmd + Espace, « Terminal »), colle la commande affichée (bouton *Copier*) et appuie sur Entrée. Accepte ensuite l'accès au micro ; pour l'option écran, autorise Python dans *Réglages Système › Confidentialité et sécurité* : *Enregistrement de l'écran*, *Accessibilité* (et *Caméra* pour les gestes). Il démarre à chaque ouverture de session.
- **Linux / Raspberry Pi** (Debian, Ubuntu, Raspberry Pi OS, Fedora, Arch, openSUSE) : colle la commande affichée dans un terminal. Pour l'option écran, ouvre une session « Xorg / X11 » (pas Wayland).
- **Android** (8 ou plus récent) : sur le téléphone, télécharge l'appli **EVA Satellite** (bouton de l'assistant ; autorise « installer des applis inconnues » si Android le demande), puis touche **« Ouvrir dans l'appli »** — ou scanne le QR code affiché sur le PC avec l'appareil photo du téléphone. Autorise le micro et les notifications. L'appli écoute « EVA… » (mains libres, ou seulement quand le téléphone est en charge), a un gros bouton **Parler**, répond avec la voix d'EVA, dit les annonces, et sonne fort quand tu demandes « où est mon téléphone ? ». Elle propose elle-même ses mises à jour. Après un redémarrage du téléphone, ouvre l'appli une fois (Android interdit de rallumer le micro tout seul).

**Durées d'installation** (affichées aussi dans l'assistant, selon les options) :

| Système | Durée | Options |
|---|---|---|
| Windows | 5 à 10 min (+3 min si Python s'installe) | écran +2 à 5 min, gestes +5 à 10 min, éveil local +1 à 3 min |
| Mac | 5 à 10 min (+5 à 15 min la 1re fois pour les outils d'Apple) | idem |
| Linux (PC) | 3 à 8 min | idem |
| Raspberry Pi 3 / 4 | 10 à 20 min | gestes déconseillés |
| Android | 1 à 2 min | — |

**Piloter le satellite** :
- **sur l'ordinateur** : l'**icône EVA à côté de l'horloge** (Windows, Linux ; clic droit) : *Parler maintenant* (sans dire « EVA »), *Mettre en pause* / *Reprendre l'écoute*, *Ouvrir EVA*, *Redémarrer*, *Arrêter*. Raccourcis sur le bureau : **EVA démarrer**, **EVA arrêter**, **EVA pause**, **EVA reprise** (Mac : fichiers `.command` sur le bureau ; Linux : aussi `~/eva-satellite/demarrer.sh`, `arreter.sh`, `pause.sh`, `reprise.sh`) ;
- **depuis EVA** (Maison › Satellites, satellite allumé) : ⏸ Pause / ▶ Activer l'écoute, 🎙 Parler, ↻ Redémarrer, ⏹ Arrêter (il repart à la prochaine ouverture de session ou avec « EVA démarrer »), 🩺 Diagnostic.

**🩺 Diagnostic** (Maison › Satellites) : dit si le satellite est connecté, montre ce que son micro entend (niveau / seuil), combien de phrases il a entendues et comprises, la dernière phrase comprise, la dernière erreur et son journal. **« Tester le haut-parleur et le micro »** : il dit une phrase, bipe, écoute 4 secondes et affiche ce qu'il a compris. Le journal est aussi dans `satellite.log` du dossier `eva-satellite`.

« EVA » ne réagit pas ? Lance le diagnostic : *aucune phrase entendue* → micro coupé / mauvais micro par défaut / trop loin ; *phrases entendues mais jamais « EVA »* → regarde ce qu'il a compris (« Entendu sans EVA » dans le journal) et commence bien ta phrase par « EVA » ; *pas connecté* → raccourci « EVA démarrer » et journal.

**Mettre en pause / réactiver l'écoute** :
- depuis EVA : Maison › Satellites › **⏸ Pause** / **▶ Activer l'écoute** (gardé même si le satellite redémarre) ;
- sur l'ordinateur : raccourcis **« EVA pause »** et **« EVA reprise »** sur le bureau (Linux : aussi `bash ~/eva-satellite/pause.sh` / `reprise.sh`) ;
- à la voix : « EVA, pause » (pour reprendre : un raccourci ou EVA) ;
- Android : interrupteur « Écoute » dans l'appli (le bouton Parler marche toujours).

En pause, le satellite n'écoute plus rien et n'envoie rien ; il dit toujours les annonces.

**Désinstaller** : Maison › Satellites › **Supprimer**. S'il est allumé, le satellite **se désinstalle tout seul** (démarrage automatique, programme et dossier). S'il est éteint, EVA affiche la commande à lancer sur la machine :

| Système | Commande |
|---|---|
| Windows | double-clic sur `desinstaller.cmd` dans le dossier `eva-satellite` (ton dossier utilisateur) |
| Mac | `curl -fsSk https://192.168.1.10:8443/api/public/satellite/desinstaller-mac.sh \| bash` |
| Linux / Raspberry Pi | `curl -fsSk https://192.168.1.10:8443/api/public/satellite/desinstaller-linux.sh \| bash` |
| Android | appui long sur l'icône EVA Satellite › Désinstaller |

Sur un Raspberry Pi installé en service système avec un mot de passe administrateur, la désinstallation à distance arrête le satellite mais te demande de lancer la commande ci-dessus pour retirer le service.

Chaque préparation crée une **nouvelle clé** pour ce satellite : l'ancienne installation cesse de marcher jusqu'à ce que tu relances l'installateur. La commande contient cette clé : ne la partage pas.

**Mises à jour : automatiques.** Depuis la version 1.3, le satellite vérifie au démarrage puis toutes les 6 heures si EVA a une version plus récente, la télécharge, vérifie qu'elle est intacte (l'ancienne est gardée en `satellite.ancien.py`), installe les modules qui manquent et redémarre. La liste des satellites indique « v1.3 à jour » ou « version ancienne : réinstalle-le une fois ». Pour l'empêcher : `"mise_a_jour_auto": false` dans `satellite.json`.

**Relance automatique (Windows, installation administrateur).** La tâche planifiée « EVA Satellite » vérifie toutes les 5 minutes que le satellite tourne et le relance s'il s'est arrêté (plantage, mise à jour). Le raccourci **EVA arrêter** (ou ⏹ Arrêter depuis EVA) le laisse éteint jusqu'à **EVA démarrer** ou au prochain démarrage du PC.

À la main, si tu préfères (mêmes options) :

```bash
# Linux / Raspberry Pi
curl -fsSk https://192.168.1.10:8443/api/public/satellite/installer-linux.sh -o installer.sh
bash installer.sh https://192.168.1.10:8443 evasat_… [local] [fenetre] [tableau] [ecran] [gestes]
# Mac
curl -fsSk https://192.168.1.10:8443/api/public/satellite/installer-mac.sh -o installer.sh
bash installer.sh https://192.168.1.10:8443 evasat_… [fenetre] [tableau] [ecran] [gestes]
```

Les options, toutes facultatives :

| Option | Ce qu'elle ajoute |
|---|---|
| `local` | Le mot d'éveil « EVA » est détecté sur le satellite lui-même : rien ne part vers le NAS avant |
| `fenetre` | Une petite fenêtre toujours visible sur le PC, avec ce que tu dis et ce qu'EVA répond |
| `tableau` | Au repos, la fenêtre affiche l'heure, la météo, l'agenda, les colis, la musique et les post-its |
| `ecran` | EVA peut lire l'écran du PC et cliquer sur un bouton visible, toujours avec ton accord |
| `gestes` | Pilotage à la main devant la webcam. Il faut Python 3.12 ou plus ancien pour MediaPipe |

Guide complet : `https://192.168.1.10:8443/api/public/satellite/LISEZMOI.txt`.

---

## 8. Dépannage

| Problème | Que faire |
|---|---|
| Page « Erreur 502 » | EVA redémarre : attends 1 à 2 minutes, puis Ctrl+F5. Si ça dure : `docker logs eva-core --tail 40` |
| Les conversations ont disparu | Recharge avec Ctrl+F5. Elles sont dans la base : `docker exec eva-db psql -U eva -d eva -c "SELECT count(*) FROM sessions;"` |
| « Serveur IA injoignable » | Le serveur IA est-il allumé ? Teste : `docker exec eva-core python -c "import urllib.request;print(urllib.request.urlopen('http://192.168.1.20:11434/api/tags',timeout=5).read()[:200])"` |
| « connexion temps réel (WebSocket) refusée » (réseau du bureau, hôtel) | Le proxy du réseau bloque les WebSocket : EVA passe toute seule en **mode compatible** (HTTP) au bout de quelques secondes ; le menu affiche « En ligne (mode compatible) ». Si le message reste : reconnecte-toi (session expirée). Le Salon (appels) a besoin des WebSocket et ne marche pas sur ces réseaux |
| Une réponse tourne en boucle | Bouton rouge **■ Arrêter**. En dernier recours : `docker restart eva-core` |
| Mot de passe perdu | `docker exec eva-db psql -U eva -d eva -c "DELETE FROM auth_users; DELETE FROM auth_sessions;" && docker restart eva-core`, puis recrée le compte |
| Construction bloquée | Voir §3.4 (`--network=host`) |
| Diagnostic complet | `cd /home/eva/eva && bash diagnostic.sh` |

**Sauvegarde :** EVA en fait une chaque jour et en garde 7. Pour en faire une à la main : Paramètres › Sécurité & données › Sauvegarde. Pense aussi à copier `.env` en lieu sûr.

---

## 9. Pour aller plus loin

| Sujet | Fichier |
|---|---|
| Maison, appareils, présence, satellites | `MAISON.md` |
| Papiers et échéances (Paperless) | `PAPIERS.md` |
| Images | `IMAGES.md` |
| Accès à distance | `ACCES-A-DISTANCE.md` |
| Certificat sans avertissement | `HTTPS-SANS-AVERTISSEMENT.md` |
| Sécurité, NIS2 | `NIS2.md` |
| Historique des versions | `CHANGELOG.md` |
