# ============================================================
# carro/views_html.py — PANTALLA HTML DEL CARRO
# Responsabilidad: operar el carro persistido de un cliente desde
# /panel/carros/, con el selector «Ver carro de: [cliente]».
#
# Punto central para la defensa: estas vistas llaman a las MISMAS
# funciones de carro/servicios.py y ordenes/servicios.py que usa la
# API REST. No hay una segunda implementación de las reglas, así
# que el control de duplicados, la validación de stock y el
# comportamiento del checkout son idénticos por ambos caminos.
#
# La pantalla no tiene login (así lo pide el enunciado): el cliente
# cuyo carro se opera se elige con un parámetro ?usuario=<id>.
# ============================================================

from django.contrib import messages
from django.shortcuts import redirect, render

from catalogo.models import Producto
from core.utilidades import entero_o_none, obtener_o_redirigir
from ordenes.servicios import (
    CarroVacioError,
    StockInsuficienteError,
    realizar_checkout,
)
from usuarios.models import Rol, Usuario

from .forms import ActualizarCantidadForm, AgregarAlCarroForm, SeleccionarClienteForm
from .servicios import (
    ErrorDeCarro,
    actualizar_cantidad,
    agregar_producto,
    obtener_carro,
    quitar_producto,
    revisar_disponibilidad,
    vaciar_carro,
)

BASE_URL = "/panel/carros/"


# ============================================================
# BLOQUE 1 — RESOLUCIÓN DEL CLIENTE ELEGIDO
# Todas las acciones necesitan saber sobre qué carro operan. Esta
# función centraliza la lectura del parámetro y su validación, de
# modo que un ?usuario=abc o un id inexistente no produzca un error
# sino un mensaje claro.
# ============================================================
def _resolver_cliente(request, origen_datos=None):
    """Devuelve (cliente, respuesta_de_error) según el parámetro usuario."""
    datos = origen_datos if origen_datos is not None else request.GET
    identificador = entero_o_none(datos.get("usuario"))

    if identificador is None:
        return None, None

    cliente = Usuario.objects.filter(pk=identificador, rol=Rol.CLIENTE).first()
    if cliente is None:
        messages.error(
            request,
            f"No existe un cliente con el id {identificador}. "
            "Elija un cliente de la lista.",
        )
        return None, redirect(BASE_URL)

    return cliente, None


def _url_del_carro(cliente) -> str:
    """URL de la pantalla del carro para un cliente concreto."""
    return f"{BASE_URL}?usuario={cliente.pk}"


# ============================================================
# BLOQUE 2 — PANTALLA PRINCIPAL DEL CARRO
# Muestra el carro persistido del cliente elegido: ítems vigentes,
# precio vigente de cada producto, subtotales, total y avisos de
# stock. Los subtotales y el total son calculados, no almacenados.
# ============================================================
def carros_panel(request):
    """Pantalla de gestión de carros con el selector de cliente."""
    cliente, error = _resolver_cliente(request)
    if error is not None:
        return error

    selector = SeleccionarClienteForm(
        initial={"usuario": cliente.pk if cliente else None}
    )

    contexto = {
        "titulo_pagina": "Carros de compras",
        "selector": selector,
        "cliente": cliente,
        "formulario_agregar": AgregarAlCarroForm(),
        "formulario_cantidad": ActualizarCantidadForm(),
        "total_clientes": Usuario.objects.filter(rol=Rol.CLIENTE, is_active=True).count(),
        "migas": [
            {"etiqueta": "Gestión", "url": "/panel/"},
            {"etiqueta": "Carros", "url": None},
        ],
    }

    if cliente is not None:
        carro = obtener_carro(cliente)
        contexto.update(
            {
                "carro": carro,
                "items": list(carro.items_activos),
                "items_quitados": carro.items.filter(activo=False).select_related("producto"),
                "avisos": revisar_disponibilidad(carro),
                "ordenes_recientes": cliente.ordenes.con_total().order_by("-creada_en")[:5],
            }
        )

    return render(request, "carro/panel_carros.html", contexto)


# ============================================================
# BLOQUE 3 — AGREGAR UN PRODUCTO
# Delega en carro.servicios.agregar_producto, que suma la cantidad
# si el producto ya estaba en el carro (sin duplicar la fila) y
# rechaza cantidades mayores al stock. No descuenta stock.
# ============================================================
def carro_agregar(request):
    """Agrega un producto al carro del cliente elegido."""
    if request.method != "POST":
        return redirect(BASE_URL)

    cliente, error = _resolver_cliente(request, request.POST)
    if error is not None:
        return error
    if cliente is None:
        messages.error(request, "Elija primero un cliente para operar su carro.")
        return redirect(BASE_URL)

    formulario = AgregarAlCarroForm(request.POST)
    if not formulario.is_valid():
        for campo, errores in formulario.errors.items():
            for texto in errores:
                messages.error(request, f"{campo}: {texto}")
        return redirect(_url_del_carro(cliente))

    carro = obtener_carro(cliente)
    producto = formulario.cleaned_data["producto"]
    cantidad = formulario.cleaned_data["cantidad"]

    try:
        item = agregar_producto(carro, producto, cantidad)
    except ErrorDeCarro as excepcion:
        messages.error(request, str(excepcion))
        return redirect(_url_del_carro(cliente))

    messages.success(
        request,
        f"«{producto.nombre}» quedó en el carro con {item.cantidad} unidad(es). "
        "No se descontó stock: eso ocurre solo al pagar la orden.",
    )
    return redirect(_url_del_carro(cliente))


# ============================================================
# BLOQUE 4 — MODIFICAR LA CANTIDAD DE UN ÍTEM
# ============================================================
def carro_actualizar(request, producto_id):
    """Fija la cantidad exacta de un producto del carro."""
    if request.method != "POST":
        return redirect(BASE_URL)

    cliente, error = _resolver_cliente(request, request.POST)
    if error is not None:
        return error
    if cliente is None:
        messages.error(request, "Elija primero un cliente para operar su carro.")
        return redirect(BASE_URL)

    producto, redireccion = obtener_o_redirigir(
        Producto,
        mensaje_error=f"No existe un producto con el id {producto_id}.",
        pk=producto_id,
    )
    if redireccion is not None:
        return redireccion(request)

    formulario = ActualizarCantidadForm(request.POST)
    if not formulario.is_valid():
        for errores in formulario.errors.values():
            for texto in errores:
                messages.error(request, texto)
        return redirect(_url_del_carro(cliente))

    carro = obtener_carro(cliente)

    try:
        item = actualizar_cantidad(carro, producto, formulario.cleaned_data["cantidad"])
    except ErrorDeCarro as excepcion:
        messages.error(request, str(excepcion))
        return redirect(_url_del_carro(cliente))

    messages.success(
        request, f"«{producto.nombre}» quedó con {item.cantidad} unidad(es) en el carro."
    )
    return redirect(_url_del_carro(cliente))


# ============================================================
# BLOQUE 5 — QUITAR UN ÍTEM (BAJA LÓGICA)
# ============================================================
def carro_quitar(request, producto_id):
    """Quita un producto del carro mediante baja lógica."""
    if request.method != "POST":
        return redirect(BASE_URL)

    cliente, error = _resolver_cliente(request, request.POST)
    if error is not None:
        return error
    if cliente is None:
        messages.error(request, "Elija primero un cliente para operar su carro.")
        return redirect(BASE_URL)

    producto, redireccion = obtener_o_redirigir(
        Producto,
        mensaje_error=f"No existe un producto con el id {producto_id}.",
        pk=producto_id,
    )
    if redireccion is not None:
        return redireccion(request)

    carro = obtener_carro(cliente)

    try:
        quitar_producto(carro, producto)
    except ErrorDeCarro as excepcion:
        messages.error(request, str(excepcion))
        return redirect(_url_del_carro(cliente))

    messages.warning(
        request,
        f"«{producto.nombre}» se quitó del carro. "
        "La fila del ítem se conserva con «activo = false».",
    )
    return redirect(_url_del_carro(cliente))


# ============================================================
# BLOQUE 6 — VACIAR EL CARRO
# ============================================================
def carro_vaciar(request):
    """Deja todos los ítems del carro con activo = False."""
    if request.method != "POST":
        return redirect(BASE_URL)

    cliente, error = _resolver_cliente(request, request.POST)
    if error is not None:
        return error
    if cliente is None:
        messages.error(request, "Elija primero un cliente para operar su carro.")
        return redirect(BASE_URL)

    carro = obtener_carro(cliente)
    cantidad = vaciar_carro(carro)

    if cantidad:
        messages.warning(request, f"Se quitaron {cantidad} ítem(s) del carro (baja lógica).")
    else:
        messages.info(request, "El carro ya estaba vacío.")

    return redirect(_url_del_carro(cliente))


# ============================================================
# BLOQUE 7 — CHECKOUT DESDE EL HTML
# Llama a ordenes.servicios.realizar_checkout, exactamente la misma
# función que atiende POST /api/ordenes/checkout/. Por eso el
# precio se congela igual y el stock tampoco se toca aquí.
# ============================================================
def carro_checkout(request):
    """Genera la orden a partir del carro del cliente elegido."""
    if request.method != "POST":
        return redirect(BASE_URL)

    cliente, error = _resolver_cliente(request, request.POST)
    if error is not None:
        return error
    if cliente is None:
        messages.error(request, "Elija primero un cliente para operar su carro.")
        return redirect(BASE_URL)

    try:
        orden = realizar_checkout(cliente)
    except CarroVacioError as excepcion:
        messages.error(request, str(excepcion))
        return redirect(_url_del_carro(cliente))
    except StockInsuficienteError as excepcion:
        messages.error(request, str(excepcion))
        return redirect(_url_del_carro(cliente))

    messages.success(
        request,
        f"Orden {orden.codigo_corto} creada en estado PENDIENTE con los precios "
        "congelados. El stock se descontará al registrar el pago.",
    )
    return redirect(f"/panel/ordenes/{orden.pk}/")
