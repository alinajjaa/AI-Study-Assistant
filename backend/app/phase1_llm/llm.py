import logging
import re
import time

from openai import (
    OpenAI, APIConnectionError, APITimeoutError,
    AuthenticationError, BadRequestError, RateLimitError, APIStatusError,
)
from app.core import config
from app.core.concurrency import llm_slot
from app.core.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT
from app.phase5_evaluation.stats import record, record_value

logger = logging.getLogger("uvicorn.error")


class LLMError(Exception):
    """Erreur d'appel au LLM, avec un message lisible par l'utilisateur."""


client = OpenAI(
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY or "missing",
    timeout=LLM_TIMEOUT,
    max_retries=1,
)

# Modèles qui refusent response_format json_schema : repli json_object mémorisé (une seule erreur par modèle)
_json_object_only: set[str] = set()

# « Please try again in 7.5s », « in 2m3.5s », « in 1h2m » (message des erreurs 429 de Groq)
_TRY_AGAIN = re.compile(r"try again in\s+(?:(\d+)h)?\s*(?:(\d+)m(?!s))?\s*(?:([\d.]+)s)?", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Limites de débit (429)
# ---------------------------------------------------------------------------

def _wait(seconds: float) -> None:
    time.sleep(seconds)


def retry_after(error: RateLimitError) -> float | None:
    """Attente demandée par le fournisseur (en-têtes retry-after, ou texte « try again in … »), en secondes."""
    headers = error.response.headers if getattr(error, "response", None) is not None else {}
    try:
        if headers.get("retry-after-ms"):
            return float(headers["retry-after-ms"]) / 1000
        if headers.get("retry-after"):
            return float(headers["retry-after"])
    except ValueError:
        pass
    match = _TRY_AGAIN.search(str(error))
    if match and any(match.groups()):
        hours, minutes, seconds = (float(g) if g else 0.0 for g in match.groups())
        return hours * 3600 + minutes * 60 + seconds
    return None


def is_daily_limit(error: RateLimitError) -> bool:
    text = str(error).lower()
    return "per day" in text or "(tpd)" in text or "(rpd)" in text


def rate_limit_message(error: RateLimitError, wait: float | None = None) -> str:
    """Message clair quand la limite de débit persiste (ou qu'il faudrait attendre trop longtemps)."""
    later = f" Réessaie dans {max(1, round(wait / 60))} min" if wait and wait > 60 else " Réessaie plus tard"
    if is_daily_limit(error):
        return (f"Limite quotidienne du fournisseur LLM atteinte (offre gratuite).{later}, "
                "ou choisis un autre modèle (LLM_MODEL).")
    return f"Limite de débit du fournisseur LLM atteinte (trop de requêtes ou de jetons par minute).{later}."


def ollama_options() -> dict:
    """Paramètres propres à Ollama (keep_alive : le modèle reste chargé en mémoire GPU entre deux appels)."""
    if config.IS_OLLAMA and config.LLM_KEEP_ALIVE:
        value = config.LLM_KEEP_ALIVE
        return {"extra_body": {"keep_alive": int(value) if value.lstrip("-").isdigit() else value}}
    return {}


def _create(**kwargs):
    """Appel au LLM (LLM_CONCURRENCY appels simultanés au plus) ; sur une erreur 429, attend le délai demandé
    puis réessaie (LLM_RATE_LIMIT_RETRIES fois). L'attente se fait hors du sémaphore : les autres appels continuent."""
    retries = max(0, config.LLM_RATE_LIMIT_RETRIES)
    for attempt in range(retries + 1):
        try:
            with llm_slot():
                return client.chat.completions.create(**kwargs, **ollama_options())
        except RateLimitError as e:
            wait = retry_after(e)
            if wait is None:
                wait = min(2.0 * 2 ** attempt, config.LLM_RATE_LIMIT_MAX_WAIT)  # 2, 4, 8, 16… s
            if attempt >= retries or wait > config.LLM_RATE_LIMIT_MAX_WAIT:
                raise LLMError(rate_limit_message(e, wait)) from e
            record("attentes_limite_debit")
            logger.warning("Limite de débit du LLM : nouvel essai dans %.1f s (%d/%d)", wait, attempt + 1, retries)
            _wait(wait + 0.5)


# ---------------------------------------------------------------------------
# Sorties structurées : json_schema, avec repli json_object
# ---------------------------------------------------------------------------

def _schema_unsupported(error: BadRequestError) -> bool:
    """Le modèle ou le fournisseur ne prend pas en charge response_format json_schema."""
    text = str(error).lower()
    return ("json_schema" in text or "response_format" in text) and any(
        word in text for word in ("not support", "unsupported", "does not support", "invalid value", "not available"))


def _json_generation_failed(error: BadRequestError) -> bool:
    """Groq : le modèle n'a pas réussi à produire un JSON conforme au schéma (code json_validate_failed)."""
    text = f"{getattr(error, 'code', '') or ''} {error}".lower()
    return "json_validate_failed" in text or "failed to validate json" in text or "failed to generate json" in text


def _response_format(json_mode: bool, json_schema: dict | None) -> tuple[dict, bool]:
    """(paramètres response_format, json_schema utilisé ?) selon LLM_JSON_MODE et les replis déjà mémorisés."""
    if json_schema and config.LLM_JSON_MODE != "json_object" and LLM_MODEL not in _json_object_only:
        return {"response_format": {"type": "json_schema",
                                    "json_schema": {"name": "reponse", "schema": json_schema}}}, True
    if json_schema or json_mode:
        return {"response_format": {"type": "json_object"}}, False
    return {}, False


def chat(
    system: str,
    user: str,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    json_mode: bool = False,
    json_schema: dict | None = None,
) -> str:
    """Envoie un message au LLM et renvoie sa réponse, ou lève LLMError.

    json_mode=True force une réponse en JSON valide.
    json_schema force en plus la réponse à respecter exactement ce schéma (sorties structurées). Si le modèle
    refuse json_schema, ou échoue à produire un JSON conforme (Groq : json_validate_failed), on réessaie en
    json_object : le JSON est alors validé par les modèles Pydantic des appelants, comme toujours.
    Erreur 429 (limite de débit) : attente puis nouvel essai, message clair si la limite persiste.
    LLM_PROVIDER=hf-local (désactivé par défaut) : le texte libre (réponses du tuteur) est écrit par le modèle
    affiné local ; les demandes JSON restent sur le LLM configuré (l'adaptateur n'a appris que le style du tuteur).
    """
    if config.LLM_PROVIDER == "hf-local" and not (json_mode or json_schema):
        from app.phase4_finetuning.hf_local import generate

        record("appels_llm")
        return generate(system, user, max_tokens=max_tokens, temperature=temperature)

    if not LLM_API_KEY:
        raise LLMError("Clé API du LLM absente : renseigne LLM_API_KEY dans le fichier .env.")

    request = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    extra, with_schema = _response_format(json_mode, json_schema)

    record("appels_llm")  # mesure (phase 5) : sans collecteur actif, aucun effet
    try:
        try:
            out = _create(**request, **extra)
        except BadRequestError as e:
            if not with_schema or not (_schema_unsupported(e) or _json_generation_failed(e)):
                raise
            if _schema_unsupported(e):
                _json_object_only.add(LLM_MODEL)
                logger.warning("%s refuse json_schema : repli sur json_object pour la suite", LLM_MODEL)
            record("replis_json_object")
            out = _create(**request, response_format={"type": "json_object"})
    except LLMError:
        raise
    except APITimeoutError as e:  # à intercepter AVANT APIConnectionError, dont il hérite
        raise LLMError(f"Le modèle n'a pas répondu en {int(LLM_TIMEOUT)} s (timeout). Réessaie.") from e
    except APIConnectionError as e:
        raise LLMError("Impossible de joindre le serveur du LLM. Vérifie qu'Ollama est lancé.") from e
    except AuthenticationError as e:
        raise LLMError("Clé API du LLM invalide.") from e
    except RateLimitError as e:
        raise LLMError(rate_limit_message(e)) from e
    except APIStatusError as e:
        if isinstance(e, BadRequestError) and _json_generation_failed(e):
            raise LLMError("Le modèle n'a pas produit de JSON valide. Réessaie.") from e
        raise LLMError(f"Le fournisseur LLM a renvoyé une erreur (code {e.status_code}).") from e

    content = out.choices[0].message.content
    if not content or not content.strip():
        raise LLMError("Le modèle a renvoyé une réponse vide. Réessaie.")
    return content


def chat_stream(system: str, user: str, on_token, max_tokens: int = 1024, temperature: float = 0.3) -> str:
    """Comme chat() en texte libre, mais transmet la réponse au fur et à mesure : on_token(fragment).

    Renvoie le texte complet (validé ensuite par l'appelant, comme une réponse de chat()). Mesure le délai avant
    le premier fragment (time_to_first_token, en secondes) dans le collecteur actif (phase 5). Mêmes erreurs
    que chat() (LLMError), même retry 429 (avant le début du flux). LLM_PROVIDER=hf-local : pas de flux, le
    texte complet est transmis en une fois.
    """
    if config.LLM_PROVIDER == "hf-local":
        text = chat(system, user, max_tokens=max_tokens, temperature=temperature)
        on_token(text)
        return text
    if not LLM_API_KEY:
        raise LLMError("Clé API du LLM absente : renseigne LLM_API_KEY dans le fichier .env.")

    record("appels_llm")
    start = time.perf_counter()
    parts: list[str] = []
    try:
        stream = _create(model=LLM_MODEL, messages=[{"role": "system", "content": system},
                                                    {"role": "user", "content": user}],
                         max_tokens=max_tokens, temperature=temperature, stream=True)
        with llm_slot():  # le flux occupe le LLM jusqu'au dernier fragment
            for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if not delta:
                    continue
                if not parts:
                    ttft = round(time.perf_counter() - start, 3)
                    record_value("time_to_first_token", ttft)
                    logger.info("Premier fragment du LLM après %.2f s", ttft)
                parts.append(delta)
                on_token(delta)
    except LLMError:
        raise
    except APITimeoutError as e:
        raise LLMError(f"Le modèle n'a pas répondu en {int(LLM_TIMEOUT)} s (timeout). Réessaie.") from e
    except APIConnectionError as e:
        raise LLMError("Impossible de joindre le serveur du LLM. Vérifie qu'Ollama est lancé.") from e
    except AuthenticationError as e:
        raise LLMError("Clé API du LLM invalide.") from e
    except RateLimitError as e:
        raise LLMError(rate_limit_message(e)) from e
    except APIStatusError as e:
        raise LLMError(f"Le fournisseur LLM a renvoyé une erreur (code {e.status_code}).") from e

    text = "".join(parts)
    if not text.strip():
        raise LLMError("Le modèle a renvoyé une réponse vide. Réessaie.")
    return text


if __name__ == "__main__":
    import json

    raw = chat(
        "Tu réponds UNIQUEMENT avec un objet JSON valide.",
        'Donne une capitale africaine au format {"pays": "...", "capitale": "..."}',
        max_tokens=100,
        json_mode=True,
    )
    print("Réponse brute :", raw)
    print("JSON valide   :", json.loads(raw))
