from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.phase2_embeddings.vectorstore import ensure_collection
from app.phase3_rag.routes import router as tutor_router

from fastapi import Request
from fastapi.responses import JSONResponse
from app.phase1_llm.llm import LLMError
from app.phase4_exam.routes import router as exam_router
from app.phase7_flashcards.routes import router as flashcards_router
@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_collection()  # crée la collection Qdrant au démarrage si besoin
    yield


app = FastAPI(title="AI Study Assistant", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],  # frontend Angular
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Questions-Generated", "X-Questions-Expected", "X-Exam-Total"],
)

app.include_router(tutor_router)
app.include_router(exam_router)
app.include_router(flashcards_router)
@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError):
    """Toute erreur du LLM devient une réponse 503 avec un message clair pour le frontend."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}