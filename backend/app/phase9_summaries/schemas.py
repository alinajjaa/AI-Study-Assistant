"""Formats imposés au LLM (sorties structurées) et format des résumés renvoyés au frontend.

Validation d'une puce : non vide, en français, avec au moins une référence [p.X] dont toutes les pages
font partie des passages fournis (passées par le contexte de validation : {"pages": {...}}).
"""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from app.phase4_exam.schemas import capitalize_first, check_french

SummaryMode = Literal["course", "topic"]

# [p.3], [p. 3], [p.3, 5], [p.3 ; p.5]
PAGE_REF = re.compile(r"\[\s*p\.\s*\d+(?:\s*[,;]\s*(?:p\.\s*)?\d+)*\s*\]", re.IGNORECASE)
SENTENCE_END = re.compile(r"[.!?…](?:\s|$)")


def page_refs(text: str) -> list[int]:
    """Numéros de page cités dans un texte, dans l'ordre."""
    return [int(n) for ref in PAGE_REF.findall(text) for n in re.findall(r"\d+", ref)]


def bullet_has_valid_pages(text: str, allowed: set[int]) -> bool:
    pages = page_refs(text)
    return bool(pages) and all(p in allowed for p in pages)


def check_bullet(value: str, info: ValidationInfo) -> str:
    # Restes de JSON parfois collés à la fin de la puce (« … [p.30]} »)
    value = capitalize_first(" ".join(value.split()).rstrip(" }\"'"))
    if len(PAGE_REF.sub("", value).strip(" .;-")) < 10:
        raise ValueError("puce vide")
    check_french(PAGE_REF.sub("", value))
    pages = page_refs(value)
    if not pages:
        raise ValueError("puce sans référence de page")
    allowed = (info.context or {}).get("pages")
    if allowed is not None and any(p not in allowed for p in pages):
        raise ValueError("page absente des passages fournis")
    return value


class SectionDraft(BaseModel):
    """Résumé d'une section du cours (étape « map »)."""

    title: str = Field(min_length=3, max_length=90)
    bullets: list[str] = Field(min_length=3, max_length=5)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return check_french(capitalize_first(value.strip(" .:-•")))

    @field_validator("bullets")
    @classmethod
    def clean_bullets(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return [check_bullet(v, info) for v in values]


class OverviewDraft(BaseModel):
    """Vue d'ensemble du cours (étape « reduce »)."""

    overview: str = Field(min_length=80, max_length=1500)

    @field_validator("overview")
    @classmethod
    def clean_overview(cls, value: str) -> str:
        value = capitalize_first(" ".join(value.split()))
        sentences = len(SENTENCE_END.findall(value + " "))
        if not 3 <= sentences <= 7:  # consigne : 4 à 6 phrases, avec une phrase de tolérance
            raise ValueError("la vue d'ensemble doit faire 4 à 6 phrases")
        check_french(PAGE_REF.sub("", value))
        return value


class TopicPart(BaseModel):
    title: str = Field(min_length=3, max_length=90)
    bullets: list[str] = Field(min_length=2, max_length=5)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return check_french(capitalize_first(value.strip(" .:-•")))

    @field_validator("bullets")
    @classmethod
    def clean_bullets(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return [check_bullet(v, info) for v in values]


class TopicDraft(BaseModel):
    """Explication d'un thème. found=false si le thème n'est pas dans les passages fournis."""

    found: bool
    introduction: str = Field(default="", max_length=800)
    parts: list[TopicPart] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def check_content(self):
        if self.found:
            if not self.parts:
                raise ValueError("explication vide")
            if len(self.introduction.strip()) < 20:
                raise ValueError("introduction manquante")
            check_french(PAGE_REF.sub("", self.introduction))
        return self


# ---------------------------------------------------------------------------
# Format renvoyé au frontend (et enregistré dans Summary.content)
# ---------------------------------------------------------------------------

class SummarySection(BaseModel):
    title: str
    pages: list[int]
    bullets: list[str]


class SummaryContent(BaseModel):
    found: bool = True
    overview: str
    sections: list[SummarySection]


class SummaryRequest(BaseModel):
    mode: SummaryMode = "course"
    topic: str | None = None
    regenerate: bool = False

    @model_validator(mode="after")
    def check_topic(self):
        if self.mode == "topic":
            topic = " ".join((self.topic or "").split())
            if len(topic) < 2:
                raise ValueError("Indique le thème à expliquer.")
            if len(topic) > 200:
                raise ValueError("Le thème ne doit pas dépasser 200 caractères.")
            self.topic = topic
        else:
            self.topic = None
        return self


class SummaryListItem(BaseModel):
    id: int
    course: str
    mode: SummaryMode
    topic: str | None
    found: bool
    section_count: int
    created_at: datetime


class SummaryOut(BaseModel):
    id: int
    course: str
    mode: SummaryMode
    topic: str | None
    content: SummaryContent
    created_at: datetime
    cached: bool = False  # True : résumé du cours entier déjà enregistré, renvoyé sans regénérer
