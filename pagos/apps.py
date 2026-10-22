# ============================================================
# pagos/apps.py — CONFIGURACIÓN DE LA APLICACIÓN PAGOS
# Responsabilidad: integración con pasarelas de pago externas.
# Hoy solo Transbank Webpay Plus, en ambiente de integración.
# ============================================================

from django.apps import AppConfig


class PagosConfig(AppConfig):
    """Aplicación «Pagos»."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "pagos"
    verbose_name = "Pagos"
