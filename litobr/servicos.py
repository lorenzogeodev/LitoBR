"""Trabalho de rede/disco do LitoBR. Estas funções rodam em thread de fundo:
nada de camada do projeto, canvas ou widget aqui dentro.
"""
import json
import zipfile
from pathlib import Path
from urllib.parse import quote

from . import catalogo as ct
from .core import arcgis, rede
from .core.erros import ErroDados, ErroRede, ErroServico
from .core.log import registrar

TAG = "LitoBR"


def baixar_nuvem(cat, plano, bbox, arq_temp, tarefa):
    """Baixa o tema para um GeoJSON temporário. Retorna {'arquivo', 'paleta'}."""
    if plano["tipo"] == "BDIA_WFS":
        raw = rede.get_bytes(arcgis.url_wfs(cat["bases"]["BDIA_WFS"], plano["caminho"], bbox))
        arcgis.validar_geojson(raw)
        Path(arq_temp).write_bytes(raw)
        return {"arquivo": arq_temp, "paleta": None}

    caminho, escala, ano = plano["caminho"], plano.get("escala"), plano.get("ano")
    if plano.get("estadual"):
        caminho, escala, ano = _camada_estadual(cat, plano)

    url_camada = arcgis.url_camada(cat["bases"]["SGB"], quote(caminho, safe="/"))

    # A descrição da camada diz se ela aceita paginação e traz a paleta oficial.
    info, paleta = {}, None
    try:
        info = rede.get_json(url_camada, {"f": "json"}, timeout_s=30)
        paleta = arcgis.paleta_do_renderer(info)
    except ErroDados as e:
        registrar(f"Sem a descrição da camada ({e}); usando a paleta do plugin.", TAG, "aviso")
    if "error" in info:
        raise ErroServico(f"ArcGIS REST: {(info['error'] or {}).get('message', info['error'])}")
    paginacao = (info.get("advancedQueryCapabilities") or {}).get("supportsPagination") is not False
    teto = info.get("maxRecordCount") or arcgis.TAMANHO_PAGINA

    def progresso(pagina, total):
        tarefa.setProgress(min(95.0, 10.0 + pagina * 8.0))
        registrar(f"{plano['tag']}: {total} feições baixadas...", TAG)

    feats, crs = arcgis.paginar(rede.get_json, url_camada + "/query", bbox,
                                tamanho=min(arcgis.TAMANHO_PAGINA, teto), paginacao=paginacao,
                                cancelado=tarefa.isCanceled, progresso=progresso)
    if tarefa.isCanceled():
        return None
    if not feats:
        raise ErroDados("O serviço não tem feições na área escolhida.")
    with open(arq_temp, "w", encoding="utf-8") as f:
        json.dump(arcgis.feature_collection(feats, crs), f, ensure_ascii=False)
    return {"arquivo": arq_temp, "paleta": paleta, "escala": escala, "ano": ano,
            "url": f"{cat['bases']['SGB']}/{caminho}"}


VALIDADE_PALETA_S = 30 * 24 * 3600


def obter_dicionario_sgb(cat, pasta):
    """Cores oficiais do SGB por unidade (ID e sigla), lidas dos serviços de litologia.

    Fica em cache em `paleta_sgb.json` por 30 dias. Sem rede e sem cache: None
    (os pacotes caem na paleta do plugin).
    """
    import time

    arq = Path(pasta) / "paleta_sgb.json"
    try:
        if arq.exists() and time.time() - arq.stat().st_mtime < VALIDADE_PALETA_S:
            return json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    infos = []
    for caminho in cat.get("paleta_sgb", []):
        url = arcgis.url_camada(cat["bases"]["SGB"], quote(caminho, safe="/"))
        try:
            infos.append(rede.get_json(url, {"f": "json"}, timeout_s=60))
        except ErroDados as e:
            registrar(f"Paleta oficial de {caminho} indisponível: {e}", TAG, "aviso")
    dic = arcgis.dicionario_cores(infos)
    if not dic["por_id"]:
        return None
    try:
        arq.write_text(json.dumps(dic, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        registrar(f"Não gravei o cache da paleta ({e}).", TAG, "aviso")
    return dic


def _camada_estadual(cat, plano):
    """Acha, pelo nome, a camada da UF no serviço estadual. Retorna (caminho, escala, ano)."""
    url = arcgis.url_camada(cat["bases"]["SGB"], quote(cat["estadual_layers"], safe="/")) + "/layers"
    camadas = (rede.get_json(url, {"f": "json"}, timeout_s=30) or {}).get("layers") or []
    achada = ct.escolher_camada_estadual(camadas, plano["nome_uf"])
    if not achada:
        raise ErroServico(f"O serviço estadual do SGB não tem mapa de {plano['nome_uf']}.")
    return f"{cat['estadual_layers']}/{achada['id']}", achada["escala"], achada["ano"]


def baixar_rigeo(cat, url, pasta, arquivo=None):
    """Resolve o item do RIGeo (DSpace 7) e baixa o pacote vetorial.

    Retorna {'caminho', 'titulo', 'escala', 'ano'}; escala e ano vêm do próprio item.
    `arquivo` é o nome do pacote conferido no catálogo (evita baixar o anexo errado).
    """
    url = url.strip()
    if ct.eh_link_direto(url):
        nome = Path(url.split("?")[0]).name or "dados_rigeo.zip"
        return {"caminho": rede.baixar_arquivo(url, Path(pasta) / nome), "titulo": None, "escala": None, "ano": None}
    uuid = ct.uuid_rigeo(url)
    if not uuid:
        raise ErroDados("Link do RIGeo inválido: precisa ser o link do item (com o código UUID) "
                        "ou o link direto do arquivo .zip/.gpkg.")
    api = cat["bases"]["RIGEO_API"]
    try:
        item = rede.get_json(f"{api}/items/{uuid}", timeout_s=30)
    except ErroRede as e:
        if "404" in str(e) or "not found" in str(e).lower():
            raise ErroServico("O RIGeo não encontrou este item. Confira o link.") from e
        raise
    meta = item.get("metadata") or {}
    escala, ano = ct.escala_ano_do_item(meta)
    titulo = ((meta.get("dc.title") or [{}])[0]).get("value")
    bundles = (rede.get_json(f"{api}/items/{uuid}/bundles", timeout_s=30).get("_embedded") or {}).get("bundles") or []
    bundle = ct.escolher_bundle(bundles)
    if not bundle:
        raise ErroServico("Este item do RIGeo não tem arquivos públicos anexados.")
    href = ((bundle.get("_links") or {}).get("bitstreams") or {}).get("href")
    if not href:
        raise ErroServico("O RIGeo não informou onde estão os arquivos deste item.")
    bitstreams = (rede.get_json(href, {"size": 100}, timeout_s=30).get("_embedded") or {}).get("bitstreams") or []
    escolhido = ct.escolher_bitstream(bitstreams, arquivo)
    if not escolhido:
        raise ErroServico("O item do RIGeo não tem arquivo vetorial (.zip, .gpkg ou .shp). "
                          "Baixe manualmente e use a aba Arquivos Locais.")
    nome, link = escolhido
    return {"caminho": rede.baixar_arquivo(link, Path(pasta) / nome), "titulo": titulo, "escala": escala, "ano": ano}


def extrair_pacote(caminho, pasta_saida):
    """Extrai um ZIP e lista os vetores. Retorna (lista de Paths, pasta de origem)."""
    caminho = Path(caminho)
    if caminho.suffix.lower() != ".zip":
        return [caminho], caminho.parent
    destino = Path(pasta_saida) / f"ext_{caminho.stem}"
    destino.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(caminho) as zf:
            zf.extractall(destino)
    except zipfile.BadZipFile:
        raise ErroDados(f"{caminho.name} não é um ZIP válido (download incompleto?).")
    vetores = sorted(list(destino.rglob("*.shp")) + list(destino.rglob("*.gpkg")))
    if not vetores:
        raise ErroDados("Nenhum vetor (.shp/.gpkg) dentro do pacote.")
    return vetores, destino
