# ============================================================
# core/apps.py — CONFIGURACIÓN DE LA APLICACIÓN CORE
# Responsabilidad: páginas transversales (inicio y documentación),
# control de rutas inexistentes, filtro de moneda chilena, context
# processors y comandos de datos de prueba.
# ============================================================

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Aplicación «Núcleo: inicio, documentación y control de rutas»."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Núcleo: inicio, documentación y control de rutas"
