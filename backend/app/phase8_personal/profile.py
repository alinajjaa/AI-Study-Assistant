"""Profil de l'étudiant : statistiques, points faibles (révisions « à revoir ») et suggestion de niveau."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Integer, cast
from sqlmodel import Session, func, select

from app.core.db import get_session
from app.phase8_personal.deps import get_current_user
from app.phase8_personal.models import LEVELS, Conversation, Course, ExamRecord, Level, Message, Review, User

router = APIRouter(prefix="/api", tags=["Profil"])

KNOWN = func.sum(cast(Review.known, Integer))  # nombre de « Je savais » (SUM d'un booléen = booléen sinon)
WEAK_MIN_REVIEWS = 2  # un concept révisé une seule fois ne dit rien
WEAK_MAX = 5
SUGGESTION_MIN_REVIEWS = 20
SUGGEST_UP_ABOVE = 0.85  # plus de 85 % de cartes sues → niveau supérieur
SUGGEST_DOWN_BELOW = 0.40  # moins de 40 % → niveau inférieur


class Stats(BaseModel):
    courses: int
    questions: int
    exams: int
    cards_reviewed: int
    known_rate: float | None  # entre 0 et 1, None sans révision


class WeakPoint(BaseModel):
    course: str
    concept: str
    reviews: int
    to_review_rate: float  # part des révisions « à revoir », entre 0 et 1


class LevelSuggestion(BaseModel):
    level: Level
    direction: str  # "up" | "down"
    reviews: int
    known_rate: float


class Profile(BaseModel):
    email: str
    level: Level
    stats: Stats
    weak_points: list[WeakPoint]
    level_suggestion: LevelSuggestion | None


def _count(session: Session, query) -> int:
    return session.exec(query).one() or 0


def compute_stats(session: Session, user_id: int) -> Stats:
    reviews = _count(session, select(func.count(Review.id)).where(Review.user_id == user_id))
    known = _count(session, select(func.count(Review.id)).where(Review.user_id == user_id, Review.known))
    return Stats(
        courses=_count(session, select(func.count(Course.id)).where(Course.user_id == user_id)),
        questions=_count(session, select(func.count(Message.id)).join(Conversation)
                         .where(Conversation.user_id == user_id, Message.role == "user")),
        exams=_count(session, select(func.count(ExamRecord.id)).where(ExamRecord.user_id == user_id)),
        cards_reviewed=reviews,
        known_rate=round(known / reviews, 3) if reviews else None,
    )


def weak_points(session: Session, user_id: int, course: str | None = None) -> list[WeakPoint]:
    """Concepts au taux « à revoir » le plus élevé (au moins 2 révisions, 5 concepts au maximum)."""
    query = (select(Review.course, Review.concept, func.count(Review.id), KNOWN)
             .where(Review.user_id == user_id).group_by(Review.course, Review.concept))
    if course is not None:
        query = query.where(Review.course == course)
    points = []
    for course_name, concept, total, known in session.exec(query):
        rate = (total - (known or 0)) / total
        if total >= WEAK_MIN_REVIEWS and rate > 0:
            points.append(WeakPoint(course=course_name, concept=concept, reviews=total, to_review_rate=round(rate, 3)))
    points.sort(key=lambda p: (-p.to_review_rate, -p.reviews, p.concept))
    return points[:WEAK_MAX]


def level_suggestion(session: Session, user: User) -> LevelSuggestion | None:
    """Suggestion (jamais un changement automatique) à partir des révisions faites depuis le dernier changement de niveau."""
    query = select(func.count(Review.id), KNOWN).where(Review.user_id == user.id)
    if user.level_changed_at is not None:
        query = query.where(Review.created_at > user.level_changed_at)
    total, known = session.exec(query).one()
    if not total or total < SUGGESTION_MIN_REVIEWS:
        return None
    rate = (known or 0) / total
    index = LEVELS.index(user.level) if user.level in LEVELS else 1
    if rate > SUGGEST_UP_ABOVE and index < len(LEVELS) - 1:
        return LevelSuggestion(level=LEVELS[index + 1], direction="up", reviews=total, known_rate=round(rate, 3))
    if rate < SUGGEST_DOWN_BELOW and index > 0:
        return LevelSuggestion(level=LEVELS[index - 1], direction="down", reviews=total, known_rate=round(rate, 3))
    return None


@router.get("/profile")
def read_profile(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> Profile:
    return Profile(
        email=user.email,
        level=user.level,
        stats=compute_stats(session, user.id),
        weak_points=weak_points(session, user.id),
        level_suggestion=level_suggestion(session, user),
    )
