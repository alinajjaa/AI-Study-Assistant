"""Tracing MLflow de l'agent (onglet « Traces » de l'expérience « agent ») sans donnée personnelle.

mlflow.langchain.autolog() trace le graphe LangGraph : un span par nœud (agent, classify, tools, finalize),
par appel au LLM et par appel d'outil, avec leurs entrées et sorties.

Choix de confidentialité (appliqué à chaque span avant son export, par redact_span) :
- le texte écrit par l'étudiant n'est JAMAIS enregistré : contenu des messages « human »/« user » (message
  actuel et historique) et arguments libres des outils (question, topic) → « [message de l'étudiant masqué] » ;
- le texte des réponses adressées à l'étudiant non plus (messages « ai »/« assistant », final_text, contenu des
  résultats d'outils) : remplacé par sa longueur. Raison : mask_pii ne reconnaît pas les noms, et le modèle
  peut répéter un prénom que l'étudiant a tapé (« Bonjour Ali ! »), constaté avec qwen2.5:7b ;
- tout autre texte passe par mask_pii (emails, numéros) ;
- restent visibles : prompts système (règles, niveau, noms des cours), outils choisis et leurs arguments
  non libres (cours, nombre, difficulté), comptes rendus des outils envoyés au LLM, contenu des quiz et
  résumés (issu du cours), routage entre les nœuds, durées, jetons.
  Le contexte de l'étudiant (identifiant, email) n'entre jamais dans le graphe : il reste dans la fermeture.
Le texte complet des échanges reste consultable par l'étudiant dans ses conversations (base de l'application).
"""
import json
import logging
import os

from app.core import config
from app.core.privacy import mask_pii

logger = logging.getLogger("uvicorn.error")

EXPERIMENT = "agent"
REDACTED = "[message de l'étudiant masqué]"
STUDENT_ROLES = {"human", "user"}
ASSISTANT_ROLES = {"ai", "assistant", "AIMessageChunk"}
FREE_TEXT_KEYS = {"question", "topic", "message", "theme"}
REPLY_KEYS = {"final_text"}
ARGS_KEYS = {"args", "arguments"}  # arguments d'un appel d'outil (dict LangChain ou chaîne JSON OpenAI)

_enabled_uri: str | None = None


def _reply_placeholder(text: str) -> str:
    return f"[réponse de l'assistant masquée : {len(text)} caractères]" if text else text


def _redact_args(value):
    """Arguments d'outil : les champs libres (question, topic…) viennent du message de l'étudiant."""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return mask_pii(value)
        return json.dumps(_redact_args(parsed), ensure_ascii=False) if isinstance(parsed, dict) else mask_pii(value)
    if isinstance(value, dict):
        return {k: REDACTED if k in FREE_TEXT_KEYS and isinstance(v, str) else redact(v) for k, v in value.items()}
    return redact(value)


def redact(value):
    """Copie de value sans le texte de l'étudiant ni celui des réponses ; le reste passe par mask_pii."""
    if isinstance(value, dict):
        role = value.get("role") or value.get("type")
        is_student = role in STUDENT_ROLES
        # Réponse à l'étudiant : message du modèle, ou résultat d'outil (ToolOutcome : kind + llm_summary)
        is_reply = role in ASSISTANT_ROLES or ("kind" in value and "llm_summary" in value)
        out = {}
        for key, item in value.items():
            if key == "content" and is_student:
                out[key] = REDACTED
            elif key in ARGS_KEYS:
                out[key] = _redact_args(item)
            elif (key == "content" and is_reply or key in REPLY_KEYS) and isinstance(item, str):
                out[key] = _reply_placeholder(item)
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return mask_pii(value)
    return value


def redact_span(span) -> None:
    """Processeur de spans MLflow : appliqué à chaque span avant son export."""
    if span.inputs is not None:
        span.set_inputs(redact(span.inputs))
    if span.outputs is not None:
        span.set_outputs(redact(span.outputs))


def enable_tracing() -> None:
    """Active (une fois par URI) l'autolog LangChain/LangGraph vers l'expérience « agent ».

    Sans effet si MLflow est désactivé ; ne lève jamais d'exception (l'agent doit fonctionner sans MLflow).
    """
    global _enabled_uri
    if not config.MLFLOW_ENABLED or _enabled_uri == config.MLFLOW_TRACKING_URI:
        return
    try:
        os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
        import mlflow

        from app.phase5_evaluation.tracking import _client

        _client()  # crée le dossier de la base SQLite si besoin
        mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
        mlflow.set_experiment(EXPERIMENT)
        mlflow.tracing.configure(span_processors=[redact_span])
        mlflow.langchain.autolog(silent=True)
        _enabled_uri = config.MLFLOW_TRACKING_URI
    except Exception as e:  # noqa: BLE001
        logger.warning("Tracing MLflow de l'agent indisponible : %s", e)


def disable_tracing() -> None:
    global _enabled_uri
    if _enabled_uri is None:
        return
    try:
        import mlflow

        mlflow.langchain.autolog(disable=True)
    except Exception:  # noqa: BLE001
        pass
    _enabled_uri = None
