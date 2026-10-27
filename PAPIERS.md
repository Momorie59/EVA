# Papiers

EVA suit les papiers de la famille (France et à l'étranger) : contrats, assurances, abonnements, impôts, garanties,
pièces d'identité. Elle les lit, repère les dates importantes et prévient **avant** qu'il soit trop tard
(préavis de résiliation, renouvellements, paiements, fins de garantie, expirations).

**Elle lit et rappelle. Elle ne résilie, ne paie et n'envoie jamais rien** (voir `CHARTE.md`).

## Comment c'est organisé

```
Dossiers du NAS ─┐
Page Papiers ────┼─► EVA ──► Paperless-ngx (OCR fra+ita, archives)
Conversation ────┘    │
                      ├─► analyse de chaque document par Ollama (échéances, préavis, garanties…)
                      ├─► page Papiers, réponses dans la conversation, outils papiers_*
                      └─► point papiers du matin (conversation + Telegram)
```

- **Paperless-ngx** (service à part, sur le NAS) fait l'OCR et garde les originaux. Il ne surveille plus aucun dossier : c'est EVA qui s'en charge.
- **EVA** fait tout le reste, dans `eva-core/app/papiers/`. Ses données sont dans `workspace/papiers/papiers.db` (incluse dans la sauvegarde d'EVA).
- Il n'y a plus de conteneur « majordome » séparé.

## Faire entrer des papiers

1. **Page Papiers › Déposer** : glisser-déposer autant de fichiers que tu veux (PDF, photos, Word…). Ils partent un par un vers Paperless.
2. **Dossiers surveillés** : choisis dans *Papiers › Réglages* un ou plusieurs dossiers du NAS. Copie-y des centaines de fichiers d'un coup : EVA les envoie par lots de 25 par minute, puis les range dans un sous-dossier `_importés` (ou les supprime, ou les laisse, au choix). Les sous-dossiers sont parcourus ; un fichier encore en cours de copie est attendu.
3. **Conversation** : joins un fichier avec « range ça dans mes papiers » (ou « papiers », « ajoute au majordome ») : envoi direct, sans passer par le modèle.

Ensuite, Paperless lit le document (1 à 3 min sur le M715q), puis EVA l'analyse par passages : 3 documents par
passage, un passage par minute (réglable), pour que le serveur IA reste disponible pour la conversation. Compte
environ 45 s par document sur une GTX 1060, soit une centaine de documents en un peu plus d'une heure et demie.
La page Papiers montre l'avancement et une estimation du temps restant.

## Au quotidien

- **Page Papiers** : échéances à venir (« C'est fait », « Ignorer »), papiers à vérifier (corriger la date, le préavis, ajouter une échéance oubliée), dépôt, réglages.
- **Réponses instantanées** (sans le modèle, environ une seconde) : « quelles sont mes échéances ? », « … de la semaine », « qu'est-ce que j'ai à payer ce mois-ci ? », « point papiers », « des papiers à vérifier ? ».
- **Questions précises** (par le modèle) : « quand expire la garantie du lave-linge ? », « quel est le préavis de la box ? ».
- **Le matin** (`EVA_PAPIERS_HEURE`, 8 h) : « Point papiers » avec les échéances qui passent un seuil (J-30, J-7, J-1, jour J, retard), comptées depuis la **date où il faut agir** (échéance moins préavis). Le lundi, le résumé du mois s'ajoute. Jamais deux fois la même alerte.

Un document passe « à vérifier » quand EVA n'est pas sûre (confiance sous le seuil), qu'elle a projeté une date
annuelle (contrat ancien reconduit), qu'un contrat ne semble contenir aucune date, ou qu'il est illisible. Tant
qu'une échéance n'est pas validée, elle ne déclenche aucune alerte. Une correction manuelle est conservée même
si le document est réanalysé.

## Qui y a accès

La fonctionnalité **Papiers** est réservée à l'administrateur par défaut. Pour l'ouvrir à quelqu'un (ton conjoint,
par exemple) : *Paramètres › Utilisateurs › fonctionnalités*. Un ami connecté à EVA ne voit jamais les papiers de
la famille, ni dans la page, ni dans la conversation. Les réglages et les dossiers surveillés restent modifiables par
l'administrateur seul.

| Outil | Permission | Rôle |
|---|---|---|
| `papiers_echeances` | auto | échéances à venir (date d'action, préavis, lien vers le document) |
| `papiers_a_verifier` | auto | extractions incertaines en attente de vérification |
| `papiers_question` | auto | question libre sur les documents (contenu marqué non fiable) |
| `papiers_deposer` | auto | envoie un fichier joint à Paperless (quand on demande de le ranger) |
| `papiers_marquer` | confirmation | faite / ignorer / valider |
| `papiers_corriger` | confirmation | date, préavis, description |

## Installation

1. **Paperless-ngx** sur le NAS (le dossier `majordome/` de l'ancienne installation convient : remplace son
   `docker-compose.yml` par celui de `paperless-pour-eva`, qui ne garde que Paperless et ses services).
2. Dans le `.env` d'EVA (ou plus tard dans *Papiers › Réglages*) :
   ```
   EVA_PAPERLESS_URL=http://host.docker.internal:8002        # Paperless vu depuis EVA
   EVA_PAPERLESS_PUBLIC_URL=http://192.168.1.10:8002        # pour ouvrir les documents depuis ton navigateur
   EVA_PAPERLESS_TOKEN=<jeton API de Paperless>
   EVA_PAPIERS_RACINE_NAS=/home/eva                           # dossier du NAS visible par EVA (monté en /papiers)
   EVA_PAPIERS_DOSSIERS=majordome/a-classer                   # facultatif : dossiers surveillés, relatifs à la racine
   ```
3. `docker compose up -d --build eva-core eva-interface`
4. Les fichiers des dossiers surveillés doivent être lisibles **et modifiables** par EVA (utilisateur 1000) pour être
   rangés : `chown -R 1000:1000 /home/eva/majordome/a-classer`.

Réglages disponibles dans la page : adresses et jeton de Paperless (avec test de connexion), modèle d'analyse (liste des
modèles du serveur IA), documents analysés par minute, seuils d'alerte, seuil de confiance, dossiers surveillés
(navigateur de dossiers, création de dossier), devenir des fichiers après import.

## Limites connues

- La qualité dépend du modèle : `qwen2.5:7b` lit souvent mieux le JSON et l'italien que `llama3.1:8b`.
- Paperless doit tourner : sans lui, EVA garde les fichiers dans les dossiers et réessaie à chaque passage.
- Testé avec de faux Paperless/Ollama (tests automatiques) et un vrai Paperless chez toi pour l'ancienne version ; la version intégrée reste à valider sur le NAS.

## Tests

```bash
cd eva-core && pip install pytest && python -m pytest tests -q
```
