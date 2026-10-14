"""Study Companion : agent LangGraph (LLM simulé), routage, repli, quiz, tâches de fond, migration, MLflow."""
import json
import threading
import time

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field
from sqlalchemy import text
from sqlmodel import select

from app.core import config
from app.core.db import engine, migrate_messages
from app.phase1_llm.llm import LLMError
from app.phase5_evaluation import tracking
from app.phase6_agent import graph, routes, tools
from app.phase6_agent.graph import MAX_TOOL_CALLS, run_agent
from app.phase6_agent.models import QuizResult
from app.phase6_agent.tools import AgentContext, match_course
from app.phase6_agent.tracing import REDACTED, redact
from app.phase8_personal.courses import add_course
from app.phase8_personal.models import Message, User
from tests.helpers import register, sample_deck, upload


# ---------------------------------------------------------------------------
# LLM simulés
# ---------------------------------------------------------------------------

class ScriptedChatModel(BaseChatModel):
    """Modèle de chat LangChain simulé : renvoie les messages du script dans l'ordre et garde les prompts."""

    model_config = {"arbitrary_types_allowed": True}

    script: list = Field(default_factory=list)
    prompts: list = Field(default_factory=list)
    tools: list = Field(default_factory=list)
    error: Exception | None = None  # le modèle ne répond plus (LLM injoignable)

    def bind_tools(self, tools, **kwargs):
        self.tools = tools
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append(messages)
        if self.error is not None:
            raise self.error
        reply = self.script.pop(0) if self.script else AIMessage("C'est prêt !")
        return ChatResult(generations=[ChatGeneration(message=reply)])

    @property
    def _llm_type(self) -> str:
        return "scripted"


def call(name: str, i: int = 0, **args) -> dict:
    return {"name": name, "args": args, "id": f"call_{name}_{i}", "type": "tool_call"}


def tool_message(*calls: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=list(calls))


class FakeClassifier:
    """Remplace chat() dans graph (classification d'intention) et dans tools (notions du quiz)."""

    def __init__(self, decision: dict | None = None):
        self.decision = decision or {"outil": "aucun"}
        self.prompts: list[str] = []

    def __call__(self, system, prompt, **kwargs):
        self.prompts.append(prompt)
        if "Demande de l'étudiant" in prompt:
            return json.dumps(self.decision)
        n = len([line for line in prompt.splitlines() if line[:1].isdigit()])
        return json.dumps({"concepts": [f"Notion {i}" for i in range(1, n + 1)]})


def sample_qcm(course, fmt="qcm", num_questions=5, difficulty="moyen", user_id=None, stats=None):
    from app.phase4_exam.schemas import Exam, ExamSection, MCQQuestion

    questions = [
        MCQQuestion(question="Quel est le rôle du pooling ?",
                    choices=["Réduire la taille", "Ajouter des poids", "Normaliser", "Mélanger"],
                    answer="A", explanation="Le pooling réduit la taille des cartes.", page=1),
        MCQQuestion(question="Que produit une couche de convolution ?",
                    choices=["Un score final", "Des cartes d'activation", "Une perte", "Un gradient"],
                    answer="B", explanation="La convolution produit des cartes d'activation.", page=2),
    ]
    return Exam(course=course, difficulty=difficulty, format="qcm", expected_questions=num_questions, sections=[
        ExamSection(letter="A", title="QCM", instructions="Une seule bonne réponse.", points_per_question=10,
                    questions=questions)])


@pytest.fixture
def agent_env(monkeypatch, llm):
    """Modèle LangChain simulé, classification simulée, générateurs longs remplacés par des versions instantanées."""
    model = ScriptedChatModel()
    classifier = FakeClassifier()
    calls = {"exam": 0, "deck": 0}

    def exam(*args, **kwargs):
        calls["exam"] += 1
        return sample_qcm(*args, **kwargs)

    def deck(course, count, user_id=None, stats=None):
        calls["deck"] += 1
        return sample_deck(course)

    monkeypatch.setattr(graph, "default_llm", lambda: model)
    monkeypatch.setattr(graph, "chat", classifier)
    monkeypatch.setattr(tools, "chat", classifier)
    monkeypatch.setattr(tools, "generate_exam", exam)
    monkeypatch.setattr(tools, "generate_deck", deck)
    return model, classifier, calls


def make_ctx(session, courses=("CNN",), selected="CNN", message="Bonjour", history=None, level="intermediaire"):
    user = User(email="etudiant@example.com", password_hash="x", level=level)
    session.add(user)
    session.commit()
    session.refresh(user)
    for course in courses:
        add_course(session, user.id, course)
    return AgentContext(session=session, user=user, courses=list(courses), selected_course=selected,
                        history=history or [], message=message)


# ---------------------------------------------------------------------------
# Agent : routage, repli, limites
# ---------------------------------------------------------------------------

def test_salutation_reponse_directe_sans_outil(session, agent_env):
    model, classifier, calls = agent_env
    model.script = [AIMessage("Bonjour ! Que veux-tu réviser aujourd'hui ?")]
    result = run_agent(make_ctx(session, message="Bonjour !"), llm=model)
    assert result.tools == [] and result.fallback is True  # aucun outil appelé → classification
    assert [(r.kind, r.content) for r in result.replies] == [("text", "Bonjour ! Que veux-tu réviser aujourd'hui ?")]
    assert calls == {"exam": 0, "deck": 0}


def test_ask_course_reponse_rag_avec_sources(client, session, agent_env, llm):
    model, _, _ = agent_env
    headers = register(client)
    upload(client, headers, "CNN")
    user = session.exec(select(User)).one()
    model.script = [tool_message(call("ask_course", question="Quel est le rôle du pooling ?"))]
    ctx = AgentContext(session=session, user=user, courses=["CNN"], selected_course="CNN",
                       message="C'est quoi le pooling ?")
    result = run_agent(ctx, llm=model)
    assert result.tools == ["ask_course"] and result.fallback is False
    reply = result.replies[0]
    assert reply.kind == "answer" and reply.content == llm.reply and reply.sources[0]["page"] == 1
    assert len(model.prompts) == 1  # la réponse du tuteur n'est pas reformulée par un 2e appel
    assert "Quel est le rôle du pooling ?" in llm.calls[0][1]


def test_quiz_puis_reponse_finale_courte(session, agent_env):
    model, classifier, calls = agent_env
    model.script = [tool_message(call("generate_quiz", count=5, difficulty="facile")),
                    AIMessage("Voici ton quiz, bonne chance !")]
    result = run_agent(make_ctx(session, message="Fais-moi un quiz facile"), llm=model)
    assert result.tools == ["generate_quiz"] and calls["exam"] == 1
    reply = result.replies[0]
    assert reply.kind == "quiz" and reply.content == "Voici ton quiz, bonne chance !"
    assert reply.payload["course"] == "CNN" and reply.payload["difficulty"] == "facile"
    assert [q["answer"] for q in reply.payload["questions"]] == ["A", "B"]
    assert [q["concept"] for q in reply.payload["questions"]] == ["Notion 1", "Notion 2"]
    assert reply.payload["result"] is None
    # 2e passage : le LLM reçoit le compte rendu de l'outil et la consigne de réponse courte
    assert "Écris maintenant ta réponse finale" in model.prompts[1][0].content
    assert "Quiz de 2 questions" in model.prompts[1][-1].content


def test_outil_invalide_repli_par_classification(session, agent_env):
    model, classifier, calls = agent_env
    classifier.decision = {"outil": "generate_flashcards", "cours": None, "nombre": 10}
    model.script = [tool_message(call("make_cards", topic="CNN")), AIMessage("Ton paquet est prêt.")]
    result = run_agent(make_ctx(session, message="Des cartes pour réviser stp"), llm=model)
    assert result.fallback is True and result.tools == ["generate_flashcards"]
    assert result.replies[0].kind == "flashcards" and result.replies[0].payload["card_count"] == 2
    assert calls["deck"] == 1
    # L'appel invalide est retiré de la conversation envoyée au LLM au 2e passage
    second = model.prompts[1]
    assert not any(getattr(m, "tool_calls", None) and m.tool_calls[0]["name"] == "make_cards" for m in second)


def test_aucun_appel_repli_choisit_un_outil(session, agent_env):
    model, classifier, _ = agent_env
    classifier.decision = {"outil": "get_progress"}
    model.script = [AIMessage("Je vais regarder."), AIMessage("Tu progresses bien !")]
    result = run_agent(make_ctx(session, message="Où j'en suis ?"), llm=model)
    assert result.fallback is True and result.tools == ["get_progress"]
    reply = result.replies[0]
    assert reply.kind == "progress" and reply.content == "Tu progresses bien !"
    assert reply.payload["level"] == "intermediaire" and "email" not in reply.payload
    assert reply.payload["stats"]["courses"] == 1


def test_maximum_trois_appels_par_message(session, agent_env):
    model, _, calls = agent_env
    model.script = [tool_message(call("generate_quiz", 1, count=5), call("generate_quiz", 2, count=10),
                                 call("generate_flashcards", 3), call("get_progress", 4)),
                    AIMessage("Tout est prêt.")]
    result = run_agent(make_ctx(session), llm=model)
    assert len(result.tools) == MAX_TOOL_CALLS == 3
    assert result.tools == ["generate_quiz", "generate_quiz", "generate_flashcards"]
    assert len(result.replies) == 3 and result.replies[-1].content == "Tout est prêt."


def test_appel_repete_non_reexecute(session, agent_env):
    model, _, calls = agent_env
    same = call("generate_quiz", count=5)
    model.script = [tool_message(same), tool_message({**same, "id": "call_bis"}), AIMessage("Prêt.")]
    result = run_agent(make_ctx(session), llm=model)
    assert calls["exam"] == 1 and result.tools == ["generate_quiz"]


def test_plusieurs_cours_sans_precision_demande_lequel(session, agent_env):
    model, _, calls = agent_env
    model.script = [tool_message(call("generate_quiz"))]
    result = run_agent(make_ctx(session, courses=("CNN", "Docker"), selected=None), llm=model)
    reply = result.replies[0]
    assert reply.kind == "text" and "quel cours" in reply.content.lower()
    assert reply.payload == {"course_choices": ["CNN", "Docker"]}
    assert calls["exam"] == 0 and len(model.prompts) == 1


def test_cours_nomme_par_le_llm_sans_cours_selectionne(session, agent_env):
    model, _, _ = agent_env
    model.script = [tool_message(call("generate_quiz", course="docker")), AIMessage("Prêt.")]
    ctx = make_ctx(session, courses=("CNN", "Docker"), selected=None, message="Un quiz sur Docker stp")
    assert run_agent(ctx, llm=model).replies[0].payload["course"] == "Docker"


def test_bug_a_le_cours_choisi_par_le_llm_ne_remplace_jamais_le_cours_selectionne(session, agent_env):
    model, _, _ = agent_env
    model.script = [tool_message(call("generate_quiz", course="docker")), AIMessage("Prêt.")]
    ctx = make_ctx(session, courses=("CNN", "Docker"), selected="CNN", message="Un quiz sur Docker stp")
    assert run_agent(ctx, llm=model).replies[0].payload["course"] == "CNN"


def _fake_answer(monkeypatch, text="Le pooling réduit la taille [p.1].", answered=True):
    """Remplace le tuteur RAG appelé par ask_course ; garde le cours interrogé."""
    asked = []

    def answer(question, course, **kwargs):
        asked.append(course)
        sources = [{"course": course or "CNN", "page": 1, "score": 0.9, "excerpt": "…"}] if answered else []
        return {"answer": text, "sources": sources, "answered": answered}

    monkeypatch.setattr(tools, "answer", answer)
    return asked


def test_bug_a_ask_course_interroge_le_cours_selectionne(session, agent_env, monkeypatch):
    model, _, _ = agent_env
    asked = _fake_answer(monkeypatch)
    model.script = [tool_message(call("ask_course", course="Docker"))]
    ctx = make_ctx(session, courses=("CNN", "Docker"), selected="CNN", message="Le pooling dans Docker ?")
    reply = run_agent(ctx, llm=model).replies[0]
    assert asked == ["CNN"] and reply.payload == {"course": "CNN"}


def test_bug_c_hors_du_cours_seule_la_phrase_not_found_est_gardee(session, agent_env, monkeypatch):
    from app.phase3_rag.rag import NOT_FOUND

    model, _, _ = agent_env
    _fake_answer(monkeypatch, text=f"{NOT_FOUND} Mais en général, Kubernetes orchestre des conteneurs.",
                 answered=False)
    model.script = [tool_message(call("ask_course"))]
    reply = run_agent(make_ctx(session, message="C'est quoi Kubernetes ?"), llm=model).replies[0]
    assert reply.kind == "answer" and reply.answered is False
    assert reply.content == NOT_FOUND and reply.sources == []


@pytest.mark.parametrize("message", [
    "Résume les idées principales de ce cours.",
    "Quelles sont les idées principales du cours ?",
    "Donne-moi les points clés de ce cours",
    "Résume l'essentiel de ce chapitre",
    "Fais-moi une synthèse des notions essentielles du cours",
])
def test_bug_b_resume_du_cours_route_vers_summarize(session, agent_env, message):
    """Le modèle choisit ask_course pour une demande de résumé du cours entier : corrigé en summarize."""
    model, _, _ = agent_env
    model.script = [tool_message(call("ask_course", question=message, course="CNN"))]
    result = run_agent(make_ctx(session, message=message), llm=model, dry_run=True)
    assert result.tools == ["summarize"]


def test_bug_b_correction_aussi_apres_le_repli(session, agent_env):
    model, classifier, _ = agent_env
    classifier.decision = {"outil": "ask_course"}
    model.script = [AIMessage("Je ne sais pas.")]
    ctx = make_ctx(session, message="Résume les idées principales de ce cours")
    result = run_agent(ctx, llm=model, dry_run=True)
    assert result.tools == ["summarize"] and result.fallback is True


@pytest.mark.parametrize("message", [
    "Explique l'essentiel du pooling dans ce cours",
    "Résume la notion de pooling",
    "Quels sont les points clés du pooling ?",
    "Résume le chapitre sur le pooling du cours",
])
def test_bug_b_une_vraie_question_reste_sur_ask_course(session, agent_env, message):
    model, _, _ = agent_env
    model.script = [tool_message(call("ask_course", question=message))]
    assert run_agent(make_ctx(session, message=message), llm=model, dry_run=True).tools == ["ask_course"]


def test_cours_invente_par_le_llm_ignore(session, agent_env):
    """Le LLM propose un cours que l'étudiant n'a pas nommé : on demande lequel au lieu de deviner."""
    model, classifier, calls = agent_env
    classifier.decision = {"outil": "generate_quiz", "cours": "CNN"}
    model.script = [AIMessage("Je ne sais pas.")]
    result = run_agent(make_ctx(session, courses=("CNN", "Docker"), selected=None, message="Fais-moi un quiz"),
                       llm=model)
    assert result.replies[0].payload == {"course_choices": ["CNN", "Docker"]} and calls["exam"] == 0


def test_reponse_finale_courte_sans_liste(session, agent_env):
    model, _, _ = agent_env
    model.script = [tool_message(call("generate_quiz")),
                    AIMessage("Voici ton quiz sur CNN ! Bonne chance.\n1. Quelle est la fonction d'une couche ?\n"
                              "2. Qu'est-ce que le pooling ?")]
    reply = run_agent(make_ctx(session), llm=model).replies[0]
    assert reply.content == "Voici ton quiz sur CNN ! Bonne chance."

    model.script = [tool_message(call("generate_quiz")), AIMessage("Voici ton quiz : 1. Quelle couche ? 2. Le pooling ?")]
    assert run_agent(make_ctx_again(session), llm=model).replies[0].content == "Voici ton quiz."


def test_match_course():
    courses = ["Réseaux de neurones", "Docker"]
    assert match_course("reseaux de neurones", courses) == "Réseaux de neurones"
    assert match_course("neurones", courses) == "Réseaux de neurones"
    assert match_course("Kubernetes", courses) is None and match_course(None, courses) is None


def test_aucune_donnee_personnelle_envoyee_au_llm(session, agent_env):
    model, classifier, _ = agent_env
    model.script = [AIMessage("Bonjour !")]
    history = [{"role": "user", "content": "Mon numéro est 22 345 678"}, {"role": "assistant", "content": "Ok."}]
    ctx = make_ctx(session, message="Écris-moi à ali.najjaa@esprit.tn", history=history)
    run_agent(ctx, llm=model)
    sent = "\n".join(str(m.content) for m in model.prompts[0]) + "\n".join(classifier.prompts)
    assert "ali.najjaa@esprit.tn" not in sent and "22 345 678" not in sent
    assert "[EMAIL]" in sent and "[NUMÉRO]" in sent
    assert "etudiant@example.com" not in sent  # l'email du compte n'est jamais dans le prompt


def test_dry_run_s_arrete_apres_le_choix(session, agent_env):
    model, classifier, calls = agent_env
    model.script = [tool_message(call("generate_quiz"))]
    result = run_agent(make_ctx(session), llm=model, dry_run=True)
    assert result.tools == ["generate_quiz"] and result.replies == [] and calls["exam"] == 0

    classifier.decision = {"outil": "summarize"}
    model.script = [AIMessage("…")]
    result = run_agent(make_ctx_again(session), llm=model, dry_run=True)
    assert result.tools == ["summarize"] and result.fallback is True


def make_ctx_again(session):
    user = session.exec(select(User)).first()
    return AgentContext(session=session, user=user, courses=["CNN"], selected_course="CNN", message="Résumé")


def test_outils_decrits_au_format_openai(session, agent_env):
    model, _, _ = agent_env
    run_agent(make_ctx(session), llm=model)
    names = [t["function"]["name"] for t in model.tools]
    assert names == ["ask_course", "summarize", "generate_quiz", "generate_flashcards", "get_progress"]
    quiz = model.tools[2]["function"]["parameters"]["properties"]
    assert quiz["count"]["enum"] == [5, 10] and quiz["difficulty"]["enum"] == ["facile", "moyen", "difficile"]


def test_resume_reutilise_le_cache(session, agent_env, monkeypatch):
    from app.phase9_summaries.models import Summary

    model, _, _ = agent_env
    ctx = make_ctx(session)
    content = {"found": True, "overview": "Vue d'ensemble.", "sections": [{"title": "Pooling", "pages": [1],
                                                                          "bullets": ["Réduit [p.1]"]}]}
    session.add(Summary(user_id=ctx.user_id, course="CNN", mode="course", content=content))
    session.commit()
    monkeypatch.setattr(tools, "generate_summary", lambda *a, **k: pytest.fail("le cache doit être réutilisé"))
    model.script = [tool_message(call("summarize")), AIMessage("Voici le résumé.")]
    reply = run_agent(ctx, llm=model).replies[0]
    assert reply.kind == "summary" and reply.payload["cached"] is True
    assert reply.payload["content"]["sections"][0]["title"] == "Pooling"


# ---------------------------------------------------------------------------
# Routes : réponse directe, tâche de fond, enregistrement des messages
# ---------------------------------------------------------------------------

def _send(client, headers, **body):
    return client.post("/api/companion/messages", json={"message": "Bonjour", **body}, headers=headers)


def test_route_protegee(client):
    assert _send(client, {}).status_code == 401
    assert client.get("/api/companion/jobs/abc").status_code == 401
    assert client.post("/api/quiz-results", json={"message_id": 1, "answers": ["A"]}).status_code == 401


def test_route_reponse_directe_et_messages_enregistres(client, agent_env):
    model, classifier, _ = agent_env
    headers = register(client)
    upload(client, headers, "CNN")
    model.script = [tool_message(call("generate_quiz")), AIMessage("Voici ton quiz !")]
    res = _send(client, headers, message="Fais-moi un quiz", course="CNN")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "done" and body["tool"] == "generate_quiz"
    exchange = body["exchange"]
    assert exchange["conversation"]["title"] == "Fais-moi un quiz"
    assert exchange["user_message"]["kind"] == "text"
    [quiz] = exchange["assistant_messages"]
    assert quiz["kind"] == "quiz" and quiz["content"] == "Voici ton quiz !" and len(quiz["payload"]["questions"]) == 2

    # Mêmes messages relus par la route existante des conversations (kind et payload compris)
    stored = client.get(f"/api/conversations/{exchange['conversation']['id']}/messages", headers=headers).json()
    assert [(m["role"], m["kind"]) for m in stored] == [("user", "text"), ("assistant", "quiz")]
    assert stored[1]["payload"]["questions"][0]["answer"] == "A"


def test_route_conversation_et_cours_d_un_autre_etudiant(client, agent_env):
    headers = register(client)
    other = register(client, email="autre@example.com")
    conv = client.post("/api/conversations", json={}, headers=other).json()["id"]
    assert _send(client, headers, conversation_id=conv).status_code == 404
    assert _send(client, headers, course="CoursInconnu").status_code == 404
    assert _send(client, headers, message="   ").status_code == 422


def test_tache_de_fond_pour_les_outils_longs(client, agent_env, monkeypatch):
    model, _, _ = agent_env
    headers = register(client)
    upload(client, headers, "CNN")
    release = threading.Event()
    original = tools.generate_exam

    def slow_exam(*args, **kwargs):
        assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(tools, "generate_exam", slow_exam)
    monkeypatch.setattr(routes, "SYNC_WAIT_S", 0.05)
    model.script = [tool_message(call("generate_quiz")), AIMessage("Quiz prêt !")]

    res = _send(client, headers, message="Un quiz stp", course="CNN")
    assert res.status_code == 202
    job = res.json()
    assert job["status"] == "running" and job["exchange"] is None
    job_id = job["job_id"]

    # Pendant la génération : l'outil en cours est visible ; un autre étudiant ne voit pas la tâche
    for _ in range(100):
        if client.get(f"/api/companion/jobs/{job_id}", headers=headers).json()["tool"] == "generate_quiz":
            break
        time.sleep(0.02)
    assert client.get(f"/api/companion/jobs/{job_id}", headers=headers).json()["tool"] == "generate_quiz"
    assert client.get(f"/api/companion/jobs/{job_id}", headers=register(client, email="b@example.com")).status_code == 404

    release.set()
    for _ in range(200):
        body = client.get(f"/api/companion/jobs/{job_id}", headers=headers).json()
        if body["status"] != "running":
            break
        time.sleep(0.02)
    assert body["status"] == "done", body
    assert body["exchange"]["assistant_messages"][0]["content"] == "Quiz prêt !"


def test_erreur_du_llm_rien_n_est_enregistre(client, agent_env, session):
    model, _, _ = agent_env
    headers = register(client)

    model.error = LLMError("Impossible de joindre le serveur du LLM. Vérifie qu'Ollama est lancé.")
    res = _send(client, headers)
    assert res.status_code == 503 and "Ollama" in res.json()["detail"]
    assert session.exec(select(Message)).all() == []

    # Échec pendant une tâche de fond : l'état de la tâche porte le message d'erreur
    monkeypatch_wait = routes.SYNC_WAIT_S
    try:
        routes.SYNC_WAIT_S = 0
        job_id = _send(client, headers).json()["job_id"]
        for _ in range(200):
            body = client.get(f"/api/companion/jobs/{job_id}", headers=headers).json()
            if body["status"] != "running":
                break
            time.sleep(0.02)
    finally:
        routes.SYNC_WAIT_S = monkeypatch_wait
    assert body["status"] == "error" and "Ollama" in body["error"] and body["exchange"] is None


# ---------------------------------------------------------------------------
# Quiz interactif : résultats, profil
# ---------------------------------------------------------------------------

def _quiz_message(client, headers, model) -> int:
    upload(client, headers, "CNN")
    model.script = [tool_message(call("generate_quiz")), AIMessage("Quiz prêt !")]
    return _send(client, headers, message="Quiz", course="CNN").json()["exchange"]["assistant_messages"][0]["id"]


def test_resultats_de_quiz(client, agent_env, session):
    model, _, _ = agent_env
    headers = register(client)
    message_id = _quiz_message(client, headers, model)

    assert client.post("/api/quiz-results", json={"message_id": message_id, "answers": ["A"]},
                       headers=headers).status_code == 422  # 2 questions, 1 réponse
    res = client.post("/api/quiz-results", json={"message_id": message_id, "answers": ["a", "C"]}, headers=headers)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["score"] == 1 and body["total"] == 2 and body["correct"] == [True, False]
    assert body["message"]["payload"]["result"]["answers"] == ["A", "C"]

    rows = session.exec(select(QuizResult).order_by(QuizResult.id)).all()
    assert [(r.course, r.concept, r.correct) for r in rows] == [("CNN", "Notion 1", True), ("CNN", "Notion 2", False)]
    # Déjà corrigé : refusé ; le score reste affiché à la réouverture de la conversation
    again = client.post("/api/quiz-results", json={"message_id": message_id, "answers": ["A", "B"]}, headers=headers)
    assert again.status_code == 409
    other = register(client, email="autre@example.com")
    assert client.post("/api/quiz-results", json={"message_id": message_id, "answers": ["A", "B"]},
                       headers=other).status_code == 404


def test_quiz_dans_le_profil_et_les_points_faibles(client, agent_env, session):
    model, _, _ = agent_env
    headers = register(client)
    for answers in (["B", "A"], ["A", "C"]):  # Notion 1 : 1 erreur sur 2 ; Notion 2 : 2 erreurs sur 2
        message_id = _quiz_message(client, headers, model)
        client.post("/api/quiz-results", json={"message_id": message_id, "answers": answers}, headers=headers)
    profile = client.get("/api/profile", headers=headers).json()
    assert profile["quiz"] == {"answers": 4, "correct_rate": 0.25}
    assert profile["weak_points"][:2] == [
        {"course": "CNN", "concept": "Notion 2", "reviews": 2, "to_review_rate": 1.0},
        {"course": "CNN", "concept": "Notion 1", "reviews": 2, "to_review_rate": 0.5},
    ]


def test_quiz_results_sur_un_message_qui_n_est_pas_un_quiz(client, agent_env):
    model, _, _ = agent_env
    headers = register(client)
    model.script = [AIMessage("Bonjour !")]
    message_id = _send(client, headers).json()["exchange"]["assistant_messages"][0]["id"]
    assert client.post("/api/quiz-results", json={"message_id": message_id, "answers": ["A"]},
                       headers=headers).status_code == 422


# ---------------------------------------------------------------------------
# Migration douce, tuteur existant, traces, MLflow, évaluation
# ---------------------------------------------------------------------------

def test_migration_douce_des_messages():
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE messages"))
        conn.execute(text(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL, role VARCHAR NOT NULL,"
            " content VARCHAR NOT NULL, course VARCHAR, sources JSON NOT NULL, answered BOOLEAN NOT NULL,"
            " created_at DATETIME NOT NULL)"))
        conn.execute(text(
            "INSERT INTO messages (conversation_id, role, content, sources, answered, created_at) VALUES "
            "(1, 'user', 'Question ?', '[]', 1, '2026-01-01'), (1, 'assistant', 'Réponse [p.1].', '[]', 1, '2026-01-01')"))
    migrate_messages()
    migrate_messages()  # idempotente
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT role, kind, payload, content FROM messages ORDER BY id")).all()
    assert [tuple(r) for r in rows] == [("user", "text", None, "Question ?"),
                                        ("assistant", "answer", None, "Réponse [p.1].")]


def test_le_tuteur_existant_enregistre_des_reponses_answer(client, llm):
    headers = register(client)
    upload(client, headers, "CNN")
    conv = client.post("/api/conversations", json={}, headers=headers).json()["id"]
    exchange = client.post(f"/api/conversations/{conv}/messages", json={"question": "Le pooling ?"},
                           headers=headers).json()
    assert exchange["user_message"]["kind"] == "text" and exchange["assistant_message"]["kind"] == "answer"
    assert exchange["assistant_message"]["payload"] is None


def test_traces_sans_texte_de_l_etudiant():
    span_inputs = {
        "messages": [[
            {"type": "system", "content": "Tu es Study Companion. Niveau : avancé."},
            {"type": "human", "content": "Je suis Ali, mon email est ali@esprit.tn"},
            {"type": "ai", "content": "", "tool_calls": [{"name": "ask_course",
                                                          "args": {"question": "Ali demande le pooling", "course": "CNN"}}]},
            {"type": "tool", "content": "Réponse du cours trouvée (pages 1)."},
            {"type": "ai", "content": "Bonjour Ali !"},
        ]],
        "role_format": [{"role": "user", "content": "texte libre"}, {"role": "assistant", "content": "Salut Ali"}],
        "outcomes": [{"kind": "answer", "content": "Ali, le pooling réduit [p.1].", "llm_summary": "Trouvée.",
                      "payload": {"questions": [{"question": "Quel est le rôle du pooling ?"}]}}],
        "final_text": "Bravo Ali !",
        "choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "summarize", "arguments": '{"topic": "le pooling selon Ali", "course": "CNN"}'}}]}}],
        "note": "contact : ali@esprit.tn",
    }
    out = redact(span_inputs)
    system, human, call_ai, tool, reply_ai = out["messages"][0]
    assert system["content"] == "Tu es Study Companion. Niveau : avancé."
    assert human["content"] == REDACTED and out["role_format"][0]["content"] == REDACTED
    assert call_ai["tool_calls"][0] == {"name": "ask_course", "args": {"question": REDACTED, "course": "CNN"}}
    assert tool["content"] == "Réponse du cours trouvée (pages 1)."  # compte rendu d'outil : visible
    assert reply_ai["content"] == "[réponse de l'assistant masquée : 13 caractères]"
    assert out["final_text"].startswith("[réponse de l'assistant masquée")
    assert out["outcomes"][0]["llm_summary"] == "Trouvée."
    assert out["outcomes"][0]["payload"]["questions"][0]["question"] == "Quel est le rôle du pooling ?"  # cours
    arguments = json.loads(out["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])
    assert arguments == {"topic": REDACTED, "course": "CNN"}
    assert out["note"] == "contact : [EMAIL]"
    assert "Ali" not in json.dumps(out, ensure_ascii=False)


class SyncExecutor:
    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


@pytest.fixture
def mlflow_runs(monkeypatch):
    from mlflow.tracking import MlflowClient

    from app.phase6_agent import tracing

    monkeypatch.setattr(config, "MLFLOW_ENABLED", True)
    monkeypatch.setattr(tracking, "_executor", SyncExecutor())
    monkeypatch.setattr(tracing, "enable_tracing", lambda: None)  # autolog testé à la main (voir le rapport)
    tracking._clients.clear()
    client = MlflowClient(tracking_uri=config.MLFLOW_TRACKING_URI)

    def runs(name):
        experiment = client.get_experiment_by_name(name)
        return client.search_runs([experiment.experiment_id]) if experiment else []

    yield runs
    for name in ("agent", "agent_eval", "exam"):
        for run in runs(name):
            client.delete_run(run.info.run_id)


def test_run_mlflow_agent_sans_donnees_personnelles(client, agent_env, mlflow_runs):
    model, classifier, _ = agent_env
    headers = register(client)
    upload(client, headers, "CNN")
    classifier.decision = {"outil": "generate_quiz"}
    model.script = [AIMessage("Pas d'outil"), AIMessage("Quiz prêt.")]
    _send(client, headers, message="Quiz pour ali@esprit.tn", course="CNN")
    [run] = mlflow_runs("agent")
    assert run.data.params["outil"] == "generate_quiz" and run.data.params["repli"] == "oui"
    assert run.data.metrics["appels_outils"] == 1 and run.data.metrics["succes"] == 1
    assert run.data.metrics["repli"] == 1 and "duree_s" in run.data.metrics
    everything = json.dumps([run.data.params, run.data.tags], ensure_ascii=False)
    assert "esprit" not in everything and "Quiz pour" not in everything
    assert mlflow_runs("exam")[0].data.tags["source"] == "agent"


def test_evaluation_de_l_agent(client, agent_env, mlflow_runs, tmp_path, capsys, monkeypatch):
    from app.phase5_evaluation import agent_eval

    model, classifier, calls = agent_env
    register(client)
    dataset = tmp_path / "jeu.json"
    dataset.write_text(json.dumps([
        {"message": "Bonjour", "expected": None},
        {"message": "Un quiz stp", "expected": "generate_quiz"},
        {"message": "Mes progrès", "expected": "get_progress"},
    ]), encoding="utf-8")
    monkeypatch.setattr(agent_eval, "RESULTS", tmp_path)
    model.script = [AIMessage("Bonjour !"), tool_message(call("generate_quiz")), tool_message(call("summarize"))]

    metrics = agent_eval.main(["etudiant@example.com", "--dataset", str(dataset)], llm=model)
    assert metrics["taux_bon_outil"] == pytest.approx(2 / 3, abs=1e-3)
    assert metrics["taux_repli"] == pytest.approx(1 / 3, abs=1e-3)
    assert metrics["taux_bon_outil_get_progress"] == 0
    assert calls == {"exam": 0, "deck": 0}  # arrêt après le choix : aucun outil long exécuté
    [run] = mlflow_runs("agent_eval")
    assert run.data.metrics["taux_bon_outil"] == pytest.approx(0.6667, abs=1e-3)
    assert "Taux de bon outil : 67%" in capsys.readouterr().out
    assert len(list(tmp_path.glob("agent_eval_*.csv"))) == 1


def test_jeu_d_evaluation_fourni():
    from app.phase5_evaluation.agent_eval import DATASET, load_dataset

    items = load_dataset(DATASET)
    assert len(items) == 26
    expected = {item["expected"] for item in items}
    assert expected == {"aucun", "ask_course", "summarize", "generate_quiz", "generate_flashcards", "get_progress"}
    # Formulations de résumé vues en test réel (bug b)
    summaries = {item["message"] for item in items if item["expected"] == "summarize"}
    assert "Résume les idées principales de ce cours" in summaries and len(summaries) == 9
