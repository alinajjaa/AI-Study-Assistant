from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator

from app.phase8_personal.models import Level

PASSWORD_MIN, PASSWORD_MAX = 8, 72  # bcrypt ignore tout ce qui dépasse 72 octets


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    level: Level = "intermediaire"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        if len(value) < PASSWORD_MIN:
            raise ValueError(f"Le mot de passe doit contenir au moins {PASSWORD_MIN} caractères.")
        if len(value.encode("utf-8")) > PASSWORD_MAX:
            raise ValueError(f"Le mot de passe ne doit pas dépasser {PASSWORD_MAX} caractères.")
        return value


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserOut(BaseModel):
    id: int
    email: str
    level: Level
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UpdateMeRequest(BaseModel):
    level: Level


# ---------------------------------------------------------------------------
# Conversations du tuteur
# ---------------------------------------------------------------------------

TITLE_MAX = 120


class ConversationCreate(BaseModel):
    title: str | None = None
    course: str | None = None


class ConversationUpdate(BaseModel):
    title: str

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Le titre ne peut pas être vide.")
        if len(value) > TITLE_MAX:
            raise ValueError(f"Le titre ne doit pas dépasser {TITLE_MAX} caractères.")
        return value


class ConversationOut(BaseModel):
    id: int
    title: str
    course: str | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    course: str | None
    sources: list
    answered: bool
    kind: str = "text"  # text | answer | quiz | summary | flashcards | progress
    payload: dict | None = None  # données de l'affichage riche (Study Companion)
    created_at: datetime


class AskInConversation(BaseModel):
    question: str
    course: str | None = None

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("La question est vide.")
        return value


class ExchangeOut(BaseModel):
    """Réponse à une question : les deux messages enregistrés et la conversation mise à jour (titre, date)."""

    conversation: ConversationOut
    user_message: MessageOut
    assistant_message: MessageOut
