# ============================================================
# catalogo/serializers.py — TRADUCCIÓN JSON DEL CATÁLOGO
# Responsabilidad: convertir categorías, marcas y productos entre
# JSON y modelo, validando las reglas del negocio con mensajes en
# español.
#
# Decisión de diseño: para Producto existen DOS serializers.
#   · ProductoSerializer (lectura) muestra categoría y marca
#     anidadas (id + nombre), cómodo para quien consume la API.
#   · ProductoEscrituraSerializer (escritura) recibe solo los ids,
#     que es lo que corresponde a las claves foráneas del modelo.
# Separarlos evita el enredo clásico de un serializer que intenta
# leer objetos anidados y escribir identificadores a la vez.
# ============================================================

from rest_framework import serializers

from .models import Categoria, Marca, Producto


# ============================================================
# BLOQUE 1 — CATEGORÍA
# El nombre es único; la validación se hace sin distinguir
# mayúsculas para que no entren "Procesadores" y "procesadores"
# como dos categorías distintas.
# ============================================================
class CategoriaSerializer(serializers.ModelSerializer):
    """Serializer de categorías, con el conteo de productos publicados."""

    total_productos_activos = serializers.IntegerField(read_only=True)

    class Meta:
        model = Categoria
        fields = [
            "id",
            "nombre",
            "descripcion",
            "icono",
            "activo",
            "total_productos_activos",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = ["id", "creado_en", "actualizado_en"]

    def validate_nombre(self, valor):
        """Impide nombres repetidos, ignorando mayúsculas y espacios."""
        limpio = valor.strip()
        consulta = Categoria.objects.filter(nombre__iexact=limpio)
        if self.instance is not None:
            consulta = consulta.exclude(pk=self.instance.pk)
        if consulta.exists():
            raise serializers.ValidationError("Ya existe una categoría con ese nombre.")
        return limpio


# ============================================================
# BLOQUE 2 — MARCA
# Mismo criterio de unicidad que la categoría.
# ============================================================
class MarcaSerializer(serializers.ModelSerializer):
    """Serializer de marcas, con el conteo de productos publicados."""

    total_productos_activos = serializers.IntegerField(read_only=True)

    class Meta:
        model = Marca
        fields = [
            "id",
            "nombre",
            "pais_origen",
            "activo",
            "total_productos_activos",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = ["id", "creado_en", "actualizado_en"]

    def validate_nombre(self, valor):
        """Impide marcas repetidas, ignorando mayúsculas y espacios."""
        limpio = valor.strip()
        consulta = Marca.objects.filter(nombre__iexact=limpio)
        if self.instance is not None:
            consulta = consulta.exclude(pk=self.instance.pk)
        if consulta.exists():
            raise serializers.ValidationError("Ya existe una marca con ese nombre.")
        return limpio


# ============================================================
# BLOQUE 3 — REFERENCIAS ANIDADAS COMPACTAS
# Se usan dentro de ProductoSerializer para mostrar la categoría y
# la marca con su id y su nombre, sin arrastrar todos los campos.
# ============================================================
class CategoriaAnidadaSerializer(serializers.ModelSerializer):
    """Vista reducida de la categoría dentro de un producto."""

    class Meta:
        model = Categoria
        fields = ["id", "nombre", "icono"]


class MarcaAnidadaSerializer(serializers.ModelSerializer):
    """Vista reducida de la marca dentro de un producto."""

    class Meta:
        model = Marca
        fields = ["id", "nombre"]


# ============================================================
# BLOQUE 4 — PRODUCTO (LECTURA)
# Muestra el producto listo para consumir: categoría y marca
# anidadas, disponibilidad y estado del stock ya calculados. Los
# datos derivados se leen de las propiedades del modelo, nunca de
# columnas guardadas (3FN).
# ============================================================
class ProductoSerializer(serializers.ModelSerializer):
    """Representación de lectura de un producto del catálogo."""

    categoria = CategoriaAnidadaSerializer(read_only=True)
    marca = MarcaAnidadaSerializer(read_only=True)
    disponible = serializers.BooleanField(read_only=True)
    estado_stock = serializers.CharField(read_only=True)

    class Meta:
        model = Producto
        fields = [
            "id",
            "sku",
            "nombre",
            "descripcion",
            "categoria",
            "marca",
            "precio",
            "stock",
            "disponible",
            "estado_stock",
            "activo",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = ["id", "creado_en", "actualizado_en"]


# ============================================================
# BLOQUE 5 — PRODUCTO (ESCRITURA)
# Recibe categoria y marca como identificadores. Valida el SKU
# único (normalizado a mayúsculas), el precio mayor que cero y el
# stock no negativo, con mensajes claros en español. Las mismas
# reglas están respaldadas por CheckConstraint en la base de datos.
# ============================================================
class ProductoEscrituraSerializer(serializers.ModelSerializer):
    """Serializer de alta y edición de productos, por ids de relación."""

    class Meta:
        model = Producto
        fields = [
            "id",
            "sku",
            "nombre",
            "descripcion",
            "categoria",
            "marca",
            "precio",
            "stock",
            "activo",
        ]

    def validate_sku(self, valor):
        """Normaliza el SKU a mayúsculas y comprueba que sea único."""
        limpio = valor.strip().upper()
        if not limpio:
            raise serializers.ValidationError("El código SKU es obligatorio.")

        consulta = Producto.objects.filter(sku=limpio)
        if self.instance is not None:
            consulta = consulta.exclude(pk=self.instance.pk)
        if consulta.exists():
            raise serializers.ValidationError("Ya existe un producto con ese código SKU.")
        return limpio

    def validate_precio(self, valor):
        """El precio debe ser mayor que cero (regla del negocio y CheckConstraint)."""
        if valor is None or valor <= 0:
            raise serializers.ValidationError("El precio debe ser mayor que cero.")
        return valor

    def validate_stock(self, valor):
        """El stock nunca puede ser negativo."""
        if valor is None or valor < 0:
            raise serializers.ValidationError("El stock no puede ser negativo.")
        return valor

    def validate_categoria(self, valor):
        """No se permite publicar un producto en una categoría dada de baja."""
        if not valor.activo:
            raise serializers.ValidationError(
                "La categoría está dada de baja; reactívela antes de usarla."
            )
        return valor

    def validate_marca(self, valor):
        """No se permite publicar un producto con una marca dada de baja."""
        if not valor.activo:
            raise serializers.ValidationError(
                "La marca está dada de baja; reactívela antes de usarla."
            )
        return valor

    def to_representation(self, instance):
        """Tras crear o editar, responde con el formato de lectura completo."""
        return ProductoSerializer(instance, context=self.context).data
