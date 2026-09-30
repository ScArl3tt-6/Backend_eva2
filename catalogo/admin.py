# ============================================================
# catalogo/admin.py — REGISTRO DEL CATÁLOGO EN DJANGO ADMIN
# Responsabilidad: administrar categorías, marcas y productos desde
# /admin/, con list_display, list_filter y search_fields, como
# apoyo del criterio "Django Admin" de la unidad.
#
# Se agregan acciones masivas de baja lógica y reactivación, que
# respetan la regla del proyecto: nada se borra físicamente.
# ============================================================

from django.contrib import admin

from .models import Categoria, Marca, Producto


# ============================================================
# BLOQUE 1 — ACCIONES MASIVAS DE BAJA LÓGICA
# Reemplazan al borrado del admin: marcan activo=False o True sin
# eliminar filas, igual que hacen la API y las pantallas HTML.
# ============================================================
@admin.action(description="Dar de baja los registros seleccionados (baja lógica)")
def dar_de_baja(modeladmin, request, queryset):
    """Marca como inactivos los registros seleccionados."""
    total = queryset.update(activo=False)
    modeladmin.message_user(request, f"{total} registro(s) dados de baja. No se borró ninguna fila.")


@admin.action(description="Reactivar los registros seleccionados")
def reactivar(modeladmin, request, queryset):
    """Vuelve a publicar los registros seleccionados."""
    total = queryset.update(activo=True)
    modeladmin.message_user(request, f"{total} registro(s) reactivados.")


# ============================================================
# BLOQUE 2 — CATEGORÍAS
# ============================================================
@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    """Administración de categorías de componentes."""

    list_display = ["nombre", "icono", "total_productos_activos", "activo", "creado_en"]
    list_filter = ["activo", "creado_en"]
    search_fields = ["nombre", "descripcion"]
    ordering = ["nombre"]
    list_per_page = 25
    readonly_fields = ["creado_en", "actualizado_en"]
    actions = [dar_de_baja, reactivar]

    @admin.display(description="productos activos")
    def total_productos_activos(self, obj):
        """Cuenta los productos publicados de la categoría."""
        return obj.total_productos_activos


# ============================================================
# BLOQUE 3 — MARCAS
# ============================================================
@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin):
    """Administración de marcas fabricantes."""

    list_display = ["nombre", "pais_origen", "total_productos_activos", "activo", "creado_en"]
    list_filter = ["activo", "pais_origen", "creado_en"]
    search_fields = ["nombre", "pais_origen"]
    ordering = ["nombre"]
    list_per_page = 25
    readonly_fields = ["creado_en", "actualizado_en"]
    actions = [dar_de_baja, reactivar]

    @admin.display(description="productos activos")
    def total_productos_activos(self, obj):
        """Cuenta los productos publicados de la marca."""
        return obj.total_productos_activos


# ============================================================
# BLOQUE 4 — PRODUCTOS
# list_select_related evita el problema N+1 al mostrar la categoría
# y la marca en cada fila del listado.
# ============================================================
@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    """Administración de productos del catálogo."""

    list_display = ["sku", "nombre", "categoria", "marca", "precio", "stock", "activo"]
    list_filter = ["activo", "categoria", "marca", "creado_en"]
    search_fields = ["sku", "nombre", "descripcion", "marca__nombre", "categoria__nombre"]
    ordering = ["nombre"]
    list_per_page = 25
    list_select_related = ["categoria", "marca"]
    autocomplete_fields = ["categoria", "marca"]
    readonly_fields = ["creado_en", "actualizado_en"]
    actions = [dar_de_baja, reactivar]

    fieldsets = (
        ("Identificación", {"fields": ("sku", "nombre", "descripcion")}),
        ("Clasificación", {"fields": ("categoria", "marca")}),
        ("Comercial", {"fields": ("precio", "stock", "activo")}),
        ("Auditoría", {"fields": ("creado_en", "actualizado_en")}),
    )
