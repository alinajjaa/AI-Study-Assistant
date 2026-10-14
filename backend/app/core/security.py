from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core import config

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hachage bcrypt avec sel aléatoire (bcrypt limite le mot de passe à 72 octets)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:  # hachage corrompu ou mot de passe trop long
        return False


def _secret() -> str:
    if not config.JWT_SECRET:
        raise RuntimeError("JWT_SECRET absent : renseigne-le dans le fichier .env.")
    return config.JWT_SECRET


def create_access_token(user_id: int) -> str:
    """Jeton signé HS256 contenant l'identifiant de l'étudiant et sa date d'expiration."""
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=config.JWT_EXPIRE_HOURS)}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Renvoie l'identifiant de l'étudiant, ou None si le jeton est invalide ou expiré."""
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM], options={"require": ["sub", "exp"]})
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
