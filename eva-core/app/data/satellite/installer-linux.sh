#!/bin/bash
# Installe un satellite vocal d'EVA (Raspberry Pi OS, Debian, Ubuntu…) et le lance au démarrage.
#   bash installer-linux.sh https://192.168.1.10:8443 evasat_XXXXXXXX [local] [fenetre] [tableau] [ecran] [gestes]
#   local : mot d'éveil détecté sur le satellite ; fenetre, tableau, ecran, gestes : options d'un PC avec écran
set -euo pipefail
EVA="${1:-}"; JETON="${2:-}"; EVEIL="whisper"; FENETRE=0; TABLEAU=0; ECRAN=0; GESTES=0
for opt in "${@:3}"; do
  case "$opt" in
    local) EVEIL="local" ;; whisper) EVEIL="whisper" ;;
    fenetre) FENETRE=1 ;; tableau) FENETRE=1; TABLEAU=1 ;; ecran) ECRAN=1 ;; gestes) GESTES=1 ;;
    *) echo "Option inconnue : $opt (local, fenetre, tableau, ecran, gestes)"; exit 1 ;;
  esac
done
BUREAU=$(( FENETRE + ECRAN + GESTES ))
if [ -z "$EVA" ] || [ -z "$JETON" ]; then
  echo "Usage : bash installer-linux.sh https://ADRESSE-DU-NAS:8443 evasat_…   (jeton : EVA › Maison › Satellites)"; exit 1
fi
EVA="${EVA%/}"
DOSSIER="$HOME/eva-satellite"
echo "== Paquets système (micro, son)"
if command -v apt-get >/dev/null; then                  # Debian, Ubuntu, Raspberry Pi OS, Mint
  sudo apt-get update -qq && sudo apt-get install -y -qq python3-venv python3-pip python3-tk libportaudio2 curl
  if [ "$BUREAU" -gt 0 ]; then sudo apt-get install -y -qq xdotool playerctl || true; fi
elif command -v dnf >/dev/null; then                    # Fedora, RHEL
  sudo dnf install -y -q python3 python3-pip python3-tkinter portaudio curl
  if [ "$BUREAU" -gt 0 ]; then sudo dnf install -y -q xdotool playerctl || true; fi
elif command -v pacman >/dev/null; then                 # Arch, Manjaro
  sudo pacman -S --needed --noconfirm python python-pip tk portaudio curl
  if [ "$BUREAU" -gt 0 ]; then sudo pacman -S --needed --noconfirm xdotool playerctl || true; fi
elif command -v zypper >/dev/null; then                 # openSUSE
  sudo zypper -n install python3 python3-pip python3-tk portaudio curl
  if [ "$BUREAU" -gt 0 ]; then sudo zypper -n install xdotool playerctl || true; fi
else
  echo "Gestionnaire de paquets inconnu : installe toi-même python3 (venv, tkinter), portaudio et curl, puis relance."
fi
if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] && [ "$ECRAN" = 1 ]; then
  echo "(Session Wayland : pour que EVA voie l'écran et clique, ouvre plutôt une session « Xorg » / « X11 » à la connexion.)"
fi
echo "== Arrêt d'une ancienne installation éventuelle"
sudo systemctl stop eva-satellite 2>/dev/null || true
pkill -f "$HOME/eva-satellite/satellite.py" 2>/dev/null || pkill -f "eva-satellite/venv/bin/python" 2>/dev/null || true
mkdir -p "$DOSSIER" && cd "$DOSSIER"
echo "== Certificat d'EVA (récupéré une fois, puis vérifié à chaque échange)"
curl -fsSk "$EVA/api/https/install/eva-certificat.crt" -o eva-certificat.crt || echo "(pas de certificat propre à EVA : vérification standard)"
echo "== Programme du satellite"
curl -fsS --cacert eva-certificat.crt "$EVA/api/public/satellite/satellite.py" -o satellite.py 2>/dev/null \
  || curl -fsS "$EVA/api/public/satellite/satellite.py" -o satellite.py
curl -fsS --cacert eva-certificat.crt "$EVA/api/public/satellite/gestes.py" -o gestes.py 2>/dev/null \
  || curl -fsS "$EVA/api/public/satellite/gestes.py" -o gestes.py || true
curl -fsSk "$EVA/api/public/satellite/desinstaller-linux.sh" -o desinstaller.sh || true     # pour désinstaller plus tard : bash desinstaller.sh
python3 -m venv venv
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q numpy sounddevice requests psutil websocket-client
if [ "$ECRAN" = 1 ]; then
  echo "== Écran : capture et lecture du texte (mss, rapidocr)"
  ./venv/bin/pip install -q mss pillow pystray
  ./venv/bin/pip install -q rapidocr_onnxruntime || ./venv/bin/pip install -q rapidocr onnxruntime
fi
if [ "$GESTES" = 1 ]; then
  echo "== Gestes : caméra (mediapipe, opencv) et modèle de la main (8 Mo, servi par EVA)"
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
if [ "$BUREAU" -gt 0 ]; then
  printf '#!/bin/bash\ncd "%s" && nohup ./venv/bin/python satellite.py > satellite.log 2>&1 &\necho "Satellite EVA démarré."\n' "$DOSSIER" > demarrer.sh
  printf '#!/bin/bash\npkill -f "%s/satellite.py"; pkill -f "eva-satellite/venv/bin/python"; echo "Satellite EVA arrêté."\n' "$DOSSIER" > arreter.sh
else
  printf '#!/bin/bash\nsudo systemctl start eva-satellite && echo "Satellite EVA démarré."\n' > demarrer.sh
  printf '#!/bin/bash\nsudo systemctl stop eva-satellite && echo "Satellite EVA arrêté."\n' > arreter.sh
fi
chmod +x demarrer.sh arreter.sh
for B in "$HOME/Bureau" "$HOME/Desktop"; do
  if [ -d "$B" ]; then
    for A in pause reprise demarrer arreter; do
      printf '[Desktop Entry]\nType=Application\nName=EVA %s\nExec=bash %s/%s.sh\nTerminal=false\nIcon=audio-input-microphone\n' "$A" "$DOSSIER" "$A" > "$B/eva-$A.desktop"
      chmod +x "$B/eva-$A.desktop"
    done
    break
  fi
done
tf() { [ "$1" = 1 ] && echo true || echo false; }
cat > satellite.json <<JSON
{"eva": "$EVA", "jeton": "$JETON", "certificat": "eva-certificat.crt", "eveil": "$EVEIL",
 "fenetre": $(tf $FENETRE), "tableau": $(tf $TABLEAU), "ecran": $(tf $ECRAN), "gestes": $(tf $GESTES)}
JSON
chmod 600 satellite.json
echo "== Micros et haut-parleurs détectés :"
./venv/bin/python satellite.py --liste-audio || true
if [ "$BUREAU" -gt 0 ]; then
  # Fenêtre, écran ou caméra : le satellite doit tourner DANS ta session graphique (pas en service système).
  echo "== Lancement à l'ouverture de session (bureau)"
  mkdir -p "$HOME/.config/autostart"
  cat > "$HOME/.config/autostart/eva-satellite.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Satellite EVA
Exec=$DOSSIER/venv/bin/python $DOSSIER/satellite.py
Path=$DOSSIER
X-GNOME-Autostart-enabled=true
DESK
  sudo systemctl disable --now eva-satellite 2>/dev/null || true
  (cd "$DOSSIER" && nohup ./venv/bin/python satellite.py > satellite.log 2>&1 &)
  echo
  echo "C'est prêt. Dis « EVA, quelle heure est-il ? ». Journal : $DOSSIER/satellite.log"
  exit 0
fi
echo "== Service au démarrage"
sudo tee /etc/systemd/system/eva-satellite.service >/dev/null <<UNIT
[Unit]
Description=Satellite vocal d'EVA
After=network-online.target sound.target
Wants=network-online.target

[Service]
User=$USER
SupplementaryGroups=audio
WorkingDirectory=$DOSSIER
ExecStart=$DOSSIER/venv/bin/python $DOSSIER/satellite.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now eva-satellite
echo
echo "C'est prêt. Dis « EVA, quelle heure est-il ? »."
echo "Journal : journalctl -u eva-satellite -f     Arrêt : sudo systemctl stop eva-satellite"
echo "Autre micro : ajoute \"micro\": NUMÉRO dans $DOSSIER/satellite.json puis sudo systemctl restart eva-satellite"
