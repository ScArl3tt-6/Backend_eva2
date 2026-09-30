# ============================================================
# usuarios/views.py — API DE AUTENTICACIÓN Y DE USUARIOS
# Responsabilidad: exponer el ciclo completo de autenticación JWT
# (registro, login con claim de rol, refresh, logout con lista
# negra y perfil) y el CRUD de usuarios reservado al administrador.
#
# Puntos evaluados que se resuelven aquí:
#   · El login devuelve access y refresh, y el token lleva el claim
#     "rol" (ver usuarios/tokens.py).
#   · El logout invalida de verdad el refresh token (blacklist).
#   · El "eliminar" de un usuario es lógico: is_active = False.
#   · El administrador puede consultar el carro persistido de
#     cualquier cliente.
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
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from carro.models import Carro
from carro.serializers import CarroSerializer

from .models import Usuario
from .permisos import EsAdministrador
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    RegistroSerializer,
    UsuarioEscrituraSerializer,
    UsuarioSerializer,
)
from .tokens import TokenConRolSerializer


# ============================================================
# BLOQUE 1 — REGISTRO PÚBLICO DE CLIENTES
# Endpoint abierto (AllowAny explícito, porque el permiso global
# del proyecto es IsAuthenticated). Crea siempre un CLIENTE y la
# señal post_save le construye su carro persistente.
# ============================================================
@extend_schema(
    tags=["Autenticación"],
    summary="Registrar una cuenta de cliente",
    description=(
        "Crea una cuenta nueva con rol CLIENTE. El rol no se puede elegir desde "
        "fuera del sistema. La contraseña se valida con las reglas de Django y se "
        "guarda cifrada. Al crear la cuenta se genera automáticamente su carro "
        "de compras persistente."
    ),
    request=RegistroSerializer,
    responses={
        201: OpenApiResponse(response=UsuarioSerializer, description="Cuenta creada."),
        400: OpenApiResponse(description="Datos inválidos (correo repetido, contraseñas distintas, etc.)."),
    },
    examples=[
        OpenApiExample(
            "Registro de una clienta nueva",
            value={
                "username": "cliente4",
                "email": "cliente4@hardpointpc.cl",
                "first_name": "Camila",
                "last_name": "Rojas",
                "telefono": "+56 9 1234 5678",
                "password": "Cliente.2026",
                "password2": "Cliente.2026",
            },
            request_only=True,
        ),
    ],
)
class RegistroView(APIView):
    """POST /api/auth/registro/ — alta pública de clientes."""

    permission_classes = [AllowAny]
    serializer_class = RegistroSerializer

    def post(self, request):
        """Valida los datos, crea el cliente y devuelve su ficha."""
        serializer = RegistroSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()

        return Response(
            {
                "mensaje": "Cuenta creada correctamente. Ya puede iniciar sesión.",
                "usuario": UsuarioSerializer(usuario).data,
            },
            status=status.HTTP_201_CREATED,
        )


# ============================================================
# BLOQUE 2 — LOGIN CON CLAIM DE ROL
# Usa TokenConRolSerializer, que inserta rol, username, email y
# nombre completo dentro del JWT. La respuesta entrega access,
# refresh, rol y los datos del usuario.
# ============================================================
@extend_schema(
    tags=["Autenticación"],
    summary="Iniciar sesión y obtener el token JWT",
    description=(
        "Valida las credenciales y devuelve el par de tokens. El token de acceso "
        "incluye el claim `rol` (CLIENTE o ADMINISTRADOR), que es el que evalúan "
        "los permisos de la API.\n\n"
        "Para usar la API desde esta página: copie el valor de `access`, pulse "
        "**Authorize** y péguelo."
    ),
    request=LoginSerializer,
    responses={
        200: OpenApiResponse(description="Par de tokens, rol y datos del usuario."),
        401: OpenApiResponse(description="Usuario o contraseña incorrectos."),
    },
    examples=[
        OpenApiExample(
            "Login del administrador de TI",
            value={"username": "admin_ti", "password": "Admin.2026"},
            request_only=True,
        ),
        OpenApiExample(
            "Login de un cliente",
            value={"username": "cliente1", "password": "Cliente.2026"},
            request_only=True,
        ),
        OpenApiExample(
            "Respuesta con el claim de rol",
            value={
                "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "rol": "ADMINISTRADOR",
                "usuario": {
                    "id": 1,
                    "username": "admin_ti",
                    "email": "admin_ti@hardpointpc.cl",
                    "nombre_completo": "Administrador de TI",
                    "rol": "ADMINISTRADOR",
                    "rol_etiqueta": "Administrador de TI",
                    "es_administrador": True,
                },
            },
            response_only=True,
        ),
    ],
)
class LoginConRolView(TokenObtainPairView):
    """POST /api/auth/login/ — entrega tokens JWT con el rol incorporado."""

    permission_classes = [AllowAny]
    serializer_class = TokenConRolSerializer


# ============================================================
# BLOQUE 3 — REFRESCO DEL TOKEN
# Con ROTATE_REFRESH_TOKENS y BLACKLIST_AFTER_ROTATION activados,
# cada refresco entrega un refresh nuevo y anula el anterior.
# ============================================================
@extend_schema(
    tags=["Autenticación"],
    summary="Renovar el token de acceso",
    description=(
        "Entrega un token de acceso nuevo a partir del token de refresco. "
        "Como la rotación está activada, también devuelve un refresh nuevo y el "
        "anterior queda en la lista negra."
    ),
    responses={
        200: OpenApiResponse(description="Token de acceso renovado."),
        401: OpenApiResponse(description="El token de refresco es inválido o ya fue invalidado."),
    },
)
class RefrescarTokenView(TokenRefreshView):
    """POST /api/auth/refresh/ — renueva el token de acceso."""

    permission_classes = [AllowAny]


# ============================================================
# BLOQUE 4 — LOGOUT CON LISTA NEGRA
# Invalida el refresh token recibido. Es la pieza que permite
# demostrar que el carro NO depende de la sesión: después del
# logout el token queda inutilizable, pero al volver a entrar los
# ítems del carro siguen exactamente igual, porque viven en
# PostgreSQL.
# ============================================================
@extend_schema(
    tags=["Autenticación"],
    summary="Cerrar sesión e invalidar el token de refresco",
    description=(
        "Envía el token de refresco a la lista negra, de modo que no pueda "
        "volver a usarse. El carro de compras NO se borra: está guardado en "
        "PostgreSQL y reaparece al iniciar sesión otra vez."
    ),
    request=LogoutSerializer,
    responses={
        200: OpenApiResponse(description="Sesión cerrada; el token quedó invalidado."),
        400: OpenApiResponse(description="Falta el token de refresco o ya no es válido."),
    },
    examples=[
        OpenApiExample(
            "Cierre de sesión",
            value={"refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."},
            request_only=True,
        ),
    ],
)
class LogoutView(APIView):
    """POST /api/auth/logout/ — invalida el refresh token del usuario."""

    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    def post(self, request):
        """Agrega el token de refresco a la lista negra."""
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
        except TokenError:
            return Response(
                {
                    "error": True,
                    "mensaje": "El token de refresco no es válido o ya fue invalidado.",
                    "detalle": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "mensaje": "Sesión cerrada. El token de refresco quedó invalidado.",
                "nota": "Su carro de compras sigue guardado en la base de datos.",
            },
            status=status.HTTP_200_OK,
        )


# ============================================================
# BLOQUE 5 — PERFIL Y CLAIMS DEL TOKEN
# Devuelve los datos del usuario y, además, el contenido
# decodificado del token con el que llegó la petición. Sirve como
# evidencia visible de que el claim "rol" viaja dentro del JWT.
# ============================================================
@extend_schema(
    tags=["Autenticación"],
    summary="Ver el perfil y los claims del token",
    description=(
        "Devuelve los datos del usuario autenticado y el contenido decodificado "
        "del token JWT recibido, incluido el claim `rol`. Es la forma directa de "
        "comprobar qué información viaja firmada en el token."
    ),
    responses={
        200: OpenApiResponse(description="Datos del usuario y claims del token."),
        401: OpenApiResponse(description="No se envió un token válido."),
    },
)
class PerfilView(APIView):
    """GET /api/auth/perfil/ — datos del usuario y claims del token."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Lee request.auth para exponer los claims tal como llegaron."""
        token = request.auth
        claims = dict(token.payload) if token is not None and hasattr(token, "payload") else {}

        return Response(
            {
                "usuario": UsuarioSerializer(request.user).data,
                "claims_del_token": claims,
                "rol_en_el_token": claims.get("rol"),
                "autenticado_con": "JWT (Bearer)" if claims else "Sesión de Django",
            },
            status=status.HTTP_200_OK,
        )


# ============================================================
# BLOQUE 6 — CRUD DE USUARIOS (SOLO ADMINISTRADOR)
# Incluye la baja lógica (DELETE → is_active=False), la
# reactivación y la consulta del carro persistido de cualquier
# cliente, que es la evidencia de que el carro está en la base de
# datos y no en la sesión del navegador.
# ============================================================
@extend_schema_view(
    list=extend_schema(
        tags=["Usuarios"],
        summary="Listar usuarios",
        description="Lista los usuarios del sistema. Con `?incluir_inactivos=true` también muestra los dados de baja.",
        parameters=[
            OpenApiParameter(
                name="incluir_inactivos",
                description="true para incluir los usuarios desactivados.",
                required=False,
                type=bool,
            ),
            OpenApiParameter(name="rol", description="Filtra por rol: CLIENTE o ADMINISTRADOR.", required=False, type=str),
            OpenApiParameter(name="search", description="Busca en usuario, nombre, apellido y correo.", required=False, type=str),
        ],
    ),
    retrieve=extend_schema(tags=["Usuarios"], summary="Ver un usuario"),
    create=extend_schema(tags=["Usuarios"], summary="Crear un usuario eligiendo su rol"),
    update=extend_schema(tags=["Usuarios"], summary="Actualizar un usuario por completo"),
    partial_update=extend_schema(tags=["Usuarios"], summary="Actualizar parcialmente un usuario"),
    destroy=extend_schema(
        tags=["Usuarios"],
        summary="Dar de baja un usuario (baja lógica)",
        description="No borra la fila: deja el usuario con `is_active = false`, conservando su historial de órdenes.",
    ),
)
class UsuarioViewSet(viewsets.ModelViewSet):
    """CRUD de usuarios reservado al Administrador de TI."""

    permission_classes = [EsAdministrador]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["username", "first_name", "last_name", "email"]
    ordering_fields = ["username", "email", "rol", "creado_en"]
    ordering = ["username"]
    filterset_fields = None

    queryset = Usuario.objects.all()

    def get_queryset(self):
        """Muestra los usuarios activos y, si se pide, también los inactivos."""
        consulta = Usuario.objects.all()

        incluir_inactivos = str(
            self.request.query_params.get("incluir_inactivos", "false")
        ).lower() in {"true", "1", "si", "sí"}

        # El filtro por estado se aplica solo al listar y al consultar. Las
        # acciones de escritura y la reactivación deben poder alcanzar una
        # cuenta ya dada de baja: si no, reactivarla respondería 404.
        if not incluir_inactivos and self.action in {"list", "retrieve"}:
            consulta = consulta.filter(is_active=True)

        rol = self.request.query_params.get("rol")
        if rol:
            consulta = consulta.filter(rol=rol.upper())

        return consulta

    def get_serializer_class(self):
        """Serializer de lectura para consultar y de escritura para modificar."""
        if self.action in {"create", "update", "partial_update"}:
            return UsuarioEscrituraSerializer
        return UsuarioSerializer

    # --- Baja lógica en lugar de borrado físico ---
    def destroy(self, request, *args, **kwargs):
        """Desactiva el usuario conservando la fila y su historial."""
        usuario = self.get_object()

        if usuario.id == request.user.id:
            return Response(
                {
                    "error": True,
                    "mensaje": "No puede darse de baja a sí mismo.",
                    "detalle": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        usuario.is_active = False
        usuario.save(update_fields=["is_active", "actualizado_en"])

        return Response(
            {
                "mensaje": f"El usuario «{usuario.username}» quedó dado de baja.",
                "baja_logica": True,
                "usuario": UsuarioSerializer(usuario).data,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Usuarios"],
        summary="Reactivar un usuario dado de baja",
        request=None,
        responses={200: OpenApiResponse(description="Usuario reactivado.")},
    )
    @action(detail=True, methods=["post"], url_path="reactivar")
    def reactivar(self, request, pk=None):
        """Vuelve a habilitar una cuenta desactivada."""
        usuario = self.get_object()
        usuario.is_active = True
        usuario.save(update_fields=["is_active", "actualizado_en"])

        return Response(
            {
                "mensaje": f"El usuario «{usuario.username}» está activo otra vez.",
                "usuario": UsuarioSerializer(usuario).data,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Usuarios"],
        summary="Ver el carro persistido de un cliente",
        description=(
            "Devuelve el carro guardado en PostgreSQL del cliente indicado, con "
            "sus ítems, precios vigentes y total. Evidencia de que el carro no "
            "depende de la sesión del navegador."
        ),
        responses={
            200: OpenApiResponse(response=CarroSerializer, description="Carro del cliente."),
            404: OpenApiResponse(description="El cliente no tiene carro asociado."),
        },
    )
    @action(detail=True, methods=["get"], url_path="carro")
    def ver_carro(self, request, pk=None):
        """Expone el carro de cualquier cliente para revisión del administrador."""
        usuario = self.get_object()
        carro = Carro.objects.filter(usuario=usuario).first()

        if carro is None:
            return Response(
                {
                    "error": True,
                    "mensaje": f"El usuario «{usuario.username}» no tiene carro asociado (solo los clientes lo tienen).",
                    "detalle": None,
                    "redireccion": "/",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(CarroSerializer(carro).data, status=status.HTTP_200_OK)
