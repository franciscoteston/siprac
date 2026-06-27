import threading

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        from core.siat_config import SIAT_ARQUIVO_PATH

        if SIAT_ARQUIVO_PATH.exists():
            thread = threading.Thread(
                target=self._carregar_indice,
                args=(SIAT_ARQUIVO_PATH,),
                daemon=True,
            )
            thread.start()

    def _carregar_indice(self, filepath):
        import logging

        try:
            from core import siat_index

            siat_index.carregar_indice(filepath)
        except MemoryError:
            logging.getLogger(__name__).error(
                "Memória insuficiente para carregar índice SIAT completo. "
                "Busca por logradouro usará fallback de streaming."
            )
        except Exception as e:
            logging.getLogger(__name__).error(f"Erro ao carregar índice SIAT: {e}")
