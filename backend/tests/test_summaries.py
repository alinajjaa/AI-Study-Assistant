import json
import re

import pytest
from pydantic import ValidationError
from qdrant_client.models import PointStruct

from app.phase2_embeddings import vectorstore
from app.phase3_rag.rag import LEVEL_INSTRUCTIONS
from app.phase5_evaluation.stats import GenerationStats
from app.phase5_evaluation.tracking import summary_run
from app.phase9_summaries.schemas import SectionDraft
from tests.helpers import fake_vector, register

TEXT = ("Le pooling réduit la taille des cartes d'activation produites par les couches de convolution "
        "et garde l'information la plus importante du passage étudié.")
OVERVIEW = ("Ce cours présente les réseaux de neurones convolutifs. Il explique le rôle de la convolution. "
            "Il décrit ensuite le pooling et la réduction de taille. Il montre comment ces couches s'enchaînent. "
            "Il termine par les usages en vision.")


def _add_chunks(n: int, user_id: int = 1, course: str = "CNN") -> None:
    vectorstore.client.upsert("courses", points=[
        PointStruct(id=i + 500, vector=fake_vector(f"c{i}"),
                    payload={"course": course, "page": i + 1, "text": f"{TEXT} ({i})", "user_id": user_id})
        for i in range(n)
    ] + [PointStruct(id=999, vector=fake_vector("titre"),  # trop court : ignoré
                     payload={"course": course, "page": 99, "text": "Titre", "user_id": user_id})])


def _allowed_pages(prompt: str) -> list[int]:
    return [int(n) for n in re.search(r"avec X parmi : ([\d, ]+)", prompt).group(1).split(",")]


class ScriptedSummaryLLM:
    """Répond selon le type de demande ; `bad_sections` sorties invalides avant les bonnes."""

    def __init__(self, bad_sections: list[dict] | None = None, overview: str = OVERVIEW, topic_found: bool = True):
        self.bad_sections = list(bad_sections or [])
        self.overview = overview
        self.topic_found = topic_found
        self.prompts: list[str] = []

    def __call__(self, system, prompt, **kwargs):
        self.prompts.append(prompt)
        if "Rédige une vue d'ensemble" in prompt:
            return json.dumps({"overview": self.overview})
        pages = _allowed_pages(prompt)
        bullets = [f"Le pooling réduit la taille des cartes, idée numéro {i} [p.{pages[0]}]" for i in range(3)]
        if "Thème demandé" in prompt:
            if not self.topic_found:
                return json.dumps({"found": False})
            return json.dumps({"found": True, "introduction": "Le pooling simplifie les cartes d'activation.",
                               "parts": [{"title": "Rôle du pooling", "bullets": bullets[:2]}]})
        if self.bad_sections:
            return json.dumps(self.bad_sections.pop(0))
        return json.dumps({"title": f"Partie sur les pages {pages[0]} à {pages[-1]}", "bullets": bullets})


@pytest.fixture
def summary_llm(monkeypatch):
    from app.phase9_summaries import generator

    monkeypatch.setattr(generator, "embed_query", fake_vector)

    def install(llm: ScriptedSummaryLLM) -> ScriptedSummaryLLM:
        monkeypatch.setattr(generator, "chat", llm)
        return llm

    return install


def _summary(client, headers, **body):
    return client.post("/api/courses/CNN/summary", json=body, headers=headers)


def _setup(client, n=13):
    headers = register(client)
    from app.phase8_personal.courses import add_course
    from app.core.db import engine
    from sqlmodel import Session

    with Session(engine) as s:
        add_course(s, 1, "CNN")
    _add_chunks(n)
    return headers


# ---------------------------------------------------------------------------
# Validation des puces
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bullet, error", [
    ("   [p.2]", "puce vide"),
    ("The pooling layer reduces the size of the feature maps [p.2]", "texte en anglais"),
    ("Le pooling réduit la taille des cartes d'activation", "puce sans référence de page"),
    ("Le pooling réduit la taille des cartes d'activation [p.42]", "page absente des passages fournis"),
])
def test_puce_refusee(bullet, error):
    ok = "Le pooling réduit la taille des cartes d'activation [p.2]"
    with pytest.raises(ValidationError, match=error):
        SectionDraft.model_validate({"title": "Le pooling", "bullets": [bullet, ok, ok]}, context={"pages": {2, 3}})


def test_puce_nettoyee_des_restes_de_json():
    draft = SectionDraft.model_validate(
        {"title": "Le pooling", "bullets": ["Le pooling réduit la taille des cartes [p.2]}"] * 3},
        context={"pages": {2}})
    assert draft.bullets[0] == "Le pooling réduit la taille des cartes [p.2]"


def test_puce_valide_avec_plusieurs_pages():
    draft = SectionDraft.model_validate(
        {"title": "le pooling", "bullets": ["Le pooling réduit la taille des cartes [p.2, 3]"] * 3},
        context={"pages": {2, 3}})
    assert draft.title == "Le pooling"


# ---------------------------------------------------------------------------
# Cours entier (map-reduce), cache, regenerate
# ---------------------------------------------------------------------------

def test_resume_du_cours_entier_et_cache(client, summary_llm):
    llm = summary_llm(ScriptedSummaryLLM())
    headers = _setup(client)
    res = _summary(client, headers, mode="course")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["cached"] is False and body["mode"] == "course"
    sections = body["content"]["sections"]
    assert len(sections) == 3  # 13 passages utiles par groupes de 6 ; le titre court est ignoré
    assert sections[0]["pages"] == [1] and len(sections[0]["bullets"]) == 3
    assert body["content"]["overview"] == OVERVIEW
    assert all("[page 99]" not in p for p in llm.prompts)
    calls = len(llm.prompts)
    assert calls == 4  # 3 sections + vue d'ensemble
    # Les titres déjà utilisés sont donnés au LLM pour éviter des sections au même titre
    assert "Partie sur les pages 1 à 6" in llm.prompts[1] and "Partie sur les pages 1 à 6" not in llm.prompts[0]

    again = _summary(client, headers, mode="course").json()
    assert again["cached"] is True and again["id"] == body["id"]
    assert len(llm.prompts) == calls  # aucun appel au LLM

    fresh = _summary(client, headers, mode="course", regenerate=True).json()
    assert fresh["cached"] is False and len(llm.prompts) == 2 * calls  # vraiment regénéré
    listing = client.get("/api/summaries", headers=headers).json()
    assert [s["id"] for s in listing] == [fresh["id"]]  # l'ancien résumé du cours est remplacé
    assert listing[0]["section_count"] == 3


def test_reessai_puis_section_ignoree(client, summary_llm):
    from app.phase9_summaries.generator import generate_summary

    bad = {"title": "Pooling", "bullets": ["The pooling layer is used [p.1]"] * 3}
    summary_llm(ScriptedSummaryLLM(bad_sections=[bad, bad, bad]))  # section 1 : 2 rejets ; section 2 : 1 rejet
    _setup(client)
    stats = GenerationStats()
    content = generate_summary("CNN", "course", user_id=1, stats=stats)
    assert len(content.sections) == 2
    assert stats.get("rejets_validation") == 3
    # Section 1 : 2 × 3 puces en anglais mais page valide ; section 2 : 3 puces citant p.1 (absente) puis 3 bonnes
    assert stats.get("puces_proposees") == 15 and stats.get("puces_page_valide") == 12
    assert stats.values["sections"] == 2 and stats.values["puces"] == 6

    params, metrics, tags = summary_run(stats, course="CNN", mode="course", content=content)
    assert metrics["reussi"] == 1 and metrics["taux_puces_page_valide"] == 0.8  # 12 / 15
    assert params["mode"] == "course" and tags["statut"] == "ok"


def test_aucune_section_valide_422(client, summary_llm):
    bad = {"title": "Pooling", "bullets": ["Sans aucune page citée dans cette puce"] * 3}
    summary_llm(ScriptedSummaryLLM(bad_sections=[bad] * 6))
    headers = _setup(client)
    res = _summary(client, headers, mode="course")
    assert res.status_code == 422
    assert client.get("/api/summaries", headers=headers).json() == []


def test_vue_d_ensemble_de_secours(client, summary_llm):
    summary_llm(ScriptedSummaryLLM(overview="Trop court."))
    headers = _setup(client)
    overview = _summary(client, headers, mode="course").json()["content"]["overview"]
    assert overview.startswith("Ce cours aborde les parties suivantes : Partie sur les pages 1 à 6")


def test_erreur_llm_503(client, monkeypatch):
    from app.phase1_llm.llm import LLMError
    from app.phase9_summaries import generator

    def broken(*args, **kwargs):
        raise LLMError("Impossible de joindre le serveur du LLM. Vérifie qu'Ollama est lancé.")

    monkeypatch.setattr(generator, "chat", broken)
    headers = _setup(client)
    res = _summary(client, headers, mode="course")
    assert res.status_code == 503 and "Ollama" in res.json()["detail"]


def test_reimport_invalide_le_cache(client, summary_llm):
    from tests.helpers import upload

    summary_llm(ScriptedSummaryLLM())
    headers = _setup(client)
    _summary(client, headers, mode="course")
    upload(client, headers, "CNN")
    assert client.get("/api/summaries", headers=headers).json() == []


# ---------------------------------------------------------------------------
# Thème
# ---------------------------------------------------------------------------

def test_theme_adapte_au_niveau_et_masque(client, summary_llm):
    llm = summary_llm(ScriptedSummaryLLM())
    headers = register(client, level="debutant")
    from app.phase8_personal.courses import add_course
    from app.core.db import engine
    from sqlmodel import Session

    with Session(engine) as s:
        add_course(s, 1, "CNN")
    _add_chunks(10)
    res = _summary(client, headers, mode="topic", topic="  Explique-moi le pooling, écris à ali@example.com ")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["topic"] == "Explique-moi le pooling, écris à ali@example.com"
    assert body["content"]["found"] is True
    assert body["content"]["sections"][0]["title"] == "Rôle du pooling"
    prompt = llm.prompts[-1]
    assert LEVEL_INSTRUCTIONS["debutant"] in prompt
    assert "ali@example.com" not in prompt and "[EMAIL]" in prompt
    assert prompt.count("[page ") == 6  # les 6 meilleurs passages

    # Un thème n'est jamais réutilisé depuis le cache : chaque demande est enregistrée
    _summary(client, headers, mode="topic", topic="la convolution")
    assert len(client.get("/api/summaries?course=CNN", headers=headers).json()) == 2


def test_theme_absent_du_cours(client, summary_llm):
    summary_llm(ScriptedSummaryLLM(topic_found=False))
    headers = _setup(client)
    body = _summary(client, headers, mode="topic", topic="Docker sur Windows").json()
    assert body["content"]["found"] is False and body["content"]["sections"] == []
    assert "n'est pas abordé dans le cours « CNN »" in body["content"]["overview"]


def test_theme_obligatoire(client):
    headers = _setup(client)
    res = _summary(client, headers, mode="topic", topic=" ")
    assert res.status_code == 422
    assert res.json()["detail"][0]["msg"] == "Indique le thème à expliquer."


def test_mlflow_sans_texte_du_theme():
    params, metrics, _ = summary_run(GenerationStats(), course="CNN", mode="topic", level="avance")
    assert "Docker" not in json.dumps(params) and "topic" not in params and params["niveau"] == "avance"
    assert metrics["reussi"] == 0


# ---------------------------------------------------------------------------
# Routes protégées et isolation
# ---------------------------------------------------------------------------

def test_isolation_et_suppression(client, summary_llm):
    summary_llm(ScriptedSummaryLLM())
    alice = _setup(client)
    summary_id = _summary(client, alice, mode="course").json()["id"]
    bob = register(client, "bob@example.com")

    assert client.post("/api/courses/CNN/summary", json={"mode": "course"}).status_code == 401
    assert _summary(client, bob, mode="course").status_code == 404
    assert client.get("/api/summaries", headers=bob).json() == []
    assert client.get(f"/api/summaries/{summary_id}", headers=bob).status_code == 404
    assert client.delete(f"/api/summaries/{summary_id}", headers=bob).status_code == 404

    assert client.get(f"/api/summaries/{summary_id}", headers=alice).json()["content"]["sections"]
    assert client.delete(f"/api/summaries/{summary_id}", headers=alice).status_code == 200
    assert client.get("/api/summaries", headers=alice).json() == []


def test_benchmark_resume(client, summary_llm, tmp_path, monkeypatch, capsys):
    from app.phase5_evaluation import benchmark

    summary_llm(ScriptedSummaryLLM())
    monkeypatch.setattr(benchmark, "RESULTS", tmp_path)
    _setup(client)
    assert benchmark.main(["etudiant@example.com", "CNN", "--skip-exam", "--skip-flashcards", "--skip-tutor"]) == 0
    assert "[résumé 1/1] 3 sections" in capsys.readouterr().out
    content = next(tmp_path.glob("CNN_*.csv")).read_text(encoding="utf-8")
    assert "summary,sections,3.0" in content and "summary,taux_puces_page_valide,1.0" in content
