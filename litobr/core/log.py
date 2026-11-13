"""Log no painel 'Mensagens de log' do QGIS, numa aba por plugin."""
import traceback

from qgis.core import Qgis, QgsMessageLog

_NIVEIS = {"info": Qgis.MessageLevel.Info, "aviso": Qgis.MessageLevel.Warning, "erro": Qgis.MessageLevel.Critical, "ok": Qgis.MessageLevel.Success}


def registrar(msg, tag, nivel="info"):
    QgsMessageLog.logMessage(str(msg), tag, _NIVEIS.get(nivel, Qgis.MessageLevel.Info))


def registrar_excecao(tag, contexto=""):
    """Grava o traceback completo no log (o usuário vê só a mensagem curta)."""
    QgsMessageLog.logMessage(f"{contexto}\n{traceback.format_exc()}", tag, Qgis.MessageLevel.Critical)
