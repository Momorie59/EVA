FROM python:3.12-slim

WORKDIR /app

# git : requis par harness/tools/git_tools.py (appelle le binaire git directement)
# passwd/util-linux : usermod/groupadd/setpriv, utilisés par l'entrypoint pour
# tourner en non-root tout en gardant l'accès au socket Docker monté
# libchromaprint-tools : fpcalc, empreinte sonore pour reconnaître une musique (AcoustID)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        passwd \
        util-linux \
        libchromaprint-tools \
    && rm -rf /var/lib/apt/lists/*

# Utilisateur non-root — RLIMIT_NPROC (anti fork-bomb) de terminal_run n'a
# aucun effet réel tant qu'on tourne en root (CAP_SYS_RESOURCE l'exempte),
# vérifié pendant le développement. Le GID du groupe "docker" du socket
# monté est inconnu à la construction de l'image (il varie d'un NAS à
# l'autre) : c'est l'entrypoint qui l'aligne au démarrage, pas cette ligne.
RUN useradd --create-home --shell /bin/bash --uid 1000 eva

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ajouts récents dans des couches à part : une mise à jour ne refait pas les longues étapes ci-dessus.
# requirements-extra : Word, Excel, PowerPoint, PDF (sans paquet Debian : la police des PDF vient de reportlab).
COPY requirements-extra.txt .
RUN pip install --no-cache-dir -r requirements-extra.txt

COPY app ./app
COPY skills ./skills
COPY seed_docs ./seed_docs
COPY selfboot.py .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "/app/selfboot.py"]
