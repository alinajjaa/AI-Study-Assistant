from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session

from app.core.db import get_session

from app.phase4_exam.generator import generate_exam
from app.phase4_exam.pdf import render_exam_pdf
from app.phase4_exam.schemas import ExamRequest
from app.phase5_evaluation.stats import GenerationStats
from app.phase5_evaluation.tracking import exam_run, log_run_async
from app.phase8_personal.courses import require_course
from app.phase8_personal.deps import get_current_user
from app.phase8_personal.exam_history import exam_filename, save_exam
from app.phase8_personal.models import User

router = APIRouter(prefix="/api", tags=["Exam Generator"])


@router.post("/courses/{course}/exam")
def create_exam(course: str, body: ExamRequest, user: User = Depends(get_current_user),
                session: Session = Depends(get_session)):
    """Génère un examen noté sur 20 (complet ou QCM rapide), l'enregistre dans l'historique et renvoie le PDF."""
    require_course(session, user.id, course)
    stats = GenerationStats()  # mesure (MLflow, expérience « exam ») : ne change pas la génération
    run = {"course": course, "fmt": body.format, "difficulty": body.difficulty, "num_questions": body.num_questions}
    try:
        exam = generate_exam(course, body.format, body.num_questions, body.difficulty, user_id=user.id, stats=stats)
    except Exception as e:
        log_run_async("exam", *exam_run(stats, **run, error=e))
        if isinstance(e, LookupError):
            raise HTTPException(404, str(e)) from e
        if isinstance(e, ValueError):
            raise HTTPException(422, str(e)) from e
        raise  # Les erreurs du LLM (LLMError) sont transformées en 503 par le gestionnaire global de main.py
    log_run_async("exam", *exam_run(stats, **run, exam=exam))

    pdf = render_exam_pdf(exam, include_answers=body.include_answers)
    filename = exam_filename(course, body.format, body.difficulty)
    record = save_exam(session, user.id, course, body.format, body.difficulty,
                       exam.question_count, body.include_answers, pdf)

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Questions-Generated": str(exam.question_count),
            "X-Questions-Expected": str(exam.expected_questions),
            "X-Exam-Total": f"{exam.total_points:g}",
            "X-Exam-Id": str(record.id),
        },
    )