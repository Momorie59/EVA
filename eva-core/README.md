# EVA CORE

Backend FastAPI d'EVA : connexion à Ollama, Agent Harness (boucle d'outils
avec permissions), mémoire persistante, et un premier comportement
proactif (monitors en tâche de fond).

## Lancer en local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # édite OLLAMA_HOST avec l'IP de ton serveur IA

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Nécessite un Postgres accessible (voir `DATABASE_URL`) et, pour les outils
Docker, un accès au socket Docker (`/var/run/docker.sock`).

Vérifie que ça tourne :
```bash
curl http://localhost:8000/api/health
```

## Avec Docker (sur le NAS)

Voir le `docker-compose.yml` à la racine du dépôt — ce service y est déjà
configuré (Postgres, socket Docker en lecture seule, workspace en volume).

## Variables d'environnement

| Variable | Rôle | Défaut |
|---|---|---|
| `OLLAMA_HOST` | URL du serveur IA où tourne Ollama | `http://192.168.1.50:11434` |
| `OLLAMA_MODEL` | Modèle à utiliser | `llama3.1:8b` |
| `CORS_ORIGINS` | Origines autorisées (séparées par des virgules) | `*` |
| `EVA_SYSTEM_PROMPT` | Prompt système d'EVA | voir `config.py` |
| `EVA_WORKSPACE` | Dossier où EVA lit/écrit (outils filesystem) | `./workspace` |
| `DATABASE_URL` | Connexion Postgres (mémoire persistante) | `postgresql://eva:eva@localhost:5432/eva` |
| `EVA_HISTORY_LIMIT` | Nb de messages rechargés à la reconnexion | `30` |
| `EVA_AUTH_TOKEN` | Jeton partagé protégeant le WebSocket (vide = pas d'auth) | _(vide)_ |

## Agent Harness

`app/harness/loop.py` implémente la boucle : le modèle décide (avec accès
aux schémas d'outils), le Harness exécute ce qui est demandé, observe le
résultat, et reboucle — jusqu'à une réponse finale sans appel d'outil (ou
`MAX_TOOL_ITERATIONS` atteint).

**Vrai streaming** : la décision elle-même (`ollama_client.stream_decide`)
est diffusée en direct — quand le modèle répond sans passer par un outil,
le texte arrive au client token par token au fur et à mesure qu'Ollama le
génère, pas rejoué artificiellement après coup. Pendant un tour avec appel
d'outil, le modèle n'émet normalement pas de texte avant les `tool_calls`,
donc rien ne s'affiche avant la vraie réponse finale.

### Outils disponibles

| Outil | Permission | Rôle |
|---|---|---|
| `fs_list`, `fs_read` | AUTO | Lire le workspace |
| `fs_write`, `fs_append` | AUTO\* | Créer/modifier un fichier |
| `fs_delete` | **CONFIRM** | Supprimer un fichier |
| `project_init` | AUTO | Crée le squelette d'un projet (README, DECISIONS.md...) |
| `project_log_decision`, `project_log_change` | AUTO | Note une décision/un changement daté dans les docs du projet |
| `weather_get` | AUTO | Météo actuelle + prévisions (Open-Meteo, sans clé) |
| `docker_ps`, `docker_logs` | AUTO | Lecture seule sur les conteneurs Docker |
| `docker_restart`, `docker_stop`, `docker_start` | **CONFIRM** | Change l'état d'un conteneur |
| `system_stats` | AUTO | CPU/RAM/disque de la machine hôte |
| `terminal_run` | **CONFIRM** | Exécute une commande shell dans le workspace — toujours confirmé, même en lecture seule |
| `web_search` | AUTO | Recherche web (DuckDuckGo, sans clé d'API) |
| `web_fetch` | AUTO\*\* | Lit le contenu texte d'une page web (HTML nettoyé ou texte brut) |
| `git_status`, `git_log`, `git_diff` | AUTO | Lecture d'un dépôt Git dans le workspace |
| `git_commit` | **CONFIRM** | `git add -A` + commit dans un dépôt du workspace |

Les niveaux de permission suivent le brief initial : la création est
autorisée automatiquement, seule la suppression demande confirmation.

\* **Permission contextuelle** (`permission_for`, pas juste statique) :
`fs_write`/`fs_append` passent en CONFIRM si le chemin est sensible —
`.env`, `docker-compose.yml`, un dossier `config(s)`/`secret(s)`, un
fichier `.key`/`.pem`/`.crt`, ou un nom contenant "password"/"secret"/
"credential"/"token". Le reste (notes, docs de projet...) reste AUTO.

\*\* **Protection SSRF** : avant toute connexion, l'hôte de l'URL est
résolu et vérifié — une IP privée/loopback/link-local (réseau local,
`127.0.0.1`, `169.254.169.254` — métadonnées cloud...) est refusée. Chaque
redirection est revalidée de la même façon (`follow_redirects` désactivé,
suivi manuel) pour empêcher un contournement par redirection. Limite
connue : la vérification a lieu avant la connexion, pas pendant — une
attaque DNS-rebinding fine (résolution différente entre la vérification et
la connexion réelle) n'est pas couverte ; un vrai pare-feu réseau sur le
conteneur reste la protection complète.

### Flux de confirmation

Pour un outil `CONFIRM`, le serveur envoie `{"type": "confirm_request", ...}`
et attend `{"type": "confirm_response", "approved": true|false}` avant de
continuer. Le frontend gère déjà ça (bulle avec boutons Autoriser/Refuser).

## Vision (photos)

Un message WebSocket peut inclure une image en base64 :
```json
{"text": "Qu'est-ce que c'est ?", "image": "<base64 JPEG>"}
```
(`text` est optionnel — sans texte, EVA reçoit une légende par défaut
"Que vois-tu sur cette image ?")

Ce n'est **pas** traité par l'Agent Harness : une image part directement
vers `EVA_VISION_MODEL` (modèle multimodal, ex. `llava` — différent du
modèle à outils configuré dans `OLLAMA_MODEL`, qui n'est généralement pas
multimodal). L'image elle-même n'est jamais renvoyée aux appels suivants
du modèle à outils ; seul un résumé texte (`"<légende> [a envoyé une
photo]"` + la réponse d'EVA) est gardé dans l'historique et la mémoire
persistante — sinon chaque photo alourdirait indéfiniment le contexte.

## Mémoire persistante

`app/db.py` + `app/memory.py` : chaque message (user/assistant) est
sauvegardé dans Postgres, par session (`?session=...` dans l'URL
WebSocket, `default` si absent). À la reconnexion, les derniers messages
sont rechargés automatiquement.

## Comportement proactif (Monitors)

`app/harness/monitors/` : des vérifications périodiques qui peuvent
notifier un client connecté sans qu'il ait rien demandé — via
`app/connections.py` (`ConnectionManager`), qui garde la liste des
WebSocket ouverts par session.

Deux monitors actifs :
- `WorkspaceWatchMonitor` — signale les fichiers créés/modifiés/supprimés
  dans le workspace (`{"type": "proactive", ...}` côté client)
- `SystemThresholdMonitor` — surveille CPU/RAM/disque (seuils réglables
  via `EVA_CPU_THRESHOLD`/`EVA_MEMORY_THRESHOLD`/`EVA_DISK_THRESHOLD`,
  défaut 90%), signale un dépassement puis le retour à la normale, sans
  re-notifier à chaque tour tant que ça reste au-dessus du seuil

D'autres monitors (agenda, mails...) suivront le même modèle une fois les
outils correspondants prêts.

## Sécurité

- **Sandboxing filesystem** : tous les outils `fs_*` sont bornés à
  `EVA_WORKSPACE` — une tentative de sortie (`../..`, chemin absolu) est
  refusée.
- **Authentification** : si `EVA_AUTH_TOKEN` est défini, le WebSocket exige
  `?token=...` en query param, sinon la connexion est refusée avant même
  d'être acceptée. Laissé vide par défaut pour le dev local — **à définir
  avant toute exposition hors réseau local de confiance**.
- **Socket Docker** : `docker_ps`/`docker_logs`/`docker_restart` etc. ont
  besoin d'accès à `/var/run/docker.sock`. Même monté en lecture seule
  côté bind Docker, ce socket reste un accès puissant côté hôte — ne
  l'expose qu'à un service de confiance, jamais à Internet directement.
- **Non-root par défaut** : le conteneur tourne en utilisateur `eva`, pas
  en root (voir `docker-entrypoint.sh`). C'est ce qui rend `RLIMIT_NPROC`
  (voir plus bas) réellement effectif — vérifié les deux façons : un
  fork-bomb (60 process concurrents) passe intégralement en root
  (`CAP_SYS_RESOURCE` exempte de la limite) mais échoue avec "Cannot fork"
  en non-root. L'entrypoint aligne automatiquement un groupe sur le GID
  réel du socket Docker monté (variable d'un hôte à l'autre) et corrige la
  propriété du volume workspace si besoin, avant de passer en `eva`.
- **`terminal_run`** : exécute avec les mêmes permissions que l'utilisateur
  `eva` du conteneur — ce n'est **pas** un vrai sandbox (pas de chroot/
  namespace dédié). Demande toujours confirmation, mais évite de combiner
  ce conteneur avec le socket Docker monté en écriture ou d'autres accès
  sensibles : un `terminal_run` confirmé par erreur avec le socket Docker
  accessible en écriture reste un risque sérieux.
  Bornes réellement effectives, testées : mémoire (512 Mo, `RLIMIT_AS`),
  temps CPU (`RLIMIT_CPU`), et nombre de processus (`RLIMIT_NPROC`, anti
  fork-bomb, effectif grâce au non-root ci-dessus) — un timeout tue tout
  l'arbre de processus (`os.setsid` + `killpg`), pas seulement le shell
  parent.
- **File d'attente des messages** : `app/broker.py` garantit qu'un message
  envoyé pendant une confirmation en attente n'est pas perdu (il est
  traité juste après la résolution de la confirmation).

## Widgets et Dashboard (REST, sans passer par le LLM)

Pour un rafraîchissement rapide côté interface, sans le coût d'un aller-
retour LLM. Protégés par `EVA_AUTH_TOKEN` comme le WebSocket (`Authorization:
Bearer ...`) — seul `/api/health` reste ouvert, pour le diagnostic.

- `GET /api/widgets/weather?city=...` — météo (défaut : `EVA_DEFAULT_CITY`)
- `GET /api/widgets/system` — CPU/RAM/disque
- `GET /api/widgets/docker` — conteneurs actifs/total
- `GET /api/dashboard/projects` — liste des projets du workspace
- `GET /api/dashboard/projects/{slug}` — contenu des 5 docs d'un projet
- `GET /api/dashboard/memory?session=default&limit=50` — historique persistant

## Ce qui n'existe pas encore

- Plus d'outils que ceux listés ci-dessus (Home Assistant, agenda, email...)
- D'autres monitors qu'espace de travail et seuils système
