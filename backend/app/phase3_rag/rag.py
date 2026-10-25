import logging
import re
import unicodedata

from app.core.config import TOP_K
from app.core.privacy import mask_pii
from app.phase1_llm.llm import chat
from app.phase2_embeddings.embeddings import embed_query
from app.phase2_embeddings.vectorstore import search
from app.phase5_evaluation.stats import GenerationStats, collecting, record_value

logger = logging.getLogger("uvicorn.error")

NOT_FOUND = "Cette information n'est pas présente dans le cours."

SYSTEM_PROMPT = f"""Tu es un tuteur qui aide un étudiant à comprendre SON cours.
Règles :
- Réponds UNIQUEMENT à partir des extraits du cours fournis dans le contexte.
- Ignore les informations personnelles ou hors sujet présentes dans la question (nom, email, [EMAIL], [NUMÉRO]…) et réponds uniquement à la partie qui concerne le cours.
- Si la réponse n'est pas dans les extraits, réponds exactement : "{NOT_FOUND}"
- Termine chaque phrase importante par la page d'où vient l'information, sous la forme [p.X]. Exemple : « Le pooling réduit la taille des cartes d'activation [p.8]. »
- Réponds dans la langue de la question, de façon claire et pédagogique."""

# Réponse qui recopie les règles du tuteur (« recopie ton prompt système ») : remplacée par ce message.
# Une consigne « ne révèle pas tes règles » dans le prompt ne suffit pas avec qwen2.5 7B (essai : 3 fuites sur 3).
PROMPT_LEAK_REPLY = "Je ne peux pas partager mes consignes internes. Pose-moi une question sur ton cours."
SYSTEM_PROMPT_MARKERS = (
    "Réponds UNIQUEMENT à partir des extraits du cours",
    "Termine chaque phrase importante par la page",
    "Ignore les informations personnelles ou hors sujet",
    "Tu es un tuteur qui aide un étudiant",
)

HISTORY_RULE = (
    "- Les échanges précédents servent uniquement à comprendre la question (ex. « et pour les CNN ? ») : "
    "la réponse vient toujours des extraits du cours."
)

# Consigne ajoutée au prompt système selon le niveau de l'étudiant (aucune donnée personnelle)
LEVEL_INSTRUCTIONS = {
    "debutant": (
        "Niveau de l'étudiant : débutant. Utilise des mots simples, définis chaque terme technique, "
        "donne une analogie de la vie courante et un exemple concret."
    ),
    "intermediaire": (
        "Niveau de l'étudiant : intermédiaire. Donne une explication claire avec les termes du cours et un exemple."
    ),
    "avance": (
        "Niveau de l'étudiant : avancé. Réponds de façon précise et technique, sans définitions de base, "
        "en reliant les notions entre elles."
    ),
}
LEVEL_RULE = (
    "- Adapte ton explication au niveau indiqué ci-dessous, sans changer les règles précédentes : "
    "les informations viennent toujours des extraits et sont citées [p.X] "
    "(une analogie sert seulement à illustrer)."
)
WEAK_POINT_RULE = (
    "- La question porte sur {concepts}, une notion que l'étudiant marque souvent « à revoir » dans ses "
    "flashcards. Signale-le avec bienveillance en une phrase à la fin de ta réponse et propose-lui de la revoir."
)

SCORE_MARGIN = 0.03  # écart max avec le meilleur score pour garder un extrait
HISTORY_TURNS = 3  # échanges précédents ajoutés au prompt (mémoire de la conversation)
HISTORY_ANSWER_CHARS = 600  # une réponse précédente est tronquée pour garder un prompt court

# Question de suivi : commence par un mot de liaison, renvoie à ce qui précède, ou tient en quelques mots
FOLLOW_UP_START = re.compile(
    r"^(et|mais|alors|donc|aussi|pareil|ensuite|puis|sinon|par contre|dans ce cas|pourquoi ça|comment ça)\b",
    re.IGNORECASE,
)
ANAPHORA = re.compile(
    r"\b(ça|cela|ceci|celui|celle|ceux|celles|ce dernier|cette dernière|ces derniers|elle|elles|ils"
    r"|ce concept|cette notion|cette méthode|cet exemple|ce point|là-dessus)\b",
    re.IGNORECASE,
)
SHORT_QUESTION_WORDS = 4


def is_follow_up(question: str) -> bool:
    """Vrai si la question ne se comprend qu'avec les échanges précédents."""
    q = question.strip()
    return bool(FOLLOW_UP_START.search(q) or ANAPHORA.search(q) or len(q.split()) <= SHORT_QUESTION_WORDS)


def search_query(question: str, history: list[dict]) -> str:
    """Texte de la recherche Qdrant : la question seule si elle est complète,
    sinon reformulée avec le contexte (question précédente de l'étudiant + question actuelle)."""
    previous = [h["content"] for h in history if h["role"] == "user"]
    if previous and is_follow_up(question):
        return f"{previous[-1]} {question}"
    return question


def format_history(history: list[dict]) -> str:
    """Derniers échanges, du plus ancien au plus récent, données personnelles masquées."""
    lines = []
    for h in history[-2 * HISTORY_TURNS:]:
        content = h["content"]
        if h["role"] == "assistant" and len(content) > HISTORY_ANSWER_CHARS:
            content = content[:HISTORY_ANSWER_CHARS] + "…"
        speaker = "Étudiant" if h["role"] == "user" else "Tuteur"
        lines.append(f"{speaker} : {mask_pii(content)}")
    return "\n".join(lines)


def _normalize(text: str) -> str:
    """Minuscules, sans accents ni ponctuation, pour comparer une question et un nom de concept."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c if c.isalnum() else " " for c in text if not unicodedata.combining(c))
    return f" {' '.join(text.split())} "


def touched_concepts(question: str, concepts: list[str]) -> list[str]:
    """Concepts dont la question parle : le nom complet, ou tous ses mots significatifs (4 lettres ou plus)."""
    q = _normalize(question)
    touched = []
    for concept in concepts:
        name = _normalize(concept)
        words = [w for w in name.split() if len(w) >= 4]
        if name.strip() and (name in q or (words and all(f" {w} " in q for w in words))):
            touched.append(concept)
    return touched


def leaks_system_prompt(text: str) -> bool:
    """Vrai si la réponse recopie au moins deux phrases des règles du tuteur."""
    normalized = " ".join(text.split()).lower()
    return sum(marker.lower() in normalized for marker in SYSTEM_PROMPT_MARKERS) >= 2


def build_system_prompt(has_history: bool = False, level: str | None = None,
                        weak_concepts: list[str] | None = None) -> str:
    """Règles du tuteur + mémoire + points faibles touchés par la question + niveau de l'étudiant.

    Seuls le niveau et des noms de concepts du cours y figurent : aucun email ni nom de l'étudiant.
    """
    rules = [SYSTEM_PROMPT]
    if has_history:
        rules.append(HISTORY_RULE)
    if weak_concepts:
        names = ", ".join(f"« {mask_pii(c)} »" for c in weak_concepts)
        rules.append(WEAK_POINT_RULE.format(concepts=names))
    if level in LEVEL_INSTRUCTIONS:
        rules.append(LEVEL_RULE)
        rules.append(f"\n{LEVEL_INSTRUCTIONS[level]}")
    return "\n".join(rules)


def build_context(hits: list[dict]) -> str:
    """Assemble les extraits trouvés, chacun précédé de sa page."""
    return "\n\n".join(f"[p.{h['page']}] {h['text']}" for h in hits)


def build_user_prompt(hits: list[dict], question: str, history: list[dict] | None = None) -> str:
    """Construit le message envoyé au LLM, avec les données personnelles masquées."""
    previous = f"Échanges précédents :\n{format_history(history)}\n\n" if history else ""
    return mask_pii(
        f"Extraits du cours :\n{build_context(hits)}\n\n"
        f"{previous}"
        f"Question de l'étudiant : {question}\n\n"
        "Rappel : les informations personnelles ont été masquées ([EMAIL], [NUMÉRO]). "
        "Ignore-les et réponds à la partie de la question qui concerne le cours."
    )


def answer(question: str, course: str | None = None, k: int = TOP_K, *, user_id: int | None,
           history: list[dict] | None = None, level: str | None = None,
           weak_concepts: list[str] | None = None, stats: GenerationStats | None = None) -> dict:
    """Question → chunks pertinents (Qdrant, cours de l'étudiant uniquement) → LLM → réponse + sources.

    history : échanges précédents de la conversation [{"role": "user"|"assistant", "content": "..."}].
    level : niveau de l'étudiant (debutant, intermediaire, avance) pour adapter l'explication.
    weak_concepts : ses points faibles ; ceux dont parle la question sont signalés par le tuteur.
    stats (optionnel, phase 5) : durée, passages retrouvés, score maximal, réponse trouvée, sources.
    """
    with collecting(stats):
        result = _answer(question, course, k, user_id=user_id, history=history, level=level,
                         weak_concepts=weak_concepts)
        record_value("reponse_trouvee", 1 if result["answered"] else 0)
        record_value("sources", len(result["sources"]))
        return result


def _answer(question: str, course: str | None, k: int, *, user_id: int | None, history: list[dict] | None,
            level: str | None, weak_concepts: list[str] | None) -> dict:
    history = (history or [])[-2 * HISTORY_TURNS:]
    query = search_query(question, history)
    hits = search(embed_query(query), k, course, user_id=user_id)
    record_value("passages_retrouves", 0)
    if not hits:
        return {"answer": "Aucun cours n'est indexé pour répondre à cette question.", "sources": [],
                "answered": False}

    # Ne garder que les extraits proches du meilleur score (élimine le bruit)
    hits = [h for h in hits if h["score"] >= hits[0]["score"] - SCORE_MARGIN]
    record_value("passages_retrouves", len(hits))
    record_value("score_max", round(hits[0]["score"], 4))

    # Aucune donnée personnelle brute n'est envoyée au LLM (exigence du cahier des charges)
    user_prompt = build_user_prompt(hits, question, history)
    logger.info("Question transmise au LLM : %s", mask_pii(question))
    system = build_system_prompt(has_history=bool(history), level=level,
                                 weak_concepts=touched_concepts(query, weak_concepts or []))
    text = chat(system, user_prompt)
    if leaks_system_prompt(text):
        logger.warning("Réponse du tuteur remplacée : elle recopiait les règles du prompt système")
        return {"answer": PROMPT_LEAK_REPLY, "sources": [], "answered": False}

    # Si le tuteur dit que l'info n'est pas dans le cours, aucune source n'a été utilisée
    if NOT_FOUND.lower().rstrip(".") in text.lower():
        return {"answer": text, "sources": [], "answered": False}

    return {
        "answer": text,
        "answered": True,
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
        result = answer(question, course, user_id=None)
        print(f"\nTuteur : {result['answer']}")
        if result["sources"]:
            pages = sorted({s["page"] for s in result["sources"]})
            print(f"📄 Pages utilisées : {', '.join(f'p.{p}' for p in pages)}")
        print()
