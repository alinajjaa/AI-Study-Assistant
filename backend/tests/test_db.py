import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.phase8_personal.models import Conversation, Course, Message, User


def test_tables_et_champs_json(session):
    user = User(email="a@example.com", password_hash="x", level="debutant")
    session.add(user)
    session.commit()
    conv = Conversation(user_id=user.id, title="CNN")
    session.add(conv)
    session.commit()
    session.add(Message(conversation_id=conv.id, role="assistant", content="Réponse",
                        sources=[{"course": "CNN", "page": 3}], answered=True))
    session.commit()

    msg = session.exec(select(Message)).one()
    assert msg.sources == [{"course": "CNN", "page": 3}]
    assert msg.created_at is not None


def test_email_unique(session):
    session.add(User(email="a@example.com", password_hash="x"))
    session.commit()
    session.add(User(email="a@example.com", password_hash="y"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_cours_unique_par_etudiant(session):
    a, b = User(email="a@example.com", password_hash="x"), User(email="b@example.com", password_hash="x")
    session.add_all([a, b])
    session.commit()
    session.add_all([Course(user_id=a.id, name="CNN"), Course(user_id=b.id, name="CNN")])
    session.commit()  # même nom chez deux étudiants : autorisé
    session.add(Course(user_id=a.id, name="CNN"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_hachage_bcrypt():
    hashed = hash_password("motdepasse123")
    assert hashed != "motdepasse123" and hashed.startswith("$2")
    assert verify_password("motdepasse123", hashed)
    assert not verify_password("mauvais", hashed)


def test_jeton_jwt():
    token = create_access_token(42)
    assert decode_access_token(token) == 42
    assert decode_access_token(token + "x") is None
    assert decode_access_token("pas-un-jeton") is None
