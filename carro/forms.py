# ============================================================
# carro/forms.py — FORMULARIOS HTML DEL CARRO
# Responsabilidad: validar los datos de la pantalla
# /panel/carros/, donde se opera el carro persistido de un cliente.
#
# Los formularios solo comprueban el formato (producto existente,
# cantidad entera y positiva). Las reglas de negocio —suma sin
# duplicar, comparación con el stock, baja lógica— viven en
# carro/servicios.py, que es el mismo módulo que usa la API.
# ============================================================

from django import forms

from catalogo.models import Producto
from usuarios.models import Rol, Usuario


# ============================================================
# BLOQUE 1 — SELECCIÓN DEL CLIENTE
# La pantalla no tiene login (así lo pide el enunciado), por lo que
# el carro que se opera se elige con un selector. Solo aparecen
# clientes activos: un administrador no tiene carro.
# ============================================================
class SeleccionarClienteForm(forms.Form):
    """Selector «Ver carro de:» de la pantalla de carros."""

    usuario = forms.ModelChoiceField(
        label="Ver carro de",
        queryset=Usuario.objects.none(),
        required=False,
        empty_label="Seleccione un cliente",
        widget=forms.Select(attrs={"class": "form-select", "onchange": "this.form.submit()"}),
    )

    def __init__(self, *args, **kwargs):
        """Carga los clientes activos en el selector."""
        super().__init__(*args, **kwargs)
        self.fields["usuario"].queryset = Usuario.objects.filter(
            rol=Rol.CLIENTE, is_active=True
        ).order_by("username")


# ============================================================
# BLOQUE 2 — AGREGAR UN PRODUCTO AL CARRO
# Solo ofrece productos activos con stock, para no invitar a
# agregar algo que el servicio va a rechazar de inmediato.
# ============================================================
class AgregarAlCarroForm(forms.Form):
    """Formulario para agregar un producto al carro del cliente elegido."""

    producto = forms.ModelChoiceField(
        label="Producto",
        queryset=Producto.objects.none(),
        empty_label="Seleccione un producto",
        widget=forms.Select(attrs={"class": "form-select"}),
        error_messages={"required": "Debe elegir un producto."},
    )
    cantidad = forms.IntegerField(
        label="Cantidad",
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1, "step": 1}),
        error_messages={
            "min_value": "La cantidad debe ser al menos 1.",
            "invalid": "La cantidad debe ser un número entero.",
            "required": "Indique la cantidad.",
        },
    )

    def __init__(self, *args, **kwargs):
        """Limita el selector a productos publicados con stock disponible."""
        super().__init__(*args, **kwargs)
        self.fields["producto"].queryset = (
            Producto.objects.filter(activo=True, stock__gt=0)
            .select_related("marca")
            .order_by("nombre")
        )


# ============================================================
# BLOQUE 3 — CAMBIAR LA CANTIDAD DE UN ÍTEM
# Se envía desde cada fila de la tabla del carro.
# ============================================================
class ActualizarCantidadForm(forms.Form):
    """Nueva cantidad exacta para un ítem del carro."""

    cantidad = forms.IntegerField(
        label="Cantidad",
        min_value=1,
        widget=forms.NumberInput(
            attrs={"class": "form-control form-control-sm", "min": 1, "step": 1, "style": "width: 6rem"}
        ),
        error_messages={
            "min_value": "La cantidad debe ser al menos 1. Para quitar el producto use el botón correspondiente.",
            "invalid": "La cantidad debe ser un número entero.",
            "required": "Indique la cantidad.",
        },
    )
