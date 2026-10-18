import hashlib
import json
import logging
import math
import threading
import time
from collections import OrderedDict, deque

import numpy as np
from pydantic import BaseModel, ValidationError
from app.phase4_exam.generator import answers_schema
from app.phase4_exam.schemas import BoolAnswers
from app.core.concurrency import parallel_map
from app.core.privacy import mask_pii
from app.phase1_llm.llm import LLMError, chat
from app.phase2_embeddings.embeddings import embed_passages, embed_query
from app.phase2_embeddings.vectorstore import get_course_chunks
from app.phase7_flashcards.schemas import Concept, ConceptBatch, Flashcard, FlashcardBatch, FlashcardDeck
from app.phase5_evaluation.stats import GenerationStats, collecting, record, record_value, reject

logger = logging.getLogger("uvicorn.error")

CONCEPT_WINDOW = 3            # passages lus ensemble pour extraire les concepts
CONCEPT_SIMILARITY = 0.97     # au-dessus, deux concepts sont considérés comme identiques
CARD_SIMILARITY = 0.92        # au-dessus, deux cartes posent la même question
CONTEXT_PASSAGES = 2          # passages retrouvés (RAG) pour rédiger une carte
CANDIDATE_MARGIN = 2.5        # on prépare plus de concepts que de cartes (certaines seront rejetées)
MIN_PASSAGE_CHARS = 60       # en dessous : bout de découpage ou titre, inutilisable pour une carte
CARD_ROUND_MAX = 5            # cartes rédigées au plus par tour (vérifiées ensemble : un appel juge)
CONCEPT_CACHE_MAX = 32        # cours gardés en mémoire (cache des concepts extraits)
SYSTEM_PROMPT = (
    "Tu es un enseignant qui prépare des fiches de révision à partir d'un cours. "
    "Tu réponds UNIQUEMENT avec un objet JSON valide et compact, sans aucun texte autour."
)
VERIFY_SYSTEM_PROMPT = (
    "Tu es un enseignant rigoureux qui vérifie des fiches de révision à partir du cours fourni. "
    "Tu réponds UNIQUEMENT avec un objet JSON valide."
)


def format_course(context: list[dict]) -> str:
    return "\n\n".join(f"[page {c['page']}] {c['text']}" for c in context)


def first_items(raw: str) -> list[dict]:
    """Lit le JSON du LLM et renvoie la liste "items" (vide si le JSON est invalide)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Réponse du LLM qui n'est pas du JSON valide, ignorée")
        return []
    items = data.get("items", []) if isinstance(data, dict) else []
    return [item for item in items if isinstance(item, dict)]


# ---------------------------------------------------------------------------
# Étape 1 : l'IA repère les concepts importants du cours
# ---------------------------------------------------------------------------

# Cache en mémoire des concepts extraits, par (user_id, cours, empreinte du contenu) puis par bloc de passages :
# un deuxième paquet sur le même cours ne relit pas le cours. Un cours réimporté change d'empreinte. Le cache ne
# contient que des noms de notions tirés du cours (rien n'est envoyé à MLflow) et reste dans le processus.
_concept_cache: OrderedDict[tuple, dict[int, list[Concept]]] = OrderedDict()
_cache_lock = threading.Lock()


def concept_cache_key(user_id: int | None, course: str, chunks: list[dict]) -> tuple:
    content = "\n".join(f"{c['page']}:{c['text']}" for c in chunks)
    return user_id, course, hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _cached_blocks(key: tuple | None) -> dict[int, list[Concept]]:
    if key is None:
        return {}
    with _cache_lock:
        if key in _concept_cache:
            _concept_cache.move_to_end(key)
            return dict(_concept_cache[key])
    return {}


def _store_blocks(key: tuple | None, blocks: dict[int, list[Concept]]) -> None:
    if key is None or not blocks:
        return
    with _cache_lock:
        _concept_cache.setdefault(key, {}).update(blocks)
        _concept_cache.move_to_end(key)
        while len(_concept_cache) > CONCEPT_CACHE_MAX:
            _concept_cache.popitem(last=False)


def clear_concept_cache() -> None:
    with _cache_lock:
        _concept_cache.clear()


def _extract_block(context: list[dict]) -> list[Concept] | LLMError:
    """Notions clés d'un bloc de passages (un appel), ou l'erreur du LLM."""
    prompt = mask_pii(f"""Cours (chaque passage commence par sa page) :
{format_course(context)}

Liste au plus 3 notions clés de ce passage qu'un étudiant doit retenir pour l'examen.
- "name" : le nom court de la notion, en français (2 à 6 mots), par exemple « Connecteur » ou « Développement natif ».
- "importance" : 3 = notion centrale (définition, principe), 2 = notion utile, 1 = détail.
- Ignore les titres, plans de cours, logos, noms de personnes et informations administratives.
- Si le passage ne contient aucune notion utile, renvoie une seule notion d'importance 1.

Format attendu :
{{"items":[{{"name":"...","importance":3}}]}}""")
    try:
        raw = chat(SYSTEM_PROMPT, prompt, max_tokens=200, temperature=0.2,
                   json_schema=ConceptBatch.model_json_schema())
    except LLMError as e:
        logger.warning("Extraction de concepts ignorée : %s", e)
        record("erreurs_llm")
        return e
    concepts = []
    for item in first_items(raw):
        try:
            concepts.append(Concept.model_validate(item))
        except ValidationError as e:
            logger.info("Concept rejeté : %s", e.errors()[0]["msg"])
            record("rejets_validation_concepts")
    return concepts


def extract_concepts(chunks: list[dict], count: int,
                     cache_key: tuple | None = None) -> tuple[list[Concept], LLMError | None]:
    """Lit le cours par blocs de passages et liste les notions clés (avec leur importance).

    On ne lit que le nombre de blocs utile (environ 3 concepts par bloc), répartis sur tout le cours :
    la durée dépend alors du nombre de cartes demandées, plus de la taille du cours. Les blocs sont
    indépendants : lus en parallèle si LLM_CONCURRENCY > 1, et repris du cache s'ils ont déjà été lus.
    """
    starts = list(range(0, len(chunks), CONCEPT_WINDOW))
    needed = math.ceil(count * CANDIDATE_MARGIN / 3) + 2
    if len(starts) > needed:
        step = len(starts) / needed
        starts = [starts[int(i * step)] for i in range(needed)]

    cached = _cached_blocks(cache_key)
    missing = [start for start in starts if start not in cached]
    if len(missing) < len(starts):
        record("blocs_concepts_en_cache", len(starts) - len(missing))
    results = parallel_map(lambda start: _extract_block(chunks[start:start + CONCEPT_WINDOW]), missing)
    fresh = {start: r for start, r in zip(missing, results) if not isinstance(r, LLMError)}
    _store_blocks(cache_key, fresh)

    blocks = {**cached, **fresh}
    concepts = [concept for start in starts for concept in blocks.get(start, [])]
    last_error = next((r for r in reversed(results) if isinstance(r, LLMError)), None)
    return concepts, last_error


def select_concepts(concepts: list[Concept], limit: int) -> list[Concept]:
    """Supprime les doublons de sens et garde les concepts les plus importants."""
    if not concepts:
        return []
    vectors = embed_passages([c.name for c in concepts])
    # Tri stable : à importance égale, on garde l'ordre du cours
    order = sorted(range(len(concepts)), key=lambda i: -concepts[i].importance)
    kept: list[int] = []
    for i in order:
        if any(concepts[i].name.lower() == concepts[j].name.lower() for j in kept):
            continue
        if kept and float(np.max(np.array([vectors[j] for j in kept]) @ np.array(vectors[i]))) >= CONCEPT_SIMILARITY:
            continue
        kept.append(i)
        if len(kept) >= limit:
            break
    return [concepts[i] for i in kept]


# ---------------------------------------------------------------------------
# Étape 2 : une carte par concept, rédigée à partir des passages retrouvés (RAG)
# ---------------------------------------------------------------------------

def retrieve(concept: Concept, chunks: list[dict], chunk_vectors: np.ndarray) -> list[dict]:
    """Recherche sémantique : les passages du cours qui parlent le plus de ce concept."""
    scores = chunk_vectors @ np.array(embed_query(concept.name))
    best = np.argsort(scores)[::-1][:CONTEXT_PASSAGES]
    return sorted((chunks[i] for i in best), key=lambda c: c["page"])


def make_card(concept: Concept, context: list[dict], temperature: float = 0.4) -> Flashcard | None:    
    """Demande au LLM une carte sur ce concept ; None si la carte est invalide."""
    prompt = mask_pii(f"""Cours (chaque passage commence par sa page) :
{format_course(context)}

Rédige 1 flashcard de révision sur la notion « {concept.name} », à partir du cours ci-dessus.
- "front" : une seule question courte et précise sur « {concept.name} », qui se termine par « ? ».
- "back" explique vraiment la notion (définition, rôle ou exemple) : il ne reformule jamais la question.
- "back" : la réponse en 1 ou 2 phrases courtes (moins de 250 caractères), tirée du cours,
  compréhensible sans relire la question, sans numéro de page.
- "page" : le numéro de la page d'où vient la réponse.
- Rédige TOUT en français : traduis le cours s'il est en anglais.
- Jamais de question oui/non, jamais de question « combien ».
- N'invente rien : utilise uniquement ce que dit le cours.
- Si le passage est illisible ou incomplet, ne devine pas : choisis une autre information claire du cours.

Format attendu :
{{"items":[{{"concept":"{concept.name}","front":"...?","back":"...","page":12}}]}}""")
    record("appels_generation")
    raw = chat(SYSTEM_PROMPT, prompt, max_tokens=250, temperature=temperature,
               json_schema=FlashcardBatch.model_json_schema())

    items = first_items(raw)
    if not items:
        reject("validation")
        return None
    item = {**items[0], "concept": concept.name}  # le concept est imposé par le code
    try:
        card = Flashcard.model_validate(item)
    except ValidationError as e:
        logger.info("Carte rejetée (%s) : %s", concept.name, e.errors()[0]["msg"])
        reject("validation")
        return None

    # Si le modèle se trompe de page, on prend la page la plus proche parmi celles fournies
    pages = [c["page"] for c in context]
    if card.page not in pages:
        card = card.model_copy(update={"page": min(pages, key=lambda p: abs(p - card.page))})
    return card

def verify_card(card: Flashcard, context: list[dict]) -> bool:
    """Le modèle relit la carte avec le cours : la réponse doit être correcte ET apporter une information."""
    prompt = mask_pii(
        f"Cours :\n{format_course(context)}\n\nQuestion : {card.front}\nRéponse : {card.back}\n\n"
        "Cette réponse contient-elle une ERREUR, c'est-à-dire une information qui contredit le cours "
        "ou qui ne s'y trouve pas ? Réponds true seulement si tu es sûr qu'il y a une erreur. "
        'Format : {"answers":[true]} ou {"answers":[false]}'
    )
    try:
        raw = chat(VERIFY_SYSTEM_PROMPT, prompt, max_tokens=20, temperature=0,
                   json_schema=BoolAnswers.model_json_schema())
        has_error = BoolAnswers.model_validate_json(raw).answers[0]
    except (LLMError, ValidationError) as e:
        logger.warning("Vérification impossible, carte gardée sans contrôle : %s", e)
        record("verifications_impossibles")
        return True
    if has_error:
        logger.info("Carte écartée (erreur détectée) : %s", card.front[:70])
        reject("verification")
    return not has_error

def verify_cards(items: list[tuple[Flashcard, list[dict]]]) -> list[bool]:
    """Vérification groupée : un seul appel juge pour les cartes d'un tour (chacune avec ses passages).

    Renvoie True pour chaque carte gardée. Une seule carte, ou JSON invalide ou incomplet : vérification
    unitaire de chaque carte (verify_card).
    """
    if len(items) <= 1:
        return [verify_card(card, context) for card, context in items]
    n = len(items)
    listing = "\n\n".join(f"--- Carte {i} ---\nExtrait du cours :\n{format_course(context)}\n"
                          f"Question : {card.front}\nRéponse : {card.back}"
                          for i, (card, context) in enumerate(items, start=1))
    prompt = mask_pii(
        f"{listing}\n\nPour chacune des {n} cartes, dans l'ordre : sa réponse contient-elle une ERREUR, c'est-à-dire "
        "une information qui contredit SON extrait du cours ou qui ne s'y trouve pas ? Réponds true seulement si tu "
        f"es sûr qu'il y a une erreur. Format : {{\"answers\":[...]}} avec exactement {n} valeurs true/false."
    )
    try:
        raw = chat(VERIFY_SYSTEM_PROMPT, prompt, max_tokens=60, temperature=0,
                   json_schema=answers_schema(BoolAnswers, n))
        errors = BoolAnswers.model_validate_json(raw).answers[:n]
    except (LLMError, ValidationError) as e:
        logger.info("Vérification groupée des cartes illisible, repli unitaire : %s", e)
        errors = []
    if len(errors) != n:
        record("verifications_groupees_repli")
        return parallel_map(lambda item: verify_card(item[0], item[1]), items)
    record("verifications_groupees")
    for (card, _), has_error in zip(items, errors):
        if has_error:
            logger.info("Carte écartée (erreur détectée) : %s", card.front[:70])
            reject("verification")
    return [not has_error for has_error in errors]


def generate_flashcards(course: str, count: int = 10, user_id: int | None = None,
                        stats: GenerationStats | None = None) -> FlashcardDeck:
    """Génère un paquet de flashcards sur les concepts les plus importants du cours (de l'étudiant user_id).

    stats (optionnel, phase 5) : collecteur rempli pendant la génération (appels, rejets, durée).
    """
    with collecting(stats):
        return _generate_flashcards(course, count, user_id)


def _chunk_vectors(chunks: list[dict]) -> np.ndarray:
    """Embeddings des passages : ceux déjà calculés à l'import (Qdrant), sinon recalculés."""
    vectors = [c.get("vector") for c in chunks]
    if all(isinstance(v, list) and v for v in vectors) and len({len(v) for v in vectors}) == 1:
        record("vecteurs_reutilises", len(vectors))
        return np.array(vectors)
    return np.array(embed_passages([c["text"] for c in chunks]))


def _draft(concept: Concept, context: list[dict], attempt: int) -> Flashcard | LLMError | None:
    """Une carte (deuxième essai à température plus haute), None si elle est invalide, ou l'erreur du LLM."""
    try:
        return make_card(concept, context, temperature=0.4 + 0.3 * attempt)
    except LLMError as e:
        logger.warning("Carte ignorée (%s) : %s", concept.name, e)
        record("erreurs_llm")
        return e


def _generate_flashcards(course: str, count: int, user_id: int | None) -> FlashcardDeck:
    chunks = get_course_chunks(course, user_id, with_vectors=True)
    if not chunks:
        raise LookupError(f"Le cours « {course} » est introuvable ou vide.")
    # Les bouts de découpage (« ingle one. ») et les titres font inventer des cartes au modèle
    chunks = [c for c in chunks if len(c["text"]) >= MIN_PASSAGE_CHARS] or chunks
    record_value("passages", len(chunks))
    t0 = time.perf_counter()

    # 1. Concepts clés (cache par étudiant et par cours)
    concepts, last_error = extract_concepts(chunks, count, concept_cache_key(user_id, course, chunks))
    candidates = select_concepts(concepts, limit=int(count * CANDIDATE_MARGIN) + 2)
    logger.info("Flashcards « %s » : %d concepts trouvés, %d retenus", course, len(concepts), len(candidates))
    record_value("concepts_trouves", len(concepts))
    record_value("concepts_retenus", len(candidates))
    if not candidates:
        if last_error:
            raise last_error
        raise ValueError("Aucun concept n'a pu être extrait de ce cours. Réessaie.")

    # 2. Une carte par concept (RAG), par tours : rédaction (en parallèle si LLM_CONCURRENCY > 1), doublons de sens
    #    écartés AVANT la vérification, puis un appel juge groupé. Une carte rejetée (validation ou vérification) a
    #    une deuxième chance, avec un autre tirage, au tour suivant.
    chunk_vectors = _chunk_vectors(chunks)
    cards: list[Flashcard] = []
    card_vectors: list[list[float]] = []
    queue: deque[tuple[Concept, int]] = deque((concept, 0) for concept in candidates)
    while queue and len(cards) < count:
        batch = [queue.popleft() for _ in range(min(count - len(cards), CARD_ROUND_MAX, len(queue)))]
        contexts = [retrieve(concept, chunks, chunk_vectors) for concept, _ in batch]
        drafts = parallel_map(lambda item: _draft(item[0][0], item[1], item[0][1]), list(zip(batch, contexts)))

        retry: list[tuple[Concept, int]] = []
        valid: list[tuple[int, Flashcard]] = []
        for i, draft in enumerate(drafts):
            if isinstance(draft, LLMError):
                last_error = draft  # pas de deuxième essai : le LLM est en erreur
            elif draft is None:
                if batch[i][1] == 0:
                    retry.append((batch[i][0], 1))
            else:
                valid.append((i, draft))

        vectors = embed_passages([f"{card.front} {card.back}" for _, card in valid]) if valid else []
        kept: list[tuple[int, Flashcard, list[float]]] = []
        for (i, card), vector in zip(valid, vectors):
            known = card_vectors + [v for _, _, v in kept]
            if known and float(np.max(np.array(known) @ np.array(vector))) >= CARD_SIMILARITY:
                logger.info("Carte écartée (doublon de sens) : %s", card.front[:70])
                reject("doublon")
                continue
            kept.append((i, card, vector))

        verdicts = verify_cards([(card, contexts[i]) for i, card, _ in kept])
        for (i, card, vector), ok in zip(kept, verdicts):
            if ok:
                cards.append(card)
                card_vectors.append(vector)
            elif batch[i][1] == 0:
                retry.append((batch[i][0], 1))
        queue.extendleft(reversed(retry))  # les deuxièmes chances passent avant les concepts suivants

    if not cards:
        if last_error:
            raise last_error
        raise ValueError("Le modèle n'a produit aucune carte valide. Réessaie.")

    cards.sort(key=lambda c: c.page)  # dans l'ordre du cours
    logger.info("Flashcards « %s » : %d/%d cartes en %.1f s", course, len(cards), count, time.perf_counter() - t0)
    return FlashcardDeck(course=course, cards=cards)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    course = sys.argv[1] if len(sys.argv) > 1 else "Chapter1_Part_1"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    deck = generate_flashcards(course, count)
    print(f"\n🃏 Flashcards « {deck.course} » — {len(deck.cards)} cartes\n")
    for number, card in enumerate(deck.cards, start=1):
        print(f"{number}. [{card.concept}] {card.front}")
        print(f"   → {card.back} (p.{card.page})\n")