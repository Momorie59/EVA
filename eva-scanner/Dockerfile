# Éclaireur réseau d'EVA : tourne dans le réseau de la machine (network_mode: host) pour voir ce qu'un conteneur ne voit pas :
# adresses MAC, diffusions UDP (appareils Tuya, WiZ, Yeelight, Kasa), mDNS/Bonjour, SSDP/UPnP. Il ne contrôle rien : il écoute.
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["python", "-m", "app.main"]
