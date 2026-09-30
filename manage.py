#!/usr/bin/env python
# ============================================================
# manage.py — PUNTO DE ENTRADA DE LAS TAREAS DE DJANGO
# Responsabilidad: ejecutar los comandos de gestión del proyecto
# (migrate, runserver, test, seed_data, simular_concurrencia...).
#
# Además del arranque estándar de Django, incluye un bloque propio
# que fuerza la salida de la consola a UTF-8. Es necesario en
# Windows: PowerShell y cmd usan por omisión la página de códigos
# cp1252, que no puede mostrar tildes, ñ ni flechas, y los comandos
# de este proyecto imprimen mensajes en español.
# ============================================================

import os
import sys


# ============================================================
# BLOQUE 1 — SALIDA DE CONSOLA EN UTF-8
# Sin esto, "python manage.py seed_data" falla en Windows con
# UnicodeEncodeError al imprimir «Catálogo» o «→».
# ============================================================
def configurar_consola_utf8():
    """Reconfigura la salida estándar a UTF-8 para los mensajes en español."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # En entornos donde la salida no se puede reconfigurar (por
            # ejemplo si está redirigida a un archivo ya abierto en otro
            # modo), se continúa sin cambios: no es un error fatal.
            pass


# ============================================================
# BLOQUE 2 — ARRANQUE DE DJANGO
# ============================================================
def main():
    """Prepara el entorno y delega en el gestor de comandos de Django."""
    configurar_consola_utf8()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tienda_hardware.settings")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. ¿Está instalado y activado el entorno "
            "virtual? Active el entorno con: .\\.venv\\Scripts\\Activate.ps1 "
            "e instale las dependencias con: pip install -r requirements.txt"
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
