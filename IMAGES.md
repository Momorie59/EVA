# Génération d'images dans EVA

« EVA, crée une image d'un renard dans la neige » — EVA envoie la demande à un serveur d'images **local** (Stable Diffusion) et affiche le résultat dans la conversation.
Rien ne part sur Internet : seul le téléchargement du modèle, une fois, passe par Hugging Face.

## Les pièces
| Pièce | Où | Rôle |
|---|---|---|
| **eva-imagegen** (dossier `eva-imagegen/`) | **serveur IA** (GTX 1060 6 Go), conteneur Docker | fabrique les images (diffusers). API « Stable Diffusion WebUI » (`/sdapi/v1/…`) **et** API OpenAI (`/v1/images/generations`) |
| EVA (eva-core) | NAS | traduit/enrichit ta description (français → anglais), appelle le serveur, range l'image dans la galerie et le dossier `generated/` |
| Paramètres › Génération d'images / Modèles d'images | interface (administrateur) | détection du serveur, réglages, essai ; liste des modèles conseillés selon ta carte, téléchargement, suppression, mise à jour du serveur |
| Onglet **Images** | interface (tout le monde) | créer, modifier, galerie, garder, purge automatique |

## Installer sur le serveur IA (adapté à ia-local-automatique)
Ton installateur met Ollama en **natif** (service systemd, parfois limité à `127.0.0.1`), Docker pour Open WebUI **en réseau hôte**, et range les données sur ton disque dédié.
`eva-imagegen` suit exactement cette logique : conteneur Docker **en réseau hôte** (il joint Ollama en `127.0.0.1:11434` même s'il n'écoute qu'en local), service systemd `eva-imagegen.service`
(ordre : Docker → Ollama → eva-imagegen, comme `open-webui.service`), règle `ufw` limitée à ton réseau local (pas ouverte à tout Internet), modèles rangés **à côté des données d'Open WebUI** (lues dans
`/var/lib/ia-installer/config.env`). Il n'efface et ne modifie rien d'existant.

Copie le dossier `eva-imagegen/` sur le serveur IA, puis :
```bash
cd eva-imagegen
sudo bash install-imagegen.sh --dry-run     # montre ce qui sera fait, sans rien toucher
sudo bash install-imagegen.sh               # installe (1re fois : 10-20 min pour construire l'image, ≈ 6 Go)
sudo bash install-imagegen.sh --status      # état
sudo bash install-imagegen.sh --uninstall   # retire conteneur, service, règle ufw (les modèles restent)
```
Options : `--model ID`, `--port N` (≥ 1024 ; 7860 par défaut, libre chez toi : dashboard 7842, Open WebUI 8080, Qdrant 6333), `--data-dir CHEMIN`, `--yes`.
Le script vérifie : Docker actif, carte NVIDIA et **pilote ≥ 525** (CUDA 12.1), **NVIDIA Container Toolkit** (proposé en installation, dépôt officiel NVIDIA — le même que ton installateur ; sinon il te renvoie vers lui), place disque (≥ 8 Go), Ollama joignable.
La variante `docker compose up -d --build` (dans le dossier) reste possible si le plugin compose est installé.

Puis dans EVA : **Paramètres › Génération d'images › Détecter le serveur** (cherche `http://<serveur IA>:7860`), ou saisis l'adresse à la main, puis *Tester*.
Alternative : `EVA_IMAGEGEN_URL=http://192.168.1.20:7860` dans `.env`.

**Bonus Open WebUI** : il sait aussi dessiner avec ce serveur — Admin › Paramètres › Images › moteur *AUTOMATIC1111* → `http://127.0.0.1:7860` (réglage dans l'interface, aucun redémarrage ni changement de ton installation).

## Pensé pour 6 Go de mémoire vidéo
- **Modèle par défaut : `stabilityai/sd-turbo`** — 4 étapes, 512 px, quelques secondes par image sur une GTX 1060. Les modèles « Turbo » n'ont pas besoin de guidage.
- **La carte est partagée avec Ollama** : avant de charger le modèle d'images, le serveur demande à Ollama de décharger les siens ; après `IMAGEGEN_IDLE_UNLOAD` secondes d'inactivité (90 par défaut) il libère la carte. Conséquence : la première question à EVA juste après une image recharge son modèle de langage (quelques secondes).
- Une image à la fois (file d'attente) ; demi-précision, attention et VAE découpés ; image noire en demi-précision → nouvel essai automatique en pleine précision.
- Taille bornée par `IMAGEGEN_MAX_PIXELS` (1 Mpx) ; mémoire saturée → message clair, le modèle est rechargé à la demande suivante.

## Changer de modèle
| Besoin | `IMAGEGEN_MODEL` | Notes (6 Go) |
|---|---|---|
| Rapide (défaut) | `stabilityai/sd-turbo` | 512 px, 1–4 étapes |
| Plus de détails | `stabilityai/sdxl-turbo` | déchargé vers le processeur par blocs : plus lent, 512 px |
| Qualité classique | `stable-diffusion-v1-5/stable-diffusion-v1-5` | 20 étapes, ≈ 10 s |
| Photoréaliste (essayer) | `SG161222/Realistic_Vision_V5.1_noVAE` ou `Lykon/dreamshaper-8` | SD 1.5 : 20 étapes, ≈ 15–25 s, garde 512 px ; ajoute « à éviter » (cartoon, flou…) |
| Photoréaliste / anime / autre | un fichier `.safetensors` ou `.ckpt` déposé dans `eva-imagegen/models/` | il apparaît dans la liste *Modèle* des Paramètres |

Modifie `IMAGEGEN_MODEL` dans `eva-imagegen/.env` puis `docker compose up -d`, ou, sur le serveur IA (script d'installation) : `sudo bash install-imagegen.sh --model AUTEUR/MODELE`. Dans Paramètres › Génération d'images, le champ *Modèle* propose la liste du serveur **et** accepte un nom « auteur/modèle » du hub (téléchargé au premier dessin).
Certains modèles du hub demandent un compte Hugging Face : mets `HF_TOKEN=` dans `.env`.

## Utilisation
L'image apparaît **dans la conversation**, sous la réponse d'EVA (clic pour agrandir, « Enregistrer » pour la télécharger) ; elle est aussi rangée dans la galerie (onglet **Images**).
EVA transmet **toutes** tes demandes d'images au serveur (formulations libres : « dessine-moi… », « je voudrais une photo de… », « fais-moi un logo pour… »). Quand le petit modèle de langage refuse de reformuler le sujet (réponse « je ne peux pas… »), il est ignoré et ta demande part telle quelle : EVA ne s'oppose pas elle-même à une demande. Les limites éventuelles viennent du modèle d'images choisi.
- **À la voix ou au texte** : « crée une image de… », « dessine… », « génère une illustration de… » (sans passer par le modèle de langage pour l'envoi).
- **Par l'agent** : l'outil `image_generate` (agents, Telegram, projets) enregistre l'image dans `generated/` et renvoie son chemin.
- **Onglet Images** : créer, retoucher, galerie (miniatures, agrandir, enregistrer, garder, supprimer) — voir plus bas.
- *Traduire et enrichir* (coché par défaut) : le petit modèle de langage local réécrit ta demande en une description anglaise détaillée. Il est sauté si seul AirLLM est disponible (trop lent) ou en cas d'erreur : ta demande part alors telle quelle.
- **Étapes 0 / Taille automatique** : le serveur choisit les bons réglages pour le modèle (Turbo : 4 étapes, sinon 20).

## Sécurité
Réglages, détection, modèles, mise à jour du serveur et purge réservés à l'administrateur. `IMAGEGEN_TOKEN` (facultatif) protège la génération du serveur ; le même jeton se saisit dans EVA. Les noms de modèles ne peuvent pas sortir du dossier `models/`. Aucun filtre de contenu n'est installé (usage personnel, local).

## Modifier une image
Joins une photo au message (trombone ou appareil photo), ou parle de l'image qui vient d'être créée (« mets-la en noir et blanc »), ou utilise l'onglet **Images** (« Envoyer une photo… » ou « Modifier » dans la visionneuse). Le résultat est une **nouvelle** image ; l'original n'est jamais modifié.
- **Retouches classiques** (instantanées, sans serveur) : noir et blanc, sépia, négatif, luminosité, contraste, saturation, netteté, flou, recadrer (carré, 16:9, 4:3…), rotation (90°, 180°, angle), miroir, redimensionner, ajouter un texte. Exemples : « mets cette photo en noir et blanc et recadre en carré ».
- **Modification par l'IA** (serveur d'images) :
  - style / ambiance de toute l'image : « transforme cette photo en aquarelle », « rends-la plus réaliste » (image→image) ;
  - **retirer ou changer un détail** : « enlève le poteau », « remplace le ciel par un coucher de soleil », « mets la voiture en rouge » — le serveur retrouve la zone à partir du mot (modèle CLIPSeg, ≈ 600 Mo téléchargés au premier usage) puis ne refait que cette zone (inpainting).
- Pour ne pas confondre avec la maison (« mets la lumière du salon en bleu »), une demande de modification n'est comprise que s'il y a une image en jeu : photo jointe, mot « photo/image… », ou « mets-la… » juste après une image.
- Taille de travail limitée à 768 px côté long pour tenir sur 6 Go.
- Par l'agent : outil `image_edit` (nom d'une image de la galerie ou chemin d'une photo, plus la demande en français). Via l'API : `POST /api/images/edit`.

## Onglet Images et purge automatique
Créer, envoyer une photo à retoucher, parcourir la galerie (filtres Toutes / Créées / Modifiées / Gardées), ouvrir une image : *Enregistrer*, *Modifier*, *Garder (jamais purgée)*, *Supprimer*.
**Purge automatique** (administrateur, en bas de l'onglet) : les images non gardées sont supprimées après N jours (30 par défaut) et au-delà de M images (200 par défaut, les plus anciennes d'abord) ; 0 = pas de limite ; « Purger maintenant ». Passage toutes les 6 h. Une image purgée affichée dans une vieille conversation devient « Image supprimée ».

## Choisir et installer les modèles depuis EVA (Paramètres › Modèles d'images)
Liste conseillée (SD Turbo, DreamShaper 8, Dreamlike Photoreal, SD 1.5, SDXL Turbo, SDXL 1.0) avec taille, vitesse, qualité et **verdict selon ta carte** (la mémoire réelle de la carte du serveur d'images est utilisée) : *Convient / Possible mais lent / Trop gros*, et un ⭐ pour le meilleur choix. *Télécharger* (barre de progression, depuis Hugging Face, sur le serveur IA — rien à taper sur le serveur), *Utiliser*, *Supprimer* (libère le disque). Champ libre « auteur/modèle » pour un autre dépôt au format diffusers. Un modèle qui demande un compte Hugging Face : `HF_TOKEN` sur le serveur IA.
Ces actions sont réservées à l'administrateur.

## Mettre à jour le serveur d'images (une fois à la main, ensuite depuis EVA)
Les nouvelles fonctions (modifier, modèles) demandent un serveur d'images en **version 2**. Si EVA répond « ton serveur d'images ne sait pas encore… » :
1. **Une seule fois, à la main** (le serveur actuel ne sait pas encore se mettre à jour) : copie le dossier `eva-imagegen/` de l'archive sur le serveur IA (remplace l'ancien) puis `cd eva-imagegen && sudo bash install-imagegen.sh`. Les modèles déjà téléchargés sont conservés (ils sont sur le disque de données) ; le script crée un **jeton** et l'affiche à la fin.
2. Dans EVA : **Paramètres › Génération d'images › Jeton** : colle ce jeton, *Enregistrer* (relire plus tard : `sudo cat <dossier-des-modèles>/.token`).
3. **Ensuite**, pour les mises à jour suivantes : **Paramètres › Modèles d'images › Mettre à jour le serveur d'images**. EVA envoie le nouveau code (fichiers `engine.py`, `main.py`, `models.py`, `__init__.py`, contrôlés avant écriture, copie de sauvegarde dans `<modèles>/.update-backup/`) et le serveur redémarre tout seul (≈ 30 s). Il faut pour cela que le dossier `eva-imagegen/app` soit à jour sur le NAS (c'est le cas après chaque `eva-update.zip` : `docker-compose.override.yml` le monte en lecture seule dans EVA).
Les changements de dépendances ou du Dockerfile demandent en revanche de relancer `install-imagegen.sh` (rare).

## EVA apprend de ce que tu lui donnes
- Les **photos** envoyées dans la conversation sont gardées (`uploads/photos/`, 400 maximum) avec, à côté, un texte : ta question + ce qu'EVA en a dit. Les **documents** déposés (PDF, Word, Excel, PowerPoint, texte, ZIP…) gardent leur texte extrait ; une **image déposée** est décrite par le modèle vision.
- Tout est **indexé tout de suite** (recherche sémantique, modèle `nomic-embed-text`) et retrouvé **automatiquement** quand ta question s'y rapporte : « que dit le contrat de Paul sur le préavis ? », « combien coûtait la facture que je t'ai envoyée ? ». Sans rapport, rien n'est ajouté (seuil réglable : `EVA_RECALL_MIN`, `EVA_RECALL_MIN_HINT`). EVA cite le nom du fichier ; l'outil `docs_search` permet la recherche explicite.
- Les passages retrouvés sont traités comme des données non fiables (aucune instruction qu'ils contiendraient n'est suivie).
- Limite : la mémoire d'une photo est ce qu'EVA en a dit ce jour-là (le modèle vision ne revoit pas l'image plus tard) — pose une vraie question en l'envoyant pour qu'elle en retienne l'essentiel.

## Administrateur et utilisateurs
L'interface complète (réglages, agents, évolution, maison, journal…) est celle de l'**administrateur** (ou de tout le monde tant que la connexion n'est pas activée). Les autres comptes (Paramètres › Sécurité › Utilisateurs, rôle « utilisateur ») ont une interface **minimaliste** : Conversation, Images, Listes. Leurs conversations et leurs images sont **privées** (l'administrateur voit tout). Ils ne peuvent ni changer les réglages ni gérer les modèles.

## Pas inclus
LoRA, vidéo, ControlNet ; génération d'images par une IA du marché (possible plus tard via « IA du marché »). EVA ne contourne pas les limites d'un modèle d'images : pour d'autres styles, installe-en un autre depuis la liste.

## Dépannage (cas rencontrés)
- **`could not select device driver "" with capabilities: [[gpu]]`** : le NVIDIA Container Toolkit n'est pas installé/configuré → `sudo apt install -y nvidia-container-toolkit && sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`. Le script le vérifie maintenant avant de démarrer.
- **`NO_PUBKEY` / dépôt « pas signé » alors que la clé est là** : droits trop stricts (umask 027) → `sudo chmod 644 /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg /etc/apt/sources.list.d/nvidia-container-toolkit.list`.
- **`/health` affiche `"device":"cpu"`** et `nvidia-smi` dans le conteneur dit `Failed to initialize NVML` : un `systemctl daemon-reload` a retiré la carte au conteneur → `sudo docker restart eva-imagegen`. Le script corrige l'ordre et redémarre tout seul si besoin.


## Vidéo par IA (expérimental)

EVA sait demander un court clip animé (1 à 3 secondes) au serveur d'images avec **LTX-Video**. **Désactivé par défaut**, et à prendre pour ce que c'est : ce modèle est conçu pour des cartes de 12 Go et plus. Sur une GTX 1060 de 6 Go, chaque pièce du modèle passe à tour de rôle par la carte : compte **plusieurs minutes** pour un clip court et petit, avec un résultat modeste. Le modèle (plusieurs dizaines de Go à télécharger la première fois) n'est chargé que le temps de la demande, puis la mémoire est rendue à Ollama.

Activer : sur le serveur IA, depuis le dossier `eva-imagegen/`, `sudo bash install-imagegen.sh --video --yes`. Vérifier : `/health` contient `"video": {"enabled": true, …}`.
Utiliser : demande à EVA « fais une petite vidéo de … » ; elle te demande confirmation (c'est long), puis le clip (WebP animé) arrive dans le dossier `generated` de l'espace de travail.
Si ça échoue (mémoire insuffisante), EVA le dit sans faire tomber le serveur ; essaie moins d'images. Pour le désactiver : relance l'installateur sans `--video`.
