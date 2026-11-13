"""Ponto de entrada do LitoBR."""
from pathlib import Path

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .core import ui

MENU = "&LitoBR"


class LitoBRPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dlg = None

    def initGui(self):
        icone = QIcon(str(Path(__file__).with_name("icon.svg")))
        self.action = QAction(icone, "LitoBR: geologia do Brasil (SGB/CPRM e BDIA/IBGE)", self.iface.mainWindow())
        self.action.triggered.connect(self.abrir)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToVectorMenu(MENU, self.action)

    def unload(self):
        if self.dlg is not None:
            self.dlg.tarefas.cancelar_todas()
        if ui.vivo(self.dlg):
            self.dlg.desligar()
            self.dlg.close()
            self.dlg.deleteLater()
        self.dlg = None
        if self.action:
            self.iface.removePluginVectorMenu(MENU, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

    def abrir(self):
        if not ui.vivo(self.dlg):
            from .dialogo import LitoBRDialog
            self.dlg = LitoBRDialog(self.iface)
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()
