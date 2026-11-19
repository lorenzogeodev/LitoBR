"""Visual comum dos plugins: cartões arredondados e botão principal em gel.

Usa a paleta do sistema (palette()) pra funcionar em tema claro e escuro;
só o botão principal tem cor própria.
"""
from qgis.PyQt import sip
from qgis.PyQt.QtWidgets import QFrame, QLabel, QMessageBox, QVBoxLayout

QSS = """
QGroupBox {
    border: 1px solid palette(mid);
    border-radius: 10px;
    margin-top: 14px;
    padding: 10px 8px 8px 8px;
    background: palette(base);
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    font-weight: bold;
}
QTabWidget::pane { border: 1px solid palette(mid); border-radius: 10px; top: -1px; }
QTabBar::tab { padding: 6px 12px; border-top-left-radius: 8px; border-top-right-radius: 8px; }
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox { border-radius: 6px; padding: 3px 6px; }
QPushButton {
    border: 1px solid palette(mid);
    border-radius: 8px;
    padding: 6px 12px;
    background: palette(button);
}
QPushButton:hover { background: palette(light); }
QPushButton:disabled { color: palette(mid); }
QPushButton#avancado { border: none; background: transparent; text-align: left; padding: 4px 6px; font-weight: bold; }
QPushButton#avancado:hover { background: palette(midlight); }
QPushButton#primario {
    color: white;
    font-weight: bold;
    padding: 9px 14px;
    border: 1px solid #0b6b5f;
    border-radius: 12px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #5fe0c8, stop:0.48 #1fb59b, stop:0.52 #12977f, stop:1 #0d7d6a);
}
QPushButton#primario:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7cebd6, stop:0.48 #2cc9ad, stop:0.52 #18a88e, stop:1 #108a75);
}
QPushButton#primario:disabled { background: #9e9e9e; border-color: #757575; }
QLabel#dica { color: palette(window-text); font-size: 9pt; }
QLabel#area { padding: 2px 4px; }
QLabel#status { padding: 6px 10px; border-radius: 8px; font-weight: bold; }
QLabel#status[tipo="ok"] { color: #0b5d4f; background: #d6f5ec; border: 1px solid #5fcbb3; }
QLabel#status[tipo="andando"] { color: #0c4a7a; background: #dcecfb; border: 1px solid #8fbfe8; }
QLabel#status[tipo="erro"] { color: #7a1f12; background: #fbe1dc; border: 1px solid #e59a8c; }
"""


QSS_CABECALHO = """
QFrame#cabecalho {{
    border-radius: 12px;
    border: 1px solid {c2};
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {claro}, stop:0.46 {c1}, stop:0.54 {c2}, stop:1 {c1});
}}
QFrame#cabecalho QLabel {{ background: transparent; color: white; }}
QLabel#tituloCab {{ font-size: 14pt; font-weight: bold; }}
QLabel#subCab {{ font-size: 9pt; }}
"""

# cor de cada plugin: (clara do brilho, base, escura)
ACENTOS = {
    "rocha": ("#f6b48f", "#c2553a", "#8a2f1e"),
    "agua": ("#9bd8fb", "#1c8fd6", "#0c5c9c"),
    "pluma": ("#d9b3f6", "#8e44c9", "#5b2391"),
}


def aplicar_estilo(widget):
    widget.setStyleSheet(QSS)


def cabecalho(titulo, subtitulo, acento):
    """Faixa do topo em gel, na cor do plugin."""
    claro, c1, c2 = ACENTOS[acento]
    quadro = QFrame()
    quadro.setObjectName("cabecalho")
    quadro.setStyleSheet(QSS_CABECALHO.format(claro=claro, c1=c1, c2=c2))
    v = QVBoxLayout(quadro)
    v.setContentsMargins(14, 10, 14, 10)
    v.setSpacing(1)
    t = QLabel(titulo)
    t.setObjectName("tituloCab")
    s = QLabel(subtitulo)
    s.setObjectName("subCab")
    s.setWordWrap(True)
    v.addWidget(t)
    v.addWidget(s)
    return quadro


# Pontos de status: verde = estável, âmbar = legado, azul = atualização contínua, cinza = sem ano.
CORES_STATUS = {
    "estavel": "#22a55b",
    "legado": "#e3a21a",
    "continuo": "#2f7fd6",
    "desconhecido": "#9aa5ae",
}
_ICONES = {}


def icone_status(status, tamanho=14):
    """Bolinha com brilho em cima (gel), desenhada no Qt: não depende de emoji."""
    chave = (status, tamanho)
    if chave not in _ICONES:
        from qgis.PyQt.QtCore import QPointF, Qt
        from qgis.PyQt.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap, QRadialGradient

        cor = QColor(CORES_STATUS.get(status, CORES_STATUS["desconhecido"]))
        pm = QPixmap(tamanho, tamanho)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = tamanho / 2.0
        grad = QRadialGradient(QPointF(r * 0.75, r * 0.6), r * 1.1)
        grad.setColorAt(0.0, cor.lighter(150))
        grad.setColorAt(1.0, cor.darker(115))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(cor.darker(140), 1))
        p.drawEllipse(QPointF(r, r), r - 1.5, r - 1.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 150))
        p.drawEllipse(QPointF(r * 0.8, r * 0.62), r * 0.38, r * 0.24)
        p.end()
        _ICONES[chave] = QIcon(pm)
    return _ICONES[chave]


def legenda_status(textos):
    """Rótulo em texto rico com as bolinhas e o que cada cor quer dizer."""
    partes = [f'<span style="white-space:nowrap;"><span style="color:{CORES_STATUS[s]}; font-size:13pt;">●</span>&nbsp;'
              f'{textos[s].replace(" ", "&nbsp;")}</span>'
              for s in ("estavel", "legado", "continuo", "desconhecido") if s in textos]
    lb = QLabel("&nbsp;&nbsp;&nbsp; ".join(partes))
    lb.setObjectName("dica")
    lb.setWordWrap(True)
    return lb


def vivo(widget):
    """False se o objeto C++ do widget já foi destruído (diálogo fechado)."""
    return widget is not None and not sip.isdeleted(widget)


def avisar(parent, titulo, msg):
    QMessageBox.warning(parent if vivo(parent) else None, titulo, msg)


def informar(parent, titulo, msg):
    QMessageBox.information(parent if vivo(parent) else None, titulo, msg)
