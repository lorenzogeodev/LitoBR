import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1] / "litobr"


def _mod(nome="catalogo"):
    spec = importlib.util.spec_from_file_location(f"litobr_{nome}", RAIZ / f"{nome}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


geo = _mod()


def test_litobr_catalogo():
    cat = geo.carregar()
    assert len(cat["estados"]) == 27 and set(cat["ufs_bbox"]) == set(cat["estados"])
    assert all(t["chave"] == "LITO" or t["chave"] in cat["endpoints_temas"] for t in cat["temas"])
    # todo produto tem escala e ano (ou o motivo de não ter) e todo item do RIGeo tem UUID
    for e in cat["escalas"] + list(cat["endpoints_temas"].values()):
        assert {"escala", "ano", "ano_rotulo"} <= set(e)
    itens = list(cat["estados"].values()) + list(cat["projetos_regionais"].values())
    for d in itens:
        assert geo.uuid_rigeo(d["url"]) and isinstance(d["ano"], int) and 1990 < d["ano"] < 2030
    assert sum(1 for d in cat["estados"].values() if d["arquivo"]) == 26        # só a Paraíba sem SIG
    assert len(cat["projetos_regionais"]) == 16
    r = geo.resolver_caminho_sgb
    assert r("geologia/litoestratigrafia_100000/MapServer/0") == "geologia/litoestratigrafia_100000/MapServer/0"
    assert r("hidrologia/aquifero_uf_sp/MapServer/14") == "hidrologia/aquifero_uf_sp/MapServer/14"
    assert r("Hosted/medidas_estruturais_ds/FeatureServer/0") == "Hosted/medidas_estruturais_ds/FeatureServer/0"
    assert r("geologia/x/MapServer") == "geologia/x/MapServer/0"
    with pytest.raises(ValueError):
        r("geologia/sem_servidor")


def test_litobr_plano():
    cat = geo.carregar()
    i_est = next(i for i, e in enumerate(cat["escalas"]) if e["tipo"] == "ESTADUAL")
    i_bdia = next(i for i, e in enumerate(cat["escalas"]) if e["tipo"] == "BDIA_WFS")
    i_1m = next(i for i, e in enumerate(cat["escalas"]) if e.get("ano") == 2004)
    i_lito = next(i for i, t in enumerate(cat["temas"]) if t["chave"] == "LITO")
    i_siagas = next(i for i, t in enumerate(cat["temas"]) if t["chave"] == "SIAGAS")
    i_cav = next(i for i, t in enumerate(cat["temas"]) if t["chave"] == "CAVERNAS")
    p = geo.plano_download(cat, i_est, i_lito, "AC")
    assert p["estadual"] and p["nome_uf"] == "Acre" and p["fallback_bdia"] and p["tag"] == "AC_Estadual"
    with pytest.raises(ValueError, match="UF"):
        geo.plano_download(cat, i_est, i_lito, None)
    assert geo.plano_download(cat, i_bdia, i_lito, None)["tipo"] == "BDIA_WFS"
    p = geo.plano_download(cat, i_1m, i_lito, None)
    assert (p["escala"], p["ano"]) == ("1:1.000.000", 2004)
    p = geo.plano_download(cat, i_est, i_siagas, None)      # tema com serviço próprio ignora escala/UF
    assert p["caminho"] == "hidrologia/SIAGAS_MODDAD/MapServer/0" and not p["fallback_bdia"]
    assert p["ano_rotulo"] == "atualização contínua"
    assert geo.plano_download(cat, i_bdia, i_cav, None)["ano"] == 2020
    assert geo.plano_bdia(cat)["caminho"] == "BDIA:geol_area"


# nomes como o servidor do SGB devolveu em 11/11/2026 (litoestratigrafia_estados/MapServer/layers)
CAMADAS_ESTADUAIS = [
    {"id": 29, "name": "Acre - 1:750.000 [2026]"}, {"id": 0, "name": "Amapá - 1:500.000 [2024]"},
    {"id": 2, "name": "Ceará - 1:500.000 [2020]"}, {"id": 13, "name": "Rio Grande do Norte - 1:500.000 [2021]"},
    {"id": 14, "name": "Rio Grande do Sul - 1:750.000 [2008]"}, {"id": 7, "name": "Mato Grosso do Sul - 1:1.000.000 [2006]"},
    {"id": 6, "name": "Mato Grosso - 1:1.000.000 [2006]"}, {"id": 99, "name": "camada sem padrão"},
]


def test_litobr_estadual_e_status():
    assert geo.ler_nome_camada_estadual("Acre - 1:750.000 [2026]") == ("Acre", "1:750.000", 2026)
    assert geo.ler_nome_camada_estadual("Unidades litoestratigráficas") is None
    e = geo.escolher_camada_estadual
    assert e(CAMADAS_ESTADUAIS, "Acre") == {"id": 29, "escala": "1:750.000", "ano": 2026}   # antes: Acre -> Amapá
    assert e(CAMADAS_ESTADUAIS, "Amapá")["id"] == 0
    assert e(CAMADAS_ESTADUAIS, "Mato Grosso")["id"] == 6            # não confunde com Mato Grosso do Sul
    assert e(CAMADAS_ESTADUAIS, "Rio Grande do Sul")["id"] == 14
    assert e(CAMADAS_ESTADUAIS, "Bahia") is None and e(None, "Acre") is None
    st = geo.status_produto
    assert (st(2014), st(2013), st(None, "atualização contínua"), st(None, "varia por folha")) == \
        ("estavel", "legado", "continuo", "desconhecido")
    assert geo.resumo_produto("1:250.000", 2017) == "1:250.000 · 2017"
    assert geo.resumo_produto(None, None, "varia por folha") == "escala não informada · varia por folha"
    meta = {"dc.title": [{"value": "Mapa geológico do estado do Acre"}], "dc.date.issued": [{"value": "2017-03"}],
            "dc.identifier.citation": [{"value": "Brasília: SGB, 2017. 1 mapa, color. Escala 1: 750.000."}]}
    assert geo.escala_ano_do_item(meta) == ("1:750.000", 2017)
    assert geo.escala_ano_do_item({}) == (None, None)


def test_litobr_rigeo_e_notas():
    u = "437cf2ae-9bfd-4299-8cf7-236b280963e6"
    assert geo.uuid_rigeo(f"https://rigeo.sgb.gov.br/items/{u}") == u
    assert geo.uuid_rigeo("https://rigeo.sgb.gov.br/handle/doc/8665") is None
    assert geo.eh_link_direto("https://x/a/mapa.ZIP?download=1") and not geo.eh_link_direto("https://x/items/zip")
    assert geo.escolher_bundle([{"name": "THUMBNAIL"}, {"name": "ORIGINAL"}])["name"] == "ORIGINAL"
    assert geo.escolher_bundle([]) is None
    bs = [{"name": "relatorio.pdf", "_links": {"content": {"href": "a"}}},
          {"name": "dados.gpkg", "_links": {"content": {"href": "b"}}},
          {"name": "SIG_geologia.zip", "_links": {"content": {"href": "c"}}},
          {"name": "outro.zip", "_links": {}}]
    assert geo.escolher_bitstream(bs) == ("SIG_geologia.zip", "c")
    assert geo.escolher_bitstream(bs, "dados.gpkg") == ("dados.gpkg", "b")         # o conferido ganha
    assert geo.escolher_bitstream(bs, "nao_existe.zip") == ("SIG_geologia.zip", "c")
    assert geo.escolher_bitstream(bs[:1]) is None
    assert geo.nota_camada("litologia", 100, True) > geo.nota_camada("drenagem", 5000, False)
    assert geo.nota_camada("vazia", 0, True) is None



def test_litobr_recomendacao():
    cat = geo.carregar()
    assert geo.denominador("1:75.000") == 75000 and geo.denominador("1:1.000.000") == 1000000
    assert geo.denominador(None) is None and geo.denominador("conforme o estado") is None
    # tela sobre o Quadrilátero Ferrífero (perto de Ouro Preto)
    rec = geo.recomendar(cat, (-43.7, -20.45, -43.4, -20.2), "MG")
    chaves = [r["chave"] for r in rec]
    assert chaves[0] == "QF_CENTRAL"                       # o mais detalhado primeiro (1:75.000)
    assert "MG" in chaves and "TAPAJOS" not in chaves
    assert chaves.index("QF_CENTRAL") < chaves.index("MG")
    # tela no Tapajós
    assert geo.recomendar(cat, (-56.5, -6.5, -56.0, -6.0), "PA")[0]["chave"] == "TAPAJOS"
    # sem contorno no serviço: entra pela UF (Juma, AM)
    assert "JUMA" in [r["chave"] for r in geo.recomendar(cat, (-60.5, -8.0, -60.0, -7.5), "AM")]
    # Paraíba não tem pacote SIG: nunca é recomendada
    assert "PB" not in [r["chave"] for r in geo.recomendar(cat, (-36.0, -7.3, -35.5, -7.0), "PB")]
    assert geo.recomendar(cat, (10.0, 40.0, 11.0, 41.0)) == []
    assert geo.ufs_na_area((-47.9, -15.9, -47.8, -15.7), cat["ufs_bbox"])[:2] == ["DF", "GO"]


def test_litobr_bdia_tem_escala_e_ano():
    cat = geo.carregar()
    p = geo.plano_bdia(cat)
    assert p["escala"] == "1:250.000" and p["ano"] == 2025
    assert geo.status_produto(p["ano"], p["ano_rotulo"]) == "estavel"


def test_litobr_servico_bdia_devolve_escala(tmp_path, monkeypatch):
    """A rota do BDIA tem que devolver escala e ano, senão o metadado sai 'escala não informada'."""
    import sys
    from unittest.mock import MagicMock

    for nome in ("qgis", "qgis.core", "qgis.PyQt", "qgis.PyQt.QtCore", "qgis.PyQt.QtNetwork"):
        monkeypatch.setitem(sys.modules, nome, MagicMock())
    for nome in [m for m in sys.modules if m.startswith("litobr")]:
        monkeypatch.delitem(sys.modules, nome)
    servicos = __import__("litobr.servicos", fromlist=["x"])
    geojson = b'{"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": null, "properties": {}}]}'
    monkeypatch.setattr(servicos.rede, "get_bytes", lambda *a, **k: geojson)
    cat = geo.carregar()
    res = servicos.baixar_nuvem(cat, geo.plano_bdia(cat), [-44, -21, -43, -20], tmp_path / "x.geojson", MagicMock())
    assert res["escala"] == "1:250.000" and res["ano"] == 2025 and res["url"].startswith("https://")
