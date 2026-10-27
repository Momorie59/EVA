#!/bin/sh
# Active ou désactive le HTTPS d'EVA.   Usage :  ./eva-https.sh off   |   ./eva-https.sh on   |   ./eva-https.sh status
# Le port reste le même (EVA_HTTPS_PORT, 8443 par défaut) ; seul le protocole change.
cd "$(dirname "$0")" || exit 1
touch .env
cur=$(grep -E '^EVA_CADDYFILE=' .env | tail -1 | cut -d= -f2)
case "$1" in
  domain)
    [ -n "$2" ] && [ -n "$3" ] || { echo "Usage : $0 domain <nom>.duckdns.org <jeton-duckdns>"; exit 1; }
    grep -v -E '^(EVA_CADDYFILE|EVA_DOMAIN|DUCKDNS_TOKEN|COMPOSE_FILE)=' .env > .env.tmp
    { echo "EVA_CADDYFILE=./caddy/Caddyfile.domain"; echo "EVA_DOMAIN=$2"; echo "DUCKDNS_TOKEN=$3"
      echo "COMPOSE_FILE=docker-compose.yml:docker-compose.override.yml:docker-compose.domain.yml"; } >> .env.tmp
    mv .env.tmp .env
    docker compose up -d --build --force-recreate caddy
    echo "Domaine : https://$2:$(grep -E '^EVA_HTTPS_PORT=' .env | tail -1 | cut -d= -f2 | grep . || echo 8443)/  (le certificat se prépare, compte 1 à 2 minutes)"
    exit 0 ;;
  off) new=./caddy/Caddyfile.http
       grep -v -E '^COMPOSE_FILE=' .env > .env.tmp; mv .env.tmp .env ;;
  on)  new=./caddy/Caddyfile
       grep -v -E '^COMPOSE_FILE=' .env > .env.tmp; mv .env.tmp .env ;;
  status|"")
    port=$(grep -E '^EVA_HTTPS_PORT=' .env | tail -1 | cut -d= -f2); port=${port:-8443}
    case "$cur" in *.domain) echo "HTTPS avec vrai certificat : https://$(grep -E '^EVA_DOMAIN=' .env | tail -1 | cut -d= -f2):$port/" ;; *.http) echo "HTTPS désactivé : http://<IP-du-NAS>:$port/" ;; *) echo "HTTPS activé : https://<IP-du-NAS>:$port/" ;; esac
    exit 0 ;;
  *) echo "Usage : $0 on|off|status|domain <nom> <jeton>"; exit 1 ;;
esac
grep -v -E '^EVA_CADDYFILE=' .env > .env.tmp; echo "EVA_CADDYFILE=$new" >> .env.tmp; mv .env.tmp .env
docker compose up -d --force-recreate caddy
sh "$0" status
