# ============================================================
# carro/apps.py — CONFIGURACIÓN DE LA APLICACIÓN CARRO
# Responsabilidad: carro de compras persistente en PostgreSQL,
# ligado 1 a 1 al usuario.
# ============================================================

from django.apps import AppConfig


class CarroConfig(AppConfig):
    """Aplicación «Carro de compras»."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "carro"
    verbose_name = "Carro de compras"
