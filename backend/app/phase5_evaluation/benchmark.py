"""Benchmark hors ligne : N examens complets, N paquets de 10 flashcards, le jeu de questions du tuteur
 et un résumé du cours entier.

Usage :
    python -m app.phase5_evaluation.benchmark <email> <cours> [--n 3] [--skip-exam] [--skip-flashcards]
        [--skip-tutor] [--skip-summary]

Chaque génération est enregistrée dans MLflow (tag source=benchmark). À la fin : un tableau récapitulatif
(moyenne et écart-type de chaque métrique, par expérience) dans la console et dans
app/phase5_evaluation/results/<cours>_<date>.csv.
"""
import argparse
import csv
import json
import logging
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, select

from app.core import config
from app.core.db import engine, init_db
from app.phase2_embeddings.embeddings import embed_query
from app.phase2_embeddings.vectorstore import search
from app.phase3_rag.rag import answer
from app.phase4_exam.generator import generate_exam
from app.phase5_evaluation.stats import GenerationStats
from app.phase5_evaluation.tracking import exam_run, flashcards_run, log_run, set_run_tags, summary_run, tutor_run
from app.phase7_flashcards.generator import generate_flashcards
from app.phase8_personal.courses import get_user_course
from app.phase8_personal.models import User
from app.phase9_summaries.generator import generate_summary

HERE = Path(__file__).parent
DATASETS = HERE / "datasets"
RESULTS = HERE / "results"
EXAM_DIFFICULTY = "moyen"
FLASHCARD_COUNT = 10
SOURCE = "benchmark"


def _line(text: str) -> None:
    print(text, flush=True)


def _fmt(value: float) -> str:
    return f"{value:.0f}" if abs(value) >= 100 else f"{value:.3g}"


def run_exams(n: int, course: str, user_id: int) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        _line(f"[examen {i}/{n}] génération d'un examen complet ({EXAM_DIFFICULTY})…")
        stats, exam, error = GenerationStats(), None, None
        try:
            exam = generate_exam(course, "complet", 20, EXAM_DIFFICULTY, user_id=user_id, stats=stats)
        except Exception as e:  # noqa: BLE001 — un échec est un résultat du benchmark
            error = e
        params, metrics, tags = exam_run(stats, course=course, fmt="complet", difficulty=EXAM_DIFFICULTY,
                                         num_questions=20, exam=exam, error=error, source=SOURCE)
        log_run("exam", params, metrics, tags)
        rows.append(metrics)
        if error:
            _line(f"[examen {i}/{n}] ÉCHEC ({type(error).__name__}) après {metrics.get('duree_s', 0):.0f} s")
        else:
            _line(f"[examen {i}/{n}] {metrics['questions_generees']:.0f}/{metrics['questions_demandees']:.0f} questions"
                  f" · {metrics['total_points']:g}/20 points · {metrics.get('appels_llm', 0):.0f} appels LLM"
                  f" · {metrics['duree_s']:.0f} s")
    return rows


def run_flashcards(n: int, course: str, user_id: int) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        _line(f"[flashcards {i}/{n}] génération de {FLASHCARD_COUNT} cartes…")
        stats, deck, error = GenerationStats(), None, None
        try:
            deck = generate_flashcards(course, FLASHCARD_COUNT, user_id=user_id, stats=stats)
        except Exception as e:  # noqa: BLE001
            error = e
        params, metrics, tags = flashcards_run(stats, course=course, count=FLASHCARD_COUNT, deck=deck,
                                               error=error, source=SOURCE)
        log_run("flashcards", params, metrics, tags)
        rows.append(metrics)
        if error:
            _line(f"[flashcards {i}/{n}] ÉCHEC ({type(error).__name__}) après {metrics.get('duree_s', 0):.0f} s")
        else:
            _line(f"[flashcards {i}/{n}] {metrics['cartes_generees']:.0f}/{FLASHCARD_COUNT} cartes"
                  f" · {metrics.get('concepts_retenus', 0):.0f} concepts retenus"
                  f" · {metrics.get('appels_llm', 0):.0f} appels LLM · {metrics['duree_s']:.0f} s")
    return rows


def load_dataset(course: str) -> list[dict]:
    path = DATASETS / f"{course}.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    items = json.loads(path.read_text(encoding="utf-8"))
    # expected_page null : question hors cours, réussie si le tuteur répond NOT_FOUND
    return [{"question": str(it["question"]),
             "expected_page": None if it.get("expected_page") is None else int(it["expected_page"])}
            for it in items]


def run_tutor(course: str, user: User) -> list[dict]:
    """Questions du cours : hit rate @3 (page attendue parmi les sources renvoyées) et taux de réponses
    trouvées. Questions hors cours (expected_page null) : taux de refus corrects (NOT_FOUND) uniquement."""
    try:
        dataset = load_dataset(course)
    except FileNotFoundError as e:
        _line(f"[tuteur] pas de jeu de questions ({e}) : évaluation du tuteur ignorée.")
        return []
    rows = []
    for i, item in enumerate(dataset, start=1):
        stats, result, error = GenerationStats(), None, None
        try:
            # Réponse en streaming (comme la page Assistant) : mesure aussi time_to_first_token
            result = answer(item["question"], course, user_id=user.id, level=user.level, stats=stats,
                            on_token=lambda _fragment: None)
        except Exception as e:  # noqa: BLE001
            error = e
        pages = {s["page"] for s in result["sources"]} if result else set()
        # Même mesure sur la seule recherche Qdrant, sans tenir compte de la réponse du LLM
        retrieved = {h["page"] for h in search(embed_query(item["question"]), config.TOP_K, course, user_id=user.id)}
        params, metrics, tags = tutor_run(stats, course=course, level=user.level, error=error, source=SOURCE)
        answered = bool(metrics.get("reponse_trouvee"))
        if item["expected_page"] is None:
            # Hors cours : seul le refus compte ; ni hit_3 ni reponse_trouvee (réservés aux questions du cours)
            metrics.pop("reponse_trouvee", None)
            metrics["refus_correct"] = 1 if error is None and not answered else 0
        else:
            metrics["hit_3"] = 1 if item["expected_page"] in pages else 0
            metrics["hit_3_recherche"] = 1 if item["expected_page"] in retrieved else 0
        params["question_index"] = i  # le numéro de la question du jeu, jamais son texte
        log_run("tutor", params, metrics, tags)
        rows.append(metrics)
        status = "ÉCHEC" if error else ("trouvée" if answered else "NOT_FOUND")
        if item["expected_page"] is None:
            verdict = "refus correct" if metrics["refus_correct"] else "refus manqué"
            expected = "hors cours"
        else:
            verdict = "hit" if metrics["hit_3"] else "raté"
            expected = f"p.{item['expected_page']} attendue"
        _line(f"[tuteur {i}/{len(dataset)}] {expected} · sources {sorted(pages) or '—'}"
              f" · {verdict} · {status} · {metrics.get('duree_s', 0):.1f} s")
    return rows


def run_summary(course: str, user_id: int) -> list[dict]:
    """Un résumé du cours entier (toujours regénéré, sans le cache) : durée, sections, puces avec page valide."""
    _line("[résumé 1/1] résumé du cours entier…")
    stats, content, error = GenerationStats(), None, None
    try:
        content = generate_summary(course, "course", user_id=user_id, stats=stats)
    except Exception as e:  # noqa: BLE001
        error = e
    params, metrics, tags = summary_run(stats, course=course, mode="course", content=content, error=error,
                                        source=SOURCE)
    log_run("summary", params, metrics, tags)
    if error:
        _line(f"[résumé 1/1] ÉCHEC ({type(error).__name__}) après {metrics.get('duree_s', 0):.0f} s")
    else:
        _line(f"[résumé 1/1] {metrics.get('sections', 0):.0f} sections · {metrics.get('puces', 0):.0f} puces"
              f" · {metrics['taux_puces_page_valide']:.0%} des puces proposées avec une page valide"
              f" · {metrics.get('appels_llm', 0):.0f} appels LLM · {metrics['duree_s']:.0f} s")
    return [metrics]


def summary_rows(results: dict[str, list[dict]]) -> list[dict]:
    """Moyenne et écart-type de chaque métrique, par expérience."""
    rows = []
    for experiment, runs in results.items():
        keys = sorted({k for run in runs for k in run})
        for key in keys:
            values = [float(run[key]) for run in runs if key in run]
            rows.append({
                "experience": experiment,
                "metrique": key,
                "moyenne": round(statistics.fmean(values), 4),
                "ecart_type": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
                "n": len(values),
            })
    return rows


def print_summary(rows: list[dict]) -> None:
    width = max([len(r["metrique"]) for r in rows] + [10])
    _line("")
    _line(f"{'Expérience':<12} {'Métrique':<{width}} {'Moyenne':>10} {'Écart-type':>11} {'N':>4}")
    _line("-" * (width + 42))
    previous = None
    for r in rows:
        name = r["experience"] if r["experience"] != previous else ""
        previous = r["experience"]
        _line(f"{name:<12} {r['metrique']:<{width}} {_fmt(r['moyenne']):>10} {_fmt(r['ecart_type']):>11} {r['n']:>4}")


def write_csv(rows: list[dict], course: str) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", course).strip("_") or "cours"
    path = RESULTS / f"{safe}_{datetime.now():%Y-%m-%d_%H%M}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["experience", "metrique", "moyenne", "ecart_type", "n"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark des générations (examens, flashcards, tuteur).")
    parser.add_argument("email", help="email du compte propriétaire du cours")
    parser.add_argument("course", help="nom du cours")
    parser.add_argument("--n", type=int, default=3, help="nombre d'examens et de paquets à générer (défaut : 3)")
    parser.add_argument("--skip-exam", action="store_true")
    parser.add_argument("--skip-flashcards", action="store_true")
    parser.add_argument("--skip-tutor", action="store_true")
    parser.add_argument("--skip-summary", action="store_true")
    parser.add_argument("--optim", choices=["avant", "apres"], default="apres",
                        help="tag MLflow optim : avant ou après l'optimisation du code (défaut : apres)")
    args = parser.parse_args(argv)
    set_run_tags(optim=args.optim)
    logging.basicConfig(level=logging.WARNING, format="  %(levelname)s : %(message)s")

    init_db()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == args.email.strip().lower())).first()
        if user is None:
            _line(f"❌ Aucun compte avec l'email « {args.email} ».")
            return 1
        if get_user_course(session, user.id, args.course) is None:
            _line(f"❌ Le cours « {args.course} » n'appartient pas à ce compte "
                  "(importe-le, ou migre tes anciens cours avec app.phase8_personal.migrate_courses).")
            return 1
        session.expunge(user)

    _line(f"Benchmark « {args.course} » · modèle {config.LLM_MODEL} · n={args.n}"
          f" · MLflow {'activé (' + config.MLFLOW_TRACKING_URI + ')' if config.MLFLOW_ENABLED else 'désactivé'}")
    t0 = time.perf_counter()
    results: dict[str, list[dict]] = {}
    if not args.skip_exam:
        results["exam"] = run_exams(args.n, args.course, user.id)
    if not args.skip_flashcards:
        results["flashcards"] = run_flashcards(args.n, args.course, user.id)
    if not args.skip_tutor:
        results["tutor"] = run_tutor(args.course, user)
    if not args.skip_summary:
        results["summary"] = run_summary(args.course, user.id)
    results = {k: v for k, v in results.items() if v}

    if not results:
        _line("Rien à mesurer.")
        return 0
    rows = summary_rows(results)
    print_summary(rows)
    path = write_csv(rows, args.course)
    _line(f"\nRésultats : {path}  ({time.perf_counter() - t0:.0f} s au total)")
    if config.MLFLOW_ENABLED:
        _line("Interface : mlflow ui --backend-store-uri " + config.MLFLOW_TRACKING_URI)
    return 0


if __name__ == "__main__":
    sys.exit(main())
