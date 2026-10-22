# ============================================================
# ordenes/views.py — API REST DE ÓRDENES
# Responsabilidad: exponer el flujo de compra y la supervisión de
# las ventas, respetando la matriz de roles de la pauta.
#
#   POST  /api/ordenes/checkout/      → CLIENTE
#   POST  /api/ordenes/{id}/pagar/    → CLIENTE dueño de la orden
#   GET   /api/mis-ordenes/           → CLIENTE (solo las propias)
#   GET   /api/ordenes/               → ADMINISTRADOR (todas, filtrables)
#   PATCH /api/ordenes/{id}/estado/   → ADMINISTRADOR
#
# Ninguna vista contiene reglas de negocio: todas llaman a
# ordenes/servicios.py, que es donde vive el control de stock y la
# máquina de estados. Aquí solo se traduce cada excepción al código
# HTTP que corresponde:
#   CarroVacioError         → 400
#   StockInsuficienteError  → 409 Conflict (con el detalle faltante)
#   TransicionInvalidaError → 400
# ============================================================

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from transbank.error.transbank_error import TransbankError

from pagos.servicios import ErrorDePago, iniciar_pago_webpay
from usuarios.permisos import EsAdministrador, EsCliente, EsPropietarioDeLaOrden

from .filtros import OrdenFilter
from .models import Orden
from .serializers import (
    CambiarEstadoSerializer,
    OrdenResumenSerializer,
    OrdenSerializer,
    WebpayIniciarSerializer,
)
from .servicios import (
    CarroVacioError,
    StockInsuficienteError,
    TransicionInvalidaError,
    cambiar_estado_orden,
    pagar_orden,
    realizar_checkout,
)


# ============================================================
# BLOQUE 1 — TRADUCCIÓN DE ERRORES DE NEGOCIO A HTTP
# Un solo lugar donde se decide el código de respuesta de cada
# excepción, para que la API sea coherente en los tres endpoints
# que pueden fallar por stock o por estado.
# ============================================================
def _respuesta_stock_insuficiente(error: StockInsuficienteError):
    """409 Conflict con la lista de productos faltantes (pedido vs. disponible)."""
    return Response(
        {
            "error": True,
            "mensaje": str(error),
            "detalle": {"faltantes": error.faltantes},
            "estado_de_la_orden": "PENDIENTE",
            "nota": "No se descontó stock: la transacción se revirtió por completo.",
        },
        status=status.HTTP_409_CONFLICT,
    )


def _respuesta_error_negocio(error, codigo=status.HTTP_400_BAD_REQUEST):
    """Formato uniforme de error para el resto de las excepciones del negocio."""
    detalle = None
    if isinstance(error, TransicionInvalidaError):
        detalle = {
            "estado_actual": error.estado_actual,
            "estado_solicitado": error.estado_pedido,
            "transiciones_permitidas": error.permitidos,
        }

    return Response(
        {"error": True, "mensaje": str(error), "detalle": detalle},
        status=codigo,
    )


# ============================================================
# BLOQUE 2 — CHECKOUT
# Convierte el carro en una orden PENDIENTE con precios congelados.
# No descuenta stock, y así lo declara la respuesta, para que quede
# explícito al probar desde Swagger.
# ============================================================
@extend_schema(
    tags=["Órdenes"],
    summary="Hacer el checkout del carro y generar la orden",
    description=(
        "Convierte el carro del cliente en una **Orden de Compra** en estado "
        "`PENDIENTE`.\n\n"
        "Qué ocurre exactamente:\n"
        "1. Se bloquea el carro para impedir dos checkout simultáneos.\n"
        "2. Se copia el precio vigente de cada producto a "
        "`DetalleOrden.precio_unitario`: ese es el **precio congelado**, que ya "
        "no cambia aunque el catálogo suba de precio mañana.\n"
        "3. Se registra el historial (creación → PENDIENTE) y se vacía el carro.\n\n"
        "**No se descuenta stock.** El stock se mueve recién al pagar."
    ),
    request=None,
    responses={
        201: OpenApiResponse(response=OrdenSerializer, description="Orden creada en estado PENDIENTE."),
        400: OpenApiResponse(description="El carro está vacío."),
        409: OpenApiResponse(description="Algún producto del carro fue dado de baja del catálogo."),
        401: OpenApiResponse(description="Falta el token JWT."),
        403: OpenApiResponse(description="El rol del token no es CLIENTE."),
    },
    examples=[
        OpenApiExample(
            "Orden creada con precios congelados",
            value={
                "mensaje": "Orden creada correctamente. Los precios quedaron congelados.",
                "orden": {
                    "id": 12,
                    "codigo": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                    "codigo_corto": "7C9E6679",
                    "estado": "PENDIENTE",
                    "estado_etiqueta": "Pendiente de pago",
                    "detalles": [
                        {
                            "producto_nombre": "Procesador Intel Core i5-14600K",
                            "producto_sku": "CPU-INT-14600K",
                            "cantidad": 1,
                            "precio_unitario": 329990,
                            "subtotal": 329990,
                        }
                    ],
                    "total": 329990,
                },
                "stock_descontado": False,
            },
            response_only=True,
            status_codes=["201"],
        ),
        OpenApiExample(
            "Error de carro vacío",
            value={
                "error": True,
                "mensaje": "Su carro está vacío: agregue productos antes de hacer el checkout.",
                "detalle": None,
            },
            response_only=True,
            status_codes=["400"],
        ),
    ],
)
class CheckoutView(APIView):
    """POST /api/ordenes/checkout/ — genera la orden a partir del carro."""

    permission_classes = [EsCliente]

    def post(self, request):
        """Ejecuta el checkout delegando en ordenes/servicios.py."""
        try:
            orden = realizar_checkout(request.user)
        except CarroVacioError as error:
            return _respuesta_error_negocio(error)
        except StockInsuficienteError as error:
            return _respuesta_stock_insuficiente(error)

        return Response(
            {
                "mensaje": "Orden creada correctamente. Los precios quedaron congelados.",
                "orden": OrdenSerializer(orden).data,
                "stock_descontado": False,
                "siguiente_paso": f"Pague la orden con POST /api/ordenes/{orden.id}/pagar/",
            },
            status=status.HTTP_201_CREATED,
        )


# ============================================================
# BLOQUE 3 — PAGO DE LA ORDEN POR EL CLIENTE
# Simula una pasarela de pago aprobada. Es el único punto (junto al
# cambio de estado a PAGADO) donde se descuenta el stock, y lo hace
# de forma atómica. Aplica el permiso de objeto para que nadie
# pague la orden de otro cliente.
# ============================================================
@extend_schema(
    tags=["Órdenes"],
    summary="Pagar una orden pendiente (descuenta el stock)",
    description=(
        "Simula la aprobación del pago. Es el momento en que **se verifica y se "
        "descuenta el stock**, de forma atómica:\n\n"
        "1. Se bloquea la orden (`select_for_update`) y se comprueba que siga en "
        "`PENDIENTE`.\n"
        "2. Se bloquean las filas de todos los productos implicados, siempre en "
        "el mismo orden por id, para evitar interbloqueos.\n"
        "3. Se relee el stock real. Si a algún producto no le alcanza, se lanza "
        "un **409 Conflict** con el detalle del faltante, se revierte toda la "
        "transacción y la orden sigue en `PENDIENTE`.\n"
        "4. Si alcanza, se descuenta con `F(\"stock\") - cantidad`, la orden pasa "
        "a `PAGADO` y se guarda la fecha de pago.\n\n"
        "Por eso, si dos clientes pagan el último producto casi a la vez, solo "
        "uno queda `PAGADO` y el stock nunca llega a ser negativo."
    ),
    request=None,
    responses={
        200: OpenApiResponse(response=OrdenSerializer, description="Pago aprobado y stock descontado."),
        400: OpenApiResponse(description="La orden ya no está en estado PENDIENTE."),
        409: OpenApiResponse(description="Stock insuficiente: se revirtió todo y la orden sigue PENDIENTE."),
        403: OpenApiResponse(description="La orden pertenece a otro cliente."),
    },
    examples=[
        OpenApiExample(
            "Pago aprobado",
            value={
                "mensaje": "Pago aprobado. El stock fue descontado y la orden quedó PAGADA.",
                "stock_descontado": True,
                "orden": {"estado": "PAGADO", "total": 329990},
            },
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "Rechazo por stock insuficiente (409)",
            value={
                "error": True,
                "mensaje": "Stock insuficiente para completar el pago. «Tarjeta de video NVIDIA GeForce RTX 4090 24GB»: pidió 1 y hay 0.",
                "detalle": {
                    "faltantes": [
                        {
                            "producto": "Tarjeta de video NVIDIA GeForce RTX 4090 24GB",
                            "sku": "GPU-NVD-RTX4090",
                            "solicitado": 1,
                            "disponible": 0,
                            "motivo": "Stock insuficiente.",
                        }
                    ]
                },
                "estado_de_la_orden": "PENDIENTE",
                "nota": "No se descontó stock: la transacción se revirtió por completo.",
            },
            response_only=True,
            status_codes=["409"],
        ),
    ],
)
class PagarOrdenView(GenericAPIView):
    """POST /api/ordenes/{id}/pagar/ — cobra la orden del cliente dueño."""

    permission_classes = [EsCliente, EsPropietarioDeLaOrden]
    serializer_class = OrdenSerializer
    queryset = Orden.objects.all()

    def post(self, request, pk=None):
        """Cobra la orden verificando el stock de forma atómica."""
        orden = Orden.objects.filter(pk=pk).first()
        if orden is None:
            return Response(
                {
                    "error": True,
                    "mensaje": f"No existe una orden con el id {pk}.",
                    "detalle": None,
                    "redireccion": "/",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Permiso de objeto: un cliente jamás paga la orden de otro.
        self.check_object_permissions(request, orden)

        try:
            orden = pagar_orden(orden, usuario=request.user)
        except StockInsuficienteError as error:
            return _respuesta_stock_insuficiente(error)
        except (TransicionInvalidaError, CarroVacioError) as error:
            return _respuesta_error_negocio(error)

        return Response(
            {
                "mensaje": "Pago aprobado. El stock fue descontado y la orden quedó PAGADA.",
                "stock_descontado": True,
                "orden": OrdenSerializer(orden).data,
            },
            status=status.HTTP_200_OK,
        )


# ============================================================
# BLOQUE 3-B — INICIAR UN PAGO CON WEBPAY PLUS
# No sustituye a POST /api/ordenes/{id}/pagar/ (que sigue existiendo
# tal cual): es una forma nueva de pagar, a través de la pasarela de
# Transbank en ambiente de integración. El cliente recibe la url y
# el token y debe enviarlos por POST (campo token_ws) al formulario
# de Transbank; Webpay vuelve al sitio por /webpay/retorno/
# (pagos/views_html.py), que confirma el pago servidor a servidor.
# ============================================================
@extend_schema(
    tags=["Órdenes"],
    summary="Iniciar un pago con Webpay Plus",
    description=(
        "Crea la transacción en **Webpay Plus** (ambiente de integración) para "
        "una orden `PENDIENTE` y devuelve la URL del formulario de pago de "
        "Transbank junto con el token.\n\n"
        "El cliente (navegador) debe enviar un formulario por **POST** a `url` "
        "con un único campo `token_ws` igual al `token` devuelto. Transbank "
        "redirige luego al sitio, que confirma el resultado servidor a servidor "
        "(no se descuenta stock aquí, recién al confirmar el pago)."
    ),
    request=None,
    responses={
        200: OpenApiResponse(response=WebpayIniciarSerializer, description="Transacción creada en Transbank."),
        400: OpenApiResponse(description="La orden no está PENDIENTE o no tiene productos."),
        403: OpenApiResponse(description="La orden pertenece a otro cliente."),
    },
)
class WebpayIniciarView(GenericAPIView):
    """POST /api/ordenes/{id}/webpay/iniciar/ — crea la transacción en Transbank."""

    permission_classes = [EsCliente, EsPropietarioDeLaOrden]
    serializer_class = WebpayIniciarSerializer
    queryset = Orden.objects.all()

    def post(self, request, pk=None):
        """Inicia el pago con Webpay Plus para la orden del cliente dueño."""
        orden = Orden.objects.filter(pk=pk).first()
        if orden is None:
            return Response(
                {
                    "error": True,
                    "mensaje": f"No existe una orden con el id {pk}.",
                    "detalle": None,
                    "redireccion": "/",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Permiso de objeto: un cliente jamás inicia el pago de otro.
        self.check_object_permissions(request, orden)

        return_url = request.build_absolute_uri("/webpay/retorno/")

        try:
            pago = iniciar_pago_webpay(orden, return_url)
        except ErrorDePago as error:
            return _respuesta_error_negocio(error)
        except TransbankError:
            return Response(
                {
                    "error": True,
                    "mensaje": "No se pudo contactar a Webpay Plus en este momento. Intente de nuevo.",
                    "detalle": None,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            WebpayIniciarSerializer({"url": pago.url_pago, "token": pago.token}).data,
            status=status.HTTP_200_OK,
        )


# ============================================================
# BLOQUE 4 — MIS ÓRDENES (CLIENTE)
# Solo devuelve las órdenes del usuario del token. El filtro por
# usuario se aplica en get_queryset, no con un parámetro de la
# petición, para que sea imposible pedir las órdenes de otro.
# ============================================================
@extend_schema_view(
    list=extend_schema(
        tags=["Órdenes"],
        summary="Listar mis órdenes (cliente)",
        description=(
            "Devuelve **solo las órdenes del cliente autenticado**, ordenadas de "
            "la más reciente a la más antigua. Un cliente nunca ve órdenes ajenas."
        ),
        parameters=[
            OpenApiParameter(name="estado", description="Filtra por estado: PENDIENTE, PAGADO, ENTREGADO o CANCELADO.", required=False, type=str),
            OpenApiParameter(name="fecha_desde", description="Órdenes creadas desde esta fecha (AAAA-MM-DD).", required=False, type=str),
            OpenApiParameter(name="fecha_hasta", description="Órdenes creadas hasta esta fecha (AAAA-MM-DD).", required=False, type=str),
        ],
    ),
    retrieve=extend_schema(
        tags=["Órdenes"],
        summary="Ver una de mis órdenes con su detalle e historial (cliente)",
    ),
)
class MisOrdenesViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/mis-ordenes/ — órdenes propias del cliente autenticado."""

    permission_classes = [EsCliente]
    filterset_class = OrdenFilter
    ordering_fields = ["creada_en", "pagada_en", "estado"]
    ordering = ["-creada_en"]
    search_fields = ["codigo"]

    queryset = Orden.objects.none()

    def get_queryset(self):
        """Restringe el conjunto a las órdenes del usuario autenticado."""
        # Al generar el esquema OpenAPI no hay usuario autenticado, así que
        # drf-spectacular marca la vista con swagger_fake_view. En ese caso
        # se devuelve un conjunto vacío del modelo correcto, suficiente para
        # que la documentación sepa qué recurso describe.
        if getattr(self, "swagger_fake_view", False):
            return Orden.objects.none()

        return (
            Orden.objects.filter(usuario=self.request.user)
            .con_relaciones()
            .order_by("-creada_en")
        )

    def get_serializer_class(self):
        """Resumen en el listado y detalle completo en la ficha."""
        if self.action == "retrieve":
            return OrdenSerializer
        return OrdenResumenSerializer


# ============================================================
# BLOQUE 5 — ÓRDENES (ADMINISTRADOR)
# Supervisión de todas las ventas, con los filtros de OrdenFilter,
# y el cambio de estado, que es el punto de la matriz de roles
# reservado al administrador: PATCH /api/ordenes/{id}/estado/.
# ============================================================
@extend_schema_view(
    list=extend_schema(
        tags=["Órdenes"],
        summary="Listar todas las órdenes (administrador)",
        description="Listado completo de ventas con filtros por estado, cliente y rango de fechas.",
        parameters=[
            OpenApiParameter(name="estado", description="PENDIENTE, PAGADO, ENTREGADO o CANCELADO.", required=False, type=str),
            OpenApiParameter(name="usuario", description="Id del cliente.", required=False, type=int),
            OpenApiParameter(name="fecha_desde", description="Órdenes creadas desde esta fecha (AAAA-MM-DD).", required=False, type=str),
            OpenApiParameter(name="fecha_hasta", description="Órdenes creadas hasta esta fecha (AAAA-MM-DD).", required=False, type=str),
            OpenApiParameter(name="codigo", description="Parte del número de orden (UUID).", required=False, type=str),
            OpenApiParameter(name="ordering", description="Orden: creada_en, -creada_en, pagada_en, estado.", required=False, type=str),
        ],
    ),
    retrieve=extend_schema(
        tags=["Órdenes"],
        summary="Ver una orden con su detalle e historial (administrador)",
    ),
)
class OrdenAdminViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/ordenes/ y PATCH /api/ordenes/{id}/estado/ — supervisión de ventas."""

    permission_classes = [EsAdministrador]
    filterset_class = OrdenFilter
    ordering_fields = ["creada_en", "pagada_en", "estado"]
    ordering = ["-creada_en"]
    search_fields = ["codigo", "usuario__username"]

    def get_queryset(self):
        """Todas las órdenes con sus relaciones precargadas."""
        return Orden.objects.con_relaciones().order_by("-creada_en")

    def get_serializer_class(self):
        """Resumen en el listado y detalle completo en la ficha."""
        if self.action == "retrieve":
            return OrdenSerializer
        return OrdenResumenSerializer

    @extend_schema(
        tags=["Órdenes"],
        summary="Cambiar el estado de una orden (administrador)",
        description=(
            "Aplica la máquina de estados del negocio:\n\n"
            "| Desde | Hacia | Efecto |\n"
            "|---|---|---|\n"
            "| PENDIENTE | PAGADO | Verifica y **descuenta** el stock de forma atómica |\n"
            "| PENDIENTE | CANCELADO | No hay stock que reponer (nunca se descontó) |\n"
            "| PAGADO | ENTREGADO | Cierra la venta |\n"
            "| PAGADO | CANCELADO | **Repone** automáticamente el stock |\n\n"
            "`ENTREGADO` y `CANCELADO` son estados finales. Cualquier otra "
            "transición responde **400** con el detalle de las transiciones "
            "permitidas. Todo cambio queda registrado en el historial."
        ),
        request=CambiarEstadoSerializer,
        responses={
            200: OpenApiResponse(response=OrdenSerializer, description="Estado cambiado."),
            400: OpenApiResponse(description="Transición no permitida o estado inválido."),
            409: OpenApiResponse(description="Stock insuficiente al intentar pasar a PAGADO."),
            403: OpenApiResponse(description="El rol del token no es ADMINISTRADOR."),
        },
        examples=[
            OpenApiExample(
                "Marcar como pagada (descuenta stock)",
                value={"estado": "PAGADO", "observacion": "Pago confirmado por transferencia."},
                request_only=True,
            ),
            OpenApiExample(
                "Marcar como entregada",
                value={"estado": "ENTREGADO", "observacion": "Retirado en tienda."},
                request_only=True,
            ),
            OpenApiExample(
                "Cancelar una orden pagada (repone stock)",
                value={"estado": "CANCELADO", "observacion": "El cliente desistió de la compra."},
                request_only=True,
            ),
            OpenApiExample(
                "Transición inválida",
                value={
                    "error": True,
                    "mensaje": "No se puede pasar de ENTREGADO a PAGADO. ENTREGADO es un estado final: ya no admite cambios.",
                    "detalle": {
                        "estado_actual": "ENTREGADO",
                        "estado_solicitado": "PAGADO",
                        "transiciones_permitidas": [],
                    },
                },
                response_only=True,
                status_codes=["400"],
            ),
        ],
    )
    @action(detail=True, methods=["patch"], url_path="estado")
    def cambiar_estado(self, request, pk=None):
        """Cambia el estado de la orden aplicando las transiciones permitidas."""
        orden = self.get_object()

        serializer = CambiarEstadoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        nuevo_estado = serializer.validated_data["estado"]
        observacion = serializer.validated_data.get("observacion", "")

        try:
            orden = cambiar_estado_orden(
                orden, nuevo_estado, usuario=request.user, observacion=observacion
            )
        except StockInsuficienteError as error:
            return _respuesta_stock_insuficiente(error)
        except (TransicionInvalidaError, CarroVacioError) as error:
            return _respuesta_error_negocio(error)

        repuestos = getattr(orden, "stock_repuesto", [])
        cuerpo = {
            "mensaje": f"La orden quedó en estado {orden.estado}.",
            "orden": OrdenSerializer(orden).data,
        }
        if nuevo_estado == "PAGADO":
            cuerpo["stock_descontado"] = True
        if repuestos:
            cuerpo["stock_repuesto"] = repuestos
            cuerpo["mensaje"] = "La orden fue cancelada y el stock se repuso automáticamente."

        return Response(cuerpo, status=status.HTTP_200_OK)
