# Backend FastAPI : Python slim, torch CPU (embeddings uniquement), modèle d'embeddings inclus, utilisateur non root.
# Aucun secret dans l'image : la configuration (clés, JWT_SECRET…) est fournie au démarrage (env_file de compose).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

# torch en version CPU (la version CUDA pèse plusieurs Go et ne sert à rien ici), puis le reste des dépendances.
# pywin32 est réservé à Windows.
COPY requirements.txt .
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu \
 && grep -vE '^(torch|pywin32)==' requirements.txt > /tmp/requirements-docker.txt \
 && pip install -r /tmp/requirements-docker.txt \
 && rm /tmp/requirements-docker.txt

# Modèle d'embeddings téléchargé au build : démarrage rapide, aucun accès au Hub à l'exécution
ARG EMBED_MODEL=intfloat/multilingual-e5-small
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBED_MODEL}')" \
 && chmod -R a+rX /opt/hf-cache

# Utilisateur non root ; ses données (SQLite, PDF des examens, MLflow) sont dans /app/data (volumes)
RUN useradd --create-home --uid 1000 app \
 && mkdir -p /app/data/db /app/data/storage /app/data/mlruns \
 && chown -R app:app /app/data

COPY --chown=app:app app ./app

USER app

ENV EMBED_MODEL=${EMBED_MODEL} \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    DATABASE_URL=sqlite:////app/data/db/study.db \
    STORAGE_DIR=/app/data/storage \
    MLFLOW_TRACKING_URI=sqlite:////app/data/mlruns/mlflow.db

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
