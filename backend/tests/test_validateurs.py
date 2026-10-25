"""Non-régression des bugs corrigés en phase conversationnelle (docs/qualite-ia.md, journal C1 à C10).

Ces correctifs n'avaient aucun test : les validateurs des examens et des flashcards étaient couverts seulement
par les routes, avec des générateurs simulés.
"""
import json

import pytest
from pydantic import ValidationError

from app.phase4_exam.schemas import MCQQuestion, OpenQuestion, ShortAnswerQuestion
from app.phase7_flashcards import generator as fc
from app.phase7_flashcards.schemas import Concept, Flashcard
from tests.helpers import fake_vector

MCQ = {"question": "Quel est le rôle du pooling ?",
       "choices": ["Réduire la taille", "Ajouter des poids", "Normaliser les données", "Mélanger les pixels"],
       "answer": "A", "explanation": "Le pooling réduit la taille des cartes d'activation.", "page": 3}
CARD = {"concept": "Pooling", "front": "Quel est le rôle du pooling ?",
        "back": "Il réduit la taille des cartes d'activation produites par la convolution.", "page": 3}
LONG_TEXT = "Le pooling réduit la taille des cartes d'activation produites par les couches de convolution."


# C1 — caractères de contrôle produits par un antislash mal échappé dans le JSON du modèle
def test_c1_antislashs_restaures():
    raw = json.loads('{"q": "Où installer Flutter, par exemple C:\\flutter\\bin ?"}')["q"]
    assert "\f" in raw and "\b" in raw  # \f = saut de page, \b = retour arrière
    question = ShortAnswerQuestion(question=raw, expected_answer="Dans le dossier indiqué par le cours.", page=2)
    assert question.question == "Où installer Flutter, par exemple C:\\flutter\\bin ?"


# C4 — une question de réflexion peut enchaîner deux consignes, pas un QCM
def test_c4_question_ouverte_avec_et_comment_acceptee():
    question = OpenQuestion(
        question="Expliquez le rôle du pooling et comment il rend le réseau plus robuste ?",
        expected_points=["Le pooling réduit la taille.", "Il garde l'information utile.",
                         "Il limite les paramètres.", "Il tolère les petites translations."],
        page=3)
    assert question.question.startswith("Expliquez")


def test_c4_qcm_double_question_refuse_et_ouverte_a_deux_points_d_interrogation_refusee():
    with pytest.raises(ValidationError, match="deux questions"):
        MCQQuestion(**{**MCQ, "question": "Quel est le rôle du pooling et comment le régler ?"})
    with pytest.raises(ValidationError, match="deux questions"):
        OpenQuestion(question="Pourquoi le pooling ? Comment le régler ?",
                     expected_points=["Point un du cours.", "Point deux du cours.", "Point trois du cours.",
                                      "Point quatre du cours."], page=3)


# C5 — l'attribut page des flashcards est obligatoire (il avait été supprimé)
def test_c5_page_obligatoire_et_corrigee_si_absente_du_contexte(monkeypatch):
    with pytest.raises(ValidationError, match="page"):
        Flashcard(**{k: v for k, v in CARD.items() if k != "page"})
    monkeypatch.setattr(fc, "chat", lambda *a, **k: json.dumps({"items": [{**CARD, "page": 40}]}))
    card = fc.make_card(Concept(name="Pooling", importance=3), [{"page": 3, "text": LONG_TEXT},
                                                                  {"page": 5, "text": LONG_TEXT}])
    assert card.page == 5  # page la plus proche parmi celles fournies


# C6 — caractères cyrilliques glissés dans un mot français
def test_c6_caracteres_cyrilliques_refuses():
    with pytest.raises(ValidationError, match="non latins"):
        MCQQuestion(**{**MCQ, "explanation": "Le pooling permet d'effектer une réduction de taille."})
    with pytest.raises(ValidationError, match="non latins"):
        Flashcard(**{**CARD, "back": "Il réduit la taille des cartes d'activatиon."})


# C7 — réponse coupée par la limite de longueur (maxLength) du schéma
def test_c7_verso_coupe_ou_trop_long_refuse():
    with pytest.raises(ValidationError, match="coupée"):
        Flashcard(**{**CARD, "back": "Il réduit la taille des cartes d'activation produites par la"})
    with pytest.raises(ValidationError):
        Flashcard(**{**CARD, "back": "Il réduit la taille. " * 15})  # plus de 250 caractères


# C8 — deux cartes de même sens : une seule est gardée
def test_c8_carte_en_double_ecartee(monkeypatch):
    concepts = [Concept(name="Pooling", importance=3), Concept(name="Sous-échantillonnage", importance=3)]
    chunks = [{"page": 3, "text": LONG_TEXT}, {"page": 4, "text": LONG_TEXT + " Il garde le maximum."}]
    monkeypatch.setattr(fc, "get_course_chunks", lambda course, user_id: chunks)
    monkeypatch.setattr(fc, "extract_concepts", lambda c, n: (concepts, None))
    monkeypatch.setattr(fc, "select_concepts", lambda c, limit: c)
    monkeypatch.setattr(fc, "embed_passages", lambda texts: [fake_vector(t) for t in texts])
    monkeypatch.setattr(fc, "embed_query", fake_vector)
    monkeypatch.setattr(fc, "verify_card", lambda card, context: True)
    monkeypatch.setattr(fc, "make_card", lambda concept, context, temperature=0.4: Flashcard(**CARD))

    deck = fc.generate_flashcards("CNN", count=10, user_id=1)

    assert len(deck.cards) == 1


# C9 — juge des cartes : il ne rejette qu'une erreur certaine
def test_c9_verification_demande_une_erreur_certaine(monkeypatch):
    prompts = []

    def judge(system, user, **kwargs):
        prompts.append(user)
        return json.dumps({"answers": [False]})

    monkeypatch.setattr(fc, "chat", judge)
    assert fc.verify_card(Flashcard(**CARD), [{"page": 3, "text": LONG_TEXT}]) is True
    assert "contient-elle une ERREUR" in prompts[0] and "seulement si tu es sûr" in prompts[0]

    monkeypatch.setattr(fc, "chat", lambda *a, **k: json.dumps({"answers": [True]}))
    assert fc.verify_card(Flashcard(**CARD), [{"page": 3, "text": LONG_TEXT}]) is False


# C10 — fragments de découpage trop courts exclus des flashcards
def test_c10_fragments_courts_exclus(monkeypatch):
    seen = {}
    chunks = [{"page": 1, "text": "ingle one."}, {"page": 2, "text": LONG_TEXT}]
    monkeypatch.setattr(fc, "get_course_chunks", lambda course, user_id: chunks)

    def extract(passages, count):
        seen["texts"] = [p["text"] for p in passages]
        return [], None

    monkeypatch.setattr(fc, "extract_concepts", extract)
    with pytest.raises(ValueError):
        fc.generate_flashcards("CNN", count=10, user_id=1)
    assert seen["texts"] == [LONG_TEXT]
    assert len("ingle one.") < fc.MIN_PASSAGE_CHARS
