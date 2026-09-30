# ============================================================
# ordenes/apps.py — CONFIGURACIÓN DE LA APLICACIÓN ORDENES
# Responsabilidad: checkout con precios congelados, pago con
# descuento atómico de stock y máquina de estados de la orden.
# ============================================================

from django.apps import AppConfig


class OrdenesConfig(AppConfig):
    """Aplicación «Órdenes de compra»."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "ordenes"
    verbose_name = "Órdenes de compra"
