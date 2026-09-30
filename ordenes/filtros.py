# ============================================================
# ordenes/filtros.py — FILTROS DE ÓRDENES (django-filter)
# Responsabilidad: permitir al administrador acotar el listado de
# órdenes por estado, cliente y rango de fechas.
#
# Como en el catálogo, el mismo FilterSet se usa en la API
# (GET /api/ordenes/) y en la pantalla HTML /panel/ordenes/, para
# que el comportamiento sea idéntico por ambos caminos.
# drf-spectacular lo publica como parámetros en Swagger.
# ============================================================

import django_filters
from django import forms

from usuarios.models import Rol, Usuario

from .models import EstadoOrden, Orden


# ============================================================
# BLOQUE 1 — FILTRO DE ÓRDENES
# fecha_desde y fecha_hasta usan lookup "date" sobre creada_en, de
# modo que el usuario compara por día sin preocuparse de la hora.
# ============================================================
class OrdenFilter(django_filters.FilterSet):
    """Filtros del listado de órdenes: estado, cliente y rango de fechas."""

    estado = django_filters.ChoiceFilter(
        choices=EstadoOrden.choices,
        label="Estado",
        empty_label="Todos los estados",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    usuario = django_filters.ModelChoiceFilter(
        field_name="usuario",
        queryset=Usuario.objects.filter(rol=Rol.CLIENTE).order_by("username"),
        label="Cliente",
        empty_label="Todos los clientes",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    fecha_desde = django_filters.DateFilter(
        field_name="creada_en",
        lookup_expr="date__gte",
        label="Creada desde",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    fecha_hasta = django_filters.DateFilter(
        field_name="creada_en",
        lookup_expr="date__lte",
        label="Creada hasta",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    codigo = django_filters.CharFilter(
        field_name="codigo",
        lookup_expr="icontains",
        label="Número de orden contiene",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Parte del código UUID"}),
    )

    class Meta:
        model = Orden
        fields = ["estado", "usuario", "fecha_desde", "fecha_hasta", "codigo"]
