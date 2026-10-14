import time

from app.phase3_rag.rag import is_follow_up, search_query
from tests.helpers import register, upload


def _ask(client, headers, conv_id, question, course="CNN"):
    return client.post(f"/api/conversations/{conv_id}/messages", json={"question": question, "course": course},
                       headers=headers)


def test_creation_et_messages(client, llm):
    headers = register(client)
    upload(client, headers, "CNN")
    conv = client.post("/api/conversations", json={"course": "CNN"}, headers=headers)
    assert conv.status_code == 201
    conv_id = conv.json()["id"]
    assert conv.json()["title"] == "Nouvelle conversation"

    question = "Quel est le rôle exact du pooling dans un réseau de neurones convolutif moderne ?"
    res = _ask(client, headers, conv_id, question)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["conversation"]["title"] == question[:60].rstrip()
    assert body["user_message"]["role"] == "user" and body["user_message"]["course"] == "CNN"
    assert body["assistant_message"]["content"] == llm.reply
    assert body["assistant_message"]["answered"] is True
    assert body["assistant_message"]["sources"][0]["course"] == "CNN"

    # Le titre ne change plus aux questions suivantes
    _ask(client, headers, conv_id, "Et la convolution, à quoi sert-elle ?")
    messages = client.get(f"/api/conversations/{conv_id}/messages", headers=headers).json()
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert client.get("/api/conversations", headers=headers).json()[0]["title"] == question[:60].rstrip()


def test_reponse_hors_cours_non_marquee_repondue(client, llm):
    headers = register(client)
    upload(client, headers, "CNN")
    conv_id = client.post("/api/conversations", json={}, headers=headers).json()["id"]
    llm.reply = "Cette information n'est pas présente dans le cours."
    res = _ask(client, headers, conv_id, "Quelle est la capitale de la France ?", course=None)
    assert res.json()["assistant_message"]["answered"] is False
    assert res.json()["assistant_message"]["sources"] == []


def test_liste_plus_recente_en_premier_renommer_supprimer(client, llm):
    headers = register(client)
    upload(client, headers, "CNN")
    first = client.post("/api/conversations", json={}, headers=headers).json()["id"]
    second = client.post("/api/conversations", json={}, headers=headers).json()["id"]
    assert [c["id"] for c in client.get("/api/conversations", headers=headers).json()] == [second, first]

    time.sleep(0.05)  # horloge Windows : ~15 ms de résolution, évite deux dates identiques
    _ask(client, headers, first, "Qu'est-ce que le pooling dans un CNN ?")  # first redevient la plus récente
    assert [c["id"] for c in client.get("/api/conversations", headers=headers).json()] == [first, second]

    res = client.patch(f"/api/conversations/{first}", json={"title": "  Révisions   CNN "}, headers=headers)
    assert res.status_code == 200 and res.json()["title"] == "Révisions CNN"
    assert client.patch(f"/api/conversations/{first}", json={"title": "   "}, headers=headers).status_code == 422

    assert client.delete(f"/api/conversations/{first}", headers=headers).status_code == 200
    assert client.get(f"/api/conversations/{first}/messages", headers=headers).status_code == 404
    assert [c["id"] for c in client.get("/api/conversations", headers=headers).json()] == [second]


def test_isolation_des_conversations(client, llm):
    alice = register(client, "alice@example.com")
    bob = register(client, "bob@example.com")
    upload(client, alice, "CNN")
    conv_id = client.post("/api/conversations", json={}, headers=alice).json()["id"]
    _ask(client, alice, conv_id, "Qu'est-ce que le pooling dans un CNN ?")

    assert client.get("/api/conversations", headers=bob).json() == []
    assert client.get(f"/api/conversations/{conv_id}/messages", headers=bob).status_code == 404
    assert _ask(client, bob, conv_id, "Question ?", course=None).status_code == 404
    assert client.patch(f"/api/conversations/{conv_id}", json={"title": "x"}, headers=bob).status_code == 404
    assert client.delete(f"/api/conversations/{conv_id}", headers=bob).status_code == 404
    # Bob ne peut pas cibler le cours d'Alice depuis sa propre conversation
    bob_conv = client.post("/api/conversations", json={}, headers=bob).json()["id"]
    assert _ask(client, bob, bob_conv, "Pooling ?", course="CNN").status_code == 404
    assert client.post("/api/conversations", json={"course": "CNN"}, headers=bob).status_code == 404


def test_memoire_des_3_derniers_echanges_masquee(client, llm):
    headers = register(client)
    upload(client, headers, "CNN")
    conv_id = client.post("/api/conversations", json={}, headers=headers).json()["id"]
    questions = [
        "Question numéro un sur le pooling ?",
        "Question numéro deux, écris-moi à ali@example.com ?",
        "Question numéro trois sur la convolution ?",
        "Question numéro quatre sur les filtres ?",
    ]
    for q in questions:
        _ask(client, headers, conv_id, q)
    _ask(client, headers, conv_id, "Et pour les CNN ?")

    system, prompt = llm.calls[-1]
    assert "Échanges précédents" in prompt
    assert questions[0] not in prompt  # seuls les 3 derniers échanges sont gardés
    assert "Question numéro deux" in prompt and questions[3] in prompt
    assert "ali@example.com" not in prompt and "[EMAIL]" in prompt
    assert "échanges précédents" in system.lower()
    # Première question : pas d'historique dans le prompt
    assert "Échanges précédents" not in llm.calls[0][1]


def test_requete_de_recherche_reformulee():
    history = [{"role": "user", "content": "Qu'est-ce que le surapprentissage ?"},
               {"role": "assistant", "content": "C'est ..."}]
    assert search_query("Et pour les CNN ?", history) == "Qu'est-ce que le surapprentissage ? Et pour les CNN ?"
    complete = "Comment fonctionne la rétropropagation du gradient dans un réseau ?"
    assert search_query(complete, history) == complete
    assert search_query("Et pour les CNN ?", []) == "Et pour les CNN ?"
    assert is_follow_up("Peux-tu donner un exemple de cela ?")
    assert not is_follow_up("Quelle est la différence entre le pooling max et le pooling moyen ?")


def test_ancienne_route_ask_toujours_fonctionnelle(client, llm):
    headers = register(client)
    upload(client, headers, "CNN")
    res = client.post("/api/ask", json={"question": "Pooling ?", "course": "CNN"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["answer"] == llm.reply and res.json()["sources"]


def test_erreur_llm_rien_enregistre(client, monkeypatch):
    from app.phase1_llm.llm import LLMError
    from app.phase3_rag import rag

    def broken(*args, **kwargs):
        raise LLMError("Impossible de joindre le serveur du LLM. Vérifie qu'Ollama est lancé.")

    monkeypatch.setattr(rag, "chat", broken)
    headers = register(client)
    upload(client, headers, "CNN")
    conv_id = client.post("/api/conversations", json={}, headers=headers).json()["id"]
    res = _ask(client, headers, conv_id, "Qu'est-ce que le pooling ?")
    assert res.status_code == 503
    assert client.get(f"/api/conversations/{conv_id}/messages", headers=headers).json() == []
