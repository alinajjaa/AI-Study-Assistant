# Hugging Face Spaces (SDK Docker) : image unique, port 7860.
#   - étape 1 : build Angular de production ;
#   - étape 2 : backend FastAPI (torch CPU, modèle d'embeddings inclus) qui sert aussi le frontend ;
#   - Qdrant en mode intégré (qdrant-client path=), sans serveur séparé.
# Contexte de build : la racine du dépôt (backend/, frontend/, deploy/hf-space/). Dans le dépôt du Space, ce
# fichier est copié à la racine par prepare-space.ps1. Aucun secret dans l'image : GROQ_API_KEY et JWT_SECRET
# sont des secrets du Space, injectés au démarrage.

FROM node:24-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npx ng build --configuration production

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu \
 && grep -vE '^(torch|pywin32)==' requirements.txt > /tmp/requirements-docker.txt \
 && pip install -r /tmp/requirements-docker.txt \
 && rm /tmp/requirements-docker.txt

ARG EMBED_MODEL=intfloat/multilingual-e5-small
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBED_MODEL}')" \
 && chmod -R a+rX /opt/hf-cache

# Spaces exécute le conteneur avec l'utilisateur 1000
RUN useradd --create-home --uid 1000 user \
 && mkdir -p /app/data/storage /app/data/qdrant /app/data/mlruns \
 && chown -R user:user /app/data

COPY --chown=user:user backend/app ./app
COPY --chown=user:user deploy/hf-space/space_app.py ./space_app.py
COPY --from=frontend --chown=user:user /src/dist/frontend/browser ./static

USER user

# Valeurs par défaut, modifiables dans les « Variables » du Space (les secrets, eux, ne sont jamais ici)
ENV EMBED_MODEL=${EMBED_MODEL} \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    LLM_BASE_URL=https://api.groq.com/openai/v1 \
    LLM_MODEL=qwen/qwen3.8-27b \
    QDRANT_PATH=/app/data/qdrant \
    DATABASE_URL=sqlite:////app/data/study.db \
    STORAGE_DIR=/app/data/storage \
    MLFLOW_ENABLED=false \
    MLFLOW_TRACKING_URI=sqlite:////app/data/mlruns/mlflow.db \
    FRONTEND_DIR=/app/static

EXPOSE 7860

CMD ["uvicorn", "space_app:app", "--host", "0.0.0.0", "--port", "7860"]
