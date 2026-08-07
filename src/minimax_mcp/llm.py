"""Abstract LLM client for the knowledge base: Ollama (default) or OpenAI-compatible."""
from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")
LLM_MODEL = os.environ.get("LLM_MODEL", "lfm2:24b")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "mxbai-embed-large")
EMBEDDING_DIM_HINT = int(os.environ.get("EMBEDDING_DIM", "1024"))
OPENAI_API_URL = os.environ.get("OPENAI_API_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "900.0"))
EMBED_TIMEOUT = float(os.environ.get("EMBED_TIMEOUT", "120.0"))

SUMMARY_PROMPT_TEMPLATE = """\
Você é um assistente que documenta conteúdo para uma base de conhecimento pessoal.

Dada a transcrição abaixo, responda APENAS com um JSON válido (sem markdown, sem texto \
fora do JSON) com estas chaves:
- "resumo": um resumo conciso (3-5 frases) do conteúdo.
- "tutorial": um tutorial detalhado, passo a passo, do que foi ensinado/demonstrado, em markdown.
- "objetivos": uma lista de objetivos/aprendizados principais (array de strings).
- "tags": uma lista de 3 a 8 tags curtas relevantes (array de strings).

Transcrição:
{transcription}
"""


def build_summary_prompt(transcription: str) -> str:
    return SUMMARY_PROMPT_TEMPLATE.format(transcription=transcription.strip())


def parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse a JSON object out of an LLM response, tolerating ```json fences."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _ollama_generate(prompt: str, model: str, *, force_json: bool) -> str:
    payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
    if force_json:
        payload["format"] = "json"
    resp = httpx.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=LLM_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["response"]


def _openai_compatible_generate(prompt: str, model: str, *, force_json: bool) -> str:
    if not OPENAI_API_URL:
        raise RuntimeError("OPENAI_API_URL not configured")
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"} if OPENAI_API_KEY else {}
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if force_json:
        body["response_format"] = {"type": "json_object"}
    resp = httpx.post(f"{OPENAI_API_URL}/chat/completions", headers=headers, json=body, timeout=LLM_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def generate_structured(
    transcription: str, *, provider: str | None = None, model: str | None = None
) -> dict[str, Any]:
    """Ask the configured LLM for {resumo, tutorial, objetivos, tags} as JSON."""
    provider = provider or LLM_PROVIDER
    model = model or LLM_MODEL
    prompt = build_summary_prompt(transcription)
    try:
        if provider == "ollama":
            raw = _ollama_generate(prompt, model, force_json=True)
        elif provider == "openai-compatible":
            raw = _openai_compatible_generate(prompt, model, force_json=True)
        else:
            return {"ok": False, "error": f"Unknown LLM_PROVIDER: {provider}"}

        parsed = parse_llm_json(raw)
        required = {"resumo", "tutorial", "objetivos", "tags"}
        missing = required - parsed.keys()
        if missing:
            return {"ok": False, "error": f"LLM response missing keys: {missing}", "raw": raw}
        return {"ok": True, "provider": provider, "model": model, **parsed}
    except Exception as e:
        return {"ok": False, "error": f"LLM generation failed: {e}"}


def embed(text: str, *, model: str | None = None) -> list[float]:
    """Generate an embedding via Ollama. Always local, independent of LLM_PROVIDER."""
    model = model or EMBEDDING_MODEL
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings", json={"model": model, "prompt": text}, timeout=EMBED_TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def chat(prompt: str, *, provider: str | None = None, model: str | None = None) -> str:
    """Free-text completion (no forced JSON) — used for RAG answers."""
    provider = provider or LLM_PROVIDER
    model = model or LLM_MODEL
    if provider == "ollama":
        return _ollama_generate(prompt, model, force_json=False)
    if provider == "openai-compatible":
        return _openai_compatible_generate(prompt, model, force_json=False)
    raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}")
