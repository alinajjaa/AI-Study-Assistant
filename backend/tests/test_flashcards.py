from tests.helpers import register, sample_deck, upload


def _fake_generator(monkeypatch):
    from app.phase7_flashcards import routes

    monkeypatch.setattr(routes, "generate_flashcards", lambda course, count, user_id=None, stats=None: sample_deck(course))


def _generate(client, headers, course="CNN"):
    return client.post(f"/api/courses/{course}/flashcards", json={"count": 10}, headers=headers)


def test_paquet_enregistre_avec_deck_id(client, monkeypatch):
    _fake_generator(monkeypatch)
    headers = register(client)
    upload(client, headers, "CNN")
    res = _generate(client, headers)
    assert res.status_code == 200
    body = res.json()
    assert body["deck_id"] == body["id"]
    assert body["course"] == "CNN" and len(body["cards"]) == 2
    assert body["cards"][0]["concept"] == "Pooling"

    decks = client.get("/api/flashcards/decks", headers=headers).json()
    assert decks == [{"id": body["deck_id"], "course": "CNN", "card_count": 2, "created_at": body["created_at"]}]
    assert client.get("/api/flashcards/decks?course=Autre", headers=headers).json() == []

    deck = client.get(f"/api/flashcards/decks/{body['deck_id']}", headers=headers).json()
    assert deck["cards"] == body["cards"]


def test_revisions_et_suppression_du_paquet(client, monkeypatch, session):
    from sqlmodel import select

    from app.phase8_personal.models import Review

    _fake_generator(monkeypatch)
    headers = register(client)
    upload(client, headers, "CNN")
    deck_id = _generate(client, headers).json()["deck_id"]

    res = client.post("/api/reviews", json={"deck_id": deck_id, "concept": "Pooling", "known": True}, headers=headers)
    assert res.status_code == 201
    assert res.json()["course"] == "CNN" and res.json()["known"] is True
    assert client.post("/api/reviews", json={"deck_id": deck_id, "concept": "Inconnu", "known": True},
                       headers=headers).status_code == 422
    assert client.post("/api/reviews", json={"deck_id": 999, "concept": "Pooling", "known": True},
                       headers=headers).status_code == 404

    assert client.delete(f"/api/flashcards/decks/{deck_id}", headers=headers).status_code == 200
    assert client.get("/api/flashcards/decks", headers=headers).json() == []
    reviews = session.exec(select(Review)).all()
    assert len(reviews) == 1 and reviews[0].deck_id is None  # l'historique reste pour le profil


def test_isolation_des_paquets(client, monkeypatch):
    _fake_generator(monkeypatch)
    alice = register(client, "alice@example.com")
    bob = register(client, "bob@example.com")
    upload(client, alice, "CNN")
    deck_id = _generate(client, alice).json()["deck_id"]

    assert client.get("/api/flashcards/decks", headers=bob).json() == []
    assert client.get(f"/api/flashcards/decks/{deck_id}", headers=bob).status_code == 404
    assert client.delete(f"/api/flashcards/decks/{deck_id}", headers=bob).status_code == 404
    assert client.post("/api/reviews", json={"deck_id": deck_id, "concept": "Pooling", "known": False},
                       headers=bob).status_code == 404
    assert client.get("/api/flashcards/decks").status_code == 401
    assert client.post("/api/reviews", json={"deck_id": deck_id, "concept": "Pooling", "known": False}).status_code == 401
