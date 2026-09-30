# ============================================================
# tienda_hardware/wsgi.py — PUNTO DE ENTRADA WSGI
# Responsabilidad: exponer la aplicación para un servidor WSGI
# (Gunicorn, uWSGI o mod_wsgi) cuando el proyecto se despliega en
# producción. En desarrollo no se usa: "manage.py runserver" monta
# su propio servidor.
#
# Al importar el paquete tienda_hardware se ejecuta su __init__.py,
# que deja listo el driver de PostgreSQL antes de que Django abra
# la primera conexión.
# ============================================================

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tienda_hardware.settings")

application = get_wsgi_application()
