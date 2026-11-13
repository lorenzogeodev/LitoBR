"""Referências ABNT NBR 6023:2018 para dados online (puro, sem QGIS)."""
from datetime import datetime

MESES = {
    1: "jan.", 2: "fev.", 3: "mar.", 4: "abr.", 5: "maio", 6: "jun.",
    7: "jul.", 8: "ago.", 9: "set.", 10: "out.", 11: "nov.", 12: "dez.",
}


def data_acesso(dt=None):
    """'10 nov. 2026' (NBR 6023: dia sem zero à esquerda, mês abreviado)."""
    dt = dt or datetime.now()
    return f"{dt.day} {MESES[dt.month]} {dt.year}"


def referencia_online(autor, titulo, url, local=None, editora=None, ano=None, dt=None):
    """AUTOR. Título. Local: Editora, ano. Disponível em: url. Acesso em: data.

    Ano desconhecido vira o ano de acesso entre colchetes, como pede a NBR 6023:2018.
    """
    dt = dt or datetime.now()
    partes = [f"{autor.strip().rstrip('.').upper()}.", f"{titulo.strip().rstrip('.')}."]
    ano_txt = str(ano) if ano else f"[{dt.year}]"
    if local and editora:
        partes.append(f"{local}: {editora}, {ano_txt}.")
    elif editora:
        partes.append(f"[S. l.]: {editora}, {ano_txt}.")
    else:
        partes.append(f"{ano_txt}.")
    partes.append(f"Disponível em: {url}.")
    partes.append(f"Acesso em: {data_acesso(dt)}.")
    return " ".join(partes)


def credito_mapa(siglas, crs_authid, dt=None):
    """Crédito curto pro layout: 'Fonte: ANA; SGB. Acesso em nov. 2026. SRC: EPSG:31983.'"""
    dt = dt or datetime.now()
    s = "; ".join(sorted(set(siglas))) if siglas else "—"
    return f"Fonte dos dados: {s}. Acesso em {MESES[dt.month]} {dt.year}. SRC: {crs_authid or 'não definido'}."


def bloco_referencias(referencias, siglas, crs_authid, dt=None):
    refs = sorted(set(referencias))
    return (
        "=== REFERÊNCIAS (ABNT NBR 6023:2018) ===\n\n"
        + "\n\n".join(refs)
        + "\n\n=== CRÉDITO CURTO PARA LAYOUT DE MAPA ===\n"
        + credito_mapa(siglas, crs_authid, dt)
        + "\n"
    )
