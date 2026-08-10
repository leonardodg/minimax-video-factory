#!/usr/bin/env python3
"""A verificação que segura a invenção de código — medida, não suposta."""
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


from minimax_mcp.llm import NAO_MOSTRADO, ancorar_codigo

print("== unit_llm_ancora: o caso real que refutou o prompt ==")

# Post 3839009985007901571: a tela NÃO tem comando nenhum, e o tutorial saiu com
# três kubectl inventados. É este caso que a regra do prompt não segurou.
FONTE_K8S = (
    "O que você quer? O que? O que você quer?\n--- texto na tela ---\n"
    "Kubernetes in 60 seconds\nincoming traffic\nmanually creating container's\n"
    "How can I automatically.\nrun, scale, and\ndelete containers?\ncrashed container"
)
TUT_K8S = (
    "1. **Criar um Pod**: Use o comando `kubectl create pod nome-pod --image=nome-imagem`.\n"
    "2. **Expor como Serviço**: Crie um serviço com `kubectl expose pod nome-pod --type=ClusterIP`.\n"
    "3. **Gerenciar**: Para escalar, use `kubectl scale deployment nome-deploy --replicas=número`."
)
saida, n = ancorar_codigo(TUT_K8S, FONTE_K8S)
if n == 3 and "kubectl" not in saida and NAO_MOSTRADO in saida:
    ok("os três kubectl inventados saem, e o texto explica que não foram mostrados")
else:
    bad(f"kubectl sobreviveu: removidos={n} saida={saida!r}")

print("== unit_llm_ancora: o código que ESTÁ na tela sobrevive ==")

# Post 3818562307589048738: aqui a visão leu o código de verdade, e ele tem de
# passar intacto -- é o conteúdo que dá valor à base.
FONTE_TOAST = (
    "--- texto na tela ---\n```python\nfrom win10toast import ToastNotifier\n"
    'toaster = ToastNotifier()\ntoaster.show_toast(\n    title="Hora de Beber Água!",\n'
    '    msg="Seu script Python te lembrou de beber água!",\n    duration=10,\n)'
)
TUT_TOAST = (
    "```\nfrom win10toast import ToastNotifier\ntoaster = ToastNotifier()\n"
    'toaster.show_toast(\n    title="Hora de Beber Água!",\n    duration=10,\n)\n```'
)
saida, n = ancorar_codigo(TUT_TOAST, FONTE_TOAST)
if n == 0 and "win10toast" in saida:
    ok("bloco ancorado na tela passa intacto")
else:
    bad(f"bloco legítimo foi mutilado: removidos={n} saida={saida!r}")

print("== unit_llm_ancora: bordas ==")

# Reformatar não pode derrubar um bloco correto: o modelo mexe em indentação e
# quebra de linha, e por isso o limiar é de maioria, não de unanimidade.
saida, n = ancorar_codigo(
    "```\nfrom win10toast import ToastNotifier\ntoaster = ToastNotifier()\nprint('extra inventado aqui')\n```",
    "from win10toast import ToastNotifier\ntoaster = ToastNotifier()",
)
if n == 0:
    ok("bloco com maioria ancorada sobrevive a uma linha estranha")
else:
    bad("uma linha a mais derrubou um bloco majoritariamente correto")

# Prosa entre crases é ênfase, não comando -- não pode virar "(não mostrado)".
saida, n = ancorar_codigo("Use o `Pod` para isso", "nada aqui")
if n == 0 and saida == "Use o `Pod` para isso":
    ok("ênfase entre crases não é tratada como código")
else:
    bad(f"ênfase virou código: {saida!r}")

# Comando que o NARRADOR falou está na transcrição, logo está ancorado.
saida, n = ancorar_codigo(
    "Rode `pip install win10toast` primeiro.",
    "primeiro você roda pip install win10toast no terminal",
)
if n == 0 and "pip install win10toast" in saida:
    ok("comando dito na narração conta como ancorado")
else:
    bad(f"comando falado foi removido: {saida!r}")

if ancorar_codigo("", "x") == ("", 0) and ancorar_codigo(None, "x") == (None, 0):
    ok("tutorial vazio ou None não quebra")
else:
    bad("borda de tutorial vazio quebrou")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
