#!/usr/bin/env python3
"""A verificação de citação, contra os seis posts reais que a moldaram.

Este arquivo é o conjunto de REGRESSÃO do usuário: seis posts que ele analisou
um a um em 2026-08-10, com o que ele disse que queria de cada um. Qualquer
desenho novo tem de passar nos seis de uma vez -- foi a falta disso que fez a
versão anterior acumular cinco heurísticas, cada uma consertando um caso e
quebrando outro.
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


from minimax_mcp.llm import NAO_VERIFICADO, ancorar_codigo

print("== o contrato: marcado = copiado do material ==")

# Bloco que confere passa inteiro.
FONTE = ("--- texto na tela ---\n```python\nfrom win10toast import ToastNotifier\n"
         "toaster = ToastNotifier()\ntoaster.show_toast(title=\"Beber Água\")")
TUT = ('```python\nfrom win10toast import ToastNotifier\ntoaster = ToastNotifier()\n```')
saida, n = ancorar_codigo(TUT, FONTE)
if n == 0 and "win10toast" in saida:
    ok("bloco copiado do material passa intacto")
else:
    bad(f"bloco legítimo mutilado: removidos={n} saida={saida!r}")

# Bloco que não confere vira a marca -- a pessoa ia colar isso.
saida, n = ancorar_codigo("```bash\nsudo apt install nmap\n```", "o vídeo fala de escanear portas")
if n == 1 and NAO_VERIFICADO in saida and "```" not in saida and "sudo apt install nmap" in saida:
    ok("bloco não conferido perde a cerca e ganha o aviso, sem perder o conteúdo")
else:
    bad(f"bloco: removidos={n} saida={saida!r}")

# Trecho inline que não confere PERDE A CRASE e mantém as palavras.
saida, n = ancorar_codigo("Use o atalho `Ctrl + D` para isso.", "apertando Ctrl mais D você seleciona")
if n == 1 and saida == "Use o atalho Ctrl + D para isso.":
    ok("inline não conferido perde a marcação, não o conteúdo")
else:
    bad(f"inline: removidos={n} saida={saida!r}")

print("== regressão: os seis posts que o usuário analisou ==")

CASOS = [
    (
        "3709415772515231896 — o nome do site está na FALA",
        ("```\n1. Cadastre-se em [Skillbuilders.aws](https://skillbuilders.aws).\n"
         "2. Explore os cursos oferecidos pela AWS.\n```"),
        "[20.70s] me cadastrar no site da Amazon, [23.70s] o Skillbuilders.aws.",
        lambda s, n: "Skillbuilders.aws" in s,
        "o nome do site sobrevive",
    ),
    (
        "3698558136683172408 — os atalhos estão na FALA",
        "Selecionar todas as palavras: `Ctrl + D`. Buscar arquivo: `Ctrl + P`.",
        "[4.38s] Apertando Ctrl mais D [11.16s] Apertando Ctrl mais P",
        lambda s, n: "Ctrl + D" in s and "Ctrl + P" in s,
        "os atalhos sobrevivem, sem a crase indevida",
    ),
    (
        "3704821969073991262 — o código na tela é ILUSTRATIVO",
        "```bash\nnmap -p- --open -T4 -v -A -iL ips.txt\n```",
        "Hoje vou te mostrar como escanear todos os IPs da internet",
        lambda s, n: n >= 1 and "```" not in s and NAO_VERIFICADO in s,
        "o comando ilustrativo perde a cerca e vem avisado",
    ),
    (
        "3671499376976917314 — metade veio da tela, metade o modelo completou",
        ("```js\nimport { useState } from 'react';\nexport const C = () => {\n"
         "const [x, setX] = useState(0);\nuseEffect(() => {\n```"),
        "export const C = () => { useEffect(() => {",
        lambda s, n: n >= 1 and NAO_VERIFICADO in s,
        "bloco metade inventado é avisado (2 de 4 = meio a meio)",
    ),
    (
        "3678218579439466538 — o texto está NAS IMAGENS e foi lido",
        '```css\n.quote::before {\n  content: "";\n}\n```',
        '--- texto na imagem ---\n.quote::before {\n  content: "";\n}',
        lambda s, n: n == 0 and "quote::before" in s,
        "CSS lido da imagem passa intacto",
    ),
    (
        "3836068477317386045 — sem fala, o conteúdo é a tela",
        "Use `np.reshape(array, (rows, cols))` para redimensionar.",
        "--- texto na tela ---\nnp.reshape(array, (rows, cols))",
        lambda s, n: n == 0 and "np.reshape" in s,
        "chamada lida da tela mantém a crase",
    ),
]

for nome, tut, fonte, verifica, descricao in CASOS:
    saida, n = ancorar_codigo(tut, fonte)
    if verifica(saida, n):
        ok(f"{nome}: {descricao}")
    else:
        bad(f"{nome}: removidos={n} saida={saida!r}")

print("== bordas ==")
if ancorar_codigo("", "x") == ("", 0) and ancorar_codigo(None, "x") == (None, 0):
    ok("tutorial vazio ou None não quebra")
else:
    bad("borda de vazio quebrou")

# Reformatação de indentação não pode derrubar bloco correto.
saida, n = ancorar_codigo(
    "```python\n    from win10toast import ToastNotifier\n    toaster = ToastNotifier()\n```",
    "from win10toast import ToastNotifier\ntoaster = ToastNotifier()",
)
if n == 0:
    ok("indentação diferente não derruba bloco copiado")
else:
    bad(f"indentação derrubou bloco: {saida!r}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
