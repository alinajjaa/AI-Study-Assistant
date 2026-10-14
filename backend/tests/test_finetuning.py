"""Phase 4 (fine-tuning) : filtres du jeu de données, format JSONL, reprise, scores avec un juge simulé."""
import json

import pytest

from app.core import config
from app.phase4_finetuning import dataset, evaluate
from app.phase4_finetuning.dataset import (
    FINETUNE_SYSTEM, QUESTION_SYSTEM, check_answer, clean_question, make_example, read_jsonl, split,
)

PASSAGE = {"course": "CNN", "page": 3, "text": (
    "Le pooling réduit la taille des cartes d'activation produites par les couches de convolution. "
    "Il garde l'information la plus importante et rend le réseau plus robuste aux petites translations. "
    "Contact du professeur : prof@example.com.")}

SENTENCE = "Le pooling réduit la taille des cartes et garde les informations utiles pour le réseau"


def french_answer(n_words: int, page: int = 3) -> str:
    """Réponse en français d'environ n_words mots, terminée par une référence de page."""
    base = SENTENCE.split()
    text = " ".join(base[i % len(base)] for i in range(n_words))
    return f"{text} [p.{page}]."


# ---------------------------------------------------------------------------
# Filtres des réponses idéales
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("level,n_words", [("debutant", 120), ("intermediaire", 80), ("avance", 50)])
def test_reponse_gardee(level, n_words):
    assert check_answer(french_answer(n_words), level, page=3) is None


@pytest.mark.parametrize("reply,level,cause", [
    ("Cette information n'est pas présente dans le cours.", "avance", "hors_cours"),
    ("The pooling layer reduces the size of the feature maps and is used with convolutions [p.3].",
     "avance", "anglais"),
    ("Pooling : max, average, stride, padding, kernel, tenseur, batch, epoch, GPU, CNN, ReLU, softmax, "
     "dropout, backpropagation, gradient, loss, optimizer, Adam, SGD, momentum, LeNet [p.3].",
     "avance", "francais"),
    (french_answer(30), "debutant", "longueur"),  # trop court pour un débutant (60 mots au moins)
    (french_answer(300), "avance", "longueur"),  # trop long pour un avancé
    (french_answer(50).replace(" [p.3]", ""), "avance", "reference"),  # aucune référence
    (french_answer(50, page=7), "avance", "reference"),  # page qui n'est pas celle du passage
    (french_answer(50).replace("Le pooling", "Le pooling est probablement"), "avance", "incertitude"),
])
def test_reponse_rejetee(reply, level, cause):
    assert check_answer(reply, level, page=3) == cause


def test_question_filtree():
    assert clean_question('{"question": "À quoi sert le pooling dans un réseau convolutif ?"}') == \
        "À quoi sert le pooling dans un réseau convolutif ?"
    assert clean_question('{"question": "Donne un exemple de couche de pooling utilisée dans un CNN."}')
    assert clean_question("pas du JSON") is None
    assert clean_question('{"question": "Le pooling"}') is None  # trop courte
    assert clean_question('{"question": "Pooling réduit la taille des cartes"}') is None  # pas une question
    assert clean_question('{"question": "What is the role of the pooling layer?"}') is None  # anglais
    assert clean_question('{"question": "Combien de couches de pooling contient le réseau ?"}') is None


# ---------------------------------------------------------------------------
# Format JSONL
# ---------------------------------------------------------------------------

def test_format_chat_et_donnees_masquees():
    example = make_example("abc-role", "role", "debutant", PASSAGE, "À quoi sert le pooling ?",
                           f"Écris à prof@example.com {french_answer(80)}")
    assert [m["role"] for m in example["messages"]] == ["system", "user", "assistant"]
    assert example["messages"][0]["content"] == FINETUNE_SYSTEM
    user = example["messages"][1]["content"]
    assert user.startswith("Niveau de l'étudiant : débutant.")
    assert "[p.3] Le pooling réduit" in user and "À quoi sert le pooling ?" in user
    assert "prof@example.com" not in json.dumps(example)  # mask_pii sur le passage et la réponse
    assert "[EMAIL]" in user and "[EMAIL]" in example["messages"][2]["content"]
    assert (example["id"], example["niveau"], example["page"]) == ("abc-role-debutant", "debutant", 3)


def test_decoupage_par_question(tmp_path):
    examples = [make_example(f"q{q}", "role", level, PASSAGE, "À quoi sert le pooling ?", french_answer(80))
                for q in range(20) for level in ("debutant", "intermediaire", "avance")]
    train, test = split(examples)
    assert len(train) + len(test) == 60
    assert len({e["qid"] for e in test}) == 2  # 10 % des 20 questions
    assert not {e["qid"] for e in train} & {e["qid"] for e in test}  # aucune fuite vers le test

    dataset.export(examples, data_dir=tmp_path)
    for name in ("train.jsonl", "test.jsonl", "sample.jsonl"):
        rows = read_jsonl(tmp_path / name)
        assert rows and all(len(r["messages"]) == 3 for r in rows)
    sample = read_jsonl(tmp_path / "sample.jsonl")
    assert len(sample) == 10 and {r["niveau"] for r in sample} == {"debutant", "intermediaire", "avance"}


# ---------------------------------------------------------------------------
# Génération avec un LLM simulé, et reprise
# ---------------------------------------------------------------------------

class TeacherLLM:
    """Pose une question, puis répond selon le niveau ; la réponse « avancé » est hors format (sans page)."""

    def __init__(self):
        self.calls = 0

    def __call__(self, system, user, **kwargs):
        self.calls += 1
        if system == QUESTION_SYSTEM:
            return json.dumps({"question": "Quel est le rôle du pooling dans un réseau convolutif ?"})
        if "avancé" in system:
            return french_answer(50).replace(" [p.3]", "").replace(" [p.4]", "")
        page = int(user.split("[p.")[1].split("]")[0])
        return french_answer(100, page=page)


def _passages(n):
    return [{**PASSAGE, "page": i + 1, "text": f"{i} {PASSAGE['text']}"} for i in range(n)]


def test_generation_rejets_et_reprise(monkeypatch, tmp_path):
    teacher = TeacherLLM()
    monkeypatch.setattr(dataset, "chat", teacher)

    examples, progress = dataset.build_dataset(_passages(4), n=4, data_dir=tmp_path, progress_bar=False)
    assert len(examples) == 4  # 2 questions × 2 niveaux gardés
    assert progress.questions == 2 and progress.rejects["reference"] == 2
    assert {e["niveau"] for e in examples} == {"debutant", "intermediaire"}
    calls = teacher.calls

    # Relance avec un objectif plus grand : les questions déjà traitées ne sont pas refaites
    examples, progress = dataset.build_dataset(_passages(4), n=8, data_dir=tmp_path, progress_bar=False)
    assert len(examples) == 8 and len(read_jsonl(tmp_path / "all.jsonl")) == 8
    assert len({e["id"] for e in examples}) == 8  # aucun doublon
    assert teacher.calls - calls == 2 * 4  # 2 nouvelles questions × (1 question + 3 réponses)
    assert progress.questions == 4 and progress.rejects["reference"] == 4


def test_generation_question_rejetee(monkeypatch, tmp_path):
    monkeypatch.setattr(dataset, "chat", lambda system, user, **kw: '{"question": "Pooling"}')
    examples, progress = dataset.build_dataset(_passages(2), n=3, data_dir=tmp_path, progress_bar=False)
    assert examples == [] and progress.rejects["question"] == 10  # 2 passages × 5 types de question


# ---------------------------------------------------------------------------
# Évaluation : juge simulé
# ---------------------------------------------------------------------------

def _result(example: dict, reply: str, variant: str) -> dict:
    return {"id": example["id"], "qid": example["qid"], "type": example["type"], "niveau": example["niveau"],
            "page": example["page"], "prompt": example["messages"][:-1], "reponse": reply,
            "modele": "Qwen/Qwen2.5-1.5B-Instruct" + (" + LoRA" if variant == "affine" else ""),
            "config": {"base_model": "Qwen/Qwen2.5-1.5B-Instruct", "adapter": "moi/study-tutor",
                       "lora_r": 16, "lora_alpha": 32, "lora_dropout": 0.05, "epochs": 3, "train_size": 270,
                       "temperature": 0.3}}


def _results():
    examples = [make_example(f"q{q}", "role", level, PASSAGE, "À quoi sert le pooling ?", "")
                for q in range(2) for level in ("debutant", "avance")]
    base = [_result(e, "The pooling is used for the size of the maps.", "base") for e in examples]
    tuned = [_result(e, french_answer(100 if e["niveau"] == "debutant" else 50), "affine") for e in examples]
    return base, tuned


def fake_judge(row, reply):
    """Note haute pour une réponse en français, basse sinon ; échoue sur une réponse précise."""
    if "échec" in reply:
        return None
    return {"niveau": 5, "fidelite": 4, "clarte": 9} if "pooling" in reply.lower() and "[p." in reply else \
        {"niveau": 1, "fidelite": 2, "clarte": 0}


def test_scores_base_contre_affine():
    base, tuned = _results()
    tuned[0]["reponse"] = "échec du juge"
    b, t, base_details, tuned_details = evaluate.evaluate(base, tuned, judge=fake_judge, progress=False)

    assert b["juge_niveau"] == 1 and b["juge_fidelite"] == 2 and b["juge_clarte"] == 1  # 0 ramené à 1
    assert t["juge_niveau"] == 5 and t["juge_clarte"] == 5  # 9 ramené à 5
    assert t["juge_moyenne"] == pytest.approx((5 + 4 + 5) / 3, abs=1e-3)
    assert t["echecs_juge"] == 1 and b["echecs_juge"] == 0 and t["reponses"] == 4
    assert b["taux_citation_valide"] == 0 and t["taux_citation_valide"] == 0.75
    assert b["taux_francais"] == 0 and t["taux_francais"] == 1
    assert t["mots_avance"] < t["mots_debutant"]
    assert len(base_details) == len(tuned_details) == 4

    rows = {r["metrique"]: r for r in evaluate.comparison_rows(b, t)}
    assert rows["juge_niveau"]["ecart"] == 4


def test_appariement_par_id():
    base, tuned = _results()
    b, t = evaluate.pair(base, list(reversed(tuned[1:])))
    assert [r["id"] for r in b] == [r["id"] for r in t] and len(b) == 3


def test_juge_llm(monkeypatch):
    base, _ = _results()
    monkeypatch.setattr(evaluate, "chat", lambda system, user, **kw: '{"niveau": 4, "fidelite": 5, "clarte": 3}')
    assert evaluate.llm_judge(base[0], "Réponse") == {"niveau": 4, "fidelite": 5, "clarte": 3}
    monkeypatch.setattr(evaluate, "chat", lambda system, user, **kw: "pas du JSON")
    assert evaluate.llm_judge(base[0], "Réponse") is None


def test_main_csv_et_mlflow(monkeypatch, tmp_path):
    from mlflow.tracking import MlflowClient

    from app.phase5_evaluation import tracking

    base, tuned = _results()
    for name, rows in (("base.jsonl", base), ("affine.jsonl", tuned)):
        dataset.write_jsonl(tmp_path / name, rows)
    monkeypatch.setattr(evaluate, "chat", lambda system, user, **kw: '{"niveau": 3, "fidelite": 4, "clarte": 5}')
    monkeypatch.setattr(evaluate, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(config, "MLFLOW_ENABLED", True)
    tracking._clients.clear()

    assert evaluate.main([str(tmp_path / "base.jsonl"), str(tmp_path / "affine.jsonl")]) == 0

    csv_files = list((tmp_path / "results").glob("finetuning_*.csv"))
    assert len(csv_files) == 1 and "juge_niveau,3.0,3.0,0.0" in csv_files[0].read_text(encoding="utf-8")
    client = MlflowClient(tracking_uri=config.MLFLOW_TRACKING_URI)
    experiment = client.get_experiment_by_name("finetuning")
    runs = {r.data.tags["variante"]: r for r in client.search_runs([experiment.experiment_id])}
    try:
        assert set(runs) == {"base", "affine"}
        assert runs["affine"].data.params["lora_r"] == "16"
        assert runs["affine"].data.params["adaptateur"] == "moi/study-tutor"
        assert runs["base"].data.params["adaptateur"] == "aucun"
        assert runs["base"].data.metrics["juge_clarte"] == 5
    finally:
        for run in runs.values():
            client.delete_run(run.info.run_id)


# ---------------------------------------------------------------------------
# Fournisseur hf-local (désactivé par défaut)
# ---------------------------------------------------------------------------

def test_fournisseur_hf_local(monkeypatch):
    from app.phase1_llm import llm
    from app.phase4_finetuning import hf_local

    assert config.LLM_PROVIDER == "openai"  # par défaut : Ollama, rien n'est chargé

    class FakeCompletions:
        def create(self, **kwargs):
            message = type("M", (), {"content": '{"ok": true}'})
            return type("R", (), {"choices": [type("C", (), {"message": message})]})

    monkeypatch.setattr(llm.client.chat, "completions", FakeCompletions())
    monkeypatch.setattr(hf_local, "generate", lambda system, user, **kw: "réponse du modèle affiné [p.1]")
    monkeypatch.setattr(config, "LLM_PROVIDER", "hf-local")

    assert llm.chat("système", "question") == "réponse du modèle affiné [p.1]"
    assert llm.chat("système", "question", json_mode=True) == '{"ok": true}'  # JSON : reste sur Ollama
