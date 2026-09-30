# ============================================================
# catalogo/models.py — CATEGORÍAS, MARCAS Y PRODUCTOS
# Responsabilidad: modelar el catálogo de componentes informáticos
# en 3.ª forma normal.
#
# Normalización aplicada:
#   1FN — todos los campos son atómicos (no hay listas ni textos
#         con varios valores separados por comas).
#   2FN — cada tabla tiene clave primaria simple y todos sus
#         campos dependen por completo de esa clave.
#   3FN — Producto NO repite el nombre de la categoría ni el de la
#         marca: solo guarda las claves foráneas. Tampoco guarda
#         valores calculables (subtotales o totales).
# ============================================================

from django.core.validators import MinValueValidator
from django.db import models


# ============================================================
# BLOQUE 1 — MODELO BASE CON BORRADO LÓGICO
# Clase abstracta que aporta el campo "activo" y las marcas de
# tiempo a las tres entidades del catálogo. Regla de la pauta:
# nada de negocio se borra físicamente, "eliminar" es activo=False.
# Al ser abstract no genera tabla propia, así que no rompe la
# normalización.
# ============================================================
class ModeloActivable(models.Model):
    """Base reutilizable con borrado lógico y auditoría de fechas."""

    activo = models.BooleanField(
        "activo",
        default=True,
        db_index=True,
        help_text="False significa eliminado lógicamente: deja de verse en el catálogo público.",
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        abstract = True

    def desactivar(self) -> None:
        """Baja lógica: el registro deja de estar disponible pero se conserva."""
        if self.activo:
            self.activo = False
            self.save(update_fields=["activo", "actualizado_en"])

    def reactivar(self) -> None:
        """Revierte la baja lógica y vuelve a publicar el registro."""
        if not self.activo:
            self.activo = True
            self.save(update_fields=["activo", "actualizado_en"])


# ============================================================
# BLOQUE 2 — CATEGORÍA
# Agrupa los componentes por tipo (Procesadores, Tarjetas de
# Video, Memorias RAM, ...). El nombre es único para que no
# existan dos categorías equivalentes, lo que garantiza que la
# clave foránea de Producto apunte a un único significado.
# ============================================================
class Categoria(ModeloActivable):
    """Tipo de componente informático que agrupa productos."""

    nombre = models.CharField(
        "nombre",
        max_length=80,
        unique=True,
        help_text="Por ejemplo: Procesadores, Tarjetas de Video, Memorias RAM.",
    )
    descripcion = models.TextField(
        "descripción",
        blank=True,
        help_text="Explicación breve de qué componentes incluye la categoría.",
    )
    icono = models.CharField(
        "icono",
        max_length=60,
        blank=True,
        default="bi-cpu",
        help_text="Clase de Bootstrap Icons, por ejemplo bi-cpu o bi-gpu-card.",
    )

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["nombre"],
                name="categoria_nombre_unico",
                violation_error_message="Ya existe una categoría con ese nombre.",
            ),
        ]
        indexes = [models.Index(fields=["activo", "nombre"], name="categoria_activo_idx")]

    def __str__(self) -> str:
        """Nombre de la categoría, usado en selectores y migas de pan."""
        return self.nombre

    @property
    def total_productos_activos(self) -> int:
        """Cuenta los productos publicados de la categoría."""
        return self.productos.filter(activo=True).count()


# ============================================================
# BLOQUE 3 — MARCA
# Fabricante del componente (Intel, AMD, NVIDIA, ...). Se separa
# en su propia tabla justamente para cumplir la 3FN: el país de
# origen depende de la marca, no del producto, así que no puede
# vivir dentro de Producto.
# ============================================================
class Marca(ModeloActivable):
    """Fabricante de los componentes del catálogo."""

    nombre = models.CharField(
        "nombre",
        max_length=80,
        unique=True,
        help_text="Por ejemplo: Intel, AMD, NVIDIA, Kingston.",
    )
    pais_origen = models.CharField(
        "país de origen",
        max_length=60,
        blank=True,
        help_text="Opcional. Depende de la marca, no del producto (3FN).",
    )

    class Meta:
        verbose_name = "marca"
        verbose_name_plural = "marcas"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["nombre"],
                name="marca_nombre_unico",
                violation_error_message="Ya existe una marca con ese nombre.",
            ),
        ]
        indexes = [models.Index(fields=["activo", "nombre"], name="marca_activo_idx")]

    def __str__(self) -> str:
        """Nombre de la marca."""
        return self.nombre

    @property
    def total_productos_activos(self) -> int:
        """Cuenta los productos publicados de la marca."""
        return self.productos.filter(activo=True).count()


# ============================================================
# BLOQUE 4 — PRODUCTO
# Componente concreto que se vende. Guarda solo lo que depende de
# él mismo: SKU, nombre, descripción, precio y stock, más las
# claves foráneas a Categoria y Marca.
#
# Decisiones de modelado:
#   · precio con decimal_places=0 porque el peso chileno no usa
#     decimales; DecimalField (no Float) para no perder exactitud.
#   · PROTECT en las relaciones: no se puede borrar una categoría
#     o marca que tenga productos, lo que preserva la integridad
#     histórica de las ventas ya realizadas.
#   · El stock es el stock físico disponible; solo lo modifica el
#     pago o la cancelación de una orden (ordenes/servicios.py).
# ============================================================
class Producto(ModeloActivable):
    """Componente informático con precio unitario y stock físico."""

    sku = models.CharField(
        "código SKU",
        max_length=40,
        unique=True,
        help_text="Código interno único. Se guarda siempre en mayúsculas.",
    )
    nombre = models.CharField(
        "nombre",
        max_length=160,
        help_text="Nombre comercial del componente.",
    )
    descripcion = models.TextField(
        "descripción",
        blank=True,
        help_text="Especificaciones técnicas del componente.",
    )
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        related_name="productos",
        verbose_name="categoría",
        help_text="Categoría a la que pertenece. Se guarda la clave, no el nombre (3FN).",
    )
    marca = models.ForeignKey(
        Marca,
        on_delete=models.PROTECT,
        related_name="productos",
        verbose_name="marca",
        help_text="Fabricante. Se guarda la clave, no el nombre (3FN).",
    )
    precio = models.DecimalField(
        "precio unitario",
        max_digits=12,
        decimal_places=0,
        validators=[MinValueValidator(1, message="El precio debe ser mayor que cero.")],
        help_text="Precio de lista en pesos chilenos, sin decimales.",
    )
    stock = models.PositiveIntegerField(
        "stock disponible",
        default=0,
        help_text="Unidades físicas en bodega. Solo el pago o la cancelación lo modifican.",
    )

    class Meta:
        verbose_name = "producto"
        verbose_name_plural = "productos"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["sku"],
                name="producto_sku_unico",
                violation_error_message="Ya existe un producto con ese código SKU.",
            ),
            # Última barrera en la base de datos: ni una condición de
            # carrera ni una consulta manual pueden dejar un precio
            # menor o igual a cero.
            models.CheckConstraint(
                condition=models.Q(precio__gt=0),
                name="producto_precio_positivo",
                violation_error_message="El precio debe ser mayor que cero.",
            ),
            # Garantiza que el descuento de stock nunca deje valores
            # negativos, aun con pagos simultáneos.
            models.CheckConstraint(
                condition=models.Q(stock__gte=0),
                name="producto_stock_no_negativo",
                violation_error_message="El stock no puede ser negativo.",
            ),
        ]
        indexes = [
            models.Index(fields=["categoria"], name="producto_categoria_idx"),
            models.Index(fields=["marca"], name="producto_marca_idx"),
            models.Index(fields=["precio"], name="producto_precio_idx"),
            models.Index(fields=["activo", "nombre"], name="producto_activo_idx"),
        ]

    def __str__(self) -> str:
        """SKU y nombre, el formato que usan los listados y el admin."""
        return f"{self.sku} — {self.nombre}"

    # ============================================================
    # BLOQUE 5 — NORMALIZACIÓN DEL SKU
    # El SKU se guarda siempre en mayúsculas y sin espacios
    # sobrantes, de modo que "rtx-4060" y "RTX-4060" no puedan
    # coexistir como dos productos distintos.
    # ============================================================
    def save(self, *args, **kwargs):
        """Normaliza el SKU antes de persistir el producto."""
        if self.sku:
            self.sku = self.sku.strip().upper()
        super().save(*args, **kwargs)

    # ============================================================
    # BLOQUE 6 — PROPIEDADES DE DISPONIBILIDAD
    # Datos derivados que NO se guardan en la tabla (3FN): se
    # calculan cada vez desde stock y activo.
    # ============================================================
    @property
    def disponible(self) -> bool:
        """True si el producto se puede comprar ahora mismo."""
        return self.activo and self.stock > 0

    @property
    def estado_stock(self) -> str:
        """Clasifica el stock para mostrar una etiqueta en la interfaz."""
        if self.stock == 0:
            return "Sin stock"
        if self.stock <= 5:
            return "Últimas unidades"
        return "Disponible"
