# Plano — sincronizar os 2145 posts restantes do Instagram

## Contexto

A base tem 12 documentos de Instagram; o usuário tem **2157 posts salvos**. Faltam
**2145**. O custo medido é de **50 s por post**, o que dá **~30 h de GPU** de
processamento puro.

O gargalo, porém, **não é a GPU — é o Instagram**. Em 2026-08-09 duas varreduras
completas dentro de uma hora geraram 429 e derrubaram coleções inteiras da
listagem: a segunda enxergou 202 posts em vez de 2157. Um plano que ignore isso
não perde tempo, perde **acesso**.

---

## Pré-requisitos, os dois bloqueantes

### 1. Fazer merge de `feat/cta-export-markdown` antes de qualquer coisa

Sem isso, os 2145 documentos nascem com CTA na transcrição **e no título** —
`"Siga para mais @fulano"`, `"Comenta 'PROCESSO' que eu te mando"`. Refazer
custaria as 30 h de novo, mais uma segunda leva de requisições ao Instagram, que
é o recurso que não se pode gastar duas vezes.

A branch está pronta: 14 testes, ruff limpo, 26 tools consistentes.

### 2. Validar os 12 re-ingeridos

São a amostra que prova o pipeline **com** a limpeza. Conferir antes de
comprometer 30 h:

- transcrição e campos gerados sem CTA;
- os 3 títulos de CTA trocados (120, 123, 128) e os outros 9 intactos;
- categoria e `colecao:` preenchidas como antes;
- nada de regressão nos 9 que não deviam mudar.

Comparar contra `output/kb-backup-antes/Knowledge/` (12 `.md`) e, se algo
estiver errado, restaurar de `docs_118_129_raw.json`.

---

## O risco de verdade: o Instagram

| operação | quantas chamadas | quando |
|---|---|---|
| **Listagem** (`sync_saved_posts`) | 1 varredura das 46 coleções | **uma única vez** |
| **Consumo** (por post) | 1 `media_info` + 1 download | 2145 vezes, espalhadas |

> **Uma listagem só.** `sync_saved_posts` enumera, filtra os `ig_pk` já
> conhecidos e publica todos os novos na fila `ig.saved` — durável, com status
> por mensagem e DLQ. Depois disso, o Instagram só é tocado **um post por vez**,
> no ritmo do consumo.
>
> ⚠️ **Nunca usar `ig_reingest.py`** para isto: ele relista as 46 coleções a cada
> execução, que é exatamente o gatilho do 429.

**A fila é o mecanismo de lote.** Publica-se tudo de uma vez e controla-se o
ritmo pelo **consumo**, não pela publicação.

---

## A lacuna que este plano precisa fechar

O worker consome com `prefetch=1` e **sem pausa entre mensagens**. A 50 s por
post, isso são ~72 posts/hora contínuos, e o único freio existente é ligar e
desligar o processo na mão.

Para uma corrida de 30 h isso não serve. **Acrescentar `IG_WORKER_MIN_INTERVAL`**
(segundos, padrão `0` = comportamento atual): o worker dorme o que faltar para
completar o intervalo depois de cada mensagem. Com 90 s → ~40 posts/hora, e a
corrida fica desatendida sem martelar o Instagram.

É uma mudança pequena, em `ig_worker.py`, testável sem GPU.

### ⚠️ Por que o ritmo tem de ser DENTRO do processo, e não por start/stop

Observado em 2026-08-09 ao subir o worker: ele chama
`/api/v1/collections/list/` — paginando — para montar o vocabulário de categorias.
Isso está **cacheado por processo** (`_categories_cache`, `ig_worker.py:232`),
então acontece **uma vez por worker**, não por mensagem.

A consequência é que **cada reinício do worker custa uma varredura das 46
coleções** — exatamente a operação que dispara 429. Controlar o ritmo ligando e
desligando o processo somaria uma listagem por ciclo; com dezenas de ciclos ao
longo de 54 h, seria pior que não ter ritmo nenhum.

> **Um worker de longa duração, com pausa interna.** Não vários ciclos curtos.

---

## Contenção de GPU

O worker carrega **Whisper + `lfm2:24b`, ~6 GB**. Um render de vídeo usa ~11 GB
dos 12 GB da placa. **Os dois não coexistem** — foi por isso que o `ig-worker`
foi parado em 2026-08-09 durante a rodada 3.

Duas formas de conviver, e é preciso escolher uma:

- **Janela dedicada** — a máquina fica só na ingestão por blocos de horas. Mais
  simples e mais rápido.
- **Ingestão como tarefa de fundo** — o worker roda e é parado antes de cada
  rodada de vídeo. Exige disciplina manual, e um render morre se alguém esquecer.

---

## Execução

### Fase 0 — preparo (sem GPU, sem Instagram)

1. Merge da branch de CTA na `main`.
2. `IG_WORKER_MIN_INTERVAL` implementado e testado.
3. Validação dos 12 (acima).
4. Conferir espaço: a mídia é apagada depois de processada, **inclusive quando
   falha**, então o disco não acumula. O que cresce é o Postgres (2145 documentos
   + chunks + embeddings).

### Fase 1 — a listagem única

`/ig-sync` uma vez. Esperado: `published ≈ 2145`, `skipped_existing = 12`.

**Se vier muito abaixo de 2145, PARAR.** Foi assim que o 429 se manifestou da
outra vez: a listagem volta truncada em vez de dar erro. Nesse caso, esperar
horas e repetir — nunca insistir em seguida.

### Fase 2 — consumo, em blocos

| bloco | posts | o que se verifica ao fim |
|---|---|---|
| **piloto** | 50 | qualidade, categorias, CTA limpo, tempo real por post |
| **2º** | 450 | tamanho do banco, profundidade da DLQ, disco |
| **restante** | ~1645 | só monitoramento |

Entre blocos, olhar `ig_queue_status` (fila e DLQ) e `ig_get_progress`
(últimos processados).

### Fase 3 — a DLQ

Depois de 3 tentativas a mensagem morre na DLQ. Ao fim, ler o que caiu lá e
decidir caso a caso: post apagado, mídia indisponível, transcrição vazia. Só
então republicar o que valer a pena.

---

## Verificação

1. **Contagem** — `SELECT count(*) FROM documents WHERE ig_pk IS NOT NULL`
   fechando com `published` menos a DLQ.
2. **Amostra às cegas** — 10 documentos aleatórios lidos à mão, procurando CTA
   sobrevivente, resumo genérico e categoria errada.
3. **Sem duplicata** — `ig_pk` é único; contagem de distintos igual à total.
4. **Busca funciona** — `kb-buscar` num termo que só aparece em post novo.

---

## Decisões tomadas (2026-08-09)

| decisão | escolha | consequência |
|---|---|---|
| **Ritmo** | `IG_WORKER_MIN_INTERVAL=90` → ~40 posts/h | **~54 h** de relógio, desatendido, risco de 429 baixo |
| **GPU** | **janela dedicada** à ingestão | nenhum render durante os blocos; nenhum morre por descuido |
| **Whisper** | manter **`small`** | a validação dos 12 representa os 2145; 50 s/post continua valendo |

A escolha do Whisper tem uma razão que vale explicitar: `small` é o modelo que
produziu os 12 documentos usados como amostra. Trocá-lo faria a validação deixar
de representar o lote — aprovar-se-ia uma coisa e rodar-se-ia outra.

### Cronograma que sai dessas escolhas

```
2145 posts ÷ 40/h ≈ 54 h de janela dedicada
  piloto      50 posts     ~1 h 15    → conferir e decidir se segue
  bloco 2    450 posts    ~11 h 15    → banco, DLQ, disco
  restante  ~1645 posts   ~41 h       → só monitorar
```

Divisível como for conveniente — a fila é durável e o worker pode parar e voltar
a qualquer momento sem perder nada.
