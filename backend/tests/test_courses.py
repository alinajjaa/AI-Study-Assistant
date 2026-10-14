from app.phase2_embeddings import vectorstore
from app.phase2_embeddings.ingest import MIN_CHUNK_CHARS, chunk_text
from app.phase8_personal.migrate_courses import migrate, orphan_courses
from tests.helpers import fake_vector, register, sample_deck, sample_exam, upload


def test_routes_protegees(client):
    assert client.get("/api/courses").status_code == 401
    assert client.post("/api/ask", json={"question": "x"}).status_code == 401
    assert client.delete("/api/courses/CNN").status_code == 401
    assert client.post("/api/courses/CNN/exam", json={}).status_code == 401
    assert client.post("/api/courses/CNN/flashcards", json={}).status_code == 401
    pdf = {"file": ("a.pdf", b"%PDF", "application/pdf")}
    assert client.post("/api/upload", files=pdf).status_code == 401


def test_import_enregistre_user_id_et_ligne_course(client):
    headers = register(client)
    res = upload(client, headers, "CNN")
    assert res.status_code == 200, res.text
    assert client.get("/api/courses", headers=headers).json() == ["CNN"]

    points, _ = vectorstore.client.scroll("courses", limit=100, with_payload=True)
    assert points and all(p.payload["user_id"] == 1 for p in points)
    # Réimporter le même cours ne crée ni doublon de ligne ni doublon de morceaux
    n = len(points)
    upload(client, headers, "CNN")
    assert client.get("/api/courses", headers=headers).json() == ["CNN"]
    assert len(vectorstore.client.scroll("courses", limit=100)[0]) == n


def test_isolation_des_cours(client, llm):
    alice = register(client, "alice@example.com")
    bob = register(client, "bob@example.com")
    upload(client, alice, "Cours-Alice")
    upload(client, bob, "Cours-Bob")

    assert client.get("/api/courses", headers=alice).json() == ["Cours-Alice"]
    assert client.get("/api/courses", headers=bob).json() == ["Cours-Bob"]

    # Bob ne peut ni interroger, ni supprimer, ni générer à partir du cours d'Alice
    assert client.post("/api/ask", json={"question": "Pooling ?", "course": "Cours-Alice"},
                       headers=bob).status_code == 404
    assert client.delete("/api/courses/Cours-Alice", headers=bob).status_code == 404
    assert client.post("/api/courses/Cours-Alice/exam", json={}, headers=bob).status_code == 404
    assert client.post("/api/courses/Cours-Alice/flashcards", json={}, headers=bob).status_code == 404

    # Recherche « tous les cours » : Bob ne reçoit que ses propres extraits
    res = client.post("/api/ask", json={"question": "Pooling ?"}, headers=bob)
    assert res.status_code == 200
    assert {s["course"] for s in res.json()["sources"]} == {"Cours-Bob"}

    assert vectorstore.get_course_chunks("Cours-Alice", 2) == []
    assert vectorstore.get_course_chunks("Cours-Alice", 1)


def test_suppression(client):
    headers = register(client)
    upload(client, headers, "CNN")
    assert client.delete("/api/courses/CNN", headers=headers).status_code == 200
    assert client.get("/api/courses", headers=headers).json() == []
    assert vectorstore.client.scroll("courses", limit=10)[0] == []
    assert client.delete("/api/courses/CNN", headers=headers).status_code == 404


def test_examen_et_flashcards_recoivent_user_id(client, monkeypatch):
    from app.phase4_exam import routes as exam_routes
    from app.phase7_flashcards import routes as flashcards_routes

    calls = {}

    def fake_exam(course, fmt, num, difficulty, user_id=None):
        calls["exam"] = user_id
        return sample_exam(course)

    def fake_flashcards(course, count, user_id=None):
        calls["flashcards"] = user_id
        return sample_deck(course)

    monkeypatch.setattr(exam_routes, "generate_exam", fake_exam)
    monkeypatch.setattr(flashcards_routes, "generate_flashcards", fake_flashcards)
    headers = register(client)
    upload(client, headers, "CNN")

    res = client.post("/api/courses/CNN/exam", json={"format": "qcm", "num_questions": 5}, headers=headers)
    assert res.status_code == 200 and res.headers["content-type"] == "application/pdf"
    assert client.post("/api/courses/CNN/flashcards", json={"count": 10}, headers=headers).status_code == 200
    assert calls == {"exam": 1, "flashcards": 1}


def test_decoupage_dernier_morceau_court():
    # 1400 caractères : morceaux à 0, 650 puis 1300 → l'ancien code gardait un 3e morceau de 100 caractères
    text = "a" * 1395 + " fin."
    chunks = chunk_text(text, size=800, overlap=150)
    assert len(chunks) == 2
    assert all(len(c) >= MIN_CHUNK_CHARS for c in chunks)
    assert chunks[-1] == text[650:]  # le morceau précédent va jusqu'à la fin

    long_text = " ".join(f"mot{i}" for i in range(400))
    pieces = chunk_text(long_text)
    assert all(len(p) >= MIN_CHUNK_CHARS for p in pieces)
    assert pieces[-1].endswith("mot399")


def test_texte_court_reste_un_seul_morceau():
    assert chunk_text("Titre") == ["Titre"]


def test_migration_des_anciens_cours(client):
    from qdrant_client.models import PointStruct

    vectorstore.client.upsert("courses", points=[
        PointStruct(id=i, vector=fake_vector(f"t{i}"), payload={"course": "Ancien", "page": 1, "text": f"t{i}"})
        for i in range(3)
    ])
    headers = register(client, "ali@example.com")
    assert client.get("/api/courses", headers=headers).json() == []  # invisibles avant migration
    assert orphan_courses() == {"Ancien": 3}

    migrated, skipped = migrate("ALI@example.com")
    assert migrated == ["Ancien"] and skipped == []
    assert orphan_courses() == {}
    assert client.get("/api/courses", headers=headers).json() == ["Ancien"]
    assert len(vectorstore.get_course_chunks("Ancien", 1)) == 3


def test_suppression_sans_proprietaire_ne_touche_pas_les_etudiants(client):
    from qdrant_client.models import PointStruct

    headers = register(client)
    upload(client, headers, "CNN")
    vectorstore.client.upsert("courses", points=[
        PointStruct(id=1, vector=fake_vector("x"), payload={"course": "CNN", "page": 1, "text": "x"}),
    ])
    vectorstore.delete_course("CNN", user_id=None)  # script CLI : seuls les points orphelins partent
    assert orphan_courses() == {}
    assert vectorstore.get_course_chunks("CNN", 1)
