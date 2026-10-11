import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Numéros de 8 à 14 chiffres, avec indicatif optionnel et séparateurs espace, point ou tiret
PHONE = re.compile(r"(?<!\d)(?:\+\d{1,3}[ .-]?)?\d(?:[ .-]?\d){7,13}(?!\d)")


def mask_pii(text: str) -> str:
    """Remplace les emails et numéros (téléphone, CIN…) par des marqueurs neutres."""
    text = EMAIL.sub("[EMAIL]", text)
    text = PHONE.sub("[NUMÉRO]", text)
    return text


if __name__ == "__main__":
    samples = [
        "Contact : ali.najjaa@esprit.tn ou +216 22 345 678",
        "CIN 12345678, téléphone 22.345.678",
        "Syrine Karoui - 2023/2024 - page 14",
        "LeNet-5 a été créé en 1998, les Transformers en 2017.",
    ]
    for s in samples:
        print(f"{s}\n  → {mask_pii(s)}\n")