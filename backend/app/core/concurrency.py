"""Parallélisme contrôlé des appels au LLM.

- llm_slot() : sémaphore partagé par toute l'application (LLM_CONCURRENCY appels au plus en même temps, y compris
  entre deux requêtes d'étudiants différents). Utilisé par phase1_llm.chat.
- parallel_map(fn, items) : applique fn à chaque élément, dans des threads si LLM_CONCURRENCY > 1. Avec 1, c'est
  une simple boucle : même ordre d'exécution, même comportement qu'avant. L'ordre des résultats suit toujours
  celui des éléments. Le contexte (collecteur de statistiques MLflow) est copié dans chaque thread.
"""
import contextvars
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from app.core import config

T = TypeVar("T")
R = TypeVar("R")

_slots = threading.BoundedSemaphore(config.LLM_CONCURRENCY)


def llm_slot() -> threading.BoundedSemaphore:
    return _slots


def concurrency() -> int:
    return config.LLM_CONCURRENCY


def parallel_map(fn: Callable[[T], R], items: Iterable[T]) -> list[R]:
    """[fn(x) for x in items], en parallèle si LLM_CONCURRENCY > 1. Une exception d'un élément est relancée."""
    items = list(items)
    workers = min(concurrency(), len(items))
    if workers <= 1:
        return [fn(item) for item in items]
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="llm") as executor:
        futures = [executor.submit(contextvars.copy_context().run, fn, item) for item in items]
        return [future.result() for future in futures]
