from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.phase8_personal.models import utcnow


class Summary(SQLModel, table=True):
    """Résumé d'un cours (mode « course », mis en cache) ou explication d'un thème (mode « topic »)."""

    __tablename__ = "summaries"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    course: str
    mode: str  # "course" | "topic"
    topic: str | None = None
    content: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utcnow)
