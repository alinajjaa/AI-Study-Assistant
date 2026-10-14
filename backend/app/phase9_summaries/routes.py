from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, col, delete, select

from app.core.db import get_session
from app.phase5_evaluation.stats import GenerationStats
from app.phase5_evaluation.tracking import log_run_async, summary_run
from app.phase8_personal.courses import require_course
from app.phase8_personal.deps import get_current_user
from app.phase8_personal.models import User
from app.phase9_summaries.generator import generate_summary
from app.phase9_summaries.models import Summary
from app.phase9_summaries.schemas import SummaryListItem, SummaryOut, SummaryRequest

router = APIRouter(prefix="/api", tags=["Résumés de cours"])


def _out(summary: Summary, cached: bool = False) -> SummaryOut:
    return SummaryOut(id=summary.id, course=summary.course, mode=summary.mode, topic=summary.topic,
                      content=summary.content, created_at=summary.created_at, cached=cached)


def cached_course_summary(session: Session, user_id: int, course: str) -> Summary | None:
    return session.exec(
        select(Summary).where(Summary.user_id == user_id, Summary.course == course, Summary.mode == "course")
        .order_by(col(Summary.created_at).desc(), col(Summary.id).desc())
    ).first()


def invalidate_course_summaries(session: Session, user_id: int, course: str) -> None:
    """Cours réimporté : son résumé en cache ne correspond plus au contenu."""
    session.exec(delete(Summary).where(Summary.user_id == user_id, Summary.course == course,
                                       Summary.mode == "course"))
    session.commit()


def get_owned_summary(summary_id: int, user: User = Depends(get_current_user),
                      session: Session = Depends(get_session)) -> Summary:
    summary = session.get(Summary, summary_id)
    if summary is None or summary.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Résumé introuvable.")
    return summary


@router.post("/courses/{course}/summary")
def create_summary(course: str, body: SummaryRequest, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)) -> SummaryOut:
    """Résumé du cours entier (réutilisé s'il existe, sauf regenerate=true) ou explication d'un thème.

    Les erreurs du LLM (LLMError) sont transformées en 503 par le gestionnaire global de main.py.
    """
    require_course(session, user.id, course)
    if body.mode == "course" and not body.regenerate:
        cached = cached_course_summary(session, user.id, course)
        if cached is not None:
            return _out(cached, cached=True)

    stats = GenerationStats()  # mesure (MLflow, expérience « summary »)
    run = {"course": course, "mode": body.mode, "level": user.level}
    try:
        content = generate_summary(course, body.mode, body.topic, user_id=user.id, level=user.level, stats=stats)
    except Exception as e:
        log_run_async("summary", *summary_run(stats, **run, error=e))
        if isinstance(e, LookupError):
            raise HTTPException(404, str(e))
        if isinstance(e, ValueError):
            raise HTTPException(422, str(e))
        raise
    log_run_async("summary", *summary_run(stats, **run, content=content))

    if body.mode == "course":
        invalidate_course_summaries(session, user.id, course)  # un seul résumé du cours entier par cours
    summary = Summary(user_id=user.id, course=course, mode=body.mode, topic=body.topic,
                      content=content.model_dump())
    session.add(summary)
    session.commit()
    session.refresh(summary)
    return _out(summary)


@router.get("/summaries")
def list_summaries(course: str | None = None, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)) -> list[SummaryListItem]:
    """Résumés de l'étudiant (éventuellement d'un seul cours), le plus récent en premier."""
    query = select(Summary).where(Summary.user_id == user.id)
    if course is not None:
        query = query.where(Summary.course == course)
    rows = session.exec(query.order_by(col(Summary.created_at).desc(), col(Summary.id).desc()))
    return [SummaryListItem(id=s.id, course=s.course, mode=s.mode, topic=s.topic,
                            found=s.content.get("found", True), section_count=len(s.content.get("sections", [])),
                            created_at=s.created_at) for s in rows]


@router.get("/summaries/{summary_id}")
def read_summary(summary: Summary = Depends(get_owned_summary)) -> SummaryOut:
    return _out(summary)


@router.delete("/summaries/{summary_id}")
def delete_summary(summary: Summary = Depends(get_owned_summary), session: Session = Depends(get_session)):
    session.delete(summary)
    session.commit()
    return {"deleted": summary.id}
