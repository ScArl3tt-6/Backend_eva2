# ============================================================
# ordenes/serializers.py — TRADUCCIÓN JSON DE LAS ÓRDENES
# Responsabilidad: mostrar la orden con su detalle de precios
# congelados, su total calculado y su historial de estados, y
# validar el cuerpo del cambio de estado.
#
# Dos puntos que conviene poder explicar en la defensa:
#   · precio_unitario es de solo lectura: lo fija el checkout y
#     nadie puede alterarlo después por la API. Es el precio
#     congelado de la venta.
#   · total no es un campo de la tabla: se calcula sumando
#     cantidad × precio_unitario de cada detalle.
# ============================================================

from rest_framework import serializers

from .models import DetalleOrden, EstadoOrden, HistorialEstadoOrden, Orden


# ============================================================
# BLOQUE 1 — DETALLE DE LA ORDEN
# Muestra el producto vendido junto al precio que se congeló. Se
# incluye el precio actual del catálogo para que se vea la
# diferencia cuando el catálogo cambió después de la venta.
# ============================================================
class DetalleOrdenSerializer(serializers.ModelSerializer):
    """Línea de la orden con su precio congelado y su subtotal."""

    producto_id = serializers.IntegerField(source="producto.id", read_only=True)
    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)
    producto_sku = serializers.CharField(source="producto.sku", read_only=True)
    precio_actual_catalogo = serializers.DecimalField(
        source="producto.precio",
        max_digits=12,
        decimal_places=0,
        read_only=True,
        help_text="Precio que tiene hoy el producto; puede diferir del congelado.",
    )
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=0, read_only=True)

    class Meta:
        model = DetalleOrden
        fields = [
            "id",
            "producto_id",
            "producto_nombre",
            "producto_sku",
            "cantidad",
            "precio_unitario",
            "precio_actual_catalogo",
            "subtotal",
        ]
        read_only_fields = fields


# ============================================================
# BLOQUE 2 — HISTORIAL DE ESTADOS
# Línea de tiempo de la orden para auditoría: cada transición con
# su autor, su fecha y su observación.
# ============================================================
class HistorialEstadoOrdenSerializer(serializers.ModelSerializer):
    """Registro de un cambio de estado de la orden."""

    estado_anterior_etiqueta = serializers.SerializerMethodField()
    estado_nuevo_etiqueta = serializers.CharField(
        source="get_estado_nuevo_display", read_only=True
    )
    cambiado_por_username = serializers.CharField(
        source="cambiado_por.username", read_only=True, default=None
    )

    class Meta:
        model = HistorialEstadoOrden
        fields = [
            "id",
            "estado_anterior",
            "estado_anterior_etiqueta",
            "estado_nuevo",
            "estado_nuevo_etiqueta",
            "cambiado_por_username",
            "fecha",
            "observacion",
        ]
        read_only_fields = fields

    def get_estado_anterior_etiqueta(self, obj) -> str:
        """Etiqueta legible del estado de origen; vacío cuando la orden nace."""
        if not obj.estado_anterior:
            return "Creación de la orden"
        return obj.get_estado_anterior_display()


# ============================================================
# BLOQUE 3 — ORDEN COMPLETA
# Respuesta de checkout, de /api/mis-ordenes/ y de /api/ordenes/.
# Incluye el código UUID, el detalle, el total y el historial.
# ============================================================
class OrdenSerializer(serializers.ModelSerializer):
    """Representación completa de una orden de compra."""

    detalles = DetalleOrdenSerializer(many=True, read_only=True)
    historial = HistorialEstadoOrdenSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=0, read_only=True)
    cantidad_items = serializers.IntegerField(read_only=True)
    estado_etiqueta = serializers.CharField(source="get_estado_display", read_only=True)
    usuario_username = serializers.CharField(source="usuario.username", read_only=True)
    codigo_corto = serializers.CharField(read_only=True)
    transiciones_posibles = serializers.SerializerMethodField()

    class Meta:
        model = Orden
        fields = [
            "id",
            "codigo",
            "codigo_corto",
            "usuario",
            "usuario_username",
            "estado",
            "estado_etiqueta",
            "transiciones_posibles",
            "detalles",
            "historial",
            "cantidad_items",
            "total",
            "creada_en",
            "pagada_en",
            "actualizada_en",
        ]
        read_only_fields = fields

    def get_transiciones_posibles(self, obj) -> list[str]:
        """Estados a los que la orden puede pasar según la máquina de estados."""
        from .servicios import transiciones_posibles

        return transiciones_posibles(obj)


# ============================================================
# BLOQUE 4 — ORDEN RESUMIDA
# Versión liviana para los listados: sin historial ni detalle, para
# no arrastrar decenas de filas en cada página de resultados.
# ============================================================
class OrdenResumenSerializer(serializers.ModelSerializer):
    """Vista compacta de una orden, pensada para listados paginados."""

    total = serializers.DecimalField(max_digits=14, decimal_places=0, read_only=True)
    cantidad_items = serializers.IntegerField(read_only=True)
    estado_etiqueta = serializers.CharField(source="get_estado_display", read_only=True)
    usuario_username = serializers.CharField(source="usuario.username", read_only=True)
    codigo_corto = serializers.CharField(read_only=True)

    class Meta:
        model = Orden
        fields = [
            "id",
            "codigo",
            "codigo_corto",
            "usuario",
            "usuario_username",
            "estado",
            "estado_etiqueta",
            "cantidad_items",
            "total",
            "creada_en",
            "pagada_en",
        ]
        read_only_fields = fields


# ============================================================
# BLOQUE 5 — CUERPO DEL CAMBIO DE ESTADO
# Entrada de PATCH /api/ordenes/{id}/estado/. Solo acepta los
# cuatro estados válidos; la legalidad de la transición concreta la
# decide ordenes/servicios.py, que es el dueño de esa regla.
# ============================================================
class CambiarEstadoSerializer(serializers.Serializer):
    """Nuevo estado que el administrador quiere aplicar a la orden."""

    estado = serializers.ChoiceField(
        choices=EstadoOrden.choices,
        help_text="Estado destino: PENDIENTE, PAGADO, ENTREGADO o CANCELADO.",
        error_messages={
            "invalid_choice": "«{input}» no es un estado válido. Use PENDIENTE, PAGADO, ENTREGADO o CANCELADO.",
        },
    )
    observacion = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Motivo del cambio; queda registrado en el historial de la orden.",
    )
