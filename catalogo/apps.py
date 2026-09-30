# ============================================================
# catalogo/apps.py — CONFIGURACIÓN DE LA APLICACIÓN CATALOGO
# Responsabilidad: categorías, marcas y productos, con su API
# REST filtrable y sus pantallas HTML de gestión.
# ============================================================

from django.apps import AppConfig


class CatalogoConfig(AppConfig):
    """Aplicación «Catálogo de componentes»."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "catalogo"
    verbose_name = "Catálogo de componentes"
