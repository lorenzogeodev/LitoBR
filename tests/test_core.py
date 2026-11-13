from datetime import datetime

import pytest

from litobr.core import abnt, arcgis, classificacao as cl, texto
from litobr.core.erros import ErroServico


def test_texto():
    assert texto.normalizar("  Formação São João ") == "formacao sao joao"
    assert texto.normalizar(None) == ""
    assert texto.eh_nulo(None) and texto.eh_nulo("") and texto.eh_nulo(" NULL ") and not texto.eh_nulo(0)
    assert texto.tokens("Ouro (Au), caulim") == ["ouro", "au", "caulim"]
    assert texto.achar_campo(["OBJECTID", "Sigla_Unid", "NOME"], ["sigla", "sigla_unid"]) == "Sigla_Unid"
    assert texto.achar_campo(["a"], ["b"]) is None
    assert texto.nome_arquivo_seguro("Benzo(a)pireno / µg") == "benzo_a_pireno_g"


def test_abnt():
    dt = datetime(2026, 11, 5)
    assert abnt.data_acesso(dt) == "5 nov. 2026"
    assert abnt.data_acesso(datetime(2026, 5, 10)) == "10 maio 2026"
    r = abnt.referencia_online("Serviço Geológico do Brasil (SGB/CPRM)", "Mapa X.", "https://x/y", "Brasília", "SGB/CPRM", dt=dt)
    assert r == ("SERVIÇO GEOLÓGICO DO BRASIL (SGB/CPRM). Mapa X. Brasília: SGB/CPRM, [2026]. "
                 "Disponível em: https://x/y. Acesso em: 5 nov. 2026.")
    assert "[S. l.]: MapBiomas, 2024." in abnt.referencia_online("Projeto MapBiomas", "Água", "u", None, "MapBiomas", 2024, dt)
    assert abnt.credito_mapa(["SGB", "ANA", "ANA"], "EPSG:31983", dt) == \
        "Fonte dos dados: ANA; SGB. Acesso em nov. 2026. SRC: EPSG:31983."
    assert abnt.bloco_referencias(["b", "a", "a"], ["X"], "EPSG:1", dt).count("\n\na\n\nb\n") == 1


@pytest.mark.parametrize("txt,esperado", [
    ("Caulim", "Minerais Industriais/Fertilizantes"),   # antes: 'au' in 'caulim' -> Metais Nobres
    ("Água mineral", "Geral"),                           # antes: 'ag' in 'agua' -> Metais Nobres
    ("Magnesita", "Minerais Industriais/Fertilizantes"),
    ("Ouro", "Metais Nobres (Au, Ag, PGM)"), ("Au", "Metais Nobres (Au, Ag, PGM)"),
    ("Areia", "Construção Civil (Areia, Brita)"), ("Minério de ferro", "Metais Base e Ferrosos"),
    ("Urânio", "Energéticos (Carvão, Urânio)"), ("Quartzo rosa", "Gemas e Ornamentais"), ("", "Geral"),
])
def test_substancia(txt, esperado):
    assert cl.classe_substancia(txt) == esperado


def test_cor_geologica():
    granito = ("#f46d75", "#99000d")
    # 'G' solto na sigla não é mais granito
    assert cl.cor_geologica("K2bg", "Formação Bauru", "arenito") == ("#a1d99b", "#238b45")
    assert cl.cor_geologica("NP3_gamma_2i", "Suíte X", "granito") == granito
    assert cl.cor_geologica("NP3γ2", "", "") == granito
    # NP não cai mais em Cenozoico por começar com N
    assert cl.cor_geologica("NP2sc", "Grupo Y", "xisto") == ("#fdae6b", "#a63603")
    assert cl.cor_geologica("N1b", "Formação Barreiras", "arenito") == ("#fff7bc", "#d95f0e")
    assert cl.cor_geologica("PP2c", "", "") == ("#d8b365", "#543005")
    assert cl.cor_geologica("P1i", "Formação Irati", "folhelho") == ("#9ecae1", "#2171b5")
    assert cl.cor_geologica("", "Represa", "") == ("#a6cee3", "#1f78b4")
    assert cl.cor_geologica("", "", "") == cl.COR_PADRAO
    assert cl.escurecer("#102030", 60) == "#000000" and cl.rgb_hex(255, 0, 16) == "#ff0010"


def test_classes_hidro_e_uf():
    assert cl.classe_aquifero("Cárstico") == "carstico" and cl.classe_aquifero("Fraturado") == "fissural"
    assert cl.classe_poco("Poço Tubular") == "tubular" and cl.classe_poco("Surgência") == "nascente"
    assert cl.classe_afloramento("Corte de estrada") == "Corte de Estrada / Rodovia"
    bb = {"CE": (-41.42, -7.86, -37.25, -2.78), "RN": (-38.58, -6.98, -34.97, -4.83)}
    assert cl.uf_por_ponto(-39.0, -5.0, bb) == "CE"
    assert cl.uf_por_ponto(-38.0, -6.0, bb) == "RN"        # menor bbox ganha
    assert cl.uf_por_ponto(0.0, 0.0, bb) is None             # antes: caía em 'CE'


def _servidor(total, pagina_max, ignora_offset=False):
    chamadas = []

    def buscar(url, params):
        chamadas.append(params)
        off = 0 if ignora_offset else params["resultOffset"]
        n = min(params["resultRecordCount"], pagina_max, total - off)
        feats = [{"type": "Feature", "id": off + i, "properties": {}} for i in range(max(n, 0))]
        return {"features": feats, "exceededTransferLimit": off + n < total, "crs": {"x": 1}}
    return buscar, chamadas


def test_paginar():
    buscar, ch = _servidor(2500, 1000)
    feats, crs = arcgis.paginar(buscar, "u", "1,2,3,4")
    assert len(feats) == 2500 and len({f["id"] for f in feats}) == 2500 and crs == {"x": 1}
    assert [c["resultOffset"] for c in ch] == [0, 1000, 2000] and ch[0]["geometry"] == "1,2,3,4"
    # servidor com teto menor que o pedido
    feats, _ = arcgis.paginar(*_servidor(700, 300)[:1], "u")
    assert len(feats) == 700
    # servidor que ignora offset não entra em laço
    buscar, ch = _servidor(5000, 1000, ignora_offset=True)
    feats, _ = arcgis.paginar(buscar, "u")
    assert len(feats) == 1000 and len(ch) == 2
    assert arcgis.paginar(lambda u, p: {"features": []}, "u") == ([], None)
    with pytest.raises(ErroServico, match="Invalid URL"):
        arcgis.paginar(lambda u, p: {"error": {"code": 400, "message": "Invalid URL"}}, "u")
    feats, _ = arcgis.paginar(*_servidor(5000, 1000)[:1], "u", cancelado=lambda: True)
    assert feats == []
    assert "geometry" not in arcgis.params_query(None)


def _servidor_sem_paginacao(total, teto=1000):
    """Imita o serviço Cavernas do SGB: supportsPagination=false, maxRecordCount=1000."""
    chamadas = []

    def buscar(url, params):
        chamadas.append(dict(params))
        if "resultOffset" in params:
            return {"error": {"code": 400, "message": "Pagination is not supported.", "details": []}}
        if params.get("returnIdsOnly") == "true":
            return {"objectIdFieldName": "OBJECTID", "objectIds": list(range(total, 0, -1))}
        if "objectIds" in params:
            ids = [int(x) for x in params["objectIds"].split(",")]
            assert len(ids) <= teto
            return {"features": [{"type": "Feature", "id": i, "properties": {}} for i in ids], "crs": {"y": 2}}
        return {"features": [{"type": "Feature", "id": i} for i in range(1, min(total, teto) + 1)],
                "exceededTransferLimit": total > teto}
    return buscar, chamadas


def test_paginar_sem_suporte_a_paginacao():
    # o servidor recusa o offset: troca sozinho pra lista de ObjectIDs
    buscar, ch = _servidor_sem_paginacao(2345)
    feats, crs = arcgis.paginar(buscar, "u", "1,2,3,4")
    assert len(feats) == 2345 and len({f["id"] for f in feats}) == 2345 and crs == {"y": 2}
    assert ch[1]["returnIdsOnly"] == "true" and ch[1]["geometry"] == "1,2,3,4" and "outFields" not in ch[1]
    assert sum("objectIds" in c for c in ch) == 5          # lotes de 500
    # sabendo de antemão (supportsPagination=false), nem tenta o offset
    buscar, ch = _servidor_sem_paginacao(10)
    feats, _ = arcgis.paginar(buscar, "u", paginacao=False)
    assert len(feats) == 10 and "resultOffset" not in ch[0]
    # área vazia, limite e cancelamento
    assert arcgis.paginar(_servidor_sem_paginacao(0)[0], "u", paginacao=False) == ([], None)
    with pytest.raises(ErroServico, match="acima do limite"):
        arcgis.paginar_por_ids(_servidor_sem_paginacao(50)[0], "u", limite_feicoes=10)
    assert arcgis.paginar_por_ids(_servidor_sem_paginacao(50)[0], "u", cancelado=lambda: True) == ([], None)
    # outro erro do servidor continua sendo erro
    with pytest.raises(ErroServico, match="Invalid URL"):
        arcgis.paginar(lambda u, p: {"error": {"code": 400, "message": "Invalid URL"}}, "u")


def test_wfs_e_paleta():
    assert arcgis.url_wfs("https://h/ows", "BDIA:geol_area", "1,2,3,4") == (
        "https://h/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=BDIA%3Ageol_area"
        "&srsName=EPSG%3A4326&bbox=1%2C2%2C3%2C4%2CEPSG%3A4326&outputFormat=application%2Fjson")
    with pytest.raises(ErroServico, match="ServiceException"):
        arcgis.validar_geojson(b"<ServiceExceptionReport>x</ServiceExceptionReport>")
    with pytest.raises(ErroServico, match="não tem feições"):
        arcgis.validar_geojson(b'{"features": []}')
    assert arcgis.validar_geojson(b'{"features": [1]}')["features"] == [1]
    info = {"drawingInfo": {"renderer": {"field1": "SIGLA", "uniqueValueInfos": [
        {"value": "NP3g", "label": "Granito", "symbol": {"color": [255, 100, 20, 255]}},
        {"value": "x", "symbol": {}}]}}}
    p = arcgis.paleta_do_renderer(info)
    assert p == {"campo": "SIGLA", "cores": {"NP3g": ("#ff6414", "#be2300", "Granito")}}
    assert arcgis.paleta_do_renderer({}) is None and arcgis.paleta_do_renderer(None) is None
    assert arcgis.url_camada("https://h/rest/services/", "/a/MapServer/0") == "https://h/rest/services/a/MapServer/0"


def test_dicionario_cores_sgb():
    def info(campo, itens):
        return {"drawingInfo": {"renderer": {"type": "uniqueValue", "field1": campo, "uniqueValueInfos": [
            {"value": v, "label": l, "symbol": {"color": c}} for v, l, c in itens]}}}
    um = info("ID_UNIDADE_ESTRATIGRAFICA", [
        ("1507", "Q2a - Depósitos aluvionares", [254, 250, 194, 255]),
        ("3604", "NP3gamma - Granito X", [249, 211, 127, 255])])
    dois = info("ID_UNIDADE_ESTRATIGRAFICA", [
        ("1507", "Q2a - Depósitos aluvionares", [254, 250, 194, 255]),
        ("9000", "NP3gamma - Granito Y", [200, 10, 10, 255]),        # mesma sigla, outra cor: ambígua
        ("9001", "sem sigla no rótulo", [1, 2, 3, 255])])
    d = arcgis.dicionario_cores([um, dois, {}, None])
    assert d["por_id"]["1507"] == ("#fefac2", "#bdb981") and set(d["por_id"]) == {"1507", "3604", "9000", "9001"}
    assert d["por_sigla"] == {"Q2a": ("#fefac2", "#bdb981")}       # NP3gamma saiu por ambiguidade
    assert arcgis.dicionario_cores([]) == {"por_id": {}, "por_sigla": {}}
