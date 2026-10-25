import json
import logging
import random
import time
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel, ValidationError

from app.core.passages import format_course
from app.core.privacy import mask_pii
from app.phase1_llm.llm import LLMError, chat
from app.phase2_embeddings.embeddings import embed_passages
from app.phase2_embeddings.vectorstore import get_course_chunks
from app.phase4_exam.schemas import (
    BoolAnswers, Difficulty, Exam, ExamFormat, ExamSection, LetterAnswers, MCQBatch, MCQQuestion,
    OpenBatch, OpenQuestion, ShortAnswerBatch, ShortAnswerQuestion, TrueFalseBatch, TrueFalseQuestion,
)
from app.phase5_evaluation.stats import GenerationStats, collecting, record, record_value, reject

logger = logging.getLogger("uvicorn.error")

CALLS_PER_QUESTION = 5      # budget d'appels au LLM par question demandée (échecs et rejets compris)
SIMILARITY_THRESHOLD = 0.96  # au-dessus, deux questions sont considérées comme des doublons (même sens)
CATCH_UP_SIMILARITY = 0.985  # en fin de budget, seules les questions quasi identiques sont refusées
EXAM_MIN_CHUNK_CHARS = 250   # en dessous (titres, schémas), les questions générées sont ambiguës
LETTERS = "ABCD"

SYSTEM_PROMPT = (
    "Tu es un enseignant qui rédige des sujets d'examen à partir d'un cours. "
    "Tu réponds UNIQUEMENT avec un objet JSON valide et compact, sans aucun texte autour."
)
VERIFY_SYSTEM_PROMPT = (
    "Tu es un étudiant rigoureux qui répond uniquement à partir du cours fourni. "
    "Tu réponds UNIQUEMENT avec un objet JSON valide."
)

DIFFICULTY_HINTS = {
    "facile": "niveau facile : définitions et reconnaissance directe d'une notion du cours",
    "moyen": "niveau moyen : compréhension, en reliant deux notions du cours",
    "difficile": "niveau difficile : application et analyse, avec des pièges proches de la bonne réponse",
}

COMMON_RULES = """- Chaque question porte sur une information précise présente dans le cours ci-dessus.
- Utilise uniquement les exemples cités dans le cours : n'en invente aucun.
- "page" est le numéro de la page d'où vient l'information.
- N'utilise jamais les mots « extraits » ou « contenu » : écris « selon le cours » si nécessaire.
- Rédige TOUT en français, y compris les réponses attendues et les corrections : traduis le cours s'il est en anglais.
- Une question ne contient jamais sa propre réponse (elle doit vraiment interroger l'étudiant).
- Jamais de question « combien », jamais de négation (« ne … pas »), jamais deux questions en une seule.
- Écris un JSON compact, sans espaces ni retours à la ligne inutiles."""


# ---------------------------------------------------------------------------
# Description de chaque type de question
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TypeSpec:
    item_model: type[BaseModel]
    batch_model: type[BaseModel]
    window: int          # nombre de passages consécutifs donnés au LLM pour une question
    max_tokens: int
    rules: str           # consignes propres au type
    example: str         # format JSON attendu


TYPE_SPECS: dict[str, TypeSpec] = {
    "qcm": TypeSpec(
        item_model=MCQQuestion, batch_model=MCQBatch, window=1, max_tokens=500,
        rules="""Rédige exactement 1 question QCM, sur une information du passage ci-dessus.
- La question est formulée de façon affirmative : jamais « lequel n'est PAS… » ni « quel élément n'est pas mentionné ».
- Il doit y avoir UNE SEULE bonne réponse. Les 3 autres choix doivent être clairement faux d'après le cours.
- Si le cours cite plusieurs éléments valables (une liste d'exemples), aucun autre élément de cette liste ne doit apparaître comme mauvaise réponse.
- Interdit : les choix du type « Tous les éléments mentionnés », « Toutes les réponses », « Aucune de ces réponses ».
- Les 4 choix sont courts, de longueur comparable et tous différents.
- Les mauvaises réponses sont plausibles et du même domaine que la bonne (jamais absurdes, comme des couleurs).
- "answer" est la lettre de la bonne réponse : A, B, C ou D.
- "explanation" explique en une phrase POURQUOI la bonne réponse est correcte, comme un enseignant.""",
        example='{"items":[{"question":"...","choices":["...","...","...","..."],"answer":"B","explanation":"...","page":12}]}',
    ),
    "vrai_faux": TypeSpec(
        item_model=TrueFalseQuestion, batch_model=TrueFalseBatch, window=1, max_tokens=300,
        rules="""Rédige exactement 1 affirmation, tirée du passage ci-dessus, que l'étudiant devra juger vraie ou fausse.
- Elle doit être {truth}.
- Une affirmation fausse ne doit jamais être absurde : elle reste plausible.
- "answer" vaut true si l'affirmation est vraie, false sinon.
- "correction" justifie la réponse en une phrase ; pour une affirmation fausse, donne la version correcte.""",
        example='{"items":[{"statement":"...","answer":false,"correction":"...","page":12}]}',
    ),
    "courte": TypeSpec(
        item_model=ShortAnswerQuestion, batch_model=ShortAnswerBatch, window=1, max_tokens=300,
        rules="""Rédige exactement 1 question à réponse courte, sur le passage ci-dessus.
- Elle porte sur UNE notion précise : une définition, une signification, un rôle ou un exemple.
- La réponse doit tenir en une ou deux phrases et se trouver clairement dans le cours.
- "expected_answer" est la réponse attendue, rédigée comme dans un corrigé.""",
        example='{"items":[{"question":"...","expected_answer":"...","page":12}]}',
    ),
    "ouverte": TypeSpec(
        item_model=OpenQuestion, batch_model=OpenBatch, window=3, max_tokens=600,
        rules="""Rédige exactement 1 question de réflexion, à partir des passages ci-dessus.
- C'est UNE seule question cohérente sur un thème précis (par exemple comparer deux notions), jamais plusieurs questions juxtaposées.
- La question tient en une ou deux phrases et ne contient NI la réponse NI d'explication.
- Elle demande de relier plusieurs notions du cours et de les expliquer, idéalement avec un exemple.
- "expected_points" contient EXACTEMENT 4 éléments de réponse attendus, chacun noté 1 point, tous tirés du cours.
- Chaque élément de réponse apporte une connaissance du cours (une phrase explicative) : il ne répète jamais les mots de la question.""",
        example='{"items":[{"question":"...","expected_points":["...","...","...","..."],"page":12}]}',
    ),
}


# ---------------------------------------------------------------------------
# Structure de l'examen (toujours noté sur 20)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SectionPlan:
    kind: str
    title: str
    instructions: str
    count: int
    points: float   # points par question


def plan_exam(fmt: ExamFormat, num_questions: int = 20) -> list[SectionPlan]:
    """Parties de l'examen et barème. Les deux formats totalisent 20 points."""
    if fmt == "qcm":
        return [SectionPlan("qcm", "QCM", "Cochez une seule réponse par question.",
                            num_questions, 20 / num_questions)]
    return [
        SectionPlan("qcm", "QCM", "Cochez une seule réponse par question.", 8, 1),
        SectionPlan("vrai_faux", "Vrai ou Faux, justifiez",
                    "Cochez Vrai ou Faux, puis justifiez votre réponse en une phrase.", 4, 1),
        SectionPlan("courte", "Questions à réponse courte", "Répondez en une ou deux phrases.", 2, 2),
        SectionPlan("ouverte", "Question de réflexion",
                    "Rédigez une réponse structurée et argumentée, avec un exemple.", 1, 4),
    ]


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------

def passage_window(chunks: list[dict], index: int, size: int) -> list[dict]:
    """Le passage choisi, avec ses voisins immédiats si le type de question demande plus de contexte."""
    start = max(0, min(index - size // 2, len(chunks) - size))
    return chunks[start:start + size]


def question_text(question: BaseModel) -> str:
    """Texte principal d'une question, quel que soit son type."""
    return question.statement if isinstance(question, TrueFalseQuestion) else question.question


def build_prompt(kind: str, context: list[dict], difficulty: Difficulty, avoid: list[str], want_true: bool) -> str:
    """Construit la consigne de génération pour un type de question (données personnelles masquées)."""
    spec = TYPE_SPECS[kind]
    already = "\n".join(f"- {q}" for q in avoid[-10:]) or "- (aucune)"
    truth = "VRAIE selon le cours" if want_true else "FAUSSE : elle modifie un seul détail précis du cours"
    prompt = f"""Cours (chaque passage commence par sa page) :
{format_course(context)}

{spec.rules.replace("{truth}", truth)}
- Questions en français, {DIFFICULTY_HINTS[difficulty]}.
{COMMON_RULES}
- Ne pose pas une question déjà posée :
{already}

Format attendu :
{spec.example}"""
    return mask_pii(prompt)


def parse_items(kind: str, raw: str, allowed_pages: list[int]) -> list[BaseModel]:
    """Lit le JSON du LLM et ne garde que les questions qui passent la validation Pydantic."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Réponse du LLM qui n'est pas du JSON valide, lot ignoré")
        reject("validation", kind)
        return []

    items = data.get("items", []) if isinstance(data, dict) else []
    valid = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item.pop("type", None)  # le type est imposé par le code, pas par le modèle
        try:
            question = TYPE_SPECS[kind].item_model.model_validate(item)
        except ValidationError as e:
            logger.info("Question %s rejetée : %s", kind, e.errors()[0]["msg"])
            reject("validation", kind)
            continue
        # Si le modèle se trompe de page, on prend la page la plus proche parmi celles fournies
        if question.page not in allowed_pages:
            nearest = min(allowed_pages, key=lambda p: abs(p - question.page))
            question = question.model_copy(update={"page": nearest})
        valid.append(question)
    return valid


# ---------------------------------------------------------------------------
# Auto-vérification : le modèle répond aux questions SANS le corrigé
# ---------------------------------------------------------------------------

def verify_mcq(questions: list[MCQQuestion], context: list[dict]) -> list[MCQQuestion]:
    """Ne garde que les QCM où le modèle retrouve la même réponse que le corrigé."""
    listing = "\n\n".join(
        f"Q{i}. {q.question}\n" + "\n".join(f"{letter}. {choice}" for letter, choice in zip(LETTERS, q.choices))
        for i, q in enumerate(questions, start=1)
    )
    prompt = mask_pii(
        f"Cours :\n{format_course(context)}\n\nQCM :\n{listing}\n\n"
        f"Pour chacune des {len(questions)} questions, dans l'ordre, donne la lettre de la seule bonne réponse "
        'selon le cours. Format : {"answers":["A","C"]}'
    )
    try:
        raw = chat(VERIFY_SYSTEM_PROMPT, prompt, max_tokens=100, temperature=0,
                   json_schema=LetterAnswers.model_json_schema())
        answers = LetterAnswers.model_validate_json(raw).answers
    except (LLMError, ValidationError) as e:
        logger.warning("Vérification QCM impossible, questions gardées sans contrôle : %s", e)
        record("verifications_impossibles")
        return questions
    return _keep_matching(questions, answers, [q.answer for q in questions])


def verify_true_false(questions: list[TrueFalseQuestion], context: list[dict]) -> list[TrueFalseQuestion]:
    """Ne garde que les affirmations où le modèle retrouve la même réponse (vrai ou faux) que le corrigé."""
    listing = "\n".join(f"A{i}. {q.statement}" for i, q in enumerate(questions, start=1))
    prompt = mask_pii(
        f"Cours :\n{format_course(context)}\n\nAffirmations :\n{listing}\n\n"
        f"Pour chacune des {len(questions)} affirmations, dans l'ordre, réponds true si elle est vraie "
        'selon le cours, false sinon. Format : {"answers":[true,false]}'
    )
    try:
        raw = chat(VERIFY_SYSTEM_PROMPT, prompt, max_tokens=60, temperature=0,
                   json_schema=BoolAnswers.model_json_schema())
        answers = BoolAnswers.model_validate_json(raw).answers
    except (LLMError, ValidationError) as e:
        logger.warning("Vérification Vrai/Faux impossible, affirmations gardées sans contrôle : %s", e)
        record("verifications_impossibles")
        return questions
    return _keep_matching(questions, answers, [q.answer for q in questions])


def _keep_matching(questions: list, given: list, expected: list) -> list:
    given = given[:len(questions)]  # le modèle renvoie parfois une réponse de trop : on l'ignore
    if len(given) != len(questions):
        logger.warning("Vérification incomplète (%d réponses pour %d questions), lot gardé",
                       len(given), len(questions))
        record("verifications_impossibles")
        return questions
    kept = []
    for question, got, want in zip(questions, given, expected):
        if got == want:
            kept.append(question)
        else:
            logger.info("Question écartée (corrigé %s, vérification %s) : %s",
                        want, got, question_text(question)[:70])
            reject("verification", question.type)
    return kept


def verify_written(question: ShortAnswerQuestion | OpenQuestion, context: list[dict]) -> bool:
    """Réponses rédigées : le modèle juge si la réponse attendue est correcte ET répond bien à la question."""
    if isinstance(question, ShortAnswerQuestion):
        expected = question.expected_answer
    else:
        expected = " ; ".join(question.expected_points)
    prompt = mask_pii(
        f"Cours :\n{format_course(context)}\n\nQuestion : {question.question}\nRéponse attendue : {expected}\n\n"
        "La réponse attendue est-elle correcte selon le cours ET répond-elle exactement à la question posée ? "
        'Format : {"answers":[true]} ou {"answers":[false]}'
    )
    try:
        raw = chat(VERIFY_SYSTEM_PROMPT, prompt, max_tokens=20, temperature=0,
                   json_schema=BoolAnswers.model_json_schema())
        verdict = BoolAnswers.model_validate_json(raw).answers[0]
    except (LLMError, ValidationError) as e:
        logger.warning("Vérification impossible, question gardée sans contrôle : %s", e)
        record("verifications_impossibles")
        return True
    if not verdict:
        logger.info("Question écartée (réponse attendue jugée incorrecte) : %s", question.question[:70])
        reject("verification", question.type)
    return verdict


def verify(kind: str, questions: list, context: list[dict]) -> list:
    """Chaque type de question est vérifié avant d'entrer dans l'examen."""
    if not questions:
        return []
    if kind == "qcm":
        return verify_mcq(questions, context)
    if kind == "vrai_faux":
        return verify_true_false(questions, context)
    return [q for q in questions if verify_written(q, context)]

def shuffle_choices(question: MCQQuestion, rng: random.Random) -> MCQQuestion:
    """Mélange les choix pour que la bonne réponse ne soit pas toujours à la même position."""
    correct = question.choices[LETTERS.index(question.answer)]
    choices = question.choices[:]
    rng.shuffle(choices)
    return question.model_copy(update={"choices": choices, "answer": LETTERS[choices.index(correct)]})


# ---------------------------------------------------------------------------
# Génération
# ---------------------------------------------------------------------------

def is_duplicate(vector: list[float], seen_vectors: list[list[float]], threshold: float) -> bool:
    """Deux questions de même sens (même si la formulation change) sont des doublons."""
    if not seen_vectors:
        return False
    return float(np.max(np.array(seen_vectors) @ np.array(vector))) >= threshold


def generate_section(plan: SectionPlan, chunks: list[dict], difficulty: Difficulty, asked: list[str],
                     seen_vectors: list[list[float]], used: set[int], rng: random.Random) -> tuple[list, LLMError | None]:
    """Génère les questions d'une partie, UNE par passage du cours, sans doublons de sens.

    Ancrer chaque question sur un passage différent force le modèle à varier les notions interrogées
    et répartit naturellement l'examen sur tout le cours.
    """
    spec = TYPE_SPECS[plan.kind]
    order = list(range(len(chunks)))
    rng.shuffle(order)
    order.sort(key=lambda i: i in used)  # les passages pas encore utilisés par une autre partie d'abord
    budget = plan.count * CALLS_PER_QUESTION
    questions: list = []
    last_error: LLMError | None = None
    calls = 0
    record(f"demandees_{plan.kind}", plan.count)

    for index in order * 2:  # deux passages sur le cours au maximum
        if len(questions) >= plan.count or calls >= budget:
            break
        context = passage_window(chunks, index, spec.window)
        allowed_pages = sorted({c["page"] for c in context})
        # Vrai/Faux : on alterne vrai et faux pour équilibrer la partie
        want_true = len(questions) % 2 == 0
        # En fin de budget, on n'écarte plus que les questions quasi identiques
        threshold = SIMILARITY_THRESHOLD if calls < budget * 2 / 3 else CATCH_UP_SIMILARITY
        prompt = build_prompt(plan.kind, context, difficulty, asked, want_true)
        calls += 1
        record("appels_generation")

        try:
            raw = chat(SYSTEM_PROMPT, prompt, max_tokens=spec.max_tokens, temperature=0.5,
                       json_schema=spec.batch_model.model_json_schema())
        except LLMError as e:
            # Un appel raté (boucle du modèle, réponse vide…) ne doit pas faire échouer tout l'examen
            logger.warning("Appel %s ignoré : %s", plan.kind, e)
            record("erreurs_llm")
            last_error = e
            continue

        candidates = verify(plan.kind, parse_items(plan.kind, raw, allowed_pages)[:1], context)
        if not candidates:
            continue
        question = candidates[0]
        vector = embed_passages([question_text(question)])[0]
        if is_duplicate(vector, seen_vectors, threshold):
            logger.info("Question écartée (doublon de sens) : %s", question_text(question)[:70])
            reject("doublon", plan.kind)
            continue

        seen_vectors.append(vector)
        asked.append(question_text(question))
        used.add(index)
        questions.append(shuffle_choices(question, rng) if plan.kind == "qcm" else question)

    if len(questions) < plan.count:
        logger.warning("Partie « %s » incomplète : %d/%d questions après %d appels",
                       plan.title, len(questions), plan.count, calls)
    return questions, last_error


def generate_exam(course: str, fmt: ExamFormat = "complet", num_questions: int = 20,
                  difficulty: Difficulty = "moyen", user_id: int | None = None,
                  stats: GenerationStats | None = None) -> Exam:
    """Génère un examen noté sur 20, réparti sur l'ensemble du cours (de l'étudiant user_id).

    stats (optionnel, phase 5) : collecteur rempli pendant la génération (appels, rejets, durée).
    """
    with collecting(stats):
        return _generate_exam(course, fmt, num_questions, difficulty, user_id)


def _generate_exam(course: str, fmt: ExamFormat, num_questions: int, difficulty: Difficulty,
                   user_id: int | None) -> Exam:
    chunks = get_course_chunks(course, user_id)
    if not chunks:
        raise LookupError(f"Le cours « {course} » est introuvable ou vide.")
    # Les slides très courtes (titres, schémas) donnent des questions ambiguës, voire un corrigé faux
    chunks = [c for c in chunks if len(c["text"]) >= EXAM_MIN_CHUNK_CHARS] or chunks
    record_value("passages", len(chunks))

    plans = plan_exam(fmt, num_questions)
    rng = random.Random()  # noqa: S311 — mélange des passages et des choix, sans enjeu de sécurité
    asked: list[str] = []
    seen_vectors: list[list[float]] = []
    used: set[int] = set()
    results: dict[str, list] = {}
    last_error: LLMError | None = None
    t0 = time.perf_counter()

    for plan in plans:
        questions, error = generate_section(plan, chunks, difficulty, asked, seen_vectors, used, rng)
        last_error = error or last_error
        results[plan.kind] = questions

    # Examen complet : s'il manque des points (questions écartées), on complète avec des Vrai/Faux à 1 point,
    # le type le plus fiable à générer et à vérifier, pour que l'examen soit toujours noté sur 20.
    if fmt == "complet":
        missing = round(20 - sum(p.points * len(results[p.kind]) for p in plans))
        if missing > 0:
            tf_plan = next(p for p in plans if p.kind == "vrai_faux")
            logger.info("Complément : %d affirmation(s) Vrai/Faux pour atteindre 20 points", missing)
            extra_plan = SectionPlan(tf_plan.kind, tf_plan.title, tf_plan.instructions, missing, tf_plan.points)
            extra, error = generate_section(extra_plan, chunks, difficulty, asked, seen_vectors, used, rng)
            last_error = error or last_error
            results["vrai_faux"].extend(extra)

    sections: list[ExamSection] = []
    for plan in plans:
        if not results[plan.kind]:
            logger.warning("Partie « %s » vide : aucune question valide générée", plan.title)
            continue
        sections.append(ExamSection(
            letter=LETTERS[len(sections)], title=plan.title, instructions=plan.instructions,
            points_per_question=plan.points, questions=results[plan.kind],
        ))

    if not sections:
        # Tout a échoué : on renvoie la vraie cause (ex. Ollama arrêté) si on la connaît
        if last_error:
            raise last_error
        raise ValueError("Le modèle n'a produit aucune question valide. Réessaie.")

    exam = Exam(course=course, difficulty=difficulty, format=fmt,
                expected_questions=sum(p.count for p in plans), sections=sections)
    logger.info("Examen « %s » (%s) : %d/%d questions, %g/20 points, en %.1f s",
                course, fmt, exam.question_count, exam.expected_questions, exam.total_points,
                time.perf_counter() - t0)
    return exam

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    course = sys.argv[1] if len(sys.argv) > 1 else "Chapter1_Part_1"
    fmt = sys.argv[2] if len(sys.argv) > 2 else "complet"
    level = sys.argv[3] if len(sys.argv) > 3 else "moyen"

    exam = generate_exam(course, fmt, 20, level)
    print(f"\n📝 Examen « {exam.course} » — {exam.format} — {exam.difficulty} — "
          f"{exam.question_count} questions — {exam.total_points:g}/20\n")
    number = 1
    for section in exam.sections:
        print(f"=== Partie {section.letter} — {section.title} ({section.total_points:g} pts) ===\n")
        for q in section.questions:
            if isinstance(q, MCQQuestion):
                print(f"{number}. {q.question}")
                for letter, choice in zip(LETTERS, q.choices):
                    print(f"   {letter}. {choice}")
                print(f"   ✔ {q.answer} — {q.explanation} (p.{q.page})\n")
            elif isinstance(q, TrueFalseQuestion):
                print(f"{number}. {q.statement}")
                print(f"   ✔ {'Vrai' if q.answer else 'Faux'} — {q.correction} (p.{q.page})\n")
            elif isinstance(q, ShortAnswerQuestion):
                print(f"{number}. {q.question}")
                print(f"   ✔ {q.expected_answer} (p.{q.page})\n")
            elif isinstance(q, OpenQuestion):
                print(f"{number}. {q.question}")
                for point in q.expected_points:
                    print(f"   • {point} (1 pt)")
                print(f"   (p.{q.page})\n")
            number += 1