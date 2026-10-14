from datetime import timedelta

from sqlmodel import select

from app.phase3_rag.rag import LEVEL_INSTRUCTIONS
from app.phase8_personal.models import FlashcardDeck, Review, User, utcnow
from tests.helpers import register, sample_deck, sample_exam, upload


def _add_reviews(session, user_id: int, results: dict[str, list[bool]], course: str = "CNN", when=None):
    """results : concept → liste de réponses (True = « Je savais »)."""
    deck = FlashcardDeck(user_id=user_id, course=course,
                         cards=[{"concept": c, "front": "?", "back": ".", "page": 1} for c in results])
    session.add(deck)
    session.commit()
    for concept, answers in results.items():
        for known in answers:
            review = Review(user_id=user_id, deck_id=deck.id, course=course, concept=concept, known=known)
            if when is not None:
                review.created_at = when
            session.add(review)
    session.commit()


def _user_id(session, email="etudiant@example.com") -> int:
    return session.exec(select(User).where(User.email == email)).one().id


def test_statistiques(client, llm, monkeypatch, session):
    from app.phase4_exam import routes as exam_routes
    from app.phase7_flashcards import routes as flashcard_routes

    monkeypatch.setattr(exam_routes, "generate_exam", lambda course, *a, **k: sample_exam(course))
    monkeypatch.setattr(flashcard_routes, "generate_flashcards", lambda course, count, user_id=None: sample_deck(course))
    headers = register(client)
    upload(client, headers, "CNN")
    upload(client, headers, "RNN")
    conv = client.post("/api/conversations", json={}, headers=headers).json()["id"]
    for q in ["Qu'est-ce que le pooling ?", "Et la convolution ?"]:
        client.post(f"/api/conversations/{conv}/messages", json={"question": q}, headers=headers)
    client.post("/api/courses/CNN/exam", json={"format": "qcm", "num_questions": 5}, headers=headers)
    deck_id = client.post("/api/courses/CNN/flashcards", json={"count": 10}, headers=headers).json()["deck_id"]
    for concept, known in [("Pooling", True), ("Pooling", True), ("Convolution", False), ("Convolution", True)]:
        client.post("/api/reviews", json={"deck_id": deck_id, "concept": concept, "known": known}, headers=headers)

    profile = client.get("/api/profile", headers=headers).json()
    assert profile["level"] == "intermediaire"
    assert profile["stats"] == {"courses": 2, "questions": 2, "exams": 1, "cards_reviewed": 4, "known_rate": 0.75}
    assert profile["level_suggestion"] is None


def test_profil_vide_et_protege(client):
    assert client.get("/api/profile").status_code == 401
    profile = client.get("/api/profile", headers=register(client)).json()
    assert profile["stats"]["known_rate"] is None
    assert profile["weak_points"] == [] and profile["level_suggestion"] is None


def test_points_faibles(client, session):
    headers = register(client)
    _add_reviews(session, _user_id(session), {
        "Pooling": [False, False],                 # 100 % à revoir
        "Convolution": [False, True, False],       # 67 %
        "Padding": [False],                        # une seule révision : ignoré
        "Filtre": [True, True, True],              # 0 % : pas un point faible
        "Stride": [False, True],                   # 50 %
        "Softmax": [False, True, True],            # 33 %
        "ReLU": [False, True, True, True],         # 25 %
        "Dropout": [False, True, True, True, True],  # 20 % : 6e, hors du top 5
    })
    weak = client.get("/api/profile", headers=headers).json()["weak_points"]
    assert [w["concept"] for w in weak] == ["Pooling", "Convolution", "Stride", "Softmax", "ReLU"]
    assert weak[0] == {"course": "CNN", "concept": "Pooling", "reviews": 2, "to_review_rate": 1.0}


def test_suggestion_de_niveau(client, session):
    headers = register(client, level="intermediaire")
    uid = _user_id(session)
    _add_reviews(session, uid, {"Pooling": [True] * 17 + [False] * 2})  # 19 révisions : pas encore
    assert client.get("/api/profile", headers=headers).json()["level_suggestion"] is None

    _add_reviews(session, uid, {"Filtre": [True]})  # 20 révisions, 18 sues = 90 %
    suggestion = client.get("/api/profile", headers=headers).json()["level_suggestion"]
    assert suggestion == {"level": "avance", "direction": "up", "reviews": 20, "known_rate": 0.9}

    # Suggestion seulement : le niveau ne change pas tant que l'étudiant n'accepte pas
    assert client.get("/api/me", headers=headers).json()["level"] == "intermediaire"
    client.patch("/api/me", json={"level": "avance"}, headers=headers)
    # Les révisions d'avant le changement ne comptent plus
    assert client.get("/api/profile", headers=headers).json()["level_suggestion"] is None


def test_suggestion_niveau_inferieur(client, session):
    headers = register(client, level="avance")
    uid = _user_id(session)
    _add_reviews(session, uid, {"Pooling": [True] * 7 + [False] * 13})  # 35 %
    suggestion = client.get("/api/profile", headers=headers).json()["level_suggestion"]
    assert suggestion["level"] == "intermediaire" and suggestion["direction"] == "down"


def test_pas_de_suggestion_hors_bornes(client, session):
    headers = register(client, level="debutant")
    _add_reviews(session, _user_id(session), {"Pooling": [False] * 20})  # déjà au niveau le plus bas
    assert client.get("/api/profile", headers=headers).json()["level_suggestion"] is None


def test_revisions_anterieures_au_changement_ignorees(client, session):
    headers = register(client, level="intermediaire")
    client.patch("/api/me", json={"level": "debutant"}, headers=headers)
    uid = _user_id(session)
    _add_reviews(session, uid, {"Pooling": [True] * 20}, when=utcnow() - timedelta(days=1))
    assert client.get("/api/profile", headers=headers).json()["level_suggestion"] is None
    _add_reviews(session, uid, {"Filtre": [True] * 20})
    assert client.get("/api/profile", headers=headers).json()["level_suggestion"]["level"] == "intermediaire"


def test_consigne_de_niveau_sans_email_ni_nom(client, llm):
    email = "ali.najjaa@example.com"
    headers = register(client, email=email, level="debutant")
    upload(client, headers, "CNN")
    conv = client.post("/api/conversations", json={}, headers=headers).json()["id"]
    client.post(f"/api/conversations/{conv}/messages", json={"question": "Qu'est-ce que le pooling ?"},
                headers=headers)
    client.post("/api/ask", json={"question": "Qu'est-ce que le pooling ?"}, headers=headers)

    assert len(llm.calls) == 2
    for system, prompt in llm.calls:
        assert LEVEL_INSTRUCTIONS["debutant"] in system
        assert "analogie de la vie courante" in system
        assert "[p.X]" in system and "UNIQUEMENT à partir des extraits" in system  # règles existantes intactes
        for secret in (email, "ali.najjaa", "najjaa"):
            assert secret not in system and secret not in prompt

    client.patch("/api/me", json={"level": "avance"}, headers=headers)
    client.post("/api/ask", json={"question": "Qu'est-ce que le pooling ?"}, headers=headers)
    assert LEVEL_INSTRUCTIONS["avance"] in llm.calls[-1][0]
    assert LEVEL_INSTRUCTIONS["debutant"] not in llm.calls[-1][0]


def test_point_faible_signale_si_la_question_le_touche(client, llm, session):
    headers = register(client)
    upload(client, headers, "CNN")
    _add_reviews(session, _user_id(session), {"Max pooling": [False, False, True]})

    client.post("/api/ask", json={"question": "Comment fonctionne le max-pooling ?", "course": "CNN"},
                headers=headers)
    assert "« Max pooling »" in llm.calls[-1][0]
    assert "bienveillance" in llm.calls[-1][0]

    client.post("/api/ask", json={"question": "Qu'est-ce qu'une convolution ?", "course": "CNN"}, headers=headers)
    assert "bienveillance" not in llm.calls[-1][0]
