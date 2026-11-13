"""Regras de classificação e cor (puro, sem QGIS).

Tudo aqui recebe texto e devolve chave/cor, pra ser testado sem QGIS.
"""
from .texto import normalizar, tokens

# ---------------------------------------------------------------------------
# Hidrogeologia
# ---------------------------------------------------------------------------
CORES_AQUIFERO = {
    "poroso": ("#ffe082", "#ff8f00"),
    "carstico": ("#90caf9", "#1565c0"),
    "fissural": ("#a5d6a7", "#2e7d32"),
    "outro": ("#eeeeee", "#757575"),
}


def classe_aquifero(txt):
    t = normalizar(txt)
    if any(k in t for k in ("poroso", "granular", "sedimentar")):
        return "poroso"
    if any(k in t for k in ("carstico", "calcari", "carbonat")):
        return "carstico"
    if any(k in t for k in ("fissural", "cristalino", "fraturado")):
        return "fissural"
    return "outro"


SIMBOLOS_POCO = {
    "tubular": {"name": "circle", "color": "#29b6f6", "outline_color": "#01579b", "size": "3.0"},
    "escavado": {"name": "square", "color": "#ffb74d", "outline_color": "#e65100", "size": "2.8"},
    "nascente": {"name": "triangle", "color": "#81c784", "outline_color": "#1b5e20", "size": "3.2"},
    "outro": {"name": "circle", "color": "#bdbdbd", "outline_color": "#424242", "size": "2.5"},
}


def classe_poco(txt):
    t = normalizar(txt)
    if "tubular" in t or "profundo" in t:
        return "tubular"
    if "escavado" in t or "cacimba" in t or "amazonas" in t:
        return "escavado"
    if "nascente" in t or "surgencia" in t or "fonte" in t:
        return "nascente"
    return "outro"


# ---------------------------------------------------------------------------
# Geologia: pontos
# ---------------------------------------------------------------------------
SIMBOLOS_AFLORAMENTO = {
    "Corte de Estrada / Rodovia": ("square", "#e65100", "#212121", "3.8"),
    "Lajedo / Afloramento Natural": ("diamond", "#2e7d32", "#003300", "3.8"),
    "Mina / Pedreira / Garimpo": ("triangle", "#c2185b", "#000000", "4.2"),
    "Drenagem / Calha de Rio": ("circle", "#0288d1", "#01579b", "3.5"),
    "Trincheira / Sondagem": ("cross2", "#6a1b9a", "#1a1a1a", "4.0"),
    "Outros / Não Especificado": ("circle", "#757575", "#212121", "3.0"),
}


def classe_afloramento(txt):
    t = normalizar(txt)
    if any(k in t for k in ("estrada", "rodovia", "corte", "talude")):
        return "Corte de Estrada / Rodovia"
    if any(k in t for k in ("lajedo", "natural", "morro", "rocha", "matacao")):
        return "Lajedo / Afloramento Natural"
    if any(k in t for k in ("mina", "pedreira", "garimpo", "cava")):
        return "Mina / Pedreira / Garimpo"
    if any(k in t for k in ("rio", "drenagem", "leito", "calha", "riacho")):
        return "Drenagem / Calha de Rio"
    if any(k in t for k in ("trincheira", "sondagem", "furo")):
        return "Trincheira / Sondagem"
    return "Outros / Não Especificado"


SIMBOLOS_SUBSTANCIA = {
    "Metais Nobres (Au, Ag, PGM)": ("star", "#ffd700", "#b29400", "4.5"),
    "Gemas e Ornamentais": ("diamond", "#00e5ff", "#00838f", "4.2"),
    "Construção Civil (Areia, Brita)": ("square", "#8d6e63", "#3e2723", "3.8"),
    "Metais Base e Ferrosos": ("circle", "#d32f2f", "#491212", "3.8"),
    "Minerais Industriais/Fertilizantes": ("hexagon", "#1976d2", "#0d47a1", "4.0"),
    "Energéticos (Carvão, Urânio)": ("cross_fill", "#212121", "#000000", "4.0"),
    "Geral": ("circle", "#ff9800", "#e65100", "3.5"),
}

# Palavras inteiras (tokens). Antes era 'au' in texto, que pegava "caulim".
_SUBST = [
    ("Metais Nobres (Au, Ag, PGM)", {"ouro", "au", "prata", "ag", "platina", "pt", "pgm", "paladio", "pd"}, ()),
    ("Gemas e Ornamentais", {"diamante", "gema", "gemas", "esmeralda", "turmalina", "agua-marinha",
                             "marmore", "granito", "quartzito", "ardosia", "ametista", "topazio"}, ("quartzo",)),
    ("Construção Civil (Areia, Brita)", {"areia", "brita", "argila", "cascalho", "saibro", "cascalheira"}, ()),
    ("Metais Base e Ferrosos", {"ferro", "fe", "manganes", "mn", "cobre", "cu", "chumbo", "pb", "zinco",
                                "zn", "niquel", "ni", "cromo", "cr", "estanho", "sn", "aluminio", "bauxita",
                                "titanio", "ilmenita", "tungstenio", "wolframita"}, ()),
    ("Minerais Industriais/Fertilizantes", {"calcario", "fosfato", "apatita", "gesso", "gipsita", "caulim",
                                            "fluorita", "barita", "talco", "potassio", "silvinita",
                                            "feldspato", "mica", "grafita", "magnesita", "dolomito"}, ()),
    ("Energéticos (Carvão, Urânio)", {"carvao", "uranio", "u", "petroleo", "gas", "turfa", "xisto"}, ()),
]


def classe_substancia(txt):
    toks = set(tokens(txt))
    norm = normalizar(txt)
    for classe, palavras, prefixos in _SUBST:
        if toks & palavras or any(norm.startswith(p) or f" {p}" in norm for p in prefixos):
            return classe
    return "Geral"


def simbolo_geossitio(txt):
    t = normalizar(txt)
    if "internacional" in t:
        return {"name": "star", "color": "#ffd700", "outline_color": "#b71c1c", "size": "5.0"}
    if "nacional" in t:
        return {"name": "diamond", "color": "#ab47bc", "outline_color": "#4a148c", "size": "4.5"}
    return {"name": "circle", "color": "#ff9800", "outline_color": "#e65100", "size": "3.5"}


def simbolo_medida_estrutural(txt):
    t = normalizar(txt)
    if "foliacao" in t or "xistosidade" in t or "acamamento" in t:
        return {"name": "line", "color": "#d50000", "size": "4.0"}
    if "lineacao" in t:
        return {"name": "arrow", "color": "#1a237e", "size": "3.5"}
    return {"name": "cross", "color": "#000000", "size": "3.0"}


# ---------------------------------------------------------------------------
# Geologia: polígonos (paleta heurística, usada só quando o servidor não dá a oficial)
# ---------------------------------------------------------------------------
COR_PADRAO = ("#d9d9d9", "#666666")


def cor_geologica(sigla, unidade="", lito="", tempo=""):
    """(preenchimento, borda) aproximando a convenção cronoestratigráfica do SGB.

    Correções em relação à v3.8.1:
      * 'G' solto na sigla não marca mais granito (só 'GAMMA'/'γ').
      * 'NP...' não cai mais em Cenozoico (o teste de 'N' vinha antes do de 'NP').
    """
    s = normalizar(sigla).upper().replace("Γ", "GAMMA")
    if "γ" in str(sigla or ""):
        s += "GAMMA"
    u, l, t = normalizar(unidade), normalizar(lito), normalizar(tempo)

    if any(k in u for k in ("agua", "acude", "represa", "reservatorio")) or s in ("H2O", "AGUA"):
        return "#a6cee3", "#1f78b4"

    granitoide = (
        "GAMMA" in s
        or any(k in l for k in ("granit", "monzonit", "sienit", "tonalit", "granodiorit", "diatexit", "pegmatit", "charnockit"))
        or any(k in u for k in ("intrusiv", "suite", "ortognaisse"))
    )
    if granitoide:
        if "diatexit" in l or "migmatit" in l:
            return "#e78ac3", "#8e24aa"
        if "monzonit" in l or "sienit" in l:
            return "#fb8072", "#b71c1c"
        if "tonalit" in l or "granodiorit" in l:
            return "#cc79a7", "#6a1b9a"
        if "ortognaisse" in u:
            return "#b284be", "#4a148c"
        if s.startswith("PP"):
            return "#d95f6e", "#7f0000"
        return "#f46d75", "#99000d"

    if any(k in l for k in ("basalt", "gabro", "diorit", "anfibolit", "ultram", "piroxenit", "peridotit", "komatiit")) or "serra geral" in u:
        if "anfibolit" in l or "ultram" in l or "komatiit" in l:
            return "#598c59", "#1b4d20"
        return "#8c66ff", "#4a148c"
    if any(k in l for k in ("calcari", "marmor", "dolomit", "carbonat")):
        return "#80ccff", "#005580"

    # Cronoestratigrafia pela sigla/tempo (prefixos longos primeiro)
    if s.startswith("NP") or "neoproterozoico" in t:
        return "#fdae6b", "#a63603"
    if s.startswith("MP") or "mesoproterozoico" in t:
        return "#fd8d3c", "#7f2704"
    if s.startswith("PP") or "paleoproterozoico" in t:
        return "#d8b365", "#543005"
    if s.startswith(("Q", "N", "E")) or any(k in t for k in ("cenozoico", "quatern", "neogeno", "paleogeno")) \
            or any(k in u for k in ("aluvi", "coluvi", "deposito", "cobertura")):
        return "#fff7bc", "#d95f0e"
    if s.startswith(("K", "J", "T")) or any(k in t for k in ("mesozoico", "cretaceo", "jurassico", "triassico")):
        return "#a1d99b", "#238b45"
    if s.startswith(("P", "C", "D", "S", "O")) or "paleozoico" in t:
        return "#9ecae1", "#2171b5"
    if s.startswith("A") or "arqueano" in t:
        return "#ce1256", "#67001f"
    return COR_PADRAO


def escurecer(hex_cor, delta=60):
    h = hex_cor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(max(0, r - delta), max(0, g - delta), max(0, b - delta))


def rgb_hex(r, g, b):
    return "#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b))


# ---------------------------------------------------------------------------
# UF pela coordenada
# ---------------------------------------------------------------------------
def uf_por_ponto(x, y, bboxes):
    """UF de menor bbox que contém (x, y), em graus. None se cair fora de todas."""
    cands = [
        ((xmax - xmin) * (ymax - ymin), uf)
        for uf, (xmin, ymin, xmax, ymax) in bboxes.items()
        if xmin <= x <= xmax and ymin <= y <= ymax
    ]
    return min(cands)[1] if cands else None
