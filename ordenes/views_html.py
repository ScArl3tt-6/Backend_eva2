# ============================================================
# ordenes/views_html.py — PANTALLAS HTML DE ÓRDENES
# Responsabilidad: listado de ventas con filtros y ficha de la
# orden con su detalle de precios congelados, su total, su código
# UUID, su historial y los botones de transición permitidos.
#
# Igual que en el carro, estas vistas NO reimplementan nada: llaman
# a ordenes/servicios.py, el mismo módulo que usa la API. Por eso:
#   · Pagar desde el HTML descuenta el stock de forma atómica.
#   · Si el stock no alcanza, se muestra un mensaje que dice
#     exactamente qué producto faltó y en qué cantidad.
#   · Cancelar una orden pagada repone el stock automáticamente.
#   · Solo se ofrecen las transiciones que la máquina de estados
#     permite desde el estado actual.
#
# Cualquiera puede VER el listado y la ficha de una orden; pagar o
# cambiar su estado exige una sesión de Administrador de TI (ver
# panel_solo_lectura_o_administrador en core/utilidades.py), que
# además queda registrado como autor del cambio en el historial.
# ============================================================

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from transbank.error.transbank_error import TransbankError

from core.utilidades import obtener_o_redirigir, panel_solo_lectura_o_administrador
from pagos.servicios import ErrorDePago, iniciar_pago_webpay

from .filtros import OrdenFilter
from .forms import CambiarEstadoOrdenForm
from .models import EstadoOrden, Orden
from .servicios import (
    CarroVacioError,
    StockInsuficienteError,
    TransicionInvalidaError,
    cambiar_estado_orden,
    pagar_orden,
    transiciones_posibles,
)

BASE_URL = "/panel/ordenes/"


# ============================================================
# BLOQUE 1 — LISTADO DE ÓRDENES
# Usa OrdenFilter, el mismo FilterSet de django-filter que
# GET /api/ordenes/, de modo que los filtros por estado, cliente y
# rango de fechas se comportan igual en la API y en la pantalla.
# El total viene anotado con Sum para no consultar el detalle de
# cada orden por separado.
# ============================================================
def ordenes_lista(request):
    """Listado de órdenes con filtros por estado, cliente y fechas."""
    base = Orden.objects.select_related("usuario").con_total()

    filtro = OrdenFilter(request.GET, queryset=base)
    ordenes = filtro.qs.order_by("-creada_en")

    paginador = Paginator(ordenes, 15)
    pagina = paginador.get_page(request.GET.get("page"))

    # --- Resumen por estado, calculado sobre el total de la base ---
    conteos = {estado: 0 for estado, _ in EstadoOrden.choices}
    for orden in Orden.objects.values("estado"):
        conteos[orden["estado"]] = conteos.get(orden["estado"], 0) + 1

    resumen = [
        {"estado": valor, "etiqueta": etiqueta, "total": conteos.get(valor, 0)}
        for valor, etiqueta in EstadoOrden.choices
    ]

    parametros = request.GET.copy()
    parametros.pop("page", None)

    contexto = {
        "titulo_pagina": "Órdenes de compra",
        "filtro": filtro,
        "pagina": pagina,
        "total_resultados": paginador.count,
        "resumen_estados": resumen,
        "total_ordenes": Orden.objects.count(),
        "parametros": parametros.urlencode(),
        "migas": [
            {"etiqueta": "Gestión", "url": "/panel/"},
            {"etiqueta": "Órdenes", "url": None},
        ],
    }
    return render(request, "ordenes/panel_ordenes.html", contexto)


# ============================================================
# BLOQUE 2 — FICHA DE LA ORDEN
# Muestra el número de orden (UUID), el cliente, el estado, el
# detalle con los precios congelados junto al precio actual del
# catálogo (para que se vea la diferencia), el total calculado y la
# línea de tiempo del historial.
# ============================================================
def orden_detalle(request, objeto_id):
    """Ficha completa de una orden con su detalle e historial."""
    orden, redireccion = obtener_o_redirigir(
        Orden,
        mensaje_error=f"No existe una orden con el id {objeto_id}.",
        pk=objeto_id,
    )
    if redireccion is not None:
        return redireccion(request)

    posibles = transiciones_posibles(orden)

    contexto = {
        "titulo_pagina": f"Orden {orden.codigo_corto}",
        "orden": orden,
        "detalles": orden.detalles.select_related("producto").order_by("producto__nombre"),
        "historial": orden.historial.select_related("cambiado_por").order_by("fecha", "id"),
        "transiciones": posibles,
        "formulario_estado": CambiarEstadoOrdenForm(estados_posibles=posibles),
        "puede_pagar": EstadoOrden.PAGADO in posibles,
        "puede_entregar": EstadoOrden.ENTREGADO in posibles,
        "puede_cancelar": EstadoOrden.CANCELADO in posibles,
        "migas": [
            {"etiqueta": "Gestión", "url": "/panel/"},
            {"etiqueta": "Órdenes", "url": BASE_URL},
            {"etiqueta": f"Orden {orden.codigo_corto}", "url": None},
        ],
    }
    return render(request, "ordenes/panel_orden_detalle.html", contexto)


# ============================================================
# BLOQUE 3 — REGISTRAR EL PAGO
# Llama a pagar_orden, la función que verifica y descuenta el stock
# de forma atómica. Si falla por stock, el mensaje de error detalla
# producto por producto cuánto se pidió y cuánto había, y la orden
# queda intacta en PENDIENTE.
# ============================================================
@panel_solo_lectura_o_administrador
def orden_pagar(request, objeto_id):
    """Registra el pago de la orden descontando el stock de forma atómica."""
    if request.method != "POST":
        return redirect(f"{BASE_URL}{objeto_id}/")

    orden, redireccion = obtener_o_redirigir(
        Orden,
        mensaje_error=f"No existe una orden con el id {objeto_id}.",
        pk=objeto_id,
    )
    if redireccion is not None:
        return redireccion(request)

    try:
        orden = pagar_orden(orden, usuario=request.user)
    except StockInsuficienteError as excepcion:
        # Mensaje explicativo: qué producto faltó y en qué cantidad.
        detalle = " ".join(
            f"«{f['producto']}» (SKU {f['sku']}): pidió {f['solicitado']} y hay {f['disponible']}."
            for f in excepcion.faltantes
        )
        messages.error(
            request,
            f"No se pudo registrar el pago por falta de stock. {detalle} "
            "No se descontó ninguna unidad y la orden sigue en PENDIENTE.",
        )
        return redirect(f"{BASE_URL}{orden.pk}/")
    except (TransicionInvalidaError, CarroVacioError) as excepcion:
        messages.error(request, str(excepcion))
        return redirect(f"{BASE_URL}{orden.pk}/")

    messages.success(
        request,
        f"Pago registrado. La orden {orden.codigo_corto} quedó PAGADA y el stock "
        "se descontó de cada producto.",
    )
    return redirect(f"{BASE_URL}{orden.pk}/")


# ============================================================
# BLOQUE 3-B — PAGAR CON WEBPAY PLUS
# No reemplaza al botón «Registrar el pago» (BLOQUE 3): queda como
# una forma nueva de pagar, pensada para que el administrador pueda
# cobrar una orden simulando el formulario real de Transbank en
# ambiente de integración. Crea la transacción (pagos/servicios.py)
# y renderiza un formulario que se autoenvía al formulario de pago
# de Transbank con el token recibido.
# ============================================================
@panel_solo_lectura_o_administrador
def orden_pagar_con_webpay(request, objeto_id):
    """Inicia un pago con Webpay Plus y redirige al formulario de Transbank."""
    if request.method != "POST":
        return redirect(f"{BASE_URL}{objeto_id}/")

    orden, redireccion = obtener_o_redirigir(
        Orden,
        mensaje_error=f"No existe una orden con el id {objeto_id}.",
        pk=objeto_id,
    )
    if redireccion is not None:
        return redireccion(request)

    # build_absolute_uri usa el esquema real de la petición (http en local,
    # https en el servidor detrás de Nginx), así que la vuelta de Transbank
    # nunca cae en una URL http:// en producción.
    return_url = request.build_absolute_uri("/webpay/retorno/")

    try:
        pago = iniciar_pago_webpay(orden, return_url)
    except ErrorDePago as excepcion:
        messages.error(request, str(excepcion))
        return redirect(f"{BASE_URL}{orden.pk}/")
    except TransbankError:
        messages.error(
            request,
            "No se pudo contactar a Webpay Plus en este momento. Intente de nuevo.",
        )
        return redirect(f"{BASE_URL}{orden.pk}/")

    contexto = {
        "titulo_pagina": "Redirigiendo a Webpay",
        "url_pago": pago.url_pago,
        "token": pago.token,
    }
    return render(request, "pagos/redireccion_webpay.html", contexto)


# ============================================================
# BLOQUE 4 — CAMBIO DE ESTADO
# Atiende los botones «Marcar entregada» y «Cancelar», y también el
# selector de estado del formulario. La legalidad de la transición
# la decide cambiar_estado_orden; aquí solo se traduce el resultado
# a un mensaje flash.
# ============================================================
@panel_solo_lectura_o_administrador
def orden_cambiar_estado(request, objeto_id):
    """Cambia el estado de la orden aplicando las transiciones permitidas."""
    if request.method != "POST":
        return redirect(f"{BASE_URL}{objeto_id}/")

    orden, redireccion = obtener_o_redirigir(
        Orden,
        mensaje_error=f"No existe una orden con el id {objeto_id}.",
        pk=objeto_id,
    )
    if redireccion is not None:
        return redireccion(request)

    nuevo_estado = (request.POST.get("estado") or "").strip().upper()
    observacion = (request.POST.get("observacion") or "").strip()

    if not nuevo_estado:
        messages.error(request, "Elija el estado al que quiere pasar la orden.")
        return redirect(f"{BASE_URL}{orden.pk}/")

    try:
        orden = cambiar_estado_orden(
            orden,
            nuevo_estado,
            usuario=request.user,
            observacion=observacion,
        )
    except StockInsuficienteError as excepcion:
        detalle = " ".join(
            f"«{f['producto']}» (SKU {f['sku']}): pidió {f['solicitado']} y hay {f['disponible']}."
            for f in excepcion.faltantes
        )
        messages.error(
            request,
            f"No se pudo pasar la orden a PAGADO por falta de stock. {detalle} "
            "No se descontó ninguna unidad y la orden sigue en PENDIENTE.",
        )
        return redirect(f"{BASE_URL}{orden.pk}/")
    except (TransicionInvalidaError, CarroVacioError) as excepcion:
        messages.error(request, str(excepcion))
        return redirect(f"{BASE_URL}{orden.pk}/")

    repuestos = getattr(orden, "stock_repuesto", [])
    if repuestos:
        detalle = ", ".join(
            f"{r['unidades_repuestas']} × {r['producto']}" for r in repuestos
        )
        messages.success(
            request,
            f"La orden {orden.codigo_corto} fue CANCELADA y el stock se repuso "
            f"automáticamente: {detalle}.",
        )
    elif orden.estado == EstadoOrden.PAGADO:
        messages.success(
            request,
            f"La orden {orden.codigo_corto} quedó PAGADA y el stock se descontó "
            "de cada producto.",
        )
    else:
        messages.success(
            request, f"La orden {orden.codigo_corto} quedó en estado {orden.estado}."
        )

    return redirect(f"{BASE_URL}{orden.pk}/")
