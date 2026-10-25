from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session
from app.core import config
from app.core.db import get_session
from app.phase2_embeddings.ingest import ingest_pdf
from app.phase2_embeddings.vectorstore import delete_course
from app.phase3_rag.rag import answer
from app.phase5_evaluation.tracking import track_tutor
from app.phase8_personal.courses import add_course, clean_course_name, list_user_courses, require_course
from app.phase8_personal.deps import get_current_user
from app.phase8_personal.models import User
from app.phase8_personal.profile import weak_points
from app.phase9_summaries.routes import invalidate_course_summaries

router = APIRouter(prefix="/api", tags=["Course Tutor"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    course: str | None = None


@router.post("/upload")
def upload_course(file: UploadFile = File(...), course: str | None = Form(None),
                  user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Upload d'un PDF : extraction, découpage et indexation dans Qdrant (cours privé de l'étudiant)."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Seuls les fichiers PDF sont acceptés")

    name = clean_course_name(course or Path(file.filename).stem)
    limit = int(config.MAX_UPLOAD_MB * 1024 * 1024)
    data = file.file.read(limit + 1)  # jamais plus que la limite en mémoire
    if len(data) > limit:
        raise HTTPException(413, f"Fichier trop volumineux : {config.MAX_UPLOAD_MB:g} Mo au maximum")
    try:
        n = ingest_pdf(data, name, user.id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    if n == 0:
        raise HTTPException(422, "Aucun texte extrait : le PDF est probablement scanné (images)")
    add_course(session, user.id, name)
    invalidate_course_summaries(session, user.id, name)  # le résumé en cache ne correspond plus
    return {"course": name, "chunks": n}


@router.get("/courses")
def get_courses(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[str]:
    """Liste des cours de l'étudiant."""
    return list_user_courses(session, user.id)


@router.delete("/courses/{course}")
def remove_course(course: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Supprime un cours de l'étudiant et tous ses chunks."""
    row = require_course(session, user.id, course)
    delete_course(course, user_id=user.id)
    session.delete(row)
    session.commit()
    return {"deleted": course}


@router.post("/ask")
def ask(body: AskRequest, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Question → réponse basée uniquement sur les cours de l'étudiant, adaptée à son niveau, avec les pages sources."""
    if body.course:
        require_course(session, user.id, body.course)
    weak = [p.concept for p in weak_points(session, user.id, body.course or None)]
    with track_tutor(course=body.course, level=user.level) as stats:
        return answer(body.question, body.course, user_id=user.id, level=user.level, weak_concepts=weak,
                      stats=stats)
