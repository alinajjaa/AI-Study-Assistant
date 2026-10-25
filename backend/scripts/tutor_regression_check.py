"""Contrôle de non-régression du tuteur RAG avec le vrai modèle, sans MLflow ni écriture en base.

Usage : python scripts/tutor_regression_check.py <user_id> <cours> <sortie.csv>

Rejoue le jeu app/phase5_evaluation/datasets/<cours>.json (questions du cours avec leur page attendue, et
questions hors cours avec expected_page = null) avec answer() : mêmes prompts, même recherche Qdrant (lecture
seule), même LLM que l'application. Mesures : hit@3, réponse trouvée, refus hors cours, citations [p.X].
Sert à comparer deux versions du prompt (avant / après un correctif).
"""
import csv
import json
import re
import sys
import time

from app.phase3_rag.rag import answer

CITATION = re.compile(r"\[p\.\d+\]")

user_id, course, out = int(sys.argv[1]), sys.argv[2], sys.argv[3]
with open(f"app/phase5_evaluation/datasets/{course}.json", encoding="utf-8") as f:
    dataset = json.load(f)

rows = []
for item in dataset:
    t0 = time.perf_counter()
    result = answer(item["question"], course, user_id=user_id)
    expected = item.get("expected_page")
    pages = {s["page"] for s in result["sources"]}
    rows.append({
        "question": item["question"][:80], "page_attendue": expected,
        "hit_3": int(expected in pages) if expected is not None else "",
        "reponse_trouvee": int(result["answered"]) if expected is not None else "",
        "refus_correct": int(not result["answered"]) if expected is None else "",
        "citation": int(bool(CITATION.search(result["answer"]))) if expected is not None else "",
        "duree_s": round(time.perf_counter() - t0, 2),
    })
    print(rows[-1], flush=True)


def mean(key: str) -> float:
    values = [r[key] for r in rows if r[key] != ""]
    return round(sum(values) / len(values), 3) if values else float("nan")


with open(out, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
print({k: mean(k) for k in ("hit_3", "reponse_trouvee", "refus_correct", "citation", "duree_s")})
