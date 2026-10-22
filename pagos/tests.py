# ============================================================
# pagos/tests.py — PRUEBAS DEL PAGO CON WEBPAY PLUS
# Responsabilidad: comprobar pagos/servicios.py completo SIN llamar
# nunca a Transbank de verdad. Se reemplaza con unittest.mock la
# clase Transaction que usa el SDK (transbank.webpay.webpay_plus.
# transaction.Transaction), así las pruebas son rápidas,
# deterministas y no dependen de la red ni del ambiente de
# integración real de Transbank.
#
# Lo que se comprueba, uno por uno:
#   1. Pago aprobado → descuenta stock y la orden queda PAGADA.
#   2. Pago rechazado → no descuenta nada, la orden sigue PENDIENTE.
#   3. Anulación por el usuario (TBK_TOKEN) → no se hace commit.
#   4. Timeout (solo TBK_ORDEN_COMPRA + TBK_ID_SESION) → no se hace commit.
#   5. Un mismo token confirmado dos veces → solo descuenta una vez
#      (idempotencia de confirmar_pago_webpay).
#   6. El monto que devuelve Transbank no coincide con el iniciado.
#   7. CASO CRÍTICO: Transbank aprueba pero ya no hay stock → refund
#      automático, PagoWebpay queda REEMBOLSADO y la orden sigue
#      PENDIENTE.
#   8. Un cliente no puede iniciar el pago de la orden de otro (403).
# ============================================================

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from carro.servicios import agregar_producto, obtener_carro
from catalogo.models import Categoria, Marca, Producto
from ordenes.models import EstadoOrden
from ordenes.servicios import realizar_checkout
from usuarios.models import Rol, Usuario

from .models import EstadoPagoWebpay, PagoWebpay
from .servicios import (
    MontoNoCoincideError,
    anular_pago_por_usuario,
    confirmar_pago_webpay,
    expirar_pago_por_timeout,
    iniciar_pago_webpay,
)

RETURN_URL_DE_PRUEBA = "https://hardpoint-genesis.duckdns.org/webpay/retorno/"


# ============================================================
# BLOQUE 1 — RESPUESTAS DE TRANSBANK SIMULADAS
# Con la misma forma exacta que devuelve el SDK real (un dict, tal
# como lo documenta la API de Webpay Plus), para que el código bajo
# prueba no pueda distinguir el mock de una respuesta real.
# ============================================================
def _respuesta_create(token="token-de-prueba-0001", url="https://webpay3gint.transbank.cl/webpayserver/initTransaction"):
    """Respuesta simulada de Transaction.create()."""
    return {"token": token, "url": url}


def _respuesta_commit(monto, aprobado=True, authorization_code="1213", card_number="6623"):
    """Respuesta simulada de Transaction.commit()."""
    return {
        "vci": "TSY",
        "amount": monto,
        "status": "AUTHORIZED" if aprobado else "FAILED",
        "response_code": 0 if aprobado else -1,
        "buy_order": "no-importa-en-la-prueba",
        "session_id": "no-importa-en-la-prueba",
        "card_detail": {"card_number": card_number},
        "accounting_date": "1022",
        "transaction_date": "2026-10-22T12:00:00.000Z",
        "authorization_code": authorization_code,
        "payment_type_code": "VN",
        "installments_number": 0,
    }


# ============================================================
# BLOQUE 2 — ESCENARIO BASE
# ============================================================
class BaseWebpay(TestCase):
    """Un cliente, un segundo cliente y un producto con stock conocido."""

    @classmethod
    def setUpTestData(cls):
        """Crea los usuarios y el producto que usan todas las pruebas."""
        cls.cliente = Usuario.objects.create_user(
            username="webpay_cliente", email="webpay_cliente@hardpointpc.cl",
            password="Compra.Segura.2026", rol=Rol.CLIENTE,
        )
        cls.otro_cliente = Usuario.objects.create_user(
            username="webpay_otro", email="webpay_otro@hardpointpc.cl",
            password="Compra.Segura.2026", rol=Rol.CLIENTE,
        )
        cls.categoria = Categoria.objects.create(nombre="Memorias RAM", icono="bi-memory")
        cls.marca = Marca.objects.create(nombre="Kingston")
        cls.producto = Producto.objects.create(
            sku="RAM-WEBPAY-01", nombre="Memoria de prueba Webpay",
            categoria=cls.categoria, marca=cls.marca, precio=Decimal("49990"), stock=5,
        )

    def _crear_orden(self, cliente=None, cantidad=2):
        """Crea una orden PENDIENTE con el producto de prueba."""
        cliente = cliente or self.cliente
        carro = obtener_carro(cliente)
        agregar_producto(carro, self.producto, cantidad)
        return realizar_checkout(cliente)


# ============================================================
# BLOQUE 3 — INICIAR Y CONFIRMAR EL PAGO
# ============================================================
class PruebasConfirmarPagoWebpay(BaseWebpay):
    """iniciar_pago_webpay() y confirmar_pago_webpay(), con Transbank simulado."""

    @patch("pagos.servicios.Transaction")
    def test_pago_aprobado_descuenta_stock(self, ClaseTransaction):
        """Aprobado por Transbank: la orden queda PAGADA y el stock baja."""
        orden = self._crear_orden(cantidad=2)
        instancia = ClaseTransaction.build_for_integration.return_value
        instancia.create.return_value = _respuesta_create()

        pago = iniciar_pago_webpay(orden, RETURN_URL_DE_PRUEBA)
        instancia.commit.return_value = _respuesta_commit(pago.monto, aprobado=True)

        pago = confirmar_pago_webpay(pago.token)

        self.assertEqual(pago.estado, EstadoPagoWebpay.APROBADO)
        self.assertEqual(pago.authorization_code, "1213")
        self.assertEqual(pago.card_number, "6623")
        orden.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.PAGADO)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 3)

    @patch("pagos.servicios.Transaction")
    def test_pago_rechazado_no_descuenta_stock(self, ClaseTransaction):
        """Rechazado por Transbank: nada se descuenta y la orden sigue PENDIENTE."""
        orden = self._crear_orden(cantidad=2)
        instancia = ClaseTransaction.build_for_integration.return_value
        instancia.create.return_value = _respuesta_create()

        pago = iniciar_pago_webpay(orden, RETURN_URL_DE_PRUEBA)
        instancia.commit.return_value = _respuesta_commit(pago.monto, aprobado=False)

        pago = confirmar_pago_webpay(pago.token)

        self.assertEqual(pago.estado, EstadoPagoWebpay.RECHAZADO)
        orden.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.PENDIENTE)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 5)

    @patch("pagos.servicios.Transaction")
    def test_anulacion_por_el_usuario_no_hace_commit(self, ClaseTransaction):
        """TBK_TOKEN (el cliente anuló en el formulario): nunca se llama a commit()."""
        orden = self._crear_orden()
        instancia = ClaseTransaction.build_for_integration.return_value
        instancia.create.return_value = _respuesta_create(token="token-anulado")

        pago = iniciar_pago_webpay(orden, RETURN_URL_DE_PRUEBA)
        resultado = anular_pago_por_usuario(pago.token)

        self.assertEqual(resultado.estado, EstadoPagoWebpay.ANULADO_POR_USUARIO)
        instancia.commit.assert_not_called()
        orden.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.PENDIENTE)

    @patch("pagos.servicios.Transaction")
    def test_timeout_no_hace_commit(self, ClaseTransaction):
        """Solo TBK_ORDEN_COMPRA + TBK_ID_SESION (venció el formulario): no se hace commit."""
        orden = self._crear_orden()
        instancia = ClaseTransaction.build_for_integration.return_value
        instancia.create.return_value = _respuesta_create()

        pago = iniciar_pago_webpay(orden, RETURN_URL_DE_PRUEBA)
        resultado = expirar_pago_por_timeout(pago.buy_order)

        self.assertEqual(resultado.estado, EstadoPagoWebpay.EXPIRADO)
        instancia.commit.assert_not_called()

    @patch("pagos.servicios.Transaction")
    def test_token_confirmado_dos_veces_no_descuenta_dos_veces(self, ClaseTransaction):
        """confirmar_pago_webpay() es idempotente: el segundo commit no se llama."""
        orden = self._crear_orden(cantidad=1)
        instancia = ClaseTransaction.build_for_integration.return_value
        instancia.create.return_value = _respuesta_create()

        pago = iniciar_pago_webpay(orden, RETURN_URL_DE_PRUEBA)
        instancia.commit.return_value = _respuesta_commit(pago.monto, aprobado=True)

        primero = confirmar_pago_webpay(pago.token)
        segundo = confirmar_pago_webpay(pago.token)

        self.assertEqual(primero.estado, EstadoPagoWebpay.APROBADO)
        self.assertEqual(segundo.pk, primero.pk)
        self.assertEqual(segundo.estado, EstadoPagoWebpay.APROBADO)
        self.assertEqual(instancia.commit.call_count, 1, "El segundo intento no debe volver a confirmar con Transbank.")
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 4, "El stock se descuenta una sola vez.")

    @patch("pagos.servicios.Transaction")
    def test_monto_que_no_coincide_marca_error_y_no_paga(self, ClaseTransaction):
        """Si Transbank devuelve un monto distinto del iniciado, se rechaza por anomalía."""
        orden = self._crear_orden(cantidad=2)
        instancia = ClaseTransaction.build_for_integration.return_value
        instancia.create.return_value = _respuesta_create()

        pago = iniciar_pago_webpay(orden, RETURN_URL_DE_PRUEBA)
        instancia.commit.return_value = _respuesta_commit(pago.monto + 1, aprobado=True)

        with self.assertRaises(MontoNoCoincideError):
            confirmar_pago_webpay(pago.token)

        pago.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPagoWebpay.ERROR)
        orden.refresh_from_db()
        self.assertEqual(orden.estado, EstadoOrden.PENDIENTE)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 5)

    @patch("pagos.servicios.Transaction")
    def test_aprobado_sin_stock_hace_refund_y_la_orden_sigue_pendiente(self, ClaseTransaction):
        """CASO CRÍTICO: Transbank aprueba, pero ya no hay stock → refund automático."""
        orden = self._crear_orden(cantidad=2)
        instancia = ClaseTransaction.build_for_integration.return_value
        instancia.create.return_value = _respuesta_create()

        pago = iniciar_pago_webpay(orden, RETURN_URL_DE_PRUEBA)

        # Otro cliente se queda con el stock justo antes de que vuelva el pago.
        self.producto.stock = 0
        self.producto.save(update_fields=["stock"])

        instancia.commit.return_value = _respuesta_commit(pago.monto, aprobado=True)
        instancia.refund.return_value = {"type": "REVERSED", "response_code": 0}

        pago = confirmar_pago_webpay(pago.token)

        self.assertEqual(pago.estado, EstadoPagoWebpay.REEMBOLSADO)
        instancia.refund.assert_called_once_with(pago.token, float(pago.monto))
        orden.refresh_from_db()
        self.assertEqual(
            orden.estado, EstadoOrden.PENDIENTE,
            "Nunca debe quedar un cliente cobrado sin que se le haya descontado el producto.",
        )


# ============================================================
# BLOQUE 4 — API: NADIE INICIA EL PAGO DE LA ORDEN DE OTRO
# ============================================================
class PruebasApiWebpayIniciar(APITestCase):
    """POST /api/ordenes/{id}/webpay/iniciar/ respeta el dueño de la orden."""

    CLAVE = "Compra.Segura.2026"

    @classmethod
    def setUpTestData(cls):
        """Dos clientes y un producto; cada uno con su propia orden PENDIENTE."""
        cls.cliente = Usuario.objects.create_user(
            username="api_webpay_cliente", email="api_webpay_cliente@hardpointpc.cl",
            password=cls.CLAVE, rol=Rol.CLIENTE,
        )
        cls.otro_cliente = Usuario.objects.create_user(
            username="api_webpay_otro", email="api_webpay_otro@hardpointpc.cl",
            password=cls.CLAVE, rol=Rol.CLIENTE,
        )
        cls.categoria = Categoria.objects.create(nombre="Fuentes de Poder", icono="bi-plug")
        cls.marca = Marca.objects.create(nombre="Corsair")
        cls.producto = Producto.objects.create(
            sku="PSU-WEBPAY-API-01", nombre="Fuente de prueba Webpay",
            categoria=cls.categoria, marca=cls.marca, precio=Decimal("99990"), stock=10,
        )

    def entrar(self, username):
        """Autentica con un token Bearer, igual que el resto de las pruebas de la API."""
        respuesta = self.client.post(
            "/api/auth/login/", {"username": username, "password": self.CLAVE}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK, respuesta.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['access']}")

    def _crear_orden(self, cliente):
        carro = obtener_carro(cliente)
        agregar_producto(carro, self.producto, 1)
        return realizar_checkout(cliente)

    @patch("pagos.servicios.Transaction")
    def test_cliente_no_puede_iniciar_el_pago_de_la_orden_de_otro(self, ClaseTransaction):
        """La orden es de self.cliente; self.otro_cliente no puede pagarla."""
        orden = self._crear_orden(self.cliente)

        self.entrar("api_webpay_otro")
        respuesta = self.client.post(f"/api/ordenes/{orden.id}/webpay/iniciar/")

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        ClaseTransaction.build_for_integration.return_value.create.assert_not_called()
        self.assertFalse(PagoWebpay.objects.filter(orden=orden).exists())

    @patch("pagos.servicios.Transaction")
    def test_el_dueno_de_la_orden_si_puede_iniciar_el_pago(self, ClaseTransaction):
        """El propio cliente sí puede iniciar el pago de su orden."""
        orden = self._crear_orden(self.cliente)
        instancia = ClaseTransaction.build_for_integration.return_value
        instancia.create.return_value = _respuesta_create(
            token="token-api", url="https://webpay3gint.transbank.cl/webpayserver/initTransaction"
        )

        self.entrar("api_webpay_cliente")
        respuesta = self.client.post(f"/api/ordenes/{orden.id}/webpay/iniciar/")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK, respuesta.data)
        self.assertEqual(respuesta.data["token"], "token-api")
        self.assertTrue(PagoWebpay.objects.filter(orden=orden, token="token-api").exists())
