# ============================================================
# pagos/views_html.py — RETORNO DE WEBPAY PLUS
# Responsabilidad: atender la ÚNICA URL a la que Transbank redirige
# el navegador del cliente después del formulario de pago, sin
# importar si el pago se inició desde el panel o desde la API.
#
# Por qué esta vista es csrf_exempt (y por qué es seguro):
# Transbank llega con un POST (o, en el caso de timeout, un GET) que
# el navegador del cliente generó siguiendo el formulario de
# Transbank, no un formulario de este sitio: no hay token CSRF
# nuestro que pueda traer. Pero NO se confía en nada de lo que venga
# en esta petición del navegador: el único dato que se usa para
# decidir si se cobra es el que devuelve commit(), una llamada
# servidor a servidor directa a Transbank (pagos/servicios.py). Si
# alguien falsificara esta petición, en el peor caso provocaría un
# commit de un token que no le pertenece, y Transbank respondería
# con el estado real de ESE token, no con uno inventado.
# ============================================================

from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .servicios import (
    MontoNoCoincideError,
    PagoNoEncontradoError,
    anular_pago_por_usuario,
    confirmar_pago_webpay,
    expirar_pago_por_timeout,
    marcar_error_de_formulario,
)


# ============================================================
# BLOQUE 1 — LOS CUATRO CASOS DEL RETORNO DE WEBPAY PLUS
# La combinación de parámetros que manda Transbank es la que indica
# cuál de los cuatro casos ocurrió; el orden de las comprobaciones
# es el que documenta Transbank:
#   1. token_ws + TBK_TOKEN juntos  → error de formulario.
#   2. solo token_ws                → pago normal (aprobado o no).
#   3. TBK_TOKEN + TBK_ORDEN_COMPRA + TBK_ID_SESION → el cliente
#      anuló el pago en el formulario de Transbank.
#   4. solo TBK_ORDEN_COMPRA + TBK_ID_SESION → venció el tiempo del
#      formulario (timeout).
# ============================================================
@csrf_exempt
def retorno_webpay(request):
    """Único punto de retorno de Webpay Plus para los cuatro casos posibles."""
    datos = request.POST if request.method == "POST" else request.GET

    token_ws = datos.get("token_ws")
    tbk_token = datos.get("TBK_TOKEN")
    tbk_orden_compra = datos.get("TBK_ORDEN_COMPRA")
    tbk_id_sesion = datos.get("TBK_ID_SESION")

    contexto = {"titulo_pagina": "Resultado del pago"}

    if token_ws and tbk_token:
        pago = marcar_error_de_formulario(token_ws)
        contexto.update(
            resultado="ERROR_FORMULARIO",
            mensaje=(
                "Hubo un error en el formulario de pago de Webpay. No se realizó "
                "ningún cobro; puede volver a intentar el pago desde la orden."
            ),
            pago=pago,
        )

    elif token_ws:
        try:
            pago = confirmar_pago_webpay(token_ws)
            contexto.update(resultado=pago.estado, pago=pago)
        except PagoNoEncontradoError:
            contexto.update(
                resultado="ERROR",
                mensaje="No se encontró el intento de pago asociado a este token.",
                pago=None,
            )
        except MontoNoCoincideError as excepcion:
            contexto.update(resultado="ERROR", mensaje=str(excepcion), pago=None)

    elif tbk_token and tbk_orden_compra and tbk_id_sesion:
        pago = anular_pago_por_usuario(tbk_token)
        contexto.update(
            resultado="ANULADO_POR_USUARIO",
            mensaje="Anuló el pago en el formulario de Webpay. No se realizó ningún cobro.",
            pago=pago,
        )

    elif tbk_orden_compra and tbk_id_sesion:
        pago = expirar_pago_por_timeout(tbk_orden_compra)
        contexto.update(
            resultado="EXPIRADO",
            mensaje="Venció el tiempo para completar el pago en Webpay. No se realizó ningún cobro.",
            pago=pago,
        )

    else:
        contexto.update(
            resultado="ERROR",
            mensaje="No se reconocieron los parámetros de vuelta de Webpay.",
            pago=None,
        )

    return render(request, "pagos/resultado_pago.html", contexto)
