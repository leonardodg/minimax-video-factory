#!/usr/bin/env python3
"""CTA em inglês — e, sobretudo, o conteúdo técnico que NÃO pode ser apagado."""
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


from minimax_mcp.ig_worker import clean_title, strip_cta

print("== CTA em inglês sai ==")
CASOS = [
    # O título real do doc 212, que passou inteiro para a base.
    ("😱Still not Following me?? You'll miss all of it..", None),
    ("Follow @darpan.decoded for more tips", None),
    ("Save this post for later!", None),
    ("Tag a friend who needs this", None),
    ("Link in bio to get the full guide", None),
]
for entrada, esperado in CASOS:
    got = clean_title(entrada)
    if got == esperado:
        ok(f"clean_title({entrada[:38]!r}) -> {got!r}")
    else:
        bad(f"clean_title({entrada[:38]!r}) = {got!r}, esperado {esperado!r}")

# O que a tela entregou junto com o conteúdo do Kubernetes.
t = strip_cta("Kubernetes in 60 seconds. Follow @darpan.decoded. How can I scale containers?")
if "darpan" not in t and "Kubernetes in 60 seconds" in t and "scale containers" in t:
    ok("strip_cta tira o Follow @conta e preserva as frases vizinhas")
else:
    bad(f"strip_cta = {t!r}")

print("== o conteúdo técnico SOBREVIVE (o risco de verdade) ==")
# Um padrão largo demais apagaria justamente o que a base existe para guardar.
INTOCAVEIS = [
    "Follow the steps below to install the package.",
    "You should follow this pattern in every handler.",
    "The compiler will follow us through the type graph.",
    "Save the file and restart the server.",
    "Share this state between the two components.",
    "Comment out the line and run it again.",
    "This function follows the same convention.",
]
for frase in INTOCAVEIS:
    if strip_cta(frase) == frase:
        ok(f"intacto: {frase[:52]}")
    else:
        bad(f"APAGOU CONTEÚDO TÉCNICO: {frase!r} -> {strip_cta(frase)!r}")

print("== ponto que NÃO é fim de frase ==")
# Defeito latente que já existia: todo `.` terminava frase, então a remoção de
# CTA quebrava dentro de nome de arquivo e número de versão -- justamente o que
# mais aparece neste conteúdo.
casos = [
    ("Open main.py and edit it. Follow me for more.", "main.py"),
    ("Requires Python 3.11 or newer. Save this post!", "Python 3.11"),
    ("Run npm i -D vitest. Link in bio for the repo.", "npm i -D vitest"),
]
for entrada, preservar in casos:
    got = strip_cta(entrada)
    if preservar in got and "Follow me" not in got and "Save this post" not in got \
       and "Link in bio" not in got:
        ok(f"preserva {preservar!r} e remove o CTA da frase seguinte")
    else:
        bad(f"strip_cta({entrada!r}) = {got!r}")

print("== português não regrediu ==")
if clean_title("Siga para mais 👉 @nikolassfaria") is None and \
   clean_title("A energia do Sol cada vez mais próxima!") == "A energia do Sol cada vez mais próxima!":
    ok("os casos em português seguem como antes")
else:
    bad("regressão no vocabulário em português")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
