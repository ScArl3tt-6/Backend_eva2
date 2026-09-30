# ============================================================
# usuarios/serializers.py — VALIDACIÓN Y TRADUCCIÓN DE USUARIOS
# Responsabilidad: convertir usuarios entre JSON y modelo, con
# todas las reglas de seguridad en un solo lugar.
#
# Reglas que se garantizan aquí:
#   · La contraseña nunca se devuelve y nunca se guarda en texto
#     plano: pasa por validate_password y por set_password.
#   · En el registro público el rol NO se puede elegir: siempre
#     queda CLIENTE, aunque el JSON intente enviar otro valor.
#   · El email es único y se compara sin distinguir mayúsculas.
# ============================================================

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as ValidationErrorDjango
from rest_framework import serializers

from .models import Rol, Usuario


# ============================================================
# BLOQUE 1 — LECTURA DE USUARIOS
# Forma en que la API muestra un usuario. Incluye la etiqueta del
# rol en español y datos derivados, pero jamás la contraseña.
# ============================================================
class UsuarioSerializer(serializers.ModelSerializer):
    """Representación de lectura de un usuario."""

    rol_etiqueta = serializers.CharField(source="get_rol_display", read_only=True)
    nombre_completo = serializers.CharField(read_only=True)
    tiene_carro = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "nombre_completo",
            "telefono",
            "rol",
            "rol_etiqueta",
            "is_active",
            "tiene_carro",
            "last_login",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = ["id", "last_login", "creado_en", "actualizado_en"]

    def get_tiene_carro(self, obj) -> bool:
        """Indica si el usuario tiene carro persistente asociado."""
        return hasattr(obj, "carro")


# ============================================================
# BLOQUE 2 — REGISTRO PÚBLICO
# Endpoint abierto POST /api/auth/registro/. El rol se fija por
# código a CLIENTE: no aparece entre los campos de entrada, de
# modo que nadie puede crearse una cuenta de administrador desde
# fuera del sistema.
# ============================================================
class RegistroSerializer(serializers.ModelSerializer):
    """Crea una cuenta nueva, siempre con rol CLIENTE."""

    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
        help_text="Mínimo 8 caracteres; no puede ser solo numérica ni demasiado común.",
    )
    password2 = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
        label="Repetir contraseña",
        help_text="Debe coincidir exactamente con la contraseña.",
    )

    class Meta:
        model = Usuario
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "telefono",
            "password",
            "password2",
        ]
        extra_kwargs = {
            "email": {"required": True},
            "first_name": {"required": False},
            "last_name": {"required": False},
        }

    # --- Validaciones campo por campo, con mensajes en español ---
    def validate_email(self, valor):
        """Exige un correo único, sin distinguir mayúsculas."""
        if Usuario.objects.filter(email__iexact=valor).exists():
            raise serializers.ValidationError("Ya existe una cuenta con ese correo electrónico.")
        return valor.lower()

    def validate_username(self, valor):
        """Exige un nombre de usuario libre."""
        if Usuario.objects.filter(username__iexact=valor).exists():
            raise serializers.ValidationError("Ese nombre de usuario ya está ocupado.")
        return valor

    def validate(self, datos):
        """Compara ambas contraseñas y aplica los validadores de Django."""
        if datos["password"] != datos["password2"]:
            raise serializers.ValidationError(
                {"password2": "Las contraseñas no coinciden."}
            )

        try:
            validate_password(datos["password"])
        except ValidationErrorDjango as error:
            raise serializers.ValidationError({"password": list(error.messages)})

        return datos

    # ============================================================
    # BLOQUE 3 — CREACIÓN SEGURA DE LA CUENTA
    # set_password aplica el algoritmo de hash configurado por
    # Django; el rol queda forzado a CLIENTE. La señal post_save de
    # usuarios/signals.py crea enseguida el carro persistente.
    # ============================================================
    def create(self, validated_data):
        """Crea el usuario con contraseña cifrada y rol CLIENTE."""
        validated_data.pop("password2")
        contrasena = validated_data.pop("password")

        usuario = Usuario(**validated_data, rol=Rol.CLIENTE)
        usuario.set_password(contrasena)
        usuario.save()
        return usuario


# ============================================================
# BLOQUE 4 — ALTA Y EDICIÓN DESDE LA ADMINISTRACIÓN
# Usado por /api/usuarios/ (solo administrador). A diferencia del
# registro público, aquí SÍ se puede elegir el rol, porque quien
# llama ya demostró ser Administrador de TI.
# ============================================================
class UsuarioEscrituraSerializer(serializers.ModelSerializer):
    """Crea o edita usuarios desde la administración, con rol elegible."""

    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        style={"input_type": "password"},
        help_text="Al editar, dejar vacío conserva la contraseña actual.",
    )

    class Meta:
        model = Usuario
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "telefono",
            "rol",
            "is_active",
            "password",
        ]

    def validate_email(self, valor):
        """Exige correo único, ignorando el propio registro al editar."""
        consulta = Usuario.objects.filter(email__iexact=valor)
        if self.instance is not None:
            consulta = consulta.exclude(pk=self.instance.pk)
        if consulta.exists():
            raise serializers.ValidationError("Ya existe otra cuenta con ese correo electrónico.")
        return valor.lower()

    def validate_password(self, valor):
        """Aplica los validadores de Django solo si se envió contraseña."""
        if not valor:
            return valor
        try:
            validate_password(valor)
        except ValidationErrorDjango as error:
            raise serializers.ValidationError(list(error.messages))
        return valor

    def validate(self, datos):
        """Al crear un usuario la contraseña es obligatoria."""
        if self.instance is None and not datos.get("password"):
            raise serializers.ValidationError(
                {"password": "La contraseña es obligatoria al crear un usuario."}
            )
        return datos

    def create(self, validated_data):
        """Crea el usuario aplicando set_password."""
        contrasena = validated_data.pop("password", "")
        usuario = Usuario(**validated_data)
        usuario.set_password(contrasena)
        usuario.save()
        return usuario

    def update(self, instance, validated_data):
        """Actualiza el usuario y cambia la contraseña solo si se envió una nueva."""
        contrasena = validated_data.pop("password", "")

        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)

        if contrasena:
            instance.set_password(contrasena)

        instance.save()
        return instance


# ============================================================
# BLOQUE 5 — SERIALIZERS DE APOYO PARA LA DOCUMENTACIÓN
# Describen en el esquema OpenAPI los cuerpos de login, logout y
# perfil, para que Swagger muestre campos reales y no un objeto
# genérico.
# ============================================================
class LoginSerializer(serializers.Serializer):
    """Credenciales que espera POST /api/auth/login/."""

    username = serializers.CharField(help_text="Nombre de usuario registrado.")
    password = serializers.CharField(
        style={"input_type": "password"}, help_text="Contraseña de la cuenta."
    )


class LogoutSerializer(serializers.Serializer):
    """Token de refresco que se envía a la lista negra al cerrar sesión."""

    refresh = serializers.CharField(
        help_text="Token de refresco entregado por el login. Queda invalidado."
    )


class PerfilSerializer(serializers.Serializer):
    """Respuesta de GET /api/auth/perfil/: datos del usuario y claims del token."""

    usuario = UsuarioSerializer(read_only=True)
    claims_del_token = serializers.DictField(
        read_only=True,
        help_text="Contenido decodificado del token con el que se hizo la petición.",
    )
