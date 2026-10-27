# EVA — Interface V1

Structure de l'application front-end d'EVA : avatar 3D (le logo EVA, animé,
tient lieu de tête), panneau de conversation, widgets satellites (météo /
maison / système) et dock de contrôle micro/caméra.

Les états d'EVA (`idle`, `listening`, `thinking`, `acting`, `speaking`,
`error`) sont maintenant pilotés en temps réel par **EVA CORE** via
WebSocket — voir `src/hooks/useEvaCore.js`. `listening` reste géré
localement (bouton micro) tant que le flux audio réel n'est pas branché.

## Lancer en développement

```bash
npm install
cp .env.example .env.local   # rien à régler en général
npm run dev
```

Ouvre ensuite `http://localhost:5173`. Aucune adresse à configurer : `src/urls.js`
dérive les URL de la même origine que la page, et `vite.config.js` relaie
`/ws/chat`, `/api` et `/voice` vers `localhost:8000`/`8100` (surcharge :
`EVA_CORE_DEV_URL`, `EVA_VOICE_DEV_URL`) — comme le fait Caddy en prod. Il faut qu'[EVA CORE](../eva-core)
tourne en parallèle (`uvicorn app.main:app --reload`) pour qu'elle réponde
vraiment — sinon un message d'erreur s'affiche dans la conversation et le
point à côté du nom "EVA" en haut reste rouge.

## Build de production

```bash
npm run build
npm run preview
```

## Structure

```
src/
├── App.jsx                  → assemble l'écran, relié à useEvaCore
├── App.css                  → mise en page et styles de tous les composants
├── hooks/useEvaCore.js       → connexion WebSocket à EVA CORE, streaming,
│                                reconnexion automatique
├── styles/tokens.css         → palette de couleurs, typographies, espacements
├── components/
│   ├── Avatar3D.jsx          → scène 3D (react-three-fiber) : le logo EVA
│   │                            fait office de tête (rotation + anneau HUD
│   │                            pulsant), anneau d'aura d'état, socle
│   │                            holographique, cou/épaules
│   ├── TopBar.jsx             → barre supérieure (logo texte, indicateur de
│   │                             connexion à EVA CORE, réglages)
│   ├── StatusLine.jsx         → texte d'état + simulateur d'état (utile en
│   │                             dev pour prévisualiser sans backend)
│   ├── WidgetArc.jsx          → dispose les widgets en arc sous l'avatar
│   ├── widgets/
│   │   ├── WeatherWidget.jsx   → météo réelle (weather_get)
│   │   ├── DockerWidget.jsx    → conteneurs actifs/total (docker_ps)
│   │   └── SystemWidget.jsx    → CPU/RAM réels (system_stats), police mono
│   ├── ControlDock.jsx        → boutons micro / caméra / projets
│   ├── ChatDrawer.jsx         → tiroir de conversation (rétractable),
│   │                            gère aussi les bulles système et les
│   │                            confirmations (Autoriser/Refuser)
│   ├── DashboardPanel.jsx     → overlay Projets/Mémoire (bouton "Projets")
│   └── CameraPanel.jsx        → prévisualisation caméra + capture photo
hooks/
├── useEvaCore.js              → connexion WebSocket, streaming, jeton d'auth
├── useVoice.js                → micro (→ STT) et lecture des réponses (→ TTS)
├── useCamera.js               → accès caméra + capture d'une photo en base64
└── useWidgetData.js           → polling générique pour les widgets
public/
└── eva-logo.png               → le vrai logo, utilisé comme texture 3D
```

## Caméra (vision)

Le bouton caméra du dock ouvre `CameraPanel` (aperçu vidéo + déclencheur).
La photo capturée (JPEG, redimensionnée à 1024px de large max) reste en
attente sous forme de miniature au-dessus du champ de texte — le tiroir de
conversation s'ouvre tout seul pour la montrer. Tape une question
(optionnel) et envoie : le texte et l'image partent ensemble à EVA CORE,
qui les traite avec son modèle vision plutôt que via le Harness (voir le
README d'`eva-core`).

## Ce qui reste à brancher

1. **`acting`** : l'état existe côté avatar et côté protocole ; il
   s'allume déjà quand le Harness utilise un outil, mais rien ne le
   distingue encore visuellement d'un `thinking` normal côté interface.
2. **Widget maison** : `DockerWidget` occupe la place en attendant un
   outil Home Assistant ; à remplacer le jour où il existe.
3. **Streaming audio continu** : le micro envoie un blob complet à la fin
   de l'enregistrement (pas de VAD ni de flux continu).

## Design

Palette et typographies définies dans `src/styles/tokens.css` — thème
holographique façon Jarvis : fond bleu-noir profond, halo teal au repos,
rose quartz à l'écoute, violet en réflexion, ambre en action, rouge ambré en
erreur, cadre HUD et scanline autour de la scène 3D. Typographie Manrope
(interface) + IBM Plex Mono (données système uniquement, widget système).
