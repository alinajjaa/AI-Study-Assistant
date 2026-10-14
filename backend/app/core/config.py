import os
from dotenv import load_dotenv

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))  # secondes avant d'abandonner un appel au LLM
# Fournisseur : "openai" (API compatible OpenAI : Ollama, par défaut) ou "hf-local" (démonstration du
# modèle affiné en phase 4 : modèle de base + adaptateur LoRA chargés avec transformers, en 4 bits)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
HF_BASE_MODEL = os.getenv("HF_BASE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
HF_ADAPTER = os.getenv("HF_ADAPTER", "")  # dépôt du Hub (<utilisateur>/study-tutor-qwen2.5-1.5b-lora) ou dossier local
EMBED_MODEL = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = "courses"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
TOP_K = 3

# Comptes étudiants (phase 8)
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_EXPIRE_HOURS = float(os.getenv("JWT_EXPIRE_HOURS", "24"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./study.db")
STORAGE_DIR = os.getenv("STORAGE_DIR", "./storage")  # PDF des examens générés

# Évaluation (phase 5) : suivi des générations dans MLflow
MLFLOW_ENABLED = os.getenv("MLFLOW_ENABLED", "true").strip().lower() in ("1", "true", "yes", "oui")
# SQLite : le stockage « fichier » (file:./mlruns) est en mode maintenance depuis MLflow 3
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlruns/mlflow.db")
