# ============================================================
# usuarios/models.py — MODELO DE USUARIO Y ROLES
# Responsabilidad: definir el usuario del sistema con los dos
# roles del negocio (Cliente y Administrador de TI) exigidos por
# la pauta, sobre la base de AbstractUser para no perder el
# sistema de contraseñas ni los permisos de Django.
# ============================================================

from django.contrib.auth.models import AbstractUser
from django.db import models


# ============================================================
# BLOQUE 1 — CHOICES DE ROL
# Se define con TextChoices (no con tuplas sueltas) para que el
# valor guardado y la etiqueta visible vivan juntos y para que
# drf-spectacular los publique como enum en el esquema OpenAPI.
# El valor viaja además dentro del token JWT como claim "rol".
# ============================================================
class Rol(models.TextChoices):
    """Roles del negocio: quién compra y quién administra el catálogo."""

    CLIENTE = "CLIENTE", "Cliente"
    ADMINISTRADOR = "ADMINISTRADOR", "Administrador de TI"


# ============================================================
# BLOQUE 2 — MODELO USUARIO
# Extiende AbstractUser agregando rol, email único y teléfono.
# El borrado es lógico: "eliminar" un usuario significa dejarlo
# con is_active=False, nunca borrar la fila (regla de la pauta).
# ============================================================
class Usuario(AbstractUser):
    """Usuario del sistema; su rol define qué puede hacer en la API."""

    email = models.EmailField(
        "correo electrónico",
        unique=True,
        help_text="Debe ser único; se usa para identificar a la persona.",
    )
    rol = models.CharField(
        "rol",
        max_length=20,
        choices=Rol.choices,
        default=Rol.CLIENTE,
        db_index=True,
        help_text="CLIENTE compra; ADMINISTRADOR gestiona el catálogo y las órdenes.",
    )
    telefono = models.CharField(
        "teléfono",
        max_length=20,
        blank=True,
        help_text="Opcional, para contacto sobre las órdenes.",
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["username"]
        indexes = [
            models.Index(fields=["rol"], name="usuario_rol_idx"),
            models.Index(fields=["is_active"], name="usuario_activo_idx"),
        ]

    def __str__(self) -> str:
        """Representación legible usada en el admin y en los selectores."""
        return f"{self.username} ({self.get_rol_display()})"

    # ============================================================
    # BLOQUE 3 — SINCRONIZACIÓN DE rol CON is_staff
    # Regla: un Administrador de TI es también staff de Django. Así
    # el mismo usuario funciona con los permisos propios del
    # proyecto (EsAdministrador, que lee el claim del token) y con
    # los de DRF basados en is_staff (IsAdminUser), sin duplicar
    # la fuente de verdad, que siempre es el campo rol.
    # ============================================================
    def save(self, *args, **kwargs):
        """Mantiene is_staff alineado con el rol antes de guardar."""
        self.is_staff = self.rol == Rol.ADMINISTRADOR
        super().save(*args, **kwargs)

    # ============================================================
    # BLOQUE 4 — PROPIEDADES DE APOYO
    # Evitan repetir comparaciones de texto en vistas, permisos y
    # plantillas, y dejan la intención explícita al leer el código.
    # ============================================================
    @property
    def es_administrador(self) -> bool:
        """True si el usuario administra el catálogo y las órdenes."""
        return self.rol == Rol.ADMINISTRADOR

    @property
    def es_cliente(self) -> bool:
        """True si el usuario compra (tiene carro y órdenes propias)."""
        return self.rol == Rol.CLIENTE

    @property
    def nombre_completo(self) -> str:
        """Nombre y apellido; si no están definidos, cae al username."""
        completo = f"{self.first_name} {self.last_name}".strip()
        return completo or self.username
