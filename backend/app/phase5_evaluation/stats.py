"""Collecteur de statistiques d'une génération (examen, flashcards, réponse du tuteur).

Les générateurs reçoivent un GenerationStats optionnel. Pendant la génération, il est rendu « actif »
(variable de contexte, propre à chaque requête) : les fonctions internes et l'appel au LLM l'incrémentent
via record() / reject(), sans changer leur signature. Sans collecteur, ces fonctions ne font rien :
le comportement des générateurs est exactement le même.

Uniquement des nombres : jamais de texte de question, d'email ni de nom.
"""
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

REJECT_CAUSES = ("validation", "verification", "doublon")


@dataclass
class GenerationStats:
    counters: Counter = field(default_factory=Counter)
    values: dict[str, float] = field(default_factory=dict)  # mesures ponctuelles (score max, passages…)
    duration_s: float | None = None

    def add(self, name: str, n: float = 1) -> None:
        self.counters[name] += n

    def get(self, name: str) -> float:
        return self.counters.get(name, 0)

    def set(self, name: str, value: float) -> None:
        self.values[name] = value

    def reject(self, cause: str, kind: str | None = None) -> None:
        """Un élément écarté : compté au total de la cause, et par type si le type est connu."""
        self.add(f"rejets_{cause}")
        if kind:
            self.add(f"rejets_{cause}_{kind}")

    def as_metrics(self) -> dict[str, float]:
        metrics = {**dict(self.counters), **self.values}
        if self.duration_s is not None:
            metrics["duree_s"] = round(self.duration_s, 3)
        return metrics


_current: ContextVar[GenerationStats | None] = ContextVar("generation_stats", default=None)


@contextmanager
def collecting(stats: GenerationStats | None) -> Iterator[GenerationStats | None]:
    """Active le collecteur pendant la génération et mesure sa durée (ne fait rien si stats est None)."""
    if stats is None:
        yield None
        return
    token = _current.set(stats)
    start = time.perf_counter()
    try:
        yield stats
    finally:
        stats.duration_s = time.perf_counter() - start
        _current.reset(token)


def record(name: str, n: float = 1) -> None:
    """Incrémente un compteur du collecteur actif (aucun effet sans collecteur)."""
    stats = _current.get()
    if stats is not None:
        stats.add(name, n)


def record_value(name: str, value: float) -> None:
    stats = _current.get()
    if stats is not None:
        stats.set(name, value)


def reject(cause: str, kind: str | None = None) -> None:
    """Compte un rejet (validation, verification ou doublon) dans le collecteur actif."""
    stats = _current.get()
    if stats is not None:
        stats.reject(cause, kind)
