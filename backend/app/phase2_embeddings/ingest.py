import pymupdf
from app.core.config import CHUNK_SIZE, CHUNK_OVERLAP
from app.phase2_embeddings.embeddings import embed_passages
from app.phase2_embeddings.vectorstore import ensure_collection, upsert, delete_course

MIN_CHUNK_CHARS = 120  # en dessous, c'est un titre ou un schéma sans contenu utile


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Découpe un texte en morceaux qui se chevauchent pour ne pas couper une idée en deux."""
    text = " ".join(text.split())  # supprime les espaces et retours à la ligne en trop
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return chunks


def extract_chunks(data: bytes, course: str) -> list[dict]:
    """Lit le PDF page par page et garde le numéro de page de chaque chunk."""
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:
        raise ValueError("Fichier PDF invalide ou corrompu") from e

    chunks = []
    for page_num, page in enumerate(doc, start=1):
        for piece in chunk_text(page.get_text()):
            if len(piece) >= MIN_CHUNK_CHARS:
                chunks.append({"course": course, "page": page_num, "text": piece})
    doc.close()
    return chunks


def ingest_pdf(data: bytes, course: str) -> int:
    """PDF → chunks → embeddings → Qdrant. Renvoie le nombre de chunks indexés."""
    chunks = extract_chunks(data, course)  # lève ValueError si le PDF est invalide
    if not chunks:
        return 0
    ensure_collection()
    delete_course(course)  # réindexer le même cours ne crée pas de doublons
    vectors = embed_passages([c["text"] for c in chunks])
    upsert(chunks, vectors)
    return len(chunks)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    from app.phase2_embeddings.embeddings import embed_query
    from app.phase2_embeddings.vectorstore import search

    if len(sys.argv) < 2:
        print('Usage : python -m app.phase2_embeddings.ingest "chemin\\vers\\cours.pdf"')
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"❌ Fichier introuvable : {path}")
        sys.exit(1)

    course = path.stem
    try:
        n = ingest_pdf(path.read_bytes(), course)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    print(f"✅ Cours « {course} » indexé : {n} chunks")

    if n == 0:
        print("⚠️ Aucun texte extrait : le PDF est probablement scanné (images).")
        sys.exit(0)

    question = input("\nPose une question pour tester la recherche : ")
    for hit in search(embed_query(question), k=3, course=course):
        print(f"\np.{hit['page']}  score={hit['score']:.3f}\n{hit['text'][:200]}...")