# Service facultatif : très gros modèles couche par couche. GPU NVIDIA si disponible (docker-compose.airllm.yml), sinon processeur.
FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime
WORKDIR /srv
# Modèles téléchargés gardés sur le volume /models (sinon perdus à chaque reconstruction du conteneur)
ENV HF_HOME=/models/hf
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
