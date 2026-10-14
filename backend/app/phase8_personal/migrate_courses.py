"""Rattache les anciens cours Qdrant (importés avant les comptes, sans user_id) à un étudiant.

Usage : python -m app.phase8_personal.migrate_courses <email>
"""
import sys

from qdrant_client.models import FieldCondition, Filter, IsEmptyCondition, MatchValue, PayloadField
from sqlmodel import Session, select

from app.core.config import COLLECTION
from app.core.db import engine, init_db
from app.phase2_embeddings import vectorstore
from app.phase8_personal.courses import add_course, get_user_course
from app.phase8_personal.models import User

# Points sans propriétaire : champ user_id absent ou nul
ORPHAN = IsEmptyCondition(is_empty=PayloadField(key="user_id"))


def orphan_courses() -> dict[str, int]:
    """Cours sans propriétaire → nombre de morceaux."""
    counts: dict[str, int] = {}
    offset = None
    while True:
        points, offset = vectorstore.client.scroll(
            COLLECTION, scroll_filter=Filter(must=[ORPHAN]), limit=256, offset=offset,
            with_payload=["course"], with_vectors=False,
        )
        for p in points:
            counts[p.payload["course"]] = counts.get(p.payload["course"], 0) + 1
        if offset is None:
            return counts


def migrate(email: str) -> tuple[list[str], list[str]]:
    """Rattache chaque cours orphelin à l'étudiant. Renvoie (cours migrés, cours ignorés car déjà présents)."""
    vectorstore.ensure_collection()
    init_db()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email.strip().lower())).first()
        if user is None:
            raise LookupError(f"Aucun compte avec l'email « {email} ». Inscris-toi d'abord dans l'application.")

        migrated, skipped = [], []
        for course in sorted(orphan_courses()):
            if get_user_course(session, user.id, course):
                skipped.append(course)  # l'étudiant a déjà réimporté ce cours : on ne mélange pas deux versions
                continue
            vectorstore.client.set_payload(
                COLLECTION,
                payload={"user_id": user.id},
                points=Filter(must=[ORPHAN, FieldCondition(key="course", match=MatchValue(value=course))]),
            )
            add_course(session, user.id, course)
            migrated.append(course)
        return migrated, skipped


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage : python -m app.phase8_personal.migrate_courses <email>")
        sys.exit(1)

    pending = orphan_courses()
    if not pending:
        print("✅ Aucun ancien cours à migrer.")
        sys.exit(0)
    print("Cours sans propriétaire : " + ", ".join(f"{c} ({n} morceaux)" for c, n in sorted(pending.items())))

    try:
        migrated, skipped = migrate(sys.argv[1])
    except LookupError as e:
        print(f"❌ {e}")
        sys.exit(1)

    for course in migrated:
        print(f"✅ « {course} » rattaché à {sys.argv[1]}")
    for course in skipped:
        print(f"⚠️ « {course} » ignoré : ce compte a déjà un cours de ce nom (supprime-le puis relance, "
              "ou réimporte le PDF).")
