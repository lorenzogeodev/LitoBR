"""Catálogo de fontes do LitoBR (puro, sem QGIS).

Os endereços ficam em catalogo.json: quando o SGB/IBGE mudar uma URL,
basta editar o JSON, sem mexer em código.
"""
import json
import re
import unicodedata
from pathlib import Path

_ARQ = Path(__file__).with_name("catalogo.json")


def normalizar(txt):
    """Minúsculo e sem acento (cópia local: este módulo é testado sem o pacote)."""
    nfkd = unicodedata.normalize("NFKD", str(txt or ""))
    return nfkd.encode("ASCII", "ignore").decode("ASCII").lower().strip()


def carregar(caminho=None):
    with open(caminho or _ARQ, encoding="utf-8") as f:
        return json.load(f)


def resolver_caminho_sgb(caminho, rest_id_uf=None):
    """Caminho REST da camada.

    'geologia/x/MapServer/3'   -> igual
    'geologia/x/MapServer'     -> '/0' no fim
    'geologia/litoestratigrafia_estados/MapServer' + rest_id_uf=2 -> '.../MapServer/2'
    """
    caminho = caminho.strip("/")
    m = re.match(r"^(.*?/(?:MapServer|FeatureServer))(?:/(\d+))?$", caminho)
    if not m:
        raise ValueError(f"Caminho de serviço inválido no catálogo: {caminho}")
    base, lid = m.group(1), m.group(2)
    if "litoestratigrafia_estados" in base:
        if rest_id_uf is None:
            raise ValueError("O mapa estadual precisa da UF da área.")
        return f"{base}/{rest_id_uf}"
    return f"{base}/{lid if lid is not None else 0}"


# --- escala, ano e status de cada produto --------------------------------------
STATUS = ("estavel", "legado", "continuo", "desconhecido")


def status_produto(ano, ano_rotulo=None, corte=2014):
    """estavel (ano >= corte), legado (ano < corte), continuo (banco atualizado sempre) ou desconhecido."""
    if isinstance(ano, int):
        return "estavel" if ano >= corte else "legado"
    if ano_rotulo and "contínua" in ano_rotulo:
        return "continuo"
    return "desconhecido"


def texto_ano(ano, ano_rotulo=None):
    if isinstance(ano, int):
        return str(ano)
    return ano_rotulo or "ano não informado"


def texto_escala(escala):
    return escala or "escala não informada"


def resumo_produto(escala, ano, ano_rotulo=None):
    """'1:250.000 · 2017' / 'escala não informada · atualização contínua'."""
    return f"{texto_escala(escala)} · {texto_ano(ano, ano_rotulo)}"


_NOME_ESTADUAL = re.compile(r"^\s*(?P<nome>.+?)\s*-\s*(?P<escala>1\s*:\s*[\d.]+)\s*\[(?P<ano>\d{4})\]")


def ler_nome_camada_estadual(nome):
    """'Acre - 1:750.000 [2026]' -> ('Acre', '1:750.000', 2026); fora do padrão -> None."""
    m = _NOME_ESTADUAL.match(nome or "")
    if not m:
        return None
    return m.group("nome"), m.group("escala").replace(" ", ""), int(m.group("ano"))


def escolher_camada_estadual(camadas, nome_uf):
    """Na lista `layers` do serviço litoestratigrafia_estados, acha a camada da UF.

    Os números das camadas mudam quando o SGB publica um estado novo, então a busca
    é pelo nome. Retorna {'id', 'escala', 'ano'} ou None se o estado não tiver camada.
    """
    alvo = normalizar(nome_uf)
    for c in camadas or []:
        lido = ler_nome_camada_estadual(c.get("name"))
        if lido and normalizar(lido[0]) == alvo and c.get("id") is not None:
            return {"id": int(c["id"]), "escala": lido[1], "ano": lido[2]}
    return None


_ESCALA_TXT = re.compile(r"1\s*:\s*\d{1,3}(?:[.\s]\d{3})+")


def escala_ano_do_item(metadados):
    """Escala e ano de um item do RIGeo (DSpace 7) a partir do `metadata` dele."""
    def valores(chave):
        return [str(v.get("value", "")) for v in (metadados or {}).get(chave) or []]
    escala = None
    for chave in ("dc.format", "dc.subject", "dc.identifier.citation", "dc.description.notas", "dc.subject.other"):
        for v in valores(chave):
            m = _ESCALA_TXT.search(v)
            if m:
                escala = re.sub(r"\s", "", m.group(0))
                break
        if escala:
            break
    ano = None
    for v in valores("dc.date.issued"):
        m = re.match(r"(\d{4})", v)
        if m:
            ano = int(m.group(1))
            break
    return escala, ano


# --- recomendação pela área da tela ----------------------------------------------
def denominador(escala):
    """'1:75.000' -> 75000; texto sem escala -> None."""
    m = re.match(r"\s*1\s*:\s*([\d.\s]+)", escala or "")
    if not m:
        return None
    digitos = re.sub(r"\D", "", m.group(1))
    return int(digitos) if digitos else None


def intersecta(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def ufs_na_area(bbox, ufs_bbox):
    """UFs cujo retângulo toca a área (aproximação: os retângulos dos estados se sobrepõem)."""
    return sorted(uf for uf, b in ufs_bbox.items() if intersecta(bbox, b))


def recomendar(cat, bbox, uf_centro=None):
    """Produtos do RIGeo que cobrem a área, do mais detalhado pro menos detalhado.

    Província entra se o contorno dela toca a área (ou, sem contorno, se a UF dela
    está na área). Estado entra se for o do centro da tela ou se tocar a área.
    Retorna lista de dicts {'tipo': 'provincia'|'estado', 'chave', 'item', 'centro'}.
    """
    ufs = set(ufs_na_area(bbox, cat["ufs_bbox"]))
    if uf_centro:
        ufs.add(uf_centro)
    achados = []
    for chave, d in cat["projetos_regionais"].items():
        if d.get("bbox"):
            dentro, certo = intersecta(bbox, d["bbox"]), True
        else:  # sem contorno: só sabemos a UF, então vai pro fim da lista
            dentro, certo = bool(ufs & set(d.get("uf", "").split("/"))), False
        if dentro:
            achados.append({"tipo": "provincia", "chave": chave, "item": d, "centro": False, "certo": certo})
    for uf in ufs:
        d = cat["estados"].get(uf)
        if d and d.get("arquivo"):
            achados.append({"tipo": "estado", "chave": uf, "item": d, "centro": uf == uf_centro, "certo": True})

    def ordem(r):
        den = denominador(r["item"].get("escala")) or 10 ** 9
        return (0 if r["certo"] else 1, den, 0 if r["centro"] else 1, -(r["item"].get("ano") or 0))
    return sorted(achados, key=ordem)


def plano_download(cat, idx_escala, idx_tema, uf):
    """Decide o que baixar a partir da escolha na aba Nuvem.

    Retorna dict: tipo ('SGB_REST' | 'BDIA_WFS'), caminho, tema, tag, origem, fallback_bdia,
    escala, ano, ano_rotulo e, no mapa estadual, estadual=True com uf e nome_uf (a camada
    certa é resolvida no servidor, pelo nome do estado).
    """
    escala = cat["escalas"][idx_escala]
    tema = cat["temas"][idx_tema]["chave"]
    if tema in cat["endpoints_temas"]:
        e = cat["endpoints_temas"][tema]
        return {"tipo": e["tipo"], "caminho": resolver_caminho_sgb(e["caminho"]), "tema": tema,
                "tag": e["tag"], "origem": "SGB", "fallback_bdia": False,
                "escala": e.get("escala"), "ano": e.get("ano"), "ano_rotulo": e.get("ano_rotulo")}
    if escala["tipo"] == "BDIA_WFS":
        return plano_bdia(cat, tema)
    if escala["tipo"] == "ESTADUAL":
        if not uf or uf not in cat["estados"]:
            raise ValueError("A área escolhida não cai em nenhuma UF do Brasil. "
                             "Aproxime o mapa da área de interesse ou use uma máscara.")
        return {"tipo": "SGB_REST", "caminho": cat["estadual_layers"], "tema": tema,
                "tag": f"{uf}_Estadual", "origem": "SGB", "fallback_bdia": True,
                "estadual": True, "uf": uf, "nome_uf": cat["estados"][uf]["nome"],
                "escala": None, "ano": None, "ano_rotulo": "conforme o estado"}
    return {"tipo": "SGB_REST", "caminho": resolver_caminho_sgb(escala["caminho"]), "tema": tema,
            "tag": escala["tag"], "origem": "SGB", "fallback_bdia": False,
            "escala": escala.get("escala"), "ano": escala.get("ano"), "ano_rotulo": escala.get("ano_rotulo")}


def plano_bdia(cat, tema="LITO"):
    e = next(x for x in cat["escalas"] if x["tipo"] == "BDIA_WFS")
    return {"tipo": "BDIA_WFS", "caminho": e["caminho"], "tema": tema, "tag": e["tag"],
            "origem": "IBGE", "fallback_bdia": False,
            "escala": e.get("escala"), "ano": e.get("ano"), "ano_rotulo": e.get("ano_rotulo")}


# --- RIGeo (DSpace 7) -------------------------------------------------------
_UUID = re.compile(r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})", re.I)
EXT_VETOR = (".zip", ".gpkg", ".shp")


def uuid_rigeo(url):
    m = _UUID.search(url or "")
    return m.group(1) if m else None


def eh_link_direto(url):
    caminho = (url or "").lower().split("?")[0]
    return caminho.endswith(EXT_VETOR)


def escolher_bundle(bundles):
    return next((b for b in bundles if b.get("name") == "ORIGINAL"), bundles[0] if bundles else None)


def escolher_bitstream(bitstreams, preferido=None):
    """(nome, link) do melhor arquivo vetorial.

    `preferido` (nome conferido no catálogo) ganha sempre. Sem ele: .zip primeiro,
    depois nome com 'lito'/'geol'/'sig'.
    """
    if preferido:
        for bs in bitstreams:
            link = ((bs.get("_links") or {}).get("content") or {}).get("href")
            if link and bs.get("name", "").lower() == preferido.lower():
                return bs["name"], link
    cands = []
    for bs in bitstreams:
        nome = bs.get("name", "")
        link = ((bs.get("_links") or {}).get("content") or {}).get("href")
        if link and nome.lower().endswith(EXT_VETOR):
            n = nome.lower()
            nota = (30 if n.endswith(".zip") else 0) + (10 if any(k in n for k in ("lito", "geol", "sig", "shp")) else 0)
            cands.append((nota, nome, link))
    if not cands:
        return None
    cands.sort(key=lambda c: -c[0])
    return cands[0][1], cands[0][2]


# --- pontuação de camadas de um pacote --------------------------------------
PALAVRAS_GEOL = ("lito", "geol", "unid", "rocha", "formacao")
PALAVRAS_HIDRO = ("drenag", "hidro", "rio", "massa_d", "curso_d")


def nome_camada_pacote(arquivo, principal=False):
    """Nome legível pra camada de um pacote: a principal de geologia vira 'Litologia';
    as outras perdem o sublinhado ('bahia_estruturas' -> 'Bahia estruturas')."""
    n = (arquivo or "").lower()
    if principal and any(k in n for k in PALAVRAS_GEOL):
        return "Litologia"
    limpo = " ".join((arquivo or "").replace("_", " ").replace("-", " ").split())
    return (limpo[:1].upper() + limpo[1:]) if limpo else "Camada"


def nota_camada(nome, n_feicoes, eh_poligono):
    """Nota pra escolher a camada principal (litologia) dentro de um ZIP."""
    if n_feicoes <= 0:
        return None
    n = nome.lower()
    nota = n_feicoes * (2 if eh_poligono else 1)
    if eh_poligono and any(k in n for k in PALAVRAS_GEOL):
        nota += 50000
    if any(k in n for k in PALAVRAS_HIDRO):
        nota -= 50000
    return nota
