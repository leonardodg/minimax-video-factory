# minimax-video-factory

Text → video **com áudio estéreo nativo**, local, numa RTX 4080 Laptop de 12 GB.
ComfyUI + MiniMax H3 (FL2VA, INT8) exposto por um servidor MCP.

> Este arquivo é carregado em **toda** sessão. O estado detalhado — o que está
> rodando, o que já foi medido, as pendências — está em **[`docs/HANDOFF.md`](docs/HANDOFF.md)**,
> e é lá que ele deve ser atualizado. Aqui ficam só as regras que não mudam.
>
> **Vai escrever prompt de desenho com fala?** A receita completa — molde,
> fichas de voz e de elenco, tratamento de emenda, o que já falhou — está em
> **[`docs/PROMPT_DESENHO_COM_FALA.md`](docs/PROMPT_DESENHO_COM_FALA.md)**.

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
linear, sem termo quadrático — **a 20 steps**. Com a Turbo LoRA a 6 steps são
**4,2 s/Mpf**, medido: 2,76× mais rápido (não os 3,3× da conta ingênua — há um
patamar de ~76 s por render, ver abaixo).

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
**Steps não são alavanca de qualidade** — 30 steps custam 1,51× e não melhoram
nada. 20 basta. Mas são a alavanca de **tempo**.

### ⚠️ O tempo NÃO é proporcional aos steps: há ~76 s de patamar

A conclusão antiga (*"1,51× para 1,5× de steps, logo o termo fixo é ~zero"*)
estava errada, e o erro era invisível no experimento que a gerou. Comparar 20
com 30 steps é um intervalo curto demais: um patamar de 76 s se dilui e o
resultado fica indistinguível de proporcionalidade pura. Descer a **6** steps é
o que o revela. Medido em 2026-08-11, mesma cena, mesma seed, 1024×576 · 124
frames (73,1 Mpf):

| steps | tempo | s/Mpf |
|---|---|---|
| 6 (turbo) | **310 s** | 4,2 |
| 20 | **857 s** | 11,7 |

```
tempo ≈ 76 s + 39 s por step        (ajuste pelos dois pontos)
```

Os 857 s batem com os 886 s históricos (3%), então a máquina não mudou.
**Consequência prática:** o ganho da Turbo LoRA é **2,76×**, não os 3,3× que a
proporcionalidade pura previa. E quanto mais curto o clipe, mais o patamar pesa.

### A Turbo LoRA: 6 steps no lugar de 20

```
submit_scene(prompt=..., turbo=True)     # 6 steps, workflow minimax_h3_t2v_turbo_api.json
submit_scene(prompt=...)                 # 20 steps, o caminho de sempre — default inalterado
```

Quatro coisas que não são óbvias:

- **Faixa útil é 4–8 steps.** 6–8 é visivelmente melhor que 4; acima de 8 não
  ganha nada. `strength` fica em 1,0.
- **`turbo_low_vram=True` (o default aqui) funde a LoRA nos pesos.** Pico de VRAM
  menor, mas num modelo quantizado parte do delta é arredondada fora — imagem
  mais macia. `False` aplica em tempo de execução: mais nítido, mais VRAM.
  **Nunca comparado lado a lado.**
- **O nó trata `pruned_int8_convrot` como caso especial.** Sem esse tratamento a
  LoRA sumiria em silêncio nos `fc2` (o kernel int8 fundido não passa pelo
  `forward` do módulo, então o hook de bypass nunca dispara). Conferir no log:
  `[MiniMaxH3TurboLoRA] pruned base [merge]: ... 51 adaln injected at run time`
  e `weight_patched=True → lora ACTIVE`.
- **Este ComfyUI (0.30.2) não tem `ModelSamplingAV`**, então o sampler do nó pisa
  vídeo (shift 12) e áudio (shift 3) em relógios separados por conta própria —
  o caminho `legacy dual-schedule` do log. É o que impede o áudio de quebrar com
  poucos steps. Ao subir a versão do ComfyUI, reconferir essa linha.

**O áudio sobrevive a 6 steps** (medido 2026-08-11, 2 falas em 5 s):

| | ROSY (S1) | BENTO (S2) |
|---|---|---|
| turbo 6 | 271 Hz | 131 Hz |
| baseline 20 | 250 Hz | 125 Hz |
| diferença | 1,4 semitons | 0,8 semitons |

As duas falas saíram palavra por palavra nos dois, nos mesmos tempos, e os
registros não se invadiram (quase uma oitava de separação). O turbo acrescentou
um `"É."` de 0,2 s no início — a 250 Hz, coerente com a ROSY, então é sílaba
extra, não troca de personagem. Lembrar que a **primeira fala do clipe** é
justamente onde a rodada 3 mediu a maior fragilidade.

⚠️ **A imagem a 6 steps não foi avaliada.** Tempo e áudio estão medidos; se o
desenho degrada, só olhando. É uma amostra de **um** clipe de 5 s.

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
distribuídas ao longo do clipe.

### A voz precisa de uma ficha travada, senão ela troca

Não existe `first_audio` — o nó só aceita imagem. Cada clipe **reinventa o timbre**
a partir do texto, e uma descrição vaga (*"bright childlike voice"*) deixa o modelo
escolher de novo a cada render. Medido por F0 (`~/bkp/minimax-night/voice_check.py`)
nas MESMAS seis falas, antes e depois:

| fala | quem | descrição vaga | ficha travada |
|---|---|---|---|
| primeira do vídeo | raposa (aguda) | **116 Hz** ❌ | **235 Hz** ✓ |
| depois da emenda | corvo (grave) | **254 Hz** ❌ | **113 Hz** ✓ |
| as outras quatro | — | ✓ | ✓ |

O defeito **não** é o clipe inteiro subir de tom: é `(S1)`/`(S2)` não ficarem
amarrados a vozes distintas — pior na primeira fala do clipe e logo depois de uma
emenda. A ficha travada zerou isso: o corvo ficou em 107 → 96 → 113 Hz ao longo de
30 s e atravessando um corte de cena (dispersão de 2,7 semitons, que é expressão).

A ficha vai **antes de qualquer ação**, declarada como invariante, com idade, sexo,
registro, textura, velocidade e sotaque:

```
Character voices, identical in every shot and never changing:
(S1) is <personagem>, a young girl's voice, high and clear, light and breathy,
     quick eager delivery, Brazilian Portuguese;
(S2) is <personagem>, an old man's voice, low and hoarse, dry and gravelly,
     slow amused delivery, Brazilian Portuguese.
```

⚠️ **Ao medir, olhe a dispersão POR PERSONAGEM, não por capítulo.** A média por
capítulo mistura os dois e acusa salto onde só houve distribuição desigual das
falas — quase virou conclusão errada em 2026-08-09.

⚠️ **A ficha reduz a deriva, não a elimina.** Numa segunda história (a mesma ficha,
roteiro que não foi usado para calibrá-la) a voz aguda ficou em 3,4 semitons de
dispersão, mas a grave foi a 7,7 — contra 17 semitons sem ficha. E o medidor **não
separa deriva de atuação**: a fala mais desviada era *"Isso não vai dar certo"*,
dita no instante em que o trenó dispara, onde o roteiro pede susto. O limite de
~4 semitons é heurística, não medida. **Teste que decide, ainda não feito:** uma
fala deliberadamente CALMA logo depois de uma emenda — se subir do mesmo jeito é
deriva, se ficar no registro era interpretação.

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
do zero. Três defesas: `non_diegetic_music` **idêntico, literalmente**, em todos os
capítulos (derrubou o degrau de 31,7 dB da rodada 2 para **0,2 dB**); a ficha de voz
travada, acima; e `unify_audio3.py` depois (ganho estático até −21 LUFS + limitador
+ fades de 80 ms).

**O degrau de áudio cresce com o número de capítulos**, mesmo com direção idêntica:
2 capítulos → 0,2 dB · 4 capítulos → 5,2 dB · 6 capítulos (rodada 2) → 8,3 a 31,7 dB.
Mais uma razão para preferir poucos clipes longos a muitos curtos.

### Emenda: três tratamentos, e o melhor não é o mais óbvio

- **Cruzamento** (`smooth_seam.py`): `xfade` no vídeo **e** `acrossfade` no áudio
  **pela mesma duração**. A proibição antiga do `acrossfade` valia para ele sozinho
  — aí ele encurta só o áudio e dessincroniza. Cruzando as duas trilhas igual, a
  sincronia se mantém (medido: 17 ms de diferença em 29,6 s, menos de meio quadro).
- **Corte de cena**: não encadear, e anunciar `Cut to a new shot from a different
  angle`. O que incomoda numa emenda encadeada não é a cena mudar — é ela ser
  *quase* a mesma e não exatamente; o olho perdoa um corte e não perdoa um plano
  que escorrega. Exige **ficha de elenco** (`cast_lock`), porque sem quadro
  atravessando a emenda nada garante que o personagem continue o mesmo.
- **Abrir em repouso**: o capítulo N já fechava parado, mas o N+1 abria em
  movimento — imagem contínua, movimento aos saltos. As duas pontas têm de ser
  repouso.

**Efeito colateral medido:** descrever os personagens em detalhe (a ficha de elenco)
faz o modelo **enquadrá-los mais perto** por conta própria. Resolveu de graça a
queixa de "o personagem ocupa 5% do quadro".

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

**Custom node novo:** clonar em `$CUSTOM_NODES_DIR` (host, bind-mount rw sobre
`/comfy/ComfyUI/custom_nodes`), instalar as deps no **python do ComfyUI**
(`/opt/conda/bin/python`, *não* o `/opt/mcp-venv` do servidor MCP — errar aqui
deixa o nó importável e quebrado), e recriar o container.
`scripts/install_custom_nodes.sh` faz os três. Antes do bind-mount, `custom_nodes`
vivia dentro da imagem e todo `build` apagava tudo sem avisar.

**Tool MCP nova custa 4 lugares:** `catalog.COMMAND_NAMES`, a lista canônica de
`unit_registry`, a tabela do `README.md`, e rodar `scripts/generate_commands.py`
(que escreve **dois** arquivos por tool). Parâmetro novo numa tool existente não
dispara esse ritual — só regerar os docs.
