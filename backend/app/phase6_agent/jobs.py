"""Tâches de fond du Study Companion : un quiz, des flashcards ou un résumé prennent 1 à 3 minutes avec un LLM
local, plus que le délai d'une requête HTTP. La route lance la tâche, attend quelques secondes (une réponse
courte revient directement), sinon répond 202 avec l'identifiant à consulter (GET /api/companion/jobs/{id}).

Les tâches sont en mémoire (un seul processus uvicorn) et oubliées une heure après leur fin.
"""
import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from app.phase1_llm.llm import LLMError

logger = logging.getLogger("uvicorn.error")

JOB_TTL_S = 3600
WORKERS = 2  # le LLM local traite de toute façon les requêtes une par une


class JobError(Exception):
    """Erreur prévue (conversation supprimée…) : son message est montré à l'étudiant."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class Job:
    id: str
    user_id: int
    status: str = "running"  # running | done | error
    tool: str | None = None  # outil en cours d'exécution (pour « L'assistant génère un quiz… »)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    result: dict | None = None
    error: str | None = None
    error_status: int | None = None
    _done: threading.Event = field(default_factory=threading.Event, repr=False)

    def wait(self, timeout: float) -> bool:
        return self._done.wait(timeout)

    @property
    def elapsed_s(self) -> float:
        return round((self.finished_at or time.time()) - self.started_at, 1)


class JobStore:
    def __init__(self, workers: int = WORKERS):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="companion")

    def submit(self, user_id: int, work: Callable[[Job], dict]) -> Job:
        """Lance work(job) dans un thread ; son résultat (dict) devient job.result."""
        job = Job(id=uuid.uuid4().hex, user_id=user_id)
        with self._lock:
            self._purge()
            self._jobs[job.id] = job
        self._executor.submit(self._run, job, work)
        return job

    def get(self, job_id: str, user_id: int) -> Job | None:
        """La tâche de l'étudiant, ou None (même réponse si elle appartient à un autre étudiant)."""
        with self._lock:
            job = self._jobs.get(job_id)
        return job if job is not None and job.user_id == user_id else None

    def _run(self, job: Job, work: Callable[[Job], dict]) -> None:
        try:
            job.result = work(job)
            job.status = "done"
        except LLMError as e:
            job.status, job.error, job.error_status = "error", str(e), 503
        except JobError as e:
            job.status, job.error, job.error_status = "error", str(e), e.status
        except Exception:  # noqa: BLE001 — l'étudiant reçoit un message clair, le détail reste dans les logs
            logger.exception("Study Companion : échec de la tâche %s", job.id)
            job.status, job.error, job.error_status = "error", "Erreur interne de l'assistant. Réessaie.", 500
        finally:
            job.finished_at = time.time()
            job._done.set()

    def _purge(self) -> None:
        limit = time.time() - JOB_TTL_S
        for job_id in [j.id for j in self._jobs.values() if j.finished_at is not None and j.finished_at < limit]:
            del self._jobs[job_id]


jobs = JobStore()
