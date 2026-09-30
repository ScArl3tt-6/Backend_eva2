# ============================================================
# carro/urls.py — RUTAS DEL CARRO (API Y HTML)
# Responsabilidad: publicar el carro del cliente por la API y la
# pantalla de gestión de carros.
#
# En la API el carro NO se direcciona por id: siempre es el del
# usuario del token, de modo que un cliente no pueda apuntar al
# carro de otro. Los ítems se direccionan por producto_id, que es
# el dato que el cliente conoce desde el catálogo.
# ============================================================

from django.urls import path

from . import views_html
from .views import CarroView, ItemCarroView

# ============================================================
# BLOQUE 1 — API DEL CARRO
# ============================================================
urlpatterns = [
    # GET ver el carro, POST agregar un producto, DELETE vaciarlo
    path("carro/", CarroView.as_view(), name="carro"),
    # PATCH cambiar la cantidad, DELETE quitar el ítem
    path("carro/items/<int:producto_id>/", ItemCarroView.as_view(), name="item-carro"),
]


# ============================================================
# BLOQUE 2 — PANTALLA DE GESTIÓN DE CARROS
# El cliente cuyo carro se opera llega en ?usuario=<id>. Las
# acciones son POST para que no se ejecuten al recargar con GET.
# ============================================================
urlpatterns_html = [
    path("panel/carros/", views_html.carros_panel, name="panel-carros"),
    path("panel/carros/agregar/", views_html.carro_agregar, name="panel-carro-agregar"),
    path(
        "panel/carros/actualizar/<int:producto_id>/",
        views_html.carro_actualizar,
        name="panel-carro-actualizar",
    ),
    path(
        "panel/carros/quitar/<int:producto_id>/",
        views_html.carro_quitar,
        name="panel-carro-quitar",
    ),
    path("panel/carros/vaciar/", views_html.carro_vaciar, name="panel-carro-vaciar"),
    path("panel/carros/checkout/", views_html.carro_checkout, name="panel-carro-checkout"),
]
