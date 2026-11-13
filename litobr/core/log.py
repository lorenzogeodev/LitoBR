"""Log no painel 'Mensagens de log' do QGIS, numa aba por plugin."""
import traceback

from qgis.core import Qgis, QgsMessageLog

_NIVEIS = {"info": Qgis.Info, "aviso": Qgis.Warning, "erro": Qgis.Critical, "ok": Qgis.Success}


def registrar(msg, tag, nivel="info"):
    QgsMessageLog.logMessage(str(msg), tag, _NIVEIS.get(nivel, Qgis.Info))


def registrar_excecao(tag, contexto=""):
    """Grava o traceback completo no log (o usuário vê só a mensagem curta)."""
    QgsMessageLog.logMessage(f"{contexto}\n{traceback.format_exc()}", tag, Qgis.Critical)
