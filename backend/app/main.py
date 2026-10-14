from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.db import init_db
from app.phase2_embeddings.vectorstore import ensure_collection
from app.phase3_rag.routes import router as tutor_router

from fastapi import Request
from fastapi.responses import JSONResponse
from app.phase1_llm.llm import LLMError
from app.phase4_exam.routes import router as exam_router
from app.phase7_flashcards.routes import router as flashcards_router
from app.phase8_personal.auth_routes import router as auth_router
from app.phase8_personal.conversation_routes import router as conversations_router
from app.phase8_personal.exam_history import router as exam_history_router
from app.phase8_personal.flashcard_history import router as flashcard_history_router
from app.phase8_personal.profile import router as profile_router
from app.phase5_evaluation.routes import router as stats_router
from app.phase9_summaries.routes import router as summaries_router
from app.phase6_agent.routes import router as companion_router
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # crée les tables SQLite (comptes, conversations, historiques) si besoin
    ensure_collection()  # crée la collection Qdrant au démarrage si besoin
    yield


app = FastAPI(title="AI Study Assistant", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],  # frontend Angular
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Questions-Generated", "X-Questions-Expected", "X-Exam-Total", "X-Exam-Id"],
)

app.include_router(auth_router)
app.include_router(tutor_router)
app.include_router(exam_router)
app.include_router(flashcards_router)
app.include_router(conversations_router)
app.include_router(exam_history_router)
app.include_router(flashcard_history_router)
app.include_router(profile_router)
app.include_router(stats_router)
app.include_router(summaries_router)
app.include_router(companion_router)
@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError):
    """Toute erreur du LLM devient une réponse 503 avec un message clair pour le frontend."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})

# Messages en français pour les champs des comptes étudiants (Pydantic répond en anglais)
FIELD_MESSAGES = {
    "email": "Adresse email invalide.",
    "level": "Niveau invalide : choisis débutant, intermédiaire ou avancé.",
}


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Erreurs de validation (422) : même format que FastAPI, sans le préfixe anglais « Value error, »."""
    errors = jsonable_encoder(exc.errors())
    for error in errors:
        field = error.get("loc", [None])[-1]
        if field in FIELD_MESSAGES and error.get("type") != "missing":
            error["msg"] = FIELD_MESSAGES[field]
        elif isinstance(error.get("msg"), str):
            error["msg"] = error["msg"].removeprefix("Value error, ")
    return JSONResponse(status_code=422, content={"detail": errors})

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}