#!/usr/bin/env python3
"""A conexao AMQP nao pode ter heartbeat: o trabalho aqui bloqueia por minutos.

Nao abre conexao nenhuma -- troca o BlockingConnection por um espiao e olha os
parametros que o `connect()` monta.
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pika  # noqa: E402

falhas = []


def ok(m):
    print(f"  [ok]   {m}")


def erro(m):
    print(f"  [FALHA] {m}")
    falhas.append(m)


def parametros_de(url: str):
    """Chama connect() com RABBITMQ_URL=url e devolve os params usados."""
    import os
    os.environ["RABBITMQ_URL"] = url
    from minimax_mcp import ig_queue
    importlib.reload(ig_queue)

    capturado = {}
    original = pika.BlockingConnection

    def espiao(params):
        capturado["params"] = params
        raise RuntimeError("nao conectar de verdade")

    pika.BlockingConnection = espiao
    try:
        ig_queue.connect()
    except RuntimeError:
        pass
    finally:
        pika.BlockingConnection = original
    return capturado.get("params")


print("== unit_ig_queue_heartbeat: sem heartbeat por padrao ==")
p = parametros_de("amqp://guest:guest@localhost:5672/")
if p is not None and p.heartbeat == 0:
    ok("heartbeat=0 (o trabalho bloqueia por minutos; 60 s derrubava a conexao)")
else:
    erro(f"heartbeat={getattr(p, 'heartbeat', '?')!r}, esperado 0")

if p is not None and p.blocked_connection_timeout == 300:
    ok("blocked_connection_timeout=300 (broker sob pressao nao pendura o publisher)")
else:
    erro(f"blocked_connection_timeout={getattr(p, 'blocked_connection_timeout', '?')!r}")

print()
print("== a URL continua mandando, se disser algo ==")
p2 = parametros_de("amqp://guest:guest@localhost:5672/?heartbeat=30")
if p2 is not None and p2.heartbeat == 30:
    ok("heartbeat=30 vindo da URL foi respeitado, nao sobrescrito")
else:
    erro(f"URL pediu 30, saiu {getattr(p2, 'heartbeat', '?')!r}")

print()
print("== o host e a porta continuam saindo da URL ==")
p3 = parametros_de("amqp://guest:guest@rabbitmq:5672/")
if p3 is not None and p3.host == "rabbitmq" and p3.port == 5672:
    ok("host=rabbitmq porta=5672 (o caminho do container nao quebrou)")
else:
    erro(f"host={getattr(p3, 'host', '?')} porta={getattr(p3, 'port', '?')}")

print()
print("ALL PASS" if not falhas else f"{len(falhas)} FALHA(S)")
sys.exit(1 if falhas else 0)
