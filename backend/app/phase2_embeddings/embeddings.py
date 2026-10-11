from functools import lru_cache
from sentence_transformers import SentenceTransformer
from app.core.config import EMBED_MODEL


@lru_cache
def get_model() -> SentenceTransformer:
    """Charge le modèle une seule fois, puis le garde en mémoire."""
    return SentenceTransformer(EMBED_MODEL)


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Vecteurs pour les morceaux du cours (préfixe 'passage: ' requis par e5)."""
    return get_model().encode(
        [f"passage: {t}" for t in texts], normalize_embeddings=True
    ).tolist()


def embed_query(query: str) -> list[float]:
    """Vecteur pour la question de l'étudiant (préfixe 'query: ' requis par e5)."""
    return get_model().encode(f"query: {query}", normalize_embeddings=True).tolist()

def dimension() -> int:
    return get_model().get_embedding_dimension()


if __name__ == "__main__":
    import numpy as np

    q = embed_query("Qu'est-ce que l'overfitting ?")
    docs = embed_passages([
        "Le surapprentissage arrive quand le modèle mémorise les données d'entraînement.",
        "La recette de la pizza nécessite de la farine et de la tomate.",
    ])
    print("Dimension :", dimension())
    for name, d in zip(["overfitting", "pizza"], docs):
        print(f"Similarité avec '{name}' : {np.dot(q, d):.3f}")