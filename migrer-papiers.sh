#!/usr/bin/env bash
# Passe de l'ancien « majordome » séparé aux papiers intégrés à EVA, en une commande.
# À lancer depuis le dossier d'EVA :  ./migrer-papiers.sh [dossier du majordome]   (défaut : /home/eva/majordome)
#
# Ce que fait le script (rien n'est supprimé : les documents de Paperless et ses réglages sont gardés) :
#  1. Paperless : ne garde que Paperless et ses services (plus de conteneur majordome ni ntfy),
#     et il ne surveille plus le dossier de dépôt (EVA le fait, sinon chaque fichier entrerait deux fois).
#  2. EVA : renseigne Paperless et le dossier surveillé dans son .env, retire les anciennes lignes EVA_MAJORDOME_*.
#  3. Donne au dossier de dépôt les droits d'EVA (utilisateur 1000), pour qu'elle puisse ranger les fichiers envoyés.
#  4. Reconstruit EVA (cœur, interface, voix).
set -euo pipefail
cd "$(dirname "$0")"
MAJ=${1:-/home/eva/majordome}
DOCKER=${DOCKER:-docker}                     # DOCKER=echo pour un essai à blanc

V="\e[32m✔\e[0m"; J="\e[33m•\e[0m"; R="\e[31m✘\e[0m"
ok() { echo -e "$V $*"; }; info() { echo -e "$J $*"; }; die() { echo -e "$R $*" >&2; exit 1; }

[[ -f docker-compose.yml && -d eva-core ]] || die "Lance ce script depuis le dossier d'EVA."
[[ -f "$MAJ/.env" ]] || die "Pas de .env dans $MAJ : indique le dossier du majordome en argument."
[[ -f paperless/docker-compose.yml ]] || die "paperless/docker-compose.yml manquant (mise à jour d'EVA incomplète)."

lire() { grep -E "^$1=" "$MAJ/.env" | tail -1 | cut -d= -f2-; }
DATA_ROOT=$(lire DATA_ROOT); CONSUME_DIR=$(lire CONSUME_DIR); TOKEN=$(lire PAPERLESS_TOKEN)
PORT=$(lire PAPERLESS_PORT); PORT=${PORT:-8000}; IP=$(lire IP_PUBLIQUE); IP=${IP:-$(hostname -I | awk '{print $1}')}
[[ -n "$DATA_ROOT" && -n "$TOKEN" ]] || die "DATA_ROOT ou PAPERLESS_TOKEN absent de $MAJ/.env."

# ---------------------------------------------------------------- 1. Paperless seul
if ! grep -q "Paperless-ngx pour EVA" "$MAJ/docker-compose.yml" 2>/dev/null; then
  cp "$MAJ/docker-compose.yml" "$MAJ/docker-compose.yml.avant-eva"
  info "Ancien docker-compose du majordome gardé : $MAJ/docker-compose.yml.avant-eva"
fi
cp paperless/docker-compose.yml "$MAJ/docker-compose.yml"
mkdir -p "$DATA_ROOT/consume"
PUID=$(lire PUID); PGID=$(lire PGID)
chown "${PUID:-1000}:${PGID:-100}" "$DATA_ROOT/consume" 2>/dev/null || true
(cd "$MAJ" && $DOCKER compose up -d --remove-orphans)
ok "Paperless relancé seul (port $PORT), conteneurs majordome et ntfy retirés"

# ---------------------------------------------------------------- 2. .env d'EVA
touch .env
cp .env ".env.avant-papiers"
sed -i '/^EVA_MAJORDOME_URL=/d;/^EVA_MAJORDOME_KEY=/d' .env
env_set() { if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi; }
RACINE=/home/eva
DOSSIER=""
if [[ -n "$CONSUME_DIR" && "$CONSUME_DIR" == "$RACINE"/* ]]; then DOSSIER=${CONSUME_DIR#"$RACINE"/}; fi
env_set EVA_PAPERLESS_URL "http://host.docker.internal:$PORT"
env_set EVA_PAPERLESS_PUBLIC_URL "http://$IP:$PORT"
env_set EVA_PAPERLESS_TOKEN "$TOKEN"
env_set EVA_PAPIERS_RACINE_NAS "$RACINE"
[[ -n "$DOSSIER" ]] && env_set EVA_PAPIERS_DOSSIERS "$DOSSIER"
ok "EVA connaît Paperless (sauvegarde de l'ancien .env : .env.avant-papiers)"
[[ -n "$DOSSIER" ]] && ok "Dossier surveillé par EVA : $RACINE/$DOSSIER" \
  || info "Dossier de dépôt hors de $RACINE : choisis les dossiers surveillés dans la page Papiers › Réglages"

# ---------------------------------------------------------------- 3. droits du dossier de dépôt
if [[ -n "$CONSUME_DIR" && -d "$CONSUME_DIR" ]]; then
  chown -R 1000:1000 "$CONSUME_DIR" && ok "Dossier de dépôt accessible à EVA"
fi

# ---------------------------------------------------------------- 4. EVA
rm -f eva-core/app/papiers.py               # ancien client du majordome, remplacé par le dossier eva-core/app/papiers/
$DOCKER compose up -d --build eva-core eva-interface eva-voice
ok "EVA reconstruite"

cat <<EOF

  Terminé. Ouvre EVA, menu « Papiers » :
   - l'onglet Réglages doit afficher « Paperless : ok · Ollama : ok · modèle : trouvé » (bouton Tester) ;
   - tes documents déjà dans Paperless vont être analysés (3 par passage, un passage par minute) : l'avancement s'affiche en haut.
  Paperless reste accessible sur http://$IP:$PORT
  En cas de souci : cp .env.avant-papiers .env  et  cp $MAJ/docker-compose.yml.avant-eva $MAJ/docker-compose.yml
EOF
