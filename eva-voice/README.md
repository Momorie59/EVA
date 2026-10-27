# EVA VOICE

Service FastAPI séparé pour la reconnaissance vocale (STT, via
[faster-whisper](https://github.com/SYSTRAN/faster-whisper)) et la synthèse
vocale (TTS, via [Piper](https://github.com/OHF-voice/piper1-gpl)) — 100%
local, aucun appel à un service cloud.

Séparé d'EVA CORE pour rester modulaire (cf. l'architecture d'outils prévue
dans le projet) et pour pouvoir, plus tard, le déplacer sur le serveur IA
(GPU) sans toucher au reste.

## Étape manuelle obligatoire : télécharger la voix Piper

Contrairement à Whisper (qui se télécharge tout seul au premier appel),
Piper a besoin que tu choisisses et télécharges une voix toi-même :

```bash
pip install piper-tts
python -m piper.download_voices --download-dir ./models fr_FR-siwis-medium
```

Ça dépose `fr_FR-siwis-medium.onnx` et `.onnx.json` dans `./models`, qui est
monté en volume dans le conteneur. D'autres voix françaises existent (voir
`python -m piper.download_voices --help` ou le catalogue Piper) — change
`PIPER_VOICE` dans `.env` si tu en choisis une autre.

## Toutes les langues

EVA comprend la langue dans laquelle on lui parle (Whisper en reconnaît une centaine, `WHISPER_LANGUAGE=auto`)
et répond dans cette langue. Pour la voix, Piper existe pour une quarantaine de langues : la première fois
qu'EVA doit parler une langue sans voix installée, elle **télécharge toute seule** la voix correspondante depuis
le catalogue officiel de Piper (Hugging Face) dans `./models`, une fois pour toutes. Le téléchargement démarre
dès que Whisper entend la nouvelle langue, pendant qu'EVA prépare sa réponse ; si la voix n'est pas encore là,
la première phrase est lue avec la voix par défaut.

- La voix choisie dans les réglages (`PIPER_VOICE` ou l'interface) est gardée pour sa propre langue.
- Imposer une voix pour une langue : `PIPER_VOICE_IT=it_IT-paola-medium`, `PIPER_VOICE_EN=…`
- Désactiver les téléchargements : `PIPER_AUTO_DOWNLOAD=0`.
- Langue sans voix Piper (japonais, coréen…) : EVA répond à l'écrit dans cette langue, la lecture utilise la voix par défaut.

Whisper, lui, télécharge son modèle automatiquement au premier appel à
`/stt` — il faut juste que la machine qui héberge ce service ait un accès
Internet normal à ce moment-là (pas besoin ensuite, le modèle reste en
cache).

## Lancer en local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m piper.download_voices --download-dir ./models fr_FR-siwis-medium

uvicorn app.main:app --reload --host 0.0.0.0 --port 8100
```

## Endpoints

- `POST /stt` — multipart, champ `audio` (wav/webm/mp3...) → `{"text": "..."}`
- `POST /tts` — JSON `{"text": "..."}` → fichier WAV (`audio/wav`)
- `GET /api/health` — état + config chargée

## Variables d'environnement

| Variable | Rôle | Défaut |
|---|---|---|
| `WHISPER_MODEL_SIZE` | Taille du modèle Whisper (`tiny`/`base`/`small`/`medium`) | `small` |
| `WHISPER_DEVICE` | `auto` (GPU NVIDIA si visible, sinon processeur), `cpu` ou `cuda`. Si le GPU échoue, retombe seul sur le processeur | `auto` |
| `WHISPER_COMPUTE_TYPE` | Précision ; vide = `float16` sur GPU, `int8` sur processeur | (vide) |
| `EVA_VOICES_DIR` | Dossier des voix Piper téléchargées | `./models` |
| `PIPER_VOICE` | Nom de la voix Piper à utiliser | `fr_FR-siwis-medium` |

## Limites connues (V1)

- Le premier appel à `/stt` est lent (chargement du modèle) — normal, les
  appels suivants sont rapides.
- Pas encore de streaming audio (le micro envoie un blob complet à la fin
  de l'enregistrement, pas un flux continu).
- Sur processeur, Whisper est plus lent que sur GPU : pour l'utiliser sur la carte NVIDIA du serveur IA,
  voir `docker-compose.gpu.yml` (service à lancer là-bas, `Dockerfile.gpu`). `GET /api/health` indique
  `whisper.device` (`cuda`/`cpu`) et la raison d'un éventuel repli.
