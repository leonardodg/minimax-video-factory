# Content-Focused IG Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Instagram→KB pipeline capture the **main content** (tip/receita/lista) instead of describing clothing/scene, for images, carousels, and videos alike.

**Architecture:** (1) a category vocabulary derived from the user's Instagram collections, threaded into (2) a structured vision prompt that returns `{tipo, categoria, conteudo_principal}`; (3) carousels download and describe **every** resource, concatenating the `conteudo_principal`; (4) the summary prompt states the general premise — the transcription/description is only supporting material, deliverables must answer "qual é a dica/receita".

**Tech Stack:** Python 3.10+, instagrapi (enumeration/download), Ollama `qwen2.5vl:7b` (vision) + `lfm2:24b` (summary), RabbitMQ `ig.saved` queue, Postgres+pgvector KB.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-09-ig-content-focused-pipeline-design.md`.
- Keep `process_message` **pure** — all IO stays injected (`download`/`transcribe`/`describe`/`ingest` callables). No RabbitMQ/network/GPU imports at module import time.
- Preserve back-compat of injected callables where possible: `_default_download` returns `filepath` **and** `filepaths`; `describe` may return `text` only or the full structured dict.
- Vision prompt is PT-BR, asks for **JSON only** (no markdown fences required, but tolerate them via existing `parse_llm_json`).
- Category list: normalized collection names, auto-collection dropped, case-insensitive dedup keeping the first spelling, fallback static list on any failure.
- Existing standalone test scripts (`tests/unit_*.py`) are `print`-based and run via `uv run python tests/unit_ig_worker.py`; pytest markers (`-m unit`) do NOT collect them. Verify BOTH the touched standalone scripts AND `uv run pytest -m unit`.
- Backround process note: a `downloads/ig/full_carousel_104/` download (8-carousel of doc 104's post) may still be running from the session before this plan. Leave it alone; it is not a deliverable of any task.

---

### Task 1: Category vocabulary from Instagram collections

**Files:**
- Modify: `src/minimax_mcp/ig_sync.py` (add after `MEDIA_TYPES`, line ~22)
- Test: `tests/unit_ig_sync.py` (append new section before final `print()`)

**Interfaces:**
- Consumes: nothing new (instagrapi `client.collections()`).
- Produces: `ig_sync.list_categories(client) -> list[str]` — normalized unique collection names, auto-collection dropped, `[]`→fallback, any exception→fallback. Used by Task 5 (`_default_describe`).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit_ig_sync.py` before the final `print()` block:

```python
print("== unit_ig_sync: list_categories ==")
class FakeCol:
    def __init__(self, name):
        self.name = name
class FakeClientCols:
    def __init__(self, cols):
        self._cols = cols
    def collections(self):
        return self._cols

cols = [
    FakeCol("Receitas "), FakeCol("receitas"), FakeCol("  Python "),
    FakeCol("Treino"), FakeCol("Treino "), FakeCol("All posts"),
    FakeCol("Todos os posts"), FakeCol(""),
]
cats = ig_sync.list_categories(FakeClientCols(cols))
expected = {"Receitas", "Python", "Treino"}
if set(cats) == expected and len(cats) == len(expected):
    ok("list_categories strips whitespace, dedups case-insensitively, drops auto-collections")
else:
    bad(f"list_categories = {cats!r}")

if ig_sync.list_categories(FakeClientCols([])) == ig_sync.FALLBACK_CATEGORIES:
    ok("list_categories with no collections falls back to static list")
else:
    bad(f"list_categories([]) = {ig_sync.list_categories(FakeClientCols([]))!r}")

class Boom:
    def collections(self):
        raise RuntimeError("boom")
if ig_sync.list_categories(Boom()) == ig_sync.FALLBACK_CATEGORIES:
    ok("list_categories swallows client errors -> fallback")
else:
    bad(f"list_categories(boom) = {ig_sync.list_categories(Boom())!r}")

if ig_sync.list_categories(None) == ig_sync.FALLBACK_CATEGORIES:
    ok("list_categories(None) -> fallback")
else:
    bad(f"list_categories(None) = {ig_sync.list_categories(None)!r}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python tests/unit_ig_sync.py`
Expected: FAIL (`NameError`/`AttributeError` for `list_categories`).

- [ ] **Step 3: Write minimal implementation**

In `src/minimax_mcp/ig_sync.py`, after the `MEDIA_TYPES` dict:

```python
# Auto-collections that are not real categories; kept out of the vocabulary.
AUTO_COLLECTION_NAMES = {"all posts", "todos os posts", "all", "todos"}

# Static fallback used when collections are unavailable (offline, API error).
FALLBACK_CATEGORIES = [
    "receita", "dica", "tutorial", "tech", "curso", "estudo", "inglês",
    "viagem", "house", "bitcoin", "treino", "car", "dog", "livro",
    "notícia", "outros",
]


def list_categories(client: Any) -> list[str]:
    """Normalized unique collection names — the category vocabulary for vision.

    Auto-collections ("All posts"/"Todos os posts") are excluded. Names are
    stripped, inner whitespace collapsed, and deduplicated case-insensitively
    keeping the first spelling. Any failure (or a None client) returns the
    static fallback list, never raises.
    """
    if client is None:
        return list(FALLBACK_CATEGORIES)
    try:
        names: list[str] = []
        seen: set[str] = set()
        for col in client.collections():
            raw = (getattr(col, "name", "") or "").strip()
            key = " ".join(raw.lower().split())
            if not key or key in AUTO_COLLECTION_NAMES or key in seen:
                continue
            seen.add(key)
            names.append(" ".join(raw.split()))
        return names or list(FALLBACK_CATEGORIES)
    except Exception:
        return list(FALLBACK_CATEGORIES)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python tests/unit_ig_sync.py`
Expected: PASS (all new lines `[ok]`).

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/ig_sync.py tests/unit_ig_sync.py
git commit -m "feat(ig): category vocabulary from Instagram collections"
```

---

### Task 2: Structured vision prompt + structured describe_image

**Files:**
- Modify: `src/minimax_mcp/llm.py` (`build_vision_prompt` at line ~199, `describe_image` at line ~207)
- Test: `tests/unit_knowledge.py` (replace the `build_vision_prompt` block near line ~321; append a `parse_vision_reply` section)

**Interfaces:**
- Consumes: `llm.parse_llm_json` (already exists).
- Produces:
  - `llm.build_vision_prompt(categories: list[str] | None = None) -> str`
  - `llm.parse_vision_reply(raw: str) -> dict` — returns `{"tipo", "categoria", "conteudo_principal"}` with defaults, never raises.
  - `llm.describe_image(image_path, *, model=None, categories=None) -> dict` — returns `{ok, text, tipo, categoria, conteudo_principal}` (and `{ok: False, error}` on failure). `text == conteudo_principal`.

- [ ] **Step 1: Write the failing test**

In `tests/unit_knowledge.py`, replace the `build_vision_prompt` block (currently lines ~321–326):

```python
print("== unit_knowledge: llm.build_vision_prompt / parse_vision_reply ==")
prompt = llm.build_vision_prompt(["Receitas", "Python", "Inglês"])
if ("conteudo_principal" in prompt and "categoria" in prompt
        and "Receitas" in prompt and "Python" in prompt and "Inglês" in prompt):
    ok("build_vision_prompt asks for structured JSON and lists the categories")
else:
    bad(f"build_vision_prompt = {prompt[:200]!r}")

clean_v = '{"tipo": "lista", "categoria": "courses", "conteudo_principal": "6 cursos gratuitos"}'
pv = llm.parse_vision_reply(clean_v)
if pv["conteudo_principal"] == "6 cursos gratuitos" and pv["categoria"] == "courses":
    ok("parse_vision_reply parses a clean vision JSON")
else:
    bad(f"parse_vision_reply(clean) = {pv!r}")

pv = llm.parse_vision_reply("apenas texto solto")
if pv["conteudo_principal"] == "apenas texto solto" and pv["categoria"] == "outros":
    ok("parse_vision_reply falls back to raw text on non-JSON")
else:
    bad(f"parse_vision_reply(text) = {pv!r}")

fenced_v = "```json\n" + clean_v + "\n```"
if llm.parse_vision_reply(fenced_v)["conteudo_principal"] == "6 cursos gratuitos":
    ok("parse_vision_reply strips ```json fences")
else:
    bad(f"parse_vision_reply(fenced) = {llm.parse_vision_reply(fenced_v)!r}")

pv = llm.parse_vision_reply('{"conteudo_principal": "x"}')
if pv["tipo"] == "outros" and pv["categoria"] == "outros":
    ok("parse_vision_reply defaults tipo/categoria when missing")
else:
    bad(f"parse_vision_reply(defaults) = {pv!r}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python tests/unit_knowledge.py`
Expected: FAIL (`parse_vision_reply` undefined, prompt assertion fails).

- [ ] **Step 3: Write minimal implementation**

In `src/minimax_mcp/llm.py`, replace `build_vision_prompt` (line ~199) with:

```python
def build_vision_prompt(categories: list[str] | None = None) -> str:
    cats = ", ".join(categories) if categories else (
        "receita, dica, tutorial, tech, curso, estudo, inglês, viagem, house, "
        "bitcoin, treino, car, dog, livro, notícia, outros"
    )
    return (
        "Você analisa uma imagem de um post do Instagram para uma base de "
        "conhecimento pessoal. Responda APENAS com um JSON válido (sem markdown, "
        "sem texto fora do JSON) com estas chaves:\n"
        '- "tipo": o tipo de conteúdo — "receita", "dica", "infografico", '
        '"tutorial", "noticia", "meme" ou "outros".\n'
        f'- "categoria": uma destas categorias — {cats}. Se nenhuma combinar, '
        'use "outros".\n'
        '- "conteudo_principal": o conteúdo em si — a dica, a receita, a lista, '
        "o que o post ensina. Leia o texto visível (títulos, listas, ingredientes, "
        "passos) e inclua-o aqui.\n"
        "IMPORTANTE: extraia o CONTEÚDO PRINCIPAL (o que o post ensina/informa). "
        "Ignore aparência física de pessoas, roupas, cenário e objetos de fundo. "
        "Não invente informações; se não houver texto legível, descreva o que a "
        "cena comunica.\n"
        "Formato exato (resposta deve ser SOMENTE este JSON):\n"
        '{"tipo": "...", "categoria": "...", "conteudo_principal": "..."}'
    )


def parse_vision_reply(raw: str) -> dict:
    """Parse the vision model's reply into {tipo, categoria, conteudo_principal}.

    Tolerates ```json fences (via parse_llm_json). If it is not JSON at all,
    the whole raw text becomes conteudo_principal. Never raises.
    """
    try:
        parsed = parse_llm_json(raw)
    except (ValueError, TypeError):
        parsed = {}
    if not isinstance(parsed, dict) or "conteudo_principal" not in parsed:
        parsed = {"conteudo_principal": raw}
    parsed.setdefault("tipo", "outros")
    parsed.setdefault("categoria", "outros")
    parsed["conteudo_principal"] = str(parsed["conteudo_principal"]).strip()
    return parsed
```

Replace `describe_image` (line ~207) with:

```python
def describe_image(
    image_path: str, *, model: str | None = None, categories: list[str] | None = None
) -> dict:
    """Describe an image with a local vision LLM via Ollama /api/generate."""
    model = model or VISION_MODEL
    try:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    except OSError as e:
        return {"ok": False, "error": f"read image failed: {e}"}

    payload = {
        "model": model,
        "prompt": build_vision_prompt(categories),
        "images": [b64],
        "stream": False,
        "options": {"num_predict": 512, "temperature": 0.2},
    }
    try:
        resp = httpx.post(
            f"{OLLAMA_URL}/api/generate", json=payload, timeout=LLM_TIMEOUT
        )
        resp.raise_for_status()
        raw = (resp.json().get("response") or "").strip()
    except Exception as e:
        return {"ok": False, "error": f"vision failed: {e}"}
    if not raw:
        return {"ok": False, "error": "vision returned empty text"}
    parsed = parse_vision_reply(raw)
    text = parsed["conteudo_principal"]
    return {
        "ok": True,
        "text": text,
        "tipo": parsed.get("tipo"),
        "categoria": parsed.get("categoria"),
        "conteudo_principal": text,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python tests/unit_knowledge.py`
Expected: PASS (new `build_vision_prompt`/`parse_vision_reply` lines `[ok]`; all pre-existing sections still pass).

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/llm.py tests/unit_knowledge.py
git commit -m "feat(llm): structured vision prompt + parse_vision_reply"
```

---

### Task 3: Generalized summary premise (all media types)

**Files:**
- Modify: `src/minimax_mcp/llm.py` (`SUMMARY_PROMPT_TEMPLATE` line ~30, `build_summary_prompt` line ~57, `generate_structured` line ~148)
- Modify: `src/minimax_mcp/knowledge.py` (`ingest_text` line ~95)
- Test: `tests/unit_knowledge.py` (append a `build_summary_prompt` is_image section)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `llm.build_summary_prompt(transcription: str, *, is_image: bool = False) -> str`
  - `llm.generate_structured(transcription, *, provider=None, model=None, is_image=False) -> dict`
  - `knowledge.ingest_text` threads `doc_type=="image"` into `is_image`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit_knowledge.py` before the final `print()`:

```python
print("== unit_knowledge: summary premise (main content) ==")
premise = "material de apoio"
if premise in llm.build_summary_prompt("qualquer coisa"):
    ok("summary prompt states transcription is only supporting material")
else:
    bad("summary prompt missing the supporting-material premise")

if "imagem/post do Instagram" in llm.build_summary_prompt("x", is_image=True):
    ok("is_image=True adds the Instagram-image context line")
else:
    bad("is_image=True did not add the image context line")

if "imagem/post do Instagram" not in llm.build_summary_prompt("x", is_image=False):
    ok("is_image=False omits the image context line")
else:
    bad("is_image=False wrongly added the image context line")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python tests/unit_knowledge.py`
Expected: FAIL (prompt text not present yet).

- [ ] **Step 3: Write minimal implementation**

In `src/minimax_mcp/llm.py`, change the `SUMMARY_PROMPT_TEMPLATE` `"resumo"` line (line ~35) to:

```python
- "resumo": um resumo conciso (3-5 frases) do CONTEÚDO PRINCIPAL — a dica, a
  receita, o passo a passo, o que foi ensinado. NÃO descreva o vídeo/imagem em
  si e não repita a transcrição. A transcrição/descrição abaixo é apenas
  material de apoio.
```

And add an `{image_note}` placeholder right before `Conteúdo a documentar:` (line ~52):

```python
{image_note}
Conteúdo a documentar:
{transcription}
```

Replace `build_summary_prompt` (line ~57):

```python
def build_summary_prompt(transcription: str, *, is_image: bool = False) -> str:
    image_note = (
        "\nA entrada é a descrição estruturada de uma imagem/post do Instagram. "
        "Extraia dela o conteúdo principal (dica, lista, receita)."
        if is_image
        else ""
    )
    return SUMMARY_PROMPT_TEMPLATE.format(
        transcription=transcription.strip(), image_note=image_note
    )
```

Replace `generate_structured` signature (line ~148):

```python
def generate_structured(
    transcription: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    is_image: bool = False,
) -> dict[str, Any]:
    """Ask the configured LLM for {resumo, tutorial, objetivos, tags} as JSON."""
    provider = provider or LLM_PROVIDER
    model = model or LLM_MODEL
    prompt = build_summary_prompt(transcription, is_image=is_image)
```

(Keep the rest of the function body unchanged.)

In `src/minimax_mcp/knowledge.py`, change `ingest_text` line ~95:

```python
    gen = llm.generate_structured(text, is_image=(doc_type == "image"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python tests/unit_knowledge.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/llm.py src/minimax_mcp/knowledge.py tests/unit_knowledge.py
git commit -m "feat(llm): summary premise — transcription is supporting material only"
```

---

### Task 4: `_download_targets` — download every carousel resource

**Files:**
- Modify: `src/minimax_mcp/ig_worker.py` (`_pick_download_target` line ~102 → replace with `_download_targets`; `_default_download` line ~126)
- Test: `tests/unit_ig_worker.py` (replace the `_pick_download_target` section, lines ~138–218, and the carousel download test)

**Interfaces:**
- Consumes: `ig_sync.make_client()`.
- Produces:
  - `ig_worker._download_targets(client, pk) -> list[tuple[str, str]]` — `(method, target_pk)` pairs: every carousel resource (`clip_download` for video resources, `photo_download` for photo resources), single media returns the pk itself.
  - `_default_download(message) -> dict` now returns `{"ok": True, "filepath": first, "filepaths": [...]}`.

- [ ] **Step 1: Write the failing test**

In `tests/unit_ig_worker.py`, replace the entire block that currently defines `FakeRes`/`FakeInfo`/`FakeClient` and the `_pick_download_target` asserts (lines ~138–218) with:

```python
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

import minimax_mcp.ig_sync as ig_sync
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python tests/unit_ig_worker.py`
Expected: FAIL (`_download_targets` undefined; old `_pick_download_target` tests now removed so no stale green).

- [ ] **Step 3: Write minimal implementation**

In `src/minimax_mcp/ig_worker.py`, replace `_pick_download_target` (line ~102, the whole function) with:

```python
def _download_targets(client: Any, pk: str) -> list[tuple[str, str]]:
    """All (method, target_pk) download pairs for a post.

    Carousels (media_type 8) have no clip of their own — the pk is an album
    container and clip_download raises "Must been video". Return one pair per
    resource: clip_download for video resources, photo_download for photo
    resources, so the whole album is captured. Single media returns the pk.
    """
    info = client.media_info(pk)
    mtype = int(getattr(info, "media_type", 0) or 0)
    if mtype == 8:
        resources = list(getattr(info, "resources", None) or [])
        if not resources:
            return [("photo_download", pk)]
        pairs: list[tuple[str, str]] = []
        for r in resources:
            rm = int(getattr(r, "media_type", 0) or 0)
            pairs.append(("clip_download" if rm == 2 else "photo_download", str(r.pk)))
        return pairs
    if mtype == 1:
        return [("photo_download", pk)]
    return [("clip_download", pk)]
```

Replace `_default_download` (line ~126, the instagrapi branch) with:

```python
    if pk:
        try:
            IG_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
            from minimax_mcp import ig_sync

            client = ig_sync.make_client()
            client.delay_range = [0.5, 1.0]
            filepaths: list[str] = []
            for method, target in _download_targets(client, pk):
                out = getattr(client, method)(target, folder=str(IG_DOWNLOADS_DIR))
                if out and Path(out).exists():
                    filepaths.append(str(Path(out)))
            if filepaths:
                return {"ok": True, "filepath": filepaths[0], "filepaths": filepaths}
        except Exception as e:
            logger.warning("instagrapi download failed for %s: %s", pk, e)

    from minimax_mcp.downloader import VideoDownloader

    IG_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    downloader = VideoDownloader(output_dir=IG_DOWNLOADS_DIR, browser="chrome")
    dl = downloader.download(url)
    if dl.get("ok") and dl.get("filepath"):
        dl["filepaths"] = [dl["filepath"]]
    return dl
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python tests/unit_ig_worker.py`
Expected: PASS (all new `_download_targets`/carousel-download lines `[ok]`; earlier `process_message`/`apply_command` sections still pass).

- [ ] **Step 5: Commit**

```bash
git add src/minimax_mcp/ig_worker.py tests/unit_ig_worker.py
git commit -m "feat(ig): download every carousel resource (not just the first)"
```

---

### Task 5: `process_message` concatenates descriptions + categoria tag + worker wiring

**Files:**
- Modify: `src/minimax_mcp/ig_worker.py` (`process_message` line ~39, add `_default_describe`, wire `run()` line ~228 and delete step ~233)
- Test: `tests/unit_ig_worker.py` (extend `process_message` image/carousel sections)

**Interfaces:**
- Consumes: `llm.describe_image(..., categories=...)` (Task 2), `ig_sync.list_categories` (Task 1), `_default_download` (Task 4).
- Produces:
  - `ig_worker._default_describe(filepath: str) -> dict` — wraps `llm.describe_image` with the cached category list.
  - `process_message` iterates `filepaths`, concatenates `conteudo_principal` (fallback `text`), tags `categoria:<name>`, returns `filepaths` in the result.
  - `run()` uses `describe=_default_describe` and deletes all downloaded files after ingest.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit_ig_worker.py` before the final `print()`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python tests/unit_ig_worker.py`
Expected: FAIL (carousel text is currently just the first item; no `filepaths` in result).

- [ ] **Step 3: Write minimal implementation**

In `src/minimax_mcp/ig_worker.py`, replace `process_message` (line ~39) with:

```python
def process_message(
    message: dict,
    *,
    download: Callable[[dict], dict],
    transcribe: Callable[[str], dict] | None,
    describe: Callable[[str], dict] | None,
    ingest: Callable[[str], dict],
) -> dict:
    """Download -> transcribe/describe -> ingest. Pure; all IO injected.

    Videos transcribe the first downloaded file. Images/carousels describe
    EVERY downloaded file and join their conteudo_principal into one text so
    content spread across carousel photos is captured. The first photo's
    categoria becomes a `categoria:<name>` tag.
    """
    if not message:
        return {"status": "error", "error": "empty message"}

    dl = download(message)
    if not dl.get("ok"):
        return {"status": "error", "error": dl.get("error", "download failed")}
    filepaths = dl.get("filepaths") or [dl.get("filepath")]
    filepaths = [f for f in filepaths if f]
    if not filepaths:
        return {"status": "error", "error": "no file downloaded"}

    kind = classify_file(filepaths[0])
    categoria = None
    if kind == "video":
        if transcribe is None:
            return {"status": "error", "error": "no transcribe provided for video"}
        tr = transcribe(filepaths[0])
        if not tr.get("ok"):
            return {"status": "error", "error": tr.get("error", "transcribe failed")}
        text, lang = tr["text"], tr.get("language", "pt")
        doc_type = "video"
    else:
        if describe is None:
            return {"status": "error", "error": "no describe provided for image"}
        pieces: list[str] = []
        for fp in filepaths:
            de = describe(fp)
            if not de.get("ok"):
                return {"status": "error", "error": de.get("error", "describe failed")}
            pieces.append(de.get("conteudo_principal") or de.get("text") or "")
            if categoria is None:
                categoria = de.get("categoria")
        text = "\n\n".join(p for p in pieces if p)
        lang = "pt"
        doc_type = "image"

    extra_tags = [message["collection_name"]] if message.get("collection_name") else None
    if categoria and categoria != "outros":
        extra_tags = (extra_tags or []) + [f"categoria:{categoria}"]
    ing = ingest(
        text,
        source_url=message.get("url"),
        title=message.get("title"),
        platform="instagram",
        doc_type=doc_type,
        language=lang,
        ig_pk=message.get("ig_pk"),
        extra_tags=extra_tags,
    )
    if not ing.get("ok"):
        return {"status": "error", "error": ing.get("error", "ingest failed")}

    return {
        "status": "done",
        "document_id": ing.get("document_id"),
        "kind": kind,
        "filepath": filepaths[0],
        "filepaths": filepaths,
    }
```

Add `_default_describe` after `_default_download` (before `_default_transcribe`, line ~156):

```python
_categories_cache: list[str] | None = None


def _default_describe(filepath: str) -> dict:
    """Describe an image with the category vocabulary threaded in.

    Fetches the category list once per process and reuses it for every
    describe call, so the worker doesn't hit instagrapi per message.
    """
    global _categories_cache
    if _categories_cache is None:
        try:
            from minimax_mcp import ig_sync

            _categories_cache = ig_sync.list_categories(ig_sync.make_client())
        except Exception:
            _categories_cache = ig_sync.list_categories(None)
    return llm.describe_image(filepath, categories=_categories_cache)
```

In `run()`, change the wiring (line ~228) `describe=llm.describe_image,` → `describe=_default_describe,`.

In `run()`, replace the delete-after-ingest step (line ~233) with:

```python
            if IG_DELETE_AFTER_INGEST:
                for fp in res.get("filepaths") or [res.get("filepath")]:
                    try:
                        Path(fp).unlink(missing_ok=True)
                    except OSError:
                        logger.warning("could not delete %s", fp)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python tests/unit_ig_worker.py`
Expected: PASS (new carousel-concatenation + legacy-describe lines `[ok]`, all earlier sections pass).

- [ ] **Step 5: Run the full unit suite**

```bash
uv run pytest -m unit -q
uv run python tests/unit_ig_sync.py && uv run python tests/unit_ig_worker.py && uv run python tests/unit_knowledge.py && uv run python tests/unit_ig_queue.py && uv run python tests/unit_transcriber.py
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/minimax_mcp/ig_worker.py tests/unit_ig_worker.py
git commit -m "feat(ig): concatenate carousel descriptions + categoria tag + describe wiring"
```

---

### Task 6: Wipe existing IG docs and re-ingest with the new pipeline

**Files:**
- Modify: `README.md` (the IG→KB section, add a re-ingest note) and `docs/KNOWLEDGE_BASE.md` (§7) — document the wipe/re-ingest procedure.
- No code changes (unit tests already green from Tasks 1–5).

**Interfaces:**
- Consumes: the worker (`uv run python -m minimax_mcp.ig_worker`), `ig_sync.sync_saved_posts`.
- Produces: fresh docs re-generated with the content-focused vision+summary prompts.

- [ ] **Step 1: Wipe existing IG documents (cascades chunks + embeddings)**

Run from the project root:

```bash
export KB_DATABASE_URL=$(grep '^KB_DATABASE_URL' .env | cut -d= -f2-)
uv run python - <<'PY'
from minimax_mcp import db
from sqlalchemy import text
s = db.get_session()
try:
    n = s.execute(text("DELETE FROM documents WHERE ig_pk IS NOT NULL")).rowcount
    s.commit()
    print(f"deleted {n} IG documents (chunks+embeddings cascade)")
finally:
    s.close()
PY
```

Verify:
```bash
uv run python -c "from minimax_mcp import db; from sqlalchemy import text; s=db.get_session(); print(s.execute(text('SELECT count(*) FROM documents WHERE ig_pk IS NOT NULL')).scalar()); s.close()"
```
Expected: `0`.

- [ ] **Step 2: Reset the worker state so dedup doesn't skip re-upload**

```bash
rm -f downloads/ig/state.json
```

- [ ] **Step 3: Stop the running worker (or let the queue drain) and clear the queue**

```bash
# if running as the host systemd unit:
systemctl --user stop ig-worker-host 2>/dev/null || true
uv run python - <<'PY'
from minimax_mcp import ig_queue
conn = ig_queue.connect()
ch = conn.channel()
ig_queue.declare(ch)
while True:
    m = ch.basic_get(ig_queue.QUEUE, auto_ack=True)
    if not m[0]:
        break
print("ig.saved drained")
ig_queue.close(conn)
PY
```

- [ ] **Step 4: Publish a small re-ingest batch and run the worker**

```bash
export IG_SESSIONID=$(grep '^IG_SESSIONID' .env | cut -d= -f2-)
uv run python - <<'PY'
from minimax_mcp import ig_sync, ig_queue, db
client = ig_sync.make_client()
items = ig_sync.saved_posts(client, max_per_collection=200)
msgs = ig_sync.to_messages(items)
new, skipped = ig_sync.split_new(msgs, db.list_ig_pks(db.get_session()))
print(f"new={len(new)} skipped_existing={skipped}")
conn = ig_queue.connect(); ch = conn.channel(); ig_queue.declare(ch)
# Priority re-ingest: the carousel + the E2E test post first.
prio = [m for m in new if m["ig_pk"] in ("3957796350083531969", "3958786364526561626")]
for m in prio:
    ig_queue.publish(ch, m)
for m in [m for m in new if m not in prio][:10]:
    ig_queue.publish(ch, m)
print("published", len(prio) + min(10, len(new) - len(prio)))
ig_queue.close(conn)
PY
```

Start the worker and watch the log:
```bash
# host-mode daemon (needs Ollama + Postgres on localhost):
uv run --directory "$PROJECT_ROOT" python -m minimax_mcp.ig_worker
```

- [ ] **Step 5: Verify the re-ingested docs are content-focused**

After the worker drains the queue, inspect the new docs:

```bash
export KB_DATABASE_URL=$(grep '^KB_DATABASE_URL' .env | cut -d= -f2-)
uv run python - <<'PY'
from minimax_mcp import db
from sqlalchemy import text
s = db.get_session()
try:
    for r in s.execute(text("""
        SELECT id, ig_pk, type, title, summary, tags
        FROM documents WHERE ig_pk IS NOT NULL ORDER BY id DESC LIMIT 8
    """)).all():
        print(f"#{r.id} ig={r.ig_pk} {r.type} tags={r.tags}")
        print("   title:", (r.title or "")[:70])
        print("   summary:", (r.summary or "")[:200])
finally:
    s.close()
PY
```

Expected:
- doc for ig_pk `3957796350083531969` (carousel) has `categoria:courses`-style tag and a summary listing **the actual courses/content**, not "pessoa com roupas casuais".
- `summary`/`tutorial` answer "qual é a dica/receita" for every re-ingested doc.

- [ ] **Step 6: Update docs**

In `docs/KNOWLEDGE_BASE.md` §7, add a short "Refazer ingest" subsection:

```markdown
**Refazer o ingest** (após mudanças de prompt ou modelo):
1. `DELETE FROM documents WHERE ig_pk IS NOT NULL;` (cascade apaga chunks/embeddings).
2. `rm -f downloads/ig/state.json` (senão o dedup pula os posts).
3. Limpe a fila e republique os posts novos (`ig_sync.sync_saved_posts`).
4. Rode o worker no host; confira os novos summaries.
```

In `README.md` IG→KB section, after the "Running it" block, add:

```markdown
**Re-ingest after prompt/model changes:** wipe IG docs from the KB, reset
`downloads/ig/state.json`, drain the queue, and re-publish — see
`docs/KNOWLEDGE_BASE.md` §7 "Refazer ingest".
```

- [ ] **Step 7: Commit**

```bash
git add README.md docs/KNOWLEDGE_BASE.md
git commit -m "docs(kb): re-ingest procedure for the content-focused pipeline"
```

---

## Self-review notes (filled by the author after writing)

- **Spec coverage:** §1 list_categories → Task 1. §2 structured vision prompt → Task 2. §3 carousel all photos → Task 4 (+ Task 5 concatenation). §4 summary premise generalized → Task 3. §5 categoria→tag → Task 5. §6 tests → Tasks 1–5. §7 wipe & re-ingest → Task 6. All covered.
- **Back-compat:** `_pick_download_target` is removed; its old unit tests were replaced in Task 4 (Task 4 explicitly deletes that block). No other module imports `_pick_download_target` (verified via grep during exploration).
- **Type consistency:** `list_categories(client)` / `build_vision_prompt(categories)` / `describe_image(path, *, model, categories)` / `generate_structured(text, *, is_image)` / `_download_targets(client, pk)` / `_default_describe(filepath)` — the names and signatures used in later tasks match the definitions in Tasks 1–5.
- **Placeholder scan:** no TBD/TODO; every step has concrete code or commands.
