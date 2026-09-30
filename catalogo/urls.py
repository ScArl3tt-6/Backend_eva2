# ============================================================
# catalogo/urls.py — RUTAS DEL CATÁLOGO (API Y HTML)
# Responsabilidad: publicar el CRUD de categorías, marcas y
# productos por dos vías.
#
# El módulo expone dos listas:
#   · urlpatterns       → API REST, se monta bajo /api/
#   · urlpatterns_html  → pantallas HTML, se montan en la raíz
# El urls.py del proyecto incluye cada lista donde corresponde.
# ============================================================

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views_html
from .views import CategoriaViewSet, MarcaViewSet, ProductoViewSet

# ============================================================
# BLOQUE 1 — ROUTER DE LA API
# Genera para cada entidad:
#   GET/POST              /api/<entidad>/
#   GET/PUT/PATCH/DELETE  /api/<entidad>/{id}/
#   POST                  /api/<entidad>/{id}/reactivar/
# ============================================================
router = SimpleRouter()
router.register("categorias", CategoriaViewSet, basename="categoria")
router.register("marcas", MarcaViewSet, basename="marca")
router.register("productos", ProductoViewSet, basename="producto")

urlpatterns = [path("", include(router.urls))]


# ============================================================
# BLOQUE 2 — PANTALLAS PÚBLICAS DEL CATÁLOGO
# /catalogo/ con filtros y paginación, y /catalogo/<id>/ con la
# ficha completa del componente.
# ============================================================
urlpatterns_html = [
    path("catalogo/", views_html.catalogo_publico, name="catalogo"),
    path("catalogo/<int:producto_id>/", views_html.detalle_publico, name="catalogo-detalle"),
]


# ============================================================
# BLOQUE 3 — PANTALLAS DE GESTIÓN
# Cada entidad tiene el mismo juego de rutas: listar, crear, ver,
# editar, desactivar (con confirmación) y reactivar.
# El orden importa: "nueva/" y "nuevo/" se declaran antes de
# "<int:objeto_id>/" para que no se interpreten como un id.
# ============================================================
urlpatterns_html += [
    # --- Categorías ---
    path("panel/categorias/", views_html.categorias_lista, name="panel-categorias"),
    path("panel/categorias/nueva/", views_html.categoria_crear, name="panel-categoria-crear"),
    path("panel/categorias/<int:objeto_id>/", views_html.categoria_detalle, name="panel-categoria-detalle"),
    path("panel/categorias/<int:objeto_id>/editar/", views_html.categoria_editar, name="panel-categoria-editar"),
    path("panel/categorias/<int:objeto_id>/desactivar/", views_html.categoria_desactivar, name="panel-categoria-desactivar"),
    path("panel/categorias/<int:objeto_id>/reactivar/", views_html.categoria_reactivar, name="panel-categoria-reactivar"),
    # --- Marcas ---
    path("panel/marcas/", views_html.marcas_lista, name="panel-marcas"),
    path("panel/marcas/nueva/", views_html.marca_crear, name="panel-marca-crear"),
    path("panel/marcas/<int:objeto_id>/", views_html.marca_detalle, name="panel-marca-detalle"),
    path("panel/marcas/<int:objeto_id>/editar/", views_html.marca_editar, name="panel-marca-editar"),
    path("panel/marcas/<int:objeto_id>/desactivar/", views_html.marca_desactivar, name="panel-marca-desactivar"),
    path("panel/marcas/<int:objeto_id>/reactivar/", views_html.marca_reactivar, name="panel-marca-reactivar"),
    # --- Productos ---
    path("panel/productos/", views_html.productos_lista, name="panel-productos"),
    path("panel/productos/nuevo/", views_html.producto_crear, name="panel-producto-crear"),
    path("panel/productos/<int:objeto_id>/", views_html.producto_detalle, name="panel-producto-detalle"),
    path("panel/productos/<int:objeto_id>/editar/", views_html.producto_editar, name="panel-producto-editar"),
    path("panel/productos/<int:objeto_id>/desactivar/", views_html.producto_desactivar, name="panel-producto-desactivar"),
    path("panel/productos/<int:objeto_id>/reactivar/", views_html.producto_reactivar, name="panel-producto-reactivar"),
]
