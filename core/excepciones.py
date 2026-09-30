# ============================================================
# core/excepciones.py — MANEJADOR DE ERRORES DE LA API
# Responsabilidad: devolver SIEMPRE el mismo formato de error en
# español, para que quien consuma la API no tenga que interpretar
# tres estructuras distintas según el tipo de fallo.
#
# Formato único de respuesta:
#   {"error": true, "mensaje": "...", "detalle": ...}
#
# Además cumple un requisito crítico de la pauta: un recurso
# inexistente en la API (por ejemplo GET /api/productos/999999/)
# responde JSON controlado en español e incluye la clave
# "redireccion": "/", nunca una página de error HTML ni el 404 de
# Django.
# ============================================================

import logging

from django.core.exceptions import PermissionDenied, ValidationError as ValidationErrorDjango
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

registro = logging.getLogger(__name__)


# ============================================================
# BLOQUE 1 — MENSAJES POR CÓDIGO DE ESTADO
# Traduce el código HTTP a una frase clara en español. Se usa
# cuando la excepción no trae un mensaje propio entendible.
# ============================================================
MENSAJES_POR_CODIGO = {
    status.HTTP_400_BAD_REQUEST: "Los datos enviados no son válidos.",
    status.HTTP_401_UNAUTHORIZED: "Debe autenticarse para usar este recurso. Envíe el token JWT en el encabezado Authorization: Bearer <token>.",
    status.HTTP_403_FORBIDDEN: "Su rol no tiene permiso para realizar esta acción.",
    status.HTTP_404_NOT_FOUND: "El recurso solicitado no existe.",
    status.HTTP_405_METHOD_NOT_ALLOWED: "El método HTTP no está permitido en este recurso.",
    status.HTTP_409_CONFLICT: "La operación no se puede completar por el estado actual de los datos.",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "El formato del contenido enviado no es compatible.",
    status.HTTP_429_TOO_MANY_REQUESTS: "Demasiadas solicitudes. Intente de nuevo en unos instantes.",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "Ocurrió un error interno en el servidor.",
}


# ============================================================
# BLOQUE 2 — EXTRACCIÓN DEL MENSAJE PRINCIPAL
# Las excepciones de DRF traen el detalle en formas distintas:
# texto, lista o diccionario por campo. Esta función obtiene una
# frase legible sin perder el detalle completo, que se devuelve
# aparte en la clave "detalle".
# ============================================================
def _mensaje_legible(detalle, codigo):
    """Obtiene una frase en español a partir del detalle de la excepción."""
    if isinstance(detalle, str):
        return detalle
    if isinstance(detalle, list) and detalle:
        return _mensaje_legible(detalle[0], codigo)
    if isinstance(detalle, dict):
        if "detail" in detalle:
            return _mensaje_legible(detalle["detail"], codigo)
        if "mensaje" in detalle:
            return _mensaje_legible(detalle["mensaje"], codigo)
        primer_campo = next(iter(detalle))
        texto = _mensaje_legible(detalle[primer_campo], codigo)
        return f"{primer_campo}: {texto}"
    return MENSAJES_POR_CODIGO.get(codigo, "Ocurrió un error al procesar la solicitud.")


# ============================================================
# BLOQUE 3 — MANEJADOR PRINCIPAL
# Se registra en REST_FRAMEWORK["EXCEPTION_HANDLER"]. Primero deja
# que DRF haga su trabajo; luego reescribe el cuerpo al formato
# uniforme del proyecto. Las excepciones de Django que DRF no
# reconoce (Http404, PermissionDenied, ValidationError del ORM)
# se traducen también, para que ninguna termine en HTML.
# ============================================================
def manejador_excepciones_api(exc, context):
    """Uniforma todas las respuestas de error de la API en español."""
    respuesta = exception_handler(exc, context)

    # --- Excepciones de Django que DRF no convierte por sí solo ---
    if respuesta is None:
        if isinstance(exc, Http404):
            respuesta = Response(
                {"detail": "El recurso solicitado no existe."},
                status=status.HTTP_404_NOT_FOUND,
            )
        elif isinstance(exc, PermissionDenied):
            respuesta = Response(
                {"detail": "Su rol no tiene permiso para realizar esta acción."},
                status=status.HTTP_403_FORBIDDEN,
            )
        elif isinstance(exc, ValidationErrorDjango):
            respuesta = Response(
                {"detail": list(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            # Cualquier fallo no previsto se registra en la consola del
            # servidor y se devuelve como JSON, nunca como página HTML.
            registro.exception("Error no controlado en la API: %s", exc)
            respuesta = Response(
                {"detail": "Ocurrió un error interno en el servidor."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    codigo = respuesta.status_code
    detalle_original = respuesta.data
    mensaje = _mensaje_legible(detalle_original, codigo)

    # Los 404 que genera Django internamente traen un texto en inglés
    # ("No Producto matches the given query."). Se reemplaza por el mensaje
    # en español del proyecto; el texto original se conserva en "detalle"
    # para no perder información de diagnóstico.
    if codigo == status.HTTP_404_NOT_FOUND:
        mensaje = MENSAJES_POR_CODIGO[status.HTTP_404_NOT_FOUND]

    cuerpo = {
        "error": True,
        "codigo": codigo,
        "mensaje": mensaje,
        "detalle": detalle_original,
    }

    # ============================================================
    # BLOQUE 4 — RUTA DE ESCAPE PARA RECURSOS INEXISTENTES
    # Requisito de la pauta: en la API, un recurso que no existe
    # responde JSON en español indicando adónde volver, de modo que
    # tampoco aquí aparezca una página 404.
    # ============================================================
    if codigo in (status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED):
        cuerpo["redireccion"] = "/"
        cuerpo["sugerencia"] = "Revise el índice de endpoints en /api/ o la documentación en /api/docs/."

    respuesta.data = cuerpo
    return respuesta
