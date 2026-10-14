"""Tests sans services externes : SQLite temporaire, Qdrant en mémoire, embeddings et LLM simulés."""
import os
import tempfile
from pathlib import Path

# Variables lues par app.core.config : à définir AVANT tout import de l'application
# (load_dotenv n'écrase pas les variables déjà présentes).
_TMP = Path(tempfile.mkdtemp(prefix="study-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["JWT_SECRET"] = "secret-de-test-uniquement-0123456789abcdef"
os.environ["STORAGE_DIR"] = str(_TMP / "storage")
os.environ["MLFLOW_ENABLED"] = "false"  # activé seulement dans les tests MLflow
os.environ["MLFLOW_TRACKING_URI"] = f"sqlite:///{(_TMP / 'mlruns' / 'mlflow.db').as_posix()}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app.core.db import engine, init_db  # noqa: E402
from tests.helpers import DIM, FakeLLM, fake_vector  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    import shutil

    SQLModel.metadata.drop_all(engine)
    init_db()
    shutil.rmtree(os.environ["STORAGE_DIR"], ignore_errors=True)
    yield


@pytest.fixture(autouse=True)
def fake_services(monkeypatch):
    """Qdrant en mémoire et embeddings simulés : aucun modèle téléchargé, aucun serveur requis."""
    from app.phase2_embeddings import ingest, vectorstore
    from app.phase3_rag import rag

    monkeypatch.setattr(vectorstore, "client", QdrantClient(":memory:"))
    monkeypatch.setattr(vectorstore, "dimension", lambda: DIM)
    monkeypatch.setattr(ingest, "embed_passages", lambda texts: [fake_vector(t) for t in texts])
    monkeypatch.setattr(rag, "embed_query", fake_vector)
    vectorstore.ensure_collection()
    yield


@pytest.fixture
def llm(monkeypatch) -> FakeLLM:
    from app.phase3_rag import rag

    fake = FakeLLM()
    monkeypatch.setattr(rag, "chat", fake)
    return fake


@pytest.fixture
def session():
    with Session(engine) as s:
        yield s


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    return TestClient(app)  # sans « with » : le lifespan (vrai Qdrant) n'est pas lancé
