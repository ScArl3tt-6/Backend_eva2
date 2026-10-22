# ============================================================
# usuarios/forms.py — FORMULARIO HTML DE USUARIOS
# Responsabilidad: permitir crear y editar usuarios desde
# /panel/usuarios/, eligiendo su rol.
#
# Reglas de seguridad que se respetan aquí:
#   · La contraseña se guarda con set_password (nunca en texto
#     plano) y pasa por los validadores de Django.
#   · Al editar, dejar la contraseña vacía conserva la existente.
#   · El correo es único, comparado sin distinguir mayúsculas.
#   · El rol sí se puede elegir en este formulario, porque es la
#     pantalla de administración; en el registro público de la API
#     el rol queda forzado a CLIENTE.
# ============================================================

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Rol, Usuario


# ============================================================
# BLOQUE 1 — FORMULARIO DE USUARIOS
# ============================================================
class UsuarioForm(forms.ModelForm):
    """Alta y edición de usuarios con elección de rol."""

    password = forms.CharField(
        label="Contraseña",
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password", "placeholder": "••••••••"}
        ),
        help_text="Obligatoria al crear. Al editar, déjela vacía para conservar la actual.",
    )

    class Meta:
        model = Usuario
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "telefono",
            "rol",
            "is_active",
        ]
        labels = {
            "username": "Nombre de usuario",
            "email": "Correo electrónico",
            "first_name": "Nombre",
            "last_name": "Apellido",
            "telefono": "Teléfono",
            "rol": "Rol",
            "is_active": "Usuario activo",
        }
        help_texts = {
            "username": "Sin espacios. Se usa para iniciar sesión.",
            "rol": "CLIENTE compra en la tienda; ADMINISTRADOR gestiona el catálogo y las órdenes.",
            "is_active": "Desmarcar equivale a dar de baja la cuenta sin borrarla.",
        }
        widgets = {
            "username": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "cliente4", "autofocus": True}
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "persona@hardpointpc.cl"}
            ),
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Camila"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Rojas"}),
            "telefono": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "+56 9 1234 5678"}
            ),
            "rol": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        """Marca la contraseña como obligatoria solo al crear la cuenta."""
        super().__init__(*args, **kwargs)

        self.fields["rol"].choices = Rol.choices
        if self.instance is None or not self.instance.pk:
            self.fields["password"].required = True
            self.fields["password"].help_text = "Mínimo 8 caracteres; no puede ser solo numérica."

    # ============================================================
    # BLOQUE 2 — VALIDACIONES
    # ============================================================
    def clean_username(self):
        """Comprueba que el nombre de usuario esté libre."""
        username = (self.cleaned_data.get("username") or "").strip()

        consulta = Usuario.objects.filter(username__iexact=username)
        if self.instance and self.instance.pk:
            consulta = consulta.exclude(pk=self.instance.pk)
        if consulta.exists():
            raise forms.ValidationError("Ese nombre de usuario ya está ocupado.")

        return username

    def clean_email(self):
        """Comprueba que el correo sea único."""
        email = (self.cleaned_data.get("email") or "").strip().lower()

        consulta = Usuario.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            consulta = consulta.exclude(pk=self.instance.pk)
        if consulta.exists():
            raise forms.ValidationError("Ya existe otra cuenta con ese correo electrónico.")

        return email

    def clean_password(self):
        """Aplica los validadores de Django cuando se envió una contraseña."""
        contrasena = self.cleaned_data.get("password") or ""
        if not contrasena:
            return contrasena

        try:
            validate_password(contrasena)
        except ValidationError as error:
            raise forms.ValidationError(list(error.messages))

        return contrasena

    # ============================================================
    # BLOQUE 3 — GUARDADO CON CONTRASEÑA CIFRADA
    # set_password aplica el algoritmo de hash de Django. El método
    # save() del modelo sincroniza además is_staff con el rol.
    # ============================================================
    def save(self, commit=True):
        """Guarda el usuario cifrando la contraseña si se indicó una nueva."""
        usuario = super().save(commit=False)

        contrasena = self.cleaned_data.get("password") or ""
        if contrasena:
            usuario.set_password(contrasena)

        if commit:
            usuario.save()

        return usuario


# ============================================================
# BLOQUE 4 — LOGIN DEL PANEL DE ADMINISTRACIÓN
# El panel (/panel/...) se puede ver sin iniciar sesión, pero
# editar algo (pagar una orden, vaciar un carro, dar de baja un
# usuario) exige ahora una sesión de Administrador de TI.
#
# Se reutiliza AuthenticationForm, la misma que usa
# django.contrib.auth.views.LoginView: la contraseña nunca se
# compara a mano, la valida authenticate() de Django. Lo único que
# se agrega es una comprobación extra en confirm_login_allowed: la
# cuenta debe tener rol ADMINISTRADOR, o el login se rechaza aunque
# la contraseña sea correcta.
# ============================================================
class FormularioLoginAdministrador(AuthenticationForm):
    """Login de sesión del panel: exige además el rol ADMINISTRADOR."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "no_admin": "Esta cuenta no tiene permisos de administrador de TI.",
    }

    def __init__(self, *args, **kwargs):
        """Agrega las clases de Bootstrap a los campos heredados."""
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"class": "form-control", "autofocus": True, "placeholder": "admin_ti"}
        )
        self.fields["password"].widget.attrs.update(
            {"class": "form-control", "placeholder": "••••••••"}
        )

    def confirm_login_allowed(self, user):
        """Además de is_active, exige que el rol sea ADMINISTRADOR."""
        super().confirm_login_allowed(user)
        if not user.es_administrador:
            raise ValidationError(self.error_messages["no_admin"], code="no_admin")
