"""Évaluation du choix d'outil de l'agent Study Companion.

Usage :
    python -m app.phase5_evaluation.agent_eval <email> [--dataset chemin.json]

Pour chaque demande du jeu (datasets/agent_requests.json : message + outil attendu, null = réponse directe),
l'agent choisit son outil (tool calling, puis repli par classification si besoin) et s'arrête là : les outils
longs ne sont pas exécutés. Le contexte est celui de l'étudiant <email> (ses cours, son niveau ; le premier
cours est « sélectionné », comme dans la page).

Résultat : taux de bon outil (global et par outil attendu) et taux de repli, dans la console, dans MLflow
(expérience « agent_eval ») et dans app/phase5_evaluation/results/agent_eval_<date>.csv.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, select

from app.core import config
from app.core.db import engine, init_db
from app.phase5_evaluation.tracking import log_run
from app.phase6_agent.graph import run_agent
from app.phase6_agent.tools import AgentContext
from app.phase8_personal.courses import list_user_courses
from app.phase8_personal.models import User

HERE = Path(__file__).parent
DATASET = HERE / "datasets" / "agent_requests.json"
RESULTS = HERE / "results"
NONE = "aucun"


def load_dataset(path: Path) -> list[dict]:
    items = json.loads(path.read_text(encoding="utf-8"))
    return [{"message": item["message"], "expected": item.get("expected") or NONE} for item in items]


def evaluate(user: User, courses: list[str], dataset: list[dict], session: Session, llm=None,
             echo=print) -> tuple[list[dict], dict]:
    """Choix de l'outil pour chaque demande (dry_run) → (lignes détaillées, métriques)."""
    rows = []
    for i, item in enumerate(dataset, start=1):
        ctx = AgentContext(session=session, user=user, courses=courses,
                           selected_course=courses[0] if courses else None, message=item["message"])
        try:
            result = run_agent(ctx, llm=llm, dry_run=True)
            chosen, fallback, duration, error = (result.tools[0] if result.tools else NONE), result.fallback, \
                result.duration_s, ""
        except Exception as e:  # noqa: BLE001 — un échec compte comme un mauvais choix
            chosen, fallback, duration, error = "erreur", False, 0.0, type(e).__name__
        ok = chosen == item["expected"]
        rows.append({"message": item["message"], "attendu": item["expected"], "choisi": chosen,
                     "correct": int(ok), "repli": int(fallback), "duree_s": round(duration, 2), "erreur": error})
        echo(f"[{i:2}/{len(dataset)}] {'OK ' if ok else 'KO '} attendu={item['expected']:<20} "
             f"choisi={chosen:<20} repli={'oui' if fallback else 'non'} ({duration:.1f} s)")

    n = len(rows)
    metrics = {
        "taux_bon_outil": round(sum(r["correct"] for r in rows) / n, 4) if n else 0.0,
        "taux_repli": round(sum(r["repli"] for r in rows) / n, 4) if n else 0.0,
        "duree_moyenne_s": round(sum(r["duree_s"] for r in rows) / n, 3) if n else 0.0,
        "demandes": n,
    }
    by_tool: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        by_tool[r["attendu"]].append(r["correct"])
    for tool, results in by_tool.items():
        metrics[f"taux_bon_outil_{tool}"] = round(sum(results) / len(results), 4)
    return rows, metrics


def main(argv: list[str] | None = None, llm=None) -> dict:
    parser = argparse.ArgumentParser(description="Taux de bon outil choisi par l'agent Study Companion.")
    parser.add_argument("email")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--optim", choices=["avant", "apres"], default="apres", help="tag MLflow optim")
    args = parser.parse_args(argv)

    init_db()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == args.email.strip().lower())).first()
        if user is None:
            print(f"Aucun compte avec l'email « {args.email} ».", file=sys.stderr)
            raise SystemExit(1)
        courses = list_user_courses(session, user.id)
        dataset = load_dataset(args.dataset)
        print(f"Évaluation de l'agent ({config.LLM_MODEL}) : {len(dataset)} demandes, "
              f"{len(courses)} cours, niveau {user.level}\n", flush=True)
        rows, metrics = evaluate(user, courses, dataset, session, llm=llm,
                                 echo=lambda line: print(line, flush=True))

    params = {"modele_llm": config.LLM_MODEL, "jeu": args.dataset.name, "demandes": len(rows),
              "cours": len(courses), "niveau": user.level}
    run_id = log_run("agent_eval", params, metrics, {"source": "evaluation", "optim": args.optim,
                                                     "llm_concurrency": str(config.LLM_CONCURRENCY)})

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"agent_eval_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["message"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nTaux de bon outil : {metrics['taux_bon_outil']:.0%}  ·  repli utilisé : {metrics['taux_repli']:.0%}"
          f"  ·  durée moyenne du choix : {metrics['duree_moyenne_s']:.1f} s")
    for key in sorted(k for k in metrics if k.startswith("taux_bon_outil_")):
        print(f"  {key.removeprefix('taux_bon_outil_'):<20} {metrics[key]:.0%}")
    print(f"Détail : {out}")
    print(f"MLflow : expérience « agent_eval », run {run_id}" if run_id else "MLflow : désactivé ou indisponible")
    return metrics


if __name__ == "__main__":
    main()
