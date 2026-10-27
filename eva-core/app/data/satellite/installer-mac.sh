#!/bin/bash
# Installe un satellite vocal d'EVA sur macOS et le lance à l'ouverture de session.
#   bash installer-mac.sh https://192.168.1.10:8443 evasat_XXXXXXXX [local] [fenetre] [tableau] [ecran] [gestes]
set -euo pipefail
EVA="${1:-}"; JETON="${2:-}"; EVEIL="whisper"; FENETRE=0; TABLEAU=0; ECRAN=0; GESTES=0
for opt in "${@:3}"; do
  case "$opt" in
    local) EVEIL="local" ;; whisper) EVEIL="whisper" ;;
    fenetre) FENETRE=1 ;; tableau) FENETRE=1; TABLEAU=1 ;; ecran) ECRAN=1 ;; gestes) GESTES=1 ;;
    *) echo "Option inconnue : $opt (local, fenetre, tableau, ecran, gestes)"; exit 1 ;;
  esac
done
if [ -z "$EVA" ] || [ -z "$JETON" ]; then
  echo "Usage : bash installer-mac.sh https://ADRESSE-DU-NAS:8443 evasat_…   (jeton : EVA › Maison › Satellites)"; exit 1
fi
EVA="${EVA%/}"
DOSSIER="$HOME/eva-satellite"
PLIST="$HOME/Library/LaunchAgents/fr.eva.satellite.plist"

echo "== Python"
PY=""
for c in python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys; assert (3, 9) <= sys.version_info[:2] <= (3, 13)" 2>/dev/null; then PY="$(command -v "$c")"; break; fi
done
if [ -z "$PY" ]; then
  if command -v brew >/dev/null; then
    brew install python@3.12 && PY="$(brew --prefix)/bin/python3.12"
  else
    echo "Python n'est pas installé. macOS va proposer d'installer les « outils de ligne de commande » : accepte,"
    echo "attends la fin, puis relance cette même commande."
    xcode-select --install 2>/dev/null || true
    exit 1
  fi
fi
echo "Python : $PY"

echo "== Arrêt d'une ancienne installation éventuelle"
launchctl unload "$PLIST" 2>/dev/null || true
pkill -f "$DOSSIER/satellite.py" 2>/dev/null || true

mkdir -p "$DOSSIER" && cd "$DOSSIER"
echo "== Certificat d'EVA"
curl -fsSk "$EVA/api/https/install/eva-certificat.crt" -o eva-certificat.crt || echo "(pas de certificat propre à EVA : vérification standard)"
echo "== Programme du satellite"
for f in satellite.py gestes.py; do
  curl -fsS --cacert eva-certificat.crt "$EVA/api/public/satellite/$f" -o "$f" 2>/dev/null || curl -fsS "$EVA/api/public/satellite/$f" -o "$f"
done
curl -fsSk "$EVA/api/public/satellite/desinstaller-mac.sh" -o desinstaller.sh || true     # pour désinstaller plus tard : bash desinstaller.sh
"$PY" -m venv venv
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q numpy sounddevice requests psutil websocket-client
if [ "$ECRAN" = 1 ]; then
  echo "== Écran : capture, lecture du texte, souris et clavier (mss, rapidocr, Quartz)"
  ./venv/bin/pip install -q mss pillow pyobjc-framework-Quartz
  ./venv/bin/pip install -q rapidocr_onnxruntime || ./venv/bin/pip install -q rapidocr onnxruntime
fi
if [ "$GESTES" = 1 ]; then
  echo "== Gestes : caméra (mediapipe, opencv) et modèle de la main"
  ./venv/bin/pip install -q mediapipe opencv-python || echo "MediaPipe ne s'installe pas avec ce Python (il faut 3.9 à 3.12)."
  curl -fsS --cacert eva-certificat.crt "$EVA/vendor/mediapipe/hand_landmarker.task" -o hand_landmarker.task 2>/dev/null \
    || curl -fsS "$EVA/vendor/mediapipe/hand_landmarker.task" -o hand_landmarker.task
fi
if [ "$EVEIL" = "local" ]; then
  echo "== Mot d'éveil local (sherpa-onnx, modèle de 17 Mo)"
  ./venv/bin/pip install -q sherpa-onnx
  mkdir -p modele-eveil
  curl -fsSL https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2 \
    | tar -xj -C modele-eveil --strip-components=1
fi
# Couper / rétablir l'écoute sans passer par EVA : bash ~/eva-satellite/pause.sh  /  bash ~/eva-satellite/reprise.sh
printf '#!/bin/bash\ntouch "%s/pause" && echo "Satellite EVA en pause : il n'"'"'écoute plus."\n' "$DOSSIER" > pause.sh
printf '#!/bin/bash\nrm -f "%s/pause" && echo "Satellite EVA : écoute réactivée."\n' "$DOSSIER" > reprise.sh
chmod +x pause.sh reprise.sh
printf '#!/bin/bash\nlaunchctl load -w "%s" 2>/dev/null; echo "Satellite EVA démarré."\n' "$PLIST" > demarrer.sh
printf '#!/bin/bash\nlaunchctl unload "%s" 2>/dev/null; pkill -f "%s/satellite.py"; echo "Satellite EVA arrêté (raccourci EVA demarrer pour le relancer)."\n' "$PLIST" "$DOSSIER" > arreter.sh
chmod +x demarrer.sh arreter.sh
for A in pause reprise demarrer arreter; do
  cp "$A.sh" "$HOME/Desktop/EVA $A.command" 2>/dev/null && chmod +x "$HOME/Desktop/EVA $A.command" || true
done
tf() { [ "$1" = 1 ] && echo true || echo false; }
cat > satellite.json <<JSON
{"eva": "$EVA", "jeton": "$JETON", "certificat": "eva-certificat.crt", "eveil": "$EVEIL",
 "fenetre": $(tf $FENETRE), "tableau": $(tf $TABLEAU), "ecran": $(tf $ECRAN), "gestes": $(tf $GESTES)}
JSON
chmod 600 satellite.json
echo "== Micros et haut-parleurs détectés :"
./venv/bin/python satellite.py --liste-audio || true

echo "== Lancement à l'ouverture de session"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>fr.eva.satellite</string>
  <key>ProgramArguments</key><array><string>$DOSSIER/venv/bin/python</string><string>$DOSSIER/satellite.py</string></array>
  <key>WorkingDirectory</key><string>$DOSSIER</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$DOSSIER/satellite.log</string>
  <key>StandardErrorPath</key><string>$DOSSIER/satellite.log</string>
</dict></plist>
PL
launchctl load -w "$PLIST"
echo
echo "C'est prêt. Dis « EVA, quelle heure est-il ? ». Journal : $DOSSIER/satellite.log"
echo "macOS va demander l'accès au MICRO : accepte."
if [ "$ECRAN" = 1 ] || [ "$GESTES" = 1 ]; then
  echo "Pour l'écran et les gestes, autorise aussi Python dans Réglages Système › Confidentialité et sécurité :"
  echo "  « Enregistrement de l'écran », « Accessibilité » et « Caméra » (Python : $DOSSIER/venv/bin/python)."
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null || true
fi
echo "Arrêt : launchctl unload $PLIST"
