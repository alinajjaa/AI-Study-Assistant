from typing import Literal
import re
from pydantic import BaseModel, Field, field_validator, model_validator

from app.phase4_exam.schemas import WORD, YES_NO, capitalize_first, check_french

CardCount = Literal[10, 20, 30]

PAGE_IN_TEXT = re.compile(r"\b(page|p\.)\s*\d+", re.IGNORECASE)
# Une flashcard affirme : une réponse qui hésite est une réponse devinée
HEDGING = re.compile(
    r"\b(probablement|peut-être|sans doute|il semble|pourrait être"
    r"|pas (directement )?abordée?s?|n'est pas mentionnée?|le cours ne)\b",
    re.IGNORECASE,
)# ---------------------------------------------------------------------------
# Étape 1 : concepts clés du cours
# ---------------------------------------------------------------------------

class Concept(BaseModel):
    """Un concept important du cours (ex. « Connecteur », « Développement natif »)."""

    name: str = Field(min_length=2, max_length=80)
    importance: Literal[1, 2, 3]   # 3 = notion centrale du cours, 1 = détail

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return capitalize_first(value.strip(" .:-•"))


class ConceptBatch(BaseModel):
    items: list[Concept] = Field(min_length=1, max_length=5)


# ---------------------------------------------------------------------------
# Étape 2 : une carte par concept
# ---------------------------------------------------------------------------

class Flashcard(BaseModel):
    """Recto : une question courte. Verso : la réponse, tirée du cours."""

    concept: str = Field(min_length=2, max_length=80)
    front: str = Field(min_length=8, max_length=150)
    back: str = Field(min_length=5, max_length=250)   # une flashcard se lit en quelques secondes
    page: int = Field(ge=1)

    @field_validator("front")
    @classmethod
    def clean_front(cls, value: str) -> str:
        value = capitalize_first(value)
        if not value.endswith("?"):
            raise ValueError("le recto doit être une question")
        if value.count("?") > 1:
            raise ValueError("deux questions sur le recto")
        return value

    @field_validator("back")
    @classmethod
    def clean_back(cls, value: str) -> str:
        if YES_NO.match(value):
            raise ValueError("réponse oui/non")
        if PAGE_IN_TEXT.search(value):
            raise ValueError("numéro de page dans la réponse")
        if HEDGING.search(value):
            raise ValueError("réponse incertaine (devinée)")
        if not value.rstrip().endswith((".", "!", ")", "»")):
            raise ValueError("réponse coupée")
        return check_french(value)

    @model_validator(mode="after")
    def back_not_in_front(self):
        """Le verso doit apporter une information : il ne répète pas simplement le recto."""
        front_words = {w.lower() for w in WORD.findall(self.front)}
        back_words = {w.lower() for w in WORD.findall(self.back)}
        if back_words and len(back_words - front_words) < 2:
            raise ValueError("le verso répète le recto")
        return self


class FlashcardBatch(BaseModel):
    items: list[Flashcard] = Field(min_length=1, max_length=1)


class FlashcardDeck(BaseModel):
    """Paquet de cartes renvoyé au frontend (JSON)."""

    course: str
    cards: list[Flashcard]


class FlashcardRequest(BaseModel):
    count: CardCount = 10


if __name__ == "__main__":
    from pydantic import ValidationError

    tests = [
        ("Carte valide", {"concept": "Connecteur", "front": "Quel est le rôle d'un connecteur ?",
                          "back": "Il effectue et régule les interactions entre les composants.", "page": 24}, True),
        ("Recto sans ?", {"concept": "Connecteur", "front": "Le rôle d'un connecteur",
                          "back": "Il régule les interactions entre les composants.", "page": 24}, False),
        ("Verso oui/non", {"concept": "Flutter", "front": "Flutter est-il multiplateforme ?",
                           "back": "Oui, il fonctionne sur Android et iOS.", "page": 2}, False),
        ("Verso en anglais", {"concept": "Composant", "front": "Qu'est-ce qu'un composant ?",
                              "back": "A building block that encapsulates a subset of the functionality of the system.",
                              "page": 23}, False),
        ("Verso qui répète", {"concept": "Composant", "front": "Qu'est-ce qu'un composant logiciel ?",
                              "back": "Un composant logiciel.", "page": 23}, False),
    ]
    ok = 0
    for name, item, should_pass in tests:
        try:
            Flashcard.model_validate(item)
            result, msg = True, "acceptée"
        except ValidationError as e:
            result, msg = False, f"rejetée : {e.errors()[0]['msg']}"
        good = result == should_pass
        ok += good
        print(f"{'✅' if good else '🔴 ERREUR'} {name} → {msg}")
    print(f"\n{ok}/{len(tests)} tests conformes")