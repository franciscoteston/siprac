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
        from core import siat_index

        siat_index.carregar_indice(filepath)
