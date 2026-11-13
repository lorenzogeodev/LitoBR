"""Tarefa em segundo plano sem gambiarra de variável global.

Regra: `trabalho(tarefa)` roda FORA da thread principal e só pode fazer rede,
disco e conta (numpy/gdal). Nada de camada do projeto, canvas ou diálogo.
`ao_terminar(ok, resultado, erro)` roda NA thread principal e é lá que se
cria/estiliza/adiciona camada.
"""
from qgis.core import QgsApplication, QgsTask

from .erros import ErroDados
from .log import registrar, registrar_excecao


class TarefaFundo(QgsTask):
    def __init__(self, descricao, trabalho, ao_terminar, tag):
        super().__init__(descricao, QgsTask.Flag.CanCancel)
        self._trabalho = trabalho
        self._ao_terminar = ao_terminar
        self._tag = tag
        self.resultado = None
        self.erro = ""

    def run(self):
        try:
            self.resultado = self._trabalho(self)
            return not self.isCanceled()
        except ErroDados as e:
            self.erro = str(e)
        except Exception as e:  # noqa: BLE001 - qualquer bug vai pro log com traceback
            registrar_excecao(self._tag, f"Erro inesperado em '{self.description()}'")
            self.erro = f"Erro inesperado ({type(e).__name__}). Detalhes no painel de log, aba {self._tag}."
        return False

    def finished(self, ok):
        if self.isCanceled() and not self.erro:
            self.erro = "Operação cancelada."
        try:
            self._ao_terminar(bool(ok), self.resultado, self.erro)
        except ErroDados as e:
            registrar(str(e), self._tag, "aviso")
            self._ao_terminar_falha(str(e))
        except Exception:  # noqa: BLE001
            registrar_excecao(self._tag, f"Erro ao finalizar '{self.description()}'")
            self._ao_terminar_falha(f"Erro ao carregar o resultado. Detalhes no painel de log, aba {self._tag}.")

    def _ao_terminar_falha(self, msg):
        try:
            self._ao_terminar(False, None, msg)
        except Exception:  # noqa: BLE001
            registrar_excecao(self._tag, "Falha também no tratamento do erro")


class GerenciadorTarefas:
    """Segura referência das tarefas (o Python apaga QgsTask sem referência e o QGIS cai)."""

    def __init__(self):
        self._vivas = set()

    def disparar(self, tarefa):
        self._vivas.add(tarefa)
        tarefa.taskCompleted.connect(lambda t=tarefa: self._vivas.discard(t))
        tarefa.taskTerminated.connect(lambda t=tarefa: self._vivas.discard(t))
        QgsApplication.taskManager().addTask(tarefa)
        return tarefa

    def cancelar_todas(self):
        for t in list(self._vivas):
            t.cancel()

    @property
    def pendentes(self):
        return len(self._vivas)
