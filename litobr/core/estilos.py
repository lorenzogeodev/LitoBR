"""Simbologia comum. Rodar na thread principal."""
from qgis.core import (
    QgsCategorizedSymbolRenderer, QgsFillSymbol, QgsMarkerSymbol, QgsPalLayerSettings,
    QgsRendererCategory, QgsSingleSymbolRenderer, QgsTextBufferSettings, QgsTextFormat,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor, QFont

from . import classificacao as cl
from .texto import achar_campo, eh_nulo


def campos(camada):
    return [f.name() for f in camada.fields()]


def valores_unicos(camada, campo):
    idx = camada.fields().indexFromName(campo)
    if idx < 0:
        return []
    vals = [v for v in camada.dataProvider().uniqueValues(idx) if not eh_nulo(v)]
    return sorted(vals, key=lambda v: str(v))


def rotulo(camada, campo=None, expressao=None, cor="#1a1a1a", buffer="#ffffff", tamanho=8.0, em_linha=False):
    """Rótulo por campo (aspas duplas = campo) ou por expressão.

    A v3.8.1 montava replace('SIGLA', ...) com aspas simples, que no QGIS é
    texto literal: todo polígono aparecia escrito "SIGLA".
    """
    if not campo and not expressao:
        return
    ls = QgsPalLayerSettings()
    if expressao:
        ls.fieldName = expressao
        ls.isExpression = True
    else:
        ls.fieldName = campo
        ls.isExpression = False
    tf = QgsTextFormat()
    tf.setFont(QFont("Sans Serif", 8, QFont.Weight.Bold))
    tf.setSize(tamanho)
    tf.setColor(QColor(cor))
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.8)
    buf.setColor(QColor(buffer))
    tf.setBuffer(buf)
    ls.setFormat(tf)
    if em_linha:
        ls.placement = QgsPalLayerSettings.Line
    camada.setLabeling(QgsVectorLayerSimpleLabeling(ls))
    camada.setLabelsEnabled(True)


def simbolo_unico(camada, cfg, tipo="marker", opacidade=1.0):
    s = (QgsMarkerSymbol if tipo == "marker" else QgsFillSymbol).createSimple(cfg)
    s.setOpacity(opacidade)
    camada.setRenderer(QgsSingleSymbolRenderer(s))


def categorizar(camada, campo, cfg_por_valor, tipo="marker", rotulo_por_valor=None, opacidade=1.0):
    """cfg_por_valor(valor) -> dict do createSimple."""
    fabrica = QgsMarkerSymbol if tipo == "marker" else QgsFillSymbol
    cats = []
    for v in valores_unicos(camada, campo):
        s = fabrica.createSimple(cfg_por_valor(v))
        s.setOpacity(opacidade)
        cats.append(QgsRendererCategory(v, s, rotulo_por_valor(v) if rotulo_por_valor else str(v)))
    if cats:
        camada.setRenderer(QgsCategorizedSymbolRenderer(campo, cats))
    return bool(cats)


def estilizar_aquiferos(camada, opacidade=0.65):
    c = campos(camada)
    campo = achar_campo(c, ["tipo_domin", "dominio", "sistema", "tipo_aquif", "litologia"])

    def cfg(v):
        fill, borda = cl.CORES_AQUIFERO[cl.classe_aquifero(v)]
        return {"color": fill, "outline_color": borda, "outline_width": "0.3", "style": "solid"}

    if not campo or not categorizar(camada, campo, cfg, "fill", opacidade=opacidade):
        simbolo_unico(camada, {"color": "#80deea", "outline_color": "#00838f", "outline_width": "0.3"}, "fill", opacidade)
    rotulo(camada, achar_campo(c, ["sigla_aq", "sistema_aq", "nome_aq", "nome_unida"]), cor="#004d40", buffer="#e0f2f1")


def estilizar_pocos(camada):
    c = campos(camada)
    campo = achar_campo(c, ["tipo_poco", "tipo_pt", "natureza"])
    if not campo or not categorizar(camada, campo, lambda v: cl.SIMBOLOS_POCO[cl.classe_poco(v)]):
        simbolo_unico(camada, {"name": "circle", "color": "#29b6f6", "outline_color": "#01579b", "size": "2.8"})
    rotulo(camada, achar_campo(c, ["q_total", "vazao", "vazao_est", "q_outorgada"]), cor="#01579b")


def atualizar_legenda(iface, camada):
    camada.triggerRepaint()
    if iface is not None and hasattr(iface, "layerTreeView"):
        iface.layerTreeView().refreshLayerSymbology(camada.id())
