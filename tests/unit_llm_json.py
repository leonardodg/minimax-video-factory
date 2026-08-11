#!/usr/bin/env python3
"""Resiliência do JSON: o documento não pode se perder por um sorteio ruim.

Duas falhas raras (~1-2% cada, medidas em 2026-08-10) descartavam o post
inteiro -- transcrição, leitura de tela e minutos de GPU já pagos:

  "Expecting ',' delimiter"                 JSON malformado
  "missing keys: {'tags', 'objetivos'}"     JSON válido, faltando as DUAS
                                            ÚLTIMAS chaves do formato
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FAIL = 0


def ok(label): print(f"  [ok]   {label}")


def bad(label):
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


from minimax_mcp import llm

COMPLETO = '{"resumo":"r","tutorial":"t","objetivos":["o"],"tags":["a"]}'


def com_respostas(*respostas):
    """Troca o gerador do ollama por uma fila de respostas fixas."""
    fila = list(respostas)
    chamadas = []

    def falso(prompt, model, *, force_json=False):
        chamadas.append(prompt)
        return fila.pop(0) if fila else fila[-1]

    return falso, chamadas


print("== unit_llm_json: repetir salva o documento ==")
_real = llm._ollama_generate
try:
    llm._ollama_generate, chamadas = com_respostas("{isto nao e json", COMPLETO)
    r = llm.generate_structured("material")
    if r.get("ok") and len(chamadas) == 2:
        ok("JSON inválido na 1ª tentativa, válido na 2ª -> documento sai")
    else:
        bad(f"não repetiu: {r!r} chamadas={len(chamadas)}")

    llm._ollama_generate, chamadas = com_respostas("{quebrado", "{quebrado de novo")
    r = llm.generate_structured("material")
    if not r.get("ok") and "JSON inválido" in r.get("error", "") and len(chamadas) == 2:
        ok("inválido nas duas -> falha clara, com a resposta bruta anexada")
    else:
        bad(f"deveria falhar após 2 tentativas: {r!r}")

    print("== unit_llm_json: enriquecimento ausente não descarta o post ==")

    # O erro real observado: o modelo fecha um JSON válido sem as duas últimas
    # chaves. Um documento sem tags é muito melhor que documento nenhum.
    llm._ollama_generate, chamadas = com_respostas('{"resumo":"r","tutorial":"t"}')
    r = llm.generate_structured("material")
    if r.get("ok") and r.get("objetivos") == [] and r.get("tags") == [] and len(chamadas) == 1:
        ok("sem objetivos/tags -> segue com vazio, sem repetir a geração")
    else:
        bad(f"descartou por falta de enriquecimento: {r!r}")

    llm._ollama_generate, _ = com_respostas('{"resumo":"r"}')
    r = llm.generate_structured("material")
    if r.get("ok") and r.get("tutorial") == "":
        ok("só com resumo ainda produz documento")
    else:
        bad(f"resumo sozinho deveria bastar: {r!r}")

    print("== unit_llm_json: sem resumo não há documento ==")

    # `resumo` é o único campo sem o qual o documento não significa nada.
    for resposta in ('{"tutorial":"t","tags":["a"]}', '{"resumo":"   "}'):
        llm._ollama_generate, _ = com_respostas(resposta)
        r = llm.generate_structured("material")
        if not r.get("ok") and "resumo" in r.get("error", ""):
            ok(f"sem resumo utilizável -> falha ({resposta[:28]}...)")
        else:
            bad(f"deveria falhar sem resumo: {r!r}")
finally:
    llm._ollama_generate = _real

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
