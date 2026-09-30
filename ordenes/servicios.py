# ============================================================
# ordenes/servicios.py — REGLAS DE NEGOCIO DE LAS ÓRDENES
# Responsabilidad: checkout, pago con descuento atómico de stock y
# máquina de estados de la orden. Es el módulo más importante del
# proyecto y el que sostiene el criterio de concurrencia.
#
# Funciones puras, sin HTTP: las llaman tanto la API REST
# (ordenes/views.py) como las pantallas HTML (ordenes/views_html.py),
# de modo que el control de stock es idéntico por ambos caminos.
#
# Las tres reglas que definen el negocio:
#   1) El CHECKOUT congela los precios y NO toca el stock.
#   2) El PAGO verifica y descuenta el stock de forma atómica.
#   3) CANCELAR una orden ya pagada REPONE el stock.
#
# Cómo se garantiza que el stock nunca quede negativo:
#   · transaction.atomic() envuelve cada operación: si algo falla,
#     se revierte todo (rollback) y no queda un estado a medias.
#   · select_for_update() bloquea en la base de datos las filas de
#     la orden y de los productos: el segundo cliente que intente
#     pagar el mismo producto ESPERA a que el primero termine y
#     luego relee el stock ya descontado.
#   · Las filas de productos se bloquean siempre en el mismo orden
#     (order_by("id")), lo que evita interbloqueos entre dos pagos
#     que compartan productos.
#   · El descuento se hace con F("stock") - cantidad, es decir con
#     una operación aritmética resuelta por PostgreSQL, sin leer y
#     escribir el valor desde Python.
#   · El CheckConstraint stock >= 0 del modelo es la última barrera.
# ============================================================

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from carro.models import Carro
from carro.servicios import vaciar_carro
from catalogo.models import Producto

from .models import DetalleOrden, EstadoOrden, HistorialEstadoOrden, Orden


# ============================================================
# BLOQUE 1 — EXCEPCIONES PROPIAS DEL NEGOCIO
# Cada una se traduce a un código HTTP distinto en las vistas:
#   CarroVacioError        → 400
#   StockInsuficienteError → 409 Conflict (con el detalle faltante)
#   TransicionInvalidaError→ 400
# ============================================================
class ErrorDeOrden(Exception):
    """Error de negocio al operar con órdenes."""


class CarroVacioError(ErrorDeOrden):
    """No se puede hacer checkout de un carro sin ítems."""

    def __init__(self, mensaje="Su carro está vacío: agregue productos antes de hacer el checkout."):
        """Guarda el mensaje que verá el cliente."""
        super().__init__(mensaje)


class StockInsuficienteError(ErrorDeOrden):
    """El stock disponible no cubre la orden; incluye el detalle faltante."""

    def __init__(self, faltantes: list[dict]):
        """Recibe la lista de productos problemáticos (pedido vs. disponible)."""
        self.faltantes = faltantes

        resumen = "; ".join(
            f"«{f['producto']}»: pidió {f['solicitado']} y hay {f['disponible']}"
            for f in faltantes
        )
        super().__init__(f"Stock insuficiente para completar el pago. {resumen}.")


class TransicionInvalidaError(ErrorDeOrden):
    """El cambio de estado solicitado no está permitido."""

    def __init__(self, estado_actual, estado_pedido, permitidos):
        """Arma un mensaje que explica qué transiciones sí se pueden hacer."""
        self.estado_actual = estado_actual
        self.estado_pedido = estado_pedido
        self.permitidos = sorted(permitidos)

        if permitidos:
            posibles = ", ".join(self.permitidos)
            detalle = f"Desde {estado_actual} solo puede pasar a: {posibles}."
        else:
            detalle = f"{estado_actual} es un estado final: ya no admite cambios."

        super().__init__(f"No se puede pasar de {estado_actual} a {estado_pedido}. {detalle}")


# ============================================================
# BLOQUE 2 — MÁQUINA DE ESTADOS
# Define qué transiciones son legales. ENTREGADO y CANCELADO son
# estados finales: no tienen salida, de modo que una orden
# entregada no puede "descancelarse" ni volver a cobrarse.
# ============================================================
TRANSICIONES_PERMITIDAS: dict[str, set[str]] = {
    EstadoOrden.PENDIENTE: {EstadoOrden.PAGADO, EstadoOrden.CANCELADO},
    EstadoOrden.PAGADO: {EstadoOrden.ENTREGADO, EstadoOrden.CANCELADO},
    EstadoOrden.ENTREGADO: set(),
    EstadoOrden.CANCELADO: set(),
}


def transiciones_posibles(orden: Orden) -> list[str]:
    """Devuelve los estados a los que la orden puede pasar ahora mismo."""
    return sorted(TRANSICIONES_PERMITIDAS.get(orden.estado, set()))


# ============================================================
# BLOQUE 3 — REGISTRO DEL HISTORIAL (AUDITORÍA)
# Cada transición deja una fila en HistorialEstadoOrden: de dónde
# venía, a dónde fue, quién la hizo y por qué. Es la evidencia que
# se muestra en la línea de tiempo del detalle de la orden.
# ============================================================
def _registrar_historial(orden, estado_anterior, estado_nuevo, usuario=None, observacion=""):
    """Anota una transición de estado en el historial de la orden."""
    return HistorialEstadoOrden.objects.create(
        orden=orden,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        cambiado_por=usuario if (usuario is not None and usuario.is_authenticated) else None,
        observacion=observacion[:255],
    )


# ============================================================
# BLOQUE 4 — CHECKOUT: DEL CARRO A LA ORDEN
# POST /api/ordenes/checkout/
#
# Qué hace y por qué:
#   · Bloquea el carro con select_for_update() para que un doble
#     clic o dos peticiones simultáneas no generen dos órdenes con
#     el mismo contenido.
#   · Exige que el carro tenga ítems y que los productos sigan
#     publicados.
#   · Crea la orden en PENDIENTE y copia el precio vigente de cada
#     producto en DetalleOrden.precio_unitario: ese es el PRECIO
#     CONGELADO. Si mañana el catálogo sube de precio, esta venta
#     no cambia.
#   · NO toca el stock. El stock se mueve recién al pagar, porque
#     una orden pendiente puede no pagarse nunca y reservar stock
#     ahí dejaría productos bloqueados sin venta.
#   · Vacía el carro (baja lógica) porque su contenido ya quedó
#     registrado en la orden.
# ============================================================
@transaction.atomic
def realizar_checkout(usuario) -> Orden:
    """Convierte el carro del cliente en una orden PENDIENTE con precios congelados."""
    # --- Bloqueo del carro para evitar dos checkout simultáneos ---
    carro, _ = Carro.objects.get_or_create(usuario=usuario)
    carro = Carro.objects.select_for_update().get(pk=carro.pk)

    items = list(carro.items.filter(activo=True).select_related("producto"))
    if not items:
        raise CarroVacioError()

    # --- Los productos dados de baja no se pueden vender ---
    no_disponibles = [
        {
            "producto": item.producto.nombre,
            "sku": item.producto.sku,
            "solicitado": item.cantidad,
            "disponible": 0,
            "motivo": "El producto fue dado de baja del catálogo.",
        }
        for item in items
        if not item.producto.activo
    ]
    if no_disponibles:
        raise StockInsuficienteError(no_disponibles)

    # --- Cabecera de la orden ---
    orden = Orden.objects.create(usuario=usuario, estado=EstadoOrden.PENDIENTE)

    # --- Detalle con el PRECIO CONGELADO de cada producto ---
    DetalleOrden.objects.bulk_create(
        [
            DetalleOrden(
                orden=orden,
                producto=item.producto,
                cantidad=item.cantidad,
                precio_unitario=item.producto.precio,
            )
            for item in items
        ]
    )

    # --- Auditoría: nacimiento de la orden (None → PENDIENTE) ---
    _registrar_historial(
        orden,
        estado_anterior=None,
        estado_nuevo=EstadoOrden.PENDIENTE,
        usuario=usuario,
        observacion="Orden creada desde el carro con los precios vigentes congelados.",
    )

    # --- El carro ya cumplió su función ---
    vaciar_carro(carro)

    return orden


# ============================================================
# BLOQUE 5 — PAGO: LA OPERACIÓN CRÍTICA DE CONCURRENCIA
# POST /api/ordenes/{id}/pagar/  (y también PATCH ... a PAGADO)
#
# Simula una pasarela de pago aprobada. La secuencia es
# deliberada:
#   1) Se bloquea la orden y se comprueba que siga PENDIENTE, para
#      que dos peticiones no la cobren dos veces.
#   2) Se bloquean TODAS las filas de productos implicadas en un
#      orden fijo por id. El segundo pago simultáneo se queda
#      esperando aquí.
#   3) Con las filas bloqueadas se relee el stock REAL y se
#      verifica producto por producto. Si a alguno no le alcanza,
#      se lanza StockInsuficienteError: la excepción revierte la
#      transacción completa, la orden sigue PENDIENTE y la API
#      responde 409 Conflict con el detalle de los faltantes.
#   4) Si todo alcanza, se descuenta con F("stock") - cantidad,
#      se marca PAGADO y se guarda la fecha de pago.
#
# Resultado: si dos clientes pagan el último producto casi a la
# vez, uno queda PAGADO y el otro es rechazado limpiamente. El
# stock final es 0, nunca -1.
# ============================================================
@transaction.atomic
def pagar_orden(orden: Orden, usuario=None, observacion="") -> Orden:
    """Cobra la orden verificando y descontando el stock de forma atómica."""
    # --- Paso 1: bloquear la orden y revalidar su estado ---
    orden = Orden.objects.select_for_update().get(pk=orden.pk)

    if orden.estado != EstadoOrden.PENDIENTE:
        raise TransicionInvalidaError(
            orden.estado,
            EstadoOrden.PAGADO,
            TRANSICIONES_PERMITIDAS.get(orden.estado, set()),
        )

    detalles = list(orden.detalles.select_related("producto"))
    if not detalles:
        raise CarroVacioError("La orden no tiene productos, no se puede pagar.")

    # --- Paso 2: bloquear las filas de productos en un orden fijo ---
    ids_productos = sorted({detalle.producto_id for detalle in detalles})
    productos_bloqueados = {
        producto.id: producto
        for producto in Producto.objects.select_for_update()
        .filter(id__in=ids_productos)
        .order_by("id")
    }

    # --- Paso 3: verificar el stock real, ya bloqueado ---
    faltantes = []
    for detalle in detalles:
        producto = productos_bloqueados.get(detalle.producto_id)

        if producto is None:
            faltantes.append(
                {
                    "producto": detalle.producto.nombre,
                    "sku": detalle.producto.sku,
                    "solicitado": detalle.cantidad,
                    "disponible": 0,
                    "motivo": "El producto ya no está en el catálogo.",
                }
            )
            continue

        if not producto.activo:
            faltantes.append(
                {
                    "producto": producto.nombre,
                    "sku": producto.sku,
                    "solicitado": detalle.cantidad,
                    "disponible": producto.stock,
                    "motivo": "El producto fue dado de baja del catálogo.",
                }
            )
            continue

        if producto.stock < detalle.cantidad:
            faltantes.append(
                {
                    "producto": producto.nombre,
                    "sku": producto.sku,
                    "solicitado": detalle.cantidad,
                    "disponible": producto.stock,
                    "motivo": "Stock insuficiente.",
                }
            )

    if faltantes:
        # La excepción provoca el rollback: no se descuenta nada y
        # la orden permanece en PENDIENTE.
        raise StockInsuficienteError(faltantes)

    # --- Paso 4: descontar el stock en la propia base de datos ---
    for detalle in detalles:
        Producto.objects.filter(pk=detalle.producto_id).update(
            stock=F("stock") - detalle.cantidad
        )

    estado_anterior = orden.estado
    orden.estado = EstadoOrden.PAGADO
    orden.pagada_en = timezone.now()
    orden.save(update_fields=["estado", "pagada_en", "actualizada_en"])

    _registrar_historial(
        orden,
        estado_anterior=estado_anterior,
        estado_nuevo=EstadoOrden.PAGADO,
        usuario=usuario,
        observacion=observacion or "Pago aprobado. Se descontó el stock de cada producto.",
    )

    return orden


# ============================================================
# BLOQUE 6 — REPOSICIÓN DE STOCK AL CANCELAR UNA ORDEN PAGADA
# Si la venta ya había descontado stock y se cancela, las unidades
# vuelven a bodega. Se usa el mismo patrón que el pago: bloqueo de
# filas en orden fijo y suma con F("stock") + cantidad, para que la
# reposición sea tan segura como el descuento.
# ============================================================
def _reponer_stock(orden: Orden) -> list[dict]:
    """Devuelve a bodega las unidades de una orden pagada que se cancela."""
    detalles = list(orden.detalles.select_related("producto"))
    ids_productos = sorted({detalle.producto_id for detalle in detalles})

    # Bloqueo en orden fijo por id: mismo criterio que en el pago.
    list(Producto.objects.select_for_update().filter(id__in=ids_productos).order_by("id"))

    repuestos = []
    for detalle in detalles:
        Producto.objects.filter(pk=detalle.producto_id).update(
            stock=F("stock") + detalle.cantidad
        )
        repuestos.append(
            {
                "producto": detalle.producto.nombre,
                "sku": detalle.producto.sku,
                "unidades_repuestas": detalle.cantidad,
            }
        )

    return repuestos


# ============================================================
# BLOQUE 7 — CAMBIO DE ESTADO (SOLO ADMINISTRADOR)
# PATCH /api/ordenes/{id}/estado/
#
# Aplica TRANSICIONES_PERMITIDAS y delega el trabajo real:
#   PENDIENTE → PAGADO     : llama a pagar_orden (descuenta stock)
#   PENDIENTE → CANCELADO  : nada que reponer, el stock no se tocó
#   PAGADO    → ENTREGADO  : cierre feliz
#   PAGADO    → CANCELADO  : repone el stock automáticamente
# Cualquier otra combinación lanza TransicionInvalidaError → 400.
# ============================================================
@transaction.atomic
def cambiar_estado_orden(orden: Orden, nuevo_estado: str, usuario=None, observacion="") -> Orden:
    """Cambia el estado de la orden aplicando las transiciones permitidas."""
    nuevo_estado = str(nuevo_estado).strip().upper()

    if nuevo_estado not in EstadoOrden.values:
        raise TransicionInvalidaError(
            orden.estado,
            nuevo_estado or "(vacío)",
            TRANSICIONES_PERMITIDAS.get(orden.estado, set()),
        )

    # --- Bloqueo de la orden antes de validar la transición ---
    orden = Orden.objects.select_for_update().get(pk=orden.pk)
    estado_anterior = orden.estado
    permitidos = TRANSICIONES_PERMITIDAS.get(estado_anterior, set())

    if nuevo_estado not in permitidos:
        raise TransicionInvalidaError(estado_anterior, nuevo_estado, permitidos)

    # --- PAGADO: se reutiliza exactamente la lógica del pago ---
    if nuevo_estado == EstadoOrden.PAGADO:
        return pagar_orden(
            orden,
            usuario=usuario,
            observacion=observacion or "Pago registrado por el administrador de TI.",
        )

    # --- CANCELADO desde PAGADO: hay stock que devolver ---
    repuestos = []
    if nuevo_estado == EstadoOrden.CANCELADO and estado_anterior == EstadoOrden.PAGADO:
        repuestos = _reponer_stock(orden)

    orden.estado = nuevo_estado
    orden.save(update_fields=["estado", "actualizada_en"])

    if repuestos:
        detalle_reposicion = ", ".join(
            f"{r['unidades_repuestas']} × {r['producto']}" for r in repuestos
        )
        texto = observacion or "Orden cancelada por el administrador de TI."
        texto = f"{texto} Stock repuesto: {detalle_reposicion}."
    else:
        texto = observacion or f"Estado cambiado a {nuevo_estado} por el administrador de TI."

    _registrar_historial(
        orden,
        estado_anterior=estado_anterior,
        estado_nuevo=nuevo_estado,
        usuario=usuario,
        observacion=texto,
    )

    # Se deja a la vista el detalle de lo repuesto, para el mensaje.
    orden.stock_repuesto = repuestos
    return orden
