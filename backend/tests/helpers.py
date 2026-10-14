"""Outils partagés par les tests (importés depuis tests.helpers, jamais depuis conftest)."""
import hashlib

from fastapi.testclient import TestClient

DIM = 16


def fake_vector(text: str) -> list[float]:
    """Vecteur déterministe et normalisé : deux textes identiques ont la même similarité maximale."""
    digest = hashlib.sha256(text.lower().encode("utf-8")).digest()
    raw = [b - 127.5 for b in digest[:DIM]]
    norm = sum(x * x for x in raw) ** 0.5
    return [x / norm for x in raw]


class FakeLLM:
    """Remplace phase1_llm.chat : enregistre les prompts et renvoie une réponse fixe."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.reply = "Le pooling réduit la taille des cartes d'activation [p.1]."

    def __call__(self, system: str, user: str, **kwargs) -> str:
        self.calls.append((system, user))
        return self.reply


def register(client: TestClient, email: str = "etudiant@example.com", password: str = "motdepasse123",
             level: str = "intermediaire") -> dict:
    """Crée un compte et renvoie l'en-tête Authorization à utiliser dans les requêtes."""
    res = client.post("/api/auth/register", json={"email": email, "password": password, "level": level})
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


PAGE_TEXT = (
    "Le pooling réduit la taille des cartes d'activation produites par les couches de convolution. "
    "Il garde l'information la plus importante et rend le réseau plus robuste aux petites translations. "
)


def make_pdf(pages: list[str]) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


def upload(client: TestClient, headers: dict, course: str, pages: list[str] | None = None):
    pdf = make_pdf(pages or [PAGE_TEXT * 3])
    return client.post("/api/upload", files={"file": (f"{course}.pdf", pdf, "application/pdf")},
                       data={"course": course}, headers=headers)


def sample_exam(course: str):
    from app.phase4_exam.schemas import Exam, ExamSection, MCQQuestion

    question = MCQQuestion(question="Quel est le rôle du pooling ?",
                           choices=["Réduire la taille", "Ajouter des poids", "Normaliser", "Mélanger"],
                           answer="A", explanation="Le pooling réduit la taille des cartes.", page=1)
    return Exam(course=course, difficulty="facile", format="qcm", expected_questions=1, sections=[
        ExamSection(letter="A", title="QCM", instructions="Une seule bonne réponse.",
                    points_per_question=20, questions=[question]),
    ])


def sample_deck(course: str):
    from app.phase7_flashcards.schemas import Flashcard, FlashcardDeck

    return FlashcardDeck(course=course, cards=[
        Flashcard(concept="Pooling", front="Quel est le rôle du pooling ?",
                  back="Il réduit la taille des cartes d'activation.", page=1),
        Flashcard(concept="Convolution", front="Que produit une couche de convolution ?",
                  back="Elle produit des cartes d'activation à partir de filtres.", page=1),
    ])
