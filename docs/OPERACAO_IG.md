# Operação: sincronizar e reprocessar o Instagram

Tudo o que é preciso para tocar a corrida sem depender de ninguém. Os comandos
assumem que você está na raiz do repositório.

> **A regra que governa tudo:** o worker e o reprocessamento **disputam a mesma
> GPU** e não cabem juntos. Medido em 2026-08-10: o pico do worker é **10,8 GB
> dos 12,3 GB** da placa, e o modelo de visão pede ~6 GB. Rodar os dois deu
> `CUDA failed with error out of memory`. **Um de cada vez, sempre.**

---

## 1. Subir a infraestrutura

```bash
cd ~/tools-local/minimax-video-factory
docker start minimax-rabbitmq minimax-kb-postgres minimax-comfyui
```

Conferir antes de qualquer coisa:

```bash
# a fila (durável: sobrevive a reboot, nada se perde)
curl -s -u guest:guest localhost:15672/api/queues \
  | python3 -c "import sys,json;[print(f\"{q['name']:18} ready={q.get('messages_ready',0)} unacked={q.get('messages_unacknowledged',0)} consumers={q.get('consumers',0)}\") for q in json.load(sys.stdin) if q['name'].startswith('ig.')]"

# a GPU tem de estar livre (~500 MB) antes de começar
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
```

---

## 2. Reprocessar documentos

Refaz documentos já ingeridos com o pipeline atual, **a partir da mídia no
disco**. Não toca o Instagram e não precisa da pausa de 90 s — ela existe para
espaçar requisições que aqui não acontecem.

**Sempre comparar antes de aplicar.** Sem `--aplicar` nada é gravado:

```bash
set -a; . ./.env; set +a
./.venv/bin/python -u scripts/ig_reprocessar.py 187 231 244
```

Isso grava `output/comparacao-10.md` e `.json` com o antes e depois completos.
Lido o resultado, aplica-se:

```bash
./.venv/bin/python -u scripts/ig_reprocessar.py $(cat output/ig-sync-2026-08-10/ids_restam.txt) --aplicar
```

Para o lote grande, sob systemd — **`nohup` não basta**, ver a seção de
armadilhas:

```bash
systemd-run --user --unit=ig-reprocessa --collect \
  --working-directory="$PWD" \
  /bin/bash -c 'set -a; . ./.env; set +a; \
    exec ./.venv/bin/python -u scripts/ig_reprocessar.py \
      $(cat output/ig-sync-2026-08-10/ids_restam.txt) --aplicar'
```

**Rede de proteção:** cada documento é copiado para
`output/kb-backup-reprocess/<id>.json` **antes** de ser tocado, e se a
regravação falhar ele é restaurado pelo ORM (com chunks e embeddings). Isso já
salvou documentos em produção — a taxa de falha por JSON foi de ~7%.

---

## 3. Soltar o worker (só DEPOIS que o reprocessamento terminar)

```bash
systemd-run --user --unit=ig-worker --collect \
  --working-directory="$PWD" \
  --description="ig-worker: consome a fila ig.saved" \
  /bin/bash -c 'set -a; . ./.env; set +a; \
    exec ./.venv/bin/python -m minimax_mcp.ig_worker >> output/ig-sync-2026-08-10/worker.log 2>&1'
```

⚠️ **`systemd-run`, não `systemctl start`.** A unidade é transitória
(`--collect`), some quando para, e `systemctl start` falha com *unit not found*.

**Conferir que subiu UM só:**

```bash
systemctl --user is-active ig-worker.service
pgrep -c -f "[m]inimax_mcp.ig_worker"     # tem de ser 1
```

---

## 4. Monitorar

```bash
# o worker, ao vivo
journalctl --user -u ig-worker.service -f
tail -f output/ig-sync-2026-08-10/worker.log

# o reprocessamento, ao vivo
journalctl --user -u ig-reprocessa.service -f

# só o que interessa: falhas e bloqueio
tail -f output/ig-sync-2026-08-10/worker.log | grep -E "public_request|DOCTYPE|Traceback|cudaMalloc|out of memory|processing failed"

# relatório completo (fila, banco, disco, GPU, ritmo)
bash scripts/ig_relatorio.sh
```

**A verificação que importa antes** — íntegro é `total == distintos`:

```bash
set -a; . ./.env; set +a
./.venv/bin/python -c "
import os
from sqlalchemy import create_engine, text
e = create_engine(os.environ['KB_DATABASE_URL'])
with e.connect() as c:
    t = c.execute(text('SELECT count(*) FROM documents WHERE ig_pk IS NOT NULL')).scalar()
    d = c.execute(text('SELECT count(DISTINCT ig_pk) FROM documents WHERE ig_pk IS NOT NULL')).scalar()
print(t, d, 'INTEGRA' if t == d else 'DIVERGENTE')
"
```

⚠️ Uma leitura de `total = distintos - 1` **durante** o reprocessamento é
normal: ele apaga e regrava, e a consulta pode cair na fresta entre as duas
operações. Repita a leitura; se persistir, aí sim há documento perdido.

---

## 5. Pausar e retomar o worker

```bash
# pausar (para liberar a GPU)
set -a; . ./.env; set +a
./.venv/bin/python -c "
import json
from minimax_mcp import ig_queue
conn = ig_queue.connect(); ch = conn.channel(); ig_queue.declare(ch)
ch.basic_publish(exchange='', routing_key=ig_queue.CONTROL_QUEUE, body=json.dumps({'command':'stop'}).encode())
ig_queue.close(conn)
"
```

⚠️ **A pausa não é instantânea.** O worker é single-thread: ele atende o comando
só ao terminar o post em curso, o que pode levar **até 90 s**. Ela efetivou
quando `consumers` da `ig.saved` chega a **0**:

```bash
until [ "$(curl -s -u guest:guest localhost:15672/api/queues \
  | python3 -c "import sys,json;print(sum(q.get('consumers',0) for q in json.load(sys.stdin) if q['name']=='ig.saved'))")" = "0" ]; do sleep 10; done
echo "pausado"
```

Para retomar, o mesmo comando com `'start'`. Para parar de vez:
`systemctl --user stop ig-worker.service`.

---

## 6. Armadilhas que já custaram caro

| armadilha | o que acontece | como evitar |
|---|---|---|
| **`nohup` não protege de SIGTERM** | o processo morre junto com o comando que o lançou; aconteceu duas vezes | `systemd-run --user` |
| **`systemctl start` em unidade transitória** | falha com *unit not found* porque `--collect` a removeu | recriar com `systemd-run` |
| **`pgrep -f ig_worker` casa com o próprio comando** | parece que há um worker quando não há | usar `[m]inimax_mcp.ig_worker` |
| **Dois workers em paralelo** | OOM, e o mais velho roda **código antigo** — em 2026-08-10 um órfão de `setsid` sobreviveu ao `systemctl stop` e gerou documentos sem a verificação de código | conferir `pgrep -c -f "[m]inimax_mcp.ig_worker"` **depois** de todo reinício |
| **`pgrep` vazio ≠ terminou** | um processo que morreu por exceção some igual a um que acabou | conferir a última linha do log e procurar `Traceback` |
| **Relistar as coleções** | cada reinício do worker custa uma varredura das 46+ coleções, que é o gatilho do 429 do Instagram | preferir poucos blocos longos a muitos curtos |

---

## 7. Onde estão os backups

| arquivo | o que é |
|---|---|
| `output/kb-backup-total-<data>.json` | **todos** os documentos, todos os campos |
| `output/kb-backup-reprocess/<id>.json` | snapshot individual, gravado antes de cada reprocessamento |
| `output/kb-backup-antes/docs_118_129_raw.json` | os 12 documentos originais |
| `output/ig-sync-2026-08-10/mensagens.json` | as mensagens da listagem do Instagram (evita relistar) |

Tirar um backup total antes de qualquer operação destrutiva:

```bash
set -a; . ./.env; set +a
./.venv/bin/python -c "
import os, json
from sqlalchemy import create_engine, text
e = create_engine(os.environ['KB_DATABASE_URL'])
COLS = 'id, ig_pk, type, source_url, platform, title, language, transcription_text, summary, tutorial, objectives, tags, raw_file_path, llm_provider, llm_model, created_at'
campos = COLS.replace(' ', '').split(',')
with e.connect() as c:
    rows = c.execute(text(f'SELECT {COLS} FROM documents ORDER BY id')).fetchall()
docs = [dict(zip(campos, r)) for r in rows]
import datetime
nome = f'output/kb-backup-total-{datetime.date.today()}.json'
open(nome, 'w', encoding='utf-8').write(json.dumps(docs, ensure_ascii=False, indent=2, default=str))
print(nome, len(docs), 'documentos')
"
```
