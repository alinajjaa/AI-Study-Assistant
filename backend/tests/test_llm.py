"""Client LLM : repli json_schema → json_object, limites de débit (429), configuration Groq et Qdrant intégré."""
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from openai import BadRequestError, RateLimitError

from app.phase1_llm import llm
from app.phase5_evaluation.stats import GenerationStats, collecting

BACKEND = Path(__file__).resolve().parents[1]
SCHEMA = {"type": "object", "properties": {"answers": {"type": "array", "items": {"type": "boolean"}}}}


def reply(content: str = '{"answers":[true]}'):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def bad_request(message: str, code: str | None = None) -> BadRequestError:
    response = httpx.Response(400, request=httpx.Request("POST", "http://llm/chat/completions"))
    return BadRequestError(message, response=response, body={"message": message, "code": code})


def rate_limited(message: str = "Rate limit reached", headers: dict | None = None) -> RateLimitError:
    response = httpx.Response(429, headers=headers or {}, request=httpx.Request("POST", "http://llm/chat/completions"))
    return RateLimitError(message, response=response, body={"message": message})


class Scripted:
    """Remplace client.chat.completions.create : renvoie (ou lève) les éléments du script dans l'ordre."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


@pytest.fixture
def scripted(monkeypatch):
    def install(*steps) -> Scripted:
        fake = Scripted(*steps)
        monkeypatch.setattr(llm.client.chat.completions, "create", fake)
        return fake

    monkeypatch.setattr(llm, "_json_object_only", set())
    monkeypatch.setattr(llm.config, "LLM_JSON_MODE", "json_schema")
    return install


@pytest.fixture
def waits(monkeypatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(llm, "_wait", slept.append)
    return slept


def formats(fake: Scripted) -> list[str | None]:
    return [c.get("response_format", {}).get("type") for c in fake.calls]


# ---------------------------------------------------------------------------
# Sorties structurées
# ---------------------------------------------------------------------------

def test_json_schema_envoye_par_defaut(scripted):
    fake = scripted(reply())
    assert llm.chat("s", "u", json_schema=SCHEMA) == '{"answers":[true]}'
    assert formats(fake) == ["json_schema"]
    assert fake.calls[0]["response_format"]["json_schema"]["schema"] == SCHEMA


def test_repli_json_object_si_schema_refuse_et_memorise(scripted):
    fake = scripted(bad_request("response_format `json_schema` is not supported by this model"), reply(), reply())
    stats = GenerationStats()
    with collecting(stats):
        llm.chat("s", "u", json_schema=SCHEMA)
        llm.chat("s", "u", json_schema=SCHEMA)  # repli mémorisé : json_object directement
    assert formats(fake) == ["json_schema", "json_object", "json_object"]
    assert stats.get("replis_json_object") == 1
    assert stats.get("appels_llm") == 2


def test_repli_json_object_si_json_non_conforme_sans_memoriser(scripted):
    error = bad_request("Failed to validate JSON. Please adjust your prompt.", code="json_validate_failed")
    fake = scripted(error, reply(), reply())
    llm.chat("s", "u", json_schema=SCHEMA)
    llm.chat("s", "u", json_schema=SCHEMA)
    assert formats(fake) == ["json_schema", "json_object", "json_schema"]


def test_json_non_conforme_meme_en_json_object(scripted):
    error = bad_request("Failed to generate JSON.", code="json_validate_failed")
    scripted(error, error)
    with pytest.raises(llm.LLMError, match="JSON valide"):
        llm.chat("s", "u", json_schema=SCHEMA)


def test_autre_erreur_400_sans_repli(scripted):
    fake = scripted(bad_request("context length exceeded"))
    with pytest.raises(llm.LLMError, match="code 400"):
        llm.chat("s", "u", json_schema=SCHEMA)
    assert len(fake.calls) == 1


def test_mode_json_object_force(scripted, monkeypatch):
    monkeypatch.setattr(llm.config, "LLM_JSON_MODE", "json_object")
    fake = scripted(reply())
    llm.chat("s", "u", json_schema=SCHEMA)
    assert formats(fake) == ["json_object"]


def test_texte_libre_sans_response_format(scripted):
    fake = scripted(reply("Bonjour"))
    assert llm.chat("s", "u") == "Bonjour"
    assert "response_format" not in fake.calls[0]


# ---------------------------------------------------------------------------
# Limites de débit (429)
# ---------------------------------------------------------------------------

def test_429_attente_puis_succes(scripted, waits):
    fake = scripted(rate_limited(headers={"retry-after": "3"}), reply())
    stats = GenerationStats()
    with collecting(stats):
        assert llm.chat("s", "u", json_schema=SCHEMA)
    assert len(fake.calls) == 2
    assert waits == [3.5]
    assert stats.get("attentes_limite_debit") == 1


def test_429_delai_lu_dans_le_message(scripted, waits):
    scripted(rate_limited("Rate limit reached on tokens per minute (TPM). Please try again in 7.5s."), reply())
    llm.chat("s", "u")
    assert waits == [8.0]


@pytest.mark.parametrize("text, seconds", [("try again in 2m3.5s", 123.5), ("try again in 1h2m", 3720.0),
                                           ("try again in 12s", 12.0), ("aucun délai", None)])
def test_retry_after_depuis_le_texte(text, seconds):
    assert llm.retry_after(rate_limited(text)) == seconds


def test_429_persistant_message_clair(scripted, waits, monkeypatch):
    monkeypatch.setattr(llm.config, "LLM_RATE_LIMIT_RETRIES", 2)
    fake = scripted(*[rate_limited(headers={"retry-after": "1"})] * 3)
    with pytest.raises(llm.LLMError, match="Limite de débit"):
        llm.chat("s", "u")
    assert len(fake.calls) == 3
    assert len(waits) == 2


def test_429_limite_quotidienne_sans_attendre(scripted, waits):
    error = rate_limited("Rate limit reached on tokens per day (TPD): Limit 200000. Please try again in 23m10s.")
    fake = scripted(error)
    with pytest.raises(llm.LLMError, match="quotidienne.*23 min"):
        llm.chat("s", "u")
    assert len(fake.calls) == 1 and waits == []


def test_429_sans_delai_attente_progressive(scripted, waits):
    scripted(rate_limited(), rate_limited(), reply())
    llm.chat("s", "u")
    assert waits == [2.5, 4.5]


def test_agent_meme_message_de_limite():
    from app.phase6_agent.graph import _as_llm_error

    error = _as_llm_error(rate_limited("Rate limit reached on requests per day (RPD)"))
    assert "quotidienne" in str(error)


# ---------------------------------------------------------------------------
# Configuration (processus séparé : config est lue à l'import)
# ---------------------------------------------------------------------------

def _config(env: dict, expression: str) -> str:
    full_env = {**os.environ, **env}
    out = subprocess.run([sys.executable, "-c", f"from app.core import config; print({expression})"],
                         cwd=BACKEND, env=full_env, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_cle_groq_prioritaire_avec_url_groq():
    env = {"LLM_BASE_URL": "https://api.groq.com/openai/v1", "LLM_API_KEY": "ollama", "GROQ_API_KEY": "gsk_test"}
    assert _config(env, "config.LLM_API_KEY") == "gsk_test"


def test_cle_groq_ignoree_avec_ollama():
    env = {"LLM_BASE_URL": "http://localhost:11434/v1", "LLM_API_KEY": "ollama", "GROQ_API_KEY": "gsk_test"}
    assert _config(env, "config.LLM_API_KEY") == "ollama"


def test_cors_origins_configurables():
    env = {"CORS_ORIGINS": "http://localhost:8080, https://exemple.hf.space"}
    assert _config(env, "config.CORS_ORIGINS") == "['http://localhost:8080', 'https://exemple.hf.space']"


def test_qdrant_integre_en_memoire():
    env = {"QDRANT_PATH": ":memory:"}
    out = _config(env, "__import__('app.phase2_embeddings.vectorstore', fromlist=['client']).client._client.__class__.__name__")
    assert out == "QdrantLocal"
