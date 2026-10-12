import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.phase4_exam.generator import generate_exam
from app.phase4_exam.pdf import render_exam_pdf
from app.phase4_exam.schemas import ExamRequest

router = APIRouter(prefix="/api", tags=["Exam Generator"])


@router.post("/courses/{course}/exam")
def create_exam(course: str, body: ExamRequest):
    """Génère un examen noté sur 20 (complet ou QCM rapide) et le renvoie sous forme de PDF."""
    try:
        exam = generate_exam(course, body.format, body.num_questions, body.difficulty)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    # Les erreurs du LLM (LLMError) sont transformées en 503 par le gestionnaire global de main.py

    pdf = render_exam_pdf(exam, include_answers=body.include_answers)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", course).strip("_") or "cours"
    filename = f"examen_{safe_name}_{body.format}_{body.difficulty}.pdf"

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Questions-Generated": str(exam.question_count),
            "X-Questions-Expected": str(exam.expected_questions),
            "X-Exam-Total": f"{exam.total_points:g}",
        },
    )