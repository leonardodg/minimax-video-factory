#!/usr/bin/env python3
"""Unit tests for ig_sync.py — duck-typed Media objects, injected client.

Rode com o ambiente do projeto:

    uv run pytest -m unit                    (a suíte)
    uv run python tests/unit_ig_sync.py      (só este)

⚠️ **Não rode com o `python3` do sistema.** Ele não tem `instagrapi`, e a
ausência dela NÃO quebra o import deste arquivo -- ela troca silenciosamente o
resultado de `post_url`, que calcula o shortcode com o `InstagramIdCodec` e cai
num fallback quando o import falha:

    com instagrapi   post_url(3939152570070606095) -> .../p/DaqrmRXICEP/
    sem instagrapi   post_url(3939152570070606095) -> .../p/3939152570070606095/

Duas asserções passam a falhar, e a saída é indistinguível de um bug de código.
Aconteceu em 2026-08-12: as duas falhas foram diagnosticadas como defeito real
do `post_url` e reportadas como pendência, inclusive numa nota de commit. Rodar
o mesmo teste na `main` "confirmou" -- com o mesmo python errado. A guarda
abaixo existe para que isso pare de ser possível.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    import instagrapi  # noqa: F401
except ImportError:
    sys.exit(
        "\n  ERRO: instagrapi não está instalado neste interpretador.\n"
        f"  ({sys.executable})\n\n"
        "  Este teste não roda sem ela: `post_url` cairia num fallback e duas\n"
        "  asserções falhariam por motivo de ambiente, parecendo bug de código.\n\n"
        "  Rode assim:  uv run python tests/unit_ig_sync.py\n"
        "         ou:   uv run pytest -m unit\n"
    )

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


from minimax_mcp import ig_sync


class User:
    username = "anajcodes"


class Media:
    def __init__(self, pk, media_type, caption="", user=None):
        self.pk = pk
        self.media_type = media_type
        self.caption_text = caption
        self.user = user or User()


print("== unit_ig_sync: to_messages ==")
items = [
    Media("1001", 2, "Reel de teste\nsegunda linha"),
    Media("1002", 1, "Foto"),
    Media("1003", 8),
    Media(None, 2),
]
entries = [{"media": m, "collection_name": None} for m in items]
msgs = ig_sync.to_messages(entries)

if len(msgs) == 3:
    ok("to_messages keeps video/image/carousel, drops pk-less")
else:
    bad(f"to_messages returned {len(msgs)} messages")

m0 = msgs[0]
if (
    m0["ig_pk"] == "1001"
    and m0["media_type"] == "video"
    # Shortcode, não o pk: `/p/` só resolve com o código. Esta linha afirmava
    # `/p/1001/`, que é o formato que gravou link quebrado em todo documento e
    # fazia o fallback de yt-dlp levar HTTP 400.
    and m0["url"] == "https://www.instagram.com/p/Pp/"
    and m0["owner_username"] == "anajcodes"
    and m0["title"] == "Reel de teste"
    and m0["collection_name"] is None
    and m0["status"] == "queued"
):
    ok("to_messages maps video Media to the message contract")
else:
    bad(f"video message = {m0!r}")

# O `code` que o Instagram manda tem de vencer o calculado -- e quando ele não
# vem, o calculado tem de dar exatamente o mesmo. Verificado com um post real
# em 2026-08-10: pk 3939152570070606095 -> DaqrmRXICEP pelos dois caminhos.
if (
    ig_sync.post_url("3939152570070606095", "DaqrmRXICEP")
    == ig_sync.post_url("3939152570070606095")
    == "https://www.instagram.com/p/DaqrmRXICEP/"
):
    ok("post_url: o code informado e o calculado do pk concordam")
else:
    bad(f"post_url divergiu: {ig_sync.post_url('3939152570070606095')!r}")

# Um pk que não é número não pode derrubar a listagem inteira.
if ig_sync.post_url("nao-numerico") == "https://www.instagram.com/p/nao-numerico/":
    ok("post_url degrada sem levantar quando o pk não é numérico")
else:
    bad(f"post_url com lixo = {ig_sync.post_url('nao-numerico')!r}")

if msgs[1]["media_type"] == "image" and msgs[2]["media_type"] == "carousel":
    ok("image and carousel media_types map correctly")
else:
    bad(f"media types = {[m['media_type'] for m in msgs]}")

if ig_sync.to_messages([{"media": Media("2001", 2), "collection_name": "Receitas"}])[0]["collection_name"] == "Receitas":
    ok("to_messages carries the collection name")
else:
    bad("collection_name not propagated")

print("== unit_ig_sync: split_new ==")
new, skipped = ig_sync.split_new(msgs, existing_pks={"1001"})
if len(new) == 2 and skipped == 1:
    ok("split_new drops existing ig_pks")
else:
    bad(f"split_new = new={len(new)} skipped={skipped}")

print("== unit_ig_sync: saved_posts (modern API) ==")
class Col:
    def __init__(self, cid, name, ctype):
        self.id, self.name, self.type = cid, name, ctype


class FakeClient:
    def collections(self):
        return [
            Col("ALL_MEDIA_AUTO_COLLECTION", "All posts", "ALL_MEDIA_AUTO_COLLECTION"),
            Col("c2", "Receitas", "MEDIA"),
        ]

    def collection_medias(self, cid, amount=200):
        return {
            "ALL_MEDIA_AUTO_COLLECTION": items[:2],
            "c2": [items[2]],
        }[cid]

    def saved_posts(self):  # legacy path, not exercised here
        return items


collected = ig_sync.saved_posts(FakeClient())
if len(collected) == 3:
    ok("saved_posts collects All posts + named collections")
else:
    bad(f"saved_posts returned {len(collected)} entries")
# A listagem tem de pedir TODAS as páginas.
# Um teto silencioso é o pior modo de falha desta sincronização: devolve um lote
# parcial que se parece com punição do Instagram, e as duas causas pedem reações
# opostas. Medido em 2026-08-10: a catch-all guarda 3618 posts, e o teto antigo
# de 200 teria entregado 200.
asked = []


class RecordingClient(FakeClient):
    def collection_medias(self, cid, amount=200):
        asked.append(amount)
        return super().collection_medias(cid, amount)


ig_sync.saved_posts(RecordingClient())
if asked and all(a == 0 for a in asked):
    ok("saved_posts pede todas as páginas (amount=0), sem teto por coleção")
else:
    bad(f"saved_posts pediu amount={asked} — um teto trunca o sync em silêncio")

names = {e["collection_name"] for e in collected}
# The catch-all maps to None, not to a name. It holds every saved post, so its
# name says nothing about the post -- and as a tag it was landing on nearly
# every document and drowning the ones that mean something.
if names == {None, "Receitas"}:
    ok("the catch-all yields no collection name; real ones are kept")
else:
    bad(f"collection names = {names}")

print("== unit_ig_sync: sync_saved_posts ==")
published = []


def fake_publish(msg):
    published.append(msg)


result = ig_sync.sync_saved_posts(FakeClient(), existing_pks={"1001"}, publish_fn=fake_publish)
if (
    result["ok"]
    and result["published"] == 2
    and result["skipped_existing"] == 1
    and result["total"] == 3
    and len(published) == 2
):
    ok("sync_saved_posts publishes only new posts and reports counts")
else:
    bad(f"sync_saved_posts = {result!r}")

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

print("== unit_ig_sync: título ausente não vira placeholder ==")


class _NoCaption:
    pk = "9001"
    media_type = 2
    caption_text = ""
    user = None


t = ig_sync.to_messages([{"media": _NoCaption(), "collection_name": None}])[0]["title"]
if t is None:
    ok("a post with no caption yields title=None")
else:
    bad(
        f"title = {t!r}. A placeholder is truthy, so knowledge.ingest_text never "
        "reaches its own fallback and the document is literally titled that."
    )

print("== unit_ig_sync: dedupe_by_pk prefere a coleção nomeada ==")

DUPES = [
    {"ig_pk": "1", "collection_name": None, "title": "a"},
    {"ig_pk": "1", "collection_name": "Dev", "title": "a"},
    {"ig_pk": "2", "collection_name": "Receitas", "title": "b"},
    {"ig_pk": "1", "collection_name": None, "title": "a"},
]
d = ig_sync.dedupe_by_pk(DUPES)

if len(d) == 2:
    ok("three messages for one post collapse into one")
else:
    bad(f"dedupe_by_pk returned {len(d)} messages, expected 2")

if d[0]["collection_name"] == "Dev":
    ok("the named collection wins over the catch-all, whatever the order")
else:
    bad(
        f"kept collection_name={d[0]['collection_name']!r}. Whichever copy is "
        "consumed first decides the tag, so the catch-all must never win."
    )

if [m["ig_pk"] for m in d] == ["1", "2"]:
    ok("input order is preserved, so a caller's priority ordering survives")
else:
    bad(f"order changed: {[m['ig_pk'] for m in d]}")

new, skipped = ig_sync.split_new(DUPES, set())
if len(new) == 2:
    ok("split_new dedupes within the batch, not just against the database")
else:
    bad(f"split_new published {len(new)} messages for 2 distinct posts")

print("== unit_ig_sync: um post podre não leva a página junto ==")

# O defeito de 2026-08-10, reduzido ao osso: o instagrapi monta a página numa
# list comprehension, então UM item que não converte derruba os outros -- e a
# exceção ainda sobe pelo laço de paginação e apaga as páginas anteriores. Foi
# assim que a catch-all inteira (3618 posts) sumiu e ~500 posts que só existem
# nela nunca chegaram a virar mensagem na fila.


class MediaFake:
    """Só o que `to_messages` usa, mais o `code` que o modelo real exige."""

    def __init__(self, raw):
        self.pk = raw["pk"]
        self.code = raw["code"]        # KeyError se faltar -- é o defeito real
        self.media_type = raw.get("media_type", 2)
        self.caption_text = raw.get("caption", "")
        self.user = User()


PAGINA = [
    {"pk": "1", "code": "AAA"},
    {"pk": "2"},                        # ← o post degradado, sem `code`
    {"pk": "3", "code": "CCC"},
]

descartes = []
sobreviventes = ig_sync.parse_items_tolerant(
    PAGINA, MediaFake, on_discard=lambda raw, exc: descartes.append((raw, exc))
)

if [m.pk for m in sobreviventes] == ["1", "3"]:
    ok("os posts sadios da página sobrevivem ao item malformado")
else:
    bad(
        f"sobraram {[m.pk for m in sobreviventes]}, esperado ['1', '3']. "
        "Um item ruim ainda está derrubando a página inteira."
    )

if len(descartes) == 1 and descartes[0][0]["pk"] == "2":
    ok("o descarte é contado e entrega o payload cru de quem falhou")
else:
    bad(f"descartes = {descartes!r}. Perda silenciosa é o modo de falha a evitar.")

# A ordem importa: o item ruim está no MEIO. Se a implementação parasse no
# primeiro erro em vez de seguir, o post "3" sumiria e o teste acima passaria
# por acidente numa página de dois itens.
if len(sobreviventes) == 2 and sobreviventes[-1].pk == "3":
    ok("a listagem continua DEPOIS do item ruim, não para nele")
else:
    bad("a conversão parou no primeiro erro em vez de seguir a página")


def registrador_quebrado(raw, exc):
    raise OSError("disco cheio")


try:
    ainda = ig_sync.parse_items_tolerant(PAGINA, MediaFake, on_discard=registrador_quebrado)
    if [m.pk for m in ainda] == ["1", "3"]:
        ok("um registrador que falha não custa a página")
    else:
        bad(f"sobraram {[m.pk for m in ainda]} com o registrador quebrado")
except Exception as exc:
    bad(f"o registrador quebrado derrubou a listagem: {exc!r} — trocar 500 posts por um log")

print("== unit_ig_sync: o descarte vai para o disco, com o payload cru ==")

import json as _json
import tempfile as _tempfile

with _tempfile.TemporaryDirectory() as _tmp:
    _alvo = str(Path(_tmp) / "sub" / "descartados.jsonl")
    ig_sync.registrar_descarte({"pk": "2", "id": "2_9"}, KeyError("code"), caminho=_alvo)
    ig_sync.registrar_descarte({"pk": "7"}, ValueError("outro"), caminho=_alvo)
    _linhas = [_json.loads(x) for x in Path(_alvo).read_text(encoding="utf-8").splitlines()]

    if len(_linhas) == 2:
        ok("cada descarte é uma linha JSONL, escrita na hora (append)")
    else:
        bad(f"gravou {len(_linhas)} linhas, esperado 2")

    if _linhas[0]["ig_pk"] == "2" and _linhas[0]["raw"] == {"pk": "2", "id": "2_9"}:
        ok("o payload cru é preservado — é a única cópia que sobra do post")
    else:
        bad(f"registro = {_linhas[0]!r}")

    if "code" in _linhas[0]["faltando"]:
        ok("o registro diz QUAL campo obrigatório faltou")
    else:
        bad(f"faltando = {_linhas[0]['faltando']!r}, esperado conter 'code'")

print("== unit_ig_sync: a coleção guarda-chuva não vira tag ==")

if ig_sync.to_messages([{"media": Media("2002", 2), "collection_name": None}])[0][
    "collection_name"
] is None:
    ok("collection_name=None survives to the message")
else:
    bad("None collection_name was replaced by something")

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("PASS")
