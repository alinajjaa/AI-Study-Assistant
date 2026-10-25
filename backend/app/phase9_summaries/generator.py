"""Résumés de cours : tout le cours (map-reduce) ou un thème (recherche sémantique + explication).

Le tuteur RAG ne lit que 3 passages : ici, le mode « course » lit TOUT le cours, section par section.
Toujours en français, uniquement à partir du cours, données personnelles masquées dans tous les prompts.
"""
import json
import logging

from pydantic import BaseModel, ValidationError

from app.core.passages import format_course
from app.core.privacy import mask_pii
from app.phase1_llm.llm import chat
from app.phase2_embeddings.embeddings import embed_query
from app.phase2_embeddings.vectorstore import get_course_chunks, search
from app.phase3_rag.rag import LEVEL_INSTRUCTIONS
from app.phase5_evaluation.stats import GenerationStats, collecting, record, record_value, reject
from app.phase9_summaries.schemas import (
    OverviewDraft, SectionDraft, SummaryContent, SummarySection, TopicDraft, bullet_has_valid_pages, page_refs,
)

logger = logging.getLogger("uvicorn.error")

MIN_PASSAGE_CHARS = 60   # en dessous : titre ou bout de découpage, sans contenu à résumer
SECTION_SIZE = 6         # passages consécutifs résumés ensemble
TOPIC_PASSAGES = 6       # passages retrouvés pour expliquer un thème
ATTEMPTS = 2             # une deuxième chance si la sortie est rejetée

SYSTEM_PROMPT = (
    "Tu es un enseignant qui rédige des fiches de révision en français, uniquement à partir du cours fourni. "
    "Tu réponds UNIQUEMENT avec un objet JSON valide et compact, sans aucun texte autour."
)

COMMON_RULES = """- Rédige TOUT en français, même si le cours est en anglais (traduis-le).
- N'utilise que ce que dit le cours ci-dessus : n'invente rien, aucune connaissance extérieure.
- Ignore les noms de personnes, les dates de cours, les logos et les informations administratives.
- Chaque puce est une phrase complète qui se termine par la page d'où vient l'information, sous la forme [p.X],
  avec X parmi : {pages}."""


def course_sections(chunks: list[dict]) -> list[list[dict]]:
    """Passages utiles (60 caractères ou plus), regroupés par 6 dans l'ordre du cours."""
    useful = [c for c in chunks if len(c["text"]) >= MIN_PASSAGE_CHARS]
    return [useful[i:i + SECTION_SIZE] for i in range(0, len(useful), SECTION_SIZE)]


def _count_bullets(raw: str, allowed: set[int]) -> None:
    """Mesure : puces proposées par le LLM et puces dont toutes les pages citées sont valides."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    groups = [data] if isinstance(data, dict) and "bullets" in data else \
        (data.get("parts", []) if isinstance(data, dict) else [])
    for group in groups:
        for bullet in group.get("bullets", []) if isinstance(group, dict) else []:
            if isinstance(bullet, str):
                record("puces_proposees")
                if bullet_has_valid_pages(bullet, allowed):
                    record("puces_page_valide")


def ask_structured(model: type[BaseModel], prompt: str, max_tokens: int, pages: set[int] | None = None,
                   what: str = "résumé") -> BaseModel | None:
    """Appelle le LLM avec le schéma JSON du modèle ; réessaie une fois si la sortie est rejetée.

    Renvoie None après deux rejets. LLMError remonte (→ 503).
    """
    for attempt in range(ATTEMPTS):
        record("appels_generation")
        raw = chat(SYSTEM_PROMPT, prompt, max_tokens=max_tokens, temperature=0.3 + 0.2 * attempt,
                   json_schema=model.model_json_schema())
        if pages is not None:
            _count_bullets(raw, pages)
        try:
            return model.model_validate_json(raw, context={"pages": pages})
        except ValidationError as e:
            logger.info("%s rejeté (tentative %d) : %s", what, attempt + 1, e.errors()[0]["msg"])
            reject("validation")
    return None


# ---------------------------------------------------------------------------
# Mode « course » : map-reduce sur tout le cours
# ---------------------------------------------------------------------------

def summarize_section(context: list[dict], used_titles: list[str] | None = None) -> SectionDraft | None:
    pages = sorted({c["page"] for c in context})
    avoid = ""
    if used_titles:
        avoid = f"\n- Le titre doit être différent de ceux des parties précédentes : {' ; '.join(used_titles)}."
    prompt = mask_pii(f"""Cours (chaque passage commence par sa page) :
{format_course(context)}

Résume cette partie du cours pour un étudiant qui révise.
- "title" : un titre court (3 à 8 mots) qui dit de quoi parle cette partie.{avoid}
- "bullets" : 3 à 5 puces avec les idées essentielles, dans l'ordre du cours.
{COMMON_RULES.format(pages=", ".join(map(str, pages)))}

Format attendu :
{{"title":"...","bullets":["... [p.{pages[0]}]","...","..."]}}""")
    return ask_structured(SectionDraft, prompt, max_tokens=600, pages=set(pages), what="Section")


def write_overview(sections: list[SummarySection]) -> str:
    """Vue d'ensemble de 4 à 6 phrases à partir des résumés de sections (étape « reduce »)."""
    plan = "\n\n".join(f"{s.title} :\n" + "\n".join(f"- {b}" for b in s.bullets) for s in sections)
    prompt = mask_pii(f"""Résumés des parties d'un cours, dans l'ordre :
{plan}

Rédige une vue d'ensemble du cours entier en 4 à 6 phrases, en français : le sujet du cours, les grandes
notions et la façon dont elles s'enchaînent. N'utilise que les résumés ci-dessus, n'invente rien.

Format attendu :
{{"overview":"..."}}""")
    draft = ask_structured(OverviewDraft, prompt, max_tokens=500, what="Vue d'ensemble")
    if draft is None:
        # Repli sans invention : la liste des parties du cours
        record("vue_ensemble_de_secours")
        return "Ce cours aborde les parties suivantes : " + " ; ".join(s.title for s in sections) + "."
    return draft.overview


def summarize_course(course: str, user_id: int | None) -> SummaryContent:
    chunks = get_course_chunks(course, user_id)
    groups = course_sections(chunks)
    if not groups:
        raise LookupError(f"Le cours « {course} » est introuvable ou vide.")
    record_value("passages", sum(len(g) for g in groups))

    sections: list[SummarySection] = []
    for context in groups:
        draft = summarize_section(context, [s.title for s in sections])
        if draft is None:
            logger.warning("Section ignorée (pages %s) : résumé rejeté deux fois",
                           sorted({c["page"] for c in context}))
            continue
        cited = sorted({p for b in draft.bullets for p in page_refs(b)})
        sections.append(SummarySection(title=draft.title, pages=cited, bullets=draft.bullets))
    if not sections:
        raise ValueError("Le modèle n'a produit aucun résumé valide. Réessaie.")
    return SummaryContent(overview=write_overview(sections), sections=sections)


# ---------------------------------------------------------------------------
# Mode « topic » : recherche sémantique + explication adaptée au niveau
# ---------------------------------------------------------------------------

def not_found(course: str) -> SummaryContent:
    return SummaryContent(found=False, sections=[],
                          overview=f"Ce thème n'est pas abordé dans le cours « {course} ».")


def explain_topic(course: str, topic: str, user_id: int | None, level: str | None = None) -> SummaryContent:
    # On cherche plus large pour garder 6 passages utiles après avoir écarté les titres trop courts
    hits = search(embed_query(topic), TOPIC_PASSAGES * 2, course, user_id=user_id)
    hits = [h for h in hits if len(h["text"]) >= MIN_PASSAGE_CHARS][:TOPIC_PASSAGES]
    if not hits:
        raise LookupError(f"Le cours « {course} » est introuvable ou vide.")
    record_value("passages", len(hits))
    context = sorted(hits, key=lambda h: h["page"])
    pages = sorted({c["page"] for c in context})
    level_rule = f"\n- Adapte l'explication au niveau de l'étudiant. {LEVEL_INSTRUCTIONS[level]}" \
        if level in LEVEL_INSTRUCTIONS else ""
    prompt = mask_pii(f"""Cours (chaque passage commence par sa page) :
{format_course(context)}

Thème demandé par l'étudiant : « {topic} »

Si les passages ci-dessus ne parlent PAS de ce thème, réponds exactement {{"found":false}}.
Sinon, explique ce thème de façon structurée :
- "found" : true.
- "introduction" : 1 à 2 phrases qui présentent le thème.
- "parts" : 1 à 4 parties, chacune avec un titre court et 2 à 5 puces.{level_rule}
{COMMON_RULES.format(pages=", ".join(map(str, pages)))}

Format attendu :
{{"found":true,"introduction":"...","parts":[{{"title":"...","bullets":["... [p.{pages[0]}]","..."]}}]}}""")
    draft = ask_structured(TopicDraft, prompt, max_tokens=900, pages=set(pages), what="Explication")
    if draft is None:
        raise ValueError("Le modèle n'a pas produit d'explication valide. Réessaie.")
    if not draft.found:
        record_value("theme_trouve", 0)
        return not_found(course)
    record_value("theme_trouve", 1)
    sections = [SummarySection(title=p.title, bullets=p.bullets,
                               pages=sorted({n for b in p.bullets for n in page_refs(b)})) for p in draft.parts]
    return SummaryContent(overview=draft.introduction.strip(), sections=sections)


def generate_summary(course: str, mode: str, topic: str | None = None, user_id: int | None = None,
                     level: str | None = None, stats: GenerationStats | None = None) -> SummaryContent:
    """Point d'entrée : résumé du cours entier (mode « course ») ou explication d'un thème (« topic »)."""
    with collecting(stats):
        content = summarize_course(course, user_id) if mode == "course" \
            else explain_topic(course, topic or "", user_id, level)
        record_value("sections", len(content.sections))
        record_value("puces", sum(len(s.bullets) for s in content.sections))
        return content
