"""Exceções com mensagem pronta pra mostrar ao usuário."""


class ErroDados(Exception):
    """Erro previsível (serviço fora, área sem feições, parâmetro inválido)."""


class ErroRede(ErroDados):
    """Falha de conexão, TLS, timeout ou HTTP."""


class ErroServico(ErroDados):
    """O servidor respondeu, mas com erro ou com conteúdo inválido."""
