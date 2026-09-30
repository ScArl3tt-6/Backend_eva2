# ============================================================
# core/templatetags/formato.py — FILTROS DE PRESENTACIÓN
# Responsabilidad: dar formato chileno a los valores que se
# muestran en las plantillas, sin ensuciar las vistas ni los
# modelos con lógica de presentación.
#
# El filtro principal es |clp, que convierte 1299990 en
# $1.299.990: en Chile el separador de miles es el punto y el peso
# no usa decimales, de ahí que el precio se modele con
# DecimalField(decimal_places=0).
# ============================================================

from decimal import Decimal, InvalidOperation

from django import template

# Django exige que la instancia de Library se llame exactamente
# "register": es el nombre que busca al descubrir las bibliotecas de
# etiquetas de cada aplicación instalada.
register = template.Library()


# ============================================================
# BLOQUE 1 — FORMATO DE MONEDA CHILENA
# Se arma a mano el separador de miles para no depender de la
# configuración regional del sistema operativo, que en Windows
# cambia de una máquina a otra.
# ============================================================
@register.filter(name="clp")
def pesos_chilenos(valor):
    """Formatea un número como precio chileno, por ejemplo $1.299.990."""
    try:
        numero = Decimal(str(valor if valor not in (None, "") else 0))
    except (InvalidOperation, TypeError, ValueError):
        return "$0"

    entero = int(numero.quantize(Decimal("1")))
    signo = "-" if entero < 0 else ""
    miles = f"{abs(entero):,}".replace(",", ".")
    return f"{signo}${miles}"


# ============================================================
# BLOQUE 2 — FORMATO DE CANTIDADES
# Mismo separador de miles, sin el símbolo de peso, para columnas
# de stock y de unidades.
# ============================================================
@register.filter(name="miles")
def separador_de_miles(valor):
    """Formatea un entero con puntos como separador de miles."""
    try:
        entero = int(Decimal(str(valor if valor not in (None, "") else 0)))
    except (InvalidOperation, TypeError, ValueError):
        return "0"
    return f"{entero:,}".replace(",", ".")


# ============================================================
# BLOQUE 3 — COLOR DEL BADGE SEGÚN EL ESTADO DE LA ORDEN
# Centraliza la correspondencia estado → clase de Bootstrap para
# que los cuatro estados se vean iguales en todas las pantallas
# (listado, detalle e inicio) sin repetir condicionales.
# ============================================================
CLASES_POR_ESTADO = {
    "PENDIENTE": "estado-pendiente",
    "PAGADO": "estado-pagado",
    "ENTREGADO": "estado-entregado",
    "CANCELADO": "estado-cancelado",
}

ICONOS_POR_ESTADO = {
    "PENDIENTE": "bi-hourglass-split",
    "PAGADO": "bi-credit-card-2-front",
    "ENTREGADO": "bi-box-seam",
    "CANCELADO": "bi-x-circle",
}


@register.filter(name="clase_estado")
def clase_estado(estado):
    """Devuelve la clase CSS del badge correspondiente al estado."""
    return CLASES_POR_ESTADO.get(str(estado).upper(), "estado-pendiente")


@register.filter(name="icono_estado")
def icono_estado(estado):
    """Devuelve el icono de Bootstrap Icons correspondiente al estado."""
    return ICONOS_POR_ESTADO.get(str(estado).upper(), "bi-circle")


# ============================================================
# BLOQUE 4 — CONSTRUCCIÓN DE ENLACES QUE CONSERVAN LOS FILTROS
# Al paginar el catálogo hay que mantener los filtros elegidos
# (categoría, precio, búsqueda). Esta etiqueta reescribe la
# cadena de consulta cambiando solo el parámetro indicado.
# ============================================================
@register.simple_tag(takes_context=True)
def url_con_parametro(context, nombre, valor):
    """Reescribe la cadena de consulta actual cambiando un parámetro."""
    peticion = context.get("request")
    if peticion is None:
        return f"?{nombre}={valor}"

    parametros = peticion.GET.copy()
    parametros[nombre] = valor
    return f"?{parametros.urlencode()}"
