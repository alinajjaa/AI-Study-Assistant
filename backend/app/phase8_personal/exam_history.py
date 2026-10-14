"""Historique des examens : PDF enregistrés dans STORAGE_DIR/exams/<uuid>.pdf et lignes ExamRecord."""
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.core import config
from app.core.db import get_session
from app.phase8_personal.deps import get_current_user
from app.phase8_personal.models import ExamRecord, User

router = APIRouter(prefix="/api/exams", tags=["Historique des examens"])

EXAMS_SUBDIR = "exams"


def exam_filename(course: str, fmt: str, difficulty: str) -> str:
    """Nom du fichier téléchargé, ex. examen_CNN_intro_qcm_moyen.pdf."""
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", course).strip("_") or "cours"
    return f"examen_{safe_name}_{fmt}_{difficulty}.pdf"


def _storage_root() -> Path:
    return Path(config.STORAGE_DIR).resolve()


def save_exam(session: Session, user_id: int, course: str, fmt: str, difficulty: str,
              question_count: int, include_answers: bool, pdf: bytes) -> ExamRecord:
    """Écrit le PDF sur le disque puis enregistre la ligne ExamRecord."""
    relative = f"{EXAMS_SUBDIR}/{uuid4()}.pdf"
    path = _storage_root() / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf)
    record = ExamRecord(user_id=user_id, course=course, format=fmt, difficulty=difficulty,
                        question_count=question_count, include_answers=include_answers, pdf_path=relative)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _pdf_file(record: ExamRecord) -> Path:
    """Chemin absolu du PDF, toujours à l'intérieur de STORAGE_DIR."""
    root = _storage_root()
    path = (root / record.pdf_path).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichier de l'examen introuvable.")
    return path


class ExamRecordOut(BaseModel):
    id: int
    course: str
    format: str
    difficulty: str
    question_count: int
    include_answers: bool
    created_at: datetime


def _out(record: ExamRecord) -> ExamRecordOut:
    return ExamRecordOut.model_validate(record, from_attributes=True)


def get_owned_exam(exam_id: int, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)) -> ExamRecord:
    record = session.get(ExamRecord, exam_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Examen introuvable.")
    return record


@router.get("")
def list_exams(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[ExamRecordOut]:
    """Examens de l'étudiant, le plus récent en premier."""
    rows = session.exec(select(ExamRecord).where(ExamRecord.user_id == user.id)
                        .order_by(col(ExamRecord.created_at).desc(), col(ExamRecord.id).desc()))
    return [_out(r) for r in rows]


@router.get("/{exam_id}/pdf")
def download_exam(record: ExamRecord = Depends(get_owned_exam)) -> FileResponse:
    path = _pdf_file(record)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Le fichier PDF de cet examen n'existe plus.")
    return FileResponse(path, media_type="application/pdf",
                        filename=exam_filename(record.course, record.format, record.difficulty))


@router.delete("/{exam_id}")
def delete_exam(record: ExamRecord = Depends(get_owned_exam), session: Session = Depends(get_session)):
    """Supprime la ligne et le fichier PDF."""
    path = _pdf_file(record)
    session.delete(record)
    session.commit()
    path.unlink(missing_ok=True)
    return {"deleted": record.id}
