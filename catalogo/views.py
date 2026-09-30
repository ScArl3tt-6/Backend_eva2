# ============================================================
# catalogo/views.py — API REST DEL CATÁLOGO
# Responsabilidad: exponer el CRUD completo de categorías, marcas
# y productos respetando la matriz de roles de la pauta.
#
#   GET  /api/categorias/  y  GET /api/productos/   → PÚBLICO
#   POST, PUT, PATCH, DELETE                        → ADMINISTRADOR
#
# El permiso EsAdministradorOSoloLectura resuelve esa matriz en
# una sola línea por vista. Sin token, un intento de escritura
# devuelve 401; con token de cliente devuelve 403.
#
# "Eliminar" nunca borra filas: DELETE ejecuta la baja lógica
# (activo = False) y existe un endpoint para reactivar.
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
from rest_framework.response import Response

from usuarios.permisos import EsAdministradorOSoloLectura

from .filtros import ProductoFilter
from .models import Categoria, Marca, Producto
from .serializers import (
    CategoriaSerializer,
    MarcaSerializer,
    ProductoEscrituraSerializer,
    ProductoSerializer,
)


# ============================================================
# BLOQUE 1 — PARÁMETRO COMPARTIDO PARA VER REGISTROS INACTIVOS
# Los listados públicos muestran solo registros activos. El
# administrador puede añadir ?incluir_inactivos=true para revisar
# y reactivar lo que dio de baja.
# ============================================================
PARAMETRO_INCLUIR_INACTIVOS = OpenApiParameter(
    name="incluir_inactivos",
    description=(
        "true para incluir también los registros dados de baja lógicamente. "
        "Pensado para el administrador, que necesita verlos para reactivarlos."
    ),
    required=False,
    type=bool,
)


def _pidio_incluir_inactivos(request) -> bool:
    """Interpreta el parámetro incluir_inactivos de la cadena de consulta."""
    valor = str(request.query_params.get("incluir_inactivos", "false")).lower()
    return valor in {"true", "1", "si", "sí"}


def _debe_filtrar_activos(vista) -> bool:
    """Decide si el conjunto de resultados debe excluir los registros de baja.

    Se excluyen solo al listar y al consultar, que es lo que ve el público.
    Las acciones de escritura y la reactivación —reservadas al administrador—
    necesitan alcanzar un registro ya dado de baja; de lo contrario,
    reactivarlo respondería 404.
    """
    if _pidio_incluir_inactivos(vista.request):
        return False
    return vista.action in {"list", "retrieve"}


# ============================================================
# BLOQUE 2 — MEZCLA CON LA BAJA LÓGICA Y LA REACTIVACIÓN
# Centraliza el comportamiento común de las tres entidades del
# catálogo: DELETE desactiva y POST .../reactivar/ vuelve a
# publicar. Se evita repetir el mismo código tres veces.
# ============================================================
class BajaLogicaMixin:
    """Aporta el borrado lógico y la reactivación a los ViewSet del catálogo."""

    nombre_entidad = "registro"

    def destroy(self, request, *args, **kwargs):
        """Da de baja el registro sin borrar la fila de la base de datos."""
        objeto = self.get_object()
        objeto.desactivar()

        return Response(
            {
                "mensaje": f"{self.nombre_entidad.capitalize()} «{objeto}» dado de baja correctamente.",
                "baja_logica": True,
                "nota": "La fila se conserva en la base de datos; puede reactivarse.",
                "datos": self.get_serializer(objeto).data,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Reactivar un registro dado de baja",
        description="Revierte la baja lógica y vuelve a publicar el registro.",
        request=None,
        responses={200: OpenApiResponse(description="Registro reactivado.")},
    )
    @action(detail=True, methods=["post"], url_path="reactivar")
    def reactivar(self, request, pk=None):
        """Vuelve a poner activo=True en el registro indicado."""
        objeto = self.get_object()
        objeto.reactivar()

        return Response(
            {
                "mensaje": f"{self.nombre_entidad.capitalize()} «{objeto}» está activo otra vez.",
                "datos": self.get_serializer(objeto).data,
            },
            status=status.HTTP_200_OK,
        )


# ============================================================
# BLOQUE 3 — CATEGORÍAS
# GET público (parte de la matriz de roles: PÚBLICO puede leer
# /api/categorias/). Escritura reservada al Administrador de TI.
# ============================================================
@extend_schema_view(
    list=extend_schema(
        tags=["Catálogo"],
        summary="Listar categorías (público)",
        description="Devuelve las categorías publicadas. No requiere token.",
        parameters=[
            PARAMETRO_INCLUIR_INACTIVOS,
            OpenApiParameter(name="search", description="Busca en el nombre y la descripción.", required=False, type=str),
            OpenApiParameter(name="ordering", description="Orden: nombre, -nombre, creado_en, -creado_en.", required=False, type=str),
        ],
    ),
    retrieve=extend_schema(tags=["Catálogo"], summary="Ver una categoría (público)"),
    create=extend_schema(
        tags=["Catálogo"],
        summary="Crear una categoría (administrador)",
        examples=[
            OpenApiExample(
                "Categoría nueva",
                value={
                    "nombre": "Refrigeración líquida",
                    "descripcion": "Sistemas de enfriamiento por líquido para procesadores.",
                    "icono": "bi-snow",
                },
                request_only=True,
            )
        ],
    ),
    update=extend_schema(tags=["Catálogo"], summary="Actualizar una categoría (administrador)"),
    partial_update=extend_schema(tags=["Catálogo"], summary="Actualizar parcialmente una categoría (administrador)"),
    destroy=extend_schema(
        tags=["Catálogo"],
        summary="Dar de baja una categoría (administrador)",
        description="Baja lógica: deja `activo = false` y conserva la fila y sus productos.",
    ),
)
class CategoriaViewSet(BajaLogicaMixin, viewsets.ModelViewSet):
    """CRUD de categorías: lectura pública, escritura del administrador."""

    serializer_class = CategoriaSerializer
    permission_classes = [EsAdministradorOSoloLectura]
    nombre_entidad = "categoría"
    search_fields = ["nombre", "descripcion"]
    ordering_fields = ["nombre", "creado_en"]
    ordering = ["nombre"]
    filterset_fields = ["activo"]

    def get_queryset(self):
        """Categorías activas; con incluir_inactivos=true también las de baja."""
        consulta = Categoria.objects.all()
        if _debe_filtrar_activos(self):
            consulta = consulta.filter(activo=True)
        return consulta


# ============================================================
# BLOQUE 4 — MARCAS
# Mismo esquema de permisos que las categorías.
# ============================================================
@extend_schema_view(
    list=extend_schema(
        tags=["Catálogo"],
        summary="Listar marcas (público)",
        parameters=[
            PARAMETRO_INCLUIR_INACTIVOS,
            OpenApiParameter(name="search", description="Busca en el nombre y el país de origen.", required=False, type=str),
        ],
    ),
    retrieve=extend_schema(tags=["Catálogo"], summary="Ver una marca (público)"),
    create=extend_schema(
        tags=["Catálogo"],
        summary="Crear una marca (administrador)",
        examples=[
            OpenApiExample(
                "Marca nueva",
                value={"nombre": "Gigabyte", "pais_origen": "Taiwán"},
                request_only=True,
            )
        ],
    ),
    update=extend_schema(tags=["Catálogo"], summary="Actualizar una marca (administrador)"),
    partial_update=extend_schema(tags=["Catálogo"], summary="Actualizar parcialmente una marca (administrador)"),
    destroy=extend_schema(
        tags=["Catálogo"],
        summary="Dar de baja una marca (administrador)",
        description="Baja lógica: deja `activo = false` y conserva la fila.",
    ),
)
class MarcaViewSet(BajaLogicaMixin, viewsets.ModelViewSet):
    """CRUD de marcas: lectura pública, escritura del administrador."""

    serializer_class = MarcaSerializer
    permission_classes = [EsAdministradorOSoloLectura]
    nombre_entidad = "marca"
    search_fields = ["nombre", "pais_origen"]
    ordering_fields = ["nombre", "creado_en"]
    ordering = ["nombre"]
    filterset_fields = ["activo", "pais_origen"]

    def get_queryset(self):
        """Marcas activas; con incluir_inactivos=true también las de baja."""
        consulta = Marca.objects.all()
        if _debe_filtrar_activos(self):
            consulta = consulta.filter(activo=True)
        return consulta


# ============================================================
# BLOQUE 5 — PRODUCTOS
# Endpoint central del catálogo. Reúne los cuatro requisitos de la
# pauta sobre consultas: filtros de django-filter (ProductoFilter),
# búsqueda por texto, ordenamiento y paginación de 10 en 10, que
# viene de la configuración global de DRF.
#
# select_related evita el problema N+1 al mostrar categoría y
# marca anidadas en el listado.
# ============================================================
@extend_schema_view(
    list=extend_schema(
        tags=["Catálogo"],
        summary="Listar productos con filtros, búsqueda y orden (público)",
        description=(
            "Catálogo público paginado de 10 en 10. Acepta los filtros de "
            "`ProductoFilter`, búsqueda libre con `search` y ordenamiento con "
            "`ordering`. No requiere token."
        ),
        parameters=[
            OpenApiParameter(name="categoria", description="Id de la categoría.", required=False, type=int),
            OpenApiParameter(name="categoria_nombre", description="Parte del nombre de la categoría.", required=False, type=str),
            OpenApiParameter(name="marca", description="Id de la marca.", required=False, type=int),
            OpenApiParameter(name="marca_nombre", description="Parte del nombre de la marca.", required=False, type=str),
            OpenApiParameter(name="precio_min", description="Precio mínimo en pesos chilenos.", required=False, type=int),
            OpenApiParameter(name="precio_max", description="Precio máximo en pesos chilenos.", required=False, type=int),
            OpenApiParameter(name="en_stock", description="true devuelve solo productos con stock disponible.", required=False, type=bool),
            OpenApiParameter(name="sku", description="Código SKU exacto, sin distinguir mayúsculas.", required=False, type=str),
            OpenApiParameter(name="buscar", description="Búsqueda libre en nombre, SKU, descripción y marca.", required=False, type=str),
            OpenApiParameter(name="search", description="Búsqueda de DRF en nombre, SKU, descripción y marca.", required=False, type=str),
            OpenApiParameter(name="ordering", description="Orden: precio, -precio, nombre, -nombre, stock, -stock, creado_en, -creado_en.", required=False, type=str),
            PARAMETRO_INCLUIR_INACTIVOS,
        ],
    ),
    retrieve=extend_schema(tags=["Catálogo"], summary="Ver el detalle de un producto (público)"),
    create=extend_schema(
        tags=["Catálogo"],
        summary="Crear un producto (administrador)",
        request=ProductoEscrituraSerializer,
        examples=[
            OpenApiExample(
                "Producto nuevo",
                value={
                    "sku": "GPU-NVD-RTX4070",
                    "nombre": "Tarjeta de video NVIDIA GeForce RTX 4070 12GB",
                    "descripcion": "12 GB GDDR6X, 5888 núcleos CUDA, PCIe 4.0.",
                    "categoria": 2,
                    "marca": 3,
                    "precio": 749990,
                    "stock": 8,
                },
                request_only=True,
            )
        ],
    ),
    update=extend_schema(tags=["Catálogo"], summary="Actualizar un producto (administrador)", request=ProductoEscrituraSerializer),
    partial_update=extend_schema(
        tags=["Catálogo"],
        summary="Actualizar parcialmente un producto (administrador)",
        request=ProductoEscrituraSerializer,
        examples=[
            OpenApiExample("Cambiar solo el precio", value={"precio": 699990}, request_only=True),
            OpenApiExample("Reponer stock", value={"stock": 25}, request_only=True),
        ],
    ),
    destroy=extend_schema(
        tags=["Catálogo"],
        summary="Dar de baja un producto (administrador)",
        description=(
            "Baja lógica: deja `activo = false`. La fila se conserva para no "
            "perder el historial de las órdenes que ya lo vendieron."
        ),
    ),
)
class ProductoViewSet(BajaLogicaMixin, viewsets.ModelViewSet):
    """CRUD de productos con filtros, búsqueda, orden y paginación."""

    permission_classes = [EsAdministradorOSoloLectura]
    filterset_class = ProductoFilter
    nombre_entidad = "producto"
    search_fields = ["nombre", "sku", "descripcion", "marca__nombre"]
    ordering_fields = ["precio", "nombre", "stock", "creado_en"]
    ordering = ["nombre"]

    def get_queryset(self):
        """Productos activos con sus relaciones precargadas (evita N+1)."""
        consulta = Producto.objects.select_related("categoria", "marca")
        if _debe_filtrar_activos(self):
            consulta = consulta.filter(activo=True)
        return consulta

    def get_serializer_class(self):
        """Lectura anidada al consultar; ids de relación al escribir."""
        if self.action in {"create", "update", "partial_update"}:
            return ProductoEscrituraSerializer
        return ProductoSerializer
