# minimax-video-factory

Text → video **com áudio estéreo nativo**, local, numa RTX 4080 Laptop de 12 GB.
ComfyUI + MiniMax H3 (FL2VA, INT8) exposto por um servidor MCP.

> Este arquivo é carregado em **toda** sessão. O estado detalhado — o que está
> rodando, o que já foi medido, as pendências — está em **[`docs/HANDOFF.md`](docs/HANDOFF.md)**,
> e é lá que ele deve ser atualizado. Aqui ficam só as regras que não mudam.

---

## Regras que valem sempre nesta máquina

1. **Não dar `git push` sem pedir.** Dispara a CI no runner self-hosted, cujo job
   `gpu-validation` renderiza de verdade e rouba a GPU no meio dos testes — e tem
   `if: always()`, então nem falha de lint o impede.
2. **Não publicar os vídeos deste repo.** Várias entradas são fotos pessoais.
3. **Nunca mexer no worktree `.worktrees/igsync`** — trabalho do usuário na branch
   `feat/ig-saved-sync`.
4. **Um render por vez.** Dois concorrentes estouram a VRAM. Esperar a fila zerar
   (`GET /queue`) antes de submeter o próximo.
5. **Mostrar a fila junto com todo vídeo entregue**, e avisar do que houver nela.
6. **Worktree é obrigatório para implementação.** Commit só de documentação, não.
7. **Nunca animar rosto de terceiro identificável.** Fotos do próprio usuário, sim.
8. **Não mexer no `ig-worker`** — o usuário está desenvolvendo em cima dele. Ele roda
   no host e disputa **a mesma GPU** (Whisper + `lfm2:24b`, ~6 GB): se chegar mensagem
   do Instagram durante um render, o render morre. Avisar, não parar por conta própria.

---

## A regra de produção

> **Orçamento de ~100 M pixel-frames por render** (largura × altura × frames).
> Gaste em resolução **ou** em duração, nunca nas duas. Acima disso, é composição.

| pixel-frames | configuração | |
|---|---|---|
| 59 M | 512×320 · 15 s | ✅ 710 s |
| 73 M | 1024×576 · 5 s | ✅ 886 s |
| 98 M | 704×384 · 15 s | ← 30 s em **duas** emendas |
| **101 M** | **1216×672 · 5 s** | ✅ 1262 s — **o maior que passou** |
| **128 M** | **1344×768 · 5 s** | ❌ OOM |
| 213 M | 1024×576 · 15 s | ❌ OOM (três vezes) |

**Tempo: 12 s por megapixel-frame**, linear, medido em 4 resoluções e 2 durações.
**Steps não são alavanca** — 30 steps custam 1,51× e não melhoram nada. 20 basta.

## O que decide a qualidade de um clipe

**O assunto, não a resolução.** Texturas contínuas (água, nuvens, neve, névoa, luz,
paisagem, desenho de traço chapado) aguentam até 512×320. Rosto em close, texto
legível, arquitetura detalhada e multidão falham em qualquer resolução.

**Formato do prompt não é alavanca** para a imagem — prosa solta, os campos do model
card e a convenção do template do ComfyUI deram o mesmo clipe. **Mas o áudio tem
sintaxe:** diálogo é `(personagem, descrição da voz (S1)) says: <d>[Portuguese] fala</d>`,
dentro de `integrated_multimodal_description` / `overall_soundscape` / `non_diegetic_music`.

## Durações longas: encadeamento de frame

O modelo é **FL2VA** — First-**Last** frame to Video+Audio. O nó
`MiniMaxH3ImageToVideo` aceita `first_frame` **e** `last_frame`.

1. Último quadro do clipe N →
   `ffmpeg -nostdin -sseof -1 -i clip.mp4 -update 1 -q:v 2 -y frame.png`
   (`-frames:v 1` junto com `-sseof` pegaria o **primeiro** quadro do trecho.)
2. Vira `first_frame` do clipe N+1.
3. `compose_final` junta no fim.

**Duas coisas não óbvias:** prompt **novo** por capítulo (o quadro dá continuidade, o
prompt faz avançar), e **cada prompt tem de recarregar as âncoras de estilo** — o
modelo só enxerga *um* quadro do passado, não os clipes anteriores.

**O áudio não é encadeado.** Não existe `first_audio`: cada capítulo inventa a trilha
do zero (degrau medido de até 31,7 dB). Duas defesas: `non_diegetic_music` **idêntico,
literalmente**, em todos os capítulos; e `scripts/unify_audio.py` depois (ganho
estático até −21 LUFS + limitador + fades de 80 ms, **nunca `acrossfade`**, que
dessincroniza).

---

## Operação

```bash
pgrep -af "rodada3|round2|ig_worker"       # o que está de pé
curl -s localhost:8188/queue                # a fila
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader
```

**`pgrep` vazio ≠ terminou.** Um driver de render que morre por exceção some do
`pgrep` igual a um que terminou. Distinguir **sempre** pela linha final no log
(`rodada N concluída`); sem ela, é crash — ler o traceback. Os drivers são
retomáveis, relançar não re-renderiza o que já está no disco.

**VRAM presa sem ninguém usando:** o ComfyUI mantém os modelos residentes depois de um
render (~11 GB a 0% de uso). Com a fila vazia:
`curl -X POST localhost:8188/free -d '{"unload_models":true,"free_memory":true}'`.

**Tool MCP nova custa 4 lugares:** `catalog.COMMAND_NAMES`, a lista canônica de
`unit_registry`, a tabela do `README.md`, e rodar `scripts/generate_commands.py`
(que escreve **dois** arquivos por tool). Parâmetro novo numa tool existente não
dispara esse ritual — só regerar os docs.
