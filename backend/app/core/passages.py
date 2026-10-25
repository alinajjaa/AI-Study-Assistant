def format_course(context: list[dict]) -> str:
    """Passages du cours tels qu'ils entrent dans les prompts : « [page X] texte », séparés par une ligne vide.

    Partagé par les générateurs d'examens, de flashcards et de résumés (le tuteur RAG utilise « [p.X] »).
    """
    return "\n\n".join(f"[page {c['page']}] {c['text']}" for c in context)
