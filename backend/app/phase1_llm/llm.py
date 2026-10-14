from openai import (
    OpenAI, APIConnectionError, APITimeoutError,
    AuthenticationError, RateLimitError, APIStatusError,
)
from app.core.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT
from app.phase5_evaluation.stats import record


class LLMError(Exception):
    """Erreur d'appel au LLM, avec un message lisible par l'utilisateur."""


client = OpenAI(
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY or "missing",
    timeout=LLM_TIMEOUT,
    max_retries=1,
)


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
    json_schema force en plus la réponse à respecter exactement ce schéma (sorties structurées).
    """
    if not LLM_API_KEY:
        raise LLMError("Clé API du LLM absente : renseigne LLM_API_KEY dans le fichier .env.")

    if json_schema:
        extra = {"response_format": {
            "type": "json_schema",
            "json_schema": {"name": "reponse", "schema": json_schema},
        }}
    elif json_mode:
        extra = {"response_format": {"type": "json_object"}}
    else:
        extra = {}

    record("appels_llm")  # mesure (phase 5) : sans collecteur actif, aucun effet
    try:
        out = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            **extra,
        )
    except APITimeoutError as e:  # à intercepter AVANT APIConnectionError, dont il hérite
        raise LLMError(f"Le modèle n'a pas répondu en {int(LLM_TIMEOUT)} s (timeout). Réessaie.") from e
    except APIConnectionError as e:
        raise LLMError("Impossible de joindre le serveur du LLM. Vérifie qu'Ollama est lancé.") from e
    except AuthenticationError as e:
        raise LLMError("Clé API du LLM invalide.") from e
    except RateLimitError as e:
        raise LLMError("Quota du fournisseur LLM atteint. Réessaie plus tard.") from e
    except APIStatusError as e:
        raise LLMError(f"Le fournisseur LLM a renvoyé une erreur (code {e.status_code}).") from e

    content = out.choices[0].message.content
    if not content or not content.strip():
        raise LLMError("Le modèle a renvoyé une réponse vide. Réessaie.")
    return content


if __name__ == "__main__":
    import json

    raw = chat(
        "Tu réponds uniquement en JSON.",
        'Donne une capitale africaine au format {"pays": "...", "capitale": "..."}',
        max_tokens=100,
        json_mode=True,
    )
    print("Réponse brute :", raw)
    print("JSON valide   :", json.loads(raw))