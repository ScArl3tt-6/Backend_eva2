# ============================================================
# pagos/models.py — INTENTOS DE PAGO CON WEBPAY PLUS
# Responsabilidad: dejar constancia de cada intento de pago con
# Transbank Webpay Plus, como lo entrega la propia pasarela: no se
# inventa ni se recalcula nada acá, se guarda la respuesta cruda de
# Transbank junto con los campos que la interfaz necesita mostrar.
#
# Por qué una app aparte y no un campo más de Orden: una orden puede
# tener más de un intento de pago (uno rechazado y, más tarde, uno
# aprobado), y el medio de pago es un dominio propio —ajeno a lo que
# es una orden— igual que "usuarios", "catalogo" o "carro" son
# dominios propios en este proyecto. Así PagoWebpay queda como el
# registro de auditoría de la pasarela, y Orden sigue representando
# solo el negocio puro de la venta.
# ============================================================

from django.db import models

from ordenes.models import Orden


# ============================================================
# BLOQUE 1 — ESTADOS DEL INTENTO DE PAGO
# No confundir con EstadoOrden (ordenes/models.py): esto es el
# estado del INTENTO en Webpay, no el estado de la orden.
#   INICIADO            — se creó la transacción en Transbank, el
#                          cliente todavía está en el formulario.
#   APROBADO            — Transbank autorizó y pagar_orden() ya
#                          descontó el stock.
#   RECHAZADO           — Transbank no autorizó el pago.
#   ANULADO_POR_USUARIO — el cliente canceló en el formulario.
#   EXPIRADO            — venció el tiempo del formulario de pago.
#   REEMBOLSADO         — Transbank aprobó, pero no había stock: se
#                          hizo el refund y la orden sigue PENDIENTE.
#   ERROR               — error de formulario o inconsistencia (por
#                          ejemplo el monto no coincide).
# ============================================================
class EstadoPagoWebpay(models.TextChoices):
    """Estados del intento de pago con Webpay Plus."""

    INICIADO = "INICIADO", "Iniciado"
    APROBADO = "APROBADO", "Aprobado"
    RECHAZADO = "RECHAZADO", "Rechazado"
    ANULADO_POR_USUARIO = "ANULADO_POR_USUARIO", "Anulado por el usuario"
    EXPIRADO = "EXPIRADO", "Expirado"
    REEMBOLSADO = "REEMBOLSADO", "Reembolsado"
    ERROR = "ERROR", "Error"


# ============================================================
# BLOQUE 2 — PAGO WEBPAY
# token es único porque Transbank lo es: con él se identifica cada
# intento sin ambigüedad y es la clave que usa confirmar_pago_webpay
# para la idempotencia (ver pagos/servicios.py).
# PROTECT sobre orden: el historial de intentos de pago de una orden
# nunca debe desaparecer, igual que el resto del proyecto no borra
# filas con valor de negocio.
# ============================================================
class PagoWebpay(models.Model):
    """Un intento de pago de una orden a través de Webpay Plus."""

    orden = models.ForeignKey(
        Orden,
        on_delete=models.PROTECT,
        related_name="pagos_webpay",
        verbose_name="orden",
    )
    token = models.CharField(
        "token de Transbank",
        max_length=64,
        unique=True,
        help_text="Token que identifica la transacción en Webpay Plus.",
    )
    buy_order = models.CharField(
        "orden de compra (buy_order)",
        max_length=26,
        help_text="Identificador corto que Transbank exige (máximo 26 caracteres).",
    )
    session_id = models.CharField(
        "id de sesión",
        max_length=61,
    )
    monto = models.PositiveIntegerField(
        "monto",
        help_text="Monto en pesos chilenos (CLP), sin decimales.",
    )
    estado = models.CharField(
        "estado",
        max_length=20,
        choices=EstadoPagoWebpay.choices,
        default=EstadoPagoWebpay.INICIADO,
        db_index=True,
    )
    response_code = models.IntegerField(
        "código de respuesta",
        null=True,
        blank=True,
        help_text="0 significa aprobado; cualquier otro valor es un rechazo de Transbank.",
    )
    authorization_code = models.CharField(
        "código de autorización",
        max_length=16,
        blank=True,
    )
    payment_type_code = models.CharField(
        "tipo de pago",
        max_length=3,
        blank=True,
        help_text="Código de Transbank (por ejemplo VD = Venta Débito, VN = Venta Normal).",
    )
    card_number = models.CharField(
        "últimos 4 dígitos de la tarjeta",
        max_length=4,
        blank=True,
        help_text="Es lo único que Transbank entrega de la tarjeta; nunca el número completo.",
    )
    respuesta_cruda = models.JSONField(
        "respuesta cruda de Transbank",
        default=dict,
        blank=True,
        help_text="Último JSON que devolvió Transbank (create, commit o refund), tal cual.",
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        verbose_name = "pago Webpay"
        verbose_name_plural = "pagos Webpay"
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["orden", "-creado_en"], name="pago_webpay_orden_idx"),
            models.Index(fields=["estado"], name="pago_webpay_estado_idx"),
        ]

    def __str__(self) -> str:
        """Token abreviado, monto y estado, como se ve en el admin."""
        return f"Webpay {self.token[:8]}… — ${self.monto} ({self.get_estado_display()})"
