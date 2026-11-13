"""Operações em camadas. Rodar SEMPRE na thread principal."""
from pathlib import Path

from qgis import processing
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeatureRequest,
    QgsProject, QgsVectorFileWriter, QgsVectorLayer,
)

from .erros import ErroDados
from .log import registrar

WGS84 = "EPSG:4326"

# (rótulo, driver OGR, extensão)
FORMATOS = [
    ("Camada temporária (memória)", "MEMORY", ""),
    ("GeoPackage (.gpkg)", "GPKG", ".gpkg"),
    ("Shapefile (.shp)", "ESRI Shapefile", ".shp"),
    ("GeoJSON (.geojson)", "GeoJSON", ".geojson"),
]


def pasta_dados(nome):
    p = Path.home() / nome
    p.mkdir(parents=True, exist_ok=True)
    return p


def extensao_wgs84(extent, crs_origem):
    """Extensão (QgsRectangle) no CRS de origem -> (retângulo em 4326, 'xmin,ymin,xmax,ymax')."""
    dst = QgsCoordinateReferenceSystem(WGS84)
    if extent.isEmpty() or not extent.isFinite():
        raise ErroDados("A área escolhida está vazia. Aproxime o mapa da área de interesse ou escolha outra máscara.")
    if crs_origem.isValid() and crs_origem != dst:
        try:
            extent = QgsCoordinateTransform(crs_origem, dst, QgsProject.instance()).transformBoundingBox(extent)
        except Exception as e:  # noqa: BLE001 - QgsCsException quando a área sai do domínio do SRC
            raise ErroDados(f"Não consegui converter a área para coordenadas geográficas: {e}")
    if not (-180 <= extent.xMinimum() < extent.xMaximum() <= 180 and -90 <= extent.yMinimum() < extent.yMaximum() <= 90):
        raise ErroDados("A área escolhida não cabe em coordenadas geográficas. Confira o SRC do projeto.")
    txt = f"{extent.xMinimum():.5f},{extent.yMinimum():.5f},{extent.xMaximum():.5f},{extent.yMaximum():.5f}"
    return extent, txt


def materializar(camada, nome=None):
    """Copia a camada pra memória. Assim o arquivo temporário de origem pode ser apagado."""
    mem = camada.materialize(QgsFeatureRequest())
    mem.setName(nome or camada.name())
    return mem


def abrir_vetor(caminho, nome, em_memoria=True):
    lyr = QgsVectorLayer(str(caminho), nome, "ogr")
    if not lyr.isValid():
        raise ErroDados(f"Não consegui abrir o arquivo baixado: {Path(caminho).name}")
    return materializar(lyr, nome) if em_memoria else lyr


def reprojetar(camada, crs_destino, tag):
    if not crs_destino or not crs_destino.isValid() or camada.crs() == crs_destino:
        return camada
    try:
        out = processing.run("native:reprojectlayer",
                             {"INPUT": camada, "TARGET_CRS": crs_destino, "OUTPUT": "memory:"})["OUTPUT"]
        out.setName(camada.name())
        return out
    except Exception as e:  # noqa: BLE001 - o processing levanta QgsProcessingException genérica
        registrar(f"Reprojeção falhou para {camada.name()}: {e}. Mantive o SRC original.", tag, "aviso")
        return camada


def recortar(camada, mascara, tag):
    """Recorta pela máscara; se der erro de geometria, corrige as duas e tenta de novo."""
    if not mascara or not mascara.isValid():
        return camada
    try:
        out = processing.run("native:clip", {"INPUT": camada, "OVERLAY": mascara, "OUTPUT": "memory:"})["OUTPUT"]
    except Exception as e1:  # noqa: BLE001
        registrar(f"Recorte direto falhou ({e1}); tentando com geometrias corrigidas.", tag, "aviso")
        try:
            a = processing.run("native:fixgeometries", {"INPUT": camada, "OUTPUT": "memory:"})["OUTPUT"]
            b = processing.run("native:fixgeometries", {"INPUT": mascara, "OUTPUT": "memory:"})["OUTPUT"]
            out = processing.run("native:clip", {"INPUT": a, "OVERLAY": b, "OUTPUT": "memory:"})["OUTPUT"]
        except Exception as e2:  # noqa: BLE001
            raise ErroDados(f"Não consegui recortar {camada.name()} pela máscara: {e2}")
    out.setName(camada.name())
    return out


def recortar_retangulo(camada, retangulo, crs_retangulo, tag):
    """Corta as feições no limite de um retângulo (a tela), no SRC em que ele foi medido."""
    if retangulo is None or retangulo.isEmpty():
        return camada
    ext = (f"{retangulo.xMinimum()},{retangulo.xMaximum()},{retangulo.yMinimum()},{retangulo.yMaximum()}"
           f" [{crs_retangulo.authid()}]")
    try:
        out = processing.run("native:extractbyextent",
                             {"INPUT": camada, "EXTENT": ext, "CLIP": True, "OUTPUT": "memory:"})["OUTPUT"]
    except Exception as e1:  # noqa: BLE001 - geometria inválida: corrige e tenta de novo
        registrar(f"Recorte pela tela falhou ({e1}); tentando com geometrias corrigidas.", tag, "aviso")
        try:
            fix = processing.run("native:fixgeometries", {"INPUT": camada, "OUTPUT": "memory:"})["OUTPUT"]
            out = processing.run("native:extractbyextent",
                                 {"INPUT": fix, "EXTENT": ext, "CLIP": True, "OUTPUT": "memory:"})["OUTPUT"]
        except Exception as e2:  # noqa: BLE001
            raise ErroDados(f"Não consegui recortar {camada.name()} no limite da tela: {e2}")
    out.setName(camada.name())
    return out


def salvar(camada, pasta, nome_base, driver, ext):
    """Grava em disco e devolve a camada aberta do arquivo. MEMORY devolve a própria camada."""
    if driver == "MEMORY":
        return camada
    caminho = Path(pasta) / f"{nome_base}{ext}"
    opc = QgsVectorFileWriter.SaveVectorOptions()
    opc.driverName = driver
    opc.fileEncoding = "UTF-8"
    opc.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
    res = QgsVectorFileWriter.writeAsVectorFormatV3(
        camada, str(caminho), QgsProject.instance().transformContext(), opc)
    if res[0] != QgsVectorFileWriter.NoError:
        raise ErroDados(f"Falha ao gravar {caminho.name}: {res[1]}")
    lyr = QgsVectorLayer(str(caminho), camada.name(), "ogr")
    if not lyr.isValid():
        raise ErroDados(f"Gravei {caminho.name}, mas não consegui reabrir.")
    return lyr


# Rótulo legível de cada chave de `detalhes` (a chave fica sem acento na propriedade da camada).
ROTULOS = {"escala": "Escala", "ano_de_publicacao": "Ano de publicação", "data_de_acesso": "Data de acesso"}


def aplicar_metadado_abnt(camada, titulo, referencia, origem, detalhes=None):
    """Título, resumo e direitos com a referência ABNT.

    `detalhes` é um dict (por exemplo escala, ano de publicação, data de acesso) que vai
    no resumo e em propriedades da camada (`litobr_<chave>`).
    """
    detalhes = detalhes or {}
    linhas = "".join(f"{ROTULOS.get(k, k.replace('_', ' ').capitalize())}: {v}\n" for k, v in detalhes.items() if v)
    meta = camada.metadata()
    meta.setTitle(titulo)
    meta.setAbstract(f"Camada carregada por {origem}.\n{linhas}Referência ABNT NBR 6023:\n{referencia}")
    meta.setRights([referencia])
    camada.setMetadata(meta)
    camada.setCustomProperty("referencia_abnt", referencia)
    for k, v in detalhes.items():
        if v:
            camada.setCustomProperty(f"litobr_{k}", str(v))


def apagar_silencioso(caminho, tag):
    try:
        Path(caminho).unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        registrar(f"Não consegui apagar o temporário {caminho}: {e}", tag, "aviso")
