from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.phase8_personal.schemas import ConversationOut, MessageOut

MESSAGE_MAX = 2000


class CompanionRequest(BaseModel):
    conversation_id: int | None = None  # None : nouvelle conversation
    course: str | None = None  # cours sélectionné dans la page
    message: str

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le message est vide.")
        if len(value) > MESSAGE_MAX:
            raise ValueError(f"Le message ne doit pas dépasser {MESSAGE_MAX} caractères.")
        return value

    @field_validator("course")
    @classmethod
    def clean_course(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class CompanionExchange(BaseModel):
    """Messages enregistrés : la demande de l'étudiant et 1 à 3 réponses de l'assistant (une par outil)."""

    conversation: ConversationOut
    user_message: MessageOut
    assistant_messages: list[MessageOut]
    tools: list[str]
    fallback: bool


class JobOut(BaseModel):
    job_id: str
    status: Literal["running", "done", "error"]
    tool: str | None  # outil en cours ou terminé
    elapsed_s: float
    exchange: CompanionExchange | None = None
    error: str | None = None


Letter = Literal["A", "B", "C", "D"]


class QuizResultRequest(BaseModel):
    message_id: int  # message « quiz » de la conversation
    answers: list[Letter] = Field(min_length=1, max_length=20)  # lettre choisie pour chaque question, dans l'ordre

    @field_validator("answers", mode="before")
    @classmethod
    def upper(cls, values):
        return [v.strip().upper() if isinstance(v, str) else v for v in values] if isinstance(values, list) else values


class QuizResultOut(BaseModel):
    score: int
    total: int
    correct: list[bool]
    message: MessageOut
