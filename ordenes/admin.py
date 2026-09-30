# ============================================================
# ordenes/admin.py — REGISTRO DE ÓRDENES EN DJANGO ADMIN
# Responsabilidad: revisar órdenes, su detalle con precios
# congelados y su historial de estados desde /admin/, con
# list_display, list_filter y search_fields, como apoyo del
# criterio "Django Admin" de la unidad.
#
# Los detalles y el historial se declaran de solo lectura a
# propósito: cambiar un precio congelado o borrar un registro de
# auditoría a mano rompería la trazabilidad de la venta. Los
# cambios de estado deben hacerse por /panel/ordenes/ o por la API,
# que pasan por ordenes/servicios.py y mueven el stock como
# corresponde.
# ============================================================

from django.contrib import admin

from .models import DetalleOrden, HistorialEstadoOrden, Orden


# ============================================================
# BLOQUE 1 — DETALLE DE LA ORDEN EN LÍNEA (SOLO LECTURA)
# ============================================================
class DetalleOrdenInline(admin.TabularInline):
    """Líneas de la orden con su precio congelado."""

    model = DetalleOrden
    extra = 0
    can_delete = False
    fields = ["producto", "cantidad", "precio_unitario", "subtotal_legible"]
    readonly_fields = ["producto", "cantidad", "precio_unitario", "subtotal_legible"]

    def has_add_permission(self, request, obj=None):
        """Las líneas solo las crea el checkout, nunca el admin."""
        return False

    @admin.display(description="subtotal")
    def subtotal_legible(self, obj):
        """cantidad × precio congelado."""
        if obj.pk is None:
            return "—"
        return f"${obj.subtotal:,.0f}".replace(",", ".")


# ============================================================
# BLOQUE 2 — HISTORIAL EN LÍNEA (SOLO LECTURA)
# ============================================================
class HistorialEstadoOrdenInline(admin.TabularInline):
    """Línea de tiempo de los cambios de estado de la orden."""

    model = HistorialEstadoOrden
    extra = 0
    can_delete = False
    fields = ["fecha", "estado_anterior", "estado_nuevo", "cambiado_por", "observacion"]
    readonly_fields = fields
    ordering = ["fecha"]

    def has_add_permission(self, request, obj=None):
        """El historial lo escribe el servicio de órdenes, no el admin."""
        return False


# ============================================================
# BLOQUE 3 — ÓRDENES
# ============================================================
@admin.register(Orden)
class OrdenAdmin(admin.ModelAdmin):
    """Administración de las órdenes de compra."""

    list_display = ["codigo_corto", "usuario", "estado", "total_legible", "creada_en", "pagada_en"]
    list_filter = ["estado", "creada_en", "pagada_en"]
    search_fields = ["codigo", "usuario__username", "usuario__email"]
    ordering = ["-creada_en"]
    list_per_page = 25
    list_select_related = ["usuario"]
    date_hierarchy = "creada_en"
    readonly_fields = ["codigo", "creada_en", "actualizada_en", "pagada_en", "total_legible"]
    inlines = [DetalleOrdenInline, HistorialEstadoOrdenInline]

    fieldsets = (
        ("Identificación", {"fields": ("codigo", "usuario")}),
        (
            "Estado",
            {
                "fields": ("estado", "pagada_en"),
                "description": (
                    "Para cambiar el estado moviendo el stock, use /panel/ordenes/ "
                    "o PATCH /api/ordenes/{id}/estado/."
                ),
            },
        ),
        ("Totales y fechas", {"fields": ("total_legible", "creada_en", "actualizada_en")}),
    )

    @admin.display(description="número de orden")
    def codigo_corto(self, obj):
        """Primeros ocho caracteres del UUID."""
        return obj.codigo_corto

    @admin.display(description="total")
    def total_legible(self, obj):
        """Total calculado sumando el detalle."""
        return f"${obj.total:,.0f}".replace(",", ".")


# ============================================================
# BLOQUE 4 — DETALLES Y HISTORIAL COMO LISTADOS PROPIOS
# Permiten buscar, por ejemplo, todas las ventas de un SKU concreto
# o todas las cancelaciones registradas.
# ============================================================
@admin.register(DetalleOrden)
class DetalleOrdenAdmin(admin.ModelAdmin):
    """Consulta de las líneas de venta con precios congelados."""

    list_display = ["orden", "producto", "cantidad", "precio_unitario"]
    list_filter = ["orden__estado", "producto__categoria", "producto__marca"]
    search_fields = ["orden__codigo", "producto__nombre", "producto__sku"]
    ordering = ["-orden__creada_en"]
    list_per_page = 25
    list_select_related = ["orden", "producto"]
    readonly_fields = ["orden", "producto", "cantidad", "precio_unitario"]


@admin.register(HistorialEstadoOrden)
class HistorialEstadoOrdenAdmin(admin.ModelAdmin):
    """Consulta del historial de cambios de estado (auditoría)."""

    list_display = ["orden", "estado_anterior", "estado_nuevo", "cambiado_por", "fecha"]
    list_filter = ["estado_nuevo", "estado_anterior", "fecha"]
    search_fields = ["orden__codigo", "cambiado_por__username", "observacion"]
    ordering = ["-fecha"]
    list_per_page = 25
    list_select_related = ["orden", "cambiado_por"]
    readonly_fields = ["orden", "estado_anterior", "estado_nuevo", "cambiado_por", "fecha", "observacion"]
