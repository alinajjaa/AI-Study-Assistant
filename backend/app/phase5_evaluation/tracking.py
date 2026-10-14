"""Enregistrement des générations dans MLflow (un run par génération) et résumé pour /api/stats.

Règles :
- Aucune donnée personnelle : seulement des nombres, des réglages et des noms de cours
  (jamais d'email, de nom ni de texte de question).
- MLflow désactivé ou indisponible : l'application continue normalement (warning dans les logs).
"""
import logging
import math
import os
import statistics
import time
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

from app.core import config
from app.phase5_evaluation.stats import REJECT_CAUSES, GenerationStats

logger = logging.getLogger("uvicorn.error")

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")  # message d'aide de MLflow inutile ici

EXPERIMENTS = ("exam", "flashcards", "tutor", "summary")
EXAM_KINDS = ("qcm", "vrai_faux", "courte", "ouverte")

# Un seul thread : l'enregistrement après une requête ne retarde pas la réponse à l'étudiant
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlflow")
_clients: dict[str, object] = {}


def _client():
    """Client MLflow (créé une fois par URI). Importé ici : MLflow est lent à charger."""
    uri = config.MLFLOW_TRACKING_URI
    if uri not in _clients:
        if uri.startswith("sqlite:///") and not uri.startswith("sqlite:////"):
            Path(uri.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        if uri.startswith("file:") or "://" not in uri:
            os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")  # stockage fichier explicitement choisi
        from mlflow.tracking import MlflowClient

        _clients[uri] = MlflowClient(tracking_uri=uri)
    return _clients[uri]


def _experiment_id(client, name: str) -> str:
    experiment = client.get_experiment_by_name(name)
    return experiment.experiment_id if experiment else client.create_experiment(name)


def log_run(experiment: str, params: dict, metrics: dict, tags: dict | None = None) -> str | None:
    """Enregistre un run MLflow. Renvoie son identifiant, ou None si MLflow est désactivé ou en erreur.

    Ne lève jamais d'exception : une panne de MLflow ne doit pas casser une génération.
    """
    if not config.MLFLOW_ENABLED:
        return None
    try:
        from mlflow.entities import Metric, Param

        client = _client()
        run = client.create_run(_experiment_id(client, experiment),
                                tags={k: str(v) for k, v in (tags or {}).items()})
        now = int(time.time() * 1000)
        client.log_batch(
            run.info.run_id,
            metrics=[Metric(k, float(v), now, 0) for k, v in metrics.items()
                     if isinstance(v, (int, float)) and math.isfinite(v)],
            params=[Param(k, str(v)[:500]) for k, v in params.items() if v is not None],
        )
        client.set_terminated(run.info.run_id)
        return run.info.run_id
    except Exception as e:  # noqa: BLE001 — MLflow ne doit jamais faire échouer l'application
        logger.warning("MLflow indisponible, run « %s » non enregistré : %s", experiment, e)
        return None


def log_run_async(experiment: str, params: dict, metrics: dict, tags: dict | None = None) -> Future | None:
    """Comme log_run, dans un thread à part (utilisé par les routes de l'application)."""
    if not config.MLFLOW_ENABLED:
        return None
    try:
        return _executor.submit(log_run, experiment, params, metrics, tags)
    except Exception as e:  # noqa: BLE001
        logger.warning("MLflow : enregistrement impossible : %s", e)
        return None


# ---------------------------------------------------------------------------
# Paramètres et métriques de chaque expérience
# ---------------------------------------------------------------------------

def _ratio(a: float, b: float) -> float:
    return round(a / b, 4) if b else 0.0


def _reject_rates(stats: GenerationStats) -> dict[str, float]:
    """Part des éléments générés par le LLM écartés pour chaque cause."""
    attempts = stats.get("appels_generation")
    return {f"taux_rejet_{cause}": _ratio(stats.get(f"rejets_{cause}"), attempts) for cause in REJECT_CAUSES}


def _tags(source: str, error: Exception | None) -> dict:
    tags = {"source": source, "statut": "echec" if error else "ok"}
    if error is not None:
        tags["erreur"] = type(error).__name__  # le type seulement, jamais le message
    return tags


def exam_run(stats: GenerationStats, *, course: str, fmt: str, difficulty: str, num_questions: int,
             exam=None, error: Exception | None = None, source: str = "app") -> tuple[dict, dict, dict]:
    """(params, métriques, tags) d'un examen généré (exam) ou raté (error)."""
    requested = exam.expected_questions if exam is not None else (num_questions if fmt == "qcm" else 15)
    tried = sum(stats.get(f"demandees_{k}") for k in EXAM_KINDS) or requested  # complément Vrai/Faux compris
    generated = exam.question_count if exam is not None else 0
    metrics = {
        **stats.as_metrics(),
        "questions_demandees": requested,
        "questions_generees": generated,
        "taux_reussite": _ratio(generated, tried),
        "total_points": exam.total_points if exam is not None else 0,
        "rendement_appels": _ratio(generated, stats.get("appels_llm")),
        **_reject_rates(stats),
    }
    if exam is not None:
        for kind in EXAM_KINDS:
            metrics[f"generees_{kind}"] = sum(1 for s in exam.sections for q in s.questions if q.type == kind)
    params = {"modele_llm": config.LLM_MODEL, "cours": course, "format": fmt, "difficulte": difficulty,
              "questions_demandees": requested, "passages": int(stats.values.get("passages", 0))}
    return params, metrics, _tags(source, error)


def flashcards_run(stats: GenerationStats, *, course: str, count: int, deck=None,
                   error: Exception | None = None, source: str = "app") -> tuple[dict, dict, dict]:
    generated = len(deck.cards) if deck is not None else 0
    metrics = {
        **stats.as_metrics(),
        "cartes_demandees": count,
        "cartes_generees": generated,
        "taux_reussite": _ratio(generated, count),
        "rendement_appels": _ratio(generated, stats.get("appels_llm")),
        **_reject_rates(stats),
    }
    params = {"modele_llm": config.LLM_MODEL, "cours": course, "cartes_demandees": count,
              "passages": int(stats.values.get("passages", 0))}
    return params, metrics, _tags(source, error)


def tutor_run(stats: GenerationStats, *, course: str | None, level: str | None,
              error: Exception | None = None, source: str = "app") -> tuple[dict, dict, dict]:
    metrics = stats.as_metrics()
    params = {"modele_llm": config.LLM_MODEL, "top_k": config.TOP_K, "niveau": level or "aucun",
              "cours": course or "tous"}
    return params, metrics, _tags(source, error)


def summary_run(stats: GenerationStats, *, course: str, mode: str, level: str | None = None,
                content=None, error: Exception | None = None, source: str = "app") -> tuple[dict, dict, dict]:
    """(params, métriques, tags) d'un résumé. Le thème demandé (texte de l'étudiant) n'est jamais enregistré."""
    metrics = {
        **stats.as_metrics(),
        "reussi": 1 if content is not None else 0,
        "taux_puces_page_valide": _ratio(stats.get("puces_page_valide"), stats.get("puces_proposees")),
        "taux_rejet_validation": _ratio(stats.get("rejets_validation"), stats.get("appels_generation")),
    }
    params = {"modele_llm": config.LLM_MODEL, "cours": course, "mode": mode,
              "niveau": (level or "aucun") if mode == "topic" else None,
              "passages": int(stats.values.get("passages", 0))}
    return params, metrics, _tags(source, error)


@contextmanager
def track_tutor(*, course: str | None, level: str | None, source: str = "app") -> Iterator[GenerationStats]:
    """Fournit un collecteur pour une réponse du tuteur, puis enregistre le run (même en cas d'erreur)."""
    stats = GenerationStats()
    error: Exception | None = None
    try:
        yield stats
    except Exception as e:
        error = e
        raise
    finally:
        log_run_async("tutor", *tutor_run(stats, course=course, level=level, error=error, source=source))


# ---------------------------------------------------------------------------
# Résumé pour GET /api/stats
# ---------------------------------------------------------------------------

SUCCESS_METRIC = {"exam": "taux_reussite", "flashcards": "taux_reussite", "tutor": "reponse_trouvee",
                  "summary": "reussi"}


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def summarize(max_runs: int = 2000) -> dict:
    """Moyennes de chaque expérience sur tous les runs enregistrés (application et benchmark)."""
    empty = {name: {"runs": 0, "duree_moyenne_s": None, "taux_reussite_moyen": None, "taux_rejet_moyens": {}}
             for name in EXPERIMENTS}
    if not config.MLFLOW_ENABLED:
        return {"mlflow": False, "portee": "globale", "experiences": empty}
    try:
        client = _client()
        result = {}
        for name in EXPERIMENTS:
            experiment = client.get_experiment_by_name(name)
            runs = client.search_runs([experiment.experiment_id], max_results=max_runs) if experiment else []
            metrics = [r.data.metrics for r in runs]

            def values(key: str) -> list[float]:
                return [m[key] for m in metrics if key in m]

            rejects = {cause: _mean(values(f"taux_rejet_{cause}")) for cause in REJECT_CAUSES}
            result[name] = {
                "runs": len(runs),
                "duree_moyenne_s": _mean(values("duree_s")),
                "taux_reussite_moyen": _mean(values(SUCCESS_METRIC[name])),
                "taux_rejet_moyens": {} if name == "tutor" else rejects,
            }
        return {"mlflow": True, "portee": "globale", "experiences": result}
    except Exception as e:  # noqa: BLE001
        logger.warning("MLflow indisponible pour les statistiques : %s", e)
        return {"mlflow": False, "portee": "globale", "experiences": empty}
