from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, Field
from app.phase2_embeddings.ingest import ingest_pdf
from app.phase2_embeddings.vectorstore import list_courses, delete_course
from app.phase3_rag.rag import answer

router = APIRouter(prefix="/api", tags=["Course Tutor"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    course: str | None = None


@router.post("/upload")
def upload_course(file: UploadFile = File(...), course: str | None = Form(None)):
    """Upload d'un PDF : extraction, découpage et indexation dans Qdrant."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Seuls les fichiers PDF sont acceptés")

    name = (course or Path(file.filename).stem).strip()
    try:
        n = ingest_pdf(file.file.read(), name)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if n == 0:
        raise HTTPException(422, "Aucun texte extrait : le PDF est probablement scanné (images)")
    return {"course": name, "chunks": n}


@router.get("/courses")
def get_courses() -> list[str]:
    """Liste des cours indexés."""
    return list_courses()


@router.delete("/courses/{course}")
def remove_course(course: str):
    """Supprime un cours et tous ses chunks."""
    delete_course(course)
    return {"deleted": course}


@router.post("/ask")
def ask(body: AskRequest):
    """Question → réponse basée uniquement sur le cours, avec les pages sources."""
    return answer(body.question, body.course)