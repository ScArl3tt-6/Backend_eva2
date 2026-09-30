# ============================================================
# core/urls.py — RUTAS TRANSVERSALES
# Responsabilidad: portada, panel de gestión, documentación del
# sistema, raíz de la API y pantalla de redirección.
#
# La ruta "redireccion/" tiene nombre propio porque el helper
# obtener_o_redirigir() la usa como destino cuando un registro no
# existe, en lugar de lanzar un 404.
# ============================================================

from django.urls import path

from . import views

app_name = "core"

# ============================================================
# BLOQUE 1 — PANTALLAS HTML TRANSVERSALES
# ============================================================
urlpatterns_html = [
    path("", views.inicio, name="inicio"),
    path("panel/", views.panel, name="panel"),
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
