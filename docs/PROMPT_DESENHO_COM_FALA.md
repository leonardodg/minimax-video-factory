# Como escrever prompt de desenho animado com fala (MiniMax H3)

Receita destilada da **rodada 3** (2026-08-09): 5 sondagens + 14 renders de
produção, ~7 h de GPU. Tudo aqui é medido ou marcado como não medido.

Números de máquina (teto de VRAM, tempo por render) estão no
[`CLAUDE.md`](../CLAUDE.md). Aqui é só **como escrever o prompt**.

---

## O molde

Três campos, do model card. Copie a estrutura inteira em **todo** capítulo.

```
integrated_multimodal_description:
<ÂNCORA DE ESTILO>. Scene: <cenário>. <FICHA DE ELENCO> <FICHA DE VOZ>
<plano + ação, uma frase por batida>. <FECHAMENTO EM REPOUSO>
(<personagem + ficha de voz> (S1)) says: <d>[Portuguese] <fala></d>
(<personagem + ficha de voz> (S2)) says: <d>[Portuguese] <fala></d>

overall_soundscape:
<ambiente + som físico da ação. Sem diálogo, sem canto.>

non_diegetic_music:
<A MESMA FRASE, LITERALMENTE IGUAL, em todos os capítulos da história.>
```

Cinco blocos precisam ser **idênticos, palavra por palavra, em todos os
capítulos**: âncora de estilo, cenário, ficha de elenco, ficha de voz e
`non_diegetic_music`. O modelo **não enxerga os capítulos anteriores** — no
máximo um quadro. Tudo o que não for reafirmado, ele reinventa.

---

## As duas fichas — o que a rodada 3 acrescentou

### Ficha de voz

**Sem ela a voz troca.** Não existe `first_audio`: o nó só aceita imagem, então
cada clipe inventa o timbre a partir do texto. Medido por F0 nas mesmas seis
falas, com descrição vaga (*"bright childlike voice"*) contra ficha travada:

| | vaga | travada |
|---|---|---|
| primeira fala do vídeo (raposa, aguda) | **116 Hz** ❌ | **235 Hz** ✓ |
| primeira fala depois da emenda (corvo, grave) | **254 Hz** ❌ | **113 Hz** ✓ |
| as outras quatro | ✓ | ✓ |

O defeito **não** é o clipe subir de tom — é `(S1)` e `(S2)` não ficarem
amarrados a vozes distintas, e falha justamente na **primeira fala do clipe** e
**logo depois de uma emenda**: os dois lugares onde o ouvinte mais repara.

Seis atributos, sempre: **idade · sexo · registro · textura · velocidade · idioma**.

```
Character voices, identical in every shot and never changing:
(S1) is the small orange fox, a young girl's voice, high and clear, light and
     breathy, quick eager delivery, Brazilian Portuguese;
(S2) is the black crow, an old man's voice, low and hoarse, dry and gravelly,
     slow amused delivery, Brazilian Portuguese.
```

**Escolha vozes que não se confundem** — uma aguda e uma grave. Duas vozes
próximas dão ao modelo a chance de trocá-las.

⚠️ **Reduz a deriva, não elimina.** Numa história que não foi usada para
calibrar, a voz aguda ficou em 3,4 semitons de dispersão e a grave em 7,7
(contra 17 sem ficha). E parte disso pode ser **atuação**: a fala mais desviada
era *"Isso não vai dar certo"*, dita no instante em que o trenó dispara.

### Ficha de elenco

Obrigatória quando a emenda é **corte** (sem quadro atravessando). Enquanto havia
encadeamento, a aparência vinha de graça no `first_frame`.

```
The same characters appear in every shot, unchanged: a small young red fox,
bright orange coat, white chest and white tail tip, black legs, large dark eyes;
a large glossy black crow with a heavy dark beak and ragged wing feathers.
```

**Efeito colateral que resolveu outro problema:** descrever os personagens em
detalhe faz o modelo **enquadrá-los mais perto** por conta própria. A queixa de
"o personagem ocupa 5% do quadro" sumiu sem eu tocar no tamanho de plano.

---

## Diálogo

**Sintaxe:** `(<personagem + ficha de voz> (S1)) says: <d>[Portuguese] <fala></d>`

Whisper large-v3 devolveu as falas escritas **palavra por palavra**, com os
turnos separados. Português funciona (o modelo suporta 11 idiomas).

**Densidade que coube com folga:**

| duração | falas |
|---|---|
| 5,17 s | 2 |
| 7,29 s | 2 |
| 15,08 s | 4 |

Em 15 s as quatro falas se distribuem ao longo do clipe inteiro, com respiro.
Não amontoam no começo — **desde que o clipe esteja dentro da faixa treinada**
(ver o fracasso do render de 30 s, abaixo).

**Batida com fala pede plano médio.** Escrever `wide shot` e `the camera pans
gently` é vocabulário de paisagem: as falas se ouvem e não se vê ninguém falando.

```
medium shot, <personagem> large in frame: <ação>, mouth moving as it speaks
medium close shot of <personagem> large in frame, <o outro> blurred behind it
```

O plano aberto fica para as batidas **mudas** — respiro e paisagem.

---

## A emenda

Um vídeo de 30 s é **dois clipes de 15 s**, porque a faixa treinada acaba em
362 frames. A emenda é o problema central, e há três tratamentos.

### 1. Corte de cena — o que a rodada 3 usou nas entregas

Não encadeia. O capítulo 2 abre com:

```
Cut to a new shot from a different angle in a new part of the location: <ação>
```

**Por que funciona:** o que incomoda numa emenda encadeada não é a cena mudar —
é ela ser **quase** a mesma e não exatamente. O olho perdoa um corte para outro
plano; não perdoa um plano que escorrega. É montagem, e o espectador aceita sem
pensar. Exige a ficha de elenco.

### 2. Encadeamento, com repouso nas duas pontas

Último quadro do capítulo N vira `first_frame` do N+1. A imagem fica contínua,
mas **o movimento salta** se só uma ponta for de repouso:

```
fim do capítulo N:      The shot settles and comes to rest at the end, the
                        movement slowing to a stop before the clip ends
início do capítulo N+1: The shot opens held and completely still, continuing a
                        pose already in place, and only then does the movement begin.
```

### 3. Cruzamento — pós-processo, zero GPU

`xfade` no vídeo **e** `acrossfade` no áudio **pela mesma duração** (0,6 s).
Como os dois quadros da emenda encadeada já são a mesma imagem, não há dissolve
aparente: ele suaviza o salto de movimento e a troca de timbre.

> A proibição antiga do `acrossfade` valia para ele **sozinho** — aí encurta só o
> áudio e dessincroniza. Cruzando as duas trilhas igual, a sincronia se mantém:
> medido 17 ms de diferença em 29,6 s, menos de meio quadro.

Implementado em `~/bkp/minimax-night/smooth_seam.py`.

---

## Áudio

**`non_diegetic_music` idêntico, literalmente, em todos os capítulos.** É a
alavanca principal, e é de graça:

| capítulos | degrau de nível bruto |
|---|---|
| 2 | **0,2 – 1,2 dB** |
| 4 | 5,2 dB |
| 6 (rodada 2) | 8,3 – 31,7 dB |

Mais uma razão para preferir poucos clipes longos a muitos curtos.

**Não peça silêncio num capítulo.** Metade do degrau da rodada 2 foi autorada:
prompts que pediam *"then quiet"* num capítulo e estouro no outro.

**Alegria também é trilha.** Trocar as falas para engraçadas e manter *"a slow
solo flute, quiet and steady"* entrega comédia com música de despedida. A direção
musical tem de mudar junto: pizzicato saltitante, valsa de acordeão, clarinete.

Depois: `unify_audio3.py` — ganho **estático** até −21 LUFS (não `loudnorm`, que
comprime e faz bombear), limitador, fades de 80 ms, vídeo copiado bit a bit.

---

## O que NÃO funcionou

### Keyframes vindos de um passe barato — o erro mais caro da rodada

Renderizar a história a 512×320 para extrair os quadros de emenda, ampliar para
1024×576 e prender os capítulos finais a eles com `first_frame`+`last_frame`.

**O mecanismo é sadio — a fonte é que estava errada.** Provado em 2026-08-09
(rodada 3.1): com os dois âncoras vindos de um render BOM em resolução nativa, o
clipe saiu de uma encosta vazia, criou a entrada dos dois personagens, deu uma
troca de falas e aterrissou no âncora de chegada — com a nitidez do melhor
material da rodada.

Com a pré-viz barata, a mesma técnica falha **duas vezes ao mesmo tempo**:

- **Congela a ação.** Os capítulos finais são obrigados a aterrissar onde a
  pré-viz derivou, não onde o roteiro manda. Em 29 s a raposa não saiu do lugar,
  não subiu a encosta e não viu o sol nascer. **A pré-viz vira a autora.**
- **Borra a imagem.** Um alvo esticado de 512 para 1024 não tem detalhe para o
  modelo interpolar em direção, e a moleza contamina o clipe inteiro. Foi a única
  variante da rodada a 1024×576 e levou a **pior nota humana** nos quatro
  capítulos — resolução alta não salva âncora ruim.

Custou 116 min contra 42 min do corte de cena, e entregou menos.

> **Regra:** âncora de `last_frame` vem de um quadro em **resolução nativa**, de um
> render que já ficou bom. Nunca de passe barato, nunca ampliado.

### O roteiro inteiro num render só (736 frames)

Cabe na VRAM (84,4 M a 448×256) e renderiza. Degrada de **dois** jeitos ao mesmo
tempo, os dois progressivos:

- **A cor.** Manchas magenta e verde que crescem; aos 20 s um corvo preto ficou
  verde. Composição e narrativa continuam de pé.
- **O tempo do áudio.** As seis falas escritas para 30 s couberam nos primeiros
  17 s; depois, 13 s de silêncio e um fragmento solto no fim.

Não é VRAM. Passar de **362 frames** é fora de especificação.

### Descrição de voz vaga

Ver a ficha de voz. `"bright childlike voice"` deixa o modelo escolher de novo.

### Casar nível e achar que resolveu a voz

Nível não é timbre. O H1 tinha 0,2 dB de degrau **e** a voz do corvo saltando de
95 para 254 Hz. Uma métrica boa pode esconder o defeito que importa.

---

## Elenco: quem pode falar

Veredito humano sobre 16 clipes da rodada 3, e ele é consistente:

| personagem | boca? | sincronia vista | veredito |
|---|---|---|---|
| raposa | boca de verdade | **a melhor** | "voz boa e sincronizada" |
| corvo | bico | funciona | ok |
| gaivota | bico | **falhou** | "não tem sincronia, horrível" |
| robô, caracol | **nenhuma** | inexistente | "não tem bocas" |
| **faroleiro (humano)** | boca | **falhou** | o pior clipe da rodada |

Duas regras que saem daí:

1. **Para diálogo visível, escale personagens com boca.** Focinho > bico >
   carcaça sem boca. A raposa teve a melhor sincronia de toda a rodada, e a
   boca dela **fecha no meio da frase** — articulação de consoante, não uma
   boca batendo solta.
2. **Evite rosto humano falando em plano fechado.** É a categoria que o
   `README.md` já listava como das mais difíceis em qualquer resolução, e a
   história do faroleiro confirmou: embaçado, sem sincronia, e no fim o
   personagem "nem parece um marinheiro".

## Enquadramento muda entre renders, nunca dentro de um

Erro cometido na rodada 3: dentro do MESMO render de 15 s, a batida 1 pedia
`medium shot, the keeper large in frame` e a batida 2 pedia `medium close shot of
the seagull large in frame`. O modelo **não corta — ele deforma a escala**, e a
gaivota "fica grande do nada".

Todas as batidas de um mesmo clipe devem compartilhar o tamanho de plano.
Mudança de enquadramento pertence à fronteira entre renders.

## Movimento compete com nitidez

O usuário notou sem ser perguntado: o capítulo com pouca movimentação saiu bom, o
com muita coisa se mexendo ao mesmo tempo saiu pior. Parece ser o **número de
elementos independentes em movimento**, não a velocidade — um trenó descendo
rápido com um só assunto ficou nítido, enquanto raposa andando + corvo voando +
câmera acompanhando degradou.

## Como verificar sem depender de ouvir tudo

| pergunta | ferramenta |
|---|---|
| as falas saíram e no tempo certo? | Whisper large-v3, `device="cpu"` (a GPU está renderizando) |
| a voz do personagem se manteve? | `voice_check.py` — F0 por fala |
| o nível bate entre capítulos? | `unify_audio3.py` imprime antes/depois |
| a imagem degradou? | grade de quadros com `ffmpeg select+tile`, e olhar |

⚠️ **Dispersão de F0 POR PERSONAGEM, nunca por capítulo.** A média por capítulo
mistura os dois personagens e acusa salto onde só houve distribuição desigual das
falas. Quase virou conclusão errada nesta rodada.

### Nitidez NÃO é medível por métrica simples — não tente de novo

Duas tentativas, as duas **anticorrelacionadas** com o julgamento humano sobre os
mesmos 16 clipes:

| métrica | o que deu |
|---|---|
| variância do laplaciano | clipes de 512×320 ("qualidade pior") no topo; o preferido do usuário quase no fundo |
| acutância de borda (p95 do gradiente) | mesma inversão |

O motivo é do estilo: num desenho de **cor chapada**, energia de alta frequência
mede **granulado**, não detalhe. O clipe ruidoso ganha pontos pelo ruído e o clipe
limpo perde pontos pelas grandes áreas lisas — que são justamente o que o faz
bonito. O que a pessoa chama de "nitidez" aqui é ausência de artefato e coerência
de forma: propriedade estrutural, não de sinal.

O script está em `~/bkp/minimax-night/sharpness.py` com as duas versões
documentadas. **Guardado como resultado negativo**: o olho continua sendo o
instrumento, e não vale gastar rodada tentando automatizar esse julgamento.

---

## A emenda não é a culpada pela voz — o erro é esporádico

Testado em 2026-08-09 (rodada 3.1) com a mesma voz grave falando **calma** dos dois
lados de uma emenda:

```
capítulo 1  corvo  "O sol ainda vai demorar pra nascer."   213 Hz  ❌
capítulo 2  corvo  "A neve vai durar a semana toda."       103 Hz  ✓
   (logo depois da emenda)
```

**A fala depois da emenda saiu perfeita.** Isso elimina a emenda como causa, e
deixa "atuação" como explicação mais provável para a dispersão medida antes — a
fala mais desviada era dita no instante em que um trenó dispara.

**Mas o erro de amarração continua, esporádico:** com a ficha ativa, cerca de
**2 falas em 15** caem no registro errado, sem relação com posição no vídeo nem
com emenda.

> Consequência prática: **uma tomada com voz errada se re-rola, não se reescreve.**
> Trocar a seed e refazer aquele clipe é o conserto. Mais engenharia de prompt não
> resolve o que é variação de amostragem.

## Em aberto

- **Corte seco, cruzado ou dissolve** — julgamento humano, não medida. Existem
  seis tratamentos da mesma história em `output/rodada3_final/H1_raposa_*`.
- **Os ~2 em 15 de voz errada** têm remédio melhor que re-rolar a seed? Não
  investigado.
- **1024×576 com âncora nativa** — a variante B nunca foi testada com âncora bom
  *na resolução dela*. O V2 provou o mecanismo a 704×384; se a moleza era só do
  âncora ampliado, 1024×576 com âncora nativo deveria ser o melhor de todos.
