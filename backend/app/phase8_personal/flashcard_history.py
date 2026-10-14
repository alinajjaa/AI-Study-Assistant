"""Paquets de flashcards enregistrés (FlashcardDeck) et révisions « Je savais » / « À revoir » (Review)."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlmodel import Session, col, select, update

from app.core.db import get_session
from app.phase7_flashcards.schemas import Flashcard
from app.phase7_flashcards.schemas import FlashcardDeck as GeneratedDeck
from app.phase8_personal.deps import get_current_user
from app.phase8_personal.models import FlashcardDeck, Review, User

router = APIRouter(prefix="/api", tags=["Flashcards enregistrées"])


class DeckSummary(BaseModel):
    id: int
    course: str
    card_count: int
    created_at: datetime


class DeckOut(BaseModel):
    """Paquet complet. deck_id est répété pour la réponse de génération (POST …/flashcards)."""

    id: int
    deck_id: int
    course: str
    cards: list[Flashcard]
    created_at: datetime


class ReviewRequest(BaseModel):
    deck_id: int
    concept: str
    known: bool

    @field_validator("concept")
    @classmethod
    def clean_concept(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le concept est vide.")
        return value


class ReviewOut(BaseModel):
    id: int
    deck_id: int | None
    course: str
    concept: str
    known: bool
    created_at: datetime


def deck_out(deck: FlashcardDeck) -> DeckOut:
    return DeckOut(id=deck.id, deck_id=deck.id, course=deck.course, cards=deck.cards, created_at=deck.created_at)


def save_deck(session: Session, user_id: int, generated: GeneratedDeck) -> FlashcardDeck:
    deck = FlashcardDeck(user_id=user_id, course=generated.course,
                         cards=[card.model_dump() for card in generated.cards])
    session.add(deck)
    session.commit()
    session.refresh(deck)
    return deck


def get_owned_deck(deck_id: int, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)) -> FlashcardDeck:
    deck = session.get(FlashcardDeck, deck_id)
    if deck is None or deck.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paquet de flashcards introuvable.")
    return deck


@router.get("/flashcards/decks")
def list_decks(course: str | None = None, user: User = Depends(get_current_user),
               session: Session = Depends(get_session)) -> list[DeckSummary]:
    """Paquets de l'étudiant (éventuellement d'un seul cours), le plus récent en premier."""
    query = select(FlashcardDeck).where(FlashcardDeck.user_id == user.id)
    if course is not None:
        query = query.where(FlashcardDeck.course == course)
    rows = session.exec(query.order_by(col(FlashcardDeck.created_at).desc(), col(FlashcardDeck.id).desc()))
    return [DeckSummary(id=d.id, course=d.course, card_count=len(d.cards), created_at=d.created_at) for d in rows]


@router.get("/flashcards/decks/{deck_id}")
def read_deck(deck: FlashcardDeck = Depends(get_owned_deck)) -> DeckOut:
    return deck_out(deck)


@router.delete("/flashcards/decks/{deck_id}")
def delete_deck(deck: FlashcardDeck = Depends(get_owned_deck), session: Session = Depends(get_session)):
    """Supprime le paquet. Ses révisions restent dans les statistiques du profil (deck_id → None)."""
    session.exec(update(Review).where(Review.deck_id == deck.id).values(deck_id=None))
    session.delete(deck)
    session.commit()
    return {"deleted": deck.id}


@router.post("/reviews", status_code=status.HTTP_201_CREATED)
def create_review(body: ReviewRequest, user: User = Depends(get_current_user),
                  session: Session = Depends(get_session)) -> ReviewOut:
    """Enregistre une réponse « Je savais » (known=true) ou « À revoir » (known=false) sur une carte."""
    deck = get_owned_deck(body.deck_id, user, session)
    concepts = {card["concept"] for card in deck.cards}
    if body.concept not in concepts:
        raise HTTPException(422, "Ce concept ne fait pas partie du paquet.")
    review = Review(user_id=user.id, deck_id=deck.id, course=deck.course, concept=body.concept, known=body.known)
    session.add(review)
    session.commit()
    session.refresh(review)
    return ReviewOut.model_validate(review, from_attributes=True)
