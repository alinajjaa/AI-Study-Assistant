from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.db import get_session

from app.phase7_flashcards.generator import generate_flashcards
from app.phase7_flashcards.schemas import FlashcardRequest
from app.phase8_personal.courses import require_course
from app.phase8_personal.deps import get_current_user
from app.phase8_personal.flashcard_history import DeckOut, deck_out, save_deck
from app.phase8_personal.models import User

router = APIRouter(tags=["flashcards"])


@router.post("/api/courses/{course}/flashcards", response_model=DeckOut)
def create_flashcards(course: str, body: FlashcardRequest, user: User = Depends(get_current_user),
                      session: Session = Depends(get_session)) -> DeckOut:
    """Génère un paquet de flashcards (JSON) sur les concepts clés du cours et l'enregistre (deck_id).

    Les erreurs du LLM (Ollama arrêté, délai dépassé…) sont gérées par le handler global de main.py (503).
    """
    require_course(session, user.id, course)
    try:
        generated = generate_flashcards(course, body.count, user_id=user.id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return deck_out(save_deck(session, user.id, generated))
