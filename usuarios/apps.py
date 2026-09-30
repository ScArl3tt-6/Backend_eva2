# ============================================================
# usuarios/apps.py — CONFIGURACIÓN DE LA APLICACIÓN USUARIOS
# Responsabilidad: registrar la app y, sobre todo, conectar las
# señales al arrancar Django. Sin el método ready() la señal que
# crea el carro de cada cliente nunca se ejecutaría.
# ============================================================

from django.apps import AppConfig


class UsuariosConfig(AppConfig):
    """Aplicación de usuarios, roles y autenticación JWT."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "usuarios"
    verbose_name = "Usuarios y roles"

    # ============================================================
    # BLOQUE 1 — REGISTRO DE SEÑALES
    # Se importa usuarios.signals aquí (no en models.py) porque es
    # el punto que Django garantiza ejecutar una sola vez, ya
    # cargado el registro de modelos.
    # ============================================================
    def ready(self):
        """Conecta las señales post_save que crean el carro del cliente."""
        from . import signals  # noqa: F401  (el import produce el registro)
