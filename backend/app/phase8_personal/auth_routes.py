import threading
import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core import config
from app.core.db import get_session
from app.core.security import create_access_token, hash_password, verify_password
from app.phase8_personal.deps import get_current_user
from app.phase8_personal.models import User, utcnow
from app.phase8_personal.schemas import AuthResponse, LoginRequest, RegisterRequest, UpdateMeRequest, UserOut

router = APIRouter(prefix="/api", tags=["Comptes étudiants"])

# Haché factice : un email inconnu prend autant de temps qu'un mauvais mot de passe
_DUMMY_HASH = hash_password("mot-de-passe-factice")


class LoginThrottle:
    """Échecs de connexion récents par email : au-delà de LOGIN_MAX_FAILURES dans la fenêtre, 429.

    En mémoire (un seul processus uvicorn) : remis à zéro au redémarrage. La clé est l'email et non l'adresse IP,
    qui est celle du proxy nginx en déploiement.
    """

    def __init__(self):
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, email: str, now: float) -> list[float]:
        window = config.LOGIN_WINDOW_MINUTES * 60
        recent = [t for t in self._failures.get(email, []) if now - t < window]
        if recent:
            self._failures[email] = recent
        else:
            self._failures.pop(email, None)
        return recent

    def retry_after(self, email: str) -> int | None:
        """Secondes à attendre si l'email est bloqué, sinon None."""
        with self._lock:
            now = time.monotonic()
            recent = self._recent(email, now)
            if len(recent) < config.LOGIN_MAX_FAILURES:
                return None
            return max(1, round(recent[0] + config.LOGIN_WINDOW_MINUTES * 60 - now))

    def failure(self, email: str) -> None:
        with self._lock:
            self._failures.setdefault(email, []).append(time.monotonic())

    def success(self, email: str) -> None:
        with self._lock:
            self._failures.pop(email, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


login_throttle = LoginThrottle()


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user, from_attributes=True))


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, session: Session = Depends(get_session)) -> AuthResponse:
    """Crée un compte étudiant et renvoie directement un jeton (connexion automatique)."""
    if session.exec(select(User).where(User.email == body.email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cet email.")
    user = User(email=body.email, password_hash=hash_password(body.password), level=body.level)
    session.add(user)
    try:
        session.commit()
    except IntegrityError:  # deux inscriptions simultanées avec le même email
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cet email.") from None
    session.refresh(user)
    return _auth_response(user)


@router.post("/auth/login")
def login(body: LoginRequest, session: Session = Depends(get_session)) -> AuthResponse:
    wait = login_throttle.retry_after(body.email)
    if wait is not None:
        minutes = max(1, round(wait / 60))
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Trop de tentatives de connexion : réessaie dans {minutes} min.",
                            headers={"Retry-After": str(wait)})
    user = session.exec(select(User).where(User.email == body.email)).first()
    valid = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not valid:
        login_throttle.failure(body.email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email ou mot de passe incorrect.")
    login_throttle.success(body.email)
    return _auth_response(user)


@router.get("/me")
def read_me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)


@router.patch("/me")
def update_me(body: UpdateMeRequest, user: User = Depends(get_current_user),
              session: Session = Depends(get_session)) -> UserOut:
    """Change le niveau de l'étudiant (débutant, intermédiaire, avancé)."""
    if body.level != user.level:
        user.level = body.level
        user.level_changed_at = utcnow()
    session.add(user)
    session.commit()
    session.refresh(user)
    return UserOut.model_validate(user, from_attributes=True)
