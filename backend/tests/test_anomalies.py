"""Anomalies relevées pendant les mesures (docs/qualite-ia.md, journal des bugs) : un test par anomalie."""
import json
import re
from pathlib import Path

from app.core import config
from app.phase4_exam import generator
from app.phase4_exam.schemas import TrueFalseQuestion
from app.phase5_evaluation.stats import GenerationStats, collecting

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
PASSAGE = [{"page": 3, "text": "Le pooling réduit la taille des cartes d'activation."}]


def test_modele_par_defaut_identique_a_env_example():
    """Sans LLM_MODEL, le code utilisait qwen2.5:3b alors que .env.example et la documentation disent qwen2.5:7b."""
    active = [line for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
              if re.match(r"^LLM_MODEL=", line)]
    assert active == [f"LLM_MODEL={config.DEFAULT_LLM_MODEL}"]
    assert config.DEFAULT_LLM_MODEL == "qwen2.5:7b"


def _statement(answer: bool) -> TrueFalseQuestion:
    return TrueFalseQuestion(statement="Le pooling réduit la taille des cartes d'activation.", answer=answer,
                             correction="Le pooling réduit bien la taille des cartes.", page=3)


def test_verification_vrai_faux_reponse_en_trop_ignoree(monkeypatch):
    """Mesure du 19/10 : pour 1 affirmation, le vérificateur a renvoyé {"answers":[true,false]}."""
    monkeypatch.setattr(generator, "chat", lambda *a, **k: json.dumps({"answers": [True, False]}))
    stats = GenerationStats()
    with collecting(stats):
        kept = generator.verify_true_false([_statement(True)], PASSAGE)
    assert len(kept) == 1  # la première réponse est la bonne : l'affirmation est gardée
    assert stats.counters.get("verifications_impossibles", 0) == 0


def test_verification_vrai_faux_reponse_en_trop_qui_contredit(monkeypatch):
    monkeypatch.setattr(generator, "chat", lambda *a, **k: json.dumps({"answers": [False, True]}))
    assert generator.verify_true_false([_statement(True)], PASSAGE) == []


def test_verification_sans_reponse_garde_la_question_et_le_compte(monkeypatch):
    monkeypatch.setattr(generator, "chat", lambda *a, **k: json.dumps({"answers": []}))
    stats = GenerationStats()
    with collecting(stats):
        kept = generator.verify_true_false([_statement(True)], PASSAGE)
    assert len(kept) == 1
    assert stats.counters["verifications_impossibles"] == 1
