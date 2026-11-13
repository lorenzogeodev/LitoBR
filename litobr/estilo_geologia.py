"""Simbologia geológica. Rodar na thread principal."""
from pathlib import Path

from qgis.core import (
    QgsCategorizedSymbolRenderer, QgsFillSymbol, QgsLineSymbol, QgsRendererCategory,
    QgsSingleSymbolRenderer, QgsWkbTypes,
)

from .core import classificacao as cl
from .core import estilos as es
from .core.log import registrar
from .core.texto import achar_campo, eh_nulo, normalizar, texto

TAG = "LitoBR"

C_SIGLA = ["sigla", "sigla_unid", "letra_simb", "simbolo"]
C_UNID = ["nome", "nome_unid", "nm_unidade", "legenda"]
C_LITO = ["litotipos", "litotipo1", "nm_lito1", "litologia"]
C_TEMPO = ["nm_tempo_g", "era_max", "eon_max", "sistema_max"]


def _campo_expr(nome):
    return '"' + nome.replace('"', '""') + '"'


def expr_sigla(campo):
    """Expressão de rótulo que troca os marcadores do SGB por letras gregas."""
    c = _campo_expr(campo)
    return f"replace(replace(replace({c}, '_gamma_', 'γ'), '_beta_', 'β'), '_alfa_', 'α')"


def _grego(s):
    return s.replace("_gamma_", "γ").replace("_beta_", "β").replace("_alfa_", "α")


def _preencher(cor, borda, largura, opacidade):
    sem_borda = float(largura) == 0.0
    s = QgsFillSymbol.createSimple({
        "color": cor, "style": "solid",
        "outline_color": borda, "outline_width": str(largura),
        "outline_style": "no" if sem_borda else "solid",
    })
    s.setOpacity(opacidade)
    return s


def _categorias_poligono(camada, campo_chave, cor_de, opacidade, largura):
    """Uma categoria por valor bruto do campo + categoria coringa pros nulos."""
    vistos = {}
    for feat in camada.getFeatures():
        v = feat[campo_chave]
        if eh_nulo(v) or v in vistos:
            continue
        vistos[v] = cor_de(feat, v)  # (legenda, fill, borda)
    cats = [
        QgsRendererCategory(v, _preencher(fill, borda, largura, opacidade), leg)
        for v, (leg, fill, borda) in sorted(vistos.items(), key=lambda kv: str(kv[0]))
    ]
    # valor '' = "todos os outros valores" no renderizador categorizado
    cats.append(QgsRendererCategory("", _preencher(*cl.COR_PADRAO, largura, opacidade), "Sem classificação"))
    return cats if len(cats) > 1 else []


C_ID = ["id_unidade_estratigrafica", "id_unidade", "cod_unidade", "id_unid_es"]


def estilizar_litologia(camada, paleta=None, opacidade=1.0, largura="0.26", dicionario=None):
    """Ordem das cores:

    1. paleta oficial publicada pelo serviço de onde a camada veio (Nuvem);
    2. campos RGB que vierem nos atributos do pacote;
    3. paleta oficial do SGB pelo ID da unidade ou pela sigla (`dicionario`, montado
       com os serviços de litologia do SGB; vale pros pacotes do RIGeo e arquivos);
    4. paleta do plugin por idade e litotipo (heurística).
    Em cada passo, unidade que não tiver cor cai na heurística, uma a uma.
    """
    c = es.campos(camada)
    f_sigla, f_unid = achar_campo(c, C_SIGLA), achar_campo(c, C_UNID)
    f_lito, f_tempo = achar_campo(c, C_LITO), achar_campo(c, C_TEMPO)

    def legenda(feat, v):
        sig = _grego(texto(feat[f_sigla])) if f_sigla else ""
        uni = texto(feat[f_unid]) if f_unid else ""
        lit = texto(feat[f_lito])[:45] if f_lito else ""
        base = " — ".join(p for p in (sig, uni) if p) or str(v)
        return base + (f" ({lit})" if lit else "")

    def heuristica(feat):
        return cl.cor_geologica(
            texto(feat[f_sigla]) if f_sigla else "", texto(feat[f_unid]) if f_unid else "",
            texto(feat[f_lito]) if f_lito else "", texto(feat[f_tempo]) if f_tempo else "")

    cats, campo_chave = [], None
    origem = "heurística"

    # 1) paleta oficial publicada pelo servidor
    if paleta:
        campo_oficial = achar_campo(c, [paleta["campo"]])
        if campo_oficial:
            cores = paleta["cores"]

            def cor_oficial(feat, v):
                achou = cores.get(str(v).strip())
                if achou:
                    return legenda(feat, v), achou[0], achou[1]
                fill, borda = heuristica(feat)
                return legenda(feat, v), fill, borda

            campo_chave = campo_oficial
            cats = _categorias_poligono(camada, campo_chave, cor_oficial, opacidade, largura)
            origem = "paleta oficial do serviço"

    # 2) campos RGB dentro do pacote (shapefiles do RIGeo costumam trazer)
    if not cats:
        f_r, f_g, f_b = (achar_campo(c, x) for x in (["cor_r", "red", "r"], ["cor_g", "green", "g"], ["cor_b", "blue", "b"]))
        chave_rgb = f_sigla or f_unid
        if f_r and f_g and f_b and chave_rgb:
            def cor_rgb(feat, v):
                try:
                    fill = cl.rgb_hex(feat[f_r], feat[f_g], feat[f_b])
                    return legenda(feat, v), fill, cl.escurecer(fill)
                except (TypeError, ValueError):
                    fill, borda = heuristica(feat)
                    return legenda(feat, v), fill, borda

            campo_chave = chave_rgb
            cats = _categorias_poligono(camada, campo_chave, cor_rgb, opacidade, largura)
            origem = "cores RGB do pacote"

    # 3) paleta oficial do SGB, por ID da unidade ou por sigla
    if not cats and dicionario:
        f_id = achar_campo(c, C_ID)
        if f_id and dicionario.get("por_id"):
            tabela, campo_chave, origem = dicionario["por_id"], f_id, "paleta oficial do SGB (ID da unidade)"
        elif f_sigla and dicionario.get("por_sigla"):
            tabela, campo_chave, origem = dicionario["por_sigla"], f_sigla, "paleta oficial do SGB (sigla)"
        else:
            tabela = None
        if tabela:
            acertos = []

            def cor_dic(feat, v):
                achou = tabela.get(str(v).strip())
                acertos.append(bool(achou))
                if achou:
                    return legenda(feat, v), achou[0], achou[1]
                fill, borda = heuristica(feat)
                return legenda(feat, v), fill, borda

            cats = _categorias_poligono(camada, campo_chave, cor_dic, opacidade, largura)
            if not any(acertos):  # nenhuma unidade do pacote existe no banco do SGB
                cats = []
            else:
                registrar(f"{camada.name()}: {sum(acertos)} de {len(acertos)} unidades com a cor oficial do SGB.", TAG)

    # 4) heurística
    if not cats:
        campo_chave = f_sigla or f_unid
        if not campo_chave:
            return False
        cats = _categorias_poligono(
            camada, campo_chave, lambda feat, v: (legenda(feat, v), *heuristica(feat)), opacidade, largura)
        origem = "heurística por idade e litotipo"
        if not cats:
            return False

    camada.setCustomProperty("litobr_origem_das_cores", origem)
    camada.setRenderer(QgsCategorizedSymbolRenderer(campo_chave, cats))
    if f_sigla:
        es.rotulo(camada, expressao=expr_sigla(f_sigla), tamanho=8.5)
    return True


def _pontos_afloramento(camada):
    c = es.campos(camada)
    campo = achar_campo(c, ["tipo_afloramento", "tipo", "tipo_ponto", "subtipo", "descricao"])

    def cfg(v):
        nome, cor, borda, tam = cl.SIMBOLOS_AFLORAMENTO[cl.classe_afloramento(v)]
        return {"name": nome, "color": cor, "outline_color": borda, "size": tam}

    if not campo or not es.categorizar(camada, campo, cfg, rotulo_por_valor=lambda v: f"{v} ({cl.classe_afloramento(v)})"):
        es.simbolo_unico(camada, cfg("lajedo"))
    es.rotulo(camada, achar_campo(c, ["ponto", "cod_ponto", "sigla_ponto"]))


def _pontos_minerais(camada):
    c = es.campos(camada)
    campo = achar_campo(c, ["substancia", "subst_pri", "mineral", "nome_subst", "recurso"])

    def cfg(v):
        nome, cor, borda, tam = cl.SIMBOLOS_SUBSTANCIA[cl.classe_substancia(v)]
        return {"name": nome, "color": cor, "outline_color": borda, "size": tam}

    if not campo or not es.categorizar(camada, campo, cfg, rotulo_por_valor=lambda v: f"{v} [{cl.classe_substancia(v)}]"):
        es.simbolo_unico(camada, cfg(""))
    es.rotulo(camada, achar_campo(c, ["nome", "nome_mina", "localidade"]) or campo)


def _pontos_geossitios(camada):
    c = es.campos(camada)
    campo = achar_campo(c, ["relevancia", "valor_cien"])
    if not campo or not es.categorizar(camada, campo, cl.simbolo_geossitio):
        es.simbolo_unico(camada, {"name": "star", "color": "#ab47bc", "outline_color": "#4a148c", "size": "4.5"})
    es.rotulo(camada, achar_campo(c, ["nome", "geossitio", "sigla"]))


def _pontos_medidas(camada):
    c = es.campos(camada)
    campo = achar_campo(c, ["tipo_est", "tipo_medida", "estrutura"])
    if not campo or not es.categorizar(camada, campo, cl.simbolo_medida_estrutural):
        es.simbolo_unico(camada, {"name": "cross", "color": "#d50000", "size": "3.5"})
    es.rotulo(camada, achar_campo(c, ["mergulho", "dip", "angulo"]))


def _pontos_cavernas(camada):
    es.simbolo_unico(camada, {"name": "triangle", "color": "#4a148c", "outline_color": "#ffffff", "size": "3.5"})
    es.rotulo(camada, achar_campo(es.campos(camada), ["caverna", "nome"]))


_POR_TEMA = {
    "AFLORAMENTOS": _pontos_afloramento, "OCORRENCIAS": _pontos_minerais, "GEOSSIT": _pontos_geossitios,
    "MEDIDAS_EST": _pontos_medidas, "CAVERNAS": _pontos_cavernas, "SIAGAS": es.estilizar_pocos,
}
_POR_NOME = [
    (("aflor",), _pontos_afloramento), (("siagas", "poco"), es.estilizar_pocos),
    (("geossit", "patrimonio"), _pontos_geossitios), (("caverna",), _pontos_cavernas),
    (("medida", "estrutural"), _pontos_medidas),
]


def _estilo_qml_do_pacote(camada, pasta):
    """Aplica um .qml que venha junto no pacote, se o nome bater com o da camada."""
    if not pasta or not Path(pasta).exists():
        return False
    alvo = normalizar(Path(camada.source().split("|")[0]).stem or camada.name())
    for qml in Path(pasta).rglob("*.qml"):
        if normalizar(qml.stem) == alvo:
            _msg, ok = camada.loadNamedStyle(str(qml))
            if ok:
                return True
            registrar(f"Estilo {qml.name} não pôde ser aplicado: {_msg}", TAG, "aviso")
    return False


def estilizar(iface, camada, tema=None, paleta=None, pasta_pacote=None, opacidade=1.0, largura="0.26", dicionario=None):
    """Escolhe o estilo pelo tema (aba Nuvem) ou, sem tema, pelo tipo de geometria e nome da camada."""
    geom = camada.geometryType()
    nome = normalizar(camada.name())
    feito = False

    if geom == QgsWkbTypes.GeometryType.LineGeometry:
        camada.setRenderer(QgsSingleSymbolRenderer(
            QgsLineSymbol.createSimple({"color": "#b71c1c", "width": "0.45", "line_style": "dash"})))
        feito = True
    elif geom == QgsWkbTypes.GeometryType.PointGeometry:
        fn = _POR_TEMA.get(tema) or next((f for chaves, f in _POR_NOME if any(k in nome for k in chaves)), _pontos_minerais)
        fn(camada)
        feito = True
    elif geom == QgsWkbTypes.GeometryType.PolygonGeometry:
        aquifero = tema in ("DOMINIOS_HIDRO", "AQUIFEROS_BR", "AQUIFEROS_SP") or (not tema and ("aquifero" in nome or "hidro" in nome))
        if _estilo_qml_do_pacote(camada, pasta_pacote):
            feito = True  # o estilo que o autor do mapa mandou junto ganha de tudo
        elif paleta and achar_campo(es.campos(camada), [paleta["campo"]]):
            feito = estilizar_litologia(camada, paleta, opacidade, largura)  # paleta oficial do serviço
        elif aquifero:
            es.estilizar_aquiferos(camada, opacidade)
            feito = True
        else:
            feito = estilizar_litologia(camada, paleta, opacidade, largura, dicionario)

    es.atualizar_legenda(iface, camada)
    return feito
