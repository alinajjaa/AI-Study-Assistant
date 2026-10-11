import os
from dotenv import load_dotenv

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))  # secondes avant d'abandonner un appel au LLM
EMBED_MODEL = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = "courses"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
TOP_K = 3