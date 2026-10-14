"""Évaluation du fine-tuning : modèle de BASE contre modèle AFFINÉ, sur les mêmes prompts du jeu de test.

Usage :
    python -m app.phase4_finetuning.evaluate <results_base.jsonl> <results_finetuned.jsonl> [--limit N]

Les deux fichiers viennent du notebook Colab (une ligne par exemple de test : id, niveau, page, prompt,
reponse…). Pour chaque réponse :
- un juge LLM (le LLM configuré, qwen2.5:7b) note de 1 à 5 le respect du niveau demandé, la fidélité au
  passage du cours et la clarté. Il ne sait pas quel modèle a écrit la réponse ;
- des mesures automatiques : longueur (en mots, par niveau), référence [p.X] valide, français.

Deux runs sont enregistrés dans MLflow (expérience « finetuning », runs « base » et « affine ») et un CSV
récapitulatif est écrit dans app/phase4_finetuning/results/, avec le détail des notes par exemple.
"""
import argparse
import csv
import json
import logging
import statistics
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from app.core import config
from app.core.privacy import mask_pii
from app.phase1_llm.llm import LLMError, chat
from app.phase4_finetuning.dataset import (
    LENGTH_WORDS, LEVEL_LABELS, has_english, is_french, read_jsonl, valid_citation, words,
)
from app.phase8_personal.models import LEVELS
from app.phase5_evaluation.tracking import log_run

RESULTS = Path(__file__).parent / "results"
EXPERIMENT = "finetuning"
CRITERIA = ("niveau", "fidelite", "clarte")

# Ce que chaque niveau attend (même esprit que la consigne du tuteur, formulé pour le juge)
LEVEL_EXPECTATIONS = {
    "debutant": "mots simples, chaque terme technique défini, une analogie de la vie courante et un exemple concret",
    "intermediaire": "explication claire avec les termes du cours et un exemple",
    "avance": "réponse précise et technique, sans définitions de base, qui relie les notions entre elles",
}

JUDGE_SYSTEM = (
    "Tu es un enseignant exigeant qui évalue la réponse d'un tuteur à un étudiant. "
    "Tu réponds UNIQUEMENT avec un objet JSON valide."
)
# La justification vient avant les notes : le juge raisonne d'abord, puis note
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"justification": {"type": "string"},
                   **{c: {"type": "integer", "minimum": 1, "maximum": 5} for c in CRITERIA}},
    "required": ["justification", *CRITERIA],
}

Judge = Callable[[dict, str], dict[str, int] | None]


def judge_prompt(row: dict, reply: str) -> str:
    level = row["niveau"]
    student = next(m["content"] for m in row["prompt"] if m["role"] == "user")
    return mask_pii(f"""Message de l'étudiant (niveau, extrait du cours et question) :
{student}

Réponse du tuteur :
{reply}

Évalue la réponse sur 3 critères, chacun noté de 1 (très mauvais) à 5 (excellent) :
- "niveau" : respect du niveau {LEVEL_LABELS[level]} demandé ({LEVEL_EXPECTATIONS[level]}).
  Une réponse trop technique pour un débutant, ou trop élémentaire pour un avancé, a 2 au plus.
- "fidelite" : fidélité à l'extrait du cours. Une information absente de l'extrait ou fausse a 2 au plus
  (une analogie qui sert seulement à illustrer est permise).
- "clarte" : clarté, organisation et français correct.

Commence par "justification" : 2 phrases au plus sur les points forts et les défauts. Puis donne les 3 notes.
Format attendu : {{"justification": "...", "niveau": <1 à 5>, "fidelite": <1 à 5>, "clarte": <1 à 5>}}""")


def llm_judge(row: dict, reply: str) -> dict[str, int] | None:
    """Notes du juge LLM (température 0), ou None si sa réponse est inutilisable."""
    try:
        raw = chat(JUDGE_SYSTEM, judge_prompt(row, reply), max_tokens=250, temperature=0.0,
                   json_schema=JUDGE_SCHEMA)
        data = json.loads(raw)
        return {c: int(data[c]) for c in CRITERIA}
    except (LLMError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logging.warning("Juge : note ignorée (%s)", type(e).__name__)
        return None


# ---------------------------------------------------------------------------
# Mesures
# ---------------------------------------------------------------------------

def auto_metrics(row: dict) -> dict[str, float]:
    """Mesures sans LLM d'une réponse : longueur, citation, français, longueur adaptée au niveau."""
    reply = row["reponse"]
    n_words = len(words(reply))
    low, high = LENGTH_WORDS[row["niveau"]]
    return {
        "mots": n_words,
        "citation_valide": 1 if valid_citation(reply, row["page"]) else 0,
        "francais": 1 if is_french(reply) and not has_english(reply) else 0,
        "longueur_adaptee": 1 if low <= n_words <= high else 0,
    }


def score_rows(rows: list[dict], judge: Judge = llm_judge, label: str = "") -> list[dict]:
    """Une ligne de détail par réponse : mesures automatiques + notes du juge (absentes si le juge échoue)."""
    from tqdm import tqdm

    details = []
    for row in tqdm(rows, desc=f"Juge {label}".strip(), unit="rép", disable=not label):
        detail = {"id": row["id"], "niveau": row["niveau"], **auto_metrics(row)}
        notes = judge(row, row["reponse"])
        if notes is not None:
            notes = {c: min(5, max(1, int(notes[c]))) for c in CRITERIA}
            detail.update({f"juge_{c}": notes[c] for c in CRITERIA})
            detail["juge_moyenne"] = round(statistics.fmean(notes.values()), 4)
        details.append(detail)
    return details


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def aggregate(details: list[dict]) -> dict[str, float]:
    """Moyennes d'un modèle (notes du juge sur les réponses notées seulement)."""
    def values(key: str, level: str | None = None) -> list[float]:
        return [d[key] for d in details if key in d and (level is None or d["niveau"] == level)]

    metrics = {f"juge_{c}": _mean(values(f"juge_{c}")) for c in (*CRITERIA, "moyenne")}
    for level in LEVELS:
        metrics[f"juge_niveau_{level}"] = _mean(values("juge_niveau", level))
        metrics[f"mots_{level}"] = _mean(values("mots", level))
    metrics.update({
        "mots_moyen": _mean(values("mots")),
        "taux_citation_valide": _mean(values("citation_valide")),
        "taux_francais": _mean(values("francais")),
        "taux_longueur_adaptee": _mean(values("longueur_adaptee")),
        "reponses": len(details),
        "echecs_juge": sum(1 for d in details if "juge_moyenne" not in d),
    })
    return {k: v for k, v in metrics.items() if v is not None}


def pair(base: list[dict], tuned: list[dict]) -> tuple[list[dict], list[dict]]:
    """Garde les exemples présents dans les deux fichiers, dans le même ordre (comparaison équitable)."""
    tuned_by_id = {r["id"]: r for r in tuned}
    common = [r for r in base if r["id"] in tuned_by_id]
    return common, [tuned_by_id[r["id"]] for r in common]


def run_params(rows: list[dict], variant: str) -> dict:
    """Paramètres MLflow : lus dans le champ « config » écrit par le notebook (modèle, LoRA, taille du jeu)."""
    cfg = next((r["config"] for r in rows if isinstance(r.get("config"), dict)), {})
    params = {
        "variante": variant,
        "modele": cfg.get("base_model") or rows[0].get("modele", "inconnu"),
        "adaptateur": cfg.get("adapter", "aucun") if variant == "affine" else "aucun",
        "juge": config.LLM_MODEL,
        "taille_test": len(rows),
        "temperature_generation": cfg.get("temperature"),
    }
    for key in ("lora_r", "lora_alpha", "lora_dropout", "epochs", "learning_rate", "train_size", "quantization"):
        if key in cfg:
            params[key] = cfg[key]
    return params


def evaluate(base: list[dict], tuned: list[dict], judge: Judge = llm_judge,
             progress: bool = True) -> tuple[dict, dict, list[dict], list[dict]]:
    """(métriques base, métriques affiné, détails base, détails affiné)."""
    base, tuned = pair(base, tuned)
    if not base:
        raise ValueError("aucun exemple commun aux deux fichiers (champ « id »)")
    base_details = score_rows(base, judge, "base" if progress else "")
    tuned_details = score_rows(tuned, judge, "affiné" if progress else "")
    return aggregate(base_details), aggregate(tuned_details), base_details, tuned_details


def comparison_rows(base_metrics: dict, tuned_metrics: dict) -> list[dict]:
    keys = list(dict.fromkeys([*base_metrics, *tuned_metrics]))
    rows = []
    for key in keys:
        b, t = base_metrics.get(key), tuned_metrics.get(key)
        rows.append({"metrique": key, "base": b, "affine": t,
                     "ecart": round(t - b, 4) if b is not None and t is not None else None})
    return rows


def _fmt(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "—"
    text = f"{value:+.3g}" if signed else f"{value:.3g}"
    return text if abs(value) < 1000 else f"{value:.0f}"


def print_table(rows: list[dict]) -> None:
    width = max(len(r["metrique"]) for r in rows)
    print(f"\n{'Métrique':<{width}} {'Base':>9} {'Affiné':>9} {'Écart':>9}")
    print("-" * (width + 30))
    for r in rows:
        print(f"{r['metrique']:<{width}} {_fmt(r['base']):>9} {_fmt(r['affine']):>9} {_fmt(r['ecart'], True):>9}")


def write_outputs(rows: list[dict], base_details: list[dict], tuned_details: list[dict],
                  results_dir: Path | None = None) -> Path:
    results_dir = results_dir or RESULTS
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y-%m-%d_%H%M}"
    path = results_dir / f"finetuning_{stamp}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metrique", "base", "affine", "ecart"])
        writer.writeheader()
        writer.writerows(rows)
    with (results_dir / f"finetuning_{stamp}_details.jsonl").open("w", encoding="utf-8") as f:
        for variant, details in (("base", base_details), ("affine", tuned_details)):
            for d in details:
                f.write(json.dumps({"variante": variant, **d}, ensure_ascii=False) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare le modèle de base et le modèle affiné (juge LLM).")
    parser.add_argument("base", type=Path, help="results_base.jsonl (notebook Colab)")
    parser.add_argument("finetuned", type=Path, help="results_finetuned.jsonl (notebook Colab)")
    parser.add_argument("--limit", type=int, default=None, help="n'évalue que les N premiers exemples")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="  %(levelname)s : %(message)s")

    for path in (args.base, args.finetuned):
        if not path.exists():
            print(f"❌ Fichier introuvable : {path}")
            return 1
    base, tuned = read_jsonl(args.base), read_jsonl(args.finetuned)
    if args.limit:
        base = base[:args.limit]
    print(f"Juge : {config.LLM_MODEL} · {len(base)} réponses de base · {len(tuned)} réponses du modèle affiné")

    try:
        base_metrics, tuned_metrics, base_details, tuned_details = evaluate(base, tuned)
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    base, tuned = pair(base, tuned)
    for variant, rows, metrics in (("base", base, base_metrics), ("affine", tuned, tuned_metrics)):
        log_run(EXPERIMENT, run_params(rows, variant), metrics,
                tags={"source": "finetuning", "variante": variant, "mlflow.runName": variant})

    rows = comparison_rows(base_metrics, tuned_metrics)
    print_table(rows)
    path = write_outputs(rows, base_details, tuned_details)
    print(f"\nRécapitulatif : {path}")
    if config.MLFLOW_ENABLED:
        print(f"MLflow : expérience « {EXPERIMENT} » · mlflow ui --backend-store-uri {config.MLFLOW_TRACKING_URI}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
