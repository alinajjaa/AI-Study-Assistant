from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import DATABASE_URL

# SQLite : FastAPI exécute les routes dans plusieurs threads, la connexion doit pouvoir être partagée
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)


def init_db() -> None:
    """Crée les tables manquantes (les tables existantes ne sont pas modifiées)."""
    import app.phase8_personal.models  # noqa: F401  (enregistre les tables dans SQLModel.metadata)

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """Dépendance FastAPI : une session par requête, fermée à la fin."""
    with Session(engine) as session:
        yield session
