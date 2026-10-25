"""Jeu de données de fine-tuning : le style du tuteur, adapté au niveau de l'étudiant.

Usage :
    python -m app.phase4_finetuning.dataset <email> [--n 300] [--seed 42] [--restart]

À partir des cours de l'étudiant indexés dans Qdrant (passages de 200 caractères ou plus) :
1. le LLM configuré (modèle enseignant) pose une question variée sur un passage
   (définition, rôle, comparaison, exemple, « pourquoi ») ;
2. pour chacun des 3 niveaux, il rédige la « réponse idéale » avec la consigne de niveau du tuteur ;
3. chaque réponse est filtrée (français, longueur adaptée au niveau, référence [p.X] valide,
   pas d'hésitation, pas d'anglais).

--n : nombre d'exemples gardés (question × niveau) à atteindre. Une question donne jusqu'à 3 exemples.

Sorties dans app/phase4_finetuning/data/ (ignoré par git, sauf sample.jsonl) :
    all.jsonl (exemples gardés, écrits au fur et à mesure), progress.json (reprise),
    train.jsonl (90 %), test.jsonl (10 %), sample.jsonl (10 exemples pour le rapport).

Les 3 niveaux d'une même question vont toujours dans le même fichier (train ou test) : le test ne contient
aucune question vue à l'entraînement. Aucune donnée d'étudiant n'est utilisée (seulement le texte des cours),
et mask_pii est appliqué au passage, à la question et à la réponse.
"""
import argparse
import hashlib
import json
import logging
import random
import re
import sys
from collections import Counter
from pathlib import Path

from app.core.privacy import mask_pii
from app.phase1_llm.llm import LLMError, chat
from app.phase3_rag.rag import NOT_FOUND, SYSTEM_PROMPT, build_system_prompt, build_user_prompt
from app.phase4_exam.schemas import ENGLISH_WORDS, NON_LATIN, check_question
from app.phase7_flashcards.schemas import HEDGING
from app.phase8_personal.models import LEVELS

DATA = Path(__file__).parent / "data"
MIN_PASSAGE_CHARS = 200
TEST_RATIO = 0.10
SAMPLE_SIZE = 10
QUESTION_TEMPERATURE = 0.7  # questions variées
ANSWER_TEMPERATURE = 0.3  # même température que le tuteur de l'application

LEVEL_LABELS = {"debutant": "débutant", "intermediaire": "intermédiaire", "avance": "avancé"}

# Types de questions posées sur un passage (un type différent à chaque passage, puis à chaque tour)
QUESTION_TYPES = {
    "definition": "une question de définition (« Qu'est-ce que… ? », « Que désigne… ? »)",
    "role": "une question sur le rôle ou l'utilité d'une notion (« À quoi sert… ? », « Quel est le rôle de… ? »)",
    "comparaison": "une question de comparaison entre deux notions du passage (« Quelle différence entre… ? »)",
    "exemple": "une question qui demande un exemple ou une application concrète (« Donne un exemple de… »)",
    "pourquoi": "une question « pourquoi » sur une cause, un avantage ou une limite (« Pourquoi… ? »)",
}

# Longueur de la réponse en mots, selon le niveau : le débutant a droit à des définitions et une analogie
LENGTH_WORDS = {"debutant": (60, 260), "intermediaire": (35, 200), "avance": (20, 170)}

CITATION = re.compile(r"\[p\.\s*(\d+)\]")
# Mots-outils français : une réponse en français en contient forcément plusieurs
FRENCH_WORDS = re.compile(r"\b(le|la|les|des|est|une|du|et|en|que|qui|pour|dans|sont|par|avec|sur)\b",
                          re.IGNORECASE)
MIN_FRENCH_RATIO = 0.08  # part minimale de mots-outils français parmi tous les mots

REJECT_CAUSES = ("question", "hors_cours", "francais", "anglais", "longueur", "reference", "incertitude",
                 "erreur_llm")

QUESTION_SYSTEM = (
    "Tu es un enseignant qui prépare des questions d'étudiants à partir d'un cours. "
    "Tu réponds UNIQUEMENT avec un objet JSON valide."
)
QUESTION_SCHEMA = {
    "type": "object",
    "properties": {"question": {"type": "string"}},
    "required": ["question"],
}

# Prompt système du modèle affiné : les règles du tuteur, SANS la consigne détaillée de chaque niveau.
# Le modèle doit apprendre à adapter son style au seul niveau indiqué dans le message de l'étudiant.
FINETUNE_SYSTEM = SYSTEM_PROMPT + "\n- Adapte ton explication au niveau de l'étudiant indiqué dans son message."


# ---------------------------------------------------------------------------
# Filtres
# ---------------------------------------------------------------------------

def words(text: str) -> list[str]:
    return re.findall(r"[\wàâçéèêëîïôûùüÿœ'-]+", text, re.IGNORECASE)


def is_french(text: str) -> bool:
    """Assez de mots-outils français (le, la, est, des…) parmi les mots du texte."""
    all_words = words(text)
    return bool(all_words) and len(FRENCH_WORDS.findall(text)) / len(all_words) >= MIN_FRENCH_RATIO


def has_english(text: str) -> bool:
    """Deux mots anglais fréquents ou plus (the, of, and…), ou des caractères non latins."""
    return len(ENGLISH_WORDS.findall(text)) >= 2 or bool(NON_LATIN.search(text))


def cited_pages(text: str) -> list[int]:
    return [int(p) for p in CITATION.findall(text)]


def valid_citation(text: str, page: int) -> bool:
    """Au moins une référence [p.X], et toutes renvoient à la page du passage."""
    pages = cited_pages(text)
    return bool(pages) and all(p == page for p in pages)


def check_answer(text: str, level: str, page: int) -> str | None:
    """Cause du rejet d'une réponse idéale, ou None si elle est gardée."""
    if NOT_FOUND.lower().rstrip(".") in text.lower():
        return "hors_cours"
    if has_english(text):
        return "anglais"
    if not is_french(text):
        return "francais"
    low, high = LENGTH_WORDS[level]
    if not low <= len(words(text)) <= high:
        return "longueur"
    if not valid_citation(text, page):
        return "reference"
    if HEDGING.search(text):
        return "incertitude"
    return None


def clean_question(raw: str) -> str | None:
    """La question générée (JSON {"question": "..."}), ou None si elle est inutilisable."""
    try:
        data = json.loads(raw)
        question = data["question"].strip() if isinstance(data, dict) else ""
    except (json.JSONDecodeError, KeyError, AttributeError):
        return None
    if not 15 <= len(question) <= 200 or not (question.endswith("?") or question.lower().startswith("donne")):
        return None
    if has_english(question) or not is_french(question):
        return None
    try:
        return check_question(question)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Format des exemples (chat : system / user / assistant)
# ---------------------------------------------------------------------------

def finetune_user_prompt(level: str, passage: dict, question: str) -> str:
    """Message de l'étudiant vu par le modèle affiné : niveau + passage + question (même forme que le tuteur)."""
    return mask_pii(f"Niveau de l'étudiant : {LEVEL_LABELS[level]}.\n\n"
                    + build_user_prompt([passage], question))


def make_example(qid: str, qtype: str, level: str, passage: dict, question: str, reply: str) -> dict:
    return {
        "id": f"{qid}-{level}",
        "qid": qid,
        "type": qtype,
        "niveau": level,
        "page": passage["page"],
        "messages": [
            {"role": "system", "content": FINETUNE_SYSTEM},
            {"role": "user", "content": finetune_user_prompt(level, passage, question)},
            {"role": "assistant", "content": mask_pii(reply.strip())},
        ],
    }


def passage_key(passage: dict) -> str:
    raw = f"{passage['course']}|{passage['page']}|{passage['text']}"
    return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]  # identifiant, pas une signature


def split(examples: list[dict], test_ratio: float = TEST_RATIO, seed: int = 42) -> tuple[list[dict], list[dict]]:
    """Découpe par question (jamais une même question dans train et test), au moins une question en test."""
    qids = sorted({e["qid"] for e in examples})
    random.Random(seed).shuffle(qids)  # noqa: S311 — découpage reproductible, sans enjeu de sécurité
    n_test = max(1, round(len(qids) * test_ratio)) if len(qids) > 1 else 0
    test_ids = set(qids[:n_test])
    train = [e for e in examples if e["qid"] not in test_ids]
    test = [e for e in examples if e["qid"] in test_ids]
    return train, test


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# Génération (avec reprise)
# ---------------------------------------------------------------------------

def load_passages(user_id: int) -> list[dict]:
    """Passages de 200 caractères ou plus de tous les cours de l'étudiant, texte masqué."""
    from sqlmodel import Session

    from app.core.db import engine
    from app.phase2_embeddings.vectorstore import get_course_chunks
    from app.phase8_personal.courses import list_user_courses

    with Session(engine) as session:
        courses = list_user_courses(session, user_id)
    passages = []
    for course in courses:
        for chunk in get_course_chunks(course, user_id):
            text = mask_pii(chunk["text"].strip())
            if len(text) >= MIN_PASSAGE_CHARS:
                passages.append({"course": course, "page": chunk["page"], "text": text})
    return passages


def generate_question(passage: dict, qtype: str) -> str | None:
    prompt = mask_pii(f"""Passage d'un cours (page {passage['page']}) :
{passage['text']}

Écris {QUESTION_TYPES[qtype]} qu'un étudiant pourrait poser sur ce passage.
- La réponse doit se trouver dans le passage.
- Une seule question, courte (moins de 25 mots), en français, sans numéro de page.
- Ne cite ni le titre du cours, ni un nom de personne.

Format attendu : {{"question": "..."}}""")
    return clean_question(chat(QUESTION_SYSTEM, prompt, max_tokens=120, temperature=QUESTION_TEMPERATURE,
                               json_schema=QUESTION_SCHEMA))


def teacher_answer(passage: dict, question: str, level: str) -> str:
    """Réponse idéale : le prompt complet du tuteur de l'application, avec la consigne du niveau."""
    return chat(build_system_prompt(level=level), build_user_prompt([passage], question),
                max_tokens=700, temperature=ANSWER_TEMPERATURE)


class Progress:
    """État de la génération, sauvegardé après chaque question : une relance reprend là où elle s'est arrêtée."""

    def __init__(self, path: Path):
        self.path = path
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.done: set[str] = set(state.get("done", []))
        self.rejects: Counter = Counter(state.get("rejects", {}))
        self.questions: int = state.get("questions", 0)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        state = {"done": sorted(self.done), "rejects": dict(self.rejects), "questions": self.questions}
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def tasks(passages: list[dict], seed: int) -> list[tuple[dict, str]]:
    """(passage, type de question) : un type différent par passage, puis un autre type à chaque tour."""
    order = passages[:]
    random.Random(seed).shuffle(order)  # noqa: S311 — ordre reproductible, sans enjeu de sécurité
    types = list(QUESTION_TYPES)
    return [(p, types[(i + turn) % len(types)]) for turn in range(len(types)) for i, p in enumerate(order)]


def build_dataset(passages: list[dict], n: int, data_dir: Path = DATA, seed: int = 42,
                  progress_bar: bool = True) -> tuple[list[dict], Progress]:
    """Génère jusqu'à n exemples gardés (en reprenant all.jsonl et progress.json s'ils existent)."""
    from tqdm import tqdm

    all_path = data_dir / "all.jsonl"
    progress = Progress(data_dir / "progress.json")
    examples = read_jsonl(all_path)
    all_path.parent.mkdir(parents=True, exist_ok=True)

    bar = tqdm(total=n, initial=min(len(examples), n), unit="ex", disable=not progress_bar,
               desc="Exemples gardés")
    with all_path.open("a", encoding="utf-8") as out:
        for passage, qtype in tasks(passages, seed):
            if len(examples) >= n:
                break
            qid = f"{passage_key(passage)}-{qtype}"
            if qid in progress.done:
                continue
            try:
                question = generate_question(passage, qtype)
            except LLMError as e:  # non marquée comme faite : une relance la retentera
                logging.warning("Question ignorée : %s", e)
                progress.rejects["erreur_llm"] += 1
                progress.save()
                continue
            if question is None:
                progress.rejects["question"] += 1
            else:
                progress.questions += 1
                for level in LEVELS:
                    try:
                        reply = teacher_answer(passage, question, level)
                    except LLMError as e:
                        logging.warning("Réponse ignorée : %s", e)
                        progress.rejects["erreur_llm"] += 1
                        continue
                    cause = check_answer(reply, level, passage["page"])
                    if cause:
                        progress.rejects[cause] += 1
                        continue
                    example = make_example(qid, qtype, level, passage, question, reply)
                    out.write(json.dumps(example, ensure_ascii=False) + "\n")
                    out.flush()
                    examples.append(example)
                    bar.update(1)
            progress.done.add(qid)
            progress.save()
            bar.set_postfix(rejets=sum(progress.rejects.values()))
    bar.close()
    return examples, progress


def export(examples: list[dict], data_dir: Path = DATA, seed: int = 42) -> tuple[list[dict], list[dict]]:
    """Écrit train.jsonl, test.jsonl et sample.jsonl (10 exemples variés, les 3 niveaux représentés)."""
    train, test = split(examples, seed=seed)
    write_jsonl(data_dir / "train.jsonl", train)
    write_jsonl(data_dir / "test.jsonl", test)
    pool = test + train
    sample = []
    for level in LEVELS * SAMPLE_SIZE:  # alterne les niveaux
        pick = next((e for e in pool if e["niveau"] == level and e not in sample), None)
        if pick is not None:
            sample.append(pick)
        if len(sample) >= SAMPLE_SIZE:
            break
    write_jsonl(data_dir / "sample.jsonl", sample)
    return train, test


def print_stats(examples: list[dict], progress: Progress, train: list[dict], test: list[dict]) -> None:
    answers = len(examples) + sum(v for k, v in progress.rejects.items() if k not in ("question", "erreur_llm"))
    print(f"\nQuestions générées : {progress.questions}")
    print(f"Exemples gardés    : {len(examples)} / {answers} réponses ({len(examples) / answers:.0%})"
          if answers else f"Exemples gardés    : {len(examples)}")
    by_level = Counter(e["niveau"] for e in examples)
    by_type = Counter(e["type"] for e in examples)
    print("  par niveau : " + ", ".join(f"{LEVEL_LABELS[lv]} {by_level[lv]}" for lv in LEVELS))
    print("  par type   : " + ", ".join(f"{t} {by_type[t]}" for t in QUESTION_TYPES))
    print("Rejets par cause :")
    for cause in REJECT_CAUSES:
        print(f"  {cause:<12} {progress.rejects.get(cause, 0)}")
    print(f"Découpage : train {len(train)} exemples · test {len(test)} exemples "
          f"({len({e['qid'] for e in test})} questions jamais vues à l'entraînement)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jeu de données de fine-tuning du style du tuteur.")
    parser.add_argument("email", help="email du compte dont les cours servent de source")
    parser.add_argument("--n", type=int, default=300, help="exemples (question × niveau) à garder (défaut : 300)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--restart", action="store_true", help="repart de zéro (efface all.jsonl et progress.json)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="  %(levelname)s : %(message)s")

    from sqlmodel import Session, select

    from app.core import config
    from app.core.db import engine, init_db
    from app.phase8_personal.models import User

    init_db()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == args.email.strip().lower())).first()
        user_id = user.id if user else None
    if user_id is None:
        print(f"❌ Aucun compte avec l'email « {args.email} ».")
        return 1

    if args.restart:
        for name in ("all.jsonl", "progress.json"):
            (DATA / name).unlink(missing_ok=True)

    passages = load_passages(user_id)
    if not passages:
        print(f"❌ Aucun passage de {MIN_PASSAGE_CHARS} caractères ou plus dans les cours de ce compte.")
        return 1
    print(f"{len(passages)} passages · modèle enseignant {config.LLM_MODEL} · objectif {args.n} exemples")

    examples, progress = build_dataset(passages, args.n, seed=args.seed)
    if not examples:
        print("❌ Aucun exemple gardé.")
        return 1
    train, test = export(examples, seed=args.seed)
    print_stats(examples, progress, train, test)
    print(f"\nFichiers : {DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
