
from uuid import uuid4
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, FilterSelector,
)
from app.core.config import QDRANT_URL, COLLECTION
from app.phase2_embeddings.embeddings import dimension

client = QdrantClient(url=QDRANT_URL)


def _course_filter(course: str) -> Filter:
    return Filter(must=[FieldCondition(key="course", match=MatchValue(value=course))])


def ensure_collection() -> None:
    """Crée la collection si elle n'existe pas encore."""
    if not client.collection_exists(COLLECTION):
        client.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=dimension(), distance=Distance.COSINE),
        )


def upsert(chunks: list[dict], vectors: list[list[float]]) -> None:
    """Stocke chaque chunk (course, page, text) avec son vecteur."""
    points = [
        PointStruct(id=str(uuid4()), vector=v, payload=c)
        for c, v in zip(chunks, vectors)
    ]
    client.upsert(COLLECTION, points=points)


def search(vector: list[float], k: int, course: str | None = None) -> list[dict]:
    """Renvoie les k chunks les plus proches, éventuellement limités à un cours."""
    res = client.query_points(
        COLLECTION,
        query=vector,
        limit=k,
        query_filter=_course_filter(course) if course else None,
        with_payload=True,
    )
    return [{**p.payload, "score": p.score} for p in res.points]


def list_courses() -> list[str]:
    """Liste les noms de cours présents dans Qdrant."""
    courses, offset = set(), None
    while True:
        points, offset = client.scroll(
            COLLECTION, limit=256, offset=offset,
            with_payload=["course"], with_vectors=False,
        )
        courses.update(p.payload["course"] for p in points)
        if offset is None:
            return sorted(courses)


def delete_course(course: str) -> None:
    """Supprime tous les chunks d'un cours (utile pour réindexer ou nettoyer)."""
    client.delete(COLLECTION, points_selector=FilterSelector(filter=_course_filter(course)))



def get_course_chunks(course: str) -> list[dict]:
    """Renvoie tous les chunks d'un cours, triés par numéro de page."""
    chunks, offset = [], None
    while True:
        points, offset = client.scroll(
            COLLECTION,
            scroll_filter=_course_filter(course),
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        chunks.extend(p.payload for p in points)
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

    for hit in search(embed_query("Comment fonctionne un réseau convolutif ?"), k=2, course="test"):
        print(f"p.{hit['page']}  score={hit['score']:.3f}  {hit['text'][:60]}...")

    delete_course("test")
    print("Après nettoyage :", list_courses())