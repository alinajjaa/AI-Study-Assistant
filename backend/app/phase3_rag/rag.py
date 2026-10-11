from app.core.config import TOP_K
from app.phase1_llm.llm import chat
from app.phase2_embeddings.embeddings import embed_query
from app.phase2_embeddings.vectorstore import search

NOT_FOUND = "Cette information n'est pas présente dans le cours."

SYSTEM_PROMPT = f"""Tu es un tuteur qui aide un étudiant à comprendre SON cours.
Règles :
- Réponds UNIQUEMENT à partir des extraits du cours fournis dans le contexte.
- Si la réponse n'est pas dans les extraits, réponds exactement : "{NOT_FOUND}"
- Termine chaque phrase importante par la page d'où vient l'information, sous la forme [p.X]. Exemple : « Le pooling réduit la taille des cartes d'activation [p.8]. »- Réponds dans la langue de la question, de façon claire et pédagogique."""

SCORE_MARGIN = 0.03  # écart max avec le meilleur score pour garder un extrait


def build_context(hits: list[dict]) -> str:
    """Assemble les extraits trouvés, chacun précédé de sa page."""
    return "\n\n".join(f"[p.{h['page']}] {h['text']}" for h in hits)


def answer(question: str, course: str | None = None, k: int = TOP_K) -> dict:
    """Question → chunks pertinents (Qdrant) → LLM → réponse + sources."""
    hits = search(embed_query(question), k, course)
    if not hits:
        return {"answer": "Aucun cours n'est indexé pour répondre à cette question.", "sources": []}

    # Ne garder que les extraits proches du meilleur score (élimine le bruit)
    hits = [h for h in hits if h["score"] >= hits[0]["score"] - SCORE_MARGIN]

    user_prompt = f"Extraits du cours :\n{build_context(hits)}\n\nQuestion : {question}"
    text = chat(SYSTEM_PROMPT, user_prompt)

    # Si le tuteur dit que l'info n'est pas dans le cours, aucune source n'a été utilisée
    if NOT_FOUND.lower().rstrip(".") in text.lower():
        return {"answer": text, "sources": []}

    return {
        "answer": text,
        "sources": [
            {
                "course": h["course"],
                "page": h["page"],
                "score": round(h["score"], 3),
                "excerpt": h["text"][:200],
            }
            for h in hits
        ],
    }


if __name__ == "__main__":
    import sys

    course = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"📚 AI Course Tutor — cours : {course or 'tous'} (tape 'exit' pour quitter)\n")
    while True:
        question = input("Toi : ").strip()
        if question.lower() in ("exit", "quit", ""):
            break
        result = answer(question, course)
        print(f"\nTuteur : {result['answer']}")
        if result["sources"]:
            pages = sorted({s["page"] for s in result["sources"]})
            print(f"📄 Pages utilisées : {', '.join(f'p.{p}' for p in pages)}")
        print()