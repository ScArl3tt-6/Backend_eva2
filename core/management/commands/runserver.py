# ============================================================
# core/management/commands/runserver.py — RUNSERVER PROPIO
# Responsabilidad: cerrar el último hueco por el que todavía se
# escapaba la página 404 de Django: los archivos estáticos.
#
# El problema: el runserver de django.contrib.staticfiles envuelve
# la aplicación en un StaticFilesHandler que atiende todo lo que
# empiece por STATIC_URL ANTES de que Django resuelva la URL. Por
# eso una dirección como /static/noexiste.css nunca llegaba al
# middleware del proyecto ni al catch-all de urls.py, y terminaba
# mostrando el 404 de Django.
#
# La solución: se hereda de ese mismo comando y se sustituye el
# manejador por uno que, cuando el archivo no existe, devuelve la
# pantalla de redirección del proyecto en lugar del 404.
#
# Para que este comando tenga prioridad sobre el de staticfiles,
# la aplicación "core" está declarada ANTES de
# django.contrib.staticfiles en INSTALLED_APPS: Django resuelve los
# comandos recorriendo esa lista al revés, así que gana el primero.
#
# Los archivos estáticos que SÍ existen se siguen sirviendo con el
# mecanismo normal de staticfiles: solo cambia el caso del archivo
# ausente.
# ============================================================

from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.contrib.staticfiles.management.commands.runserver import (
    Command as ComandoRunserverStaticfiles,
)
from django.http import Http404


# ============================================================
# BLOQUE 1 — MANEJADOR DE ESTÁTICOS CON REDIRECCIÓN
# Solo interviene en el camino de error. Si el archivo existe, la
# respuesta la produce tal cual la clase de Django.
# ============================================================
class ManejadorEstaticosConRedireccion(StaticFilesHandler):
    """Sirve los archivos estáticos y, si faltan, muestra la pantalla de aviso."""

    def get_response(self, request):
        """Devuelve el archivo pedido o la pantalla de redirección del proyecto."""
        try:
            return self.serve(request)
        except Http404:
            # Importación diferida: al cargarse este módulo, el registro
            # de aplicaciones de Django todavía puede estar a medio armar.
            from core.views import redireccion_inicio

            return redireccion_inicio(request)


# ============================================================
# BLOQUE 2 — COMANDO runserver
# Hereda todo el comportamiento del runserver de staticfiles
# (recarga automática, opción --nostatic, comprobaciones previas) y
# solo cambia la clase del manejador.
# ============================================================
class Command(ComandoRunserverStaticfiles):
    """runserver del proyecto: igual que el de Django, sin páginas 404."""

    help = (
        "Levanta el servidor de desarrollo. Igual que el runserver de Django, "
        "pero un archivo estático inexistente muestra la pantalla de redirección "
        "del proyecto en lugar de la página 404."
    )

    def get_handler(self, *args, **opciones):
        """Envuelve la aplicación con el manejador de estáticos propio."""
        manejador = super().get_handler(*args, **opciones)

        # super() devuelve un StaticFilesHandler cuando corresponde servir
        # estáticos (DEBUG activo y sin --nostatic). En ese caso se
        # reemplaza por el del proyecto, conservando la aplicación interna.
        if isinstance(manejador, StaticFilesHandler):
            return ManejadorEstaticosConRedireccion(manejador.application)

        return manejador
