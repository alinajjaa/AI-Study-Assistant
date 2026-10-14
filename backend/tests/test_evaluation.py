import json
import random

import pytest
from qdrant_client.models import PointStruct

from app.core import config
from app.phase2_embeddings import vectorstore
from app.phase5_evaluation import tracking
from app.phase5_evaluation.stats import GenerationStats, collecting, record, reject
from tests.helpers import fake_vector, register, sample_exam, upload

LONG_TEXT = ("Le pooling réduit la taille des cartes d'activation produites par les couches de convolution "
             "et garde l'information la plus importante du passage. ") * 3


def _add_chunks(n: int = 6, user_id: int = 1, course: str = "CNN") -> None:
    vectorstore.client.upsert("courses", points=[
        PointStruct(id=i + 100, vector=fake_vector(f"p{i}"),
                    payload={"course": course, "page": i + 1, "text": f"{i} {LONG_TEXT}", "user_id": user_id})
        for i in range(n)
    ])


class SyncExecutor:
    """Remplace le thread MLflow : l'enregistrement est fait tout de suite (tests déterministes)."""

    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


@pytest.fixture
def mlflow_on(monkeypatch):
    monkeypatch.setattr(config, "MLFLOW_ENABLED", True)
    monkeypatch.setattr(tracking, "_executor", SyncExecutor())
    from mlflow.tracking import MlflowClient

    tracking._clients.clear()
    yield MlflowClient(tracking_uri=config.MLFLOW_TRACKING_URI)
    # Base MLflow vidée entre les tests
    client = MlflowClient(tracking_uri=config.MLFLOW_TRACKING_URI)
    for name in tracking.EXPERIMENTS:
        experiment = client.get_experiment_by_name(name)
        if experiment:
            for run in client.search_runs([experiment.experiment_id]):
                client.delete_run(run.info.run_id)


def _runs(client, experiment: str):
    exp = client.get_experiment_by_name(experiment)
    return client.search_runs([exp.experiment_id]) if exp else []


# ---------------------------------------------------------------------------
# Collecteur
# ---------------------------------------------------------------------------

def test_collecteur_inactif_sans_stats():
    record("appels_llm")  # aucun collecteur actif : aucun effet, aucune erreur
    reject("validation", "qcm")
    with collecting(None) as stats:
        record("appels_llm")
    assert stats is None


def test_collecteur_compte_et_mesure_la_duree():
    stats = GenerationStats()
    with collecting(stats):
        record("appels_llm")
        record("appels_llm")
        reject("validation", "qcm")
        reject("doublon")
    record("appels_llm")  # hors du bloc : ignoré
    assert stats.get("appels_llm") == 2
    assert stats.get("rejets_validation") == 1 and stats.get("rejets_validation_qcm") == 1
    assert stats.get("rejets_doublon") == 1
    assert stats.duration_s is not None and stats.as_metrics()["duree_s"] >= 0


class ScriptedExamLLM:
    """LLM simulé pour un QCM : JSON invalide, question invalide, réponse contredite, doublon, puis valides."""

    def __init__(self):
        self.generation = 0
        self.verification = 0

    def __call__(self, system, prompt, **kwargs):
        from app.phase4_exam.generator import VERIFY_SYSTEM_PROMPT

        if system == VERIFY_SYSTEM_PROMPT:
            self.verification += 1
            return json.dumps({"answers": ["B" if self.verification == 1 else "A"]})
        self.generation += 1
        n = self.generation
        if n == 1:
            return "pas du json"
        question = {"question": f"Quel est le rôle numéro {n} du pooling ?",
                    "choices": ["Réduire la taille", "Ajouter des poids", "Normaliser les entrées", "Mélanger"],
                    "answer": "A", "explanation": "Le pooling réduit la taille des cartes.", "page": 1}
        if n == 2:
            question["question"] = "Le pooling sans point d'interrogation"
        if n == 5:
            question["question"] = "Quel est le rôle numéro 4 du pooling ?"  # même sens que la 4e : doublon
        return json.dumps({"items": [question]})


def _exam_setup(monkeypatch):
    from app.phase4_exam import generator

    monkeypatch.setattr(generator, "chat", ScriptedExamLLM())
    monkeypatch.setattr(generator, "embed_passages", lambda texts: [fake_vector(t) for t in texts])
    real_random = random.Random
    monkeypatch.setattr(generator.random, "Random", lambda: real_random(42))
    _add_chunks()
    return generator


def test_chat_compte_les_appels(monkeypatch):
    from types import SimpleNamespace

    from app.phase1_llm import llm

    reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])
    monkeypatch.setattr(llm.client.chat.completions, "create", lambda **kwargs: reply)
    stats = GenerationStats()
    with collecting(stats):
        llm.chat("système", "question")
        llm.chat("système", "question")
    assert llm.chat("système", "question") == "ok"  # sans collecteur : même réponse
    assert stats.get("appels_llm") == 2


def test_examen_compteurs(monkeypatch):
    generator = _exam_setup(monkeypatch)
    # Le LLM étant simulé, on compte ses appels comme le fait phase1_llm.chat
    scripted = generator.chat

    def counted(*args, **kwargs):
        record("appels_llm")
        return scripted(*args, **kwargs)

    monkeypatch.setattr(generator, "chat", counted)
    stats = GenerationStats()
    exam = generator.generate_exam("CNN", "qcm", 5, "facile", user_id=1, stats=stats)

    assert exam.question_count == 5
    assert stats.get("demandees_qcm") == 5
    assert stats.get("rejets_validation") == 2 and stats.get("rejets_validation_qcm") == 2
    assert stats.get("rejets_verification_qcm") == 1
    assert stats.get("rejets_doublon_qcm") == 1
    assert stats.get("appels_generation") == 9  # 5 questions + 4 rejets
    assert stats.get("appels_llm") == 9 + 7  # + une vérification par question valide
    assert stats.values["passages"] == 6

    params, metrics, tags = tracking.exam_run(stats, course="CNN", fmt="qcm", difficulty="facile",
                                              num_questions=5, exam=exam)
    assert metrics["questions_generees"] == 5 and metrics["taux_reussite"] == 1.0
    assert metrics["generees_qcm"] == 5 and metrics["total_points"] == 20
    assert metrics["taux_rejet_validation"] == round(2 / 9, 4)
    assert params["passages"] == 6 and params["format"] == "qcm" and tags["statut"] == "ok"


def test_examen_identique_sans_collecteur(monkeypatch):
    generator = _exam_setup(monkeypatch)
    without = generator.generate_exam("CNN", "qcm", 5, "facile", user_id=1)
    monkeypatch.setattr(generator, "chat", ScriptedExamLLM())  # même script, rejoué depuis le début
    with_stats = generator.generate_exam("CNN", "qcm", 5, "facile", user_id=1, stats=GenerationStats())
    assert without.model_dump() == with_stats.model_dump()


class ScriptedFlashcardLLM:
    """Concepts Pooling / Convolution / Filtre ; carte invalide, doublon et carte jugée fausse."""

    def __init__(self):
        self.cards = 0

    def __call__(self, system, prompt, **kwargs):
        from app.phase7_flashcards.generator import VERIFY_SYSTEM_PROMPT

        if system == VERIFY_SYSTEM_PROMPT:
            return json.dumps({"answers": ["filtre" in prompt.lower()]})  # « true » = erreur détectée
        if "notions clés" in prompt:
            return json.dumps({"items": [{"name": "Pooling", "importance": 3}, {"name": "Convolution", "importance": 2},
                                         {"name": "Filtre", "importance": 1}]})
        self.cards += 1
        if self.cards == 1:
            return "pas du json"
        concept = prompt.split("notion « ")[1].split(" »")[0]
        front, back = "Quel est le rôle du pooling ?", "Il réduit la taille des cartes d'activation."
        if concept == "Filtre":
            front, back = "Qu'est-ce qu'un filtre ?", "Une petite matrice de poids appliquée à l'image."
        return json.dumps({"items": [{"concept": concept, "front": front, "back": back, "page": 1}]})


def _flashcards_setup(monkeypatch):
    from app.phase7_flashcards import generator

    monkeypatch.setattr(generator, "chat", ScriptedFlashcardLLM())
    monkeypatch.setattr(generator, "embed_passages", lambda texts: [fake_vector(t) for t in texts])
    monkeypatch.setattr(generator, "embed_query", fake_vector)
    _add_chunks()
    return generator


def test_flashcards_compteurs(monkeypatch):
    generator = _flashcards_setup(monkeypatch)
    stats = GenerationStats()
    deck = generator.generate_flashcards("CNN", 10, user_id=1, stats=stats)

    assert len(deck.cards) == 1  # Pooling ; Convolution = doublon de sens ; Filtre = jugée fausse
    assert stats.values["concepts_retenus"] == 3
    assert stats.values["concepts_trouves"] == 6  # 2 blocs de 3 passages, 3 concepts chacun
    assert stats.get("rejets_validation") == 1
    assert stats.get("rejets_doublon") == 1
    assert stats.get("rejets_verification") == 2  # deux tentatives pour Filtre
    assert stats.get("appels_generation") == 5

    params, metrics, _ = tracking.flashcards_run(stats, course="CNN", count=10, deck=deck)
    assert metrics["cartes_generees"] == 1 and metrics["taux_reussite"] == 0.1
    assert metrics["taux_rejet_verification"] == 0.4 and params["cartes_demandees"] == 10


def test_flashcards_identiques_sans_collecteur(monkeypatch):
    generator = _flashcards_setup(monkeypatch)
    without = generator.generate_flashcards("CNN", 10, user_id=1)
    monkeypatch.setattr(generator, "chat", ScriptedFlashcardLLM())
    assert generator.generate_flashcards("CNN", 10, user_id=1, stats=GenerationStats()) == without


def test_tuteur_mesures(client, llm):
    from app.phase3_rag.rag import answer

    headers = register(client)
    upload(client, headers, "CNN")
    stats = GenerationStats()
    result = answer("Qu'est-ce que le pooling ?", "CNN", user_id=1, stats=stats)
    assert stats.values["reponse_trouvee"] == 1 and stats.values["sources"] == len(result["sources"])
    assert stats.values["passages_retrouves"] >= 1 and 0 < stats.values["score_max"] <= 1
    assert result == answer("Qu'est-ce que le pooling ?", "CNN", user_id=1)  # identique sans collecteur

    llm.reply = "Cette information n'est pas présente dans le cours."
    stats = GenerationStats()
    answer("Capitale de la France ?", "CNN", user_id=1, stats=stats)
    assert stats.values["reponse_trouvee"] == 0 and stats.values["sources"] == 0


# ---------------------------------------------------------------------------
# log_run : jamais d'exception
# ---------------------------------------------------------------------------

def test_log_run_desactive():
    assert config.MLFLOW_ENABLED is False
    assert tracking.log_run("exam", {"format": "qcm"}, {"duree_s": 1.0}) is None
    assert tracking.log_run_async("exam", {}, {}) is None


def test_log_run_mlflow_indisponible(monkeypatch, caplog):
    monkeypatch.setattr(config, "MLFLOW_ENABLED", True)

    def broken():
        raise ConnectionError("serveur MLflow injoignable")

    monkeypatch.setattr(tracking, "_client", broken)
    assert tracking.log_run("exam", {"format": "qcm"}, {"duree_s": 1.0}) is None
    assert "MLflow indisponible" in caplog.text
    assert tracking.summarize()["mlflow"] is False


def test_log_run_enregistre(mlflow_on):
    run_id = tracking.log_run("exam", {"format": "qcm", "vide": None},
                              {"duree_s": 2.5, "nan": float("nan"), "texte": "ignoré"}, {"source": "test"})
    assert run_id
    run = mlflow_on.get_run(run_id)
    assert run.data.params == {"format": "qcm"}
    assert run.data.metrics == {"duree_s": 2.5}
    assert run.data.tags["source"] == "test"


# ---------------------------------------------------------------------------
# Routes : runs enregistrés sans données personnelles, /api/stats
# ---------------------------------------------------------------------------

def test_runs_des_routes_sans_donnees_personnelles(client, llm, monkeypatch, mlflow_on):
    from app.phase4_exam import routes as exam_routes

    monkeypatch.setattr(exam_routes, "generate_exam", lambda course, *a, **k: sample_exam(course))
    email, question = "ali.najjaa@example.com", "Explique le pooling à Ali Najjaa stp"
    headers = register(client, email, level="debutant")
    upload(client, headers, "CNN")
    client.post("/api/courses/CNN/exam", json={"format": "qcm", "num_questions": 5}, headers=headers)
    conv = client.post("/api/conversations", json={}, headers=headers).json()["id"]
    client.post(f"/api/conversations/{conv}/messages", json={"question": question, "course": "CNN"}, headers=headers)
    client.post("/api/ask", json={"question": question}, headers=headers)

    exam_runs, tutor_runs = _runs(mlflow_on, "exam"), _runs(mlflow_on, "tutor")
    assert len(exam_runs) == 1 and len(tutor_runs) == 2
    assert exam_runs[0].data.params["cours"] == "CNN"
    assert tutor_runs[0].data.params["niveau"] == "debutant"
    assert tutor_runs[0].data.metrics["reponse_trouvee"] == 1
    for run in exam_runs + tutor_runs:
        dump = json.dumps([run.data.params, run.data.tags, run.data.metrics]).lower()
        for secret in ("ali.najjaa", "najjaa", "example.com", "explique", "pooling à"):
            assert secret not in dump


def test_echec_de_generation_enregistre(client, monkeypatch, mlflow_on):
    from app.phase7_flashcards import routes

    def failing(*args, **kwargs):
        raise ValueError("Aucun concept n'a pu être extrait de ce cours. Réessaie.")

    monkeypatch.setattr(routes, "generate_flashcards", failing)
    headers = register(client)
    upload(client, headers, "CNN")
    assert client.post("/api/courses/CNN/flashcards", json={"count": 10}, headers=headers).status_code == 422
    run = _runs(mlflow_on, "flashcards")[0]
    assert run.data.tags["statut"] == "echec" and run.data.tags["erreur"] == "ValueError"
    assert run.data.metrics["taux_reussite"] == 0


def test_api_stats(client, mlflow_on):
    assert client.get("/api/stats").status_code == 401
    headers = register(client)
    tracking.log_run("exam", {}, {"duree_s": 100, "taux_reussite": 1.0, "taux_rejet_validation": 0.2})
    tracking.log_run("exam", {}, {"duree_s": 200, "taux_reussite": 0.5, "taux_rejet_validation": 0.4})
    tracking.log_run("tutor", {}, {"duree_s": 4, "reponse_trouvee": 1})

    body = client.get("/api/stats", headers=headers).json()
    assert body["mlflow"] is True and body["portee"] == "globale"
    exam = body["experiences"]["exam"]
    assert exam["runs"] == 2 and exam["duree_moyenne_s"] == 150
    assert exam["taux_reussite_moyen"] == 0.75
    assert exam["taux_rejet_moyens"]["validation"] == pytest.approx(0.3)
    assert body["experiences"]["tutor"]["taux_reussite_moyen"] == 1
    assert body["experiences"]["flashcards"]["runs"] == 0


def test_api_stats_mlflow_desactive(client):
    body = client.get("/api/stats", headers=register(client)).json()
    assert body["mlflow"] is False
    assert body["experiences"]["exam"]["runs"] == 0


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

def test_jeu_de_questions_chapter1():
    from app.phase5_evaluation.benchmark import load_dataset

    dataset = load_dataset("Chapter1_Part_1")
    assert len({d["question"] for d in dataset}) == len(dataset) >= 10
    assert all(d["expected_page"] is None or isinstance(d["expected_page"], int) for d in dataset)
    assert any(d["expected_page"] is None for d in dataset)  # questions hors cours


def test_resume_moyenne_ecart_type():
    from app.phase5_evaluation.benchmark import summary_rows

    rows = summary_rows({"exam": [{"duree_s": 100, "taux_reussite": 1}, {"duree_s": 200, "taux_reussite": 0.5}]})
    duree = next(r for r in rows if r["metrique"] == "duree_s")
    assert duree == {"experience": "exam", "metrique": "duree_s", "moyenne": 150, "ecart_type": 70.7107, "n": 2}


def test_benchmark_tuteur_de_bout_en_bout(client, llm, monkeypatch, tmp_path, capsys, mlflow_on):
    from app.phase5_evaluation import benchmark

    monkeypatch.setattr(benchmark, "embed_query", fake_vector)
    monkeypatch.setattr(benchmark, "DATASETS", tmp_path)
    monkeypatch.setattr(benchmark, "RESULTS", tmp_path / "results")
    (tmp_path / "CNN.json").write_text(json.dumps([
        {"question": "Qu'est-ce que le pooling ?", "expected_page": 1},
        {"question": "Que fait la convolution ?", "expected_page": 9},
        {"question": "Comment installer Docker sur Windows ?", "expected_page": None},
        {"question": "Qui a gagné la Coupe du monde 2022 ?", "expected_page": None},
    ]), encoding="utf-8")
    headers = register(client, "ali@example.com")
    upload(client, headers, "CNN")

    assert benchmark.main(["ali@example.com", "CNN", "--skip-exam", "--skip-flashcards", "--skip-summary"]) == 0
    out = capsys.readouterr().out
    assert "[tuteur 1/4]" in out and "hit_3" in out and "hors cours" in out
    csv_files = list((tmp_path / "results").glob("CNN_*.csv"))
    assert len(csv_files) == 1
    content = csv_files[0].read_text(encoding="utf-8")
    assert "tutor,hit_3,0.5,0.7071,2" in content  # page 1 trouvée, page 9 absente ; hors cours non comptées
    assert "tutor,refus_correct,0.0,0.0,2" in content  # le LLM simulé répond toujours (aucun refus)
    assert "tutor,reponse_trouvee,1.0,0.0,2" in content  # seulement les 2 questions du cours
    runs = _runs(mlflow_on, "tutor")
    assert len(runs) == 4 and all(r.data.tags["source"] == "benchmark" for r in runs)
    assert all("pooling" not in json.dumps(r.data.params).lower() for r in runs)


def test_benchmark_compte_ou_cours_inconnu(client, capsys):
    from app.phase5_evaluation import benchmark

    assert benchmark.main(["personne@example.com", "CNN"]) == 1
    register(client, "ali@example.com")
    assert benchmark.main(["ali@example.com", "CNN"]) == 1
    assert "n'appartient pas à ce compte" in capsys.readouterr().out


def test_benchmark_refus_correct_hors_cours(client, llm, monkeypatch, tmp_path, capsys):
    from app.phase5_evaluation import benchmark

    monkeypatch.setattr(benchmark, "embed_query", fake_vector)
    monkeypatch.setattr(benchmark, "DATASETS", tmp_path)
    monkeypatch.setattr(benchmark, "RESULTS", tmp_path / "results")
    (tmp_path / "CNN.json").write_text(json.dumps([
        {"question": "Comment installer Docker sur Windows ?", "expected_page": None},
    ]), encoding="utf-8")
    llm.reply = "Cette information n'est pas présente dans le cours."
    headers = register(client, "ali@example.com")
    upload(client, headers, "CNN")

    assert benchmark.main(["ali@example.com", "CNN", "--skip-exam", "--skip-flashcards", "--skip-summary"]) == 0
    assert "refus correct" in capsys.readouterr().out
    content = next((tmp_path / "results").glob("CNN_*.csv")).read_text(encoding="utf-8")
    assert "tutor,refus_correct,1.0,0.0,1" in content
    assert "hit_3" not in content and "reponse_trouvee" not in content
