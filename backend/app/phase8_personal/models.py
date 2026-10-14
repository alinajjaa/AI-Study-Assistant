from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

Level = Literal["debutant", "intermediaire", "avance"]
LEVELS: tuple[Level, ...] = ("debutant", "intermediaire", "avance")


def utcnow() -> datetime:
    """Date UTC avec fuseau (SQLModel la relit en UTC, même depuis SQLite)."""
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=254)
    password_hash: str
    level: str = Field(default="intermediaire")  # Level
    # Dernier changement de niveau : la suggestion d'ajustement ne compte que les révisions faites depuis
    level_changed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Course(SQLModel, table=True):
    """Un cours importé par un étudiant (ses morceaux sont dans Qdrant, avec le même user_id)."""

    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str
    created_at: datetime = Field(default_factory=utcnow)


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    title: str = Field(default="Nouvelle conversation", max_length=120)
    course: str | None = None  # None = tous les cours
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversations.id", index=True)
    role: str  # "user" | "assistant"
    content: str
    course: str | None = None  # cours interrogé pour cette question (None = tous les cours)
    sources: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    answered: bool = True  # False si la réponse n'est pas dans le cours
    # Affichage riche (Study Companion) : text | answer | quiz | summary | flashcards | progress
    kind: str = Field(default="text")
    payload: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=utcnow)


MESSAGE_KINDS = ("text", "answer", "quiz", "summary", "flashcards", "progress")


class ExamRecord(SQLModel, table=True):
    __tablename__ = "exam_records"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    course: str
    format: str
    difficulty: str
    question_count: int
    include_answers: bool
    pdf_path: str  # chemin relatif à STORAGE_DIR
    created_at: datetime = Field(default_factory=utcnow)


class FlashcardDeck(SQLModel, table=True):
    __tablename__ = "flashcard_decks"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    course: str
    cards: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utcnow)


class Review(SQLModel, table=True):
    """Une réponse « Je savais » / « À revoir » sur une carte.

    deck_id passe à None si le paquet est supprimé : l'historique reste dans les statistiques du profil.
    """

    __tablename__ = "reviews"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    deck_id: int | None = Field(default=None, foreign_key="flashcard_decks.id")
    course: str
    concept: str
    known: bool
    created_at: datetime = Field(default_factory=utcnow)
