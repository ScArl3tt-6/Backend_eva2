# ============================================================
# ordenes/forms.py — FORMULARIO HTML DE CAMBIO DE ESTADO
# Responsabilidad: recoger el estado destino y la observación en la
# pantalla /panel/ordenes/<id>/.
#
# El formulario no decide si la transición es legal: se limita a
# ofrecer únicamente los estados alcanzables desde el estado actual
# (según TRANSICIONES_PERMITIDAS) y deja la validación definitiva
# en ordenes/servicios.py, único dueño de la máquina de estados.
# ============================================================

from django import forms

from .models import EstadoOrden


# ============================================================
# BLOQUE 1 — CAMBIO DE ESTADO DE LA ORDEN
# El conjunto de opciones se construye en __init__ a partir de las
# transiciones posibles de la orden concreta, de modo que la
# interfaz nunca ofrezca un cambio que el servicio rechazaría.
# ============================================================
class CambiarEstadoOrdenForm(forms.Form):
    """Estado destino y observación para una orden concreta."""

    estado = forms.ChoiceField(
        label="Nuevo estado",
        choices=[],
        widget=forms.Select(attrs={"class": "form-select"}),
        error_messages={
            "required": "Elija el estado al que quiere pasar la orden.",
            "invalid_choice": "Ese estado no es alcanzable desde el estado actual de la orden.",
        },
    )
    observacion = forms.CharField(
        label="Observación",
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Motivo del cambio (queda en el historial)",
                "maxlength": 255,
            }
        ),
        help_text="Opcional. Se guarda en el historial de la orden como evidencia.",
    )

    def __init__(self, *args, estados_posibles=None, **kwargs):
        """Ofrece solo los estados alcanzables desde el estado actual."""
        super().__init__(*args, **kwargs)

        etiquetas = dict(EstadoOrden.choices)
        opciones = [(estado, etiquetas.get(estado, estado)) for estado in (estados_posibles or [])]
        self.fields["estado"].choices = opciones

        if not opciones:
            self.fields["estado"].widget.attrs["disabled"] = True
            self.fields["estado"].required = False
