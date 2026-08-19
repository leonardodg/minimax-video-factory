#!/usr/bin/env python3
"""Conteúdo cortado em silêncio -- os pontos onde o material sumia sem aviso.

Medido em 2026-08-19. O pior deles não estava no nosso código: o Ollama usa
`num_ctx=2048` por padrão, descarta pela FRENTE e devolve HTTP 200 como se nada
tivesse acontecido:

    enviados 7206 tokens, num_ctx padrão -> leu 2051
      pergunta: "qual é o MARCADOR-INICIO e qual é o MARCADOR-FIM?"
      resposta: "O marcador início é JABUTICABA e o fim é JABUTICABA"
                 (JABUTICABA era o do FIM)
    mesmos 7206 tokens, num_ctx=8192     -> leu 7768, acertou os dois

Como o molde do prompt vem no começo e o material no fim, o que se perdia num
documento longo eram as INSTRUÇÕES.

    uv run python tests/unit_cortes.py
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


from minimax_mcp import ig_sync, llm  # noqa: E402

print("== unit_cortes: num_ctx é declarado em toda chamada ao Ollama ==")

p = llm._ollama_payload("oi", "m", force_json=True)
if p["options"].get("num_ctx") == llm.LLM_NUM_CTX:
    ok(f"o resumo declara num_ctx={llm.LLM_NUM_CTX}, não o padrão 2048 do Ollama")
else:
    bad(f"options sem num_ctx: {p['options']!r} -- o Ollama corta em 2048 calado")

if llm.LLM_NUM_CTX >= 4096:
    ok("a janela do resumo cobre com folga o documento mediano")
else:
    bad(f"LLM_NUM_CTX={llm.LLM_NUM_CTX} é pequeno demais")

print("== unit_cortes: o corte é NOSSO, do material, e registrado ==")

molde = llm.build_summary_prompt("")
limite = llm.orcamento_de_material(num_ctx=8192, num_predict=3072, molde=molde)

if limite > 12000:
    ok(f"com num_ctx=8192 cabem {limite} caracteres de material")
else:
    bad(f"orçamento de só {limite} caracteres -- a conta está errada")

# O orçamento tem de DESCONTAR o molde e a resposta, senão o Ollama corta de novo.
apertado = llm.orcamento_de_material(num_ctx=2048, num_predict=3072, molde=molde)
if apertado == 0:
    ok("resposta maior que a janela -> orçamento zero, sem número negativo")
else:
    bad(f"orçamento {apertado} com num_predict > num_ctx")

curto, perdidos = llm.cortar_material("abc def", 1000)
if curto == "abc def" and perdidos == 0:
    ok("material que cabe passa intocado")
else:
    bad(f"mexeu em material que cabia: {curto!r}, perdidos={perdidos}")

texto = "palavra " * 500                       # 4000 caracteres
curto, perdidos = llm.cortar_material(texto, 1000)
if len(curto) <= 1000 and perdidos == len(texto) - len(curto):
    ok("material que não cabe é cortado, e a perda é devolvida para virar log")
else:
    bad(f"corte errado: ficou {len(curto)}, perdidos {perdidos}, de {len(texto)}")

if curto.endswith("palavra") and not curto.endswith("palav"):
    ok("corta na fronteira de palavra, não no meio de uma")
else:
    bad(f"cortou no meio da palavra: ...{curto[-12:]!r}")

# O começo é o que se preserva: o fim de uma transcrição costuma ser CTA e
# despedida, e é do começo que sai o assunto.
if curto == texto[:len(curto)]:
    ok("preserva o COMEÇO do material, que é onde está o assunto")
else:
    bad("o corte não preservou o começo")

# Texto sem espaço nenhum (base64, URL gigante) não pode virar string vazia.
solto, _ = llm.cortar_material("x" * 5000, 1000)
if len(solto) == 1000:
    ok("texto sem espaços é cortado no limite, não zerado")
else:
    bad(f"texto sem espaços virou {len(solto)} caracteres")

print("== unit_cortes: a visão também declara janela ==")

fontes = (ROOT / "src" / "minimax_mcp" / "llm.py").read_text(encoding="utf-8")
if fontes.count("VISION_NUM_CTX") >= 3:
    ok("describe_image e read_screen declaram num_ctx")
else:
    bad("alguma chamada de visão ficou sem num_ctx")

if '"num_predict": 512' not in fontes:
    ok("o teto de 512 tokens da leitura de tela saiu")
else:
    bad("ainda há num_predict=512 -- um print denso para no meio")

print("== unit_cortes: a legenda INTEIRA viaja na mensagem ==")


class User:
    username = "quem"


class Media:
    pk = "9"
    media_type = 2
    user = User()
    code = "abc"
    caption_text = "Primeira linha da legenda\nSegunda linha\nTerceira linha com o passo a passo"


msg = ig_sync.to_messages([{"media": Media(), "collection_name": None}])[0]

if msg.get("caption") == Media.caption_text:
    ok("a legenda completa vai na mensagem, não só a primeira linha")
else:
    bad(f"caption na mensagem = {msg.get('caption')!r}")

if msg["title"] == "Primeira linha da legenda":
    ok("o título continua sendo a primeira linha")
else:
    bad(f"título = {msg['title']!r}")

# Sem legenda não se inventa string vazia -- None é o que o resto do código espera.
class SemLegenda(Media):
    caption_text = ""


if ig_sync.to_messages([{"media": SemLegenda(), "collection_name": None}])[0]["caption"] is None:
    ok("post sem legenda -> caption None, não string vazia")
else:
    bad("caption vazio deveria ser None")

print("== unit_cortes: os DOIS ramos do worker usam a legenda da mensagem ==")

from minimax_mcp import ig_worker  # noqa: E402

MSG = {"ig_pk": "9", "media_type": "video", "url": "u", "title": "titulo curto",
       "caption": "A LEGENDA COMPLETA com o passo a passo que importa",
       "owner_username": "quem", "collection_name": None, "status": "queued"}

recebido = {}


def ingest(text, **kw):
    recebido["text"] = text
    return {"ok": True, "document_id": 1}


# Ramo 1: tem texto na tela e nenhuma fala -- era aqui que a legenda sumia.
res = ig_worker.process_message(
    MSG,
    download=lambda m: {"ok": True, "filepath": "/tmp/x.mp4"},   # sem "caption": veio do disco
    transcribe=lambda p: {"ok": True, "text": "", "language": "pt"},
    describe=None,
    read_screen=lambda p: {"ok": True, "text": "TEXTO NA TELA"},
    ingest=ingest,
)
if res["status"] == "done" and "LEGENDA COMPLETA" in recebido.get("text", ""):
    ok("com texto na tela, a legenda da mensagem chega ao modelo")
else:
    bad(f"legenda perdida no ramo da tela: {recebido.get('text')!r}")

# Ramo 2: sem fala e sem tela -- já funcionava, tem de continuar funcionando.
recebido.clear()
res = ig_worker.process_message(
    MSG,
    download=lambda m: {"ok": True, "filepath": "/tmp/x.mp4"},
    transcribe=lambda p: {"ok": True, "text": "", "language": "pt"},
    describe=None, read_screen=None, ingest=ingest,
)
if res["status"] == "done" and "LEGENDA COMPLETA" in recebido.get("text", ""):
    ok("sem tela nenhuma, a legenda da mensagem também chega")
else:
    bad(f"legenda perdida no ramo sem tela: {recebido.get('text')!r}")

# Mensagem ANTIGA, enfileirada antes desta correção: não tem `caption`, e o
# título tem de continuar servindo de último reserva.
recebido.clear()
antiga = {k: v for k, v in MSG.items() if k != "caption"}
res = ig_worker.process_message(
    antiga,
    download=lambda m: {"ok": True, "filepath": "/tmp/x.mp4"},
    transcribe=lambda p: {"ok": True, "text": "", "language": "pt"},
    describe=None,
    read_screen=lambda p: {"ok": True, "text": "TEXTO NA TELA"},
    ingest=ingest,
)
if res["status"] == "done" and "titulo curto" in recebido.get("text", ""):
    ok("mensagem antiga sem caption ainda cai no reserva do título")
else:
    bad(f"mensagem antiga perdeu tudo: {recebido.get('text')!r}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
