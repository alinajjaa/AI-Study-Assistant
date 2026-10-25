"""Refactorings sans changement de comportement (docs/qualite-ia.md, section 4)."""
from app.core.passages import format_course
from app.phase4_exam import generator as exam
from app.phase5_evaluation.tracking import _values
from app.phase7_flashcards import generator as flashcards
from app.phase9_summaries import generator as summaries

PASSAGES = [{"page": 3, "text": "Le pooling réduit la taille."}, {"page": 4, "text": "La convolution filtre."}]


def test_format_des_passages_inchange():
    """Même texte qu'avant le refactoring : les prompts des générateurs restent identiques."""
    assert format_course(PASSAGES) == "[page 3] Le pooling réduit la taille.\n\n[page 4] La convolution filtre."


def test_une_seule_fonction_pour_les_trois_generateurs():
    assert exam.format_course is flashcards.format_course is summaries.format_course is format_course


def test_valeurs_d_une_metrique():
    metrics = [{"duree_s": 2.0}, {"autre": 1.0}, {"duree_s": 4.0}]
    assert _values(metrics, "duree_s") == [2.0, 4.0]
    assert _values(metrics, "absente") == []
