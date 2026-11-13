"""HTTP pelo gerenciador de rede do QGIS.

O QgsBlockingNetworkRequest:
  * verifica o certificado TLS (sem brecha de man-in-the-middle);
  * respeita proxy, autenticação e certificados configurados no QGIS;
  * pode ser chamado de dentro de uma QgsTask (thread de fundo).
"""
import json
from urllib.parse import urlencode, urlparse

from qgis.core import QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from .erros import ErroRede, ErroServico

USER_AGENT = "LitoBR (QGIS plugin)"


def _montar_url(url, params):
    if not params:
        return url
    return url + ("&" if "?" in url else "?") + urlencode(params)


def get_bytes(url, params=None, timeout_s=90, feedback=None):
    url = _montar_url(url, params)
    req = QNetworkRequest(QUrl(url))
    req.setRawHeader(b"User-Agent", USER_AGENT.encode())
    req.setRawHeader(b"Accept", b"application/json, application/geo+json, */*")
    if hasattr(req, "setTransferTimeout"):  # Qt >= 5.15
        req.setTransferTimeout(int(timeout_s * 1000))
    bnr = QgsBlockingNetworkRequest()
    codigo = bnr.get(req, True, feedback)
    if codigo != QgsBlockingNetworkRequest.ErrorCode.NoError:
        host = urlparse(url).netloc
        raise ErroRede(f"Falha ao acessar {host}: {bnr.errorMessage()}")
    return bytes(bnr.reply().content())


def get_json(url, params=None, timeout_s=90, feedback=None):
    raw = get_bytes(url, params, timeout_s, feedback)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        trecho = raw[:200].decode("utf-8", errors="ignore").strip()
        raise ErroServico(f"Resposta não é JSON: {trecho}")


def baixar_arquivo(url, destino, timeout_s=180, feedback=None):
    """Baixa para `destino` (Path). Arquivo vai inteiro pra memória antes de gravar."""
    raw = get_bytes(url, None, timeout_s, feedback)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(raw)
    return destino
