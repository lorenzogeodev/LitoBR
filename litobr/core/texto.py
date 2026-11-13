"""Utilitários de texto e de valores de atributo (puro, sem QGIS)."""
import re
import unicodedata


def normalizar(txt):
    """Minúsculo, sem acento, sem espaço nas pontas. None vira ''."""
    if txt is None:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(txt))
    return nfkd.encode("ASCII", "ignore").decode("ASCII").lower().strip()


def eh_nulo(valor):
    """True para None, NULL do QGIS (QVariant nulo), '' e a string 'NULL'."""
    if valor is None:
        return True
    is_null = getattr(valor, "isNull", None)
    if callable(is_null):
        try:
            if is_null():
                return True
        except TypeError:
            pass
    return str(valor).strip().upper() in ("", "NULL")


def texto(valor):
    """Valor de atributo como texto limpo; nulos viram ''."""
    return "" if eh_nulo(valor) else str(valor).strip()


def tokens(txt):
    """Palavras normalizadas: 'Ouro (Au), caulim' -> ['ouro', 'au', 'caulim']."""
    return re.findall(r"[a-z0-9]+", normalizar(txt))


def achar_campo(nomes_campos, candidatos):
    """Primeiro campo cujo nome normalizado bate com um candidato (ordem dos candidatos)."""
    mapa = {normalizar(n): n for n in nomes_campos}
    for c in candidatos:
        n = mapa.get(normalizar(c))
        if n is not None:
            return n
    return None


def nome_arquivo_seguro(txt, max_len=80):
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", normalizar(txt)).strip("_")
    return (base or "camada")[:max_len]
