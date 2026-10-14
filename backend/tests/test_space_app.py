"""Point d'entrée Hugging Face Spaces (deploy/hf-space/space_app.py) : frontend statique + API sur un seul port."""
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SPACE_APP = Path(__file__).resolve().parents[2] / "deploy" / "hf-space" / "space_app.py"


@pytest.fixture
def space_client(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<app-root>frontend</app-root>", encoding="utf-8")
    (tmp_path / "main.js").write_text("console.log('ok')", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIR", str(tmp_path))

    from app.main import app

    routes_before = list(app.router.routes)
    spec = importlib.util.spec_from_file_location("space_app", SPACE_APP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # ajoute le montage « / » à l'application partagée
    try:
        with TestClient(module.app) as client:
            yield client
    finally:
        app.router.routes[:] = routes_before  # les autres tests gardent l'application d'origine


def test_frontend_servi_a_la_racine(space_client):
    response = space_client.get("/")
    assert response.status_code == 200 and "frontend" in response.text
    assert space_client.get("/main.js").text == "console.log('ok')"


def test_route_angular_renvoie_index(space_client):
    response = space_client.get("/companion")
    assert response.status_code == 200 and "frontend" in response.text


def test_api_prioritaire_et_404_json(space_client):
    assert space_client.get("/health").json() == {"status": "ok"}
    assert space_client.get("/api/courses").status_code == 401  # route de l'API, protégée
    unknown = space_client.get("/api/inconnue")
    assert unknown.status_code == 404 and unknown.headers["content-type"].startswith("application/json")
