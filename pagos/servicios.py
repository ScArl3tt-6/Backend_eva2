# ============================================================
# pagos/servicios.py — REGLAS DE NEGOCIO DEL PAGO CON WEBPAY PLUS
# Responsabilidad: hablar con el SDK de Transbank y decidir qué
# hacer con cada respuesta. Ninguna vista llama al SDK directamente;
# todas pasan por acá, igual que ordenes/servicios.py es el único
# lugar que toca el stock.
#
# Dos funciones concentran todo el flujo:
#   iniciar_pago_webpay()   — crea la transacción en Transbank y
#                             guarda el intento en estado INICIADO.
#   confirmar_pago_webpay() — hace el commit (server a server) y,
#                             si Transbank aprobó, descuenta el stock
#                             llamando a la función pagar_orden() que
#                             ya existía. Es IDEMPOTENTE: si el token
#                             ya se procesó, no vuelve a cobrar ni a
#                             descontar stock.
#
# CASO CRÍTICO: Transbank aprueba, pero al momento de descontar el
# stock ya no alcanza (otro cliente se adelantó). El dinero del
# cliente ya está retenido en el banco, así que NO se puede dejar la
# orden así. Se hace un refund (anulación) del monto completo en
# Transbank, se marca el pago REEMBOLSADO y la orden queda PENDIENTE
# con un mensaje claro: nunca un cliente cobrado sin su producto.
# ============================================================

import uuid

from django.conf import settings
from django.db import transaction
from transbank.webpay.webpay_plus.transaction import Transaction

from ordenes.models import EstadoOrden, Orden
from ordenes.servicios import StockInsuficienteError, pagar_orden

from .models import EstadoPagoWebpay, PagoWebpay


# ============================================================
# BLOQUE 1 — EXCEPCIONES PROPIAS
# ============================================================
class ErrorDePago(Exception):
    """Error de negocio al iniciar o confirmar un pago con Webpay."""


class OrdenNoPagableError(ErrorDePago):
    """La orden no está PENDIENTE o no tiene productos que cobrar."""


class PagoNoEncontradoError(ErrorDePago):
    """No existe un PagoWebpay con ese token."""


class MontoNoCoincideError(ErrorDePago):
    """El monto que devolvió Transbank no coincide con el iniciado."""

    def __init__(self, esperado: int, recibido: int):
        self.esperado = esperado
        self.recibido = recibido
        super().__init__(
            f"El monto que devolvió Webpay (${recibido}) no coincide con el "
            f"monto iniciado (${esperado})."
        )


# ============================================================
# BLOQUE 2 — TRANSACCIÓN DEL SDK SEGÚN EL AMBIENTE
# Transaction.build_for_integration()/build_for_production() son los
# constructores que trae el propio SDK (transbank.common.
# webpay_transaction.WebpayTransaction): fijan el código de
# comercio, la API Key y el host de Transbank que corresponde.
# ============================================================
def _transaccion_webpay() -> Transaction:
    """Construye el cliente de Webpay Plus según TRANSBANK_AMBIENTE."""
    if settings.TRANSBANK_AMBIENTE == "produccion":
        return Transaction.build_for_production(
            settings.TRANSBANK_CODIGO_COMERCIO, settings.TRANSBANK_API_KEY
        )
    return Transaction.build_for_integration(
        settings.TRANSBANK_CODIGO_COMERCIO, settings.TRANSBANK_API_KEY
    )


def _generar_buy_order(orden: Orden) -> str:
    """Genera un buy_order corto (máx. 26 caracteres) y único para Transbank."""
    for _ in range(5):
        candidato = f"HP{orden.pk}-{uuid.uuid4().hex[:12]}"[:26]
        if not PagoWebpay.objects.filter(buy_order=candidato).exists():
            return candidato
    raise ErrorDePago("No se pudo generar un buy_order único para Webpay.")


# ============================================================
# BLOQUE 3 — INICIAR EL PAGO
# Crea la transacción en Transbank y guarda el intento en INICIADO.
# No toca el stock ni el estado de la orden: eso ocurre solo cuando
# vuelve la confirmación (ver BLOQUE 4).
# ============================================================
def iniciar_pago_webpay(orden: Orden, return_url: str) -> PagoWebpay:
    """Crea la transacción de Webpay Plus para una orden PENDIENTE."""
    orden = Orden.objects.get(pk=orden.pk)

    if orden.estado != EstadoOrden.PENDIENTE:
        raise OrdenNoPagableError(
            f"La orden {orden.codigo_corto} no está pendiente de pago."
        )

    monto = int(orden.total)
    if monto <= 0:
        raise OrdenNoPagableError(
            "La orden no tiene productos: no se puede iniciar el pago."
        )

    buy_order = _generar_buy_order(orden)
    session_id = f"sesion-{orden.pk}-{uuid.uuid4().hex[:8]}"

    respuesta = _transaccion_webpay().create(buy_order, session_id, monto, return_url)

    pago = PagoWebpay.objects.create(
        orden=orden,
        token=respuesta["token"],
        buy_order=buy_order,
        session_id=session_id,
        monto=monto,
        estado=EstadoPagoWebpay.INICIADO,
        respuesta_cruda=respuesta,
    )
    # Atributo transitorio: la URL de Transbank no se guarda en la base de
    # datos (no es un dato propio de HardPoint), solo la necesita la vista
    # que arma el formulario de redirección.
    pago.url_pago = respuesta["url"]
    return pago


# ============================================================
# BLOQUE 4 — CONFIRMAR EL PAGO (COMMIT SERVIDOR A SERVIDOR)
# El commit() es la llamada de red a Transbank; se hace FUERA de
# cualquier transacción de base de datos, para no mantener filas
# bloqueadas mientras se espera la respuesta. El resultado se
# procesa aparte, en _registrar_resultado_commit(), que sí es
# atómica y que vuelve a comprobar el estado del pago con
# select_for_update(): si dos peticiones llegaran con el mismo token
# (por ejemplo el navegador reintentando la vuelta desde Transbank),
# solo la primera hace el trabajo.
# ============================================================
def confirmar_pago_webpay(token: str) -> PagoWebpay:
    """Confirma con Transbank un token ya creado. Idempotente por token."""
    pago = PagoWebpay.objects.filter(token=token).first()
    if pago is None:
        raise PagoNoEncontradoError(f"No existe un pago Webpay con el token {token}.")

    if pago.estado != EstadoPagoWebpay.INICIADO:
        # Ya se procesó antes: no se vuelve a cobrar ni a descontar stock.
        return pago

    respuesta = _transaccion_webpay().commit(token)

    # El monto se compara ANTES de entrar a la transacción atómica: si se
    # comprobara adentro y se lanzara la excepción ahí, Django revertiría
    # también el pago.estado = ERROR que se acaba de guardar.
    monto_devuelto = int(respuesta.get("amount") or 0)
    if monto_devuelto != pago.monto:
        _marcar_error(pago.pk, respuesta)
        raise MontoNoCoincideError(pago.monto, monto_devuelto)

    return _registrar_resultado_commit(pago.pk, respuesta)


@transaction.atomic
def _marcar_error(pago_id: int, respuesta: dict) -> None:
    """Deja constancia de una respuesta anómala de Transbank (por ejemplo, monto distinto)."""
    pago = PagoWebpay.objects.select_for_update().get(pk=pago_id)
    if pago.estado != EstadoPagoWebpay.INICIADO:
        return
    pago.respuesta_cruda = respuesta
    pago.estado = EstadoPagoWebpay.ERROR
    pago.save()


@transaction.atomic
def _registrar_resultado_commit(pago_id: int, respuesta: dict) -> PagoWebpay:
    """Aplica el resultado del commit dentro de una transacción atómica."""
    pago = PagoWebpay.objects.select_for_update().get(pk=pago_id)

    if pago.estado != EstadoPagoWebpay.INICIADO:
        # Otra petición concurrente con el mismo token ya lo resolvió.
        return pago

    pago.respuesta_cruda = respuesta
    pago.response_code = respuesta.get("response_code")
    pago.authorization_code = respuesta.get("authorization_code") or ""
    pago.payment_type_code = respuesta.get("payment_type_code") or ""
    pago.card_number = (respuesta.get("card_detail") or {}).get("card_number") or ""

    aprobado = respuesta.get("status") == "AUTHORIZED" and respuesta.get("response_code") == 0
    if not aprobado:
        pago.estado = EstadoPagoWebpay.RECHAZADO
        pago.save()
        return pago

    try:
        pagar_orden(
            pago.orden,
            usuario=pago.orden.usuario,
            observacion=f"Pago aprobado por Webpay Plus (autorización {pago.authorization_code}).",
        )
    except StockInsuficienteError:
        # CASO CRÍTICO: Transbank ya aprobó y retuvo el dinero, pero el
        # stock ya no alcanza. Se devuelve el dinero y la orden queda
        # PENDIENTE: nunca un cliente cobrado sin su producto.
        _transaccion_webpay().refund(pago.token, float(pago.monto))
        pago.estado = EstadoPagoWebpay.REEMBOLSADO
        pago.save()
        return pago

    pago.estado = EstadoPagoWebpay.APROBADO
    pago.save()
    return pago


# ============================================================
# BLOQUE 5 — LOS OTROS TRES CASOS DEL RETORNO DE WEBPAY PLUS
# Ninguno de estos tres hace commit: Transbank ya avisa, en la propia
# vuelta, que no hay nada que cobrar. Solo se deja constancia en el
# PagoWebpay para que el historial quede completo.
# ============================================================
def anular_pago_por_usuario(tbk_token: str) -> PagoWebpay | None:
    """El cliente canceló el pago en el formulario de Webpay (TBK_TOKEN)."""
    pago = PagoWebpay.objects.filter(token=tbk_token).first()
    if pago is not None and pago.estado == EstadoPagoWebpay.INICIADO:
        pago.estado = EstadoPagoWebpay.ANULADO_POR_USUARIO
        pago.save(update_fields=["estado", "actualizado_en"])
    return pago


def expirar_pago_por_timeout(buy_order: str) -> PagoWebpay | None:
    """Venció el tiempo del formulario de pago (solo llegan TBK_ORDEN_COMPRA y TBK_ID_SESION)."""
    pago = PagoWebpay.objects.filter(buy_order=buy_order).first()
    if pago is not None and pago.estado == EstadoPagoWebpay.INICIADO:
        pago.estado = EstadoPagoWebpay.EXPIRADO
        pago.save(update_fields=["estado", "actualizado_en"])
    return pago


def marcar_error_de_formulario(token_ws: str) -> PagoWebpay | None:
    """Error de formulario: Transbank envía token_ws y TBK_TOKEN juntos.

    La documentación oficial de Transbank indica que, en este caso, el
    estado del intento es ambiguo y no se debe hacer commit. Se deja
    constancia del error sin tocar el stock ni la orden.
    """
    pago = PagoWebpay.objects.filter(token=token_ws).first()
    if pago is not None and pago.estado == EstadoPagoWebpay.INICIADO:
        pago.estado = EstadoPagoWebpay.ERROR
        pago.save(update_fields=["estado", "actualizado_en"])
    return pago
