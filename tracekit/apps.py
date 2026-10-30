from django.apps import AppConfig


class TracekitConfig(AppConfig):
    name = "tracekit"
    verbose_name = "Tracekit APM"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from tracekit.buffer import BufferManager

        BufferManager().start()
