# ============================================================
# tienda_hardware/asgi.py — PUNTO DE ENTRADA ASGI
# Responsabilidad: exponer la aplicación para un servidor ASGI
# (Uvicorn o Daphne), la vía moderna de despliegue de Django y la
# que haría falta si en el futuro se agregaran WebSockets.
#
# El proyecto actual es por completo sincrónico, así que en la
# práctica se sirve con WSGI; este archivo se conserva porque es la
# puerta de entrada estándar y no cuesta nada dejarla lista.
# ============================================================

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tienda_hardware.settings")

application = get_asgi_application()
