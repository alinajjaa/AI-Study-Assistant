"""Agent LangGraph du Study Companion.

    agent ──(appels d'outil valides)──────────────► tools ──► agent … ──► finalize
      │                                               ▲
      └─(aucun appel, ou appels tous invalides)──► classify ──(outil choisi)──┘
                                                      └─(« aucun » : salutation, question sur l'app)──► finalize

- agent : le LLM (compatible OpenAI : Ollama aujourd'hui, Groq demain) choisit un outil par tool calling ;
- classify : repli si le modèle n'appelle aucun outil ou appelle un outil invalide — classification
  d'intention en sortie structurée (json_schema), puis exécution de l'outil choisi ;
- tools : exécute les appels (3 au maximum par message, doublons ignorés) ;
- agent (2e passage) : réponse finale courte en français, adaptée au niveau, ou un autre outil ;
- finalize : texte final. Une réponse du tuteur RAG (avec ses [p.X]) n'est jamais reformulée.

Garde-fou : une demande de résumé du cours entier (« résume les idées principales de ce cours ») routée vers
ask_course par le modèle est corrigée en summarize (le tuteur RAG ne lit que quelques passages du cours).

Confidentialité : le LLM ne reçoit que des textes passés par mask_pii (message, historique) ; jamais l'email
ni le nom de l'étudiant (le contexte AgentContext reste côté serveur, dans la fermeture du graphe).
"""
import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Annotated, Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, RateLimitError
from pydantic import BaseModel, ValidationError

from app.core import config
from app.core.privacy import mask_pii
from app.phase1_llm.llm import LLMError, chat, rate_limit_message
from app.phase3_rag.rag import LEVEL_INSTRUCTIONS
from app.phase6_agent.tools import AgentContext, _normalize, openai_tools, run_tool, validate_call

logger = logging.getLogger("uvicorn.error")

MAX_TOOL_CALLS = 3
HISTORY_MESSAGES = 6  # 3 derniers échanges donnés à l'agent pour comprendre « et fais-en un quiz »
HISTORY_CHARS = 300
RECURSION_LIMIT = 15  # garde-fou LangGraph (agent ↔ tools)

DEFAULT_REPLY = ("Je suis ton assistant d'étude : je peux répondre à une question sur ton cours, le résumer, "
                 "te faire un quiz, préparer des flashcards ou te montrer tes progrès. Que veux-tu faire ?")

SYSTEM_PROMPT = """Tu es « Study Companion », l'assistant d'étude d'un étudiant. Tu réponds toujours en français.
Tu disposes d'outils ; choisis celui qui correspond à la demande :
- ask_course : question précise sur le contenu d'un cours (définition, explication, comparaison, exemple).
- summarize : résumé d'un cours entier (sans topic) — aussi « idées principales », « points clés », « l'essentiel »,
  « synthèse » ou « récapitulatif » du cours —, ou explication structurée d'un thème (topic).
- generate_quiz : quiz QCM pour s'entraîner ou se tester (count 5 ou 10, difficulty facile, moyen ou difficile).
- generate_flashcards : paquet de flashcards (cartes de révision).
- get_progress : progrès, statistiques, niveau, points faibles de l'étudiant.
Règles :
- Salutation, remerciement ou question sur l'application elle-même : réponds directement en une ou deux phrases,
  sans outil.
- Toute demande sur le contenu d'un cours passe par un outil : n'invente jamais de contenu de cours.
- Au plus 3 outils par message.
- N'indique un cours (course) que si l'étudiant le nomme ; sinon laisse-le vide.
- Tutoie l'étudiant. N'utilise jamais son nom, son email ou une autre information personnelle.
{courses}
{level}"""

AFTER_TOOLS_RULE = """
Les outils ont été exécutés et leur résultat est affiché à l'étudiant (quiz, résumé, flashcards, progression).
Écris maintenant ta réponse finale : 1 à 3 phrases courtes et chaleureuses, en tutoyant l'étudiant, adaptées
à son niveau, qui présentent ce qui a été préparé. Ne recopie pas le contenu et n'invente rien. N'appelle un autre
outil que si la demande de l'étudiant n'est pas encore satisfaite."""


def system_prompt(ctx: AgentContext, after_tools: bool) -> str:
    names = ", ".join(f"« {mask_pii(c)} »" for c in ctx.courses) or "aucun (l'étudiant doit d'abord importer un PDF)"
    selected = (f"\nCours sélectionné dans la page : « {mask_pii(ctx.selected_course)} »." if ctx.selected_course
                else "\nAucun cours sélectionné dans la page.")
    level = f"Niveau de l'étudiant : {LEVEL_INSTRUCTIONS[ctx.level]}" if ctx.level in LEVEL_INSTRUCTIONS else ""
    prompt = SYSTEM_PROMPT.format(courses=f"Cours de l'étudiant : {names}.{selected}", level=level)
    return prompt + AFTER_TOOLS_RULE if after_tools else prompt


# ---------------------------------------------------------------------------
# Repli : classification d'intention en sortie structurée
# ---------------------------------------------------------------------------

class IntentDecision(BaseModel):
    outil: Literal["ask_course", "summarize", "generate_quiz", "generate_flashcards", "get_progress", "aucun"]
    cours: str | None = None
    theme: str | None = None
    nombre: int | None = None
    difficulte: Literal["facile", "moyen", "difficile"] | None = None

    def tool_args(self) -> dict:
        if self.outil == "ask_course":
            return {"course": self.cours}
        if self.outil == "summarize":
            return {"course": self.cours, "topic": self.theme}
        if self.outil == "generate_quiz":
            return {"course": self.cours, "count": self.nombre or 5, "difficulty": self.difficulte or "moyen"}
        if self.outil == "generate_flashcards":
            return {"course": self.cours, "count": self.nombre or 10}
        return {}


CLASSIFY_SYSTEM = ("Tu classes la demande d'un étudiant pour choisir l'outil de son assistant d'étude. "
                   "Tu réponds UNIQUEMENT avec un objet JSON valide.")
CLASSIFY_PROMPT = """Outils possibles :
- ask_course : question précise sur le contenu d'un cours (définition, explication, exemple, comparaison).
- summarize : résumé d'un cours entier (idées principales, points clés, essentiel, synthèse, récapitulatif du cours),
  ou explication structurée d'un thème (theme).
- generate_quiz : quiz, QCM, s'entraîner, se tester (nombre 5 ou 10, difficulte facile, moyen ou difficile).
- generate_flashcards : flashcards, fiches ou cartes de révision.
- get_progress : progrès, statistiques, niveau, points faibles.
- aucun : salutation, remerciement, question sur l'application elle-même.
Cours de l'étudiant : {courses}
{previous}Demande de l'étudiant : « {message} »

Format attendu : {{"outil":"...","cours":null,"theme":null,"nombre":null,"difficulte":null}}
(« cours » seulement si l'étudiant nomme un de ses cours.)"""


def classify_intent(ctx: AgentContext) -> IntentDecision:
    """Outil choisi par classification ; « aucun » si le LLM échoue (le message reçoit alors l'aide par défaut)."""
    last_user = next((h["content"] for h in reversed(ctx.history) if h["role"] == "user"), None)
    previous = f"Demande précédente : « {mask_pii(last_user[:HISTORY_CHARS])} »\n" if last_user else ""
    prompt = CLASSIFY_PROMPT.format(courses=", ".join(ctx.courses) or "aucun", previous=previous,
                                    message=ctx.message)
    try:
        raw = chat(CLASSIFY_SYSTEM, mask_pii(prompt), max_tokens=150, temperature=0,
                   json_schema=IntentDecision.model_json_schema())
        return IntentDecision.model_validate_json(raw)
    except ValidationError as e:
        logger.warning("Classification d'intention invalide : %s", e.errors()[0]["msg"])
        return IntentDecision(outil="aucun")


# ---------------------------------------------------------------------------
# Garde-fou : résumé du cours entier
# ---------------------------------------------------------------------------

# Sur le texte normalisé (minuscules, sans accents ni ponctuation) : « résume les idées principales de ce cours »,
# « points clés du cours », « l'essentiel de ce chapitre », « synthèse des notions essentielles du cours »…
# Entre le mot-clé et le cours, seuls des mots de liaison : « l'essentiel du pooling dans ce cours » n'en est pas un.
_SUMMARY_WORD = (r"(?:resum\w*|synthese|synthetise\w*|recapitul\w*|recap|idees? principales?|grandes? idees?"
                 r"|points? (?:cles?|principaux|essentiels?)|essentiel|notions? (?:essentielles?|principales?|cles?))")
_FILLER = (r"(?:moi|me|un|une|les|des|de|d|la|l|du|notions?|idees?|points?|principales?|principaux|essentiel(?:le)?s?"
           r"|cles?|grandes?|importantes?|complete?s?|general|global)")
COURSE_SUMMARY = re.compile(
    rf"\b{_SUMMARY_WORD}(?: {_FILLER})*? (?:du|de ce|de cette|de mon|de tout le|le|ce|cette|tout le|l) "
    r"(?:cours|chapitre|module|support)\b(?! sur )")  # « le chapitre sur le pooling » : un thème, pas tout le cours


def is_course_summary_request(message: str) -> bool:
    return COURSE_SUMMARY.search(_normalize(message)) is not None


def reroute_course_summary(reply: AnyMessage, message: str) -> AnyMessage:
    """ask_course choisi pour une demande de résumé du cours entier → summarize (même cours, sans thème)."""
    if not isinstance(reply, AIMessage) or not any(c["name"] == "ask_course" for c in reply.tool_calls):
        return reply
    if not is_course_summary_request(message):
        return reply
    calls = [{**c, "name": "summarize", "args": {"course": (c.get("args") or {}).get("course"), "topic": None}}
             if c["name"] == "ask_course" else c for c in reply.tool_calls]
    return reply.model_copy(update={"tool_calls": calls})


# ---------------------------------------------------------------------------
# Graphe
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    tool_calls: int  # outils exécutés pour ce message
    executed: list[str]  # empreintes (nom + arguments) des appels déjà exécutés
    outcomes: list[dict]  # ToolOutcome (dict) dans l'ordre d'exécution, avec le nom de l'outil
    fallback: bool  # le repli par classification a été utilisé
    stalled: bool  # le dernier passage dans tools n'a rien exécuté de nouveau
    stop: bool  # question « quel cours ? » ou échec : on s'arrête là
    final_text: str
    dry_run: bool  # évaluation : arrêt juste après le choix de l'outil


def valid_calls(message: AnyMessage) -> list[dict]:
    if not isinstance(message, AIMessage):
        return []
    return [c for c in message.tool_calls if validate_call(c["name"], c.get("args")) is not None]


def _as_llm_error(e: Exception) -> LLMError:
    """Mêmes messages que phase1_llm.chat pour les erreurs du client OpenAI utilisé par LangChain."""
    if isinstance(e, APITimeoutError):
        return LLMError(f"Le modèle n'a pas répondu en {int(config.LLM_TIMEOUT)} s (timeout). Réessaie.")
    if isinstance(e, APIConnectionError):
        return LLMError("Impossible de joindre le serveur du LLM. Vérifie qu'Ollama est lancé.")
    if isinstance(e, AuthenticationError):
        return LLMError("Clé API du LLM invalide.")
    if isinstance(e, RateLimitError):
        return LLMError(rate_limit_message(e))
    if isinstance(e, APIStatusError):
        return LLMError(f"Le fournisseur LLM a renvoyé une erreur (code {e.status_code}).")
    return LLMError(f"Erreur du LLM : {type(e).__name__}.")


# Début de liste : « 1. », « 2) » (1 ou 2 chiffres, pas une année) ou puce en début de ligne
LIST_START = re.compile(r"(?:^|\s)\d{1,2}[.)]\s|^\s*[-*•]\s", re.MULTILINE)
SENTENCE = re.compile(r"[^.!?…]+[.!?…]+")
FINAL_SENTENCES = 3
FINAL_CHARS = 350


def short_reply(text: str) -> str:
    """Réponse finale courte : coupée avant toute liste (le modèle recopie ou invente parfois les questions
    du quiz), au plus 3 phrases. Le contenu lui-même est affiché par la carte du quiz, du résumé…"""
    text = text.strip()
    match = LIST_START.search(text)
    if match:
        text = text[:match.start()].rstrip(" :,\n")
        if text and text[-1] not in ".!?…":
            text += "."
    sentences = SENTENCE.findall(text)
    if sentences:
        text = "".join(sentences[:FINAL_SENTENCES]).strip()
    if len(text) > FINAL_CHARS:
        text = text[:FINAL_CHARS].rsplit(" ", 1)[0] + "…"
    return text if len(text) >= 10 else ""


def _looks_like_tool_json(text: str) -> bool:
    """Certains modèles écrivent l'appel d'outil dans le texte au lieu d'un vrai tool call."""
    stripped = text.strip()
    return stripped.startswith(("{", "[", "```")) or "<tool_call>" in stripped or '"arguments"' in stripped


def build_graph(llm: BaseChatModel, ctx: AgentContext):
    """Graphe compilé pour un message. ctx reste dans la fermeture : il n'apparaît ni dans l'état ni dans les traces."""
    llm_with_tools = llm.bind_tools(openai_tools())

    def agent(state: AgentState) -> dict:
        after_tools = state.get("tool_calls", 0) > 0
        prompt = [SystemMessage(system_prompt(ctx, after_tools)), *state["messages"]]
        try:
            reply = llm_with_tools.invoke(prompt)
        except LLMError:
            raise
        except Exception as e:  # erreurs du client OpenAI → message clair (503)
            raise _as_llm_error(e) from e
        if not after_tools:
            reply = reroute_course_summary(reply, ctx.message)
        return {"messages": [reply]}

    def route_after_agent(state: AgentState) -> str:
        last = state["messages"][-1]
        if valid_calls(last):
            return END if state.get("dry_run") else "tools"
        if state.get("tool_calls", 0) == 0 and not state.get("fallback"):
            return "classify"
        return "finalize"

    def classify(state: AgentState) -> dict:
        decision = classify_intent(ctx)
        last = state["messages"][-1]
        messages: list = []
        if isinstance(last, AIMessage) and last.tool_calls:
            messages.append(RemoveMessage(id=last.id))  # appels invalides : retirés de la conversation
        if decision.outil != "aucun":
            call = {"name": decision.outil, "args": decision.tool_args(), "id": f"repli_{uuid.uuid4().hex[:8]}",
                    "type": "tool_call"}
            messages.append(reroute_course_summary(AIMessage(content="", tool_calls=[call]), ctx.message))
        return {"messages": messages, "fallback": True}

    def route_after_classify(state: AgentState) -> str:
        if valid_calls(state["messages"][-1]):
            return END if state.get("dry_run") else "tools"
        return "finalize"

    def tools(state: AgentState) -> dict:
        call_message = state["messages"][-1]
        done = state.get("tool_calls", 0)
        executed = list(state.get("executed", []))
        outcomes = list(state.get("outcomes", []))
        stop, ran = False, False
        replies = []
        for call in call_message.tool_calls:
            args = validate_call(call["name"], call.get("args"))
            # Empreinte (nom + arguments) : l'état, donc les traces, ne contient pas la question en clair
            signature = hashlib.sha256(json.dumps([call["name"], args], sort_keys=True).encode()).hexdigest()[:16]
            if args is None:
                reply = "Outil inconnu ou arguments invalides : appel ignoré."
            elif stop:
                reply = "Non exécuté : une précision de l'étudiant est nécessaire."
            elif done >= MAX_TOOL_CALLS:
                reply = f"Non exécuté : {MAX_TOOL_CALLS} appels d'outil au maximum par message."
            elif signature in executed:
                reply = "Déjà exécuté pour ce message."
            else:
                outcome = run_tool(ctx, call["name"], args)
                done, ran = done + 1, True
                executed.append(signature)
                outcomes.append({"tool": call["name"], **asdict(outcome)})
                reply = outcome.llm_summary
                stop = outcome.final and not outcome.ok  # « quel cours ? » ou échec : rien d'autre à faire
            replies.append(ToolMessage(content=reply, tool_call_id=call["id"], name=call["name"]))
        return {"messages": replies, "tool_calls": done, "executed": executed, "outcomes": outcomes,
                "stop": state.get("stop", False) or stop, "stalled": not ran}

    def route_after_tools(state: AgentState) -> str:
        outcomes = state.get("outcomes", [])
        if state.get("stop") or state.get("stalled"):
            return "finalize"
        if outcomes and all(o["final"] for o in outcomes):
            return "finalize"  # réponse du tuteur RAG : déjà rédigée, avec ses sources
        return "agent"  # réponse finale courte (un nouvel appel au-delà de 3 outils sera refusé)

    def finalize(state: AgentState) -> dict:
        last = state["messages"][-1]
        text = ""
        if isinstance(last, AIMessage) and not last.tool_calls and isinstance(last.content, str):
            text = last.content.strip()
        if _looks_like_tool_json(text):
            text = ""
        if not state.get("outcomes"):
            return {"final_text": text or DEFAULT_REPLY}  # réponse directe (salutation, aide)
        text = short_reply(text)
        return {"final_text": text}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_node("classify", classify)
    graph.add_node("tools", tools)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, ["tools", "classify", "finalize", END])
    graph.add_conditional_edges("classify", route_after_classify, ["tools", "finalize", END])
    graph.add_conditional_edges("tools", route_after_tools, ["agent", "finalize"])
    graph.add_edge("finalize", END)
    return graph.compile()


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

@dataclass
class Reply:
    """Un message de l'assistant à enregistrer (Message.kind / content / payload / sources)."""

    kind: str
    content: str
    payload: dict | None = None
    sources: list = field(default_factory=list)
    answered: bool = True


@dataclass
class AgentResult:
    replies: list[Reply]
    tools: list[str]  # outils exécutés (ou seulement choisis, en dry_run)
    fallback: bool
    duration_s: float


_llm: BaseChatModel | None = None


def default_llm() -> BaseChatModel:
    """Client LangChain compatible OpenAI, configuré comme phase1_llm (LLM_BASE_URL / LLM_MODEL / LLM_API_KEY)."""
    global _llm
    if _llm is None:
        if not config.LLM_API_KEY:
            raise LLMError("Clé API du LLM absente : renseigne LLM_API_KEY dans le fichier .env.")
        from langchain_openai import ChatOpenAI

        # max_retries : le client OpenAI réessaie aussi les erreurs 429 (limite de débit) avec une attente
        _llm = ChatOpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, model=config.LLM_MODEL,
                          temperature=0, timeout=config.LLM_TIMEOUT,
                          max_retries=max(1, config.LLM_RATE_LIMIT_RETRIES))
    return _llm


def initial_messages(ctx: AgentContext) -> list[AnyMessage]:
    """Derniers échanges puis le message de l'étudiant, données personnelles masquées."""
    messages: list[AnyMessage] = []
    for h in ctx.history[-HISTORY_MESSAGES:]:
        content = mask_pii(h["content"][:HISTORY_CHARS])
        messages.append(HumanMessage(content) if h["role"] == "user" else AIMessage(content))
    messages.append(HumanMessage(mask_pii(ctx.message)))
    return messages


def run_agent(ctx: AgentContext, llm: BaseChatModel | None = None, dry_run: bool = False) -> AgentResult:
    """Traite un message de l'étudiant. dry_run : s'arrête après le choix de l'outil (évaluation)."""
    from app.phase6_agent.tracing import enable_tracing

    enable_tracing()
    start = time.perf_counter()
    graph = build_graph(llm or default_llm(), ctx)
    state = graph.invoke({"messages": initial_messages(ctx), "dry_run": dry_run},
                         {"recursion_limit": RECURSION_LIMIT, "run_name": "study_companion"})
    duration = time.perf_counter() - start
    fallback = state.get("fallback", False)

    if dry_run:
        return AgentResult(replies=[], tools=[c["name"] for c in valid_calls(state["messages"][-1])],
                           fallback=fallback, duration_s=duration)

    outcomes = state.get("outcomes", [])
    replies = [Reply(kind=o["kind"], content=o["content"], payload=o["payload"], sources=o["sources"],
                     answered=o["answered"]) for o in outcomes]
    final_text = state.get("final_text", "")
    if not replies:
        replies = [Reply(kind="text", content=final_text or DEFAULT_REPLY)]
    elif final_text and not outcomes[-1]["final"]:
        replies[-1].content = final_text  # réponse courte du LLM, adaptée au niveau
    return AgentResult(replies=replies, tools=[o["tool"] for o in outcomes], fallback=fallback,
                       duration_s=duration)
