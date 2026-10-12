import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

Difficulty = Literal["facile", "moyen", "difficile"]
ExamFormat = Literal["complet", "qcm"]

# Préfixe de choix ajouté par le modèle : "A. ", "b) ", "C: "…
CHOICE_PREFIX = re.compile(r"^\s*[A-Da-d]\s*[.):-]\s*")
# Choix interdits dans un QCM : « Tous les éléments… », « Toutes les réponses », « Aucune de ces réponses »
FORBIDDEN_CHOICE = re.compile(r"\b(tous les|toutes les|aucune de|aucun de)\b", re.IGNORECASE)
# Choix réduit à une simple lettre (« A », « d ») : les vraies propositions sont ailleurs
LONE_LETTER = re.compile(r"^[A-Da-d]$")
# Réponse fermée (« Oui, car… », « Non… ») : interdite pour une question à réponse courte
YES_NO = re.compile(r"^\s*(oui|non)\b", re.IGNORECASE)
# Questions de dénombrement (« combien de types… ») : ambiguës, souvent fausses
COUNTING = re.compile(r"\bcombien\b", re.IGNORECASE)
# Négations (« ne sont pas », « n'est pas », « ne doit jamais ») : rendent la question confuse
NEGATION = re.compile(r"\b(?:ne\s+\S+|n['’]\S+)\s+(?:pas|jamais|plus)\b", re.IGNORECASE)
# Deux questions juxtaposées (« … et quelles sont… »)
DOUBLE_QUESTION = re.compile(r"\bet\s+(?:quel|quelle|quels|quelles|comment|pourquoi)\b", re.IGNORECASE)
# Mots anglais fréquents : 2 ou plus → texte non traduit
ENGLISH_WORDS = re.compile(r"\b(the|of|and|is|are|between|about|which|with|for)\b", re.IGNORECASE)
WORD = re.compile(r"[a-zàâçéèêëîïôûùüÿœ]{4,}", re.IGNORECASE)

# Antislashs mal échappés dans le JSON : « C:\flutter\bin » devient \f (saut de page) et \b (retour arrière)
CONTROL_CHARS = {"\f": "\\f", "\b": "\\b", "\t": "\\t", "\r": "\\r", "\v": "\\v"}


def capitalize_first(text: str) -> str:
    """Restaure les antislashs perdus, retire les espaces autour et met la première lettre en majuscule."""
    for char, escaped in CONTROL_CHARS.items():
        text = text.replace(char, escaped)
    text = text.strip()
    return text[:1].upper() + text[1:]


def check_question(text: str) -> str:
    """Règles communes à toutes les questions : pas de « combien », pas deux questions en une."""
    text = capitalize_first(text)
    if COUNTING.search(text):
        raise ValueError("question de dénombrement (« combien »)")
    if DOUBLE_QUESTION.search(text) or text.count("?") > 1:
        raise ValueError("deux questions en une")
    return text


def check_french(text: str) -> str:
    """Refuse un texte resté en anglais (réponse attendue, correction, explication)."""
    text = capitalize_first(text)
    if len(ENGLISH_WORDS.findall(text)) >= 2:
        raise ValueError("texte en anglais")
    return text


# ---------------------------------------------------------------------------
# Les 4 types de questions
# ---------------------------------------------------------------------------

class MCQQuestion(BaseModel):
    """QCM : exactement 4 choix distincts, une seule bonne réponse (A à D)."""

    type: Literal["qcm"] = "qcm"
    question: str = Field(min_length=10, max_length=250)
    choices: list[str] = Field(min_length=4, max_length=4)
    answer: Literal["A", "B", "C", "D"]
    explanation: str = Field(min_length=10)
    page: int = Field(ge=1)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        """Une vraie question (« ? » ou « : » final), sans liste, sans négation."""
        value = check_question(value)
        if "•" in value:
            raise ValueError("la question contient une liste de propositions")
        if not value.rstrip().endswith(("?", ":")):
            raise ValueError("ce n'est pas une question")
        if NEGATION.search(value):
            raise ValueError("question négative")
        return value

    @field_validator("choices")
    @classmethod
    def clean_choices(cls, choices: list[str]) -> list[str]:
        """Retire les préfixes « A. », refuse les choix vides, en double, réduits à une lettre ou du type « Tous les… »."""
        cleaned = [CHOICE_PREFIX.sub("", c).strip() for c in choices]
        if any(not c for c in cleaned):
            raise ValueError("un des choix est vide")
        if any(LONE_LETTER.match(c) for c in cleaned):
            raise ValueError("un choix est réduit à une simple lettre")
        if any(YES_NO.match(c) for c in cleaned):
            raise ValueError("question fermée (choix oui/non)")
        if len({c.lower() for c in cleaned}) < 4:
            raise ValueError("deux choix sont identiques")
        if any(FORBIDDEN_CHOICE.search(c) for c in cleaned):
            raise ValueError("choix interdit (« tous les… », « aucune de… »)")
        return [capitalize_first(c) for c in cleaned]

    @field_validator("answer", mode="before")
    @classmethod
    def normalize_answer(cls, value):
        """Accepte « b », « B. » ou « B) » et garde uniquement la lettre en majuscule."""
        if isinstance(value, str):
            return value.strip().upper()[:1]
        return value

    @field_validator("explanation")
    @classmethod
    def french_explanation(cls, value: str) -> str:
        return check_french(value)


class TrueFalseQuestion(BaseModel):
    """Vrai ou Faux : une affirmation, la bonne réponse et la justification attendue."""

    type: Literal["vrai_faux"] = "vrai_faux"
    statement: str = Field(min_length=15, max_length=250)
    answer: bool
    correction: str = Field(min_length=10)
    page: int = Field(ge=1)

    @field_validator("statement")
    @classmethod
    def clean_statement(cls, value: str) -> str:
        """Une seule affirmation simple : sans liste, sans « combien », sans négation."""
        value = check_question(value)
        if ":" in value or "•" in value:
            raise ValueError("l'affirmation contient une liste")
        if NEGATION.search(value):
            raise ValueError("affirmation négative")
        return value

    @field_validator("correction")
    @classmethod
    def french_correction(cls, value: str) -> str:
        return check_french(value)


class ShortAnswerQuestion(BaseModel):
    """Question à réponse courte : une notion précise (définition, signification, rôle…)."""

    type: Literal["courte"] = "courte"
    question: str = Field(min_length=10, max_length=250)
    expected_answer: str = Field(min_length=3)
    page: int = Field(ge=1)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        return check_question(value)

    @field_validator("expected_answer")
    @classmethod
    def clean_answer(cls, value: str) -> str:
        """Refuse les questions fermées (« Oui »/« Non ») et les réponses en anglais."""
        if YES_NO.match(value):
            raise ValueError("question fermée (réponse oui/non)")
        return check_french(value)


class OpenQuestion(BaseModel):
    """Question de réflexion : exactement 4 éléments de réponse attendus, notés 1 point chacun."""

    type: Literal["ouverte"] = "ouverte"
    question: str = Field(min_length=20, max_length=300)
    expected_points: list[str] = Field(min_length=4, max_length=4)
    page: int = Field(ge=1)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        """Une réflexion peut enchaîner plusieurs consignes (« Expliquez… et comment… »), mais avec un seul « ? »."""
        value = capitalize_first(value)
        if COUNTING.search(value):
            raise ValueError("question de dénombrement (« combien »)")
        if value.count("?") > 1:
            raise ValueError("deux questions en une")
        return value

    @field_validator("expected_points")
    @classmethod
    def clean_points(cls, points: list[str]) -> list[str]:
        cleaned = [p.strip().lstrip("-•*0123456789.) ").strip() for p in points]
        if any(len(p) < 5 for p in cleaned):
            raise ValueError("un élément de réponse attendu est trop court")
        return [check_french(p) for p in cleaned]

    @model_validator(mode="after")
    def points_not_in_question(self):
        """Refuse des éléments de réponse qui ne font que répéter les mots de la question."""
        question_words = {w.lower() for w in WORD.findall(self.question)}
        echoes = 0
        for point in self.expected_points:
            words = {w.lower() for w in WORD.findall(point)}
            if words and len(words & question_words) / len(words) >= 0.8:
                echoes += 1
        if echoes >= 2:
            raise ValueError("les éléments de réponse répètent la question")
        return self
    


Question = Annotated[
    Union[MCQQuestion, TrueFalseQuestion, ShortAnswerQuestion, OpenQuestion],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Formats imposés au LLM (sorties structurées)
# ---------------------------------------------------------------------------

class MCQBatch(BaseModel):
    items: list[MCQQuestion] = Field(min_length=1, max_length=5)


class TrueFalseBatch(BaseModel):
    items: list[TrueFalseQuestion] = Field(min_length=1, max_length=5)


class ShortAnswerBatch(BaseModel):
    items: list[ShortAnswerQuestion] = Field(min_length=1, max_length=5)


class OpenBatch(BaseModel):
    items: list[OpenQuestion] = Field(min_length=1, max_length=2)


class LetterAnswers(BaseModel):
    """Vérification des QCM : une lettre par question, dans l'ordre."""

    answers: list[Literal["A", "B", "C", "D"]] = Field(min_length=1, max_length=5)


class BoolAnswers(BaseModel):
    """Vérification des Vrai/Faux : true ou false par affirmation, dans l'ordre."""

    answers: list[bool] = Field(min_length=1, max_length=5)


# ---------------------------------------------------------------------------
# Examen complet
# ---------------------------------------------------------------------------

class ExamSection(BaseModel):
    """Une partie de l'examen (ex. « Partie A — QCM »), avec son barème."""

    letter: str
    title: str
    instructions: str
    points_per_question: float
    questions: list[Question]

    @property
    def total_points(self) -> float:
        return self.points_per_question * len(self.questions)


class Exam(BaseModel):
    """Examen complet, prêt à être mis en page en PDF."""

    course: str
    difficulty: Difficulty
    format: ExamFormat
    expected_questions: int
    sections: list[ExamSection]

    @property
    def total_points(self) -> float:
        return sum(s.total_points for s in self.sections)

    @property
    def question_count(self) -> int:
        return sum(len(s.questions) for s in self.sections)


class ExamRequest(BaseModel):
    """Options choisies par l'utilisateur pour générer un examen (toujours noté sur 20)."""

    format: ExamFormat = "complet"
    num_questions: Literal[5, 10, 20] = 20   # utilisé uniquement pour le format « qcm » (4, 2 ou 1 point par question)
    difficulty: Difficulty = "moyen"
    include_answers: bool = True


if __name__ == "__main__":
    from pydantic import ValidationError

    MCQ_OK = {"question": "Quel élément régule les interactions ?", "choices": ["A. Un module", "Un connecteur",
              "Une vue", "Un acteur"], "answer": "b.", "explanation": "Le connecteur régule les interactions.", "page": 24}
    POINTS_OK = ["Le composant encapsule une fonctionnalité", "Le connecteur régule les interactions",
                 "Les deux forment la structure", "Exemple : appel de procédure"]

    tests = [
        ("QCM valide", MCQQuestion, MCQ_OK, True),
        ("QCM affirmation (sans ?)", MCQQuestion,
         {**MCQ_OK, "question": "Selon le cours, l'architecture implique une prévision réaliste."}, False),
        ("QCM « combien »", MCQQuestion,
         {**MCQ_OK, "question": "Un système logiciel comprend combien de types ?"}, False),
        ("QCM négatif", MCQQuestion,
         {**MCQ_OK, "question": "Quel type d'interaction ne sont pas fournies par les connecteurs ?"}, False),
        ("QCM « tous les »", MCQQuestion,
         {**MCQ_OK, "choices": ["Embarqués", "Mobiles", "Tous les systèmes", "Aucun"]}, False),
        ("Vrai/Faux en minuscule", TrueFalseQuestion,
         {"statement": "l'architecture a un impact sur la conception du système.", "answer": True,
          "correction": "Le cours la présente comme un facteur d'impact sur la conception.", "page": 18}, True),
        ("Vrai/Faux avec liste", TrueFalseQuestion,
         {"statement": "Une bonne architecture doit considérer : l'ergonomie et la maintenance.", "answer": False,
          "correction": "Le cours cite d'autres aspects.", "page": 5}, False),
        ("Réponse courte oui/non", ShortAnswerQuestion,
         {"question": "L'architecture doit-elle considérer les changements futurs ?",
          "expected_answer": "Oui, car elle est clairvoyante.", "page": 31}, False),
        ("Question ouverte valide", OpenQuestion,
         {"question": "Expliquez la différence entre composant et connecteur, avec un exemple.",
          "expected_points": POINTS_OK, "page": 23}, True),
        ("Question ouverte double", OpenQuestion,
         {"question": "Comment l'architecture influence-t-elle le design ? Quelles sont ses composantes ?",
                   "expected_points": POINTS_OK, "page": 16}, False),
                ("Question ouverte qui se répète", OpenQuestion,
         {"question": "Comment un système embarqué comme un ADSL modem illustre-t-il une approche utilisateur centrée et une bonne architecture logicielle ?",
          "expected_points": ["Une approche utilisateur centrée", "Une bonne architecture logicielle",
                              "Un système embarqué comme un ADSL modem", "Un exemple de système embarqué"], "page": 5}, False),
        ("Question ouverte en anglais", OpenQuestion,
         {"question": "Expliquez la différence entre composant et connecteur, avec un exemple.",
          "expected_points": ["The set of significant decisions about the organization", *POINTS_OK[1:]], "page": 16}, False),
    ]
    ok = 0
    for name, model, item, should_pass in tests:
        try:
            model.model_validate(item)
            result, msg = True, "acceptée"
        except ValidationError as e:
            result, msg = False, f"rejetée : {e.errors()[0]['msg']}"
        good = result == should_pass
        ok += good
        print(f"{'✅' if good else '🔴 ERREUR'} {name} → {msg}")
    print(f"\n{ok}/{len(tests)} tests conformes")