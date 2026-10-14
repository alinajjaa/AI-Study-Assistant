from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.phase8_personal.models import Course


def course_not_found(name: str) -> HTTPException:
    """Même réponse que le cours n'existe pas ou appartienne à un autre étudiant (rien ne fuit)."""
    return HTTPException(status.HTTP_404_NOT_FOUND, f"Le cours « {name} » est introuvable.")


def get_user_course(session: Session, user_id: int, name: str) -> Course | None:
    return session.exec(select(Course).where(Course.user_id == user_id, Course.name == name)).first()


def require_course(session: Session, user_id: int, name: str) -> Course:
    """Le cours de l'étudiant, ou 404."""
    course = get_user_course(session, user_id, name)
    if course is None:
        raise course_not_found(name)
    return course


def list_user_courses(session: Session, user_id: int) -> list[str]:
    return list(session.exec(select(Course.name).where(Course.user_id == user_id).order_by(Course.name)))


def add_course(session: Session, user_id: int, name: str) -> Course:
    """Enregistre le cours (réimporter un cours existant ne crée pas de doublon)."""
    course = get_user_course(session, user_id, name)
    if course is None:
        course = Course(user_id=user_id, name=name)
        session.add(course)
        session.commit()
        session.refresh(course)
    return course
