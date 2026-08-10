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

print("== unit_llm_ancora: prosa embrulhada em cerca NÃO é código ==")

# Os dois casos que o usuário analisou em 2026-08-10. A régua antiga apagava os
# blocos inteiros -- e com eles a resposta que o post tinha.
FONTE_AWS = ("[20.70s] Primeiro, eu tive que me cadastrar no site da Amazon, "
             "[23.70s] o Skillbuilders.aws. [25.90s] E assim que você entra na plataforma,")
TUT_AWS = ("```\n1. Cadastre-se em [Skillbuilders.aws](https://skillbuilders.aws).\n"
           "2. Explore os cursos oferecidos pela AWS.\n"
           "3. Selecione a certificação desejada e verifique os pré-requisitos.\n```")
saida, n = ancorar_codigo(TUT_AWS, FONTE_AWS)
if n == 0 and "Skillbuilders.aws" in saida:
    ok("lista numerada em prosa sobrevive, e o nome do site com ela")
else:
    bad(f"prosa foi apagada: removidos={n} saida={saida!r}")

FONTE_VS = ("[4.38s] Apertando Ctrl mais D, você vai selecionar todas as palavras iguais "
            "[11.16s] Apertando Ctrl mais P, você consegue buscar um nome de arquivo")
TUT_VS = ("```\n1. Aumentar produtividade no VS Code com atalhos.\n"
          "2. Selecionar todas as palavras: Ctrl + D\n"
          "3. Buscar e abrir arquivos rapidamente: Ctrl + P\n```")
saida, n = ancorar_codigo(TUT_VS, FONTE_VS)
if n == 0 and "Ctrl + D" in saida:
    ok("atalho falado e escrito na forma canônica sobrevive")
else:
    bad(f"atalhos apagados: removidos={n} saida={saida!r}")

print("== unit_llm_ancora: e o código de verdade continua sendo cobrado ==")

# CSS inventado (doc 333): tem chave, ponto-e-vírgula e ::, é para copiar.
TUT_CSS = '```\ntag[role="quote"]::before {\n  content: "";\n  font-style: italic;\n}\n```'
saida, n = ancorar_codigo(TUT_CSS, "São pseudo-elementos do CSS que deixam você adicionar coisas")
if n == 1 and "font-style" not in saida:
    ok("bloco CSS sem âncora na fonte continua caindo")
else:
    bad(f"CSS inventado sobreviveu: removidos={n} saida={saida!r}")

# Comando de terminal inventado (doc 310).
saida, n = ancorar_codigo(
    "```\nnmap -p- --open -T4 -v -A -iL ips.txt\n```",
    "Hoje vou te mostrar como escanear todos os IPs da internet",
)
if n == 1:
    ok("comando de terminal sem âncora continua caindo")
else:
    bad(f"comando inventado sobreviveu: removidos={n}")

# E o misto do doc 322: metade do bloco veio da tela, metade o modelo completou.
FONTE_REACT = "export const Component = () => { useEffect(() => {"
TUT_REACT = ("```\nimport { useState, useEffect } from 'react';\n"
             "export const Component = () => {\n"
             "const [count, setCount] = useState(0);\n"
             "useEffect(() => {\n```")
saida, n = ancorar_codigo(TUT_REACT, FONTE_REACT)
if n == 1:
    ok("bloco com metade inventada cai (2 de 4 ancoradas, abaixo do limiar)")
else:
    bad(f"bloco misto: removidos={n} saida={saida!r}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
