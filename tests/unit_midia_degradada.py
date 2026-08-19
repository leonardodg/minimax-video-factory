#!/usr/bin/env python3
"""Mídia que o pipeline recusava por formato, não por conteúdo.

Duas causas medidas na corrida de 2026-08-18, juntas responsáveis por ~59 dos
66 posts que pararam na DLQ:

  vision failed: 400 Bad Request     imagem `.webp` -- o decodificador do
                                     Ollama nao le esse formato, e o Instagram
                                     serve boa parte dos posts assim
  Transcription failed:              video SEM faixa de audio -- o PyAV pede a
  tuple index out of range           faixa pelo indice e levanta IndexError

Nas duas o post morria por uma questao de embalagem, com o conteudo intacto do
lado de dentro.

    uv run python tests/unit_midia_degradada.py
"""
from __future__ import annotations

import base64
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FAIL = 0


def ok(label): print(f"  [ok]   {label}")


def bad(label):
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


try:
    from PIL import Image
except ImportError:
    sys.exit(
        "\n  ERRO: Pillow nao esta instalado neste interpretador.\n"
        f"  ({sys.executable})\n\n"
        "  Ela vem junto com o instagrapi, que e' dependencia do projeto -- se\n"
        "  falta aqui, o interpretador esta' errado, nao o codigo.\n"
        "  Rode assim:  uv run python tests/unit_midia_degradada.py\n"
    )

from minimax_mcp import llm, transcriber  # noqa: E402

print("== unit_midia_degradada: .webp vira JPEG antes de ir para o Ollama ==")

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # Uma imagem de verdade, nos dois formatos, com o MESMO conteudo.
    origem = Image.new("RGB", (64, 48), (200, 30, 90))

    caminho_webp = tmp / "post.webp"
    origem.save(caminho_webp, format="WEBP")
    b64 = llm.imagem_para_b64(str(caminho_webp))
    convertida = Image.open(io.BytesIO(base64.b64decode(b64)))

    if convertida.format == "JPEG":
        ok("webp -> JPEG, que e' o que o Ollama aceita")
    else:
        bad(f"saiu como {convertida.format}; o Ollama devolve 400 para webp")

    if convertida.size == (64, 48):
        ok("a conversao preserva as dimensoes da imagem")
    else:
        bad(f"dimensoes mudaram: {convertida.size}")

    # O caminho comum nao pode pagar pela excecao: JPEG entra e sai igual.
    caminho_jpg = tmp / "post.jpg"
    origem.save(caminho_jpg, format="JPEG", quality=90)
    if base64.b64decode(llm.imagem_para_b64(str(caminho_jpg))) == caminho_jpg.read_bytes():
        ok("JPEG passa direto, byte a byte -- sem reencodar de graca")
    else:
        bad("o JPEG foi reencodado sem necessidade")

    # PNG com transparencia: `save(JPEG)` levanta OSError sem o convert("RGB").
    caminho_png = tmp / "transparente.png"
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(caminho_png, format="PNG")
    try:
        llm.imagem_para_b64(str(caminho_png))
        ok("PNG com canal alfa nao levanta")
    except Exception as exc:
        bad(f"alfa quebrou a normalizacao: {exc!r}")

    # O formato manda, nao a extensao: entre os posts que falharam havia um
    # `.heic` cujos bytes eram JPEG.
    mentiroso = tmp / "mentiroso.heic"
    mentiroso.write_bytes(caminho_jpg.read_bytes())
    if base64.b64decode(llm.imagem_para_b64(str(mentiroso))) == caminho_jpg.read_bytes():
        ok("decide pelos BYTES, nao pela extensao mentirosa")
    else:
        bad("deixou a extensao decidir; um .heic que era JPEG seria reencodado")

    # Arquivo que nao e' imagem: manda como esta' e deixa o Ollama recusar --
    # inventar um erro novo aqui so' trocaria a mensagem do diagnostico.
    lixo = tmp / "lixo.jpg"
    lixo.write_bytes(b"nao sou uma imagem")
    try:
        if base64.b64decode(llm.imagem_para_b64(str(lixo))) == b"nao sou uma imagem":
            ok("arquivo ilegivel segue como esta', sem levantar")
        else:
            bad("mexeu num arquivo que nao conseguiu ler")
    except Exception as exc:
        bad(f"levantou em vez de degradar: {exc!r}")

print("== unit_midia_degradada: video sem audio e' 'sem fala', nao falha ==")

try:
    import av
except ImportError:
    bad("PyAV ausente -- ele vem com o faster-whisper; interpretador errado?")
    av = None

if av is not None:
    with tempfile.TemporaryDirectory() as tmp:
        mudo = Path(tmp) / "mudo.mp4"
        # Um mp4 legitimo com UMA faixa de video e nenhuma de audio -- que e'
        # exatamente o que o ffprobe mostrou nos posts que falharam.
        with av.open(str(mudo), mode="w") as c:
            fluxo = c.add_stream("mpeg4", rate=5)
            fluxo.width, fluxo.height, fluxo.pix_fmt = 32, 32, "yuv420p"
            for _ in range(5):
                quadro = av.VideoFrame(32, 32, "yuv420p")
                for pacote in fluxo.encode(quadro):
                    c.mux(pacote)
            for pacote in fluxo.encode():
                c.mux(pacote)

        if transcriber.tem_faixa_de_audio(mudo) is False:
            ok("detecta a AUSENCIA de faixa de audio")
        else:
            bad(f"disse {transcriber.tem_faixa_de_audio(mudo)!r} para um video mudo")

        # O terceiro estado: nao deu para saber. Colapsar isso em False faria um
        # arquivo corrompido virar, em silencio, um post "sem fala".
        quebrado = Path(tmp) / "quebrado.mp4"
        quebrado.write_bytes(b"isto nao e' um container")
        if transcriber.tem_faixa_de_audio(quebrado) is None:
            ok("arquivo ilegivel devolve None, distinto de 'nao tem audio'")
        else:
            bad("confundiu 'nao consegui abrir' com 'nao tem audio'")

        # O que decide o post: ok=True e texto vazio entrega o video a' cadeia
        # tela -> legenda do ig_worker, em vez de matar a mensagem.
        r = transcriber.AudioTranscriber(model_size="small", device="cpu").transcribe(mudo)
        if r.get("ok") and r.get("text") == "" and r.get("sem_audio"):
            ok("video mudo -> ok=True com texto vazio (segue para tela/legenda)")
        else:
            bad(f"transcribe devolveu {r!r}; com ok=False o post morre no ig_worker:243")

        faltando = Path(tmp) / "nao_existe.mp4"
        if transcriber.AudioTranscriber(device="cpu").transcribe(faltando).get("ok") is False:
            ok("arquivo ausente continua sendo falha de verdade")
        else:
            bad("arquivo inexistente passou como sucesso")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
