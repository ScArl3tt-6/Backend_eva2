# ============================================================
# carro/serializers.py — TRADUCCIÓN JSON DEL CARRO
# Responsabilidad: mostrar el carro con los precios vigentes y
# validar los datos de entrada al agregar o modificar ítems.
#
# Detalle importante para la defensa: ni el subtotal ni el total
# son campos de la base de datos. Se calculan al momento de
# responder, a partir del precio actual del producto (3FN). El
# precio se congela recién en el checkout, dentro de DetalleOrden.
# ============================================================

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from catalogo.models import Producto
from catalogo.serializers import ProductoSerializer

from .models import Carro, ItemCarro


# ============================================================
# BLOQUE 1 — ÍTEM DEL CARRO (LECTURA)
# Cada línea muestra el producto completo, el precio vigente, la
# cantidad y el subtotal calculado, más un aviso de si el stock
# actual alcanza.
# ============================================================
class ItemCarroSerializer(serializers.ModelSerializer):
    """Representación de lectura de una línea del carro."""

    producto = ProductoSerializer(read_only=True)
    precio_vigente = serializers.DecimalField(
        max_digits=12, decimal_places=0, read_only=True
    )
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=0, read_only=True)
    stock_suficiente = serializers.BooleanField(read_only=True)

    class Meta:
        model = ItemCarro
        fields = [
            "id",
            "producto",
            "cantidad",
            "precio_vigente",
            "subtotal",
            "stock_suficiente",
            "agregado_en",
            "actualizado_en",
        ]


# ============================================================
# BLOQUE 2 — CARRO COMPLETO (LECTURA)
# Responde GET /api/carro/. Solo incluye los ítems activos: los
# quitados quedan con activo=False y no forman parte del carro.
# ============================================================
class CarroSerializer(serializers.ModelSerializer):
    """Representación de lectura del carro persistente."""

    items = serializers.SerializerMethodField()
    total = serializers.DecimalField(max_digits=14, decimal_places=0, read_only=True)
    cantidad_items = serializers.IntegerField(read_only=True)
    esta_vacio = serializers.BooleanField(read_only=True)
    usuario_username = serializers.CharField(source="usuario.username", read_only=True)

    class Meta:
        model = Carro
        fields = [
            "id",
            "usuario",
            "usuario_username",
            "items",
            "cantidad_items",
            "total",
            "esta_vacio",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = fields

    # extend_schema_field le indica a drf-spectacular qué tipo devuelve
    # este campo calculado, para que el esquema OpenAPI documente la
    # lista de ítems y no un texto genérico.
    @extend_schema_field(ItemCarroSerializer(many=True))
    def get_items(self, obj):
        """Devuelve solo los ítems vigentes del carro."""
        return ItemCarroSerializer(obj.items_activos, many=True, context=self.context).data


# ============================================================
# BLOQUE 3 — AGREGAR UN PRODUCTO (ESCRITURA)
# Cuerpo de POST /api/carro/. Valida que el producto exista, esté
# publicado y que la cantidad sea al menos 1. El resto de las
# reglas (suma sin duplicar, comparación con el stock) vive en
# carro/servicios.py, que es el único dueño de esa lógica.
# ============================================================
class AgregarAlCarroSerializer(serializers.Serializer):
    """Datos para agregar un producto al carro."""

    producto = serializers.PrimaryKeyRelatedField(
        queryset=Producto.objects.all(),
        help_text="Id del producto que se agrega al carro.",
        error_messages={
            "does_not_exist": "No existe un producto con ese id.",
            "incorrect_type": "El id del producto debe ser un número entero.",
        },
    )
    cantidad = serializers.IntegerField(
        min_value=1,
        default=1,
        help_text="Unidades que se agregan. Si el producto ya está en el carro, se suman.",
        error_messages={
            "min_value": "La cantidad debe ser al menos 1.",
            "invalid": "La cantidad debe ser un número entero.",
        },
    )

    def validate_producto(self, valor):
        """Rechaza productos dados de baja antes de llegar al servicio."""
        if not valor.activo:
            raise serializers.ValidationError(
                f"«{valor.nombre}» está dado de baja y no se puede comprar."
            )
        return valor


# ============================================================
# BLOQUE 4 — MODIFICAR LA CANTIDAD (ESCRITURA)
# Cuerpo de PATCH /api/carro/items/{producto_id}/. Fija la
# cantidad exacta del ítem, no la suma.
# ============================================================
class ActualizarCantidadSerializer(serializers.Serializer):
    """Nueva cantidad exacta para un ítem del carro."""

    cantidad = serializers.IntegerField(
        min_value=1,
        help_text="Cantidad exacta que queda en el carro para ese producto.",
        error_messages={
            "min_value": "La cantidad debe ser al menos 1. Para quitar el producto use DELETE.",
            "invalid": "La cantidad debe ser un número entero.",
        },
    )
