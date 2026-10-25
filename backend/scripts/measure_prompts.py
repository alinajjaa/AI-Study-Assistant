"""Usage : python scripts/measure_prompts.py <modèle Ollama> <sortie.csv> <results_base.jsonl>

Mesure réelle (jetons, durée) de chaque type d'appel LLM du projet, avec les prompts du code.

Les fonctions `chat` des modules sont remplacées par un appel à l'API native d'Ollama (/api/chat),
qui renvoie prompt_eval_count, eval_count et les durées. Mêmes temperature, max_tokens et schémas JSON.
"""
import csv
import json
import sys
import time
from types import SimpleNamespace

import httpx

MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5-7b-gpu"
OUT = sys.argv[2]
DATA = sys.argv[3]  # results_base.jsonl : passages réels du cours (article public sur les CNN)

rows: list[dict] = []
label = "?"


def measured_chat(system, user, max_tokens=1024, temperature=0.3, json_mode=False, json_schema=None):
    body = {"model": MODEL, "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": temperature, "num_predict": max_tokens}}
    if json_schema:
        body["format"] = json_schema
    elif json_mode:
        body["format"] = "json"
    t0 = time.perf_counter()
    r = httpx.post("http://127.0.0.1:11434/api/chat", json=body, timeout=300).json()
    wall = time.perf_counter() - t0
    out = r["message"]["content"]
    rows.append({
        "appel": label, "modele": MODEL, "temperature": temperature, "max_tokens": max_tokens,
        "format": "json_schema" if json_schema else ("json" if json_mode else "texte"),
        "jetons_entree": r.get("prompt_eval_count", 0), "jetons_sortie": r.get("eval_count", 0),
        "tronque": r.get("done_reason") == "length",
        "duree_s": round(wall, 2),
        "debit_sortie_tok_s": round(r["eval_count"] / (r["eval_duration"] / 1e9), 1) if r.get("eval_duration") else "",
        "debut_sortie": out[:90].replace("\n", " "),
    })
    print(f"{label:28s} in={rows[-1]['jetons_entree']:5d} out={rows[-1]['jetons_sortie']:4d} "
          f"{wall:5.1f}s trunc={rows[-1]['tronque']}", flush=True)
    return out


from app.phase3_rag import rag  # noqa: E402
from app.phase4_exam import generator as exam  # noqa: E402
from app.phase7_flashcards import generator as fc  # noqa: E402
from app.phase9_summaries import generator as summ  # noqa: E402
from app.phase6_agent import graph, tools  # noqa: E402

for module in (rag, exam, fc, summ, graph, tools):
    module.chat = measured_chat

passages, seen = [], set()
with open(DATA, encoding="utf-8") as f:
    for line in f:
        user_msg = json.loads(line)["prompt"][1]["content"]
        block = user_msg.split("Extraits du cours :\n", 1)[1].split("\n\nQuestion de l'étudiant", 1)[0]
        page = int(block[3:block.index("]")])
        text = block[block.index("]") + 2:]
        if text[:50] not in seen:
            seen.add(text[:50])
            passages.append({"page": page, "text": text, "course": "CNN_intro", "score": 0.85})
passages.sort(key=lambda p: p["page"])
print(f"{len(passages)} passages distincts", flush=True)

# 1. Tuteur RAG (3 passages, niveau intermédiaire), puis question hors cours
hits = passages[:3]
label = "tuteur"
rag.chat(rag.build_system_prompt(level="intermediaire"),
         rag.build_user_prompt(hits, "À quoi sert la couche de pooling dans un CNN ?"))
label = "tuteur_suivi_historique"
history = [{"role": "user", "content": "À quoi sert la couche de pooling ?"},
           {"role": "assistant", "content": "Le pooling réduit la dimension spatiale des cartes [p.8]."}]
rag.chat(rag.build_system_prompt(has_history=True, level="debutant"),
         rag.build_user_prompt(hits, "et pour la convolution ?", history))
label = "tuteur_hors_cours"
rag.chat(rag.build_system_prompt(), rag.build_user_prompt(hits, "Qui a gagné la Coupe du monde 2018 ?"))

# 2. Examens : génération puis vérification, pour chaque type
for kind in ("qcm", "vrai_faux", "courte", "ouverte"):
    spec = exam.TYPE_SPECS[kind]
    context = exam.passage_window(passages, 2, spec.window)
    pages = sorted({c["page"] for c in context})
    label = f"examen_generation_{kind}"
    raw = exam.chat(exam.SYSTEM_PROMPT, exam.build_prompt(kind, context, "moyen", [], True),
                    max_tokens=spec.max_tokens, temperature=0.5, json_schema=spec.batch_model.model_json_schema())
    items = exam.parse_items(kind, raw, pages)[:1]
    if items:
        label = f"examen_verification_{kind}"
        exam.verify(kind, items, context)
    else:
        print(f"  ({kind} rejeté par la validation : pas de vérification)")

# 3. Flashcards : concepts, carte, vérification
label = "flashcards_concepts"
concepts, _ = fc.extract_concepts(passages[:3], count=1)
if concepts:
    label = "flashcards_carte"
    card = fc.make_card(concepts[0], passages[:2])
    if card:
        label = "flashcards_verification"
        fc.verify_card(card, passages[:2])

# 4. Résumés : section (map), vue d'ensemble (reduce), thème
label = "resume_section_map"
section = summ.summarize_section(passages[:6])
if section:
    from app.phase9_summaries.schemas import SummarySection
    label = "resume_vue_ensemble_reduce"
    summ.write_overview([SummarySection(title=section.title, pages=[p["page"] for p in passages[:6]],
                                        bullets=section.bullets)])

# 5. Agent : classification de repli, étiquetage des notions, choix d'outil (tool calling)
ctx = SimpleNamespace(courses=["CNN_intro"], selected_course="CNN_intro", level="intermediaire",
                      history=[], message="Fais-moi un quiz de 5 questions sur ce cours")
label = "agent_classification_repli"
graph.classify_intent(ctx)

label = "agent_choix_outil_tool_calling"
body = {"model": MODEL, "stream": False, "tools": tools.openai_tools(), "options": {"temperature": 0},
        "messages": [{"role": "system", "content": graph.system_prompt(ctx, after_tools=False)},
                     {"role": "user", "content": ctx.message}]}
t0 = time.perf_counter()
r = httpx.post("http://127.0.0.1:11434/api/chat", json=body, timeout=300).json()
calls = r["message"].get("tool_calls") or []
rows.append({"appel": label, "modele": MODEL, "temperature": 0, "max_tokens": "défaut", "format": "tool calling",
             "jetons_entree": r["prompt_eval_count"], "jetons_sortie": r["eval_count"], "tronque": False,
             "duree_s": round(time.perf_counter() - t0, 2),
             "debit_sortie_tok_s": round(r["eval_count"] / (r["eval_duration"] / 1e9), 1),
             "debut_sortie": json.dumps([c["function"] for c in calls], ensure_ascii=False)[:90]})
print(f"{label:28s} in={r['prompt_eval_count']} out={r['eval_count']} -> {rows[-1]['debut_sortie']}")

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
    w.writeheader()
    w.writerows(rows)
print("écrit :", OUT)
