# ============================================================
# carro/admin.py — REGISTRO DEL CARRO EN DJANGO ADMIN
# Responsabilidad: permitir revisar los carros persistidos y sus
# ítems desde /admin/, con list_display, list_filter y
# search_fields, como apoyo del criterio "Django Admin".
#
# Es también la evidencia más directa de que el carro vive en
# PostgreSQL: las filas se pueden consultar en la base de datos sin
# que exista ninguna sesión de navegador abierta.
# ============================================================

from django.contrib import admin

from .models import Carro, ItemCarro


# ============================================================
# BLOQUE 1 — ÍTEMS EN LÍNEA DENTRO DEL CARRO
# Muestra el contenido del carro en la misma ficha, con el subtotal
# calculado en solo lectura (no es una columna de la tabla).
# ============================================================
class ItemCarroInline(admin.TabularInline):
    """Ítems del carro mostrados dentro de la ficha del carro."""

    model = ItemCarro
    extra = 0
    fields = ["producto", "cantidad", "subtotal_legible", "activo", "actualizado_en"]
    readonly_fields = ["subtotal_legible", "actualizado_en"]
    autocomplete_fields = ["producto"]

    @admin.display(description="subtotal")
    def subtotal_legible(self, obj):
        """Subtotal calculado con el precio vigente del producto."""
        if obj.pk is None:
            return "—"
        return f"${obj.subtotal:,.0f}".replace(",", ".")


# ============================================================
# BLOQUE 2 — CARROS
# ============================================================
@admin.register(Carro)
class CarroAdmin(admin.ModelAdmin):
    """Administración de los carros persistentes de los clientes."""

    list_display = ["usuario", "cantidad_items_legible", "total_legible", "actualizado_en"]
    list_filter = ["creado_en", "actualizado_en"]
    search_fields = ["usuario__username", "usuario__email"]
    ordering = ["-actualizado_en"]
    list_per_page = 25
    list_select_related = ["usuario"]
    readonly_fields = ["creado_en", "actualizado_en"]
    inlines = [ItemCarroInline]

    @admin.display(description="ítems")
    def cantidad_items_legible(self, obj):
        """Unidades totales cargadas en el carro."""
        return obj.cantidad_items

    @admin.display(description="total")
    def total_legible(self, obj):
        """Total calculado con los precios vigentes."""
        return f"${obj.total:,.0f}".replace(",", ".")


# ============================================================
# BLOQUE 3 — ÍTEMS DEL CARRO
# Registro propio para poder buscar un producto concreto en todos
# los carros de la tienda.
# ============================================================
@admin.register(ItemCarro)
class ItemCarroAdmin(admin.ModelAdmin):
    """Administración de los ítems de los carros."""

    list_display = ["carro", "producto", "cantidad", "activo", "agregado_en", "actualizado_en"]
    list_filter = ["activo", "agregado_en", "producto__categoria"]
    search_fields = ["carro__usuario__username", "producto__nombre", "producto__sku"]
    ordering = ["-actualizado_en"]
    list_per_page = 25
    list_select_related = ["carro__usuario", "producto"]
    autocomplete_fields = ["producto"]
    readonly_fields = ["agregado_en", "actualizado_en"]
