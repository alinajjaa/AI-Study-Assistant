from datetime import datetime, timedelta, UTC

import jwt

from app.core import config
from tests.helpers import register


def test_inscription_puis_me(client):
    res = client.post("/api/auth/register",
                      json={"email": "  Ali@Example.com ", "password": "motdepasse123", "level": "debutant"})
    assert res.status_code == 201
    body = res.json()
    assert body["user"]["email"] == "ali@example.com"
    assert body["user"]["level"] == "debutant"
    assert "password_hash" not in body["user"]

    me = client.get("/api/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "ali@example.com"


def test_email_deja_utilise(client):
    register(client, "ali@example.com")
    res = client.post("/api/auth/register", json={"email": "ALI@example.com", "password": "autremotdepasse"})
    assert res.status_code == 409
    assert res.json()["detail"] == "Un compte existe déjà avec cet email."


def test_validation_en_francais(client):
    res = client.post("/api/auth/register", json={"email": "pas-un-email", "password": "court"})
    assert res.status_code == 422
    messages = [e["msg"] for e in res.json()["detail"]]
    assert "Adresse email invalide." in messages
    assert "Le mot de passe doit contenir au moins 8 caractères." in messages

    trop_long = client.post("/api/auth/register", json={"email": "a@example.com", "password": "x" * 73})
    assert trop_long.status_code == 422


def test_connexion(client):
    register(client, "ali@example.com", "motdepasse123")
    ok = client.post("/api/auth/login", json={"email": "ali@example.com", "password": "motdepasse123"})
    assert ok.status_code == 200
    assert ok.json()["access_token"]
    assert ok.json()["user"]["email"] == "ali@example.com"


def test_mauvais_mot_de_passe(client):
    register(client, "ali@example.com", "motdepasse123")
    res = client.post("/api/auth/login", json={"email": "ali@example.com", "password": "mauvais-mdp"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Email ou mot de passe incorrect."
    inconnu = client.post("/api/auth/login", json={"email": "personne@example.com", "password": "motdepasse123"})
    assert inconnu.status_code == 401


def test_me_sans_jeton(client):
    res = client.get("/api/me")
    assert res.status_code == 401
    assert res.json()["detail"] == "Authentification requise : connecte-toi."


def test_me_jeton_invalide_ou_expire(client):
    assert client.get("/api/me", headers={"Authorization": "Bearer abc.def.ghi"}).status_code == 401
    headers = register(client)
    expired = jwt.encode({"sub": "1", "exp": datetime.now(UTC) - timedelta(minutes=1)},
                         config.JWT_SECRET, algorithm="HS256")
    res = client.get("/api/me", headers={"Authorization": f"Bearer {expired}"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Session expirée ou invalide : reconnecte-toi."
    assert client.get("/api/me", headers=headers).status_code == 200


def test_changer_de_niveau(client):
    headers = register(client, level="debutant")
    res = client.patch("/api/me", json={"level": "avance"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["level"] == "avance"
    assert client.get("/api/me", headers=headers).json()["level"] == "avance"
    assert client.patch("/api/me", json={"level": "expert"}, headers=headers).status_code == 422
