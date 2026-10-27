#!/bin/bash
# Diagnostic EVA en une commande :  cd /home/eva/eva && bash diagnostic.sh
# Affiche l'état des conteneurs, les dernières erreurs, la santé du serveur et la configuration (sans aucun secret).
cd "$(dirname "$0")" || exit 1
echo "=== 1. Conteneurs ==="; docker compose ps
echo; echo "=== 2. Santé d'eva-core (depuis le conteneur) ==="
docker compose exec -T eva-core python -c "import urllib.request,json;print(json.dumps(json.load(urllib.request.urlopen('http://localhost:8000/api/health',timeout=5)),indent=1)[:900])" 2>&1 | tail -15
echo; echo "=== 3. Dernières lignes d'eva-core ==="; docker compose logs --tail=40 eva-core 2>&1 | tail -40
echo; echo "=== 4. Erreurs récentes (tous services) ==="; docker compose logs --tail=300 2>&1 | grep -iE "error|traceback|exception|refused|denied|403|401" | tail -15
echo; echo "=== 5. Configuration (.env, valeurs masquées) ==="
[ -f .env ] && sed -E 's/^([A-Za-z_]*(TOKEN|KEY|SECRET|PASSWORD|PASS)[A-Za-z_]*)=.*/\1=********/' .env || echo ".env absent"
echo; echo "=== 6. Ressources ==="; df -h . | tail -1; free -m | head -2
echo; echo "Envoie-moi tout ce texte."
