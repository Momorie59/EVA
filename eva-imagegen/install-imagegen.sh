#!/usr/bin/env bash
# Installe le serveur d'images d'EVA (eva-imagegen) sur le SERVEUR IA, dans le même esprit que ia-local-automatique :
#   Docker en réseau hôte (comme Open WebUI), service systemd (Docker → Ollama → eva-imagegen), règle ufw limitée au réseau local,
#   modèles rangés sur ton disque de données. N'efface ni ne modifie rien d'existant (Ollama, Open WebUI, Qdrant, dashboard).
#
#   sudo bash install-imagegen.sh              installe / met à jour
#   sudo bash install-imagegen.sh --status     état
#   sudo bash install-imagegen.sh --uninstall  retire le conteneur et le service (les modèles téléchargés restent)
#   Options : --model ID  --port N  --data-dir CHEMIN  --video (vidéo IA expérimentale, lente sur 6 Go)  --dry-run (affiche sans rien faire)  --yes (sans questions)
set -u
NAME="eva-imagegen"; IMG="eva-imagegen:latest"
MODEL="stabilityai/sd-turbo"; PORT="7860"; DATA_DIR=""; DRY=0; YES=0; ACTION="install"; VIDEO=0
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_CFG="${IA_CONFIG_FILE:-/var/lib/ia-installer/config.env}"
UNIT="${EVA_UNIT_PATH:-/etc/systemd/system/${NAME}.service}"

while [ $# -gt 0 ]; do
  case "$1" in
    --model) MODEL="$2"; shift 2 ;; --port) PORT="$2"; shift 2 ;; --data-dir) DATA_DIR="$2"; shift 2 ;;
    --video) VIDEO=1; shift ;; --dry-run) DRY=1; shift ;; --yes|-y) YES=1; shift ;; --status) ACTION="status"; shift ;; --uninstall) ACTION="uninstall"; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1"; exit 2 ;;
  esac
done

ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m⚠\033[0m %s\n' "$*"; }
nok()  { printf '  \033[31m✘\033[0m %s\n' "$*"; }
step() { printf '\n\033[1m%s\033[0m\n' "$*"; }
run()  { if [ "$DRY" = 1 ]; then echo "  [dry-run] $*"; else "$@"; fi; }
ask()  { [ "$YES" = 1 ] && return 0; local r; read -r -p "  $1 [o/N] " r; [[ "$r" =~ ^[oOyY] ]]; }

[[ "$PORT" =~ ^[0-9]{2,5}$ ]] && [ "$PORT" -ge 1024 ] && [ "$PORT" -le 65535 ] || { nok "Port invalide : $PORT"; exit 2; }
[[ "$MODEL" =~ ^[A-Za-z0-9._/-]+$ ]] || { nok "Nom de modèle invalide."; exit 2; }
if [ "$DRY" = 0 ] && [ "$(id -u)" -ne 0 ]; then nok "À lancer avec sudo (root)."; exit 1; fi

# ── Où ranger les modèles : à côté des données d'Open WebUI (disque de données de ia-local-automatique), sinon /var/lib
default_data_dir() {
  local w=""
  if [ -r "$STATE_CFG" ]; then
    w="$(sed -n 's/^CFG\[webui_dir\]=//p' "$STATE_CFG" | tail -1 | tr -d "\"'")"
  fi
  if [ -n "$w" ] && [ -d "$(dirname "$w")" ]; then echo "$(dirname "$w")/eva-imagegen"; else echo "/var/lib/eva-imagegen"; fi
}
[ -z "$DATA_DIR" ] && DATA_DIR="$(default_data_dir)"

lan_ip()   { ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' | head -1; }
lan_cidr() { local ip dev; ip="$(lan_ip)"; [ -z "$ip" ] && return; ip -4 -o addr show 2>/dev/null | awk -v ip="$ip" '{split($4,a,"/"); if (a[1]==ip) print $4}' | head -1 | python3 -c "import sys,ipaddress
l=sys.stdin.read().strip()
print(ipaddress.ip_interface(l).network if l else '')" 2>/dev/null; }

status() {
  step "État d'eva-imagegen"
  if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${NAME}\$"; then ok "Conteneur actif"; else nok "Conteneur arrêté ou absent"; fi
  local p; p="$(docker inspect "$NAME" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | sed -n 's/^IMAGEGEN_PORT=//p')"; p="${p:-$PORT}"
  if curl -sf --max-time 4 "http://127.0.0.1:${p}/health" >/dev/null 2>&1; then ok "API : http://$(lan_ip):${p}/health répond"; curl -s "http://127.0.0.1:${p}/health" | head -c 400; echo; else nok "L'API ne répond pas sur le port ${p}"; fi
  systemctl is-enabled "${NAME}.service" >/dev/null 2>&1 && ok "Démarrage au boot : activé" || warn "Service systemd absent ou non activé"
}

uninstall() {
  step "Désinstallation d'eva-imagegen"
  if systemctl list-unit-files 2>/dev/null | grep -q "^${NAME}.service"; then run systemctl disable --now "${NAME}.service" 2>/dev/null; fi
  run rm -f "$UNIT"; run systemctl daemon-reload
  run docker rm -f "$NAME" 2>/dev/null
  if command -v ufw >/dev/null 2>&1; then          # retire nos règles (repérées par leur commentaire), de la dernière à la première
    local n; for n in $(ufw status numbered 2>/dev/null | grep "EVA imagegen" | sed -n 's/^\[ *\([0-9]*\)\].*/\1/p' | sort -rn); do run ufw --force delete "$n" >/dev/null 2>&1; done
  fi
  ok "Retiré. Les modèles téléchargés restent dans ${DATA_DIR} (supprime ce dossier pour récupérer la place)."
}

check_prereqs() {
  step "1/5 Vérifications"
  command -v docker >/dev/null 2>&1 || { nok "Docker est absent. Installe-le (ton installateur ia-local-automatique le propose) puis relance."; exit 1; }
  docker info >/dev/null 2>&1 || { nok "Le service Docker ne répond pas (systemctl start docker)."; exit 1; }
  ok "Docker disponible"
  if curl -sf --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then ok "Ollama répond (127.0.0.1:11434) : sa mémoire vidéo sera libérée avant chaque image"; else warn "Ollama ne répond pas en local : les images fonctionneront, mais sans libération automatique de la carte."; fi
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    local drv; drv="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)"
    ok "Carte NVIDIA : $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1) (pilote ${drv})"
    local major="${drv%%.*}"; if [[ "$major" =~ ^[0-9]+$ ]] && [ "$major" -lt 525 ]; then nok "Pilote NVIDIA ${drv} trop ancien pour CUDA 12.1 (≥ 525 requis) : mets-le à jour avec ton installateur."; exit 1; fi
    GPU=1
  else
    warn "Aucune carte NVIDIA utilisable : le serveur tournera sur le processeur (très lent)."; GPU=0
  fi
  if [ "${GPU:-0}" = 1 ]; then
    if command -v nvidia-ctk >/dev/null 2>&1 && docker info 2>/dev/null | grep -qi 'nvidia'; then ok "Runtime NVIDIA de Docker présent"
    else
      warn "Le NVIDIA Container Toolkit n'est pas configuré pour Docker."
      if command -v apt-get >/dev/null 2>&1 && ask "L'installer maintenant (dépôt officiel NVIDIA, comme ton installateur) ?"; then install_toolkit_apt
      else nok "Sans lui Docker ne voit pas la carte. Relance l'installateur ia-local-automatique (étape drivers/Docker GPU) puis ce script."; [ "$DRY" = 1 ] || exit 1; fi
    fi
  fi
  local free; free="$(df -BG --output=avail "$(dirname "$DATA_DIR")" 2>/dev/null | tail -1 | tr -dc 0-9)"
  if [ -n "$free" ] && [ "$free" -lt 8 ]; then nok "Moins de 8 Go libres sur $(dirname "$DATA_DIR") (image Docker ≈ 6 Go + modèle ≈ 2 Go)."; exit 1; fi
  ok "Place suffisante"
}

install_toolkit_apt() {
  run bash -c 'curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg && chmod 644 /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg'
  run bash -c 'curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed "s#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g" > /etc/apt/sources.list.d/nvidia-container-toolkit.list && chmod 644 /etc/apt/sources.list.d/nvidia-container-toolkit.list'
  run apt-get update -qq
  run apt-get install -y nvidia-container-toolkit
  run nvidia-ctk runtime configure --runtime=docker
  run systemctl restart docker
}

build_image() {
  step "2/5 Construction de l'image (la 1re fois : 10 à 20 minutes, ≈ 6 Go)"
  [ -f "$HERE/Dockerfile" ] || { nok "Dockerfile introuvable à côté du script ($HERE)."; exit 1; }
  run docker build -t "$IMG" "$HERE" || { nok "La construction a échoué."; exit 1; }
}

# Vérifie que Docker donne vraiment la carte à un conteneur (sinon tout tournerait sur le processeur)
gpu_check() {
  [ "${GPU:-0}" = 1 ] && [ "$DRY" != 1 ] || return 0
  if docker run --rm --gpus all --entrypoint nvidia-smi "$IMG" -L >/dev/null 2>&1; then ok "Docker donne bien la carte aux conteneurs"
  else nok "Docker ne donne pas la carte aux conteneurs. Installe/configure le toolkit : sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker, puis relance ce script."; exit 1; fi
}

run_container() {
  step "4/5 Démarrage"
  run mkdir -p "$DATA_DIR/models"
  # Jeton du serveur : indispensable pour que EVA puisse le mettre à jour et lui faire télécharger des modèles. Conservé d'une installation à l'autre.
  local tok="${IMAGEGEN_TOKEN:-}"
  [ -z "$tok" ] && tok="$(docker inspect "$NAME" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | sed -n 's/^IMAGEGEN_TOKEN=//p' | head -1)"
  [ -z "$tok" ] && [ -r "$DATA_DIR/.token" ] && tok="$(head -1 "$DATA_DIR/.token")"
  [ -z "$tok" ] && tok="$(python3 -c 'import secrets;print(secrets.token_hex(16))' 2>/dev/null || head -c16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  TOKEN_VALUE="$tok"
  if [ "$DRY" != 1 ]; then ( umask 077; printf '%s\n' "$tok" > "$DATA_DIR/.token" ); fi
  run docker rm -f "$NAME" >/dev/null 2>&1
  local gpu_flag=""; [ "${GPU:-0}" = 1 ] && gpu_flag="--gpus all"
  local token_env=(-e "IMAGEGEN_TOKEN=${tok}") hf_env=()
  [ -n "${HF_TOKEN:-}" ] && hf_env=(-e "HF_TOKEN=${HF_TOKEN}")
  # shellcheck disable=SC2086
  run docker run -d --name "$NAME" --restart unless-stopped --network host $gpu_flag \
    -e IMAGEGEN_PORT="$PORT" -e IMAGEGEN_MODEL="$MODEL" -e IMAGEGEN_VIDEO="$VIDEO" -e IMAGEGEN_IDLE_UNLOAD=90 -e IMAGEGEN_OLLAMA_URL=http://127.0.0.1:11434 \
    "${token_env[@]}" "${hf_env[@]}" -v "$DATA_DIR/models:/models" "$IMG" || { nok "Le démarrage a échoué (docker logs $NAME)."; exit 1; }
  ok "Conteneur lancé (modèles dans $DATA_DIR/models)"
  gpu_verify
}

# Un « systemctl daemon-reload » juste après le lancement peut retirer la carte au conteneur : on contrôle et on redémarre au besoin
gpu_verify() {
  [ "${GPU:-0}" = 1 ] && [ "$DRY" != 1 ] || return 0
  sleep 3
  if ! docker exec "$NAME" nvidia-smi -L >/dev/null 2>&1; then
    warn "Le conteneur ne voit pas la carte : redémarrage du conteneur"
    docker restart "$NAME" >/dev/null 2>&1; sleep 4
    if docker exec "$NAME" nvidia-smi -L >/dev/null 2>&1; then ok "Carte visible dans le conteneur"; else nok "Le conteneur ne voit toujours pas la carte (docker logs $NAME)."; fi
  else ok "Carte visible dans le conteneur"; fi
}

systemd_unit() {
  step "3/5 Démarrage automatique"
  if ! command -v systemctl >/dev/null 2>&1; then warn "Pas de systemd : le conteneur redémarre seul (--restart unless-stopped)."; return; fi
  if [ "$DRY" = 1 ]; then echo "  [dry-run] écrirait $UNIT"; return; fi
  cat > "$UNIT" <<UEOF
[Unit]
Description=EVA imagegen — génération d'images locale
After=docker.service ollama.service network-online.target
Requires=docker.service
Wants=ollama.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash -c 'docker start ${NAME} 2>/dev/null || { echo "[${NAME}] conteneur absent : relance install-imagegen.sh"; exit 1; }'
ExecStop=/usr/bin/docker stop ${NAME}
Restart=on-failure
RestartSec=10
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
UEOF
  systemctl daemon-reload && systemctl enable "${NAME}.service" >/dev/null 2>&1 && ok "Service ${NAME}.service activé au boot (après Docker et Ollama)"
}

firewall() {
  step "5/5 Pare-feu"
  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "active"; then
    local cidr; cidr="$(lan_cidr)"
    if [ -n "$cidr" ]; then run ufw allow from "$cidr" to any port "$PORT" proto tcp comment "EVA imagegen" >/dev/null && ok "ufw : port ${PORT} ouvert au réseau local seulement (${cidr})"
    else run ufw allow "${PORT}/tcp" comment "EVA imagegen" >/dev/null && warn "ufw : port ${PORT} ouvert (réseau local non déterminé : restreins la règle si besoin)"; fi
  elif command -v firewall-cmd >/dev/null 2>&1; then
    run firewall-cmd --permanent --add-port="${PORT}/tcp" >/dev/null 2>&1; run firewall-cmd --reload >/dev/null 2>&1; ok "firewalld : port ${PORT}/tcp ouvert"
  else ok "Aucun pare-feu actif à configurer"; fi
}

case "$ACTION" in
  status) status; exit 0 ;;
  uninstall) uninstall; exit 0 ;;
esac
check_prereqs; build_image; gpu_check; systemd_unit; run_container; firewall
step "Terminé"
if [ "$DRY" != 1 ] && [ -n "${TOKEN_VALUE:-}" ]; then
  ok "Jeton du serveur (à coller UNE fois dans EVA : Paramètres › Génération d'images › Jeton) :"
  printf '      %s\n' "$TOKEN_VALUE"
  echo "      (relisible plus tard : sudo cat ${DATA_DIR}/.token)"
fi
ip="$(lan_ip)"; ok "Dans EVA : Paramètres › Génération d'images › « Détecter le serveur » (ou http://${ip:-<IP-du-serveur>}:${PORT})"
echo "  Le 1er dessin télécharge le modèle (≈ 2 Go) : compte une à deux minutes. Suivi : docker logs -f ${NAME}"
echo "  Open WebUI peut s'en servir aussi : Admin › Paramètres › Images › AUTOMATIC1111 → http://127.0.0.1:${PORT}"
