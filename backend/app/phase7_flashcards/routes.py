from fastapi import APIRouter, HTTPException

from app.phase7_flashcards.generator import generate_flashcards
from app.phase7_flashcards.schemas import FlashcardDeck, FlashcardRequest

router = APIRouter(tags=["flashcards"])


@router.post("/api/courses/{course}/flashcards", response_model=FlashcardDeck)
def create_flashcards(course: str, body: FlashcardRequest) -> FlashcardDeck:
    """Génère un paquet de flashcards (JSON) sur les concepts clés du cours.

    Les erreurs du LLM (Ollama arrêté, délai dépassé…) sont gérées par le handler global de main.py (503).
    """
    try:
        return generate_flashcards(course, body.count)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))