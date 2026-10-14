from pathlib import Path

from app.core import config
from tests.helpers import register, sample_exam, upload


def _generate(client, headers, course="CNN"):
    return client.post(f"/api/courses/{course}/exam",
                       json={"format": "qcm", "num_questions": 5, "difficulty": "facile", "include_answers": False},
                       headers=headers)


def _fake_generator(monkeypatch):
    from app.phase4_exam import routes

    monkeypatch.setattr(routes, "generate_exam", lambda course, *args, **kwargs: sample_exam(course))


def test_examen_enregistre_et_reteleechargeable(client, monkeypatch):
    _fake_generator(monkeypatch)
    headers = register(client)
    upload(client, headers, "CNN")
    res = _generate(client, headers)
    assert res.status_code == 200
    exam_id = int(res.headers["X-Exam-Id"])

    exams = client.get("/api/exams", headers=headers).json()
    assert len(exams) == 1
    assert exams[0] == {**exams[0], "id": exam_id, "course": "CNN", "format": "qcm", "difficulty": "facile",
                        "question_count": 1, "include_answers": False}
    assert exams[0]["created_at"].endswith("Z")

    files = list((Path(config.STORAGE_DIR) / "exams").glob("*.pdf"))
    assert len(files) == 1

    pdf = client.get(f"/api/exams/{exam_id}/pdf", headers=headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content == res.content
    assert 'filename="examen_CNN_qcm_facile.pdf"' in pdf.headers["content-disposition"]

    assert client.delete(f"/api/exams/{exam_id}", headers=headers).status_code == 200
    assert client.get("/api/exams", headers=headers).json() == []
    assert not files[0].exists()
    assert client.get(f"/api/exams/{exam_id}/pdf", headers=headers).status_code == 404


def test_isolation_des_examens(client, monkeypatch):
    _fake_generator(monkeypatch)
    alice = register(client, "alice@example.com")
    bob = register(client, "bob@example.com")
    upload(client, alice, "CNN")
    exam_id = int(_generate(client, alice).headers["X-Exam-Id"])

    assert client.get("/api/exams", headers=bob).json() == []
    assert client.get(f"/api/exams/{exam_id}/pdf", headers=bob).status_code == 404
    assert client.delete(f"/api/exams/{exam_id}", headers=bob).status_code == 404
    assert client.get("/api/exams").status_code == 401
    assert len(client.get("/api/exams", headers=alice).json()) == 1


def test_echec_de_generation_rien_enregistre(client, monkeypatch):
    from app.phase4_exam import routes

    def failing(*args, **kwargs):
        raise ValueError("Le modèle n'a produit aucune question valide. Réessaie.")

    monkeypatch.setattr(routes, "generate_exam", failing)
    headers = register(client)
    upload(client, headers, "CNN")
    assert _generate(client, headers).status_code == 422
    assert client.get("/api/exams", headers=headers).json() == []
