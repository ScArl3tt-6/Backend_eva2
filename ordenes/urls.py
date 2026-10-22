# ============================================================
# ordenes/urls.py — RUTAS DE ÓRDENES (API Y HTML)
# Responsabilidad: publicar el flujo de compra del cliente, la
# supervisión del administrador y las pantallas de gestión.
#
# Orden deliberado de las rutas de la API: "checkout" y "pagar" se
# declaran ANTES del router, para que "checkout" no se interprete
# como el id de una orden dentro de /api/ordenes/{id}/.
# ============================================================

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views_html
from .views import (
    CheckoutView,
    MisOrdenesViewSet,
    OrdenAdminViewSet,
    PagarOrdenView,
    WebpayIniciarView,
)

# ============================================================
# BLOQUE 1 — ROUTERS DE LA API
# mis-ordenes → solo las órdenes del cliente autenticado.
# ordenes     → todas las órdenes, solo para el administrador,
#               incluida la acción PATCH /api/ordenes/{id}/estado/.
# ============================================================
router = SimpleRouter()
router.register("mis-ordenes", MisOrdenesViewSet, basename="mi-orden")
router.register("ordenes", OrdenAdminViewSet, basename="orden")

urlpatterns = [
    path("ordenes/checkout/", CheckoutView.as_view(), name="checkout"),
    path("ordenes/<int:pk>/pagar/", PagarOrdenView.as_view(), name="pagar-orden"),
    path("ordenes/<int:pk>/webpay/iniciar/", WebpayIniciarView.as_view(), name="webpay-iniciar-orden"),
    path("", include(router.urls)),
]


# ============================================================
# BLOQUE 2 — PANTALLAS DE GESTIÓN DE ÓRDENES
# Listado con filtros, ficha con el detalle y el historial, y las
# acciones de pago y de cambio de estado (siempre por POST).
# ============================================================
urlpatterns_html = [
    path("panel/ordenes/", views_html.ordenes_lista, name="panel-ordenes"),
    path(
        "panel/ordenes/<int:objeto_id>/",
        views_html.orden_detalle,
        name="panel-orden-detalle",
    ),
    path(
        "panel/ordenes/<int:objeto_id>/pagar/",
        views_html.orden_pagar,
        name="panel-orden-pagar",
    ),
    path(
        "panel/ordenes/<int:objeto_id>/webpay/iniciar/",
        views_html.orden_pagar_con_webpay,
        name="panel-orden-webpay-iniciar",
    ),
    path(
        "panel/ordenes/<int:objeto_id>/estado/",
        views_html.orden_cambiar_estado,
        name="panel-orden-estado",
    ),
]
