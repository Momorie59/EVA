# Serveur de génération d'images d'EVA (Stable Diffusion via diffusers). Pensé pour une carte de 6 Go (GTX 1060) :
# demi-précision, découpage de l'attention, chargement à la demande et déchargement au repos pour laisser la mémoire à Ollama.
# GPU : nécessite le NVIDIA Container Toolkit. Sans GPU, le même conteneur tourne sur le processeur (lent).
FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV HF_HOME=/models/hf PYTHONUNBUFFERED=1
ENV IMAGEGEN_PORT=7860
EXPOSE 7860
# Forme « shell » : le port se règle avec IMAGEGEN_PORT (le conteneur tourne en réseau hôte, comme Open WebUI).
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${IMAGEGEN_PORT}
