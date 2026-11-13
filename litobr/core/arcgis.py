"""Consultas ArcGIS REST e WFS (puro: recebe a função de rede por injeção).

`buscar_json(url, params) -> dict` é injetada. No plugin é a `rede.get_json`;
nos testes é um dublê. Assim a paginação é testada sem internet.
"""
import json
from urllib.parse import urlencode

from .erros import ErroServico

TAMANHO_PAGINA = 1000
LIMITE_PAGINAS = 500


def params_query(bbox=None, offset=0, tamanho=TAMANHO_PAGINA):
    p = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
        "resultOffset": offset,
        "resultRecordCount": tamanho,
    }
    if bbox:
        p.update({
            "geometry": bbox,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        })
    return p


def _id(feat):
    return feat.get("id", (feat.get("properties") or {}).get("OBJECTID"))


LOTE_IDS = 500  # ids por requisição: mantém a URL abaixo de ~6 KB
LIMITE_FEICOES = 300000


def _erro_do_servidor(data):
    err = data["error"]
    msg = err.get("message", err) if isinstance(err, dict) else err
    detalhes = err.get("details") if isinstance(err, dict) else None
    if detalhes:
        msg = f"{msg} ({'; '.join(str(d) for d in detalhes)})"
    return ErroServico(f"ArcGIS REST: {msg}")


def _sem_paginacao(erro):
    return "pagination" in str(erro).lower()


def params_ids(bbox=None):
    p = params_query(bbox)
    for k in ("outFields", "returnGeometry", "outSR", "resultOffset", "resultRecordCount"):
        p.pop(k, None)
    p.update({"returnIdsOnly": "true", "f": "json"})
    return p


def paginar_por_ids(buscar_json, url_query, bbox=None, tamanho=LOTE_IDS,
                    cancelado=lambda: False, progresso=None, limite_feicoes=LIMITE_FEICOES):
    """Para camadas sem suporte a resultOffset (supportsPagination = false).

    Pede só os ObjectIDs da área (o servidor devolve todos, sem limite de página)
    e depois busca as feições em lotes com `objectIds=`.
    """
    data = buscar_json(url_query, params_ids(bbox))
    if not isinstance(data, dict):
        raise ErroServico("Resposta inesperada do ArcGIS REST ao listar os ObjectIDs.")
    if "error" in data:
        raise _erro_do_servidor(data)
    ids = sorted(data.get("objectIds") or [])
    if len(ids) > limite_feicoes:
        raise ErroServico(f"A área tem {len(ids)} feições, acima do limite de {limite_feicoes}. Reduza a área.")
    feats, crs = [], None
    for pagina, i in enumerate(range(0, len(ids), tamanho)):
        if cancelado():
            break
        lote = ids[i:i + tamanho]
        p = {"objectIds": ",".join(str(x) for x in lote), "outFields": "*",
             "returnGeometry": "true", "outSR": "4326", "f": "geojson"}
        res = buscar_json(url_query, p)
        if not isinstance(res, dict):
            raise ErroServico("Resposta inesperada do ArcGIS REST.")
        if "error" in res:
            raise _erro_do_servidor(res)
        feats.extend(res.get("features") or [])
        crs = crs or res.get("crs")
        if progresso:
            progresso(pagina, len(feats))
    return feats, crs


def paginar(buscar_json, url_query, bbox=None, tamanho=TAMANHO_PAGINA,
            cancelado=lambda: False, progresso=None, limite_paginas=LIMITE_PAGINAS, paginacao=True):
    """Baixa todas as feições de uma camada ArcGIS REST. Retorna (features, crs).

    `paginacao=False` (camada com supportsPagination = false) vai direto pela lista
    de ObjectIDs. Se o servidor recusar o offset com "Pagination is not supported",
    a troca é automática.
    """
    if not paginacao:
        return paginar_por_ids(buscar_json, url_query, bbox, cancelado=cancelado, progresso=progresso)
    try:
        return _paginar_offset(buscar_json, url_query, bbox, tamanho, cancelado, progresso, limite_paginas)
    except ErroServico as e:
        if not _sem_paginacao(e):
            raise
        return paginar_por_ids(buscar_json, url_query, bbox, cancelado=cancelado, progresso=progresso)


def _paginar_offset(buscar_json, url_query, bbox, tamanho, cancelado, progresso, limite_paginas):
    feats, crs, offset, ultimo_primeiro = [], None, 0, object()
    for pagina in range(limite_paginas):
        if cancelado():
            break
        data = buscar_json(url_query, params_query(bbox, offset, tamanho))
        if not isinstance(data, dict):
            raise ErroServico("Resposta inesperada do ArcGIS REST.")
        if "error" in data:
            raise _erro_do_servidor(data)
        lote = data.get("features") or []
        crs = crs or data.get("crs")
        if not lote:
            break
        primeiro = _id(lote[0])
        if primeiro is not None and primeiro == ultimo_primeiro:
            break  # servidor sem suporte a resultOffset: devolveu a mesma página
        ultimo_primeiro = primeiro
        feats.extend(lote)
        if progresso:
            progresso(pagina, len(feats))
        if data.get("exceededTransferLimit") or len(lote) >= tamanho:
            offset += len(lote)
        else:
            break
    return feats, crs


def feature_collection(features, crs=None):
    fc = {"type": "FeatureCollection", "features": features}
    if crs:
        fc["crs"] = crs
    return fc


def url_wfs(base, typename, bbox, versao="1.0.0"):
    q = {
        "service": "WFS", "version": versao, "request": "GetFeature",
        "typeName": typename, "srsName": "EPSG:4326",
        "bbox": f"{bbox},EPSG:4326", "outputFormat": "application/json",
    }
    return f"{base}?{urlencode(q)}"


def validar_geojson(raw):
    """Bytes de um WFS -> dict. ErroServico com trecho da resposta se vier XML de erro."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        trecho = raw[:200].decode("utf-8", errors="ignore").strip()
        raise ErroServico(f"O WFS não devolveu GeoJSON (provável ServiceException): {trecho}")
    if not data.get("features"):
        raise ErroServico("O serviço não tem feições na área escolhida.")
    return data


def url_camada(base_rest, caminho):
    """'.../rest/services' + 'pasta/Serv/MapServer/0' sem barra dupla."""
    return f"{base_rest.rstrip('/')}/{caminho.strip('/')}"


def dicionario_cores(infos_camadas):
    """Junta as paletas oficiais de vários serviços num dicionário só.

    Nos serviços de litologia do SGB o renderer é por ID_UNIDADE_ESTRATIGRAFICA e o
    rótulo começa pela sigla ('Q2a - Depósitos aluvionares'). Retorna
    {'por_id': {id: (fill, borda)}, 'por_sigla': {sigla: (fill, borda)}}.
    Sigla que aparece com cores diferentes em serviços diferentes fica de fora
    (é ambígua e poderia pintar errado).
    """
    por_id, siglas = {}, {}
    for info in infos_camadas or []:
        pal = paleta_do_renderer(info)
        if not pal:
            continue
        for valor, (fill, borda, rotulo) in pal["cores"].items():
            por_id.setdefault(valor, (fill, borda))
            sigla = str(rotulo).split(" - ")[0].strip() if " - " in str(rotulo) else ""
            if sigla:
                siglas.setdefault(sigla, set()).add((fill, borda))
    por_sigla = {s: next(iter(c)) for s, c in siglas.items() if len(c) == 1}
    return {"por_id": por_id, "por_sigla": por_sigla}


def paleta_do_renderer(info_camada):
    """Lê drawingInfo de `.../MapServer/N?f=json` e devolve {'campo': str, 'cores': {valor: (fill, borda, rotulo)}}.

    Na v3.8.1 isso era pedido em `/query?f=json`, que não traz drawingInfo,
    então a paleta oficial nunca chegava.
    """
    rend = ((info_camada or {}).get("drawingInfo") or {}).get("renderer") or {}
    campo = rend.get("field1")
    cores = {}
    for item in rend.get("uniqueValueInfos") or []:
        val = str(item.get("value", "")).strip()
        cor = (item.get("symbol") or {}).get("color") or []
        if val and len(cor) >= 3:
            fill = "#{:02x}{:02x}{:02x}".format(*[int(c) for c in cor[:3]])
            borda = "#{:02x}{:02x}{:02x}".format(*[max(0, int(c) - 65) for c in cor[:3]])
            cores[val] = (fill, borda, str(item.get("label") or val))
    return {"campo": campo, "cores": cores} if campo and cores else None
