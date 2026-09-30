# ============================================================
# ordenes/models.py — ORDEN DE COMPRA, DETALLE E HISTORIAL
# Responsabilidad: modelar la venta ya cerrada.
#
# Dos ideas centrales del negocio:
#   1) La orden congela los precios. DetalleOrden guarda
#      precio_unitario, que es un HECHO HISTÓRICO (el precio que
#      el cliente aceptó ese día), no una copia redundante del
#      catálogo: si mañana sube el precio del producto, la venta
#      ya realizada no cambia. Por eso no viola la 3FN.
#   2) El total NO se guarda. Es un valor calculable a partir del
#      detalle, así que se expone como propiedad y como anotación
#      de consulta con Sum(F("cantidad") * F("precio_unitario")).
# ============================================================

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Sum

from catalogo.models import Producto


# ============================================================
# BLOQUE 1 — CHOICES DE ESTADO
# Ciclo de vida de la orden. Con TextChoices el valor y la
# etiqueta visible quedan juntos y drf-spectacular los publica
# como enum en el esquema OpenAPI.
#   PENDIENTE  — creada por el checkout, sin tocar el stock.
#   PAGADO     — pago aprobado; el stock ya se descontó.
#   ENTREGADO  — estado final feliz.
#   CANCELADO  — estado final; si venía de PAGADO, repone el stock.
# ============================================================
class EstadoOrden(models.TextChoices):
    """Estados posibles de una orden de compra."""

    PENDIENTE = "PENDIENTE", "Pendiente de pago"
    PAGADO = "PAGADO", "Pagado"
    ENTREGADO = "ENTREGADO", "Entregado"
    CANCELADO = "CANCELADO", "Cancelado"


# ============================================================
# BLOQUE 2 — CONJUNTO DE CONSULTAS CON EL TOTAL ANOTADO
# Permite pedir el total a la base de datos en una sola consulta
# (sin recorrer los detalles en Python), evitando el problema
# N+1 en los listados de órdenes.
# ============================================================
class OrdenQuerySet(models.QuerySet):
    """Consultas reutilizables sobre órdenes."""

    def con_total(self):
        """Anota el total sumando cantidad × precio_unitario de cada detalle."""
        return self.annotate(
            total_anotado=Sum(F("detalles__cantidad") * F("detalles__precio_unitario"))
        )

    def con_relaciones(self):
        """Precarga usuario, detalles y productos para listados y fichas."""
        return self.select_related("usuario").prefetch_related(
            "detalles__producto", "historial__cambiado_por"
        )


# ============================================================
# BLOQUE 3 — ORDEN
# Cabecera de la venta. El campo "codigo" es un UUID: es el
# número de orden único que ve el cliente, imposible de adivinar
# o enumerar, a diferencia del id secuencial.
# PROTECT sobre usuario: un cliente con ventas registradas no
# puede desaparecer de la base (solo se desactiva).
# ============================================================
class Orden(models.Model):
    """Orden de compra con precios congelados en el momento del checkout."""

    codigo = models.UUIDField(
        "número de orden",
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Identificador único e irrepetible de la orden.",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ordenes",
        verbose_name="cliente",
    )
    estado = models.CharField(
        "estado",
        max_length=20,
        choices=EstadoOrden.choices,
        default=EstadoOrden.PENDIENTE,
        db_index=True,
        help_text="Avanza según las transiciones permitidas en ordenes/servicios.py.",
    )
    creada_en = models.DateTimeField("creada en", auto_now_add=True)
    pagada_en = models.DateTimeField(
        "pagada en",
        null=True,
        blank=True,
        help_text="Se llena cuando el pago se aprueba y se descuenta el stock.",
    )
    actualizada_en = models.DateTimeField("actualizada en", auto_now=True)

    objects = OrdenQuerySet.as_manager()

    class Meta:
        verbose_name = "orden"
        verbose_name_plural = "órdenes"
        ordering = ["-creada_en"]
        indexes = [
            models.Index(fields=["estado"], name="orden_estado_idx"),
            models.Index(fields=["usuario", "-creada_en"], name="orden_usuario_idx"),
            models.Index(fields=["-creada_en"], name="orden_fecha_idx"),
        ]

    def __str__(self) -> str:
        """Número de orden abreviado y estado, como se ve en los listados."""
        return f"Orden {str(self.codigo)[:8].upper()} ({self.get_estado_display()})"

    # ============================================================
    # BLOQUE 4 — TOTAL CALCULADO
    # No existe una columna "total": se suma el detalle. Se prefiere
    # el valor ya anotado por con_total() cuando está disponible,
    # para no repetir consultas en los listados.
    # ============================================================
    @property
    def total(self) -> Decimal:
        """Suma de cantidad × precio congelado de todos los detalles."""
        anotado = getattr(self, "total_anotado", None)
        if anotado is not None:
            return Decimal(anotado)
        agregado = self.detalles.aggregate(
            suma=Sum(F("cantidad") * F("precio_unitario"))
        )["suma"]
        return Decimal(agregado or 0)

    @property
    def cantidad_items(self) -> int:
        """Unidades totales compradas en la orden."""
        return self.detalles.aggregate(suma=Sum("cantidad"))["suma"] or 0

    @property
    def codigo_corto(self) -> str:
        """Primeros ocho caracteres del UUID, para mostrar en tablas."""
        return str(self.codigo)[:8].upper()

    # ============================================================
    # BLOQUE 5 — CONSULTAS DE ESTADO PARA LA INTERFAZ
    # Las plantillas usan estas propiedades para decidir qué
    # botones mostrar, sin repetir la lógica de transiciones que
    # vive en ordenes/servicios.py.
    # ============================================================
    @property
    def es_pendiente(self) -> bool:
        """True si la orden aún espera el pago."""
        return self.estado == EstadoOrden.PENDIENTE

    @property
    def es_pagada(self) -> bool:
        """True si el pago fue aprobado y el stock ya se descontó."""
        return self.estado == EstadoOrden.PAGADO

    @property
    def es_final(self) -> bool:
        """True si la orden ya no admite más cambios de estado."""
        return self.estado in {EstadoOrden.ENTREGADO, EstadoOrden.CANCELADO}


# ============================================================
# BLOQUE 6 — DETALLE DE LA ORDEN
# Una línea por producto comprado, con el precio congelado.
# UniqueConstraint(orden, producto) evita líneas duplicadas del
# mismo producto en una misma orden.
# PROTECT sobre producto: un producto vendido nunca se borra, de
# modo que el historial de ventas siempre se puede reconstruir.
# ============================================================
class DetalleOrden(models.Model):
    """Línea de una orden con la cantidad y el precio congelado."""

    orden = models.ForeignKey(
        Orden,
        on_delete=models.CASCADE,
        related_name="detalles",
        verbose_name="orden",
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="detalles_orden",
        verbose_name="producto",
    )
    cantidad = models.PositiveIntegerField(
        "cantidad",
        help_text="Unidades vendidas en esta línea.",
    )
    precio_unitario = models.DecimalField(
        "precio unitario congelado",
        max_digits=12,
        decimal_places=0,
        help_text="Precio vigente al hacer el checkout. Los cambios posteriores del catálogo no lo afectan.",
    )

    class Meta:
        verbose_name = "detalle de la orden"
        verbose_name_plural = "detalles de la orden"
        ordering = ["producto__nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["orden", "producto"],
                name="detalle_unico_por_orden",
                violation_error_message="Ese producto ya está en la orden.",
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad__gte=1),
                name="detalle_cantidad_minima",
                violation_error_message="La cantidad debe ser al menos 1.",
            ),
            models.CheckConstraint(
                condition=models.Q(precio_unitario__gt=0),
                name="detalle_precio_positivo",
                violation_error_message="El precio congelado debe ser mayor que cero.",
            ),
        ]
        indexes = [models.Index(fields=["orden"], name="detalle_orden_idx")]

    def __str__(self) -> str:
        """Línea legible con cantidad, producto y precio congelado."""
        return f"{self.cantidad} × {self.producto.nombre} a ${self.precio_unitario}"

    @property
    def subtotal(self) -> Decimal:
        """cantidad × precio congelado. Calculado, nunca almacenado (3FN)."""
        return self.precio_unitario * self.cantidad


# ============================================================
# BLOQUE 7 — HISTORIAL DE ESTADOS (AUDITORÍA)
# Registra cada transición de la orden: de qué estado a cuál,
# quién la hizo y cuándo. Sirve de evidencia ante un reclamo y
# permite mostrar la línea de tiempo en el detalle de la orden.
# cambiado_por admite null porque un pago automático o el arranque
# de datos de prueba pueden no tener usuario asociado.
# ============================================================
class HistorialEstadoOrden(models.Model):
    """Registro de auditoría de cada cambio de estado de una orden."""

    orden = models.ForeignKey(
        Orden,
        on_delete=models.CASCADE,
        related_name="historial",
        verbose_name="orden",
    )
    estado_anterior = models.CharField(
        "estado anterior",
        max_length=20,
        choices=EstadoOrden.choices,
        null=True,
        blank=True,
        help_text="Vacío en el primer registro, cuando la orden se crea.",
    )
    estado_nuevo = models.CharField(
        "estado nuevo",
        max_length=20,
        choices=EstadoOrden.choices,
    )
    cambiado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cambios_de_estado",
        verbose_name="cambiado por",
    )
    fecha = models.DateTimeField("fecha", auto_now_add=True)
    observacion = models.CharField(
        "observación",
        max_length=255,
        blank=True,
        help_text="Motivo del cambio, por ejemplo el detalle de una cancelación.",
    )

    class Meta:
        verbose_name = "cambio de estado"
        verbose_name_plural = "historial de estados"
        ordering = ["fecha", "id"]
        indexes = [models.Index(fields=["orden", "fecha"], name="historial_orden_idx")]

    def __str__(self) -> str:
        """Transición legible, por ejemplo 'PENDIENTE → PAGADO'."""
        origen = self.estado_anterior or "creada"
        return f"{origen} → {self.estado_nuevo}"
