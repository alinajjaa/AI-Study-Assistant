from openai import OpenAI
from app.core.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)


def chat(system: str, user: str, max_tokens: int = 1024, temperature: float = 0.3) -> str:
    """Envoie un message au LLM (Ollama, Groq ou Hugging Face) et renvoie sa réponse."""
    out = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return out.choices[0].message.content


if __name__ == "__main__":
    print(chat("Tu es un tuteur pédagogue.", "Explique l'overfitting en 3 phrases."))