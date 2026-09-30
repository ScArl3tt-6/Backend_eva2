# ============================================================
# usuarios/permisos.py — PERMISOS REUTILIZABLES POR ROL
# Responsabilidad: implementar la matriz de roles de la pauta en
# un solo lugar, para que ninguna vista repita comprobaciones.
#
# Matriz exigida:
#   PÚBLICO        → GET /api/productos/, GET /api/categorias/
#   CLIENTE        → GET/POST/DELETE /api/carro/,
#                    POST /api/ordenes/checkout/, GET /api/mis-ordenes/
#   ADMINISTRADOR  → POST/PUT/DELETE /api/productos/,
#                    PATCH /api/ordenes/{id}/estado/
#
# Criterio de verificación (defensa en profundidad): se exige que
# coincidan el claim "rol" del token firmado Y el rol guardado en
# la base de datos, además de que la cuenta siga activa. Así, si un
# administrador es degradado o desactivado, su token vigente deja
# de tener efecto sin esperar a que expire.
#
# Respuestas esperadas: sin token → 401 (lo produce la capa de
# autenticación); con token de rol incorrecto → 403.
# ============================================================

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Rol


# ============================================================
# BLOQUE 1 — COMPROBACIÓN COMÚN DE ROL
# Función de apoyo usada por los permisos concretos. Lee el claim
# del token cuando está disponible (request.auth es el token
# decodificado con JWTAuthentication) y lo compara con la base.
# ============================================================
def _tiene_rol(request, rol_esperado: str) -> bool:
    """True si el usuario autenticado y su token corresponden al rol pedido."""
    usuario = getattr(request, "user", None)

    if usuario is None or not usuario.is_authenticated or not usuario.is_active:
        return False

    # El rol guardado en la base de datos es la fuente de verdad.
    if usuario.rol != rol_esperado:
        return False

    # Si la petición llegó con un token JWT, su claim debe concordar.
    token = getattr(request, "auth", None)
    if token is not None and hasattr(token, "get"):
        rol_del_token = token.get("rol")
        if rol_del_token is not None and rol_del_token != rol_esperado:
            return False

    return True


# ============================================================
# BLOQUE 2 — SOLO ADMINISTRADOR DE TI
# Protege la gestión del catálogo (crear, editar y dar de baja
# productos, categorías y marcas), la administración de usuarios y
# el cambio de estado de las órdenes.
# ============================================================
class EsAdministrador(BasePermission):
    """Concede acceso únicamente al Administrador de TI."""

    message = "Solo un Administrador de TI puede realizar esta acción."

    def has_permission(self, request, view) -> bool:
        """Verifica el rol ADMINISTRADOR en el token y en la base de datos."""
        return _tiene_rol(request, Rol.ADMINISTRADOR)


# ============================================================
# BLOQUE 3 — SOLO CLIENTE
# Protege el carro de compras, el checkout, el pago y la consulta
# de las órdenes propias. Un administrador no tiene carro: su rol
# es gestionar, no comprar.
# ============================================================
class EsCliente(BasePermission):
    """Concede acceso únicamente a usuarios con rol CLIENTE."""

    message = "Esta acción está reservada a los clientes de la tienda."

    def has_permission(self, request, view) -> bool:
        """Verifica el rol CLIENTE en el token y en la base de datos."""
        return _tiene_rol(request, Rol.CLIENTE)


# ============================================================
# BLOQUE 4 — LECTURA PÚBLICA, ESCRITURA SOLO DEL ADMINISTRADOR
# Es el permiso del catálogo: cualquier visitante puede consultar
# productos y categorías sin token (GET, HEAD, OPTIONS), pero
# crear, modificar o dar de baja exige rol ADMINISTRADOR.
# ============================================================
class EsAdministradorOSoloLectura(BasePermission):
    """Lectura abierta a todos; escritura reservada al administrador."""

    message = "Solo un Administrador de TI puede modificar el catálogo."

    def has_permission(self, request, view) -> bool:
        """Permite los métodos seguros a cualquiera y el resto al administrador."""
        if request.method in SAFE_METHODS:
            return True
        return _tiene_rol(request, Rol.ADMINISTRADOR)


# ============================================================
# BLOQUE 5 — PROPIETARIO DE LA ORDEN (PERMISO DE OBJETO)
# Garantiza que un cliente jamás vea ni pague la orden de otro:
# se compara el dueño de la orden con el usuario autenticado. El
# administrador queda habilitado porque su rol es supervisar todas
# las ventas.
# ============================================================
class EsPropietarioDeLaOrden(BasePermission):
    """Autoriza solo al dueño de la orden (o al administrador)."""

    message = "Esta orden pertenece a otro cliente."

    def has_object_permission(self, request, view, obj) -> bool:
        """Compara el usuario de la orden con quien hace la petición."""
        usuario = request.user
        if not usuario.is_authenticated:
            return False
        if usuario.es_administrador:
            return True
        return obj.usuario_id == usuario.id
