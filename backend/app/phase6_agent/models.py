from datetime import datetime

from sqlmodel import Field, SQLModel

from app.phase8_personal.models import utcnow


class QuizResult(SQLModel, table=True):
    """Réponse à une question d'un quiz du Study Companion (correcte ou non).

    concept : notion testée par la question (sert aux points faibles du profil, comme les révisions de
    flashcards). message_id : message « quiz » d'origine (None si la conversation a été supprimée).
    """

    __tablename__ = "quiz_results"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    message_id: int | None = Field(default=None, index=True)
    course: str
    concept: str
    question: str
    correct: bool
    created_at: datetime = Field(default_factory=utcnow)
