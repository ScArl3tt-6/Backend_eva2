# ============================================================
# catalogo/filtros.py — FILTROS DEL CATÁLOGO (django-filter)
# Responsabilidad: definir en un único lugar los filtros del
# catálogo, que se reutilizan tal cual en dos consumidores:
#   · la API REST, en GET /api/productos/
#   · la pantalla HTML /catalogo/, cuyo formulario GET usa este
#     mismo FilterSet
# Así el comportamiento de los filtros es idéntico en la API y en
# la interfaz, y basta cambiarlo aquí para cambiarlo en ambas.
#
# drf-spectacular lee este FilterSet y publica cada filtro como
# parámetro documentado en Swagger.
# ============================================================

import django_filters
from django import forms

from .models import Categoria, Marca, Producto


# ============================================================
# BLOQUE 1 — FILTRO DE PRODUCTOS
# Cubre búsqueda por relación (categoría y marca, por id o por
# nombre parcial), rango de precios, disponibilidad de stock y
# SKU exacto sin distinguir mayúsculas.
# ============================================================
class ProductoFilter(django_filters.FilterSet):
    """Filtros del catálogo de productos, compartidos por la API y el HTML."""

    # --- Filtros por categoría ---
    categoria = django_filters.ModelChoiceFilter(
        field_name="categoria",
        queryset=Categoria.objects.filter(activo=True),
        label="Categoría",
        empty_label="Todas las categorías",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    categoria_nombre = django_filters.CharFilter(
        field_name="categoria__nombre",
        lookup_expr="icontains",
        label="Nombre de la categoría contiene",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Procesadores"}),
    )

    # --- Filtros por marca ---
    marca = django_filters.ModelChoiceFilter(
        field_name="marca",
        queryset=Marca.objects.filter(activo=True),
        label="Marca",
        empty_label="Todas las marcas",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    marca_nombre = django_filters.CharFilter(
        field_name="marca__nombre",
        lookup_expr="icontains",
        label="Nombre de la marca contiene",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Intel"}),
    )

    # --- Rango de precios en pesos chilenos ---
    precio_min = django_filters.NumberFilter(
        field_name="precio",
        lookup_expr="gte",
        label="Precio mínimo",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "0", "min": 0}),
    )
    precio_max = django_filters.NumberFilter(
        field_name="precio",
        lookup_expr="lte",
        label="Precio máximo",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "2000000", "min": 0}),
    )

    # --- Disponibilidad y código ---
    en_stock = django_filters.BooleanFilter(
        method="filtrar_en_stock",
        label="Solo con stock disponible",
        widget=forms.Select(
            choices=[("", "Con y sin stock"), ("true", "Solo con stock"), ("false", "Solo sin stock")],
            attrs={"class": "form-select"},
        ),
    )
    sku = django_filters.CharFilter(
        field_name="sku",
        lookup_expr="iexact",
        label="Código SKU exacto",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "CPU-INT-14600K"}),
    )

    # --- Búsqueda libre, equivalente al ?search= de la API ---
    buscar = django_filters.CharFilter(
        method="buscar_texto",
        label="Buscar",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Nombre, SKU, descripción o marca"}
        ),
    )

    class Meta:
        model = Producto
        fields = [
            "categoria",
            "categoria_nombre",
            "marca",
            "marca_nombre",
            "precio_min",
            "precio_max",
            "en_stock",
            "sku",
            "buscar",
        ]

    # ============================================================
    # BLOQUE 2 — MÉTODOS DE FILTRADO PROPIOS
    # "en_stock" no corresponde a un campo, sino a la condición
    # stock > 0; "buscar" replica en el HTML la búsqueda que en la
    # API hace SearchFilter sobre los mismos campos.
    # ============================================================
    def filtrar_en_stock(self, queryset, nombre, valor):
        """Filtra por disponibilidad real: stock mayor que cero."""
        if valor is None:
            return queryset
        if valor:
            return queryset.filter(stock__gt=0)
        return queryset.filter(stock=0)

    def buscar_texto(self, queryset, nombre, valor):
        """Busca el texto en nombre, SKU, descripción y nombre de la marca."""
        texto = (valor or "").strip()
        if not texto:
            return queryset

        from django.db.models import Q

        return queryset.filter(
            Q(nombre__icontains=texto)
            | Q(sku__icontains=texto)
            | Q(descripcion__icontains=texto)
            | Q(marca__nombre__icontains=texto)
        )
