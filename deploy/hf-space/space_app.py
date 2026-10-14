"""Point d'entrée Hugging Face Spaces : l'API FastAPI et le frontend Angular construit, sur un seul port (7860).

L'application (app.main) n'est pas modifiée : on lui ajoute seulement les fichiers statiques du frontend.
Les routes /api et /health, déclarées avant, restent prioritaires. Une route Angular (/companion, /flashcards…)
rechargée dans le navigateur renvoie index.html ; une route /api inconnue garde sa réponse 404 en JSON.
"""
import os
from pathlib import Path

from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.main import app

FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", "static"))


class SPAStaticFiles(StaticFiles):
    """Fichiers statiques, avec repli sur index.html pour les routes du frontend."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code != 404 or path.startswith(("api/", "api")) or path == "health":
                raise
            return await super().get_response("index.html", scope)


app.mount("/", SPAStaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
