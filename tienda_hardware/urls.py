# ============================================================
# tienda_hardware/urls.py — ENRUTADO RAÍZ DEL PROYECTO
# Responsabilidad: montar la API REST, la documentación OpenAPI,
# las pantallas HTML y —muy importante— el control total de las
# rutas inexistentes.
#
# Requisito crítico de la pauta: ninguna dirección debe mostrar la
# página 404 de Django. Se implementan tres capas:
#
#   CAPA 1 — el catch-all re_path(r"^.*$") del final de este
#            archivo atrapa cualquier dirección que no coincida con
#            ninguna ruta y la envía a la pantalla de redirección.
#            Va después de TODO, incluidas las rutas de estáticos.
#   CAPA 2 — handler404 = "core.views.pagina_no_encontrada", que
#            actúa cuando DEBUG = False.
#   CAPA 3 — core.middleware.RedireccionNoEncontradaMiddleware,
#            declarado en settings.py, que atrapa los Http404
#            lanzados dentro de una vista incluso con DEBUG = True.
#
# El orden de los bloques de este archivo no es decorativo: define
# qué ruta gana cuando dos podrían coincidir.
# ============================================================

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path, re_path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from carro import urls as carro_urls
from catalogo import urls as catalogo_urls
from core import urls as core_urls
from core.views import redireccion_inicio
from ordenes import urls as ordenes_urls
from pagos import urls as pagos_urls
from usuarios import urls as usuarios_urls

# ============================================================
# BLOQUE 1 — RUTAS DE LA API REST
# Se concatenan las listas urlpatterns de cada aplicación y se
# montan bajo /api/. core va primero para que GET /api/ devuelva el
# índice de endpoints del proyecto.
# ============================================================
rutas_api = (
    core_urls.urlpatterns
    + usuarios_urls.urlpatterns
    + catalogo_urls.urlpatterns
    + carro_urls.urlpatterns
    + ordenes_urls.urlpatterns
)


# ============================================================
# BLOQUE 2 — RUTAS DE LAS PANTALLAS HTML
# Se montan en la raíz del sitio. core aporta la portada, el panel
# y la documentación; las demás aportan sus módulos de gestión.
# El espacio de nombres "core" permite que el helper
# obtener_o_redirigir() use reverse("core:redireccion").
# ============================================================
rutas_html = (
    catalogo_urls.urlpatterns_html
    + carro_urls.urlpatterns_html
    + ordenes_urls.urlpatterns_html
    + usuarios_urls.urlpatterns_html
    + pagos_urls.urlpatterns_html
)


urlpatterns = [
    # ============================================================
    # BLOQUE 3 — DOCUMENTACIÓN OpenAPI 3
    # /api/schema/ entrega el esquema; /api/docs/ es Swagger UI con
    # el botón Authorize operativo; /api/redoc/ es ReDoc. Ambas
    # interfaces usan una plantilla propia que añade el footer con
    # los datos de la alumna.
    # ============================================================
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema",
            template_name="drf_spectacular/swagger_ui_hardpoint.html",
        ),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(
            url_name="schema",
            template_name="drf_spectacular/redoc_hardpoint.html",
        ),
        name="redoc",
    ),
    # ============================================================
    # BLOQUE 4 — API REST Y ADMIN DE DJANGO
    # El admin queda registrado como apoyo del criterio "Django
    # Admin" de la unidad; no forma parte de la demostración ni se
    # enlaza desde la interfaz.
    # ============================================================
    path("api/", include((rutas_api, "api"))),
    path("admin/", admin.site.urls),
    # ============================================================
    # BLOQUE 5 — PANTALLAS HTML
    # ============================================================
    *rutas_html,
    path("", include((core_urls.urlpatterns_html, "core"))),
]


# ============================================================
# BLOQUE 6 — ARCHIVOS ESTÁTICOS Y MEDIA
# Se declaran ANTES del catch-all; si estuvieran después, el
# catch-all se quedaría con /static/... y la hoja de estilos nunca
# llegaría al navegador.
# ============================================================
urlpatterns += staticfiles_urlpatterns()
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


# ============================================================
# BLOQUE 7 — CAPA 1: CATCH-ALL DE RUTAS INEXISTENTES
# Debe ser la ÚLTIMA ruta del proyecto. Cualquier dirección que no
# haya coincidido antes (/asdf, /api/xyz, /%%%, /catalogo/abc/...)
# termina en la pantalla de redirección, con su cuenta regresiva de
# 3 segundos y su botón «Volver al inicio».
#
# Nota fina: este catch-all anula el comportamiento de APPEND_SLASH,
# porque atrapa la dirección antes de que Django intente agregar la
# barra final. Por eso la vista redireccion_inicio comprueba con
# resolve() si la misma ruta existe con barra y, en ese caso,
# redirige a ella (por ejemplo /catalogo → /catalogo/).
# ============================================================
urlpatterns += [
    re_path(r"^.*$", redireccion_inicio, name="redireccion"),
]


# ============================================================
# BLOQUE 8 — CAPA 2: HANDLER 404
# Entra en acción con DEBUG = False y reutiliza la misma pantalla,
# para que la experiencia sea idéntica en desarrollo y producción.
# ============================================================
handler404 = "core.views.pagina_no_encontrada"
