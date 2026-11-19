"""Janela do LitoBR (não modal: o QGIS continua usável durante o download)."""
import time
from pathlib import Path

from qgis import processing
from qgis.core import (
    Qgis, QgsMapLayerProxyModel, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsWkbTypes,
)
from qgis.gui import QgsFileWidget, QgsMapLayerComboBox
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem,
    QProgressBar, QPushButton, QRadioButton, QSlider, QTabWidget, QVBoxLayout, QWidget,
)

from . import catalogo as ct
from . import estilo_geologia, servicos
from .core import abnt, geo, ui
from .core.classificacao import uf_por_ponto
from .core.erros import ErroDados
from .core.log import registrar
from .core.tarefa import GerenciadorTarefas, TarefaFundo

TAG = "LitoBR"
VERSAO = "1.0.2"
ORIGEM = f"LitoBR v{VERSAO}"
PASTA = "QGIS_LitoBR_Data"
BORDAS = [("Borda 0,26 mm", "0.26"), ("Borda fina 0,08 mm", "0.08"), ("Sem borda", "0.0")]
AUTORES = {"SGB": ("Serviço Geológico do Brasil (SGB/CPRM)", "SGB/CPRM", "Brasília"),
           "IBGE": ("Instituto Brasileiro de Geografia e Estatística (IBGE)", "IBGE", "Rio de Janeiro")}


ROLE_TEXTO = Qt.ItemDataRole.UserRole + 7  # texto original do item, sem a ★


def _combo_camadas():
    cb = QComboBox()
    cb.addItem("Escolher depois de baixar (a litologia vem marcada)", "escolher")
    cb.addItem("Só a litologia (camada principal)", "principal")
    cb.addItem("Todas as camadas, num grupo", "todas")
    return cb


def _dialogo_camadas(pai, camadas, principal):
    """Lista com caixinhas pra escolher o que entra no projeto. Retorna a lista ou None."""
    nomes_geom = {QgsWkbTypes.GeometryType.PolygonGeometry: "polígonos", QgsWkbTypes.GeometryType.LineGeometry: "linhas",
                  QgsWkbTypes.GeometryType.PointGeometry: "pontos"}
    d = QDialog(pai)
    d.setWindowTitle("LitoBR: camadas do pacote")
    d.setMinimumSize(520, 420)
    v = QVBoxLayout(d)
    lb = QLabel("Marque o que vai para o projeto. O recorte e o estilo valem para todas as marcadas.")
    lb.setWordWrap(True)
    v.addWidget(lb)
    lista = QListWidget()
    for lyr in camadas:
        it = QListWidgetItem(f"{lyr.name()}  ·  {nomes_geom.get(lyr.geometryType(), 'outro')}, {lyr.featureCount()} feições")
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        it.setCheckState(Qt.CheckState.Checked if lyr is principal else Qt.CheckState.Unchecked)
        lista.addItem(it)
    v.addWidget(lista)
    hb = QHBoxLayout()
    b_todas, b_nenhuma = QPushButton("Marcar todas"), QPushButton("Só a litologia")
    b_todas.clicked.connect(lambda: [lista.item(i).setCheckState(Qt.CheckState.Checked) for i in range(lista.count())])
    b_nenhuma.clicked.connect(lambda: [lista.item(i).setCheckState(Qt.CheckState.Checked if camadas[i] is principal else Qt.CheckState.Unchecked)
                                       for i in range(lista.count())])
    hb.addWidget(b_todas)
    hb.addWidget(b_nenhuma)
    hb.addStretch()
    v.addLayout(hb)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    bb.button(QDialogButtonBox.StandardButton.Ok).setText("Carregar")
    bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    v.addWidget(bb)
    if d.exec() != QDialog.DialogCode.Accepted:
        return None
    return [camadas[i] for i in range(lista.count()) if lista.item(i).checkState() == Qt.CheckState.Checked]


def nome_produto(titulo, escala, ano, ano_rotulo=None):
    """Nome da camada no projeto: 'Litologia, Acre (1:750.000, 2026)'."""
    partes = [p for p in (escala, ct.texto_ano(ano, ano_rotulo) if (ano or ano_rotulo) else None) if p]
    return f"{titulo} ({', '.join(partes)})" if partes else titulo


def detalhes_produto(escala, ano, ano_rotulo=None):
    """O que vai no metadado da camada, além da referência."""
    return {
        "escala": ct.texto_escala(escala),
        "ano_de_publicacao": ct.texto_ano(ano, ano_rotulo),
        "data_de_acesso": abnt.data_acesso(),
    }


class LitoBRDialog(QDialog):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.cat = ct.carregar()
        self.tarefas = GerenciadorTarefas()
        self.setWindowTitle(f"LitoBR v{VERSAO}")
        self.setMinimumWidth(620)
        ui.aplicar_estilo(self)
        self._montar()

    # ------------------------------------------------------------------ UI
    def _montar(self):
        layout = QVBoxLayout(self)
        layout.addWidget(ui.cabecalho(
            "LitoBR", "Mapa geológico recortado, estilizado e com citação ABNT em poucos cliques (SGB/CPRM e IBGE)", "rocha"))
        self.lb_area = QLabel("")
        self.lb_area.setObjectName("area")
        self.lb_area.setWordWrap(True)
        layout.addWidget(self.lb_area)
        self.tabs = QTabWidget()

        # Aba 1: nuvem
        t1, l1 = QWidget(), QVBoxLayout()
        corte = self.cat.get("ano_corte_estavel", 2014)
        self.cb_escala = QComboBox()
        for e in self.cat["escalas"]:
            st = ct.status_produto(e.get("ano"), e.get("ano_rotulo"), corte)
            self.cb_escala.addItem(ui.icone_status(st), f"{e['rotulo']}  ·  {ct.texto_ano(e.get('ano'), e.get('ano_rotulo'))}")
        self.cb_tema = QComboBox()
        for t in self.cat["temas"]:
            e = self.cat["endpoints_temas"].get(t["chave"])
            if e is None:  # litologia: escala e ano vêm do combo de escala
                self.cb_tema.addItem(ui.icone_status("desconhecido"), f"{t['rotulo']}  ·  escala e ano na opção abaixo")
                continue
            st = ct.status_produto(e.get("ano"), e.get("ano_rotulo"), corte)
            self.cb_tema.addItem(ui.icone_status(st),
                                 f"{t['rotulo']}  ·  {ct.resumo_produto(e.get('escala'), e.get('ano'), e.get('ano_rotulo'))}")
        l1.addWidget(QLabel("Tema:"))
        l1.addWidget(self.cb_tema)
        self.lb_escala = QLabel("Escala da litologia:")
        l1.addWidget(self.lb_escala)
        l1.addWidget(self.cb_escala)
        dica = QLabel("A escala só vale para o tema de litologia; os outros temas têm serviço próprio.")
        dica.setObjectName("dica")
        dica.setWordWrap(True)
        l1.addWidget(dica)
        l1.addWidget(ui.legenda_status(self.cat["legenda_status"]))
        l1.addStretch()
        t1.setLayout(l1)
        self.cb_tema.currentIndexChanged.connect(self._ajustar_escala)
        self.cb_escala.currentIndexChanged.connect(self._sincronizar_tema)
        self._sincronizar_tema()
        self.tabs.addTab(t1, "Temas da área")

        # Aba 2: RIGeo
        t2, l2 = QWidget(), QVBoxLayout()
        self.cb_uf = QComboBox()
        self.cb_uf.setMaxVisibleItems(20)
        corte = self.cat.get("ano_corte_estavel", 2014)
        for uf, d in sorted(self.cat["estados"].items()):
            st = ct.status_produto(d.get("ano"), None, corte)
            if not d.get("arquivo"):
                self.cb_uf.addItem(ui.icone_status(st), f"{uf} — {d['nome']}  ·  sem pacote SIG no RIGeo", None)
                self.cb_uf.model().item(self.cb_uf.count() - 1).setEnabled(False)
                continue
            self.cb_uf.addItem(ui.icone_status(st), f"{uf} — {d['nome']}  ·  {ct.resumo_produto(d.get('escala'), d.get('ano'))}",
                               dict(d, produto=f"{uf} {d['nome']}", chave=uf))
        self.cb_uf.insertSeparator(self.cb_uf.count())
        for d in sorted(self.cat["projetos_regionais"].values(), key=lambda x: x["nome"]):
            st = ct.status_produto(d.get("ano"), None, corte)
            chave = next(k for k, v in self.cat["projetos_regionais"].items() if v is d)
            self.cb_uf.addItem(ui.icone_status(st), f"{d['nome']} ({d['uf']})  ·  {ct.resumo_produto(d.get('escala'), d.get('ano'))}",
                               dict(d, produto=d["nome"], chave=chave))
        for i in range(self.cb_uf.count()):
            self.cb_uf.setItemData(i, self.cb_uf.itemText(i), ROLE_TEXTO)
        l2.addWidget(QLabel("Mapa estadual ou província mineral (pacotes do RIGeo/SGB):"))
        l2.addWidget(self.cb_uf)
        hr = QHBoxLayout()
        self.lb_recom = QLabel("")
        self.lb_recom.setWordWrap(True)
        hr.addWidget(self.lb_recom, 1)
        self.btn_recom = QPushButton("Usar o mais detalhado")
        self.btn_recom.setVisible(False)
        self.btn_recom.clicked.connect(self._usar_recomendacao)
        hr.addWidget(self.btn_recom)
        l2.addLayout(hr)
        l2.addWidget(ui.legenda_status({k: v for k, v in self.cat["legenda_status"].items() if k != "continuo"}))
        self.chk_link = QCheckBox("Usar outro link do RIGeo (avançado)")
        l2.addWidget(self.chk_link)
        self.txt_url = QLineEdit()
        self.txt_url.setPlaceholderText("https://rigeo.sgb.gov.br/items/...")
        self.txt_url.setVisible(False)
        l2.addWidget(self.txt_url)
        self.chk_link.toggled.connect(self._alternar_link)
        self.cb_uf.currentIndexChanged.connect(self._atualizar_url)
        self.cb_uf.currentIndexChanged.connect(lambda _i: self._mostrar_botao_recom())
        self._atualizar_url()
        self.cb_camadas = _combo_camadas()
        hc = QHBoxLayout()
        hc.addWidget(QLabel("Camadas do pacote:"))
        hc.addWidget(self.cb_camadas, 1)
        l2.addLayout(hc)
        l2.addStretch()
        t2.setLayout(l2)
        self.tabs.addTab(t2, "Mapas estaduais e províncias")

        # Aba 3: local
        t3, l3 = QWidget(), QVBoxLayout()
        self.file_w = QgsFileWidget()
        self.file_w.setFilter("Pacotes e vetores (*.zip *.shp *.gpkg)")
        l3.addWidget(QLabel("Pacote geológico ou vetor já baixado:"))
        l3.addWidget(self.file_w)
        self.cb_camadas_loc = _combo_camadas()
        hc3 = QHBoxLayout()
        hc3.addWidget(QLabel("Camadas do pacote:"))
        hc3.addWidget(self.cb_camadas_loc, 1)
        l3.addLayout(hc3)
        l3.addStretch()
        t3.setLayout(l3)
        self.tabs.addTab(t3, "Meu arquivo")
        layout.addWidget(self.tabs)

        # Cartografia
        g_cart = QGroupBox("Cartografia")
        lc = QHBoxLayout()
        self.sld_op = QSlider(Qt.Orientation.Horizontal)
        self.sld_op.setRange(20, 100)
        self.sld_op.setValue(100)
        self.lb_op = QLabel("100%")
        self.sld_op.valueChanged.connect(lambda v: self.lb_op.setText(f"{v}%"))
        lc.addWidget(QLabel("Opacidade dos polígonos:"))
        lc.addWidget(self.sld_op)
        lc.addWidget(self.lb_op)
        self.cb_borda = QComboBox()
        self.cb_borda.addItems([b[0] for b in BORDAS])
        self.cb_borda.setMinimumWidth(190)
        lc.addWidget(self.cb_borda)
        g_cart.setLayout(lc)
        layout.addWidget(g_cart)

        # Área: o essencial à vista, o resto em "Opções avançadas"
        g_out = QGroupBox("Área")
        lo = QVBoxLayout()
        self.rb_canvas = QRadioButton("Recortar pela tela do mapa (recomendado)")
        self.rb_tudo = QRadioButton("Sem recorte: baixar tudo o que toca a tela ou o pacote inteiro")
        self.rb_mask = QRadioButton("Recortar por uma camada de polígono (máscara):")
        self.rb_canvas.setChecked(True)
        self.grupo_area = QButtonGroup(self)
        for rb in (self.rb_canvas, self.rb_tudo, self.rb_mask):
            self.grupo_area.addButton(rb)
            rb.toggled.connect(lambda _on: self._atualizar_area())
        lo.addWidget(self.rb_canvas)
        lo.addWidget(self.rb_tudo)
        g_out.setLayout(lo)
        layout.addWidget(g_out)

        self.btn_avancado = QPushButton("▸ Opções avançadas")
        self.btn_avancado.setObjectName("avancado")
        self.btn_avancado.setCheckable(True)
        self.btn_avancado.toggled.connect(self._alternar_avancado)
        layout.addWidget(self.btn_avancado)
        self.g_avancado = QGroupBox("Opções avançadas")
        la = QVBoxLayout()
        h = QHBoxLayout()
        h.addWidget(QLabel("Salvar como:"))
        self.cb_fmt = QComboBox()
        self.cb_fmt.addItems([f[0] for f in geo.FORMATOS])
        self.cb_fmt.setCurrentIndex(1)
        h.addWidget(self.cb_fmt, 1)
        self.chk_reproj = QCheckBox("Reprojetar para o SRC do projeto")
        self.chk_reproj.setChecked(True)
        h.addWidget(self.chk_reproj)
        la.addLayout(h)
        hm = QHBoxLayout()
        hm.addWidget(self.rb_mask)
        self.cb_mask = QgsMapLayerComboBox()
        self.cb_mask.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        self.cb_mask.setEnabled(False)
        self.rb_mask.toggled.connect(self.cb_mask.setEnabled)
        hm.addWidget(self.cb_mask, 1)
        la.addLayout(hm)
        hr2 = QHBoxLayout()
        self.chk_raster = QCheckBox("Recortar também a imagem (raster):")
        self.chk_raster.setEnabled(False)
        self.rb_mask.toggled.connect(self.chk_raster.setEnabled)
        hr2.addWidget(self.chk_raster)
        self.cb_raster = QgsMapLayerComboBox()
        self.cb_raster.setFilters(QgsMapLayerProxyModel.Filter.RasterLayer)
        self.cb_raster.setEnabled(False)
        self.chk_raster.toggled.connect(self.cb_raster.setEnabled)
        self.rb_mask.toggled.connect(lambda on: self.cb_raster.setEnabled(on and self.chk_raster.isChecked()))
        hr2.addWidget(self.cb_raster, 1)
        la.addLayout(hr2)
        self.g_avancado.setLayout(la)
        self.g_avancado.setVisible(False)
        layout.addWidget(self.g_avancado)

        self.lb_status = QLabel("")
        self.lb_status.setObjectName("status")
        self.lb_status.setWordWrap(True)
        self.lb_status.setVisible(False)
        layout.addWidget(self.lb_status)

        self.barra = QProgressBar()
        self.barra.setRange(0, 0)
        self.barra.setVisible(False)
        layout.addWidget(self.barra)

        hb = QHBoxLayout()
        self.btn_exec = QPushButton("Baixar e estilizar")
        self.btn_exec.setObjectName("primario")
        self.btn_exec.clicked.connect(self.executar)
        hb.addWidget(self.btn_exec, 1)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.tarefas.cancelar_todas)
        hb.addWidget(self.btn_cancel)
        layout.addLayout(hb)
        self._ajustar_escala()
        # a linha de área e a recomendação acompanham a tela
        self.iface.mapCanvas().extentsChanged.connect(self._tela_mudou)
        self.tabs.currentChanged.connect(lambda _i: self._tela_mudou())
        self._tela_mudou()

    def desligar(self):
        """Solta o sinal do mapa (chamado quando o plugin é descarregado)."""
        try:
            self.iface.mapCanvas().extentsChanged.disconnect(self._tela_mudou)
        except (TypeError, RuntimeError):
            pass

    def _bbox_tela(self):
        canvas = self.iface.mapCanvas()
        ext84, _txt = geo.extensao_wgs84(canvas.extent(), canvas.mapSettings().destinationCrs())
        return (ext84.xMinimum(), ext84.yMinimum(), ext84.xMaximum(), ext84.yMaximum()), ext84.center()

    def _tela_mudou(self):
        if not ui.vivo(self):
            return
        self._atualizar_area()
        self._atualizar_recomendacao()

    def _atualizar_area(self):
        """Diz, em cima, qual área vai ser baixada (o leigo precisa saber que é a tela)."""
        if not ui.vivo(self) or not hasattr(self, "rb_mask"):
            return
        if self.rb_mask.isChecked():
            self.lb_area.setText("<b>Área:</b> a camada de polígono escolhida nas opções avançadas.")
            return
        try:
            bbox, centro = self._bbox_tela()
        except ErroDados:
            self.lb_area.setText("<b>Área:</b> aproxime o mapa de uma região do Brasil antes de baixar.")
            return
        ufs = ", ".join(ct.ufs_na_area(bbox, self.cat["ufs_bbox"])) \
            or uf_por_ponto(centro.x(), centro.y(), self.cat["ufs_bbox"])
        if not ufs:
            self.lb_area.setText("<b>Área:</b> a tela do mapa está fora do Brasil. Aproxime de uma região do país.")
            return
        self.lb_area.setText(f"<b>Área:</b> a tela atual do mapa ({ufs}). Para mudar, dê zoom ou arraste o mapa.")

    def _sincronizar_tema(self):
        """A litologia mostra a bolinha da escala escolhida (antes ficava cinza, parecendo dado sem ano)."""
        icone = self.cb_escala.itemIcon(self.cb_escala.currentIndex())
        for i, tema in enumerate(self.cat["temas"]):
            if tema["chave"] not in self.cat["endpoints_temas"]:
                self.cb_tema.setItemIcon(i, icone)

    def _alternar_avancado(self, on):
        self.g_avancado.setVisible(on)
        self.btn_avancado.setText(("▾ " if on else "▸ ") + "Opções avançadas")
        if not on and self.rb_mask.isChecked():
            self.rb_canvas.setChecked(True)  # máscara escondida não pode ficar valendo
        self.adjustSize()

    def _mostrar_botao_recom(self):
        """O botão só aparece quando existe um mapa mais detalhado que o já escolhido."""
        rec = getattr(self, "_recomendados", None)
        atual = self.cb_uf.currentData()
        chave = atual.get("chave") if isinstance(atual, dict) else None
        self.btn_recom.setVisible(bool(rec) and (self.chk_link.isChecked() or rec[0]["chave"] != chave))

    def _atualizar_recomendacao(self):
        """Marca com ★ os produtos do RIGeo que cobrem a tela e sugere o mais detalhado."""
        if not ui.vivo(self) or self.tabs.currentIndex() != 1:
            return
        try:
            bbox, centro = self._bbox_tela()
        except ErroDados:
            self.lb_recom.setText("Aproxime o mapa do Brasil para ver o que cobre a sua área.")
            self._recomendados = []
            self.btn_recom.setVisible(False)
            return
        uf = uf_por_ponto(centro.x(), centro.y(), self.cat["ufs_bbox"])
        self._recomendados = ct.recomendar(self.cat, bbox, uf)
        chaves = {r["chave"] for r in self._recomendados}
        for i in range(self.cb_uf.count()):
            base = self.cb_uf.itemData(i, ROLE_TEXTO)
            d = self.cb_uf.itemData(i)
            if base:
                marca = "★ " if isinstance(d, dict) and d.get("chave") in chaves else ""
                self.cb_uf.setItemText(i, marca + base)
        if not self._recomendados:
            self.lb_recom.setText("Nenhum mapa do catálogo cobre a área da tela.")
            self.btn_recom.setVisible(False)
            return
        r = self._recomendados[0]["item"]
        ufs = ", ".join(ct.ufs_na_area(bbox, self.cat["ufs_bbox"])) or uf or "fora do Brasil"
        self.lb_recom.setText(
            f"★ = cobre a sua área ({ufs}). Mais detalhado: <b>{r.get('nome')}</b> "
            f"({ct.resumo_produto(r.get('escala'), r.get('ano'))}).")
        self._mostrar_botao_recom()

    def _usar_recomendacao(self):
        if not getattr(self, "_recomendados", None):
            return
        alvo = self._recomendados[0]["chave"]
        for i in range(self.cb_uf.count()):
            d = self.cb_uf.itemData(i)
            if isinstance(d, dict) and d.get("chave") == alvo:
                self.chk_link.setChecked(False)
                self.cb_uf.setCurrentIndex(i)
                return

    def _ajustar_escala(self):
        lito = self.cat["temas"][self.cb_tema.currentIndex()]["chave"] not in self.cat["endpoints_temas"]
        self.cb_escala.setEnabled(lito)
        self.lb_escala.setEnabled(lito)

    def _alternar_link(self, on):
        self.txt_url.setVisible(on)
        self._mostrar_botao_recom()
        if not on:
            self._atualizar_url()

    def _atualizar_url(self):
        if not self.chk_link.isChecked():
            d = self.cb_uf.currentData()
            self.txt_url.setText(d["url"] if isinstance(d, dict) else "")

    def _ocupado(self, on):
        if not ui.vivo(self):
            return
        self.barra.setVisible(on)
        self.btn_exec.setEnabled(not on)
        self.btn_cancel.setEnabled(on)
        if on:
            self._status("Baixando e preparando o mapa…", "andando")

    # -------------------------------------------------------------- opções
    def _opcoes(self):
        """Lê tudo da interface de uma vez (na thread principal), antes de disparar a tarefa."""
        usar_mask = self.rb_mask.isChecked()
        canvas = self.iface.mapCanvas()
        modo = "mascara" if usar_mask else ("tudo" if self.rb_tudo.isChecked() else "tela")
        mask = self.cb_mask.currentLayer() if usar_mask else None
        if usar_mask and mask is None:
            raise ErroDados("Escolha uma camada máscara de polígono para o recorte.")
        if mask is not None:
            ext, crs = mask.extent(), mask.crs()
        else:
            ext = self.iface.mapCanvas().extent()
            crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        ext84, bbox = geo.extensao_wgs84(ext, crs)
        raster = self.cb_raster.currentLayer() if (usar_mask and self.chk_raster.isChecked()) else None
        _rot, driver, extensao = geo.FORMATOS[self.cb_fmt.currentIndex()]
        return {
            "bbox": bbox,
            "centro": (ext84.center().x(), ext84.center().y()),
            "mask_id": mask.id() if mask is not None else None,
            "raster_id": raster.id() if raster is not None else None,
            "crs_destino": QgsProject.instance().crs() if self.chk_reproj.isChecked() else None,
            "driver": driver, "ext": extensao,
            "opacidade": self.sld_op.value() / 100.0,
            "borda": BORDAS[self.cb_borda.currentIndex()][1],
            "pasta": geo.pasta_dados(PASTA),
            "modo_area": modo,
            "ret_tela": canvas.extent() if modo == "tela" else None,
            "crs_tela": canvas.mapSettings().destinationCrs(),
        }

    # ------------------------------------------------------------ execução
    def executar(self):
        try:
            op = self._opcoes()
            aba = self.tabs.currentIndex()
            if aba == 0:
                uf = uf_por_ponto(*op["centro"], self.cat["ufs_bbox"])
                try:
                    plano = ct.plano_download(self.cat, self.cb_escala.currentIndex(), self.cb_tema.currentIndex(), uf)
                except ValueError as e:
                    raise ErroDados(str(e))
                self._disparar_nuvem(plano, op)
            elif aba == 1:
                url = self.txt_url.text().strip()
                if not url:
                    raise ErroDados("Informe o link do item no RIGeo.")
                item = None if self.chk_link.isChecked() else self.cb_uf.currentData()
                self._disparar_pacote(op, url=url, modo_camadas=self.cb_camadas.currentData(),
                                      item=item if isinstance(item, dict) else None)
            else:
                arq = self.file_w.filePath()
                if not arq or not Path(arq).exists():
                    raise ErroDados("Escolha um arquivo local (.zip, .shp ou .gpkg).")
                self._disparar_pacote(op, arquivo=Path(arq), modo_camadas=self.cb_camadas_loc.currentData())
        except ErroDados as e:
            ui.avisar(self, "LitoBR", str(e))

    def _disparar_nuvem(self, plano, op):
        arq_base = f"LitoBR_{plano['tema']}_{plano['tag']}_{int(time.time())}"
        arq_temp = op["pasta"] / f"{arq_base}_temp.geojson"
        cat, bbox = self.cat, op["bbox"]
        estado = {"baixou": False}

        def trabalho(tarefa):
            return servicos.baixar_nuvem(cat, plano, bbox, arq_temp, tarefa)

        def ao_terminar(ok, res, erro):
            if not ok or not res:
                geo.apagar_silencioso(arq_temp, TAG)
                if plano["fallback_bdia"] and not estado["baixou"] and erro != "Operação cancelada.":
                    registrar(f"Serviço estadual falhou ({erro}); tentando BDIA 1:250.000.", TAG, "aviso")
                    self.iface.messageBar().pushMessage(
                        "LitoBR", "Serviço estadual do SGB indisponível; carregando BDIA/IBGE 1:250.000.",
                        level=Qgis.MessageLevel.Warning, duration=8)
                    self._disparar_nuvem(ct.plano_bdia(cat, plano["tema"]), op)
                    return
                self._falhou(erro)
                return
            estado["baixou"] = True
            escala, ano = res.get("escala"), res.get("ano")
            titulo = next(t["rotulo"] for t in cat["temas"] if t["chave"] == plano["tema"]).split(" (")[0]
            if plano.get("estadual"):
                titulo = f"{titulo}, {plano['nome_uf']}"
            elif plano["tipo"] == "BDIA_WFS":
                titulo = f"{titulo}, BDIA/IBGE"
            nome = nome_produto(titulo, escala, ano, plano.get("ano_rotulo"))
            try:
                camada = geo.abrir_vetor(res["arquivo"], nome, em_memoria=True)
            finally:
                geo.apagar_silencioso(arq_temp, TAG)
            autor, sigla, local = AUTORES[plano["origem"]]
            url_fonte = cat["bases"]["BDIA_WFS"] if plano["tipo"] == "BDIA_WFS" else res.get("url")
            titulo_ref = f"{titulo}, escala {escala}" if escala else titulo
            ref = abnt.referencia_online(autor, titulo_ref, url_fonte, local, sigla, ano if isinstance(ano, int) else None)
            detalhes = detalhes_produto(escala, ano, plano.get("ano_rotulo"))
            camada = self._pos_processar(camada, nome, arq_base, op, ref, forcar_salvar=True, detalhes=detalhes)
            QgsProject.instance().addMapLayer(camada)
            estilo_geologia.estilizar(self.iface, camada, plano["tema"], res["paleta"], None, op["opacidade"], op["borda"])
            self._recortar_raster(op)
            self._concluir([camada])

        self._ocupado(True)
        self.tarefas.disparar(TarefaFundo(f"LitoBR: baixando {plano['tag']}", trabalho, ao_terminar, TAG))

    def _disparar_pacote(self, op, url=None, arquivo=None, modo_camadas="escolher", item=None):
        """`item` é a entrada do catálogo (estado ou província) quando veio da lista."""
        cat, pasta = self.cat, op["pasta"]
        preferido = (item or {}).get("arquivo")

        def trabalho(_tarefa):
            if url:
                baixado = servicos.baixar_rigeo(cat, url, pasta, preferido)
            else:
                baixado = {"caminho": arquivo, "titulo": None, "escala": None, "ano": None}
            vetores, origem = servicos.extrair_pacote(baixado["caminho"], pasta)
            dicionario = servicos.obter_dicionario_sgb(cat, pasta)
            return dict(baixado, vetores=vetores, origem=origem, nome=Path(baixado["caminho"]).stem,
                        dicionario=dicionario)

        def ao_terminar(ok, res, erro):
            if not ok or not res:
                self._falhou(erro)
                return
            escolhidas = self._escolher_camadas(res["vetores"], modo_camadas)
            if escolhidas is None:  # a pessoa cancelou a escolha
                self._falhou("Operação cancelada.")
                return
            if not escolhidas:
                raise ErroDados("Nenhuma camada com feições dentro do pacote.")
            fonte = url or str(arquivo)
            carimbo = int(time.time())
            # o catálogo foi conferido no RIGeo; o que faltar vem dos metadados do próprio item
            escala = (item or {}).get("escala") or res.get("escala")
            ano = (item or {}).get("ano") or res.get("ano")
            produto = (item or {}).get("produto") or res.get("titulo") or res["nome"]
            titulo_item = (item or {}).get("titulo") or res.get("titulo") or produto
            local = (item or {}).get("nome") or produto
            detalhes = detalhes_produto(escala, ano) if url else {}
            camadas = []
            for lyr in escolhidas:
                if url:
                    titulo_ref = f"{titulo_item}: {lyr.name()}" + (f", escala {escala}" if escala else "")
                    ref = abnt.referencia_online(AUTORES["SGB"][0], titulo_ref, fonte, "Brasília", "SGB/CPRM",
                                                 ano if isinstance(ano, int) else None)
                    amigavel = ct.nome_camada_pacote(lyr.name(), bool(lyr.customProperty("litobr_principal")))
                    nome = nome_produto(f"{amigavel}, {local}", escala, ano)
                else:
                    ref, nome = f"Arquivo local: {fonte}", lyr.name()
                camadas.append(self._pos_processar(lyr, nome, f"{lyr.name()}_{carimbo}", op, ref, detalhes=detalhes))
            if len(camadas) > 1:
                rotulo_grupo = nome_produto(local, escala, ano) if url else res["nome"]
                grp = QgsProject.instance().layerTreeRoot().insertGroup(0, rotulo_grupo)
                # polígonos por baixo, pontos por cima
                for lyr in sorted(camadas, key=lambda c: -c.geometryType()):
                    QgsProject.instance().addMapLayer(lyr, False)
                    grp.insertLayer(0, lyr)
            else:
                QgsProject.instance().addMapLayer(camadas[0])
            for lyr in camadas:
                estilo_geologia.estilizar(self.iface, lyr, None, None, res["origem"], op["opacidade"], op["borda"],
                                          res.get("dicionario"))
            self._recortar_raster(op)
            self._concluir(camadas)

        self._ocupado(True)
        desc = "LitoBR: baixando pacote do RIGeo" if url else "LitoBR: abrindo pacote local"
        self.tarefas.disparar(TarefaFundo(desc, trabalho, ao_terminar, TAG))

    # ------------------------------------------------------ thread principal
    def _escolher_camadas(self, vetores, modo):
        """modo 'principal' (só a litologia), 'todas' ou 'escolher' (abre a lista). None = cancelado."""
        abertas = []
        for arq in vetores:
            lyr = QgsVectorLayer(str(arq), arq.stem, "ogr")
            if not lyr.isValid():
                registrar(f"Ignorei {arq.name}: não abriu como vetor.", TAG, "aviso")
                continue
            nota = ct.nota_camada(arq.stem, lyr.featureCount(), lyr.geometryType() == QgsWkbTypes.GeometryType.PolygonGeometry)
            if nota is not None:
                abertas.append((nota, lyr))
        if not abertas:
            return []
        abertas.sort(key=lambda x: -x[0])
        principal = abertas[0][1]
        principal.setCustomProperty("litobr_principal", True)
        if modo == "principal":
            return [principal]
        if modo == "todas":
            return [lyr for _n, lyr in abertas]
        return _dialogo_camadas(self, [lyr for _n, lyr in abertas], principal)

    def _pos_processar(self, camada, nome, nome_arquivo, op, referencia, forcar_salvar=False, detalhes=None):
        """Recorta, reprojeta e grava. Pacote local que não mudou continua lendo do arquivo original."""
        original = camada
        mask = QgsProject.instance().mapLayer(op["mask_id"]) if op["mask_id"] else None
        if op["mask_id"] and mask is None:
            registrar("A camada máscara foi removida do projeto; carreguei sem recorte.", TAG, "aviso")
        camada = geo.recortar(camada, mask, TAG)
        if op.get("modo_area") == "tela":
            camada = geo.recortar_retangulo(camada, op["ret_tela"], op["crs_tela"], TAG)
            if camada.featureCount() == 0:
                registrar(f"{nome}: nada desta camada cai dentro da tela.", TAG, "aviso")
        camada = geo.reprojetar(camada, op["crs_destino"], TAG)
        camada.setName(nome)
        if forcar_salvar or camada is not original:
            camada = geo.salvar(camada, op["pasta"], nome_arquivo, op["driver"], op["ext"])
        geo.aplicar_metadado_abnt(camada, nome, referencia, ORIGEM, detalhes)
        return camada

    def _recortar_raster(self, op):
        if not op["raster_id"] or not op["mask_id"]:
            return
        raster = QgsProject.instance().mapLayer(op["raster_id"])
        mask = QgsProject.instance().mapLayer(op["mask_id"])
        if raster is None or mask is None:
            return
        saida = str(op["pasta"] / f"{raster.name()}_recorte_{int(time.time())}.tif")
        try:
            res = processing.run("gdal:cliprasterbymasklayer", {
                "INPUT": raster, "MASK": mask, "CROP_TO_CUTLINE": True,
                "KEEP_RESOLUTION": True, "OUTPUT": saida})
            rl = QgsRasterLayer(res["OUTPUT"], f"{raster.name()}_recorte")
            if rl.isValid():
                QgsProject.instance().addMapLayer(rl)
        except Exception as e:  # noqa: BLE001 - erro do GDAL/processing
            registrar(f"Recorte do raster falhou: {e}", TAG, "aviso")
            self.iface.messageBar().pushMessage("LitoBR", "O recorte do raster falhou (veja o log).", level=Qgis.MessageLevel.Warning)

    def _concluir(self, camadas):
        self._ocupado(False)
        self.iface.setActiveLayer(camadas[0])
        self.iface.zoomToActiveLayer()
        registrar(f"{len(camadas)} camada(s) carregada(s).", TAG, "ok")
        self.iface.messageBar().pushMessage("LitoBR", f"{len(camadas)} camada(s) carregada(s) e estilizada(s).",
                                            level=Qgis.MessageLevel.Success, duration=5)
        extra = f" e mais {len(camadas) - 1}" if len(camadas) > 1 else ""
        self._status(f"✔ Pronto: {camadas[0].name()}{extra}. Já está no mapa, com a citação ABNT nos metadados.", "ok")

    def _status(self, texto, tipo="ok"):
        if not ui.vivo(self):
            return
        self.lb_status.setText(texto)
        self.lb_status.setProperty("tipo", tipo)
        self.lb_status.style().unpolish(self.lb_status)
        self.lb_status.style().polish(self.lb_status)
        self.lb_status.setVisible(bool(texto))

    def _falhou(self, erro):
        self._ocupado(False)
        msg = erro or "A operação não foi concluída."
        registrar(msg, TAG, "aviso")
        self._status("Não concluído: " + msg, "erro")
        if msg != "Operação cancelada.":
            if ui.vivo(self) and self.isVisible():
                ui.avisar(self, "LitoBR", msg)
            else:
                self.iface.messageBar().pushMessage("LitoBR", msg, level=Qgis.MessageLevel.Warning, duration=10)
