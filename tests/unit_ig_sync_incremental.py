#!/usr/bin/env python3
"""A sincronizacao publica conforme enumera, e na ordem que preserva a colecao.

Roda sem rede, sem banco e sem fila: o client do Instagram e o publish_fn sao
dublês.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from minimax_mcp import ig_sync  # noqa: E402

falhas = []


def ok(msg):
    print(f"  [ok]   {msg}")


def erro(msg):
    print(f"  [FALHA] {msg}")
    falhas.append(msg)


class Media:
    def __init__(self, pk):
        self.pk = pk
        self.media_type = 1          # imagem
        self.caption_text = f"post {pk}"
        self.code = f"c{pk}"
        self.user = type("U", (), {"username": "alguem"})()


class Colecao:
    def __init__(self, cid, nome, catch_all=False):
        self.id = cid
        self.name = nome
        self.type = "ALL_MEDIA_AUTO_COLLECTION" if catch_all else "MEDIA"


class Client:
    """A catch-all vem PRIMEIRO, como o Instagram costuma devolver."""
    def __init__(self):
        self._cols = [
            Colecao(0, "All posts", catch_all=True),
            Colecao(1, "Dev"),
            Colecao(2, "Receitas"),
        ]
        self._medias = {
            0: [Media("100"), Media("200"), Media("300")],   # todos
            1: [Media("100")],                               # 100 e de Dev
            2: [Media("200")],                               # 200 e de Receitas
        }

    def collections(self):
        return self._cols

    def collection_medias(self, cid, amount=0):
        return self._medias[cid]


print("== ig_sync incremental: a catch-all e enumerada POR ULTIMO ==")
nomes = [nome for nome, _ in ig_sync.saved_posts_by_collection(Client())]
if nomes[-1] is None and set(nomes[:-1]) == {"Dev", "Receitas"}:
    ok(f"ordem: {nomes[:-1]} e a catch-all no fim")
else:
    erro(f"ordem errada: {nomes}")

print()
print("== a colecao nomeada vence, mesmo publicando incrementalmente ==")
publicadas = []
r = ig_sync.sync_saved_posts(Client(), existing_pks=set(),
                             publish_fn=publicadas.append)
por_pk = {m["ig_pk"]: m["collection_name"] for m in publicadas}
if por_pk.get("100") == "Dev" and por_pk.get("200") == "Receitas":
    ok("100 -> Dev, 200 -> Receitas (nao perderam a tag para a catch-all)")
else:
    erro(f"tags perdidas: {por_pk}")
if por_pk.get("300") is None and "300" in por_pk:
    ok("300 -> sem colecao (so existe na catch-all), como esperado")
else:
    erro(f"300 saiu como {por_pk.get('300')!r}")

print()
print("== um post salvo em N colecoes e publicado UMA vez ==")
if len(publicadas) == 3:
    ok("3 mensagens para 3 posts distintos (nao 5)")
else:
    erro(f"publicou {len(publicadas)}: {[m['ig_pk'] for m in publicadas]}")

print()
print("== progress_fn recebe sinal de vida por colecao ==")
eventos = []
ig_sync.sync_saved_posts(Client(), existing_pks=set(),
                         publish_fn=lambda m: None, progress_fn=eventos.append)
if len(eventos) == 3 and all("published_total" in e for e in eventos):
    ok(f"3 eventos, acumulado final = {eventos[-1]['published_total']}")
else:
    erro(f"eventos: {eventos}")

print()
print("== existing_pks pula o que ja esta no banco ==")
pub2 = []
r2 = ig_sync.sync_saved_posts(Client(), existing_pks={"100", "200"},
                              publish_fn=pub2.append)
if [m["ig_pk"] for m in pub2] == ["300"] and r2["published"] == 1:
    ok("so o 300 foi publicado; 100 e 200 contados como pulados")
else:
    erro(f"publicou {[m['ig_pk'] for m in pub2]}, resultado {r2}")

print()
print("== reprocessar=True ignora o banco e reenfileira tudo ==")
pub3 = []
r3 = ig_sync.sync_saved_posts(Client(), existing_pks={"100", "200", "300"},
                              publish_fn=pub3.append, reprocessar=True)
if r3["published"] == 3 and len(pub3) == 3:
    ok("3 republicados apesar de todos constarem no banco")
else:
    erro(f"reprocessar publicou {r3['published']}: {[m['ig_pk'] for m in pub3]}")

print()
print("== saved_posts() antigo continua devolvendo a lista achatada ==")
plano = ig_sync.saved_posts(Client())
if len(plano) == 5 and all("media" in e and "collection_name" in e for e in plano):
    ok("5 pares (post, colecao), forma inalterada")
else:
    erro(f"saved_posts devolveu {len(plano)} entradas")

print()
print("ALL PASS" if not falhas else f"{len(falhas)} FALHA(S)")
sys.exit(1 if falhas else 0)
