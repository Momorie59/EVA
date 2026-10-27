#!/bin/sh
set -e

# Si le socket Docker est monté, aligne un groupe sur son GID pour que
# l'utilisateur non-root "eva" puisse l'utiliser (docker_ps, docker_logs,
# docker_restart...). Le GID du socket varie d'un hôte à l'autre (souvent
# le groupe "docker" du NAS), d'où cette détection au démarrage plutôt
# qu'un GID figé dans l'image.
if [ -S /var/run/docker.sock ]; then
    SOCK_GID=$(stat -L -c '%g' /var/run/docker.sock)
    if ! getent group "$SOCK_GID" >/dev/null 2>&1; then
        groupadd -g "$SOCK_GID" dockersock
    fi
    usermod -aG "$SOCK_GID" eva
fi

# Le volume du workspace peut avoir été créé par root au premier montage —
# s'assure que "eva" peut y écrire.
if [ -n "$EVA_WORKSPACE" ] && [ -d "$EVA_WORKSPACE" ]; then
    # seulement ce qui n'appartient pas déjà à eva : un chown -R systématique réécrit chaque fichier et ralentit le démarrage
    find "$EVA_WORKSPACE" ! -user eva -exec chown eva:eva {} + 2>/dev/null || true
fi

# Volume du code d'EVA (auto-modification validée) : même principe.
if [ -n "$EVA_SELF_DIR" ] && [ -d "$EVA_SELF_DIR" ]; then
    find "$EVA_SELF_DIR" ! -user eva -exec chown eva:eva {} + 2>/dev/null || true
fi

export HOME=/home/eva
exec setpriv --reuid=eva --regid=eva --init-groups "$@"
