"""Optimisations du temps de réponse : parallélisme contrôlé, vérifications groupées, cache des concepts,
vecteurs Qdrant réutilisés, streaming SSE du tuteur et de l'assistant, keep_alive d'Ollama."""
import json
import re
import threading
from types import SimpleNamespace

import httpx
import pytest
from openai import RateLimitError
from qdrant_client.models import PointStruct

from app.core import concurrency, config
from app.phase1_llm import llm
from app.phase2_embeddings import vectorstore
from app.phase5_evaluation.stats import GenerationStats, collecting, record
from tests.helpers import fake_vector, register, upload

LONG_TEXT = ("Le pooling réduit la taille des cartes d'activation et rend le réseau plus robuste. " * 5).strip()


def add_chunks(n: int = 8, user_id: int = 1, course: str = "CNN") -> None:
    vectorstore.client.upsert("courses", points=[
        PointStruct(id=i + 300, vector=fake_vector(f"passage {i}"),
                    payload={"course": course, "page": i + 1, "text": f"Passage {i}. {LONG_TEXT}", "user_id": user_id})
        for i in range(n)
    ])


def sse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.split("\n\n"):
        name = re.search(r"^event: (.+)$", block, re.M)
        data = re.search(r"^data: (.+)$", block, re.M)
        if name and data:
            events.append((name.group(1), json.loads(data.group(1))))
    return events


# ---------------------------------------------------------------------------
# parallel_map et sémaphore
# ---------------------------------------------------------------------------

def test_parallel_map_sequentiel_avec_1(monkeypatch):
    monkeypatch.setattr(config, "LLM_CONCURRENCY", 1)
    threads = []
    result = concurrency.parallel_map(lambda x: (threads.append(threading.current_thread().name), x * 2)[1], [1, 2, 3])
    assert result == [2, 4, 6]
    assert set(threads) == {threading.current_thread().name}  # aucune création de thread


def test_parallel_map_en_threads_ordre_et_collecteur_conserves(monkeypatch):
    monkeypatch.setattr(config, "LLM_CONCURRENCY", 3)
    barrier = threading.Barrier(3, timeout=5)  # les 3 éléments doivent tourner en même temps

    def work(x):
        barrier.wait()
        record("appels_llm")  # le collecteur actif est visible dans chaque thread
        return x * 10

    stats = GenerationStats()
    with collecting(stats):
        assert concurrency.parallel_map(work, [3, 1, 2]) == [30, 10, 20]
    assert stats.get("appels_llm") == 3


def test_concurrence_par_defaut():
    assert config.LLM_CONCURRENCY == 1  # tests : URL locale (pas Groq), aucune variable LLM_CONCURRENCY


# ---------------------------------------------------------------------------
# Examen : moteur par tours
# ---------------------------------------------------------------------------

class PassageExamLLM:
    """Réponse déterminée par le passage du prompt (et non par l'ordre des appels) : même examen en parallèle."""

    def __init__(self, grouped_ok: bool = True):
        self.grouped_ok = grouped_ok
        self.lock = threading.Lock()
        self.prompts: list[tuple[str, str]] = []

    def __call__(self, system, prompt, **kwargs):
        from app.phase4_exam.generator import VERIFY_SYSTEM_PROMPT

        with self.lock:
            self.prompts.append((system, prompt))
        if system == VERIFY_SYSTEM_PROMPT:
            n = prompt.count("--- Question ")
            if n and not self.grouped_ok:
                return "pas du json"
            return json.dumps({"answers": ["A"] * max(1, n)})
        page = int(re.search(r"\[page (\d+)\]", prompt).group(1))
        return json.dumps({"items": [{
            "question": f"Quelle notion du cours est présentée à la page {page} ?",
            "choices": [f"Notion {page}", f"Autre notion {page}", f"Troisième idée {page}", f"Dernier choix {page}"],
            "answer": "A", "explanation": "Le cours la présente à cette page.", "page": page}]})


def _exam(monkeypatch, llm_fake, concurrency_level: int = 1):
    import random

    from app.phase4_exam import generator

    monkeypatch.setattr(config, "LLM_CONCURRENCY", concurrency_level)
    monkeypatch.setattr(generator, "chat", llm_fake)
    monkeypatch.setattr(generator, "embed_passages", lambda texts: [fake_vector(t) for t in texts])
    real_random = random.Random
    monkeypatch.setattr(generator.random, "Random", lambda *args: real_random(7))
    stats = GenerationStats()
    exam = generator.generate_exam("CNN", "qcm", 5, "moyen", user_id=1, stats=stats)
    return exam, stats


def test_examen_identique_en_parallele(monkeypatch):
    add_chunks()
    sequential, stats_1 = _exam(monkeypatch, PassageExamLLM(), 1)
    parallel, stats_3 = _exam(monkeypatch, PassageExamLLM(), 3)
    assert sequential.model_dump() == parallel.model_dump()
    assert sequential.question_count == 5
    assert stats_1.get("appels_generation") == stats_3.get("appels_generation") == 5
    assert stats_1.get("verifications_groupees") == 1  # tour de 4 vérifié en un appel, puis 1 question seule


def test_verification_groupee_illisible_repli_unitaire(monkeypatch):
    add_chunks()
    fake = PassageExamLLM(grouped_ok=False)
    exam, stats = _exam(monkeypatch, fake)
    assert exam.question_count == 5
    assert stats.get("verifications_groupees_repli") == 1
    from app.phase4_exam.generator import VERIFY_SYSTEM_PROMPT

    verifications = [p for s, p in fake.prompts if s == VERIFY_SYSTEM_PROMPT]
    assert len(verifications) == 1 + 4 + 1  # appel groupé illisible, 4 vérifications unitaires, puis la 5e question


def test_questions_acceptees_rappelees_au_generateur(monkeypatch):
    add_chunks()
    fake = PassageExamLLM()
    _exam(monkeypatch, fake)
    from app.phase4_exam.generator import SYSTEM_PROMPT

    generations = [p for s, p in fake.prompts if s == SYSTEM_PROMPT]
    assert "- (aucune)" in generations[0]
    assert "Quelle notion du cours est présentée à la page" in generations[-1]  # 5e question : 4 déjà acceptées


# ---------------------------------------------------------------------------
# Flashcards : cache des concepts et vecteurs Qdrant
# ---------------------------------------------------------------------------

class ConceptCountingLLM:
    def __init__(self):
        self.concept_calls = 0
        self.lock = threading.Lock()

    def __call__(self, system, prompt, **kwargs):
        from app.phase7_flashcards.generator import VERIFY_SYSTEM_PROMPT

        if system == VERIFY_SYSTEM_PROMPT:
            cards = prompt.split("--- Carte ")[1:] or [prompt]
            return json.dumps({"answers": [False] * len(cards)})
        if "notions clés" in prompt:
            with self.lock:
                self.concept_calls += 1
            page = int(re.search(r"\[page (\d+)\]", prompt).group(1))
            return json.dumps({"items": [{"name": f"Notion {chr(64 + page)}", "importance": 3}]})
        concept = prompt.split("notion « ")[1].split(" »")[0]
        return json.dumps({"items": [{"concept": concept, "front": f"Que désigne la {concept.lower()} ?",
                                      "back": f"Elle décrit l'idée principale expliquée sur {concept.lower()}.",
                                      "page": 1}]})


def _flashcards(monkeypatch, fake, concurrency_level=1):
    from app.phase7_flashcards import generator

    monkeypatch.setattr(config, "LLM_CONCURRENCY", concurrency_level)
    monkeypatch.setattr(generator, "chat", fake)
    encoded: list[str] = []

    def embed(texts):
        encoded.extend(texts)
        return [fake_vector(t) for t in texts]

    monkeypatch.setattr(generator, "embed_passages", embed)
    monkeypatch.setattr(generator, "embed_query", fake_vector)
    stats = GenerationStats()
    deck = generator.generate_flashcards("CNN", 10, user_id=1, stats=stats)
    return deck, stats, encoded


def test_concepts_en_cache_et_vecteurs_reutilises(monkeypatch):
    add_chunks(12)
    fake = ConceptCountingLLM()
    deck, stats, encoded = _flashcards(monkeypatch, fake)
    first_calls = fake.concept_calls
    assert first_calls == 4 and deck.cards  # 12 passages : 4 blocs de 3
    assert stats.get("vecteurs_reutilises") == 12
    assert not any(t.startswith("Passage ") for t in encoded)  # aucun passage ré-encodé

    _, stats_2, _ = _flashcards(monkeypatch, fake)
    assert fake.concept_calls == first_calls  # deuxième paquet : concepts repris du cache
    assert stats_2.get("blocs_concepts_en_cache") == 4


def test_cache_par_etudiant(monkeypatch):
    add_chunks(6, user_id=1)
    add_chunks(6, user_id=2)  # mêmes ids : remplace les passages, même contenu pour l'étudiant 2
    from app.phase7_flashcards import generator

    chunks = vectorstore.get_course_chunks("CNN", 2)
    assert generator.concept_cache_key(1, "CNN", chunks) != generator.concept_cache_key(2, "CNN", chunks)


def test_flashcards_identiques_en_parallele(monkeypatch):
    add_chunks(12)
    from app.phase7_flashcards.generator import clear_concept_cache

    sequential, _, _ = _flashcards(monkeypatch, ConceptCountingLLM(), 1)
    clear_concept_cache()
    parallel, _, _ = _flashcards(monkeypatch, ConceptCountingLLM(), 3)
    assert sequential == parallel


# ---------------------------------------------------------------------------
# Résumé : sections en parallèle
# ---------------------------------------------------------------------------

def test_resume_parallele_refait_les_titres_en_double(monkeypatch):
    add_chunks(12)
    from app.phase9_summaries import generator

    lock = threading.Lock()
    prompts: list[str] = []

    def fake(system, prompt, **kwargs):
        with lock:
            prompts.append(prompt)
        if "Rédige une vue d'ensemble" in prompt:
            return json.dumps({"overview": "Le cours présente le pooling. Il explique son rôle. Il donne des "
                                           "exemples. Il relie les notions entre elles."})
        page = int(re.search(r"\[page (\d+)\]", prompt).group(1))
        title = "Rôle du pooling" if "différent de ceux" not in prompt else f"Suite du cours page {page}"
        bullets = [f"Le pooling réduit la taille des cartes, idée {i} [p.{page}]" for i in range(3)]
        return json.dumps({"title": title, "bullets": bullets})

    monkeypatch.setattr(config, "LLM_CONCURRENCY", 3)
    monkeypatch.setattr(generator, "chat", fake)
    stats = GenerationStats()
    content = generator.generate_summary("CNN", "course", user_id=1, stats=stats)
    titles = [s.title for s in content.sections]
    assert len(titles) == 2 and len(set(titles)) == 2  # 12 passages : 2 sections de 6
    assert stats.get("sections_titre_refait") == 1


# ---------------------------------------------------------------------------
# Client LLM : keep_alive, streaming, 429 avant le flux
# ---------------------------------------------------------------------------

def test_keep_alive_envoye_seulement_a_ollama(monkeypatch):
    monkeypatch.setattr(config, "IS_OLLAMA", True)
    monkeypatch.setattr(config, "LLM_KEEP_ALIVE", "-1")
    assert llm.ollama_options() == {"extra_body": {"keep_alive": -1}}
    monkeypatch.setattr(config, "LLM_KEEP_ALIVE", "30m")
    assert llm.ollama_options() == {"extra_body": {"keep_alive": "30m"}}
    monkeypatch.setattr(config, "IS_OLLAMA", False)  # Groq : paramètre inconnu, jamais envoyé
    assert llm.ollama_options() == {}


def _chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


def test_chat_stream_fragments_et_time_to_first_token(monkeypatch):
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        return iter([_chunk(None), _chunk("Le pooling "), _chunk("réduit [p.1].")])

    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    fragments: list[str] = []
    stats = GenerationStats()
    with collecting(stats):
        text = llm.chat_stream("s", "u", fragments.append)
    assert text == "Le pooling réduit [p.1]." and fragments == ["Le pooling ", "réduit [p.1]."]
    assert sent["stream"] is True
    assert stats.values["time_to_first_token"] >= 0 and stats.get("appels_llm") == 1


def test_chat_stream_vide_et_429(monkeypatch):
    monkeypatch.setattr(llm, "_wait", lambda s: None)
    response = httpx.Response(429, headers={"retry-after": "1"}, request=httpx.Request("POST", "http://llm"))
    steps = [RateLimitError("limite", response=response, body=None), iter([_chunk("ok")]), iter([_chunk("")])]

    def create(**kwargs):
        step = steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    assert llm.chat_stream("s", "u", lambda t: None) == "ok"  # 429 puis nouvel essai
    with pytest.raises(llm.LLMError, match="vide"):
        llm.chat_stream("s", "u", lambda t: None)


# ---------------------------------------------------------------------------
# Streaming SSE
# ---------------------------------------------------------------------------

def test_ask_stream_fragments_puis_final_valide(client, llm):
    headers = register(client)
    upload(client, headers, "CNN")
    res = client.post("/api/ask/stream", json={"question": "Rôle du pooling ?", "course": "CNN"}, headers=headers)
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/event-stream")
    events = sse_events(res.text)
    tokens = [d["text"] for e, d in events if e == "token"]
    name, final = events[-1]
    assert name == "final" and "".join(tokens) == final["answer"] == llm.reply
    assert final["answered"] is True and final["sources"][0]["page"] == 1
    assert final["time_to_first_token"] is None  # chat_stream simulé : pas de mesure


def test_ask_stream_erreur_llm(client, monkeypatch):
    from app.phase3_rag import rag

    def broken(*args, **kwargs):
        raise llm.LLMError("Impossible de joindre le serveur du LLM.")

    monkeypatch.setattr(rag, "chat_stream", broken)
    headers = register(client)
    upload(client, headers, "CNN")
    events = sse_events(client.post("/api/ask/stream", json={"question": "Q ?"}, headers=headers).text)
    assert events[-1] == ("error", {"detail": "Impossible de joindre le serveur du LLM.", "status": 503})


def test_ask_stream_protege(client):
    assert client.post("/api/ask/stream", json={"question": "Q ?"}).status_code == 401


def test_companion_stream(client, monkeypatch):
    from app.phase6_agent import routes
    from app.phase6_agent.graph import AgentResult, Reply

    def fake_agent(ctx):
        ctx.on_tool("ask_course")
        ctx.on_token("Le pooling ")
        ctx.on_token("réduit [p.1].")
        return AgentResult(replies=[Reply(kind="answer", content="Le pooling réduit [p.1].",
                                          sources=[{"course": "CNN", "page": 1, "score": 0.9, "excerpt": "…"}])],
                           tools=["ask_course"], fallback=False, duration_s=0.1)

    monkeypatch.setattr(routes, "run_agent", fake_agent)
    headers = register(client)
    res = client.post("/api/companion/messages/stream", json={"message": "Rôle du pooling ?"}, headers=headers)
    events = sse_events(res.text)
    names = [e for e, _ in events]
    assert names[0] == "start" and "tool" in names and names[-1] == "final"
    assert "".join(d["text"] for e, d in events if e == "token") == "Le pooling réduit [p.1]."
    final = events[-1][1]
    assert final["status"] == "done" and final["exchange"]["tools"] == ["ask_course"]
    conversation_id = events[0][1]["conversation_id"]
    stored = client.get(f"/api/conversations/{conversation_id}/messages", headers=headers).json()
    assert [m["role"] for m in stored] == ["user", "assistant"] and stored[1]["sources"][0]["page"] == 1
