import json
import logging
import random
import time
from dataclasses import dataclass, field

import numpy as np
from pydantic import BaseModel, ValidationError

from app.core.concurrency import concurrency, parallel_map
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
ROUND_MAX = 4                # candidats au plus par partie et par tour (vérifiés ensemble : un appel juge)
AVOID_MAX = 15               # questions déjà acceptées rappelées au modèle (« ne pose pas une question déjà posée »)
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


def format_course(context: list[dict]) -> str:
    return "\n\n".join(f"[page {c['page']}] {c['text']}" for c in context)


def question_text(question: BaseModel) -> str:
    """Texte principal d'une question, quel que soit son type."""
    return question.statement if isinstance(question, TrueFalseQuestion) else question.question


def build_prompt(kind: str, context: list[dict], difficulty: Difficulty, avoid: list[str], want_true: bool) -> str:
    """Construit la consigne de génération pour un type de question (données personnelles masquées)."""
    spec = TYPE_SPECS[kind]
    already = "\n".join(f"- {q}" for q in avoid[-AVOID_MAX:]) or "- (aucune)"
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
    prompt = mask_pii(
        f"Cours :\n{format_course(context)}\n\nQuestion : {question.question}\n"
        f"Réponse attendue : {_expected(question)}\n\n"
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


def _expected(question: ShortAnswerQuestion | OpenQuestion) -> str:
    if isinstance(question, ShortAnswerQuestion):
        return question.expected_answer
    return " ; ".join(question.expected_points)


def verify(kind: str, questions: list, context: list[dict]) -> list:
    """Vérification unitaire (un passage) de questions d'un même type."""
    if not questions:
        return []
    if kind == "qcm":
        return verify_mcq(questions, context)
    if kind == "vrai_faux":
        return verify_true_false(questions, context)
    return [q for q in questions if verify_written(q, context)]


# ---------------------------------------------------------------------------
# Vérification groupée : un seul appel juge pour les questions d'un même type d'un tour (chacune avec son
# propre passage). JSON invalide ou incomplet → repli sur la vérification unitaire de chaque question.
# ---------------------------------------------------------------------------

def answers_schema(model: type[BaseModel], n: int) -> dict:
    """Schéma JSON envoyé au LLM pour une vérification groupée : exactement n réponses (le modèle recopie sinon
    l'exemple de format, souvent de longueur 2). La validation Pydantic des réponses reste celle de `model`."""
    schema = model.model_json_schema()
    schema["properties"]["answers"] = {**schema["properties"]["answers"], "minItems": n, "maxItems": n}
    return schema


def _grouped_listing(items: list[tuple[BaseModel, list[dict]]], render) -> str:
    return "\n\n".join(f"--- Question {i} ---\nExtrait du cours :\n{format_course(context)}\n{render(question)}"
                       for i, (question, context) in enumerate(items, start=1))


def _render_mcq(q: MCQQuestion) -> str:
    return f"Question : {q.question}\n" + "\n".join(f"{letter}. {choice}" for letter, choice in zip(LETTERS, q.choices))


def _render_tf(q: TrueFalseQuestion) -> str:
    return f"Affirmation : {q.statement}"


def _render_written(q: ShortAnswerQuestion | OpenQuestion) -> str:
    return f"Question : {q.question}\nRéponse attendue : {_expected(q)}"


def _unit_verdicts(kind: str, items: list[tuple[BaseModel, list[dict]]]) -> list[bool]:
    return parallel_map(lambda item: bool(verify(kind, [item[0]], item[1])), items)


def verify_group(kind: str, items: list[tuple[BaseModel, list[dict]]]) -> list[bool]:
    """Verdict (gardée ou non) de chaque question, dans l'ordre. Une seule question : vérification unitaire."""
    if len(items) <= 1:
        return _unit_verdicts(kind, items)
    n = len(items)
    if kind == "qcm":
        instruction = (f"Pour chacune des {n} questions, dans l'ordre, donne la lettre de la seule bonne réponse "
                       f'selon SON extrait du cours. Format : {{"answers":[...]}} avec exactement {n} lettres.')
        listing, model, max_tokens = _grouped_listing(items, _render_mcq), LetterAnswers, 100
        expected = [q.answer for q, _ in items]
    elif kind == "vrai_faux":
        instruction = (f"Pour chacune des {n} affirmations, dans l'ordre, réponds true si elle est vraie selon SON "
                       f'extrait du cours, false sinon. Format : {{"answers":[...]}} avec exactement {n} valeurs.')
        listing, model, max_tokens = _grouped_listing(items, _render_tf), BoolAnswers, 60
        expected = [q.answer for q, _ in items]
    else:
        instruction = (f"Pour chacune des {n} questions, dans l'ordre, réponds true si la réponse attendue est "
                       "correcte selon SON extrait du cours ET répond exactement à la question posée, false sinon. "
                       f'Format : {{"answers":[...]}} avec exactement {n} valeurs.')
        listing, model, max_tokens = _grouped_listing(items, _render_written), BoolAnswers, 60
        expected = [True] * n
    prompt = mask_pii(f"{listing}\n\n{instruction}")
    try:
        raw = chat(VERIFY_SYSTEM_PROMPT, prompt, max_tokens=max_tokens, temperature=0,
                   json_schema=answers_schema(model, n))
        answers = model.model_validate_json(raw).answers[:n]  # une réponse de trop est ignorée
    except (LLMError, ValidationError) as e:
        logger.info("Vérification groupée (%s) illisible, repli unitaire : %s", kind, e)
        answers = []
    if len(answers) != n:
        record("verifications_groupees_repli")
        return _unit_verdicts(kind, items)
    record("verifications_groupees")
    verdicts = [got == want for got, want in zip(answers, expected)]
    for (question, _), ok in zip(items, verdicts):
        if not ok:
            logger.info("Question écartée (vérification groupée) : %s", question_text(question)[:70])
            reject("verification", question.type)
    return verdicts


def shuffle_choices(question: MCQQuestion, rng: random.Random) -> MCQQuestion:
    """Mélange les choix pour que la bonne réponse ne soit pas toujours à la même position."""
    correct = question.choices[LETTERS.index(question.answer)]
    choices = question.choices[:]
    rng.shuffle(choices)
    return question.model_copy(update={"choices": choices, "answer": LETTERS[choices.index(correct)]})


# ---------------------------------------------------------------------------
# Génération par tours
# ---------------------------------------------------------------------------
# À chaque tour, chaque partie incomplète reçoit jusqu'à ROUND_MAX candidats, chacun ancré sur un passage
# différent. Les candidats d'un tour sont générés (en parallèle si LLM_CONCURRENCY > 1), filtrés (validation
# Pydantic, puis doublons de sens par embeddings, AVANT tout appel de vérification), puis vérifiés en un appel
# groupé par type. La logique ne dépend pas de LLM_CONCURRENCY : seule l'exécution change.

def is_duplicate(vector: list[float], seen_vectors: list[list[float]], threshold: float) -> bool:
    """Deux questions de même sens (même si la formulation change) sont des doublons."""
    if not seen_vectors:
        return False
    return float(np.max(np.array(seen_vectors) @ np.array(vector))) >= threshold


@dataclass
class SectionState:
    """Avancement d'une partie de l'examen."""

    plan: SectionPlan
    pending: list[int]           # passages encore disponibles (deux passages sur le cours au maximum)
    questions: list = field(default_factory=list)
    calls: int = 0               # appels de génération (le budget ne compte pas les vérifications)

    @property
    def budget(self) -> int:
        return self.plan.count * CALLS_PER_QUESTION

    @property
    def missing(self) -> int:
        return self.plan.count - len(self.questions)


@dataclass
class Candidate:
    state: SectionState
    index: int                   # passage d'ancrage
    context: list[dict]
    want_true: bool
    threshold: float             # seuil de doublon au moment de la génération
    question: BaseModel | None = None
    vector: list[float] | None = None
    error: LLMError | None = None


def new_section(plan: SectionPlan, n_chunks: int, rng: random.Random) -> SectionState:
    order = list(range(n_chunks))
    rng.shuffle(order)
    record(f"demandees_{plan.kind}", plan.count)
    return SectionState(plan=plan, pending=order * 2)


def _pick(state: SectionState, k: int, taken: set[int], used: set[int]) -> list[int]:
    """k passages pour cette partie : jamais deux fois le même dans un tour, les passages pas encore utilisés
    par une question acceptée d'abord (l'examen se répartit sur tout le cours)."""
    chosen: list[int] = []
    for only_new in (True, False):
        for index in list(state.pending):
            if len(chosen) >= k:
                return chosen
            if index in taken or index in chosen or (only_new and index in used):
                continue
            chosen.append(index)
            state.pending.remove(index)
    return chosen


def _generate(candidate: Candidate, difficulty: Difficulty, avoid: list[str]) -> Candidate:
    """Un appel de génération pour un candidat (exécuté dans un thread si LLM_CONCURRENCY > 1)."""
    kind = candidate.state.plan.kind
    spec = TYPE_SPECS[kind]
    allowed_pages = sorted({c["page"] for c in candidate.context})
    record("appels_generation")
    try:
        raw = chat(SYSTEM_PROMPT, build_prompt(kind, candidate.context, difficulty, avoid, candidate.want_true),
                   max_tokens=spec.max_tokens, temperature=0.5, json_schema=spec.batch_model.model_json_schema())
    except LLMError as e:
        # Un appel raté (boucle du modèle, réponse vide…) ne doit pas faire échouer tout l'examen
        logger.warning("Appel %s ignoré : %s", kind, e)
        record("erreurs_llm")
        candidate.error = e
        return candidate
    items = parse_items(kind, raw, allowed_pages)[:1]
    candidate.question = items[0] if items else None
    return candidate


def run_sections(states: list[SectionState], chunks: list[dict], difficulty: Difficulty, asked: list[str],
                 seen_vectors: list[list[float]], used: set[int], rng: random.Random) -> LLMError | None:
    """Remplit les parties tour par tour, jusqu'au nombre demandé ou à l'épuisement du budget ou des passages."""
    last_error: LLMError | None = None
    while True:
        round_: list[Candidate] = []
        taken: set[int] = set()
        for state in states:
            k = min(state.missing, ROUND_MAX, state.budget - state.calls)
            if k <= 0:
                continue
            window = TYPE_SPECS[state.plan.kind].window
            for j, index in enumerate(_pick(state, k, taken, used)):
                taken.add(index)
                # En fin de budget, on n'écarte plus que les questions quasi identiques
                threshold = SIMILARITY_THRESHOLD if state.calls < state.budget * 2 / 3 else CATCH_UP_SIMILARITY
                state.calls += 1
                round_.append(Candidate(state=state, index=index, context=passage_window(chunks, index, window),
                                        # Vrai/Faux : on alterne vrai et faux pour équilibrer la partie
                                        want_true=(len(state.questions) + j) % 2 == 0, threshold=threshold))
        if not round_:
            return last_error

        # 1. Génération. Les questions déjà acceptées sont données au modèle (« ne pose pas une question déjà
        #    posée ») ; en séquentiel, aussi les candidats déjà générés dans ce tour (en parallèle, ils ne sont pas
        #    encore connus : le filtre par embeddings ci-dessous les écarte).
        if concurrency() <= 1:
            avoid = list(asked)
            for candidate in round_:
                _generate(candidate, difficulty, avoid[-AVOID_MAX:])
                if candidate.question is not None:
                    avoid.append(question_text(candidate.question))
        else:
            avoid = asked[-AVOID_MAX:]
            round_ = parallel_map(lambda c: _generate(c, difficulty, avoid), round_)
        last_error = next((c.error for c in reversed(round_) if c.error), last_error)

        # 2. Doublons de sens AVANT la vérification : un doublon ne coûte plus d'appel au juge
        valid = [c for c in round_ if c.question is not None]
        vectors = embed_passages([question_text(c.question) for c in valid]) if valid else []
        kept: list[Candidate] = []
        for candidate, vector in zip(valid, vectors):
            if is_duplicate(vector, seen_vectors + [k.vector for k in kept], candidate.threshold):
                logger.info("Question écartée (doublon de sens) : %s", question_text(candidate.question)[:70])
                reject("doublon", candidate.state.plan.kind)
                continue
            candidate.vector = vector
            kept.append(candidate)

        # 3. Vérification groupée, un appel par type de question (les types en parallèle si possible)
        groups: dict[str, list[Candidate]] = {}
        for candidate in kept:
            groups.setdefault(candidate.state.plan.kind, []).append(candidate)
        verdicts = parallel_map(
            lambda group: verify_group(group[0], [(c.question, c.context) for c in group[1]]), list(groups.items()))

        # 4. Questions acceptées, dans l'ordre du tour
        accepted = {id(c) for (_, group), oks in zip(groups.items(), verdicts) for c, ok in zip(group, oks) if ok}
        for candidate in kept:
            if id(candidate) not in accepted:
                continue
            question = candidate.question
            seen_vectors.append(candidate.vector)
            asked.append(question_text(question))
            used.add(candidate.index)
            candidate.state.questions.append(shuffle_choices(question, rng) if candidate.state.plan.kind == "qcm"
                                             else question)


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
    rng = random.Random()
    asked: list[str] = []
    seen_vectors: list[list[float]] = []
    used: set[int] = set()
    t0 = time.perf_counter()

    states = [new_section(plan, len(chunks), rng) for plan in plans]
    last_error = run_sections(states, chunks, difficulty, asked, seen_vectors, used, rng)
    results: dict[str, list] = {state.plan.kind: state.questions for state in states}

    # Examen complet : s'il manque des points (questions écartées), on complète avec des Vrai/Faux à 1 point,
    # le type le plus fiable à générer et à vérifier, pour que l'examen soit toujours noté sur 20.
    if fmt == "complet":
        missing = round(20 - sum(p.points * len(results[p.kind]) for p in plans))
        if missing > 0:
            tf_plan = next(p for p in plans if p.kind == "vrai_faux")
            logger.info("Complément : %d affirmation(s) Vrai/Faux pour atteindre 20 points", missing)
            extra_plan = SectionPlan(tf_plan.kind, tf_plan.title, tf_plan.instructions, missing, tf_plan.points)
            extra = new_section(extra_plan, len(chunks), rng)
            last_error = run_sections([extra], chunks, difficulty, asked, seen_vectors, used, rng) or last_error
            states.append(extra)
            results["vrai_faux"].extend(extra.questions)

    for state in states:
        if state.missing > 0:
            logger.warning("Partie « %s » incomplète : %d/%d questions après %d appels",
                           state.plan.title, len(state.questions), state.plan.count, state.calls)

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