# ============================================================
# core/nombres.py — NOMBRES DE LAS VISTAS EN LA API NAVEGABLE
# Responsabilidad: que la Browsable API de DRF muestre títulos en
# español correcto.
#
# El problema que resuelve: por omisión, DRF arma el título a partir
# del nombre de la clase en Python. Así, ProductoViewSet aparecía
# como «Producto List» —mitad español, mitad inglés— y RaizApiView
# como «Raiz Api», sin la tilde. Son textos que ve cualquier
# visitante, así que se traducen aquí.
#
# Se registra en REST_FRAMEWORK["VIEW_NAME_FUNCTION"]. La
# descripción de cada vista no hace falta traducirla: DRF la toma
# del docstring de la clase, que ya está en español.
# ============================================================

from rest_framework.views import get_view_name as nombre_por_omision

# ============================================================
# BLOQUE 1 — TÍTULO DE CADA VISTA
# La clave es el nombre de la clase; el valor, el título que se
# muestra. Si una clase no está en el diccionario, se usa el
# comportamiento estándar de DRF, de modo que nada se rompe al
# agregar una vista nueva.
# ============================================================
NOMBRES_DE_VISTA = {
    # --- General ---
    "RaizApiView": "Índice de la API",
    # --- Autenticación ---
    "RegistroView": "Registro de cliente",
    "LoginConRolView": "Inicio de sesión",
    "RefrescarTokenView": "Renovación del token",
    "LogoutView": "Cierre de sesión",
    "PerfilView": "Perfil y claims del token",
    # --- Catálogo ---
    "CategoriaViewSet": "Categorías",
    "MarcaViewSet": "Marcas",
    "ProductoViewSet": "Productos",
    # --- Carro ---
    "CarroView": "Carro de compras",
    "ItemCarroView": "Ítem del carro",
    # --- Órdenes ---
    "CheckoutView": "Checkout del carro",
    "PagarOrdenView": "Pago de la orden",
    "MisOrdenesViewSet": "Mis órdenes",
    "OrdenAdminViewSet": "Órdenes",
    # --- Usuarios ---
    "UsuarioViewSet": "Usuarios",
}


# ============================================================
# BLOQUE 2 — SUFIJO SEGÚN LA ACCIÓN
# Los routers de DRF marcan cada ruta con un sufijo ("List" para el
# listado, "Instance" para el detalle). Se traducen para que el
# título quede, por ejemplo, «Productos · listado».
# ============================================================
SUFIJOS = {
    "List": "listado",
    "Instance": "detalle",
}


def nombre_de_vista(view) -> str:
    """Devuelve el título en español de una vista de la API navegable."""
    nombre = NOMBRES_DE_VISTA.get(view.__class__.__name__)

    if nombre is None:
        # Vista no registrada: se conserva el comportamiento de DRF.
        return nombre_por_omision(view)

    sufijo = getattr(view, "suffix", None)
    if sufijo:
        return f"{nombre} · {SUFIJOS.get(sufijo, sufijo.lower())}"

    return nombre
