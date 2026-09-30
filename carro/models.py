# ============================================================
# carro/models.py — CARRO DE COMPRAS PERSISTENTE
# Responsabilidad: modelar el carro de compras del cliente y sus
# ítems, siempre en PostgreSQL.
#
# Requisito clave de la pauta: el carro NO vive en la sesión, ni
# en cookies, ni en localStorage. Está ligado al id del usuario
# mediante una relación 1 a 1, por lo que sobrevive al logout, al
# cierre del navegador, a la caída del servidor y al cambio de
# dispositivo: al volver a entrar, los ítems siguen ahí.
#
# Normalización: ItemCarro no guarda el precio ni el subtotal. El
# precio vigente depende del producto (dependencia transitiva que
# la 3FN prohíbe duplicar) y el subtotal es calculable, así que
# ambos son propiedades, no columnas.
# ============================================================

from decimal import Decimal

from django.conf import settings
from django.db import models

from catalogo.models import Producto


# ============================================================
# BLOQUE 1 — CARRO
# Un único carro por usuario (OneToOneField). La señal post_save
# de usuarios/signals.py lo crea automáticamente al registrarse
# un cliente, de modo que nunca falta el carro al agregar el
# primer producto.
# ============================================================
class Carro(models.Model):
    """Carro de compras persistente, uno por usuario."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="carro",
        verbose_name="usuario",
        help_text="Relación 1 a 1: el carro pertenece a este usuario y a ningún otro.",
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        verbose_name = "carro"
        verbose_name_plural = "carros"
        ordering = ["-actualizado_en"]
        indexes = [models.Index(fields=["usuario"], name="carro_usuario_idx")]

    def __str__(self) -> str:
        """Identifica el carro por el usuario dueño."""
        return f"Carro de {self.usuario.username}"

    # ============================================================
    # BLOQUE 2 — ÍTEMS VIGENTES
    # Solo los ítems activos forman parte del carro: quitar un
    # producto es una baja lógica (activo=False), nunca un DELETE.
    # ============================================================
    @property
    def items_activos(self):
        """Ítems que el cliente tiene realmente en el carro."""
        return self.items.filter(activo=True).select_related("producto")

    # ============================================================
    # BLOQUE 3 — VALORES CALCULADOS (NO SE GUARDAN)
    # total y cantidad_items se recalculan al leerlos, con el
    # precio vigente del catálogo. Guardarlos violaría la 3FN y
    # además quedarían desactualizados al cambiar un precio.
    # ============================================================
    @property
    def total(self) -> Decimal:
        """Suma de los subtotales de los ítems, con precios vigentes."""
        return sum((item.subtotal for item in self.items_activos), Decimal("0"))

    @property
    def cantidad_items(self) -> int:
        """Cantidad total de unidades cargadas en el carro."""
        return sum(item.cantidad for item in self.items_activos)

    @property
    def esta_vacio(self) -> bool:
        """True cuando no hay ningún ítem activo; bloquea el checkout."""
        return not self.items.filter(activo=True).exists()


# ============================================================
# BLOQUE 4 — ÍTEM DEL CARRO
# Une un carro con un producto y la cantidad pedida.
#
# Reglas que impone la base de datos:
#   · UniqueConstraint(carro, producto): un producto no puede
#     aparecer dos veces en el mismo carro. Al agregar un producto
#     repetido, el servicio suma la cantidad al ítem existente.
#   · CheckConstraint cantidad >= 1: no existen ítems en cero.
#   · PROTECT sobre producto: un producto que está en algún carro
#     no puede borrarse físicamente.
# ============================================================
class ItemCarro(models.Model):
    """Producto y cantidad dentro del carro de un cliente."""

    carro = models.ForeignKey(
        Carro,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="carro",
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="items_carro",
        verbose_name="producto",
        help_text="El precio no se copia aquí: se lee del producto (3FN).",
    )
    cantidad = models.PositiveIntegerField(
        "cantidad",
        default=1,
        help_text="Unidades pedidas. Debe ser al menos 1.",
    )
    activo = models.BooleanField(
        "activo",
        default=True,
        db_index=True,
        help_text="False significa que el ítem fue quitado del carro (baja lógica).",
    )
    agregado_en = models.DateTimeField("agregado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        verbose_name = "ítem del carro"
        verbose_name_plural = "ítems del carro"
        ordering = ["producto__nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["carro", "producto"],
                name="item_unico_por_carro",
                violation_error_message="Ese producto ya está en el carro.",
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad__gte=1),
                name="item_carro_cantidad_minima",
                violation_error_message="La cantidad debe ser al menos 1.",
            ),
        ]
        indexes = [
            models.Index(fields=["carro", "activo"], name="item_carro_activo_idx"),
        ]

    def __str__(self) -> str:
        """Cantidad y producto, como se lee en el detalle del carro."""
        return f"{self.cantidad} × {self.producto.nombre}"

    # ============================================================
    # BLOQUE 5 — SUBTOTAL CALCULADO
    # cantidad × precio vigente del producto. No se guarda en la
    # tabla porque es un dato derivado (3FN) y porque el carro debe
    # reflejar siempre el precio actual del catálogo: el precio se
    # congela recién en el checkout, dentro de DetalleOrden.
    # ============================================================
    @property
    def subtotal(self) -> Decimal:
        """Precio vigente del producto multiplicado por la cantidad."""
        return self.producto.precio * self.cantidad

    @property
    def precio_vigente(self) -> Decimal:
        """Precio actual del catálogo para este producto."""
        return self.producto.precio

    @property
    def stock_suficiente(self) -> bool:
        """Aviso informativo: indica si el stock actual cubre la cantidad."""
        return self.producto.stock >= self.cantidad
