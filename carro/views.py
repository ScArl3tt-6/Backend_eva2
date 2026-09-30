# ============================================================
# carro/views.py — API REST DEL CARRO DE COMPRAS
# Responsabilidad: exponer el carro persistente del cliente.
#
# Matriz de roles (pauta): CLIENTE → GET/POST/DELETE /api/carro/.
# El permiso EsCliente lo garantiza: sin token la respuesta es 401
# y con token de administrador es 403, porque el administrador
# gestiona la tienda pero no compra.
#
# Endpoints:
#   GET    /api/carro/                        → ver el carro
#   POST   /api/carro/                        → agregar producto
#   DELETE /api/carro/                        → vaciar el carro
#   PATCH  /api/carro/items/{producto_id}/    → cambiar cantidad
#   DELETE /api/carro/items/{producto_id}/    → quitar un ítem
#
# Toda la lógica se delega en carro/servicios.py, el mismo módulo
# que usan las pantallas HTML.
# ============================================================

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalogo.models import Producto
from usuarios.permisos import EsCliente

from .serializers import (
    ActualizarCantidadSerializer,
    AgregarAlCarroSerializer,
    CarroSerializer,
)
from .servicios import (
    ErrorDeCarro,
    StockInsuficienteEnCarroError,
    actualizar_cantidad,
    agregar_producto,
    obtener_carro,
    quitar_producto,
    revisar_disponibilidad,
    vaciar_carro,
)


# ============================================================
# BLOQUE 1 — RESPUESTAS COMPARTIDAS
# Funciones de apoyo para que todas las operaciones del carro
# respondan con la misma estructura: un mensaje y el carro
# completo actualizado, de modo que el cliente no tenga que hacer
# una segunda petición para conocer el estado resultante.
# ============================================================
def _respuesta_carro(carro, mensaje, codigo=status.HTTP_200_OK, extras=None):
    """Arma la respuesta estándar con el estado actual del carro."""
    cuerpo = {"mensaje": mensaje, "carro": CarroSerializer(carro).data}
    if extras:
        cuerpo.update(extras)
    return Response(cuerpo, status=codigo)


def _respuesta_error_carro(error, codigo=status.HTTP_400_BAD_REQUEST):
    """Traduce una excepción del servicio al formato de error del proyecto."""
    detalle = None
    if isinstance(error, StockInsuficienteEnCarroError):
        detalle = {
            "producto": error.producto.nombre,
            "sku": error.producto.sku,
            "solicitado": error.solicitado,
            "disponible": error.disponible,
        }

    return Response(
        {"error": True, "mensaje": str(error), "detalle": detalle},
        status=codigo,
    )


# ============================================================
# BLOQUE 2 — CARRO DEL CLIENTE AUTENTICADO
# El carro se identifica por el usuario del token, nunca por un id
# recibido desde fuera: así un cliente no puede leer ni modificar
# el carro de otro.
# ============================================================
class CarroView(APIView):
    """GET, POST y DELETE sobre /api/carro/ — carro del cliente autenticado."""

    permission_classes = [EsCliente]
    serializer_class = AgregarAlCarroSerializer

    @extend_schema(
        tags=["Carro"],
        summary="Ver mi carro de compras",
        description=(
            "Devuelve los ítems vigentes del carro con el precio vigente de cada "
            "producto, el subtotal por línea, el total y la cantidad de ítems.\n\n"
            "El carro está guardado en PostgreSQL y ligado al id del usuario, así "
            "que sobrevive al cierre de sesión, al cierre del navegador y al "
            "cambio de dispositivo."
        ),
        responses={
            200: OpenApiResponse(response=CarroSerializer, description="Carro del cliente."),
            401: OpenApiResponse(description="Falta el token JWT."),
            403: OpenApiResponse(description="El rol del token no es CLIENTE."),
        },
    )
    def get(self, request):
        """Entrega el carro persistido del cliente."""
        carro = obtener_carro(request.user)
        avisos = revisar_disponibilidad(carro)

        cuerpo = CarroSerializer(carro).data
        if avisos:
            cuerpo["avisos_de_stock"] = avisos
            cuerpo["nota"] = (
                "Algunos productos ya no tienen stock suficiente. El pago se "
                "rechazará hasta que ajuste las cantidades."
            )

        return Response(cuerpo, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Carro"],
        summary="Agregar un producto al carro",
        description=(
            "Agrega un producto al carro. Si el producto ya estaba, **suma la "
            "cantidad al ítem existente** en lugar de crear otra línea (lo "
            "garantiza además el UniqueConstraint carro+producto).\n\n"
            "Esta operación **no descuenta stock**: solo valida que la cantidad "
            "pedida no supere el stock disponible. El descuento ocurre al pagar."
        ),
        request=AgregarAlCarroSerializer,
        responses={
            200: OpenApiResponse(description="Producto agregado o cantidad sumada."),
            400: OpenApiResponse(description="Producto inactivo, sin stock o cantidad mayor al stock."),
            401: OpenApiResponse(description="Falta el token JWT."),
            403: OpenApiResponse(description="El rol del token no es CLIENTE."),
        },
        examples=[
            OpenApiExample(
                "Agregar dos unidades de un producto",
                value={"producto": 1, "cantidad": 2},
                request_only=True,
            ),
            OpenApiExample(
                "Agregar una unidad",
                value={"producto": 5, "cantidad": 1},
                request_only=True,
            ),
            OpenApiExample(
                "Error por stock insuficiente",
                value={
                    "error": True,
                    "mensaje": "«Tarjeta de video NVIDIA GeForce RTX 4090 24GB»: pidió 5 unidades y solo hay 1 disponibles.",
                    "detalle": {
                        "producto": "Tarjeta de video NVIDIA GeForce RTX 4090 24GB",
                        "sku": "GPU-NVD-RTX4090",
                        "solicitado": 5,
                        "disponible": 1,
                    },
                },
                response_only=True,
                status_codes=["400"],
            ),
        ],
    )
    def post(self, request):
        """Agrega un producto al carro sumando la cantidad si ya estaba."""
        serializer = AgregarAlCarroSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        carro = obtener_carro(request.user)
        producto = serializer.validated_data["producto"]
        cantidad = serializer.validated_data["cantidad"]

        try:
            item = agregar_producto(carro, producto, cantidad)
        except ErrorDeCarro as error:
            return _respuesta_error_carro(error)

        return _respuesta_carro(
            carro,
            f"«{producto.nombre}» quedó en el carro con {item.cantidad} unidad(es).",
            extras={"stock_descontado": False, "nota": "El stock se descuenta solo al pagar la orden."},
        )

    @extend_schema(
        tags=["Carro"],
        summary="Vaciar el carro",
        description=(
            "Deja todos los ítems del carro con `activo = false` (baja lógica). "
            "Las filas se conservan en la base de datos: nada se borra."
        ),
        request=None,
        responses={
            200: OpenApiResponse(description="Carro vaciado."),
            401: OpenApiResponse(description="Falta el token JWT."),
            403: OpenApiResponse(description="El rol del token no es CLIENTE."),
        },
    )
    def delete(self, request):
        """Vacía el carro mediante baja lógica de todos sus ítems."""
        carro = obtener_carro(request.user)
        cantidad_afectada = vaciar_carro(carro)

        return _respuesta_carro(
            carro,
            f"Se quitaron {cantidad_afectada} ítem(s) del carro.",
            extras={"baja_logica": True},
        )


# ============================================================
# BLOQUE 3 — ÍTEM CONCRETO DEL CARRO
# Se direcciona por producto_id (no por el id del ítem) porque es
# lo que el cliente conoce desde el catálogo, y porque la pareja
# carro+producto es única por diseño.
# ============================================================
class ItemCarroView(APIView):
    """PATCH y DELETE sobre /api/carro/items/{producto_id}/."""

    permission_classes = [EsCliente]
    serializer_class = ActualizarCantidadSerializer

    def _obtener_producto(self, producto_id):
        """Busca el producto sin lanzar Http404, para responder JSON controlado."""
        return Producto.objects.filter(pk=producto_id).first()

    def _error_producto_inexistente(self, producto_id):
        """Respuesta JSON en español cuando el producto no existe."""
        return Response(
            {
                "error": True,
                "mensaje": f"No existe un producto con el id {producto_id}.",
                "detalle": None,
                "redireccion": "/",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    @extend_schema(
        tags=["Carro"],
        summary="Cambiar la cantidad de un producto del carro",
        description=(
            "Fija la cantidad **exacta** del producto en el carro (no la suma). "
            "Valida contra el stock disponible, sin descontarlo."
        ),
        request=ActualizarCantidadSerializer,
        responses={
            200: OpenApiResponse(description="Cantidad actualizada."),
            400: OpenApiResponse(description="Cantidad inválida o mayor al stock disponible."),
            404: OpenApiResponse(description="El producto no existe o no está en el carro."),
        },
        examples=[
            OpenApiExample("Dejar tres unidades", value={"cantidad": 3}, request_only=True),
        ],
    )
    def patch(self, request, producto_id):
        """Actualiza la cantidad exacta de un ítem del carro."""
        producto = self._obtener_producto(producto_id)
        if producto is None:
            return self._error_producto_inexistente(producto_id)

        serializer = ActualizarCantidadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        carro = obtener_carro(request.user)

        try:
            item = actualizar_cantidad(carro, producto, serializer.validated_data["cantidad"])
        except ErrorDeCarro as error:
            return _respuesta_error_carro(error)

        return _respuesta_carro(
            carro, f"«{producto.nombre}» quedó con {item.cantidad} unidad(es)."
        )

    @extend_schema(
        tags=["Carro"],
        summary="Quitar un producto del carro",
        description=(
            "Quita el producto del carro con baja lógica (`activo = false`). "
            "La fila del ítem se conserva en la base de datos."
        ),
        request=None,
        responses={
            200: OpenApiResponse(description="Producto quitado del carro."),
            404: OpenApiResponse(description="El producto no existe o no está en el carro."),
        },
    )
    def delete(self, request, producto_id):
        """Quita un ítem del carro sin borrar la fila."""
        producto = self._obtener_producto(producto_id)
        if producto is None:
            return self._error_producto_inexistente(producto_id)

        carro = obtener_carro(request.user)

        try:
            quitar_producto(carro, producto)
        except ErrorDeCarro as error:
            return _respuesta_error_carro(error, codigo=status.HTTP_404_NOT_FOUND)

        return _respuesta_carro(
            carro,
            f"«{producto.nombre}» se quitó del carro.",
            extras={"baja_logica": True},
        )
