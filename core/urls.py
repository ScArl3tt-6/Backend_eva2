# ============================================================
# core/urls.py — RUTAS TRANSVERSALES
# Responsabilidad: portada, panel de gestión, documentación del
# sistema, raíz de la API y pantalla de redirección.
#
# La ruta "redireccion/" tiene nombre propio porque el helper
# obtener_o_redirigir() la usa como destino cuando un registro no
# existe, en lugar de lanzar un 404.
# ============================================================

from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "core"

# ============================================================
# BLOQUE 1 — PANTALLAS HTML TRANSVERSALES
# panel/login/ y panel/logout/ son sesión de Django (cookies), no
# JWT: habilitan la escritura en el panel de gestión, que se puede
# seguir viendo sin iniciar sesión. El logout es por POST porque
# Django 5 ya no admite GET en LogoutView (evita cerrar la sesión
# de otro con un simple enlace, que sería un CSRF de logout).
# ============================================================
urlpatterns_html = [
    path("", views.inicio, name="inicio"),
    path("panel/", views.panel, name="panel"),
    path("panel/login/", views.PanelLoginView.as_view(), name="panel-login"),
    path(
        "panel/logout/",
        LogoutView.as_view(next_page="core:inicio"),
        name="panel-logout",
    ),
    path("documentacion/", views.documentacion, name="documentacion"),
    path("redireccion/", views.redireccion_inicio, name="redireccion"),
]


# ============================================================
# BLOQUE 2 — RAÍZ DE LA API
# GET /api/ público con el índice de endpoints y los datos de la
# alumna.
# ============================================================
urlpatterns = [
    path("", views.RaizApiView.as_view(), name="raiz-api"),
]
