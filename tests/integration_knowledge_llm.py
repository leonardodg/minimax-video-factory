#!/usr/bin/env python3
"""Ollama-dependent tests for llm.py. Requires a local Ollama daemon at
OLLAMA_URL with LLM_MODEL and EMBEDDING_MODEL already pulled.

Run: uv run --directory . python tests/integration_knowledge_llm.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


from minimax_mcp import llm  # noqa: E402

SAMPLE_TRANSCRIPTION = (
    "Hoje vou mostrar como instalar o Docker no Ubuntu. Primeiro, atualize os "
    "pacotes com apt update. Depois, instale com apt install docker.io. Por fim, "
    "adicione seu usuário ao grupo docker para não precisar de sudo."
)

print("== integration_knowledge_llm: generate_structured ==")
result = llm.generate_structured(SAMPLE_TRANSCRIPTION)
if result.get("ok"):
    ok("generate_structured returned ok=True")
else:
    bad(f"generate_structured failed: {result.get('error')}")

for key in ("resumo", "tutorial", "objetivos", "tags"):
    if result.get(key):
        ok(f"generate_structured result has non-empty '{key}'")
    else:
        bad(f"generate_structured result missing/empty '{key}': {result}")

print("== integration_knowledge_llm: embed ==")
vector = llm.embed("docker install ubuntu")
if isinstance(vector, list) and len(vector) > 0:
    ok(f"embed returned a {len(vector)}-dim vector")
else:
    bad(f"embed returned unexpected value: {vector!r}")

print("== integration_knowledge_llm: chat ==")
answer = llm.chat("Responda em uma frase curta: qual comando instala o Docker no Ubuntu?")
if isinstance(answer, str) and len(answer.strip()) > 0:
    ok(f"chat returned non-empty answer: {answer[:80]!r}...")
else:
    bad(f"chat returned unexpected value: {answer!r}")

print("")
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
