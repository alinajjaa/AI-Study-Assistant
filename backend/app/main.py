from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.phase2_embeddings.vectorstore import ensure_collection
from app.phase3_rag.routes import router as tutor_router


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
)

app.include_router(tutor_router)


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}