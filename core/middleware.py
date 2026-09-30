# ============================================================
# core/middleware.py — CONTROL DE RUTAS INEXISTENTES (CAPA 3)
# Responsabilidad: impedir que el usuario vea alguna vez la página
# 404 de Django o una traza de error.
#
# El proyecto protege las rutas inexistentes con tres capas:
#   Capa 1 — catch-all re_path(r"^.*$") al final de urls.py, que
#            atrapa cualquier dirección que no coincida con nada.
#   Capa 2 — handler404 = "core.views.pagina_no_encontrada", que
#            actúa cuando DEBUG = False.
#   Capa 3 — ESTE middleware, que atrapa los Http404 lanzados
#            DENTRO de una vista (por ejemplo un id que no existe)
#            y también cualquier respuesta 404 ya construida, aun
#            con DEBUG = True, situación en la que handler404 no
#            se aplica.
#
# Las rutas de la API quedan fuera a propósito: allí el formato
# correcto es el JSON uniforme de core/excepciones.py, no una
# pantalla HTML.
# ============================================================

from django.http import Http404

# Prefijos que NO se redirigen a la pantalla HTML porque deben
# responder en JSON (API) o son herramientas de Django.
PREFIJOS_EXCLUIDOS = ("/api/", "/admin/", "/static/", "/media/")


class RedireccionNoEncontradaMiddleware:
    """Convierte cualquier 404 de una vista HTML en la pantalla de redirección."""

    def __init__(self, get_response):
        """Guarda la siguiente capa de la cadena de middleware."""
        self.get_response = get_response

    # ============================================================
    # BLOQUE 1 — REVISIÓN DE LA RESPUESTA YA CONSTRUIDA
    # Si una vista devolvió 404 (sin lanzar excepción), se sustituye
    # la respuesta por la pantalla de redirección del proyecto.
    # ============================================================
    def __call__(self, request):
        """Intercepta las respuestas 404 de las pantallas HTML."""
        respuesta = self.get_response(request)

        if respuesta.status_code == 404 and self._es_ruta_html(request):
            return self._pantalla_redireccion(request)

        return respuesta

    # ============================================================
    # BLOQUE 2 — CAPTURA DE Http404 LANZADO EN LA VISTA
    # process_exception se ejecuta antes de que Django arme su
    # propia página de error, así que aquí se corta el problema de
    # raíz incluso en modo DEBUG.
    # ============================================================
    def process_exception(self, request, exception):
        """Atrapa Http404 dentro de una vista HTML y redirige con aviso."""
        if isinstance(exception, Http404) and self._es_ruta_html(request):
            return self._pantalla_redireccion(request)
        return None

    # ============================================================
    # BLOQUE 3 — APOYO
    # _es_ruta_html decide si corresponde una respuesta HTML.
    # _pantalla_redireccion delega en la vista del proyecto, que es
    # la misma que usa el catch-all, para que el usuario vea
    # siempre exactamente la misma pantalla.
    # ============================================================
    def _es_ruta_html(self, request) -> bool:
        """True si la ruta debe responder con una pantalla HTML."""
        return not request.path.startswith(PREFIJOS_EXCLUIDOS)

    def _pantalla_redireccion(self, request):
        """Renderiza la pantalla de redirección del proyecto."""
        from core.views import redireccion_inicio

        return redireccion_inicio(request)
