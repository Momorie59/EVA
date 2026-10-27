#!/usr/bin/env bash
# Mise à jour d'EVA en une commande, après avoir décompressé l'archive dans le dossier d'EVA.
# À lancer depuis le dossier d'EVA :  ./mettre-a-jour.sh
#
# Ce que fait le script (tes données ne sont pas touchées) :
#  1. Garde une copie de ton .env, puis règle les modèles : qwen2.5:7b (principal) et llama3.2:3b (rapide).
#     Si tu avais choisi d'autres modèles exprès, relance avec GARDER_MODELES=1.
#  2. Vérifie que ces modèles sont présents sur le serveur IA (sans rien y installer : tu les télécharges depuis EVA).
#  3. Reconstruit EVA (cœur et interface) et attend qu'elle réponde.
set -euo pipefail
cd "$(dirname "$0")"
DOCKER=${DOCKER:-docker}                     # DOCKER=echo pour un essai à blanc

V="\e[32m✔\e[0m"; J="\e[33m•\e[0m"; R="\e[31m✘\e[0m"
ok() { echo -e "$V $*"; }; info() { echo -e "$J $*"; }; die() { echo -e "$R $*" >&2; exit 1; }

[[ -f docker-compose.yml && -d eva-core && -d eva-interface ]] || die "Lance ce script depuis le dossier d'EVA (ex. cd /home/eva/eva)."
[[ -f .env ]] || die "Pas de fichier .env ici : ce n'est pas une installation d'EVA."

# ---------------------------------------------------------------- 1. .env
COPIE=".env.avant-maj-$(date +%Y%m%d-%H%M%S)"
cp .env "$COPIE"
ok "Copie de ton .env : $COPIE"

lire() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
regler() {                                   # regler CLE valeur : remplace la ligne, ou l'ajoute
  if grep -qE "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else printf '\n%s=%s\n' "$1" "$2" >> .env; fi
}
if [[ "${GARDER_MODELES:-0}" == "1" ]]; then
  info "Modèles gardés tels quels : $(lire OLLAMA_MODEL) / $(lire EVA_MODELE_RAPIDE)"
else
  AVANT=$(lire OLLAMA_MODEL)
  regler OLLAMA_MODEL qwen2.5:7b
  regler EVA_MODELE_RAPIDE llama3.2:3b
  ok "Modèle principal : qwen2.5:7b${AVANT:+ (avant : $AVANT)} — modèle rapide : llama3.2:3b"
fi

# ---------------------------------------------------------------- 2. modèles présents sur le serveur IA ?
OLLAMA=$(lire OLLAMA_HOST)
if [[ -n "$OLLAMA" ]] && command -v curl >/dev/null; then
  if TAGS=$(curl -s --max-time 8 "$OLLAMA/api/tags"); then
    for m in "$(lire OLLAMA_MODEL)" "$(lire EVA_MODELE_RAPIDE)"; do
      [[ -z "$m" ]] && continue
      if grep -q "\"$m\"" <<<"$TAGS" || grep -q "\"$m:latest\"" <<<"$TAGS"; then ok "Modèle $m présent sur le serveur IA"
      else info "Modèle $m absent du serveur IA : télécharge-le depuis EVA (Paramètres › Intelligence › Modèles), sans rien faire sur le serveur."; fi
    done
  else
    info "Serveur IA injoignable ($OLLAMA) : vérification des modèles sautée."
  fi
fi

# ---------------------------------------------------------------- 3. reconstruction
info "Reconstruction d'EVA (2 à 5 minutes)…"
$DOCKER compose up -d --build eva-core eva-interface
if [[ "$DOCKER" == "echo" ]]; then exit 0; fi
for i in $(seq 1 60); do
  if $DOCKER compose exec -T eva-core python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health',timeout=3)" >/dev/null 2>&1; then
    ok "EVA répond. Mise à jour terminée."
    echo
    echo "Nouveautés à essayer :"
    echo "  • Paramètres › Sécurité & données : « Mes données » (tout récupérer / tout effacer) et les quotas par personne."
    echo "  • Page Mémoire : dis à EVA « retiens que je préfère les réponses courtes », puis « que sais-tu de moi ? »."
    echo "  • Paramètres › Intelligence › Agent de code : « Installer l'agent de code » (une fois, ~650 Mo)."
    exit 0
  fi
  sleep 5
done
die "EVA ne répond pas après 5 minutes. Envoie-moi :  docker compose logs --tail=60 eva-core"
