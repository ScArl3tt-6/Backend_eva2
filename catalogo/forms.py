# ============================================================
# catalogo/forms.py — FORMULARIOS HTML DEL CATÁLOGO
# Responsabilidad: validar los datos que llegan desde las
# pantallas de gestión (/panel/categorias/, /panel/marcas/ y
# /panel/productos/).
#
# Se usan ModelForm para que las reglas del modelo (unicidad del
# SKU, precio positivo, stock no negativo) se apliquen también en
# el HTML, sin duplicar la lógica de los serializers. Los widgets
# llevan las clases de Bootstrap para que el formulario se vea
# igual que el resto del sitio, y los mensajes de error están en
# español.
# ============================================================

from django import forms

from .models import Categoria, Marca, Producto


# ============================================================
# BLOQUE 1 — FORMULARIO DE CATEGORÍAS
# El icono se elige de una lista cerrada de Bootstrap Icons para
# que la interfaz no dependa de que la persona escriba bien una
# clase CSS.
# ============================================================
ICONOS_DISPONIBLES = [
    ("bi-cpu", "Procesador (bi-cpu)"),
    ("bi-gpu-card", "Tarjeta de video (bi-gpu-card)"),
    ("bi-memory", "Memoria RAM (bi-memory)"),
    ("bi-motherboard", "Placa madre (bi-motherboard)"),
    ("bi-device-hdd", "Almacenamiento (bi-device-hdd)"),
    ("bi-plug", "Fuente de poder (bi-plug)"),
    ("bi-fan", "Refrigeración (bi-fan)"),
    ("bi-pc-display", "Gabinete o monitor (bi-pc-display)"),
    ("bi-keyboard", "Periférico (bi-keyboard)"),
    ("bi-box", "Genérico (bi-box)"),
]


class CategoriaForm(forms.ModelForm):
    """Alta y edición de categorías desde el panel de gestión."""

    class Meta:
        model = Categoria
        fields = ["nombre", "descripcion", "icono", "activo"]
        labels = {
            "nombre": "Nombre de la categoría",
            "descripcion": "Descripción",
            "icono": "Icono",
            "activo": "Categoría activa (visible en el catálogo)",
        }
        help_texts = {
            "nombre": "Por ejemplo: Procesadores, Tarjetas de Video, Memorias RAM.",
            "descripcion": "Explique brevemente qué componentes agrupa.",
        }
        widgets = {
            "nombre": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Procesadores", "autofocus": True}
            ),
            "descripcion": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Unidades centrales de proceso..."}
            ),
            "icono": forms.Select(choices=ICONOS_DISPONIBLES, attrs={"class": "form-select"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_nombre(self):
        """Evita categorías repetidas sin distinguir mayúsculas."""
        nombre = (self.cleaned_data.get("nombre") or "").strip()

        consulta = Categoria.objects.filter(nombre__iexact=nombre)
        if self.instance and self.instance.pk:
            consulta = consulta.exclude(pk=self.instance.pk)
        if consulta.exists():
            raise forms.ValidationError("Ya existe una categoría con ese nombre.")

        return nombre


# ============================================================
# BLOQUE 2 — FORMULARIO DE MARCAS
# ============================================================
class MarcaForm(forms.ModelForm):
    """Alta y edición de marcas desde el panel de gestión."""

    class Meta:
        model = Marca
        fields = ["nombre", "pais_origen", "activo"]
        labels = {
            "nombre": "Nombre de la marca",
            "pais_origen": "País de origen",
            "activo": "Marca activa (visible en el catálogo)",
        }
        help_texts = {
            "nombre": "Por ejemplo: Intel, AMD, NVIDIA, Kingston.",
            "pais_origen": "Opcional. Depende de la marca, no del producto.",
        }
        widgets = {
            "nombre": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Intel", "autofocus": True}
            ),
            "pais_origen": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Estados Unidos"}
            ),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_nombre(self):
        """Evita marcas repetidas sin distinguir mayúsculas."""
        nombre = (self.cleaned_data.get("nombre") or "").strip()

        consulta = Marca.objects.filter(nombre__iexact=nombre)
        if self.instance and self.instance.pk:
            consulta = consulta.exclude(pk=self.instance.pk)
        if consulta.exists():
            raise forms.ValidationError("Ya existe una marca con ese nombre.")

        return nombre


# ============================================================
# BLOQUE 3 — FORMULARIO DE PRODUCTOS
# Solo ofrece categorías y marcas activas: no tiene sentido
# publicar un producto bajo una categoría dada de baja. El SKU se
# normaliza a mayúsculas, igual que en el modelo y en el serializer,
# para que los tres caminos coincidan.
# ============================================================
class ProductoForm(forms.ModelForm):
    """Alta y edición de productos desde el panel de gestión."""

    class Meta:
        model = Producto
        fields = [
            "sku",
            "nombre",
            "descripcion",
            "categoria",
            "marca",
            "precio",
            "stock",
            "activo",
        ]
        labels = {
            "sku": "Código SKU",
            "nombre": "Nombre del producto",
            "descripcion": "Descripción",
            "categoria": "Categoría",
            "marca": "Marca",
            "precio": "Precio unitario (pesos chilenos)",
            "stock": "Stock disponible",
            "activo": "Producto activo (visible en el catálogo)",
        }
        help_texts = {
            "sku": "Código interno único; se guarda en mayúsculas.",
            "precio": "Debe ser mayor que cero. Sin decimales ni separadores.",
            "stock": "Unidades físicas en bodega. Solo el pago o la cancelación lo modifican.",
        }
        widgets = {
            "sku": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "CPU-INT-14600K", "autofocus": True}
            ),
            "nombre": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Procesador Intel Core i5-14600K"}
            ),
            "descripcion": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "placeholder": "14 núcleos, 20 hilos, socket LGA1700..."}
            ),
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "marca": forms.Select(attrs={"class": "form-select"}),
            "precio": forms.NumberInput(attrs={"class": "form-control", "min": 1, "step": 1}),
            "stock": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": 1}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        """Limita los selectores a categorías y marcas activas."""
        super().__init__(*args, **kwargs)

        self.fields["categoria"].queryset = Categoria.objects.filter(activo=True).order_by("nombre")
        self.fields["marca"].queryset = Marca.objects.filter(activo=True).order_by("nombre")
        self.fields["categoria"].empty_label = "Seleccione una categoría"
        self.fields["marca"].empty_label = "Seleccione una marca"

        # Al editar, se mantiene visible la relación aunque haya sido
        # dada de baja después de crear el producto.
        if self.instance and self.instance.pk:
            if self.instance.categoria_id and not self.instance.categoria.activo:
                self.fields["categoria"].queryset = Categoria.objects.filter(
                    pk__in=[self.instance.categoria_id]
                ) | self.fields["categoria"].queryset
            if self.instance.marca_id and not self.instance.marca.activo:
                self.fields["marca"].queryset = Marca.objects.filter(
                    pk__in=[self.instance.marca_id]
                ) | self.fields["marca"].queryset

    def clean_sku(self):
        """Normaliza el SKU a mayúsculas y comprueba que sea único."""
        sku = (self.cleaned_data.get("sku") or "").strip().upper()
        if not sku:
            raise forms.ValidationError("El código SKU es obligatorio.")

        consulta = Producto.objects.filter(sku=sku)
        if self.instance and self.instance.pk:
            consulta = consulta.exclude(pk=self.instance.pk)
        if consulta.exists():
            raise forms.ValidationError("Ya existe un producto con ese código SKU.")

        return sku

    def clean_precio(self):
        """El precio debe ser mayor que cero (regla del negocio)."""
        precio = self.cleaned_data.get("precio")
        if precio is None or precio <= 0:
            raise forms.ValidationError("El precio debe ser mayor que cero.")
        return precio

    def clean_stock(self):
        """El stock nunca puede ser negativo."""
        stock = self.cleaned_data.get("stock")
        if stock is None or stock < 0:
            raise forms.ValidationError("El stock no puede ser negativo.")
        return stock
