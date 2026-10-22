# ============================================================
# ordenes/tests.py — PRUEBAS DEL CHECKOUT, EL PAGO Y EL STOCK
# Responsabilidad: comprobar el corazón del negocio y del criterio
# de concurrencia de la rúbrica:
#
#   1. El checkout congela los precios y NO descuenta stock.
#   2. El pago SÍ descuenta stock, de forma atómica.
#   3. El pago con stock insuficiente responde 409 y no modifica nada.
#   4. Cancelar una orden PAGADA repone el stock.
#   5. Las transiciones inválidas responden 400.
#   6. Dos pagos simultáneos por el último producto: solo uno queda
#      PAGADO y el stock nunca llega a ser negativo.
#   7. Un cliente jamás ve las órdenes de otro.
#
# La prueba de concurrencia usa TransactionTestCase, porque necesita
# transacciones reales (TestCase envuelve cada prueba en una
# transacción y eso impediría que los hilos vieran los cambios).
# ============================================================

import threading
from decimal import Decimal

from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from carro.servicios import agregar_producto, obtener_carro
from catalogo.models import Categoria, Marca, Producto
from ordenes.models import DetalleOrden, EstadoOrden, HistorialEstadoOrden, Orden
from ordenes.servicios import (
    TRANSICIONES_PERMITIDAS,
    CarroVacioError,
    StockInsuficienteError,
    TransicionInvalidaError,
    cambiar_estado_orden,
    pagar_orden,
    realizar_checkout,
    transiciones_posibles,
)
from usuarios.models import Rol, Usuario


# ============================================================
# BLOQUE 1 — ESCENARIO BASE
# ============================================================
class BaseOrdenes(APITestCase):
    """Escenario base con dos clientes, un administrador y productos."""

    CLAVE = "Compra.Segura.2026"
    CLAVE_ADMIN = "Llave.Segura.2026"

    @classmethod
    def setUpTestData(cls):
        """Crea usuarios y productos con distintos niveles de stock."""
        cls.cliente = Usuario.objects.create_user(
            username="orden_uno", email="orden_uno@hardpointpc.cl",
            password=cls.CLAVE, rol=Rol.CLIENTE,
        )
        cls.otro_cliente = Usuario.objects.create_user(
            username="orden_dos", email="orden_dos@hardpointpc.cl",
            password=cls.CLAVE, rol=Rol.CLIENTE,
        )
        cls.administrador = Usuario.objects.create_user(
            username="orden_admin", email="orden_admin@hardpointpc.cl",
            password=cls.CLAVE_ADMIN, rol=Rol.ADMINISTRADOR,
        )

        cls.categoria = Categoria.objects.create(nombre="Procesadores", icono="bi-cpu")
        cls.marca = Marca.objects.create(nombre="AMD", pais_origen="Estados Unidos")

        cls.producto = Producto.objects.create(
            sku="CPU-ORDEN-01", nombre="Procesador de prueba",
            categoria=cls.categoria, marca=cls.marca,
            precio=Decimal("279990"), stock=10,
        )
        cls.producto_escaso = Producto.objects.create(
            sku="CPU-ORDEN-ESCASO", nombre="Procesador con una unidad",
            categoria=cls.categoria, marca=cls.marca,
            precio=Decimal("899990"), stock=1,
        )

    def entrar(self, username="orden_uno", password=None):
        """Autentica el cliente de pruebas con un token Bearer."""
        respuesta = self.client.post(
            "/api/auth/login/",
            {"username": username, "password": password or self.CLAVE},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK, respuesta.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['access']}")
        return respuesta.data

    def entrar_como_administrador(self):
        """Autentica como Administrador de TI."""
        return self.entrar("orden_admin", self.CLAVE_ADMIN)

    def cargar_carro(self, usuario, producto, cantidad):
        """Deja un producto en el carro del usuario usando el servicio real."""
        carro = obtener_carro(usuario)
        agregar_producto(carro, producto, cantidad)
        return carro


# ============================================================
# BLOQUE 2 — CHECKOUT
# Criterio evaluado: congela precios y NO descuenta stock.
# ============================================================
class PruebasCheckout(BaseOrdenes):
    """El checkout genera la orden con precios congelados."""

    def test_checkout_crea_la_orden_en_pendiente(self):
        """La orden nace en PENDIENTE con su código UUID y su total."""
        self.cargar_carro(self.cliente, self.producto, 2)
        self.entrar()

        respuesta = self.client.post("/api/ordenes/checkout/")

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED, respuesta.data)
        orden = respuesta.data["orden"]
        self.assertEqual(orden["estado"], EstadoOrden.PENDIENTE)
        self.assertIsNotNone(orden["codigo"])
        self.assertEqual(Decimal(orden["total"]), Decimal("279990") * 2)
        self.assertFalse(respuesta.data["stock_descontado"])

    def test_checkout_no_descuenta_stock(self):
        """Criterio central: el stock queda intacto tras el checkout."""
        self.cargar_carro(self.cliente, self.producto, 3)
        stock_inicial = self.producto.stock
        self.entrar()

        self.client.post("/api/ordenes/checkout/")

        self.producto.refresh_from_db()
        self.assertEqual(
            self.producto.stock, stock_inicial,
            "El checkout no debe modificar el stock.",
        )

    def test_checkout_congela_el_precio(self):
        """Un cambio de precio posterior no altera la orden ya creada."""
        self.cargar_carro(self.cliente, self.producto, 1)
        self.entrar()
        self.client.post("/api/ordenes/checkout/")

        orden = Orden.objects.filter(usuario=self.cliente).first()
        detalle = orden.detalles.get(producto=self.producto)
        self.assertEqual(detalle.precio_unitario, Decimal("279990"))

        # --- El catálogo sube de precio después de la venta ---
        self.producto.precio = Decimal("999999")
        self.producto.save()

        detalle.refresh_from_db()
        orden.refresh_from_db()
        self.assertEqual(
            detalle.precio_unitario, Decimal("279990"),
            "El precio congelado no puede cambiar al cambiar el catálogo.",
        )
        self.assertEqual(orden.total, Decimal("279990"))

    def test_checkout_vacia_el_carro(self):
        """El carro queda vacío porque su contenido pasó a la orden."""
        carro = self.cargar_carro(self.cliente, self.producto, 2)
        self.entrar()

        self.client.post("/api/ordenes/checkout/")

        carro.refresh_from_db()
        self.assertTrue(carro.esta_vacio)
        self.assertEqual(carro.items.count(), 1, "Las filas se conservan (baja lógica).")

    def test_checkout_registra_el_historial_inicial(self):
        """Se anota la transición de creación a PENDIENTE."""
        self.cargar_carro(self.cliente, self.producto, 1)
        self.entrar()
        self.client.post("/api/ordenes/checkout/")

        orden = Orden.objects.filter(usuario=self.cliente).first()
        registro = orden.historial.first()

        self.assertEqual(orden.historial.count(), 1)
        self.assertIsNone(registro.estado_anterior)
        self.assertEqual(registro.estado_nuevo, EstadoOrden.PENDIENTE)
        self.assertEqual(registro.cambiado_por, self.cliente)

    def test_checkout_con_carro_vacio_responde_400(self):
        """Sin ítems en el carro no se puede generar una orden."""
        self.entrar()

        respuesta = self.client.post("/api/ordenes/checkout/")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vacío", respuesta.data["mensaje"].lower())
        self.assertFalse(Orden.objects.filter(usuario=self.cliente).exists())

    def test_checkout_requiere_rol_cliente(self):
        """Un administrador no puede hacer checkout: responde 403."""
        self.entrar_como_administrador()

        respuesta = self.client.post("/api/ordenes/checkout/")

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_checkout_sin_token_responde_401(self):
        """Sin autenticación, el checkout responde 401."""
        respuesta = self.client.post("/api/ordenes/checkout/")

        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cada_orden_tiene_un_codigo_unico(self):
        """El campo «codigo» del modelo es un UUID distinto en cada orden."""
        self.entrar()
        codigos = set()

        for _ in range(3):
            self.cargar_carro(self.cliente, self.producto, 1)
            respuesta = self.client.post("/api/ordenes/checkout/")
            codigos.add(respuesta.data["orden"]["codigo"])

        self.assertEqual(len(codigos), 3)


# ============================================================
# BLOQUE 3 — PAGO
# Criterio evaluado: el pago SÍ descuenta stock; con stock
# insuficiente responde 409 y no modifica nada.
# ============================================================
class PruebasPago(BaseOrdenes):
    """El pago verifica y descuenta el stock de forma atómica."""

    def _crear_orden(self, usuario=None, producto=None, cantidad=1):
        """Crea una orden PENDIENTE mediante el servicio de checkout."""
        usuario = usuario or self.cliente
        producto = producto or self.producto
        self.cargar_carro(usuario, producto, cantidad)
        return realizar_checkout(usuario)

    def test_el_pago_descuenta_el_stock(self):
        """Tras pagar, el stock baja exactamente en la cantidad vendida."""
        orden = self._crear_orden(cantidad=3)
        stock_inicial = self.producto.stock
        self.entrar()

        respuesta = self.client.post(f"/api/ordenes/{orden.id}/pagar/")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK, respuesta.data)
        self.assertTrue(respuesta.data["stock_descontado"])
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, stock_inicial - 3)

    def test_el_pago_marca_la_orden_y_la_fecha(self):
        """La orden pasa a PAGADO y se guarda pagada_en."""
        orden = self._crear_orden()
        self.entrar()

        self.client.post(f"/api/ordenes/{orden.id}/pagar/")

        orden.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.PAGADO)
        self.assertIsNotNone(orden.pagada_en)

    def test_el_pago_registra_el_historial(self):
        """Queda anotada la transición PENDIENTE → PAGADO."""
        orden = self._crear_orden()
        self.entrar()

        self.client.post(f"/api/ordenes/{orden.id}/pagar/")

        registro = orden.historial.order_by("fecha", "id").last()
        self.assertEqual(registro.estado_anterior, EstadoOrden.PENDIENTE)
        self.assertEqual(registro.estado_nuevo, EstadoOrden.PAGADO)

    def test_pago_con_stock_insuficiente_responde_409(self):
        """Si el stock bajó, el pago se rechaza con 409 y detalle del faltante."""
        orden = self._crear_orden(producto=self.producto, cantidad=5)

        # Otro proceso agotó el stock entre el checkout y el pago.
        self.producto.stock = 2
        self.producto.save()

        self.entrar()
        respuesta = self.client.post(f"/api/ordenes/{orden.id}/pagar/")

        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)
        faltante = respuesta.data["detalle"]["faltantes"][0]
        self.assertEqual(faltante["solicitado"], 5)
        self.assertEqual(faltante["disponible"], 2)

    def test_pago_rechazado_no_modifica_nada(self):
        """Tras un 409, la orden sigue PENDIENTE y el stock no cambió."""
        orden = self._crear_orden(cantidad=5)
        self.producto.stock = 2
        self.producto.save()

        self.entrar()
        self.client.post(f"/api/ordenes/{orden.id}/pagar/")

        orden.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.PENDIENTE)
        self.assertIsNone(orden.pagada_en)
        self.assertEqual(self.producto.stock, 2, "El rollback deja el stock intacto.")

    def test_pago_de_producto_dado_de_baja_responde_409(self):
        """Un producto retirado del catálogo impide el pago."""
        orden = self._crear_orden()
        self.producto.desactivar()

        self.entrar()
        respuesta = self.client.post(f"/api/ordenes/{orden.id}/pagar/")

        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)
        orden.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.PENDIENTE)
        self.producto.reactivar()

    def test_no_se_puede_pagar_dos_veces(self):
        """Una orden ya pagada no se vuelve a cobrar."""
        orden = self._crear_orden(cantidad=2)
        self.entrar()
        self.client.post(f"/api/ordenes/{orden.id}/pagar/")
        self.producto.refresh_from_db()
        stock_tras_el_pago = self.producto.stock

        respuesta = self.client.post(f"/api/ordenes/{orden.id}/pagar/")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, stock_tras_el_pago)

    def test_un_cliente_no_puede_pagar_la_orden_de_otro(self):
        """El permiso de objeto impide pagar una orden ajena."""
        orden = self._crear_orden(usuario=self.cliente)
        self.entrar("orden_dos")

        respuesta = self.client.post(f"/api/ordenes/{orden.id}/pagar/")

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        orden.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.PENDIENTE)

    def test_pagar_una_orden_inexistente_responde_json_controlado(self):
        """Un id que no existe devuelve JSON en español con la redirección."""
        self.entrar()

        respuesta = self.client.post("/api/ordenes/999999/pagar/")

        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(respuesta.data["redireccion"], "/")


# ============================================================
# BLOQUE 4 — MÁQUINA DE ESTADOS
# Criterio evaluado: cancelar una orden PAGADA repone el stock y
# las transiciones inválidas responden 400.
# ============================================================
class PruebasCambioDeEstado(BaseOrdenes):
    """El administrador mueve la orden según las transiciones legales."""

    def _orden_pendiente(self, cantidad=2):
        """Crea una orden PENDIENTE lista para cambiar de estado."""
        self.cargar_carro(self.cliente, self.producto, cantidad)
        return realizar_checkout(self.cliente)

    def _orden_pagada(self, cantidad=2):
        """Crea una orden ya pagada (con el stock ya descontado)."""
        orden = self._orden_pendiente(cantidad)
        return pagar_orden(orden, usuario=self.administrador)

    def test_administrador_pasa_pendiente_a_pagado(self):
        """PENDIENTE → PAGADO descuenta el stock."""
        orden = self._orden_pendiente(cantidad=2)
        stock_inicial = self.producto.stock
        self.entrar_como_administrador()

        respuesta = self.client.patch(
            f"/api/ordenes/{orden.id}/estado/",
            {"estado": "PAGADO", "observacion": "Pago por transferencia."},
            format="json",
        )

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK, respuesta.data)
        self.assertTrue(respuesta.data["stock_descontado"])
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, stock_inicial - 2)

    def test_pagado_a_entregado(self):
        """PAGADO → ENTREGADO cierra la venta sin mover el stock."""
        orden = self._orden_pagada(cantidad=2)
        self.producto.refresh_from_db()
        stock_tras_el_pago = self.producto.stock
        self.entrar_como_administrador()

        respuesta = self.client.patch(
            f"/api/ordenes/{orden.id}/estado/", {"estado": "ENTREGADO"}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        orden.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.ENTREGADO)
        self.assertEqual(self.producto.stock, stock_tras_el_pago)

    def test_cancelar_una_orden_pagada_repone_el_stock(self):
        """PAGADO → CANCELADO devuelve las unidades a bodega."""
        stock_original = self.producto.stock
        orden = self._orden_pagada(cantidad=3)

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, stock_original - 3)

        self.entrar_como_administrador()
        respuesta = self.client.patch(
            f"/api/ordenes/{orden.id}/estado/",
            {"estado": "CANCELADO", "observacion": "El cliente desistió."},
            format="json",
        )

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK, respuesta.data)
        self.assertIn("stock_repuesto", respuesta.data)
        self.producto.refresh_from_db()
        self.assertEqual(
            self.producto.stock, stock_original,
            "Cancelar una orden pagada debe reponer el stock.",
        )

    def test_cancelar_una_orden_pendiente_no_toca_el_stock(self):
        """PENDIENTE → CANCELADO no repone nada, porque nunca se descontó."""
        orden = self._orden_pendiente(cantidad=2)
        stock_inicial = self.producto.stock
        self.entrar_como_administrador()

        respuesta = self.client.patch(
            f"/api/ordenes/{orden.id}/estado/", {"estado": "CANCELADO"}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertNotIn("stock_repuesto", respuesta.data)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, stock_inicial)

    def test_transicion_invalida_responde_400(self):
        """PENDIENTE → ENTREGADO no está permitido."""
        orden = self._orden_pendiente()
        self.entrar_como_administrador()

        respuesta = self.client.patch(
            f"/api/ordenes/{orden.id}/estado/", {"estado": "ENTREGADO"}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("transiciones_permitidas", respuesta.data["detalle"])
        orden.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.PENDIENTE)

    def test_los_estados_finales_no_admiten_cambios(self):
        """ENTREGADO y CANCELADO no tienen salida."""
        orden = self._orden_pagada()
        cambiar_estado_orden(orden, EstadoOrden.ENTREGADO, usuario=self.administrador)
        self.entrar_como_administrador()

        for destino in ["PAGADO", "CANCELADO", "PENDIENTE"]:
            with self.subTest(destino=destino):
                respuesta = self.client.patch(
                    f"/api/ordenes/{orden.id}/estado/", {"estado": destino}, format="json"
                )
                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

        orden.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.ENTREGADO)

    def test_estado_inexistente_responde_400(self):
        """Un valor que no está en los CHOICES se rechaza."""
        orden = self._orden_pendiente()
        self.entrar_como_administrador()

        respuesta = self.client.patch(
            f"/api/ordenes/{orden.id}/estado/", {"estado": "INVENTADO"}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_un_cliente_no_puede_cambiar_estados(self):
        """PATCH del estado está reservado al administrador: 403."""
        orden = self._orden_pendiente()
        self.entrar()

        respuesta = self.client.patch(
            f"/api/ordenes/{orden.id}/estado/", {"estado": "PAGADO"}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_token_no_se_puede_cambiar_estados(self):
        """Sin autenticación, el cambio de estado responde 401."""
        orden = self._orden_pendiente()

        respuesta = self.client.patch(
            f"/api/ordenes/{orden.id}/estado/", {"estado": "PAGADO"}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cada_cambio_queda_en_el_historial(self):
        """El historial acumula la traza completa de la orden."""
        orden = self._orden_pagada()
        cambiar_estado_orden(
            orden, EstadoOrden.ENTREGADO, usuario=self.administrador,
            observacion="Retirado en tienda.",
        )

        transiciones = list(
            orden.historial.order_by("fecha", "id").values_list(
                "estado_anterior", "estado_nuevo"
            )
        )

        self.assertEqual(
            transiciones,
            [
                (None, EstadoOrden.PENDIENTE),
                (EstadoOrden.PENDIENTE, EstadoOrden.PAGADO),
                (EstadoOrden.PAGADO, EstadoOrden.ENTREGADO),
            ],
        )

    def test_diccionario_de_transiciones_declarado(self):
        """TRANSICIONES_PERMITIDAS describe exactamente la máquina de estados."""
        self.assertEqual(
            TRANSICIONES_PERMITIDAS[EstadoOrden.PENDIENTE],
            {EstadoOrden.PAGADO, EstadoOrden.CANCELADO},
        )
        self.assertEqual(
            TRANSICIONES_PERMITIDAS[EstadoOrden.PAGADO],
            {EstadoOrden.ENTREGADO, EstadoOrden.CANCELADO},
        )
        self.assertEqual(TRANSICIONES_PERMITIDAS[EstadoOrden.ENTREGADO], set())
        self.assertEqual(TRANSICIONES_PERMITIDAS[EstadoOrden.CANCELADO], set())


# ============================================================
# BLOQUE 5 — AISLAMIENTO DE LAS ÓRDENES POR CLIENTE
# Criterio evaluado: un cliente jamás ve órdenes ajenas.
# ============================================================
class PruebasMisOrdenes(BaseOrdenes):
    """/api/mis-ordenes/ solo devuelve las órdenes propias."""

    def setUp(self):
        """Crea una orden para cada cliente."""
        self.cargar_carro(self.cliente, self.producto, 1)
        self.orden_propia = realizar_checkout(self.cliente)

        self.cargar_carro(self.otro_cliente, self.producto, 2)
        self.orden_ajena = realizar_checkout(self.otro_cliente)

    def test_el_listado_solo_trae_las_propias(self):
        """El cliente ve una sola orden: la suya."""
        self.entrar("orden_uno")

        respuesta = self.client.get("/api/mis-ordenes/")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        codigos = {fila["codigo"] for fila in respuesta.data["results"]}
        self.assertEqual(codigos, {str(self.orden_propia.codigo)})

    def test_no_puede_ver_el_detalle_de_una_orden_ajena(self):
        """Pedir la orden de otro cliente responde 404 (ni siquiera existe para él)."""
        self.entrar("orden_uno")

        respuesta = self.client.get(f"/api/mis-ordenes/{self.orden_ajena.id}/")

        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)

    def test_el_detalle_propio_incluye_productos_e_historial(self):
        """La ficha de la orden propia trae el detalle y el historial."""
        self.entrar("orden_uno")

        respuesta = self.client.get(f"/api/mis-ordenes/{self.orden_propia.id}/")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(respuesta.data["detalles"]), 1)
        self.assertEqual(len(respuesta.data["historial"]), 1)
        self.assertIn("total", respuesta.data)

    def test_el_administrador_ve_todas_las_ordenes(self):
        """GET /api/ordenes/ devuelve las ventas de todos los clientes."""
        self.entrar_como_administrador()

        respuesta = self.client.get("/api/ordenes/")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(respuesta.data["count"], 2)

    def test_un_cliente_no_puede_usar_el_listado_del_administrador(self):
        """GET /api/ordenes/ con rol CLIENTE responde 403."""
        self.entrar("orden_uno")

        respuesta = self.client.get("/api/ordenes/")

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_filtro_por_estado_en_el_listado_del_administrador(self):
        """El OrdenFilter filtra por estado."""
        pagar_orden(self.orden_propia, usuario=self.administrador)
        self.entrar_como_administrador()

        pagadas = self.client.get("/api/ordenes/", {"estado": "PAGADO"})
        pendientes = self.client.get("/api/ordenes/", {"estado": "PENDIENTE"})

        self.assertEqual(pagadas.data["count"], 1)
        self.assertEqual(pendientes.data["count"], 1)

    def test_filtro_por_usuario_en_el_listado_del_administrador(self):
        """El OrdenFilter filtra por cliente."""
        self.entrar_como_administrador()

        respuesta = self.client.get("/api/ordenes/", {"usuario": self.otro_cliente.id})

        self.assertEqual(respuesta.data["count"], 1)
        self.assertEqual(respuesta.data["results"][0]["usuario_username"], "orden_dos")


# ============================================================
# BLOQUE 6 — NORMALIZACIÓN Y CÁLCULOS DE LA ORDEN
# El total no se guarda: es propiedad y anotación de consulta.
# ============================================================
class PruebasCalculosOrden(BaseOrdenes):
    """El total se calcula; el precio congelado sí se almacena."""

    def test_la_orden_no_tiene_columna_total(self):
        """No existe un campo total en el modelo Orden (3FN)."""
        nombres = {campo.name for campo in Orden._meta.get_fields()}

        self.assertNotIn("total", nombres)

    def test_el_detalle_no_tiene_columna_subtotal(self):
        """El subtotal del detalle es calculado, no almacenado."""
        nombres = {campo.name for campo in DetalleOrden._meta.get_fields()}

        self.assertNotIn("subtotal", nombres)
        self.assertIn("precio_unitario", nombres)

    def test_total_como_propiedad_y_como_anotacion(self):
        """La propiedad y la anotación con Sum dan el mismo resultado."""
        self.cargar_carro(self.cliente, self.producto, 2)
        carro = obtener_carro(self.cliente)
        agregar_producto(carro, self.producto_escaso, 1)
        orden = realizar_checkout(self.cliente)

        esperado = Decimal("279990") * 2 + Decimal("899990")
        self.assertEqual(orden.total, esperado)

        anotada = Orden.objects.con_total().get(pk=orden.pk)
        self.assertEqual(anotada.total, esperado)
        self.assertEqual(Decimal(anotada.total_anotado), esperado)

    def test_cantidad_items_y_codigo_corto(self):
        """Las propiedades de apoyo devuelven valores coherentes."""
        self.cargar_carro(self.cliente, self.producto, 4)
        orden = realizar_checkout(self.cliente)

        self.assertEqual(orden.cantidad_items, 4)
        self.assertEqual(len(orden.codigo_corto), 8)
        self.assertEqual(orden.codigo_corto, str(orden.codigo)[:8].upper())

    def test_transiciones_posibles_segun_el_estado(self):
        """transiciones_posibles refleja el estado actual de la orden."""
        self.cargar_carro(self.cliente, self.producto, 1)
        orden = realizar_checkout(self.cliente)

        self.assertEqual(transiciones_posibles(orden), ["CANCELADO", "PAGADO"])

        pagar_orden(orden, usuario=self.administrador)
        orden.refresh_from_db()
        self.assertEqual(transiciones_posibles(orden), ["CANCELADO", "ENTREGADO"])


# ============================================================
# BLOQUE 7 — CAPA DE SERVICIOS
# Se prueban las excepciones propias directamente, sin HTTP.
# ============================================================
class PruebasServiciosOrdenes(TestCase):
    """Las funciones de ordenes/servicios.py lanzan sus excepciones."""

    @classmethod
    def setUpTestData(cls):
        """Crea un cliente y un producto para operar los servicios."""
        cls.cliente = Usuario.objects.create_user(
            username="servicio_orden", email="servicio_orden@hardpointpc.cl",
            password="Compra.Segura.2026", rol=Rol.CLIENTE,
        )
        cls.categoria = Categoria.objects.create(nombre="Fuentes de Poder", icono="bi-plug")
        cls.marca = Marca.objects.create(nombre="Corsair")
        cls.producto = Producto.objects.create(
            sku="PSU-SERVICIO-01", nombre="Fuente de prueba",
            categoria=cls.categoria, marca=cls.marca,
            precio=Decimal("109990"), stock=4,
        )

    def test_carro_vacio_lanza_su_excepcion(self):
        """realizar_checkout exige un carro con ítems."""
        with self.assertRaises(CarroVacioError):
            realizar_checkout(self.cliente)

    def test_stock_insuficiente_lanza_su_excepcion_con_faltantes(self):
        """StockInsuficienteError trae la lista de productos faltantes."""
        carro = obtener_carro(self.cliente)
        agregar_producto(carro, self.producto, 4)
        orden = realizar_checkout(self.cliente)

        self.producto.stock = 1
        self.producto.save()

        with self.assertRaises(StockInsuficienteError) as contexto:
            pagar_orden(orden, usuario=self.cliente)

        faltantes = contexto.exception.faltantes
        self.assertEqual(len(faltantes), 1)
        self.assertEqual(faltantes[0]["solicitado"], 4)
        self.assertEqual(faltantes[0]["disponible"], 1)

    def test_transicion_invalida_lanza_su_excepcion(self):
        """TransicionInvalidaError informa las transiciones legales."""
        carro = obtener_carro(self.cliente)
        agregar_producto(carro, self.producto, 1)
        orden = realizar_checkout(self.cliente)

        with self.assertRaises(TransicionInvalidaError) as contexto:
            cambiar_estado_orden(orden, EstadoOrden.ENTREGADO, usuario=self.cliente)

        self.assertEqual(contexto.exception.estado_actual, EstadoOrden.PENDIENTE)
        self.assertEqual(contexto.exception.estado_pedido, EstadoOrden.ENTREGADO)
        self.assertIn(EstadoOrden.PAGADO, contexto.exception.permitidos)

    def test_el_rollback_no_deja_rastros(self):
        """Un pago fallido no crea registros de historial ni cambia el stock."""
        carro = obtener_carro(self.cliente)
        agregar_producto(carro, self.producto, 4)
        orden = realizar_checkout(self.cliente)

        historial_antes = orden.historial.count()
        self.producto.stock = 0
        self.producto.save()

        with self.assertRaises(StockInsuficienteError):
            pagar_orden(orden, usuario=self.cliente)

        orden.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(orden.historial.count(), historial_antes)
        self.assertEqual(orden.estado, EstadoOrden.PENDIENTE)
        self.assertEqual(self.producto.stock, 0)


# ============================================================
# BLOQUE 8 — CONCURRENCIA REAL
# Criterio evaluado: dos pagos simultáneos por el último producto →
# solo uno queda PAGADO y el stock nunca queda negativo.
#
# Se usa TransactionTestCase (no TestCase) porque hacen falta
# transacciones de verdad: TestCase envuelve cada prueba en una
# transacción que los otros hilos no verían.
# ============================================================
class PruebasConcurrencia(TransactionTestCase):
    """Dos pagos simultáneos no pueden vender la misma última unidad."""

    reset_sequences = True

    def setUp(self):
        """Prepara un producto con stock 1 y dos órdenes que lo reclaman."""
        self.categoria = Categoria.objects.create(nombre="Tarjetas de Video", icono="bi-gpu-card")
        self.marca = Marca.objects.create(nombre="NVIDIA")
        self.producto = Producto.objects.create(
            sku="GPU-CONCURRENCIA", nombre="Tarjeta de video con una sola unidad",
            categoria=self.categoria, marca=self.marca,
            precio=Decimal("2299990"), stock=1,
        )

        self.ordenes = []
        for indice in (1, 2):
            cliente = Usuario.objects.create_user(
                username=f"concurrente{indice}",
                email=f"concurrente{indice}@hardpointpc.cl",
                password="Compra.Segura.2026",
                rol=Rol.CLIENTE,
            )
            carro = obtener_carro(cliente)
            agregar_producto(carro, self.producto, 1)
            self.ordenes.append(realizar_checkout(cliente))

        # El checkout no descuenta stock: sigue habiendo una sola unidad
        # y dos órdenes que la reclaman.
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 1)

    def test_dos_pagos_simultaneos_solo_uno_queda_pagado(self):
        """El segundo pago es rechazado y el stock final es 0, nunca -1."""
        resultados = {}
        bloqueo = threading.Lock()
        barrera = threading.Barrier(len(self.ordenes))

        def pagar(indice, orden_id):
            """Cada hilo intenta pagar su orden en el mismo instante."""
            try:
                barrera.wait(timeout=15)
                orden = Orden.objects.get(pk=orden_id)
                with transaction.atomic():
                    pagar_orden(orden, usuario=orden.usuario)
                with bloqueo:
                    resultados[indice] = "PAGADO"
            except StockInsuficienteError:
                with bloqueo:
                    resultados[indice] = "RECHAZADO"
            except Exception as error:  # noqa: BLE001
                with bloqueo:
                    resultados[indice] = f"ERROR: {type(error).__name__}: {error}"
            finally:
                # Cada hilo cierra su propia conexión a PostgreSQL.
                connection.close()

        hilos = [
            threading.Thread(target=pagar, args=(indice, orden.pk))
            for indice, orden in enumerate(self.ordenes)
        ]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=30)

        # --- Un pago aprobado y uno rechazado ---
        self.assertEqual(
            sorted(resultados.values()),
            ["PAGADO", "RECHAZADO"],
            f"Resultado inesperado de los hilos: {resultados}",
        )

        # --- Estados finales de las órdenes ---
        estados = sorted(
            Orden.objects.filter(pk__in=[o.pk for o in self.ordenes]).values_list(
                "estado", flat=True
            )
        )
        self.assertEqual(estados, [EstadoOrden.PAGADO, EstadoOrden.PENDIENTE])

        # --- El stock nunca queda negativo ---
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 0, "El stock final debe ser 0, nunca -1.")
        self.assertGreaterEqual(self.producto.stock, 0)

    def test_solo_se_registra_un_pago_en_el_historial(self):
        """Tras la carrera, solo existe una transición a PAGADO."""
        barrera = threading.Barrier(len(self.ordenes))

        def pagar(orden_id):
            """Intenta pagar, ignorando el rechazo esperado."""
            try:
                barrera.wait(timeout=15)
                orden = Orden.objects.get(pk=orden_id)
                with transaction.atomic():
                    pagar_orden(orden, usuario=orden.usuario)
            except StockInsuficienteError:
                pass
            finally:
                connection.close()

        hilos = [threading.Thread(target=pagar, args=(orden.pk,)) for orden in self.ordenes]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=30)

        pagos = HistorialEstadoOrden.objects.filter(estado_nuevo=EstadoOrden.PAGADO).count()
        self.assertEqual(pagos, 1)


# ============================================================
# BLOQUE 9 — PANTALLAS HTML DE ÓRDENES
# Las vistas HTML usan las mismas funciones de servicio, así que el
# control de stock es idéntico al de la API.
# ============================================================
class PruebasHtmlOrdenes(TestCase):
    """El panel de órdenes paga, entrega y cancela con las mismas reglas.

    Se puede VER sin iniciar sesión, pero EDITAR (pagar, cambiar de
    estado) exige una sesión de Administrador de TI; por eso setUp()
    inicia sesión con cls.administrador antes de cada prueba.
    """

    @classmethod
    def setUpTestData(cls):
        """Crea un cliente, un administrador y dos productos."""
        cls.cliente = Usuario.objects.create_user(
            username="html_orden", email="html_orden@hardpointpc.cl",
            password="Compra.Segura.2026", rol=Rol.CLIENTE,
        )
        cls.administrador = Usuario.objects.create_user(
            username="html_orden_admin", email="html_orden_admin@hardpointpc.cl",
            password="Llave.Segura.2026", rol=Rol.ADMINISTRADOR,
        )
        cls.categoria = Categoria.objects.create(nombre="Placas Madre", icono="bi-motherboard")
        cls.marca = Marca.objects.create(nombre="ASUS")
        cls.producto = Producto.objects.create(
            sku="MB-HTML-01", nombre="Placa madre de prueba",
            categoria=cls.categoria, marca=cls.marca,
            precio=Decimal("269990"), stock=8,
        )

    def setUp(self):
        """Inicia sesión como administrador: las pruebas de este archivo escriben."""
        self.client.force_login(self.administrador)

    def _crear_orden(self, cantidad=2):
        """Crea una orden PENDIENTE con el servicio de checkout."""
        carro = obtener_carro(self.cliente)
        agregar_producto(carro, self.producto, cantidad)
        return realizar_checkout(self.cliente)

    def test_listado_de_ordenes_responde_200(self):
        """La pantalla /panel/ordenes/ se sirve correctamente."""
        self._crear_orden()

        respuesta = self.client.get("/panel/ordenes/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "html_orden")

    def test_ficha_muestra_el_precio_congelado_y_el_total(self):
        """La ficha de la orden muestra el precio congelado."""
        orden = self._crear_orden(cantidad=2)

        respuesta = self.client.get(f"/panel/ordenes/{orden.id}/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Precios congelados")
        self.assertContains(respuesta, "$269.990")
        self.assertContains(respuesta, "$539.980")

    def test_checkout_desde_el_html(self):
        """La pantalla de carros genera la orden llamando al servicio."""
        carro = obtener_carro(self.cliente)
        agregar_producto(carro, self.producto, 1)
        stock_inicial = self.producto.stock

        respuesta = self.client.post(
            "/panel/carros/checkout/", {"usuario": self.cliente.id}, follow=True
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(Orden.objects.filter(usuario=self.cliente).exists())
        self.producto.refresh_from_db()
        self.assertEqual(
            self.producto.stock, stock_inicial,
            "El checkout por HTML tampoco descuenta stock.",
        )

    def test_pagar_desde_el_html_descuenta_stock(self):
        """El botón de pago descuenta el stock de forma atómica."""
        orden = self._crear_orden(cantidad=3)
        stock_inicial = self.producto.stock

        respuesta = self.client.post(f"/panel/ordenes/{orden.id}/pagar/", follow=True)

        self.assertEqual(respuesta.status_code, 200)
        orden.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.PAGADO)
        self.assertEqual(self.producto.stock, stock_inicial - 3)

    def test_pago_html_con_stock_insuficiente_muestra_el_producto_faltante(self):
        """El mensaje de error explica qué producto faltó y en qué cantidad."""
        orden = self._crear_orden(cantidad=5)
        self.producto.stock = 1
        self.producto.save()

        respuesta = self.client.post(f"/panel/ordenes/{orden.id}/pagar/", follow=True)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Placa madre de prueba")
        self.assertContains(respuesta, "pidió 5 y hay 1")
        orden.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.PENDIENTE)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 1)

    def test_cancelar_una_orden_pagada_desde_el_html_repone_stock(self):
        """La cancelación por HTML también repone el stock."""
        stock_original = self.producto.stock
        orden = self._crear_orden(cantidad=2)
        self.client.post(f"/panel/ordenes/{orden.id}/pagar/", follow=True)

        respuesta = self.client.post(
            f"/panel/ordenes/{orden.id}/estado/",
            {"estado": "CANCELADO", "observacion": "Prueba de reposición."},
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "stock se repuso")
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, stock_original)

    def test_marcar_entregada_desde_el_html(self):
        """El botón de entrega cierra la venta."""
        orden = self._crear_orden(cantidad=1)
        self.client.post(f"/panel/ordenes/{orden.id}/pagar/", follow=True)

        self.client.post(
            f"/panel/ordenes/{orden.id}/estado/", {"estado": "ENTREGADO"}, follow=True
        )

        orden.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.ENTREGADO)

    def test_transicion_invalida_desde_el_html_muestra_el_error(self):
        """Una transición ilegal muestra el mensaje y no cambia la orden."""
        orden = self._crear_orden()

        respuesta = self.client.post(
            f"/panel/ordenes/{orden.id}/estado/", {"estado": "ENTREGADO"}, follow=True
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No se puede pasar de PENDIENTE a ENTREGADO")
        orden.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.PENDIENTE)

    def test_orden_inexistente_no_muestra_404(self):
        """Una orden que no existe lleva a la pantalla de redirección."""
        respuesta = self.client.get("/panel/ordenes/999999/", follow=True)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No existe una orden")

    def test_el_historial_aparece_en_la_ficha(self):
        """La línea de tiempo muestra las transiciones registradas."""
        orden = self._crear_orden(cantidad=1)
        self.client.post(f"/panel/ordenes/{orden.id}/pagar/", follow=True)

        respuesta = self.client.get(f"/panel/ordenes/{orden.id}/")

        self.assertContains(respuesta, "Historial de estados")
        self.assertContains(respuesta, "Pago aprobado")


# ============================================================
# BLOQUE 14 — SIN LOGIN SE VE, PERO NO SE PAGA NI SE CAMBIA DE ESTADO
# Corrige el agujero de seguridad detectado en el panel: cualquiera
# podía pagar o cancelar la orden de cualquier cliente. Ahora GET
# sigue abierto a todos; POST exige una sesión de Administrador de TI.
# ============================================================
class PruebasSeguridadHtmlOrdenes(TestCase):
    """Sin iniciar sesión se puede ver una orden, pero no pagarla ni cambiarla."""

    @classmethod
    def setUpTestData(cls):
        """Cliente, producto y una orden PENDIENTE para probar sin sesión de administrador."""
        cls.cliente = Usuario.objects.create_user(
            username="seg_orden_cliente", email="seg_orden_cliente@hardpointpc.cl",
            password="Compra.Segura.2026", rol=Rol.CLIENTE,
        )
        cls.categoria = Categoria.objects.create(nombre="Memorias RAM", icono="bi-memory")
        cls.marca = Marca.objects.create(nombre="Kingston")
        cls.producto = Producto.objects.create(
            sku="RAM-SEG-01", nombre="Memoria de prueba de seguridad",
            categoria=cls.categoria, marca=cls.marca, precio=Decimal("49990"), stock=10,
        )
        carro = obtener_carro(cls.cliente)
        agregar_producto(carro, cls.producto, 2)
        cls.orden = realizar_checkout(cls.cliente)

    def test_anonimo_puede_ver_la_orden_de_cualquier_cliente(self):
        """Ver la ficha de la orden sigue sin exigir sesión."""
        respuesta = self.client.get(f"/panel/ordenes/{self.orden.id}/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "seg_orden_cliente")

    def test_anonimo_no_puede_pagar_la_orden_de_otro(self):
        """Sin sesión de administrador, el pago no se ejecuta."""
        respuesta = self.client.post(f"/panel/ordenes/{self.orden.id}/pagar/")

        self.assertEqual(respuesta.status_code, 302)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, EstadoOrden.PENDIENTE)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 10, "El pago bloqueado no debe tocar el stock.")

    def test_cliente_autenticado_sin_rol_administrador_tampoco_puede_cambiar_estado(self):
        """Estar logueado no basta: el rol debe ser ADMINISTRADOR."""
        self.client.force_login(self.cliente)

        respuesta = self.client.post(
            f"/panel/ordenes/{self.orden.id}/estado/", {"estado": "CANCELADO"}
        )

        self.assertEqual(respuesta.status_code, 302)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, EstadoOrden.PENDIENTE)
