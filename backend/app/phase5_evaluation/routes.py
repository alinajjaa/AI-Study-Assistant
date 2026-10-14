from fastapi import APIRouter, Depends

from app.phase5_evaluation.tracking import summarize
from app.phase8_personal.deps import get_current_user
from app.phase8_personal.models import User

router = APIRouter(prefix="/api", tags=["Évaluation"])


@router.get("/stats")
def read_stats(user: User = Depends(get_current_user)) -> dict:
    """Statistiques des générations (MLflow), pour une future page « Statistiques ».

    Moyennes globales de tous les runs : les runs MLflow ne contiennent aucun identifiant d'étudiant,
    ils ne peuvent donc pas être filtrés par compte.
    """
    return summarize()
