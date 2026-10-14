from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.db import get_session
from app.core.security import decode_access_token
from app.phase8_personal.models import User

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    """Étudiant connecté, d'après l'en-tête « Authorization: Bearer <jeton> ». 401 sinon."""
    if credentials is None:
        raise _unauthorized("Authentification requise : connecte-toi.")
    user_id = decode_access_token(credentials.credentials)
    user = session.get(User, user_id) if user_id is not None else None
    if user is None:
        raise _unauthorized("Session expirée ou invalide : reconnecte-toi.")
    return user
