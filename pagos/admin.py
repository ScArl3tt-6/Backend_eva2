# ============================================================
# pagos/admin.py — REGISTRO DE PAGOS WEBPAY EN DJANGO ADMIN
# Responsabilidad: revisar los intentos de pago con Webpay Plus
# desde /admin/, como apoyo del criterio "Django Admin" de la
# unidad.
#
# Todos los campos son de solo lectura: un pago Webpay es un
# registro de auditoría de lo que respondió Transbank, igual que
# HistorialEstadoOrden (ordenes/admin.py). Nadie debe "arreglar" a
# mano el resultado de una pasarela de pago desde el admin.
# ============================================================

from django.contrib import admin

from .models import PagoWebpay


@admin.register(PagoWebpay)
class PagoWebpayAdmin(admin.ModelAdmin):
    """Consulta de los intentos de pago con Webpay Plus."""

    list_display = [
        "token_corto",
        "orden",
        "monto_legible",
        "estado",
        "authorization_code",
        "card_number",
        "creado_en",
    ]
    list_filter = ["estado", "creado_en"]
    search_fields = ["token", "buy_order", "orden__codigo", "orden__usuario__username"]
    ordering = ["-creado_en"]
    list_per_page = 25
    list_select_related = ["orden", "orden__usuario"]
    date_hierarchy = "creado_en"
    readonly_fields = [campo.name for campo in PagoWebpay._meta.fields]

    def has_add_permission(self, request):
        """Un pago Webpay solo lo crea el servicio, nunca el admin."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Se conserva como evidencia del intento, igual que el resto del historial."""
        return False

    @admin.display(description="token")
    def token_corto(self, obj):
        """Primeros ocho caracteres del token."""
        return f"{obj.token[:8]}…"

    @admin.display(description="monto")
    def monto_legible(self, obj):
        """Monto en pesos chilenos con separador de miles."""
        return f"${obj.monto:,.0f}".replace(",", ".")
