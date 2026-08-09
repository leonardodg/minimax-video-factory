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
| 84 M | 448×256 · 30,7 s | ✅ 1094 s — mas **fora da faixa treinada**, ver abaixo |
| 98 M | 704×384 · 15 s | ✅ 1242 s — **limpo**; é como se fazem 30 s com UMA emenda |
| 101 M | 1216×672 · 5 s | ✅ 1262 s |
| **103 M** | **1024×576 · 7,3 s** | ✅ 1313 s — **o maior que passou** |
| **128 M** | **1344×768 · 5 s** | ❌ OOM |
| 213 M | 1024×576 · 15 s | ❌ OOM (três vezes) |

**Tempo: 12 s por megapixel-frame** (medido entre 12,0 e 13,0 em 6 resoluções),
linear, sem termo quadrático.

### A faixa treinada acaba em 362 frames (15,08 s), e isso é um limite à parte

O nó aceita `length` até 3600 e a VRAM aguenta 736 frames a 448×256 (84 M). O
modelo **renderiza** — e degrada de dois jeitos independentes, medidos em
2026-08-09 com um clipe de 30,7 s:

- **A cor.** Manchas magenta/verde que crescem ao longo do clipe; aos 20 s um
  corvo preto ficou verde. A composição e a narrativa continuam de pé.
- **O tempo do áudio.** As seis falas escritas para 30 s couberam nos primeiros
  17 s; depois vieram 13 s de silêncio e um fragmento solto no último segundo.

**Não é uma questão de VRAM.** Passar de 362 frames é fora de especificação.
Para durar mais, é composição.
**Steps não são alavanca** — 30 steps custam 1,51× e não melhoram nada. 20 basta.

## O que decide a qualidade de um clipe

**O assunto, não a resolução.** Texturas contínuas (água, nuvens, neve, névoa, luz,
paisagem, desenho de traço chapado) aguentam até 512×320. Rosto em close, texto
legível, arquitetura detalhada e multidão falham em qualquer resolução.

**Formato do prompt não é alavanca** para a imagem — prosa solta, os campos do model
card e a convenção do template do ComfyUI deram o mesmo clipe. **Mas o áudio tem
sintaxe:** diálogo é `(personagem, descrição da voz (S1)) says: <d>[Portuguese] fala</d>`,
dentro de `integrated_multimodal_description` / `overall_soundscape` / `non_diegetic_music`.

**Diálogo em português funciona** (medido 2026-08-09): Whisper large-v3 devolveu as
falas escritas **palavra por palavra**, com `(S1)` e `(S2)` virando dois turnos
separados. Densidade que coube com folga: **2 falas em 5 s, 4 falas em 15 s**,
distribuídas ao longo do clipe. Descrever o timbre junto do personagem
(*"hoarse mocking voice"*) faz parte da sintaxe, não é enfeite.

## Durações longas: encadeamento de frame

O modelo é **FL2VA** — First-**Last** frame to Video+Audio. O nó
`MiniMaxH3ImageToVideo` aceita `first_frame` **e** `last_frame`, e desde
2026-08-09 as tools `submit_scene` e `generate_video` expõem os dois.

**O modelo obedece ao `last_frame`**, medido: com âncoras de cenas diferentes nas
duas pontas, SSIM do quadro final contra o alvo = **0,877**, contra a âncora de
partida = **0,503**. É o segundo número que prova — sem ele, dois quadros do mesmo
desenho já se pareceriam.

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
