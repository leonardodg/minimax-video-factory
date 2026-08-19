#!/usr/bin/env python3
"""Unit tests for ig_worker.py — injected download/transcribe/describe/ingest."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


from minimax_mcp import ig_worker

MESSAGE = {
    "ig_pk": "1001", "media_type": "video",
    "url": "https://www.instagram.com/p/1001/", "title": "t",
    "owner_username": "u", "collection_name": None, "status": "queued",
}

print("== unit_ig_worker: classify_file ==")
if ig_worker.classify_file("x.mp4") == "video" and ig_worker.classify_file("x.jpg") == "image":
    ok("classify_file splits video/image by extension")
else:
    bad(f"classify_file = {ig_worker.classify_file('x.mp4')}/{ig_worker.classify_file('x.jpg')}")

print("== unit_ig_worker: process_message (video) ==")


def dl_video(msg):
    assert msg == MESSAGE
    return {"ok": True, "filepath": "/tmp/x.mp4"}


def tr(path):
    assert path == "/tmp/x.mp4"
    return {"ok": True, "text": "transcrito", "language": "pt"}


def ingest_ok(text, **kw):
    assert text == "transcrito"
    assert kw["doc_type"] == "video" and kw["ig_pk"] == "1001"
    return {"ok": True, "document_id": 42}


res = ig_worker.process_message(
    MESSAGE, download=dl_video, transcribe=tr, describe=None, ingest=ingest_ok
)
if res["status"] == "done" and res["document_id"] == 42 and res["kind"] == "video":
    ok("video message -> transcribe -> ingest -> done")
else:
    bad(f"video process = {res!r}")

print("== unit_ig_worker: process_message (image via describe) ==")


def dl_img(msg):
    return {"ok": True, "filepath": "/tmp/x.jpg"}


def describe(path):
    assert path == "/tmp/x.jpg"
    return {"ok": True, "text": "descrição da foto"}


def ingest_img(text, **kw):
    assert text == "descrição da foto"
    assert kw["doc_type"] == "image"
    return {"ok": True, "document_id": 43}


res = ig_worker.process_message(
    MESSAGE, download=dl_img, transcribe=None, describe=describe, ingest=ingest_img
)
if res["status"] == "done" and res["kind"] == "image":
    ok("image message -> describe -> ingest -> done")
else:
    bad(f"image process = {res!r}")

print("== unit_ig_worker: process_message (carousel -> first item) ==")


def dl_carousel(msg):
    assert msg["media_type"] == "carousel"
    return {"ok": True, "filepath": "/tmp/first.mp4"}


def tr_first(path):
    assert path == "/tmp/first.mp4"
    return {"ok": True, "text": "transcrito", "language": "pt"}


res = ig_worker.process_message(
    {**MESSAGE, "media_type": "carousel"},
    download=dl_carousel, transcribe=tr_first, describe=describe, ingest=ingest_ok,
)
if res["status"] == "done" and res["kind"] == "video":
    ok("carousel message is processed via its first downloaded item")
else:
    bad(f"carousel process = {res!r}")

print("== unit_ig_worker: process_message (failures) ==")
if ig_worker.process_message(MESSAGE, download=lambda m: {"ok": False, "error": "x"},
                             transcribe=tr, describe=describe, ingest=ingest_ok)["status"] == "error":
    ok("download failure -> error status")
else:
    bad("download failure not reported")

if ig_worker.process_message(MESSAGE, download=dl_video,
                             transcribe=lambda p: {"ok": False, "error": "t"},
                             describe=describe, ingest=ingest_ok)["status"] == "error":
    ok("transcribe failure -> error status")
else:
    bad("transcribe failure not reported")

print("== unit_ig_worker: apply_command ==")
state = {"paused": True}
if ig_worker.apply_command(state, "start") == "resumed" and state["paused"] is False:
    ok("start resumes a paused worker")
else:
    bad(f"apply_command(start) = {ig_worker.apply_command(state, 'start')}")
if ig_worker.apply_command(state, "stop") == "paused" and state["paused"] is True:
    ok("stop pauses a running worker")
else:
    bad("apply_command(stop) did not pause")

# O booleano NÃO pausava nada: era lido só numa linha de log, e o worker seguia
# consumindo depois de responder "paused". Custou um OOM real em 2026-08-10 --
# a GPU foi entregue a um reprocessamento confiando numa pausa que não existia.
# O que prova a pausa é o cancelamento da assinatura, não o booleano.
class CanalFalso:
    def __init__(self):
        self.cancelados = []
        self.consumos = []
        self._n = 0

    def basic_cancel(self, tag):
        self.cancelados.append(tag)

    def basic_consume(self, queue, on_message_callback):
        self._n += 1
        self.consumos.append(queue)
        return f"tag{self._n}"


canal = CanalFalso()
st = {"paused": False, "canal": canal, "tag": "tag0", "on_work": lambda *a: None}

ig_worker.apply_command(st, "stop")
if canal.cancelados == ["tag0"] and st["tag"] is None:
    ok("stop CANCELA a assinatura da fila de trabalho, não só marca um booleano")
else:
    bad(f"stop não cancelou: cancelados={canal.cancelados} tag={st['tag']!r}")

ig_worker.apply_command(st, "start")
if canal.consumos == [ig_worker.ig_queue.QUEUE] and st["tag"] == "tag1":
    ok("start volta a assinar a fila de trabalho")
else:
    bad(f"start não reassinou: consumos={canal.consumos} tag={st['tag']!r}")

# Comando repetido não pode cancelar duas vezes nem duplicar o consumo.
ig_worker.apply_command(st, "start")
if canal.consumos == [ig_worker.ig_queue.QUEUE]:
    ok("start repetido não duplica a assinatura")
else:
    bad(f"start repetido duplicou: {canal.consumos}")

ig_worker.apply_command(st, "stop")
ig_worker.apply_command(st, "stop")
if canal.cancelados == ["tag0", "tag1"]:
    ok("stop repetido não cancela duas vezes")
else:
    bad(f"stop repetido cancelou demais: {canal.cancelados}")

# Sem canal (testes, ou comando antes da conexão) o booleano ainda vale.
st2 = {"paused": False, "canal": None, "tag": None}
if ig_worker.apply_command(st2, "stop") == "paused" and st2["paused"] is True:
    ok("sem canal, apply_command não quebra")
else:
    bad("apply_command quebrou sem canal")

print("== unit_ig_worker: _download_targets ==")
class FakeRes:
    def __init__(self, media_type, pk, video_url=None, thumbnail_url=None):
        self.media_type = media_type
        self.pk = pk
        # O instagrapi entrega estas duas em todo recurso de álbum; são elas que
        # permitem baixar sem re-resolver o recurso na API pública.
        self.video_url = video_url if video_url is not None else (
            f"https://cdn/{pk}.mp4" if media_type == 2 else None
        )
        self.thumbnail_url = thumbnail_url if thumbnail_url is not None else (
            f"https://cdn/{pk}.jpg" if media_type != 2 else None
        )
class FakeInfo:
    def __init__(self, media_type, resources=()):
        self.media_type = media_type
        self.resources = list(resources)
class FakeClient:
    def __init__(self, info):
        self._info = info
    def media_info(self, pk):
        return self._info

r = ig_worker._download_targets(FakeClient(FakeInfo(1)), "111")
if r == [("photo_download", "111")]:
    ok("single photo -> [photo_download(pk)]")
else:
    bad(f"single photo targets = {r!r}")

r = ig_worker._download_targets(FakeClient(FakeInfo(2)), "222")
if r == [("clip_download", "222")]:
    ok("single video -> [clip_download(pk)]")
else:
    bad(f"single video targets = {r!r}")

# Carrossel baixa POR URL. Baixar por pk fazia o instagrapi chamar
# media_info(resource_pk) por dentro, não achar (recurso de álbum não é mídia
# autônoma na API privada), cair no GraphQL público, levar 401 e entrar em laço
# na página de login. Foi o que bloqueou o sync em 2026-08-10.
car = FakeInfo(8, [FakeRes(1, "p1"), FakeRes(2, "v2"), FakeRes(1, "p3")])
r = ig_worker._download_targets(FakeClient(car), "888")
if r == [
    ("photo_download_by_url", "https://cdn/p1.jpg"),
    ("video_download_by_url", "https://cdn/v2.mp4"),
    ("photo_download_by_url", "https://cdn/p3.jpg"),
]:
    ok("carousel -> download by URL, one pair per resource, video vs photo")
else:
    bad(f"carousel targets = {r!r}")

if not any(m in ("clip_download", "photo_download") for m, _ in r):
    ok("carousel never uses the pk methods that fall back to the public API")
else:
    bad(f"carousel still routes through a pk download: {r!r}")

car_img = FakeInfo(8, [FakeRes(1, "p1"), FakeRes(1, "p2")])
if ig_worker._download_targets(FakeClient(car_img), "888") == [
    ("photo_download_by_url", "https://cdn/p1.jpg"),
    ("photo_download_by_url", "https://cdn/p2.jpg"),
]:
    ok("carousel with only images -> photo_download_by_url per photo")
else:
    bad(f"carousel img targets = {ig_worker._download_targets(FakeClient(car_img), '888')!r}")

# Recurso sem URL: cai no caminho antigo em vez de sumir do álbum. Pode bater na
# API pública, mas um álbum incompleto em silêncio é pior.
car_nourl = FakeInfo(8, [FakeRes(2, "v9", video_url="", thumbnail_url="")])
if ig_worker._download_targets(FakeClient(car_nourl), "888") == [("clip_download", "v9")]:
    ok("resource without url falls back to the pk method instead of vanishing")
else:
    bad(f"no-url resource = {ig_worker._download_targets(FakeClient(car_nourl), '888')!r}")

if ig_worker._download_targets(FakeClient(FakeInfo(8, [])), "888") == [("photo_download", "888")]:
    ok("empty carousel -> [photo_download(pk)]")
else:
    bad(f"empty carousel targets = {ig_worker._download_targets(FakeClient(FakeInfo(8, [])), '888')!r}")

print("== unit_ig_worker: _default_download downloads every resource ==")
class FakeClientDownload(FakeClient):
    def __init__(self, info):
        super().__init__(info)
        self.calls = []
    def photo_download(self, pk, folder=""):
        self.calls.append(("photo_download", pk))
        p = Path(folder) / f"fake_{pk}.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        return str(p)
    def clip_download(self, pk, folder=""):
        self.calls.append(("clip_download", pk))
        p = Path(folder) / f"fake_{pk}.mp4"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        return str(p)
    # As duas rotas por URL, que é como carrossel passa a ser baixado. O nome do
    # arquivo sai da URL, como o instagrapi faz quando `filename` vem vazio.
    def photo_download_by_url(self, url, filename="", folder=""):
        self.calls.append(("photo_download_by_url", url))
        p = Path(folder) / f"fake_{Path(url).name}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        return str(p)
    def video_download_by_url(self, url, filename="", folder=""):
        self.calls.append(("video_download_by_url", url))
        p = Path(folder) / f"fake_{Path(url).name}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        return str(p)

from minimax_mcp import ig_sync

_orig_make_client = ig_sync.make_client
ig_sync.make_client = lambda: FakeClientDownload(FakeInfo(8, [FakeRes(1, "p1"), FakeRes(2, "v2")]))
try:
    res = ig_worker._default_download({**MESSAGE, "media_type": "carousel", "ig_pk": "999", "url": ""})
finally:
    ig_sync.make_client = _orig_make_client
fps = res.get("filepaths") or []
if res.get("ok") and len(fps) == 2 and fps[0].endswith("fake_p1.jpg") and fps[1].endswith("fake_v2.mp4"):
    ok("carousel download returns all filepaths (p1.jpg + v2.mp4)")
else:
    bad(f"carousel download = {res!r}")

# single video still works and exposes filepaths = [filepath]
ig_sync.make_client = lambda: FakeClientDownload(FakeInfo(2))
try:
    res = ig_worker._default_download({**MESSAGE, "media_type": "video", "ig_pk": "555", "url": ""})
finally:
    ig_sync.make_client = _orig_make_client
if res.get("ok") and res["filepath"] == res["filepaths"][0] and res["filepath"].endswith("fake_555.mp4"):
    ok("single video download keeps filepath == filepaths[0]")
else:
    bad(f"single video download = {res!r}")

print("== unit_ig_worker: process_message carousel concatenates descriptions ==")

def dl_carousel_multi(msg):
    assert msg["media_type"] == "carousel"
    return {"ok": True, "filepath": "/tmp/c1.jpg", "filepaths": ["/tmp/c1.jpg", "/tmp/c2.jpg"]}

def describe_structured(path):
    return {
        "ok": True, "text": f"conteudo {path}",
        "tipo": "dica", "categoria": "courses", "conteudo_principal": f"conteudo {path}",
    }

def ingest_carousel(text, **kw):
    assert text == "conteudo /tmp/c1.jpg\n\nconteudo /tmp/c2.jpg", f"text={text!r}"
    assert kw["doc_type"] == "image"
    assert "categoria:courses" in (kw.get("extra_tags") or []), f"tags={kw.get('extra_tags')!r}"
    return {"ok": True, "document_id": 70}

res = ig_worker.process_message(
    {**MESSAGE, "media_type": "carousel"},
    download=dl_carousel_multi, transcribe=None, describe=describe_structured, ingest=ingest_carousel,
)
if res["status"] == "done" and res["kind"] == "image" and len(res["filepaths"]) == 2:
    ok("carousel -> describe each photo -> concatenated text + categoria tag")
else:
    bad(f"carousel process = {res!r}")

print("== unit_ig_worker: describe-only contract still works ==")

def dl_single(msg):
    return {"ok": True, "filepath": "/tmp/x.jpg"}

def describe_legacy(path):
    return {"ok": True, "text": "descrição da foto"}

def ingest_legacy(text, **kw):
    assert text == "descrição da foto"
    assert kw["doc_type"] == "image"
    return {"ok": True, "document_id": 71}

res = ig_worker.process_message(
    MESSAGE, download=dl_single, transcribe=None, describe=describe_legacy, ingest=ingest_legacy,
)
if res["status"] == "done" and res["kind"] == "image":
    ok("describe returning only text (no conteudo_principal) still ingested")
else:
    bad(f"legacy describe process = {res!r}")

print("== unit_ig_worker: a tag de coleção é namespeada ==")

captured = {}


def _ingest_capture(text, **kw):
    captured.update(kw)
    return {"ok": True, "document_id": 71}


def _describe_plain(path):
    return {"ok": True, "text": "x", "tipo": "dica",
            "categoria": "outros", "conteudo_principal": "x"}


ig_worker.process_message(
    {**MESSAGE, "media_type": "carousel", "collection_name": "Dev"},
    download=lambda m: {"ok": True, "filepath": "/tmp/a.jpg", "filepaths": ["/tmp/a.jpg"]},
    transcribe=None, describe=_describe_plain, ingest=_ingest_capture,
)
tags = captured.get("extra_tags") or []

if "colecao:Dev" in tags:
    ok("the collection lands as colecao:<name>")
else:
    bad(f"expected colecao:Dev, got {tags!r}")

# A bare name is indistinguishable from a tag the LLM produced, which is how
# "Todos os posts" ended up on 11 of 12 documents as if it meant something.
if "Dev" not in tags:
    ok("the bare collection name is not written as a tag")
else:
    bad(f"bare collection name still present: {tags!r}")

# categoria == "outros" carries no information and must stay out.
if not any(t.startswith("categoria:") for t in tags):
    ok("categoria 'outros' is not tagged")
else:
    bad(f"'outros' was tagged: {tags!r}")

captured.clear()
ig_worker.process_message(
    {**MESSAGE, "media_type": "carousel", "collection_name": None},
    download=lambda m: {"ok": True, "filepath": "/tmp/a.jpg", "filepaths": ["/tmp/a.jpg"]},
    transcribe=None, describe=_describe_plain, ingest=_ingest_capture,
)
if not (captured.get("extra_tags") or []):
    ok("no collection means no tag at all")
else:
    bad(f"tags appeared without a collection: {captured.get('extra_tags')!r}")

print("== unit_ig_worker: a mídia é PRESERVADA por padrão, e descartável sob pedido ==")

# Esta seção afirmava o contrário -- que a mídia é apagada sempre, inclusive no
# caminho de erro -- e estava certa para a política antiga. A política mudou por
# uma assimetria de custo: requisição ao Instagram é escassa e punível,
# reprocessar na GPU é só tempo de máquina local. Apagar amarrava as duas.
#
# O que a política antiga protegia (disco) continua protegido, e por um caminho
# melhor: com a mídia no disco, `_default_download` reaproveita e o retry da DLQ
# não volta à rede -- antes, cada uma das três tentativas baixava de novo.
CASES = [
    ("transcrição falhou", {"status": "error", "error": "x", "filepaths": ["/tmp/_t1.mp4"]}),
    ("ingestão falhou", {"status": "error", "error": "x", "filepaths": ["/tmp/_t2.mp4"]}),
    ("sucesso", {"status": "done", "document_id": 1, "filepaths": ["/tmp/_t3.mp4"]}),
    ("carrossel, vários arquivos", {"status": "error", "error": "x",
                                    "filepaths": ["/tmp/_t4a.jpg", "/tmp/_t4b.jpg"]}),
]

for label, res in CASES:
    paths = res["filepaths"]
    for p in paths:
        Path(p).write_text("x")
    ig_worker._discard_media(res)
    survived = [p for p in paths if Path(p).exists()]
    if survived == paths:
        ok(f"{label}: mídia preservada")
    else:
        bad(f"{label}: mídia sumiu, some o trabalho de rede")
    for p in paths:
        Path(p).unlink(missing_ok=True)

# Quem liga a variável continua tendo a garantia antiga, inclusive no erro.
_orig_flag = ig_worker.IG_DELETE_AFTER_INGEST
ig_worker.IG_DELETE_AFTER_INGEST = True
try:
    for label, res in CASES:
        paths = res["filepaths"]
        for p in paths:
            Path(p).write_text("x")
        ig_worker._discard_media(res)
        left = [p for p in paths if Path(p).exists()]
        if not left:
            ok(f"{label}: com a variável ligada, apaga mesmo assim")
        else:
            bad(f"{label}: variável ligada e sobrou {left}")
finally:
    ig_worker.IG_DELETE_AFTER_INGEST = _orig_flag

# Erro antes do download não tem o que apagar, e não pode explodir.
try:
    ig_worker._discard_media({"status": "error", "error": "download failed"})
    ok("um erro sem arquivo nenhum não quebra a limpeza")
except Exception as e:
    bad(f"_discard_media levantou sem filepaths: {e!r}")

# Um arquivo que já sumiu (retry, limpeza concorrente) também não pode explodir.
try:
    ig_worker._discard_media({"status": "done", "filepaths": ["/tmp/_nao_existe_.mp4"]})
    ok("arquivo já inexistente é ignorado")
except Exception as e:
    bad(f"_discard_media levantou em arquivo ausente: {e!r}")

print("== unit_ig_worker: vídeo também recebe categoria ==")

VOCAB = ["Dev", "Receitas", "Inglês"]
seen = {}


def _ingest_seen(text, **kw):
    seen.clear()
    seen.update(kw)
    return {"ok": True, "document_id": 80}


# Video: no vision runs, so the summary model is the only judge there is.
# Before this, `categoria` was reachable only through describe_image, and 11 of
# the 12 documents in the first real run were videos -- so in practice almost
# nothing was ever categorised.
ig_worker.process_message(
    MESSAGE,
    download=lambda m: {"ok": True, "filepath": "/tmp/v.mp4"},
    transcribe=lambda p: {"ok": True, "text": "conteudo", "language": "pt"},
    describe=None,
    ingest=_ingest_seen,
    categories=VOCAB,
)
if seen.get("categories") == VOCAB:
    ok("video ingestion receives the category vocabulary")
else:
    bad(f"video got categories={seen.get('categories')!r}")

# Image: vision already looked at the picture. Asking the summary model to
# classify the same post again would be a second, weaker opinion.
ig_worker.process_message(
    {**MESSAGE, "media_type": "carousel"},
    download=lambda m: {"ok": True, "filepath": "/tmp/a.jpg", "filepaths": ["/tmp/a.jpg"]},
    transcribe=None,
    describe=lambda p: {"ok": True, "text": "x", "tipo": "dica",
                        "categoria": "Dev", "conteudo_principal": "x"},
    ingest=_ingest_seen,
    categories=VOCAB,
)
if seen.get("categories") is None:
    ok("image ingestion does not ask again — vision already classified it")
else:
    bad(f"image got categories={seen.get('categories')!r}, a duplicate judgement")

if "categoria:Dev" in (seen.get("extra_tags") or []):
    ok("the vision categoria still becomes the tag for images")
else:
    bad(f"vision categoria lost: {seen.get('extra_tags')!r}")

# An image whose vision categoria is "outros" carries no judgement, so the
# summary model should get its turn.
ig_worker.process_message(
    {**MESSAGE, "media_type": "carousel"},
    download=lambda m: {"ok": True, "filepath": "/tmp/a.jpg", "filepaths": ["/tmp/a.jpg"]},
    transcribe=None,
    describe=lambda p: {"ok": True, "text": "x", "tipo": "dica",
                        "categoria": "outros", "conteudo_principal": "x"},
    ingest=_ingest_seen,
    categories=VOCAB,
)
if seen.get("categories") == VOCAB:
    ok("'outros' from vision is not a judgement — the summary model gets a turn")
else:
    bad(f"'outros' blocked the second attempt: categories={seen.get('categories')!r}")

print("== unit_ig_worker: strip_cta ==")
from minimax_mcp.ig_worker import strip_cta

# A sentence containing a CTA is removed entirely.
cleaned = strip_cta(
    "Misture a batata doce amassada com o azeite. "
    "Já me segue aqui para não perder uma receita. "
    "Asse na Air Fryer a 170°C por 15 minutos."
)
if "Já me segue aqui" not in cleaned and "Asse na Air Fryer" in cleaned and "Misture a batata" in cleaned:
    ok("strip_cta removes the CTA sentence, keeps surrounding content")
else:
    bad(f"strip_cta = {cleaned!r}")

# No CTA -> text unchanged.
plain = "Asse na Air Fryer a 170°C por 15 minutos e sirva."
if strip_cta(plain) == plain:
    ok("strip_cta leaves CTA-free text intact")
else:
    bad(f"strip_cta(plain) = {strip_cta(plain)!r}")

# Empty / whitespace input never raises.
try:
    if strip_cta("") == "" and strip_cta("   ").strip() == "":
        ok("strip_cta handles empty/whitespace input")
    else:
        bad("strip_cta empty input result wrong")
except Exception as e:
    bad(f"strip_cta('') raised {e!r}")

# 'link na bio' as its own sentence.
if "link na bio" not in strip_cta("Curte e compartilha. Link na bio. O conteúdo principal.").lower():
    ok("strip_cta removes 'link na bio' sentence")
else:
    bad("strip_cta did not remove 'link na bio'")

# Standalone accented 'Já me segue' (no following 'para perder') is stripped.
accented = strip_cta("A receita é boa. Já me segue. Asse por 15 min.")
if "Já me segue" not in accented and "A receita é boa" in accented and "Asse por 15 min" in accented:
    ok("strip_cta strips standalone accented 'Já me segue'")
else:
    bad(f"strip_cta(accented) = {accented!r}")

# A legit sentence containing the bare word 'já' survives (no over-match).
already = "Já assei por 15 minutos. O resto é fácil."
if strip_cta(already) == already:
    ok("strip_cta leaves a sentence with bare 'já' intact")
else:
    bad(f"strip_cta(bare já) = {strip_cta(already)!r}")

# The 'comenta...que eu te mando' CTA fully inside one sentence is removed.
same = strip_cta("A receita é boa. Comenta que eu te mando a receita. Asse por 15 min.")
if "Comenta que eu te mando" not in same and "A receita é boa" in same and "Asse por 15 min" in same:
    ok("strip_cta removes a single sentence fully containing 'comenta...que eu te mando'")
else:
    bad(f"strip_cta(same-sentence) = {same!r}")

# The CTA split across two sentences is NOT removed: the regex must not cross
# the period. (The user's 'Comenta e ativa o sininho. Depois que eu te mando
# a receita.' example is shadowed by the earlier 'ativa o sininho' alternative,
# so use a first sentence whose only pattern is 'comenta'.)
split = strip_cta("Comenta a receita agora. Depois que eu te mando o passo a passo. Asse por 15 min.")
if "Depois que eu te mando o passo a passo" in split and "Asse por 15 min" in split:
    ok("strip_cta does not cross the sentence boundary of 'comenta...que eu te mando'")
else:
    bad(f"strip_cta(split-sentence) = {split!r}")

print("== unit_ig_worker: process_message strips CTA before ingest ==")
def dl_vid(msg):
    return {"ok": True, "filepath": "/tmp/y.mp4"}

def tr_cta(path):
    return {"ok": True, "text": "A dica é boa. Segue pra não perder. Asse por 15 min.", "language": "pt"}

seen_text = {}
def ingest_record(text, **kw):
    seen_text["text"] = text
    return {"ok": True, "document_id": 45}

ig_worker.process_message(
    MESSAGE, download=dl_vid, transcribe=tr_cta, describe=None, ingest=ingest_record
)
if "Segue pra não perder" not in seen_text.get("text", "") and "A dica é boa" in seen_text.get("text", ""):
    ok("process_message passes CTA-stripped text to ingest")
else:
    bad(f"ingest received uncleaned text: {seen_text.get('text')!r}")

print("== unit_ig_worker: pace_sleep_seconds ==")
from minimax_mcp.ig_worker import pace_sleep_seconds

# Desconta o tempo já gasto: a pausa é um TETO de velocidade, não um imposto fixo
# somado ao processamento. Sem descontar, o espaçamento real viraria
# `processamento + intervalo` e variaria com o tamanho de cada vídeo -- 39 s num
# post curto, minutos num longo.
if pace_sleep_seconds(30.0, 90.0) == 60.0:
    ok("desconta o tempo já gasto (30 s de 90 -> dorme 60)")
else:
    bad(f"pace(30,90) = {pace_sleep_seconds(30.0, 90.0)}")

# Post mais lento que o intervalo segue direto: quem manda passa a ser o
# processamento, e a pausa não atrasa nada de propósito.
if pace_sleep_seconds(120.0, 90.0) == 0.0:
    ok("post mais lento que o intervalo não dorme nada")
else:
    bad(f"pace(120,90) = {pace_sleep_seconds(120.0, 90.0)}")

# Padrão 0 = comportamento antigo, para não mudar nada de quem não configurou.
if pace_sleep_seconds(1.0, 0.0) == 0.0 and pace_sleep_seconds(0.0, 0.0) == 0.0:
    ok("intervalo 0 desliga a pausa (comportamento antigo preservado)")
else:
    bad("intervalo 0 ainda dorme")

# Medição negativa (relógio, ou início registrado errado) não pode virar pausa
# maior que o intervalo.
if pace_sleep_seconds(-5.0, 90.0) == 90.0:
    ok("elapsed negativo não vira pausa maior que o intervalo")
else:
    bad(f"pace(-5,90) = {pace_sleep_seconds(-5.0, 90.0)}")

print("== unit_ig_worker: clean_title ==")
from minimax_mcp.ig_worker import clean_title

# Os quatro casos vêm dos doze títulos REAIS já ingeridos, não de exemplos
# inventados: a primeira tentativa (reusar strip_cta no título) passou nos meus
# exemplos e falhou nos títulos de verdade, de dois jeitos diferentes.
CASES = [
    # CTA sem pontuação final: o strip_cta sozinho devolvia isto INTACTO, porque
    # a expressão de sentença exige `.`, `!` ou `?` para fechar.
    ("Siga para mais 👉 @nikolassfaria", None),
    # CTA + hashtags: o strip_cta sozinho devolvia "#code #c" -- pior que o
    # original, porque vira o título e o nome do arquivo exportado.
    ("Comenta “PROCESSO” que eu te mando o passo a passo completo no privado! #code #c", None),
    # CTA no fim de conteúdo real: o conteúdo fica, a chamada sai.
    ("Estude comigo na Fluency. Link na Bio.", "Estude comigo na Fluency."),
    # Sem CTA: intacto, PONTUAÇÃO INCLUÍDA. Cortar o ponto final mudaria títulos
    # bons e encheria qualquer comparação de ruído.
    ("Uma receita simples, natural e muito poderosa.", "Uma receita simples, natural e muito poderosa."),
    ("A energia do Sol cada vez mais próxima!", "A energia do Sol cada vez mais próxima!"),
    (None, None),
    ("", None),
]
for raw, expected in CASES:
    got = clean_title(raw)
    if got == expected:
        ok(f"clean_title({raw!r:.42}) -> {got!r:.42}")
    else:
        bad(f"clean_title({raw!r:.42}) = {got!r}, esperado {expected!r}")

# Um título que sobra com uma palavra só não é título -- deixa o resumo assumir.
if clean_title("Link na bio! #dev") is None:
    ok("clean_title devolve None quando sobra menos de duas palavras")
else:
    bad(f"clean_title de resto curto = {clean_title('Link na bio! #dev')!r}")

print("== unit_ig_worker: imagem simples baixa pela URL assinada ==")


class _InfoFoto:
    media_type = 1
    thumbnail_url = "https://cdn.example/assinada.jpg"


# O conserto de carrossel (43453e2) trocou a re-resolução por URL assinada no
# álbum e deixou a imagem simples no caminho antigo. `photo_download(pk)` faz o
# instagrapi re-resolver por dentro, cair no GraphQL público e bater na parede
# de login -- observado em produção em 2026-08-10.
if ig_worker._targets_from_info(_InfoFoto(), "55") == [
    ("photo_download_by_url", "https://cdn.example/assinada.jpg")
]:
    ok("imagem simples usa photo_download_by_url, sem re-resolver pelo pk")
else:
    bad(f"imagem simples = {ig_worker._targets_from_info(_InfoFoto(), '55')!r}")


class _InfoFotoSemUrl:
    media_type = 1


# Sem URL, é melhor o caminho antigo que descartar o post em silêncio.
if ig_worker._targets_from_info(_InfoFotoSemUrl(), "55") == [("photo_download", "55")]:
    ok("sem thumbnail_url, cai no download por pk em vez de perder o post")
else:
    bad(f"fallback de imagem = {ig_worker._targets_from_info(_InfoFotoSemUrl(), '55')!r}")

print("== unit_ig_worker: leitura de tela ==")

# Quadros vizinhos repetem a tela, e um deles costuma vir truncado no meio da
# linha. Repetir isso no documento não acrescenta nada e desvia o resumo.
# O truncamento real vem CRU, sem fechar a aspa -- é o quadro pegando a tela no
# meio da digitação. Observado em 2026-08-10 no post 3818562307589048738:
#   quadro 3: msg="Seu script Python te lembrou de beber água!",
#   quadro 4: msg="Seu script Python te lembrou d
# (Uma versão anterior deste teste inventou a aspa de fechamento na linha
# cortada, o que não acontece e tornava o caso insolúvel por subcadeia.)
juntado = ig_worker.merge_screen_text([
    "from win10toast import ToastNotifier",
    "from win10toast import ToastNotifier\ntoaster = ToastNotifier()",
    'toaster = ToastNotifier()\nmsg="Seu script te lembrou d',
    'msg="Seu script te lembrou de beber água!"',
])
linhas = juntado.splitlines()
if (
    linhas.count("from win10toast import ToastNotifier") == 1
    and len(linhas) == 3
    and linhas[-1] == 'msg="Seu script te lembrou de beber água!"'
):
    ok("merge_screen_text não repete linha e a completa substitui a truncada")
else:
    bad(f"merge_screen_text = {juntado!r}")

# E no sentido inverso: a completa chega primeiro, a truncada depois.
inv = ig_worker.merge_screen_text([
    'msg="Seu script te lembrou de beber água!"',
    'msg="Seu script te lembrou d',
])
if inv == 'msg="Seu script te lembrou de beber água!"':
    ok("truncada que chega depois da completa é descartada")
else:
    bad(f"merge_screen_text inverso = {inv!r}")

if ig_worker.merge_screen_text([]) == "" and ig_worker.merge_screen_text(["", None]) == "":
    ok("merge_screen_text aguenta vazio e None")
else:
    bad("merge_screen_text quebrou no caso vazio")

# A tela entra no documento junto com a fala, rotulada.
_v = {}


def _ing_v(text, **kw):
    _v.clear(); _v["text"] = text; _v.update(kw)
    return {"ok": True, "document_id": 901}


r = ig_worker.process_message(
    {"ig_pk": "9", "url": "u", "title": "t"},
    download=lambda m: {"ok": True, "filepath": "/tmp/x.mp4", "filepaths": ["/tmp/x.mp4"]},
    transcribe=lambda f: {"ok": True, "text": "olha esse código aqui", "language": "pt"},
    describe=None,
    read_screen=lambda f: {"ok": True, "text": "from win10toast import ToastNotifier"},
    ingest=_ing_v,
)
if r["status"] == "done" and "win10toast" in _v["text"] and "olha esse código" in _v["text"]:
    ok("a tela entra no documento junto com a fala")
else:
    bad(f"tela não entrou: {_v.get('text')!r}")

# Sem fala, a tela é o conteúdo -- e vem ANTES da legenda, que é divulgação.
r = ig_worker.process_message(
    {"ig_pk": "10", "url": "u", "title": "t"},
    download=lambda m: {"ok": True, "filepath": "/tmp/x.mp4", "filepaths": ["/tmp/x.mp4"],
                        "caption": "Comenta CHEAT que eu envio"},
    transcribe=lambda f: {"ok": True, "text": "", "language": "pt"},
    describe=None,
    read_screen=lambda f: {"ok": True, "text": "np.reshape(a, (2,3))"},
    ingest=_ing_v,
)
if r["status"] == "done" and _v["text"].index("np.reshape") < _v["text"].index("Comenta"):
    ok("vídeo mudo com tela: a tela vem antes da legenda")
else:
    bad(f"ordem errada: {_v.get('text')!r}")

# Falha ao ler a tela não pode custar a transcrição que já foi paga.
r = ig_worker.process_message(
    {"ig_pk": "11", "url": "u", "title": "t"},
    download=lambda m: {"ok": True, "filepath": "/tmp/x.mp4", "filepaths": ["/tmp/x.mp4"]},
    transcribe=lambda f: {"ok": True, "text": "a fala sobreviveu", "language": "pt"},
    describe=None,
    read_screen=lambda f: {"ok": False, "error": "ollama caiu"},
    ingest=_ing_v,
)
if r["status"] == "done" and _v["text"] == "a fala sobreviveu":
    ok("falha na leitura de tela não descarta a transcrição")
else:
    bad(f"falha de tela contaminou: {r!r} / {_v.get('text')!r}")

# A capa sai de graça: é cópia de um quadro que já foi extraído para ler a tela.
with tempfile.TemporaryDirectory() as _t:
    _p = Path(_t)
    (_p / "post.mp4").write_bytes(b"v")
    qs = []
    for i, cor in enumerate([b"aaa", b"bbb", b"ccc", b"ddd"]):
        f = _p / f"f_{i}.jpg"
        f.write_bytes(cor)
        qs.append(str(f))
    capa = ig_worker.guardar_capa(qs, str(_p / "post.mp4"))
    # O segundo quadro: a abertura costuma ser rosto ou tela preta.
    if capa and Path(capa).name == "capa.jpg" and Path(capa).read_bytes() == b"bbb":
        ok("guardar_capa escolhe o segundo quadro e grava ao lado do vídeo")
    else:
        bad(f"capa = {capa!r}")

    if ig_worker.guardar_capa([], str(_p / "post.mp4")) is None:
        ok("sem quadros, guardar_capa devolve None em vez de quebrar")
    else:
        bad("guardar_capa deveria devolver None sem quadros")

    um = ig_worker.guardar_capa([qs[0]], str(_p / "post.mp4"))
    if um and Path(um).read_bytes() == b"aaa":
        ok("com um quadro só, usa esse mesmo")
    else:
        bad(f"capa de quadro único = {um!r}")

print("== unit_ig_worker: vídeo mudo cai para a legenda ==")

# 10% dos 40 primeiros posts do piloto (2026-08-10) eram reel de música: o VAD
# do Whisper remove 100% do áudio e a transcrição volta vazia.
_visto: dict = {}


def _ing_captura(text, **kw):
    _visto.clear()
    _visto["text"] = text
    _visto.update(kw)
    return {"ok": True, "document_id": 900}


r = ig_worker.process_message(
    {"ig_pk": "1", "url": "u", "title": "Primeira linha cortada"},
    download=lambda m: {"ok": True, "filepath": "/tmp/x.mp4", "filepaths": ["/tmp/x.mp4"],
                        "caption": "A legenda inteira do post, bem mais longa que o título."},
    transcribe=lambda f: {"ok": True, "text": "   ", "language": "pt"},
    describe=None,
    ingest=_ing_captura,
)
if r["status"] == "done" and _visto["text"].startswith("A legenda inteira"):
    ok("sem fala, o documento nasce da legenda COMPLETA do media_info")
else:
    bad(f"fallback de legenda não usou o caption: {r!r} / {_visto.get('text')!r}")

# Sem media_info (mídia reaproveitada do disco) sobra o título da mensagem.
r = ig_worker.process_message(
    {"ig_pk": "2", "url": "u", "title": "Só o título sobrou aqui"},
    download=lambda m: {"ok": True, "filepath": "/tmp/x.mp4", "filepaths": ["/tmp/x.mp4"]},
    transcribe=lambda f: {"ok": True, "text": "", "language": "pt"},
    describe=None,
    ingest=_ing_captura,
)
if r["status"] == "done" and _visto["text"] == "Só o título sobrou aqui":
    ok("sem caption, o título da mensagem é o reserva")
else:
    bad(f"reserva de título falhou: {r!r} / {_visto.get('text')!r}")

# Sem fala E sem legenda não há documento possível -- e repetir isso três vezes
# é desperdício determinístico, então tem de ser falha PERMANENTE.
r = ig_worker.process_message(
    {"ig_pk": "3", "url": "u", "title": None},
    download=lambda m: {"ok": True, "filepath": "/tmp/x.mp4", "filepaths": ["/tmp/x.mp4"],
                        "caption": ""},
    transcribe=lambda f: {"ok": True, "text": "", "language": "pt"},
    describe=None,
    ingest=_ing_captura,
)
if r["status"] == "error" and r.get("permanent") is True:
    ok("sem fala e sem legenda vira falha permanente, sem gastar retry")
else:
    bad(f"deveria ser permanente: {r!r}")

# E uma falha comum continua NÃO sendo permanente -- timeout de CDN merece retry.
r = ig_worker.process_message(
    {"ig_pk": "4", "url": "u", "title": "x"},
    download=lambda m: {"ok": False, "error": "Read timed out"},
    transcribe=None, describe=None, ingest=_ing_captura,
)
if r["status"] == "error" and not r.get("permanent"):
    ok("falha de rede continua retentável")
else:
    bad(f"falha de rede não pode ser permanente: {r!r}")

# A parte pura não pode pedir media_info de novo: é a chamada autenticada.
class _Info:
    media_type = 2


if ig_worker._targets_from_info(_Info(), "77") == [("clip_download", "77")]:
    ok("_targets_from_info decide sem tocar no client")
else:
    bad(f"_targets_from_info = {ig_worker._targets_from_info(_Info(), '77')!r}")

print("== unit_ig_worker: mídia preservada e reaproveitada ==")

import minimax_mcp.ig_worker as _w

with tempfile.TemporaryDirectory() as tmp:
    _orig_dir = _w.IG_DOWNLOADS_DIR
    _w.IG_DOWNLOADS_DIR = Path(tmp)
    try:
        # Sem nada no disco, não há o que reaproveitar.
        if _w.existing_media("999") == []:
            ok("existing_media devolve vazio quando o post nunca foi baixado")
        else:
            bad(f"existing_media de post novo = {_w.existing_media('999')!r}")

        # Uma pasta por ig_pk: é o que liga os oito arquivos de um carrossel ao
        # álbum, já que o nome do arquivo carrega o pk do RECURSO, não o do post.
        d = _w.post_media_dir("555")
        d.mkdir(parents=True)
        for i, name in enumerate(["b_second.jpg", "a_first.jpg", "c_third.jpg"]):
            p = d / name
            p.write_bytes(b"x")
            # mtimes distintos e crescentes na ordem de "download"
            os.utime(p, (1_000_000 + i, 1_000_000 + i))

        got = [Path(f).name for f in _w.existing_media("555")]
        # Ordem de download, NÃO alfabética: num carrossel process_message junta
        # a descrição de cada foto em ordem, então reordenar mudaria o texto do
        # documento entre a primeira passada e um reprocessamento.
        if got == ["b_second.jpg", "a_first.jpg", "c_third.jpg"]:
            ok("existing_media preserva a ordem de download, não a alfabética")
        else:
            bad(f"existing_media ordenou {got}")

        # O reuso tem de vir ANTES de qualquer requisição. Se _default_download
        # tocasse a rede aqui, make_client falharia ou cobraria uma chamada --
        # o teste roda sem sessão de propósito.
        res = _w._default_download({"ig_pk": "555", "url": "https://example/p/x/"})
        if res.get("ok") and res.get("reused") and len(res.get("filepaths", [])) == 3:
            ok("_default_download reaproveita o disco sem tocar o Instagram")
        else:
            bad(f"_default_download não reaproveitou: {res!r}")

        # E o que ele devolve tem de servir de raw_file_path.
        if res.get("filepath") == res["filepaths"][0]:
            ok("filepath aponta para o primeiro arquivo, que vira raw_file_path")
        else:
            bad(f"filepath={res.get('filepath')!r} destoa de filepaths[0]")
    finally:
        _w.IG_DOWNLOADS_DIR = _orig_dir

# Guardar é o padrão: um .env esquecido não pode apagar trabalho de rede.
if _w.IG_DELETE_AFTER_INGEST is False:
    ok("IG_DELETE_AFTER_INGEST vem desligado por padrão")
else:
    bad("IG_DELETE_AFTER_INGEST ligado por padrão apagaria a mídia preservada")

print("== unit_ig_worker: carrossel misto (foto + vídeo) ==")

# Os 9 posts que sobraram na DLQ de 2026-08-18 eram todos assim: fotos E vídeos
# no mesmo post, `kind` decidido pelo PRIMEIRO arquivo. Começando por foto, o
# post entrava como imagem e mandava os `.mp4` para o modelo de visão, que
# devolvia `Failed to load image or audio file` -- e uma descrição falha
# abortava o carrossel inteiro, com as fotos boas ao lado.

MISTO = ["/tmp/a.jpg", "/tmp/b.mp4", "/tmp/c.jpg", "/tmp/d.mp4"]


# Receptor permissivo: aqui o que se testa é QUAIS arquivos chegam ao modelo de
# visão, não o texto final -- o `ingest_img` de cima trava num texto fixo.
textos = []


def ingest_qualquer(text, **kw):
    textos.append(text)
    return {"ok": True, "document_id": 99}


def dl_misto(msg):
    return {"ok": True, "filepaths": list(MISTO), "filepath": MISTO[0]}


vistos = []


def describe_so_imagem(path):
    vistos.append(path)
    if path.endswith(".mp4"):
        # O que o Ollama de verdade devolve para um vídeo.
        return {"ok": False, "error": "vision failed: Client error '400 Bad Request'"}
    return {"ok": True, "conteudo_principal": f"desc {path}", "categoria": "receita"}


res = ig_worker.process_message(
    {**MESSAGE, "media_type": "carousel"},
    download=dl_misto, transcribe=None, describe=describe_so_imagem,
    read_screen=None, ingest=ingest_qualquer,
)

if res["status"] == "done":
    ok("carrossel misto vira documento em vez de morrer no primeiro .mp4")
else:
    bad(f"carrossel misto = {res!r}")

if vistos == ["/tmp/a.jpg", "/tmp/c.jpg"]:
    ok("só as imagens vão para o modelo de visão; os vídeos nem são tentados")
else:
    bad(f"mandou {vistos!r} -- um .mp4 no modelo de imagem é 400 na certa")

# Uma foto ruim no meio não pode custar as outras -- é o mesmo erro estrutural
# que fazia um post malformado derrubar a coleção inteira na listagem.
def describe_uma_ruim(path):
    if path == "/tmp/a.jpg":
        return {"ok": False, "error": "vision failed: 400"}
    return {"ok": True, "conteudo_principal": "sobrevivi", "categoria": "receita"}


res = ig_worker.process_message(
    {**MESSAGE, "media_type": "carousel"},
    download=dl_misto, transcribe=None, describe=describe_uma_ruim,
    read_screen=None, ingest=ingest_qualquer,
)
if res["status"] == "done":
    ok("uma foto que falha não derruba as outras do carrossel")
else:
    bad(f"uma falha derrubou o carrossel inteiro: {res!r}")

# Mas se NENHUMA descreve, não há post -- e o erro tem de dizer isso.
res = ig_worker.process_message(
    {**MESSAGE, "media_type": "carousel"},
    download=dl_misto, transcribe=None,
    describe=lambda p: {"ok": False, "error": "vision failed: 400"},
    read_screen=None, ingest=ingest_qualquer,
)
if res["status"] == "error" and "todas" in res.get("error", ""):
    ok("nenhuma imagem descreveu -> erro claro, não documento vazio")
else:
    bad(f"deveria falhar com todas as imagens ruins: {res!r}")

# Carrossel só de vídeo entra como vídeo pelo `kind`; o caso que chega aqui é o
# post cujo primeiro arquivo é imagem mas nenhum outro é -- não pode virar
# documento sem nada descrito.
res = ig_worker.process_message(
    {**MESSAGE, "media_type": "carousel"},
    download=lambda m: {"ok": True, "filepaths": ["/tmp/x.jpg"], "filepath": "/tmp/x.jpg"},
    transcribe=None, describe=lambda p: {"ok": False, "error": "vision failed: 400"},
    read_screen=None, ingest=ingest_qualquer,
)
if res["status"] == "error":
    ok("imagem única que não descreve continua sendo falha")
else:
    bad(f"imagem única ruim passou como sucesso: {res!r}")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
