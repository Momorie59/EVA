#!/bin/bash
# Désinstalle le satellite EVA de ce Mac (lancement à l'ouverture de session, dossier).
#   bash desinstaller-mac.sh        (ou : curl -fsSk https://ADRESSE-DU-NAS:8443/api/public/satellite/desinstaller-mac.sh | bash)
DOSSIER="$HOME/eva-satellite"
PLIST="$HOME/Library/LaunchAgents/fr.eva.satellite.plist"
echo "== Arrêt du satellite"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
pkill -f "$DOSSIER/satellite.py" 2>/dev/null || true
echo "== Suppression de $DOSSIER"
rm -rf "$DOSSIER"
echo "Le satellite est désinstallé. Tu peux aussi retirer Python des autorisations (Réglages Système › Confidentialité et sécurité)."
echo "Pense à le supprimer aussi dans EVA (Maison › Satellites) s'il y est encore."
