
from uuid import uuid4
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, PayloadSchemaType,
    Filter, FieldCondition, MatchValue, FilterSelector, IsEmptyCondition, PayloadField,
)
from app.core.config import QDRANT_PATH, QDRANT_URL, COLLECTION
from app.core.safety import neutralize_instructions
from app.phase2_embeddings.embeddings import dimension

# Serveur Qdrant (Docker) par défaut ; mode intégré (dossier local ou ":memory:") si QDRANT_PATH est défini
client = QdrantClient(path=QDRANT_PATH) if QDRANT_PATH and QDRANT_PATH != ":memory:" else     QdrantClient(":memory:") if QDRANT_PATH == ":memory:" else QdrantClient(url=QDRANT_URL)


def _filter(course: str | None = None, user_id: int | None = None) -> Filter | None:
    """Filtre sur le cours et/ou le propriétaire (user_id=None : aucun filtre de propriétaire, scripts uniquement)."""
    must = []
    if course is not None:
        must.append(FieldCondition(key="course", match=MatchValue(value=course)))
    if user_id is not None:
        must.append(FieldCondition(key="user_id", match=MatchValue(value=user_id)))
    return Filter(must=must) if must else None


def _readable(chunk: dict) -> dict:
    """Passage prêt à entrer dans un prompt : les consignes cachées dans le PDF sont retirées (injection de prompt)."""
    return {**chunk, "text": neutralize_instructions(chunk.get("text", ""))}


def ensure_collection() -> None:
    """Crée la collection si elle n'existe pas encore, avec un index sur le propriétaire des cours."""
    if not client.collection_exists(COLLECTION):
        client.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=dimension(), distance=Distance.COSINE),
        )
    # Sans effet si l'index existe déjà ; accélère le filtre user_id présent dans toutes les lectures
    client.create_payload_index(COLLECTION, field_name="user_id", field_schema=PayloadSchemaType.INTEGER)


def upsert(chunks: list[dict], vectors: list[list[float]]) -> None:
    """Stocke chaque chunk (course, page, text, user_id) avec son vecteur."""
    points = [
        PointStruct(id=str(uuid4()), vector=v, payload=c)
        for c, v in zip(chunks, vectors)
    ]
    client.upsert(COLLECTION, points=points)


def search(vector: list[float], k: int, course: str | None = None, *, user_id: int | None) -> list[dict]:
    """Renvoie les k chunks les plus proches parmi les cours de l'étudiant, éventuellement limités à un cours."""
    res = client.query_points(
        COLLECTION,
        query=vector,
        limit=k,
        query_filter=_filter(course or None, user_id),
        with_payload=True,
    )
    return [_readable({**p.payload, "score": p.score}) for p in res.points]


def list_courses(user_id: int | None = None) -> list[str]:
    """Liste les noms de cours présents dans Qdrant (l'API lit plutôt la table Course)."""
    courses, offset = set(), None
    while True:
        points, offset = client.scroll(
            COLLECTION, limit=256, offset=offset, scroll_filter=_filter(user_id=user_id),
            with_payload=["course"], with_vectors=False,
        )
        courses.update(p.payload["course"] for p in points)
        if offset is None:
            return sorted(courses)


def delete_course(course: str, *, user_id: int | None) -> None:
    """Supprime tous les chunks d'un cours de l'étudiant (utile pour réindexer ou nettoyer).

    user_id=None (scripts) : uniquement les chunks sans propriétaire, jamais le cours d'un étudiant.
    """
    selected = _filter(course, user_id)
    if user_id is None:
        selected.must.append(IsEmptyCondition(is_empty=PayloadField(key="user_id")))
    client.delete(COLLECTION, points_selector=FilterSelector(filter=selected))



def get_course_chunks(course: str, user_id: int | None) -> list[dict]:
    """Renvoie tous les chunks d'un cours de l'étudiant, triés par numéro de page."""
    chunks, offset = [], None
    while True:
        points, offset = client.scroll(
            COLLECTION,
            scroll_filter=_filter(course, user_id),
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        chunks.extend(_readable(p.payload) for p in points)
        if offset is None:
            return sorted(chunks, key=lambda c: c["page"])

if __name__ == "__main__":
    from app.phase2_embeddings.embeddings import embed_passages, embed_query

    ensure_collection()

    chunks = [
        {"course": "test", "page": 1, "text": "Un CNN utilise des couches de convolution pour extraire des caractéristiques d'images."},
        {"course": "test", "page": 2, "text": "Le surapprentissage arrive quand le modèle mémorise les données d'entraînement."},
        {"course": "test", "page": 3, "text": "La descente de gradient met à jour les poids pour minimiser la perte."},
    ]
    upsert(chunks, embed_passages([c["text"] for c in chunks]))
    print("Cours :", list_courses())

    for hit in search(embed_query("Comment fonctionne un réseau convolutif ?"), k=2, course="test", user_id=None):
        print(f"p.{hit['page']}  score={hit['score']:.3f}  {hit['text'][:60]}...")

    delete_course("test", user_id=None)
    print("Après nettoyage :", list_courses())