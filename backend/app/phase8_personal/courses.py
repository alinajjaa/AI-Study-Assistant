import re

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.phase8_personal.models import Course

COURSE_NAME_MAX = 100
# Barres obliques : le nom sert de paramètre d'URL (/api/courses/{course}), un « / » rendrait le cours
# impossible à interroger ou à supprimer. Caractères de contrôle : invisibles et dangereux dans les en-têtes.
FORBIDDEN_IN_NAME = re.compile(r"[/\\\x00-\x1f\x7f]")


def clean_course_name(name: str) -> str:
    """Nom de cours importé, espaces normalisés ; 400 s'il est vide, trop long ou contient / \\ ou un caractère
    de contrôle."""
    if FORBIDDEN_IN_NAME.search(name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Le nom du cours ne doit contenir ni « / », ni « \\ », ni caractère de contrôle.")
    name = " ".join(name.split())
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Le nom du cours est vide")
    if len(name) > COURSE_NAME_MAX:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Le nom du cours est trop long ({COURSE_NAME_MAX} caractères au maximum).")
    return name


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
