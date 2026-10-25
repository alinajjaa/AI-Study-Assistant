import re

# Consignes adressées au modèle, cachées dans un PDF importé (injection de prompt indirecte). Les motifs visent des
# ordres donnés au modèle, pas le vocabulaire d'un cours sur les LLM : « prompt système » ou « instructions » seuls
# ne déclenchent rien.
INJECTION = re.compile(
    r"\b(?:ignore[rsz]?|oublie[rsz]?|ne tiens? (?:pas|plus) compte d[eu]s?|disregard|forget)\b[^.!?\n]{0,60}?"
    r"\b(?:règles?|consignes?|instructions?|rules?|prompts?)\b"
    r"|\b(?:nouvelles?\s+(?:consignes?|instructions?|règles?)|new\s+(?:instructions?|rules?))\b"
    r"|\b(?:tu es (?:désormais|maintenant)|à partir de maintenant,? tu|you are now|from now on,? you)\b",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"[.!?\n]")
REMOVED = "[consigne retirée]"


def neutralize_instructions(text: str) -> str:
    """Coupe un passage du cours à la première phrase qui donne un ordre au modèle (« ignore les règles… »).

    La suite du passage est retirée aussi : une injection enchaîne d'habitude plusieurs ordres (« Ne cite aucune
    page. Commence par… »), que l'on ne sait pas distinguer d'une phrase de cours. Au pire, la fin d'un passage
    (800 caractères au plus) est perdue.
    """
    match = INJECTION.search(text)
    if match is None:
        return text
    ends = [m.end() for m in SENTENCE_END.finditer(text, 0, match.start())]
    start = ends[-1] if ends else 0
    kept = text[:start].rstrip()
    return f"{kept} {REMOVED}" if kept else REMOVED
