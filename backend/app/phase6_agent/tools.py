"""Outils du Study Companion : chacun appelle une fonction existante avec l'identifiant de l'étudiant connecté.

Le LLM choisit l'outil et ses arguments (cours, thème, nombre…), jamais l'étudiant concerné : user_id, niveau
et cours disponibles viennent du contexte (AgentContext), construit par la route à partir du jeton JWT.

Chaque outil renvoie un ToolOutcome :
- kind / content / payload : le message enregistré dans la conversation (affichage riche du frontend) ;
- llm_summary : un compte rendu court renvoyé au LLM pour sa réponse finale (aucune donnée personnelle) ;
- final : le texte est déjà la réponse (réponse RAG avec ses [p.X], question « quel cours ? »), le LLM ne le
  reformule pas.
"""
import json
import logging
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlmodel import Session

from app.core.privacy import mask_pii
from app.phase1_llm.llm import LLMError, chat
from app.phase3_rag.rag import HISTORY_TURNS, NOT_FOUND, answer
from app.phase4_exam.generator import generate_exam
from app.phase4_exam.schemas import MCQQuestion
from app.phase5_evaluation.stats import GenerationStats
from app.phase5_evaluation.tracking import exam_run, flashcards_run, log_run_async, summary_run, track_tutor
from app.phase7_flashcards.generator import generate_flashcards as generate_deck
from app.phase8_personal.flashcard_history import save_deck
from app.phase8_personal.models import User
from app.phase8_personal.profile import compute_stats, level_suggestion, quiz_stats, weak_points
from app.phase9_summaries.generator import generate_summary
from app.phase9_summaries.models import Summary
from app.phase9_summaries.routes import cached_course_summary, invalidate_course_summaries

logger = logging.getLogger("uvicorn.error")

SOURCE = "agent"  # tag MLflow des générations lancées par l'agent


@dataclass
class AgentContext:
    """Tout ce que les outils savent de l'étudiant (rien de tout cela n'est choisi par le LLM)."""

    session: Session
    user: User
    courses: list[str]
    selected_course: str | None = None
    # Échanges précédents de la conversation [{"role": "user"|"assistant", "content": "..."}]
    history: list[dict] = field(default_factory=list)
    message: str = ""  # message de l'étudiant (texte brut : jamais envoyé tel quel au LLM)
    on_tool: Callable[[str], None] | None = None  # suivi de la tâche de fond (outil en cours)
    on_token: Callable[[str], None] | None = None  # streaming SSE de la réponse du tuteur (ask_course)

    @property
    def user_id(self) -> int:
        return self.user.id

    @property
    def level(self) -> str:
        return self.user.level


@dataclass
class ToolOutcome:
    kind: str  # text | answer | quiz | summary | flashcards | progress
    content: str
    llm_summary: str
    payload: dict | None = None
    sources: list = field(default_factory=list)
    answered: bool = True
    final: bool = False
    ok: bool = True


# ---------------------------------------------------------------------------
# Arguments des outils (validés : un argument invalide rend l'appel invalide → repli)
# ---------------------------------------------------------------------------

def _blank_to_none(value):
    if isinstance(value, str) and value.strip().lower() in ("", "null", "none", "aucun"):
        return None
    return value.strip() if isinstance(value, str) else value


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")


class AskCourseArgs(ToolArgs):
    """Répondre à une question sur le contenu d'un cours (définition, explication, comparaison, exemple)."""

    question: str | None = Field(None, description="La question de l'étudiant, complète et autonome.")
    course: str | None = Field(None, description="Nom du cours, seulement si l'étudiant le précise.")

    clean_blank = field_validator("question", "course", mode="before")(_blank_to_none)


class SummarizeArgs(ToolArgs):
    """Résumer un cours entier, ou expliquer de façon structurée un thème précis du cours (topic)."""

    course: str | None = Field(None, description="Nom du cours, seulement si l'étudiant le précise.")
    topic: str | None = Field(None, description="Thème à expliquer. Vide pour résumer tout le cours.")

    clean_blank = field_validator("course", "topic", mode="before")(_blank_to_none)


class QuizArgs(ToolArgs):
    """Générer un quiz QCM interactif pour s'entraîner sur un cours."""

    course: str | None = Field(None, description="Nom du cours, seulement si l'étudiant le précise.")
    count: Literal[5, 10] = Field(5, description="Nombre de questions : 5 ou 10.")
    difficulty: Literal["facile", "moyen", "difficile"] = Field("moyen", description="Difficulté du quiz.")

    clean_blank = field_validator("course", mode="before")(_blank_to_none)

    @field_validator("count", mode="before")
    @classmethod
    def nearest_count(cls, value):
        try:
            return 5 if int(value) <= 7 else 10
        except (TypeError, ValueError):
            return 5

    @field_validator("difficulty", mode="before")
    @classmethod
    def known_difficulty(cls, value):
        value = _normalize(str(value or "")).strip()
        synonyms = {"facile": "facile", "easy": "facile", "simple": "facile", "moyen": "moyen", "medium": "moyen",
                    "moyenne": "moyen", "difficile": "difficile", "hard": "difficile", "dur": "difficile"}
        return synonyms.get(value, "moyen")


class FlashcardsArgs(ToolArgs):
    """Générer un paquet de flashcards de révision sur un cours (enregistré dans « Mes paquets »)."""

    course: str | None = Field(None, description="Nom du cours, seulement si l'étudiant le précise.")
    count: Literal[10, 20, 30] = Field(10, description="Nombre de cartes : 10, 20 ou 30.")

    clean_blank = field_validator("course", mode="before")(_blank_to_none)

    @field_validator("count", mode="before")
    @classmethod
    def nearest_count(cls, value):
        try:
            return min((10, 20, 30), key=lambda n: abs(n - int(value)))
        except (TypeError, ValueError):
            return 10


class ProgressArgs(ToolArgs):
    """Afficher la progression de l'étudiant : niveau, statistiques, points faibles."""


# ---------------------------------------------------------------------------
# Choix du cours
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c if c.isalnum() else " " for c in text if not unicodedata.combining(c))
    return " ".join(text.split())


def match_course(requested: str | None, courses: list[str]) -> str | None:
    """Le cours de l'étudiant que désigne le LLM (casse, accents et ponctuation ignorés), ou None."""
    if not requested:
        return None
    wanted = _normalize(requested)
    if not wanted:
        return None
    by_name = {_normalize(c): c for c in courses}
    if wanted in by_name:
        return by_name[wanted]
    close = [c for name, c in by_name.items() if wanted in name or (len(name) >= 3 and name in wanted)]
    return close[0] if len(close) == 1 else None


GENERIC_WORDS = {"cours", "chapitre", "chapter", "part", "partie", "intro", "introduction", "les", "des", "the"}


def mentioned(course: str, ctx: AgentContext) -> bool:
    """Le cours est-il nommé dans la demande (ou la précédente) ? Le LLM ne doit pas en choisir un au hasard."""
    said = f" {_normalize(' '.join([ctx.message, *[h['content'] for h in ctx.history[-2:] if h['role'] == 'user']]))} "
    name = _normalize(course)
    words = [w for w in name.split() if len(w) >= 3 and w not in GENERIC_WORDS]
    return f" {name} " in said or any(f" {w} " in said for w in words)


def requested_course(ctx: AgentContext, requested: str | None) -> str | None:
    """Cours proposé par le LLM, retenu seulement s'il existe et si l'étudiant l'a nommé."""
    course = match_course(requested, ctx.courses)
    return course if course is not None and mentioned(course, ctx) else None


def chosen_course(ctx: AgentContext, requested: str | None) -> str | None:
    """Le cours sélectionné dans la page prime toujours : un cours choisi par le LLM ne le remplace jamais
    (il ne sert que si aucun cours n'est sélectionné, et seulement s'il est nommé par l'étudiant)."""
    return ctx.selected_course or requested_course(ctx, requested)


def resolve_course(ctx: AgentContext, requested: str | None) -> tuple[str | None, ToolOutcome | None]:
    """Cours sélectionné dans la page → cours nommé dans la demande → seul cours de l'étudiant.

    Sinon : (None, question « quel cours ? ») avec la liste des cours en payload (boutons de choix).
    """
    course = chosen_course(ctx, requested)
    if course is None and len(ctx.courses) == 1:
        course = ctx.courses[0]
    if course is not None:
        return course, None
    if not ctx.courses:
        text = "Tu n'as encore importé aucun cours. Importe un PDF avec « Importer un cours », puis redemande-moi."
        return None, ToolOutcome(kind="text", content=text, llm_summary="Aucun cours importé.", final=True, ok=False)
    text = "Sur quel cours veux-tu travailler ? Choisis-le ci-dessous ou dans le sélecteur de cours."
    return None, ToolOutcome(kind="text", content=text, llm_summary="Cours à préciser par l'étudiant.",
                             payload={"course_choices": list(ctx.courses)}, final=True, ok=False)


def _failure(what: str, error: Exception) -> ToolOutcome:
    """Erreur prévisible d'un générateur (cours vide, aucune sortie valide) : message clair, pas de 500."""
    text = f"Je n'ai pas pu {what} : {error}"
    return ToolOutcome(kind="text", content=text, llm_summary=f"Échec : {what}.", final=True, ok=False)


def _notify(ctx: AgentContext, tool: str) -> None:
    if ctx.on_tool is not None:
        ctx.on_tool(tool)


# ---------------------------------------------------------------------------
# Les 5 outils
# ---------------------------------------------------------------------------

def ask_course(ctx: AgentContext, question: str | None = None, course: str | None = None) -> ToolOutcome:
    """Tuteur RAG existant : réponse tirée du cours (ou de tous les cours), avec les pages sources [p.X]."""
    _notify(ctx, "ask_course")
    # Sans cours sélectionné ni nommé, le tuteur cherche dans tous les cours de l'étudiant (« Tous les cours »)
    course = chosen_course(ctx, course)
    if not ctx.courses:
        return resolve_course(ctx, None)[1]
    # Question reformulée par le LLM (utile si le message demande plusieurs choses), sinon le message lui-même
    question = question or ctx.message
    weak = [p.concept for p in weak_points(ctx.session, ctx.user_id, course)]
    with track_tutor(course=course, level=ctx.level, source=SOURCE) as stats:
        result = answer(question, course, user_id=ctx.user_id, history=ctx.history[-2 * HISTORY_TURNS:],
                        level=ctx.level, weak_concepts=weak, stats=stats, on_token=ctx.on_token)
    pages = sorted({s["page"] for s in result["sources"]})
    summary = (f"Réponse du cours trouvée (pages {', '.join(map(str, pages))})." if result["answered"]
               else "L'information n'est pas dans le cours.")
    # Hors du cours : seule la phrase NOT_FOUND est gardée (le modèle la complète parfois malgré la consigne)
    content = result["answer"]
    if not result["answered"] and NOT_FOUND.lower().rstrip(".") in content.lower():
        content = NOT_FOUND
    return ToolOutcome(kind="answer", content=content, llm_summary=summary,
                       payload={"course": course}, sources=result["sources"], answered=result["answered"],
                       final=True)


def summarize(ctx: AgentContext, course: str | None = None, topic: str | None = None) -> ToolOutcome:
    """Résumé du cours entier (cache existant réutilisé) ou explication d'un thème, enregistré dans « Résumés »."""
    course, ask = resolve_course(ctx, course)
    if ask:
        return ask
    if topic and _normalize(topic) in {"cours", "le cours", "tout le cours", "resume", _normalize(course)}:
        topic = None
    mode = "topic" if topic else "course"
    _notify(ctx, "summarize")

    summary, cached = None, False
    if mode == "course":
        summary = cached_course_summary(ctx.session, ctx.user_id, course)
        cached = summary is not None
    if summary is None:
        stats = GenerationStats()
        run = {"course": course, "mode": mode, "level": ctx.level, "source": SOURCE}
        try:
            content = generate_summary(course, mode, topic, user_id=ctx.user_id, level=ctx.level, stats=stats)
        except (LookupError, ValueError) as e:
            log_run_async("summary", *summary_run(stats, **run, error=e))
            return _failure("préparer ce résumé", e)
        except Exception as e:
            log_run_async("summary", *summary_run(stats, **run, error=e))
            raise
        log_run_async("summary", *summary_run(stats, **run, content=content))
        if mode == "course":
            invalidate_course_summaries(ctx.session, ctx.user_id, course)
        summary = Summary(user_id=ctx.user_id, course=course, mode=mode, topic=topic, content=content.model_dump())
        ctx.session.add(summary)
        ctx.session.commit()
        ctx.session.refresh(summary)

    payload = {"id": summary.id, "course": summary.course, "mode": summary.mode, "topic": summary.topic,
               "content": summary.content, "created_at": summary.created_at.isoformat(), "cached": cached}
    sections = summary.content.get("sections", [])
    if not summary.content.get("found", True):
        text = f"Ce thème n'est pas abordé dans le cours « {course} »."
        return ToolOutcome(kind="summary", content=text, llm_summary=text, payload=payload)
    what = f"Résumé du cours « {course} »" if mode == "course" else f"Explication du thème dans « {course} »"
    llm_summary = f"{what} prêt : {len(sections)} sections ({', '.join(s['title'] for s in sections[:6])})."
    return ToolOutcome(kind="summary", content=f"{what} : {len(sections)} sections.", llm_summary=llm_summary,
                       payload=payload)


CONCEPTS_SCHEMA = {
    "type": "object",
    "properties": {"concepts": {"type": "array", "items": {"type": "string"}}},
    "required": ["concepts"],
}


def label_concepts(questions: list[MCQQuestion]) -> list[str]:
    """Notion testée par chaque question (2 à 6 mots), pour regrouper les erreurs en points faibles.

    Repli sans erreur : le début de la question, si le LLM échoue ou ne renvoie pas une notion par question.
    """
    fallback = [q.question[:80] for q in questions]
    listing = "\n".join(f"{i}. {q.question}" for i, q in enumerate(questions, start=1))
    prompt = mask_pii(f"""Questions d'un quiz de révision :
{listing}

Pour chaque question, dans l'ordre, donne la notion du cours qu'elle teste, en français, en 2 à 6 mots
(par exemple « Pooling » ou « Fonction d'activation »).
Format attendu : {{"concepts":["...","..."]}}""")
    try:
        raw = chat("Tu réponds UNIQUEMENT avec un objet JSON valide.", prompt, max_tokens=300, temperature=0,
                   json_schema=CONCEPTS_SCHEMA)
        concepts = json.loads(raw)["concepts"]
    except (LLMError, ValueError, KeyError, TypeError) as e:
        logger.warning("Notions du quiz non étiquetées : %s", e)
        return fallback
    if not isinstance(concepts, list) or len(concepts) != len(questions):
        return fallback
    return [" ".join(str(c).split())[:80].strip(" .") or f for c, f in zip(concepts, fallback)]


def generate_quiz(ctx: AgentContext, course: str | None = None, count: int = 5,
                  difficulty: str = "moyen") -> ToolOutcome:
    """QCM interactif : générateur d'examen existant au format « qcm », renvoyé en JSON (pas de PDF)."""
    course, ask = resolve_course(ctx, course)
    if ask:
        return ask
    _notify(ctx, "generate_quiz")
    stats = GenerationStats()
    run = {"course": course, "fmt": "qcm", "difficulty": difficulty, "num_questions": count, "source": SOURCE}
    try:
        exam = generate_exam(course, "qcm", count, difficulty, user_id=ctx.user_id, stats=stats)
    except (LookupError, ValueError) as e:
        log_run_async("exam", *exam_run(stats, **run, error=e))
        return _failure("générer ce quiz", e)
    except Exception as e:
        log_run_async("exam", *exam_run(stats, **run, error=e))
        raise
    log_run_async("exam", *exam_run(stats, **run, exam=exam))

    questions = [q for s in exam.sections for q in s.questions if isinstance(q, MCQQuestion)]
    if not questions:
        return _failure("générer ce quiz", ValueError("le modèle n'a produit aucune question valide."))
    concepts = label_concepts(questions)
    payload = {
        "course": course,
        "difficulty": difficulty,
        "questions": [{**q.model_dump(include={"question", "choices", "answer", "explanation", "page"}),
                       "concept": concept} for q, concept in zip(questions, concepts)],
        "result": None,  # rempli par POST /api/quiz-results
    }
    n = len(questions)
    text = f"Quiz de {n} question{'s' if n > 1 else ''} sur « {course} » ({difficulty})."
    return ToolOutcome(kind="quiz", content=text, payload=payload,
                       llm_summary=f"{text} Notions : {', '.join(dict.fromkeys(concepts))}.")


def generate_flashcards(ctx: AgentContext, course: str | None = None, count: int = 10) -> ToolOutcome:
    """Générateur de flashcards existant ; le paquet est enregistré (deck_id) pour la page Flashcards."""
    course, ask = resolve_course(ctx, course)
    if ask:
        return ask
    _notify(ctx, "generate_flashcards")
    stats = GenerationStats()
    try:
        generated = generate_deck(course, count, user_id=ctx.user_id, stats=stats)
    except (LookupError, ValueError) as e:
        log_run_async("flashcards", *flashcards_run(stats, course=course, count=count, error=e, source=SOURCE))
        return _failure("générer ces flashcards", e)
    except Exception as e:
        log_run_async("flashcards", *flashcards_run(stats, course=course, count=count, error=e, source=SOURCE))
        raise
    log_run_async("flashcards", *flashcards_run(stats, course=course, count=count, deck=generated, source=SOURCE))
    deck = save_deck(ctx.session, ctx.user_id, generated)
    concepts = [card["concept"] for card in deck.cards]
    n = len(concepts)
    text = f"Paquet de {n} flashcard{'s' if n > 1 else ''} prêt pour « {course} »."
    return ToolOutcome(kind="flashcards", content=text, llm_summary=f"{text} Notions : {', '.join(concepts[:10])}.",
                       payload={"deck_id": deck.id, "course": course, "card_count": n, "concepts": concepts})


def get_progress(ctx: AgentContext) -> ToolOutcome:
    """Profil existant : niveau, statistiques (flashcards et quiz), points faibles, suggestion de niveau."""
    _notify(ctx, "get_progress")
    stats = compute_stats(ctx.session, ctx.user_id)
    quiz = quiz_stats(ctx.session, ctx.user_id)
    weak = weak_points(ctx.session, ctx.user_id)
    suggestion = level_suggestion(ctx.session, ctx.user)
    payload = {  # tout le profil sauf l'email
        "level": ctx.level,
        "stats": stats.model_dump(),
        "quiz": quiz.model_dump(),
        "weak_points": [w.model_dump() for w in weak],
        "level_suggestion": suggestion.model_dump() if suggestion else None,
    }
    known = f"{round(stats.known_rate * 100)} %" if stats.known_rate is not None else "aucune révision"
    correct = f"{round(quiz.correct_rate * 100)} %" if quiz.correct_rate is not None else "aucun quiz"
    weak_text = ", ".join(f"{w.concept} ({w.course})" for w in weak) or "aucun"
    llm_summary = (f"Niveau {ctx.level}. {stats.courses} cours, {stats.questions} questions posées, "
                   f"{stats.exams} examens, {stats.cards_reviewed} cartes révisées (réussite {known}), "
                   f"{quiz.answers} réponses de quiz (réussite {correct}). Points faibles : {weak_text}.")
    return ToolOutcome(kind="progress", content="Voici ta progression.", llm_summary=mask_pii(llm_summary),
                       payload=payload)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    args: type[ToolArgs]
    run: Callable[..., ToolOutcome]
    long: bool  # génération longue (1 à 3 minutes) : la route répond par une tâche de fond


TOOLS: dict[str, ToolSpec] = {
    spec.name: spec for spec in (
        ToolSpec("ask_course", AskCourseArgs, ask_course, long=False),
        ToolSpec("summarize", SummarizeArgs, summarize, long=True),
        ToolSpec("generate_quiz", QuizArgs, generate_quiz, long=True),
        ToolSpec("generate_flashcards", FlashcardsArgs, generate_flashcards, long=True),
        ToolSpec("get_progress", ProgressArgs, get_progress, long=False),
    )
}


def openai_tools() -> list[dict]:
    """Description des outils au format « function calling » d'OpenAI (compatible Ollama et Groq)."""
    tools = []
    for spec in TOOLS.values():
        schema = spec.args.model_json_schema()
        schema.pop("title", None)
        schema.pop("description", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
        tools.append({"type": "function", "function": {
            "name": spec.name, "description": spec.args.__doc__.strip(), "parameters": schema}})
    return tools


def validate_call(name: str, args: dict | None) -> dict | None:
    """Arguments validés d'un appel d'outil, ou None si l'outil n'existe pas ou si ses arguments sont invalides."""
    spec = TOOLS.get(name)
    if spec is None:
        return None
    try:
        return spec.args.model_validate(args or {}).model_dump()
    except ValidationError:
        return None


def run_tool(ctx: AgentContext, name: str, args: dict) -> ToolOutcome:
    return TOOLS[name].run(ctx, **args)
