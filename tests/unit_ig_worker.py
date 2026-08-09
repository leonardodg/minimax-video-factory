#!/usr/bin/env python3
"""Unit tests for ig_worker.py — injected download/transcribe/describe/ingest."""
from __future__ import annotations

import sys
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

print("== unit_ig_worker: _download_targets ==")
class FakeRes:
    def __init__(self, media_type, pk):
        self.media_type = media_type
        self.pk = pk
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

car = FakeInfo(8, [FakeRes(1, "p1"), FakeRes(2, "v2"), FakeRes(1, "p3")])
r = ig_worker._download_targets(FakeClient(car), "888")
if r == [("photo_download", "p1"), ("clip_download", "v2"), ("photo_download", "p3")]:
    ok("carousel -> one pair per resource, video->clip, photo->photo")
else:
    bad(f"carousel targets = {r!r}")

car_img = FakeInfo(8, [FakeRes(1, "p1"), FakeRes(1, "p2")])
if ig_worker._download_targets(FakeClient(car_img), "888") == [
    ("photo_download", "p1"), ("photo_download", "p2"),
]:
    ok("carousel with only images -> photo_download per photo")
else:
    bad(f"carousel img targets = {ig_worker._download_targets(FakeClient(car_img), '888')!r}")

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

from minimax_mcp import ig_sync

_orig_make_client = ig_sync.make_client
ig_sync.make_client = lambda: FakeClientDownload(FakeInfo(8, [FakeRes(1, "p1"), FakeRes(2, "v2")]))
try:
    res = ig_worker._default_download({**MESSAGE, "media_type": "carousel", "ig_pk": "999", "url": ""})
finally:
    ig_sync.make_client = _orig_make_client
fps = res.get("filepaths") or []
if res.get("ok") and len(fps) == 2 and any(fps[0].endswith("fake_p1.jpg") for f in fps) and any(fps[1].endswith("fake_v2.mp4") for f in fps):
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

print("== unit_ig_worker: a mídia é descartada mesmo quando falha ==")

# Só o caminho de sucesso apagava. Um post que falhava deixava o arquivo, e o
# retry da DLQ baixava de novo a cada tentativa -- num sync de 2000+ posts é a
# diferença entre alguns MB de rotatividade e encher o disco.
for label, res in [
    ("transcrição falhou", {"status": "error", "error": "x", "filepaths": ["/tmp/_t1.mp4"]}),
    ("ingestão falhou", {"status": "error", "error": "x", "filepaths": ["/tmp/_t2.mp4"]}),
    ("sucesso", {"status": "done", "document_id": 1, "filepaths": ["/tmp/_t3.mp4"]}),
    ("carrossel, vários arquivos", {"status": "error", "error": "x",
                                    "filepaths": ["/tmp/_t4a.jpg", "/tmp/_t4b.jpg"]}),
]:
    paths = res["filepaths"]
    for p in paths:
        Path(p).write_text("x")
    ig_worker._discard_media(res)
    left = [p for p in paths if Path(p).exists()]
    if not left:
        ok(f"{label}: mídia apagada")
    else:
        bad(f"{label}: sobrou no disco {left}")

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

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
