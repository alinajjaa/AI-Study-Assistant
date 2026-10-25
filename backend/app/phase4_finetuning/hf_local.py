"""Fournisseur LLM_PROVIDER=hf-local (optionnel, désactivé par défaut) : le modèle affiné dans l'application.

Charge le modèle de base (HF_BASE_MODEL) quantifié en 4 bits + l'adaptateur LoRA (HF_ADAPTER, dépôt du Hub
ou dossier local) avec transformers et peft. En 4 bits, Qwen2.5-1.5B tient dans environ 1,5 Go de VRAM :
compatible avec une RTX 4050 de 6 Go.

Activation (dans backend/.env), après avoir installé requirements-finetuning.txt :
    LLM_PROVIDER=hf-local
    HF_ADAPTER=<HF_USERNAME>/study-tutor-qwen2.5-1.5b-lora

Seules les réponses en texte libre (tuteur, explications) passent par ce modèle ; les demandes JSON
(examens, flashcards, résumés, agent) restent sur le LLM configuré (Ollama).

Test rapide : python -m app.phase4_finetuning.hf_local
"""
import logging
import threading

from app.core import config
from app.phase1_llm.llm import LLMError

logger = logging.getLogger("uvicorn.error")

_lock = threading.Lock()  # un seul modèle en mémoire, une génération à la fois (GPU partagé)
_model = None
_tokenizer = None


def load():
    """Charge le modèle une seule fois (premier appel), puis le garde en mémoire."""
    global _model, _tokenizer
    if _model is not None:
        return _model, _tokenizer
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except ImportError as e:
        raise LLMError("LLM_PROVIDER=hf-local : installe requirements-finetuning.txt "
                       f"(module manquant : {e.name}).") from e
    if not config.HF_ADAPTER:
        raise LLMError("LLM_PROVIDER=hf-local : renseigne HF_ADAPTER (dépôt du Hub ou dossier de l'adaptateur).")

    cuda = torch.cuda.is_available()
    quantization = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    ) if cuda else None  # sans GPU : bitsandbytes indisponible, modèle chargé en float32 sur le CPU (lent)
    logger.info("hf-local : chargement de %s + %s (%s)", config.HF_BASE_MODEL, config.HF_ADAPTER,
                "4 bits, GPU" if cuda else "CPU")
    try:
        tokenizer = AutoTokenizer.from_pretrained(config.HF_BASE_MODEL, revision=config.HF_BASE_REVISION,
                                                  token=config.HF_TOKEN)
        base = AutoModelForCausalLM.from_pretrained(
            config.HF_BASE_MODEL, quantization_config=quantization, device_map="auto" if cuda else None,
            dtype=torch.float16 if cuda else torch.float32, revision=config.HF_BASE_REVISION, token=config.HF_TOKEN,
        )
        model = PeftModel.from_pretrained(base, config.HF_ADAPTER, revision=config.HF_ADAPTER_REVISION,
                                          token=config.HF_TOKEN)
    except Exception as e:  # noqa: BLE001 — réseau, dépôt introuvable, mémoire insuffisante…
        raise LLMError(f"Chargement du modèle affiné impossible : {type(e).__name__}.") from e
    model.eval()
    _model, _tokenizer = model, tokenizer
    return _model, _tokenizer


def generate(system: str, user: str, max_tokens: int = 1024, temperature: float = 0.3) -> str:
    """Même contrat que phase1_llm.chat (texte libre) : la réponse, ou LLMError."""
    import torch

    with _lock:
        model, tokenizer = load()
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt",
                                               return_dict=True).to(model.device)
        sampling = {"do_sample": True, "temperature": temperature, "top_p": 0.9} if temperature > 0 \
            else {"do_sample": False}
        try:
            with torch.inference_mode():
                output = model.generate(**inputs, max_new_tokens=max_tokens, repetition_penalty=1.05,
                                        pad_token_id=tokenizer.eos_token_id, **sampling)
        except torch.cuda.OutOfMemoryError as e:
            raise LLMError("Mémoire GPU insuffisante pour le modèle affiné.") from e
    text = tokenizer.decode(output[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    if not text:
        raise LLMError("Le modèle a renvoyé une réponse vide. Réessaie.")
    return text


if __name__ == "__main__":
    from app.phase3_rag.rag import build_system_prompt, build_user_prompt

    passage = {"page": 3, "text": "Le pooling réduit la taille des cartes d'activation produites par les "
                                  "couches de convolution et rend le réseau plus robuste aux petites translations."}
    for level in ("debutant", "avance"):
        print(f"--- {level} ---")
        print(generate(build_system_prompt(level=level), build_user_prompt([passage], "À quoi sert le pooling ?")))
