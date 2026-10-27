#!/bin/bash
# Désinstalle le satellite EVA de cet ordinateur Linux / Raspberry Pi (service, lancement automatique, dossier).
#   bash desinstaller-linux.sh        (ou : curl -fsSk https://ADRESSE-DU-NAS:8443/api/public/satellite/desinstaller-linux.sh | bash)
DOSSIER="$HOME/eva-satellite"
echo "== Arrêt du satellite"
if [ -f /etc/systemd/system/eva-satellite.service ]; then
  sudo systemctl disable --now eva-satellite 2>/dev/null || true
  sudo rm -f /etc/systemd/system/eva-satellite.service
  sudo systemctl daemon-reload
fi
rm -f "$HOME/.config/autostart/eva-satellite.desktop"
pkill -f "$DOSSIER/satellite.py" 2>/dev/null || pkill -f "eva-satellite/venv/bin/python" 2>/dev/null || true
echo "== Suppression de $DOSSIER"
rm -rf "$DOSSIER"
echo "Le satellite est désinstallé. Pense à le supprimer aussi dans EVA (Maison › Satellites) s'il y est encore."
