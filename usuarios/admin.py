# ============================================================
# usuarios/admin.py — REGISTRO DEL USUARIO EN DJANGO ADMIN
# Responsabilidad: dejar el modelo Usuario administrable desde
# /admin/ con list_display, list_filter y search_fields, como apoyo
# del criterio "Django Admin" de la unidad.
#
# Nota: el admin no forma parte de la demostración ni se enlaza
# desde la interfaz del sitio; la gestión se hace en /panel/.
# ============================================================

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


# ============================================================
# BLOQUE 1 — ADMINISTRACIÓN DE USUARIOS
# Se hereda de UserAdmin para conservar el manejo seguro de
# contraseñas y se añade el campo rol a los formularios y filtros.
# ============================================================
@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Administración de usuarios con el rol del negocio."""

    list_display = ["username", "email", "nombre_completo", "rol", "is_active", "creado_en"]
    list_filter = ["rol", "is_active", "is_staff", "creado_en"]
    search_fields = ["username", "first_name", "last_name", "email", "telefono"]
    ordering = ["username"]
    list_per_page = 25
    readonly_fields = ["creado_en", "actualizado_en", "last_login", "date_joined"]

    fieldsets = UserAdmin.fieldsets + (
        (
            "Datos del negocio",
            {
                "fields": ("rol", "telefono", "creado_en", "actualizado_en"),
                "description": "El rol define los permisos de la API y se sincroniza con is_staff.",
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Datos del negocio", {"fields": ("email", "rol", "telefono")}),
    )

    @admin.display(description="nombre completo")
    def nombre_completo(self, obj):
        """Columna con el nombre y apellido del usuario."""
        return obj.nombre_completo
