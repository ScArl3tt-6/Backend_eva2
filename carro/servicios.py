# ============================================================
# carro/servicios.py — REGLAS DE NEGOCIO DEL CARRO
# Responsabilidad: concentrar toda la lógica del carro de compras
# en funciones puras, independientes de HTTP.
#
# Por qué existe esta capa: la API REST (carro/views.py) y las
# pantallas HTML (carro/views_html.py) llaman exactamente a estas
# mismas funciones. Así es imposible que el carro se comporte de
# una manera desde Swagger y de otra desde el navegador, y las
# validaciones de stock y de duplicados quedan escritas una sola
# vez.
#
# Regla central que se aplica aquí: agregar al carro NO descuenta
# stock. El stock solo se mueve al pagar la orden
# (ordenes/servicios.py). Aquí el stock se consulta únicamente
# como validación informativa, para no dejar que el cliente cargue
# más unidades de las que existen.
# ============================================================

from django.db import transaction

from catalogo.models import Producto

from .models import Carro, ItemCarro


# ============================================================
# BLOQUE 1 — EXCEPCIONES PROPIAS DEL CARRO
# Permiten que las vistas traduzcan cada fallo al código HTTP o al
# mensaje flash correspondiente, sin inspeccionar cadenas de texto.
# ============================================================
class ErrorDeCarro(Exception):
    """Error de negocio del carro de compras."""


class ProductoNoDisponibleError(ErrorDeCarro):
    """El producto está dado de baja o no tiene stock."""


class CantidadInvalidaError(ErrorDeCarro):
    """La cantidad pedida no es un entero mayor o igual a 1."""


class StockInsuficienteEnCarroError(ErrorDeCarro):
    """La cantidad pedida supera el stock disponible del producto."""

    def __init__(self, producto, solicitado, disponible):
        """Guarda el detalle del faltante para poder mostrarlo al cliente."""
        self.producto = producto
        self.solicitado = solicitado
        self.disponible = disponible
        super().__init__(
            f"«{producto.nombre}»: pidió {solicitado} unidades y solo hay {disponible} disponibles."
        )


class ItemNoEnCarroError(ErrorDeCarro):
    """El producto indicado no está en el carro."""


# ============================================================
# BLOQUE 2 — OBTENCIÓN DEL CARRO
# El carro se crea con una señal al registrar al cliente, pero
# get_or_create deja la función a prueba de datos antiguos o de
# usuarios creados antes de que existiera la señal.
# ============================================================
def obtener_carro(usuario) -> Carro:
    """Devuelve el carro persistente del usuario, creándolo si faltara."""
    carro, _ = Carro.objects.get_or_create(usuario=usuario)
    return carro


# ============================================================
# BLOQUE 3 — VALIDACIÓN DE LA CANTIDAD
# Se acepta texto (viene de un formulario HTML) y se exige un
# entero mayor o igual a 1, igual que el CheckConstraint de la
# base de datos.
# ============================================================
def _validar_cantidad(cantidad) -> int:
    """Convierte y valida la cantidad pedida; lanza CantidadInvalidaError."""
    try:
        numero = int(cantidad)
    except (TypeError, ValueError):
        raise CantidadInvalidaError("La cantidad debe ser un número entero.")

    if numero < 1:
        raise CantidadInvalidaError("La cantidad debe ser al menos 1.")

    return numero


# ============================================================
# BLOQUE 4 — AGREGAR UN PRODUCTO
# Reglas que se cumplen:
#   · Producto inactivo o sin stock → ProductoNoDisponibleError.
#   · Si el producto YA está en el carro, se suma la cantidad al
#     ítem existente en lugar de crear otra fila. El
#     UniqueConstraint(carro, producto) respalda esa regla en la
#     base de datos.
#   · Si el ítem estaba dado de baja (activo=False), se reactiva y
#     la cantidad parte desde la nueva, no desde la antigua.
#   · La cantidad total del ítem nunca puede superar el stock
#     actual; si lo supera se lanza StockInsuficienteEnCarroError
#     con el detalle de lo pedido y lo disponible.
#   · NO se descuenta stock: eso ocurre solo al pagar.
# La operación es atómica para que la lectura del ítem y su
# actualización no se entrelacen con otra petición del mismo
# cliente.
# ============================================================
@transaction.atomic
def agregar_producto(carro: Carro, producto: Producto, cantidad=1) -> ItemCarro:
    """Agrega un producto al carro o suma la cantidad si ya estaba."""
    cantidad = _validar_cantidad(cantidad)

    # --- El producto debe estar publicado y con existencias ---
    if not producto.activo:
        raise ProductoNoDisponibleError(
            f"«{producto.nombre}» está dado de baja y no se puede comprar."
        )
    if producto.stock == 0:
        raise ProductoNoDisponibleError(f"«{producto.nombre}» no tiene stock disponible.")

    item = ItemCarro.objects.filter(carro=carro, producto=producto).first()

    if item is None:
        # --- Primera vez que este producto entra al carro ---
        if cantidad > producto.stock:
            raise StockInsuficienteEnCarroError(producto, cantidad, producto.stock)
        return ItemCarro.objects.create(carro=carro, producto=producto, cantidad=cantidad)

    if not item.activo:
        # --- El ítem había sido quitado: se reactiva desde cero ---
        if cantidad > producto.stock:
            raise StockInsuficienteEnCarroError(producto, cantidad, producto.stock)
        item.activo = True
        item.cantidad = cantidad
        item.save(update_fields=["activo", "cantidad", "actualizado_en"])
        return item

    # --- El producto ya estaba: se suma sin duplicar la fila ---
    cantidad_total = item.cantidad + cantidad
    if cantidad_total > producto.stock:
        raise StockInsuficienteEnCarroError(producto, cantidad_total, producto.stock)

    item.cantidad = cantidad_total
    item.save(update_fields=["cantidad", "actualizado_en"])
    return item


# ============================================================
# BLOQUE 5 — MODIFICAR LA CANTIDAD DE UN ÍTEM
# Fija la cantidad exacta (no suma). Valida contra el stock actual
# y vuelve a reactivar el ítem si estaba dado de baja.
# ============================================================
@transaction.atomic
def actualizar_cantidad(carro: Carro, producto: Producto, cantidad) -> ItemCarro:
    """Fija la cantidad exacta de un producto que ya está en el carro."""
    cantidad = _validar_cantidad(cantidad)

    item = ItemCarro.objects.filter(carro=carro, producto=producto).first()
    if item is None:
        raise ItemNoEnCarroError(f"«{producto.nombre}» no está en el carro.")

    if not producto.activo:
        raise ProductoNoDisponibleError(
            f"«{producto.nombre}» está dado de baja y no se puede comprar."
        )

    if cantidad > producto.stock:
        raise StockInsuficienteEnCarroError(producto, cantidad, producto.stock)

    item.cantidad = cantidad
    item.activo = True
    item.save(update_fields=["cantidad", "activo", "actualizado_en"])
    return item


# ============================================================
# BLOQUE 6 — QUITAR UN ÍTEM (BAJA LÓGICA)
# Regla de la pauta: nada de negocio se borra físicamente. Quitar
# un producto del carro deja el ítem con activo=False, de modo que
# la fila se conserva y puede reactivarse al volver a agregarlo.
# ============================================================
@transaction.atomic
def quitar_producto(carro: Carro, producto: Producto) -> ItemCarro:
    """Quita un producto del carro mediante baja lógica."""
    item = ItemCarro.objects.filter(carro=carro, producto=producto).first()
    if item is None:
        raise ItemNoEnCarroError(f"«{producto.nombre}» no está en el carro.")

    if item.activo:
        item.activo = False
        item.save(update_fields=["activo", "actualizado_en"])

    return item


# ============================================================
# BLOQUE 7 — VACIAR EL CARRO
# Deja todos los ítems en activo=False con una sola consulta de
# actualización. Se usa desde el endpoint DELETE /api/carro/ y
# también al final del checkout, cuando el contenido del carro ya
# quedó registrado en la orden.
# ============================================================
@transaction.atomic
def vaciar_carro(carro: Carro) -> int:
    """Da de baja todos los ítems del carro y devuelve cuántos afectó."""
    return carro.items.filter(activo=True).update(activo=False)


# ============================================================
# BLOQUE 8 — AVISOS DE STOCK DEL CARRO
# Revisa el carro completo y devuelve los ítems cuyo stock ya no
# alcanza (porque otro cliente compró antes). Permite avisar en la
# pantalla del carro antes de intentar el checkout, sin bloquear
# nada: la verificación definitiva ocurre al pagar.
# ============================================================
def revisar_disponibilidad(carro: Carro) -> list[dict]:
    """Devuelve los ítems del carro cuyo stock actual es insuficiente."""
    avisos = []
    for item in carro.items_activos:
        if not item.producto.activo:
            avisos.append(
                {
                    "producto": item.producto.nombre,
                    "sku": item.producto.sku,
                    "motivo": "El producto fue dado de baja del catálogo.",
                    "solicitado": item.cantidad,
                    "disponible": 0,
                }
            )
        elif item.producto.stock < item.cantidad:
            avisos.append(
                {
                    "producto": item.producto.nombre,
                    "sku": item.producto.sku,
                    "motivo": "El stock disponible bajó por debajo de la cantidad pedida.",
                    "solicitado": item.cantidad,
                    "disponible": item.producto.stock,
                }
            )
    return avisos
