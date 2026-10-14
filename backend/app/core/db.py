from collections.abc import Iterator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import DATABASE_URL

# SQLite : FastAPI exécute les routes dans plusieurs threads, la connexion doit pouvoir être partagée
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)


def init_db() -> None:
    """Crée les tables manquantes (les tables existantes ne sont pas modifiées)."""
    import app.phase8_personal.models  # noqa: F401  (enregistre les tables dans SQLModel.metadata)
    import app.phase9_summaries.models  # noqa: F401
    import app.phase6_agent.models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    migrate_messages()


def migrate_messages() -> None:
    """Migration douce : ajoute les colonnes kind et payload aux messages d'une base existante.

    create_all ne modifie pas une table déjà créée. Les anciens messages deviennent « text » (question de
    l'étudiant) ou « answer » (réponse du tuteur) ; leur contenu n'est pas modifié.
    """
    columns = {c["name"] for c in inspect(engine).get_columns("messages")}
    with engine.begin() as conn:
        if "kind" not in columns:
            conn.execute(text("ALTER TABLE messages ADD COLUMN kind VARCHAR NOT NULL DEFAULT 'text'"))
            conn.execute(text("UPDATE messages SET kind = 'answer' WHERE role = 'assistant'"))
        if "payload" not in columns:
            conn.execute(text("ALTER TABLE messages ADD COLUMN payload JSON"))


def get_session() -> Iterator[Session]:
    """Dépendance FastAPI : une session par requête, fermée à la fin."""
    with Session(engine) as session:
        yield session
