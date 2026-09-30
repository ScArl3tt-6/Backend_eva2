# ============================================================
# core/context_processors.py — DATOS GLOBALES PARA LAS PLANTILLAS
# Responsabilidad: inyectar en TODAS las plantillas los datos de
# la alumna y el nombre comercial, además de la información de
# navegación que usa la barra superior.
#
# Regla de la pauta: el nombre, la sección y el año NUNCA se
# escriben a mano dentro de una plantilla. Viven en el archivo
# .env, settings.py los lee con python-decouple y este context
# processor los entrega al footer de cada pantalla, incluidas la
# de redirección, Swagger UI y la Browsable API de DRF.
# ============================================================

from django.conf import settings


# ============================================================
# BLOQUE 1 — IDENTIFICACIÓN DE LA ALUMNA
# Expone las cuatro variables que consume templates/parciales/
# footer.html. Al venir de settings (y por tanto del .env),
# cambiar la sección o el año es editar una sola línea.
# ============================================================
def datos_alumno(request):
    """Entrega a la plantilla los datos de la alumna y el nombre comercial."""
    return {
        "ALUMNO_NOMBRE": settings.ALUMNO_NOMBRE,
        "ALUMNO_SECCION": settings.ALUMNO_SECCION,
        "ALUMNO_ANIO": settings.ALUMNO_ANIO,
        "NOMBRE_COMERCIAL": settings.NOMBRE_COMERCIAL,
    }


# ============================================================
# BLOQUE 2 — NAVEGACIÓN Y RUTA ACTUAL
# La barra superior marca como activo el módulo en el que está la
# visitante. Se calcula aquí, a partir del primer segmento de la
# ruta, para no repetir comparaciones de URL en cada plantilla.
# ============================================================
def navegacion(request):
    """Indica qué sección del menú debe aparecer resaltada."""
    ruta = request.path
    primer_segmento = ruta.strip("/").split("/")[0] if ruta.strip("/") else "inicio"

    return {
        "RUTA_ACTUAL": ruta,
        "SECCION_ACTUAL": primer_segmento or "inicio",
        "ENLACES_MENU": [
            {"etiqueta": "Inicio", "url": "/", "icono": "bi-house-door", "clave": "inicio"},
            {"etiqueta": "Catálogo", "url": "/catalogo/", "icono": "bi-grid", "clave": "catalogo"},
            {"etiqueta": "Gestión", "url": "/panel/", "icono": "bi-sliders", "clave": "panel"},
            {
                "etiqueta": "Documentación",
                "url": "/documentacion/",
                "icono": "bi-book",
                "clave": "documentacion",
            },
        ],
    }
