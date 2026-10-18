import os
import re
from dotenv import load_dotenv

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
# Windows : « localhost » se résout d'abord en ::1 (IPv6), alors qu'Ollama n'écoute que sur 127.0.0.1. Chaque
# nouvelle connexion attend alors ~2 s avant de passer en IPv4 (mesuré : 2,1 s), et un appel en streaming ne
# réutilise pas sa connexion : +2 s sur chaque réponse du tuteur. On vise donc directement 127.0.0.1.
# LLM_FORCE_IPV4=false désactive cette correction (Ollama joignable seulement en IPv6).
if os.getenv("LLM_FORCE_IPV4", "true").strip().lower() not in ("0", "false", "no", "non"):
    LLM_BASE_URL = re.sub(r"^(https?://)localhost(?=[:/]|$)", r"\g<1>127.0.0.1", LLM_BASE_URL)
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
# Groq : si LLM_BASE_URL pointe vers api.groq.com, la clé GROQ_API_KEY (si elle existe) est prioritaire.
# Un même fichier .env sert ainsi à Ollama en local et à Groq dans Docker (où seul LLM_BASE_URL change).
if "api.groq.com" in LLM_BASE_URL and os.getenv("GROQ_API_KEY"):
    LLM_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))  # secondes avant d'abandonner un appel au LLM
# Sorties JSON : "json_schema" (par défaut, repli automatique sur json_object si le modèle le refuse)
# ou "json_object" (forcé, pour un modèle sans sorties structurées) ; le code valide tout avec Pydantic.
LLM_JSON_MODE = os.getenv("LLM_JSON_MODE", "json_schema").strip().lower()
# Limites de débit (erreur 429, offre gratuite de Groq) : nombre de nouveaux essais et attente maximale
# acceptée pour un essai (au-delà, par exemple une limite quotidienne, on abandonne avec un message clair).
LLM_RATE_LIMIT_RETRIES = int(os.getenv("LLM_RATE_LIMIT_RETRIES", "4"))
LLM_RATE_LIMIT_MAX_WAIT = float(os.getenv("LLM_RATE_LIMIT_MAX_WAIT", "60"))
# Appels au LLM simultanés (sémaphore partagé par toute l'application). 1 = exécution séquentielle, identique au
# comportement historique : défaut pour Ollama en local (un GPU traite les requêtes une par une). 3 par défaut
# pour Groq (API distante, limitée en jetons par minute : au-delà, les attentes 429 annulent le gain).
_IS_GROQ = "api.groq.com" in LLM_BASE_URL
LLM_CONCURRENCY = max(1, int(os.getenv("LLM_CONCURRENCY", "").strip() or ("3" if _IS_GROQ else "1")))
# Ollama : durée pendant laquelle le modèle reste chargé en mémoire GPU après un appel (-1 = toujours, "30m"…).
# Envoyé seulement à Ollama (paramètre inconnu des autres API). Vide : réglage du serveur (OLLAMA_KEEP_ALIVE).
LLM_KEEP_ALIVE = os.getenv("LLM_KEEP_ALIVE", "-1").strip()
IS_OLLAMA = ":11434" in LLM_BASE_URL or "ollama" in LLM_BASE_URL.lower()
# Fournisseur : "openai" (API compatible OpenAI : Ollama, par défaut) ou "hf-local" (démonstration du
# modèle affiné en phase 4 : modèle de base + adaptateur LoRA chargés avec transformers, en 4 bits)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
HF_BASE_MODEL = os.getenv("HF_BASE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
HF_ADAPTER = os.getenv("HF_ADAPTER", "")  # dépôt du Hub (<utilisateur>/study-tutor-qwen2.5-1.5b-lora) ou dossier local
EMBED_MODEL = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
# Qdrant intégré (sans serveur, ex. Hugging Face Spaces) : dossier local ou ":memory:". Prioritaire sur QDRANT_URL.
QDRANT_PATH = os.getenv("QDRANT_PATH", "").strip()
COLLECTION = "courses"

# Origines autorisées à appeler l'API depuis un navigateur (séparées par des virgules). Inutile derrière nginx
# ou quand FastAPI sert le frontend (même origine).
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:4200").split(",") if o.strip()]

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
