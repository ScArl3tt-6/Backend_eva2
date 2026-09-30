# ============================================================
# usuarios/urls.py — RUTAS DE AUTENTICACIÓN Y USUARIOS
# Responsabilidad: publicar el ciclo de autenticación JWT bajo
# /api/auth/, el CRUD de usuarios bajo /api/usuarios/ y las
# pantallas de gestión de usuarios del panel.
# ============================================================

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views_html
from .views import (
    LoginConRolView,
    LogoutView,
    PerfilView,
    RefrescarTokenView,
    RegistroView,
    UsuarioViewSet,
)

# ============================================================
# BLOQUE 1 — ROUTER DEL CRUD DE USUARIOS
# Genera /api/usuarios/, /api/usuarios/{id}/,
# /api/usuarios/{id}/reactivar/ y /api/usuarios/{id}/carro/.
# ============================================================
router = SimpleRouter()
router.register("usuarios", UsuarioViewSet, basename="usuario")


# ============================================================
# BLOQUE 2 — RUTAS DE AUTENTICACIÓN
# Orden deliberado: primero las rutas de /api/auth/ y después las
# del router, para que ninguna capture a la otra.
# ============================================================
urlpatterns = [
    path("auth/registro/", RegistroView.as_view(), name="registro"),
    path("auth/login/", LoginConRolView.as_view(), name="login"),
    path("auth/refresh/", RefrescarTokenView.as_view(), name="refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/perfil/", PerfilView.as_view(), name="perfil"),
    path("", include(router.urls)),
]


# ============================================================
# BLOQUE 3 — PANTALLAS DE GESTIÓN DE USUARIOS
# "nuevo/" se declara antes de "<int:objeto_id>/" para que no se
# interprete como un identificador.
# ============================================================
urlpatterns_html = [
    path("panel/usuarios/", views_html.usuarios_lista, name="panel-usuarios"),
    path("panel/usuarios/nuevo/", views_html.usuario_formulario, name="panel-usuario-crear"),
    path(
        "panel/usuarios/<int:objeto_id>/",
        views_html.usuario_detalle,
        name="panel-usuario-detalle",
    ),
    path(
        "panel/usuarios/<int:objeto_id>/editar/",
        views_html.usuario_formulario,
        name="panel-usuario-editar",
    ),
    path(
        "panel/usuarios/<int:objeto_id>/desactivar/",
        views_html.usuario_desactivar,
        name="panel-usuario-desactivar",
    ),
    path(
        "panel/usuarios/<int:objeto_id>/reactivar/",
        views_html.usuario_reactivar,
        name="panel-usuario-reactivar",
    ),
]
