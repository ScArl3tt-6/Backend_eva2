# ============================================================
# carro/tests.py — PRUEBAS DEL CARRO DE COMPRAS
# Responsabilidad: comprobar las tres afirmaciones centrales del
# criterio "carro persistente" de la rúbrica:
#
#   1. El carro vive en PostgreSQL y sobrevive al logout y a un
#      nuevo inicio de sesión (no depende de la sesión ni de cookies).
#   2. Agregar el mismo producto dos veces SUMA la cantidad y no
#      duplica filas.
#   3. Agregar al carro NO descuenta stock.
#
# Además se prueba la baja lógica de los ítems y el aislamiento
# entre los carros de distintos clientes.
# ============================================================

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from carro.models import Carro, ItemCarro
from carro.servicios import (
    CantidadInvalidaError,
    ItemNoEnCarroError,
    ProductoNoDisponibleError,
    StockInsuficienteEnCarroError,
    actualizar_cantidad,
    agregar_producto,
    obtener_carro,
    quitar_producto,
    vaciar_carro,
)
from catalogo.models import Categoria, Marca, Producto
from usuarios.models import Rol, Usuario


# ============================================================
# BLOQUE 1 — ESCENARIO BASE
# Un cliente, un segundo cliente (para probar el aislamiento) y
# tres productos con stock distinto.
# ============================================================
class BaseCarro(APITestCase):
    """Escenario base con clientes y productos para operar el carro."""

    CLAVE = "Compra.Segura.2026"
    CLAVE_ADMIN = "Llave.Segura.2026"

    @classmethod
    def setUpTestData(cls):
        """Crea usuarios y productos con distintos niveles de stock."""
        cls.cliente = Usuario.objects.create_user(
            username="carro_uno", email="carro_uno@hardpointpc.cl",
            password=cls.CLAVE, rol=Rol.CLIENTE,
        )
        cls.otro_cliente = Usuario.objects.create_user(
            username="carro_dos", email="carro_dos@hardpointpc.cl",
            password=cls.CLAVE, rol=Rol.CLIENTE,
        )
        cls.administrador = Usuario.objects.create_user(
            username="carro_admin", email="carro_admin@hardpointpc.cl",
            password=cls.CLAVE_ADMIN, rol=Rol.ADMINISTRADOR,
        )

        cls.categoria = Categoria.objects.create(nombre="Memorias RAM", icono="bi-memory")
        cls.marca = Marca.objects.create(nombre="Kingston")

        cls.producto = Producto.objects.create(
            sku="RAM-CARRO-01", nombre="Memoria de prueba",
            categoria=cls.categoria, marca=cls.marca, precio=Decimal("49990"), stock=20,
        )
        cls.producto_escaso = Producto.objects.create(
            sku="RAM-CARRO-ESCASA", nombre="Memoria con una sola unidad",
            categoria=cls.categoria, marca=cls.marca, precio=Decimal("159990"), stock=1,
        )
        cls.producto_agotado = Producto.objects.create(
            sku="RAM-CARRO-AGOTADA", nombre="Memoria sin existencias",
            categoria=cls.categoria, marca=cls.marca, precio=Decimal("99990"), stock=0,
        )

    def entrar(self, username=None, password=None):
        """Inicia sesión por la API y devuelve el par de tokens."""
        respuesta = self.client.post(
            "/api/auth/login/",
            {"username": username or "carro_uno", "password": password or self.CLAVE},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK, respuesta.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['access']}")
        return respuesta.data


# ============================================================
# BLOQUE 2 — PERSISTENCIA DEL CARRO
# Criterio evaluado: el carro persiste tras el logout (con el
# refresh en lista negra) y un nuevo login; los ítems siguen iguales.
# ============================================================
class PruebasPersistenciaDelCarro(BaseCarro):
    """El carro vive en la base de datos, no en la sesión."""

    def test_el_carro_sobrevive_al_logout_y_a_un_nuevo_login(self):
        """Tras cerrar sesión y volver a entrar, los ítems siguen intactos."""
        # --- Primera sesión: se cargan dos productos ---
        tokens = self.entrar()
        self.client.post("/api/carro/", {"producto": self.producto.id, "cantidad": 3}, format="json")
        self.client.post("/api/carro/", {"producto": self.producto_escaso.id, "cantidad": 1}, format="json")

        antes = self.client.get("/api/carro/")
        self.assertEqual(antes.status_code, status.HTTP_200_OK)
        self.assertEqual(len(antes.data["items"]), 2)
        self.assertEqual(antes.data["cantidad_items"], 4)
        total_antes = antes.data["total"]

        # --- Logout: el refresh token queda en la lista negra ---
        logout = self.client.post("/api/auth/logout/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(logout.status_code, status.HTTP_200_OK)

        # El refresh invalidado ya no sirve: la sesión anterior se terminó.
        self.client.credentials()
        reintento = self.client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(reintento.status_code, status.HTTP_401_UNAUTHORIZED)

        # --- Segunda sesión: token nuevo, carro idéntico ---
        self.entrar()
        despues = self.client.get("/api/carro/")

        self.assertEqual(despues.status_code, status.HTTP_200_OK)
        self.assertEqual(len(despues.data["items"]), 2)
        self.assertEqual(despues.data["cantidad_items"], 4)
        self.assertEqual(despues.data["total"], total_antes)

    def test_el_carro_existe_en_la_base_de_datos(self):
        """Los ítems se pueden consultar con el ORM, sin ninguna petición HTTP."""
        self.entrar()
        self.client.post("/api/carro/", {"producto": self.producto.id, "cantidad": 2}, format="json")

        carro = Carro.objects.get(usuario=self.cliente)
        self.assertEqual(carro.items.filter(activo=True).count(), 1)
        self.assertEqual(carro.items.get(producto=self.producto).cantidad, 2)

    def test_cada_cliente_ve_solo_su_carro(self):
        """Un cliente jamás ve los ítems de otro."""
        self.entrar("carro_uno", self.CLAVE)
        self.client.post("/api/carro/", {"producto": self.producto.id, "cantidad": 5}, format="json")

        self.client.credentials()
        self.entrar("carro_dos", self.CLAVE)
        respuesta = self.client.get("/api/carro/")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(respuesta.data["items"]), 0)
        self.assertTrue(respuesta.data["esta_vacio"])

    def test_la_relacion_con_el_usuario_es_uno_a_uno(self):
        """No se puede crear un segundo carro para el mismo usuario."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Carro.objects.create(usuario=self.cliente)


# ============================================================
# BLOQUE 3 — AGREGAR SIN DUPLICAR
# Criterio evaluado: agregar el mismo producto dos veces suma la
# cantidad y no crea una segunda fila.
# ============================================================
class PruebasAgregarAlCarro(BaseCarro):
    """Agregar productos aplica las reglas del servicio."""

    def test_agregar_el_mismo_producto_suma_sin_duplicar_filas(self):
        """Dos POST del mismo producto dejan una sola fila con la suma."""
        self.entrar()

        self.client.post("/api/carro/", {"producto": self.producto.id, "cantidad": 2}, format="json")
        self.client.post("/api/carro/", {"producto": self.producto.id, "cantidad": 3}, format="json")

        carro = Carro.objects.get(usuario=self.cliente)
        self.assertEqual(
            carro.items.filter(producto=self.producto).count(),
            1,
            "Debe existir una sola fila por producto en el carro.",
        )
        self.assertEqual(carro.items.get(producto=self.producto).cantidad, 5)

    def test_la_base_de_datos_impide_el_item_duplicado(self):
        """El UniqueConstraint item_unico_por_carro respalda la regla."""
        carro = obtener_carro(self.cliente)
        ItemCarro.objects.create(carro=carro, producto=self.producto, cantidad=1)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ItemCarro.objects.create(carro=carro, producto=self.producto, cantidad=2)

    def test_agregar_no_descuenta_stock(self):
        """Criterio central: el stock no se toca al agregar al carro."""
        self.entrar()
        stock_inicial = self.producto.stock

        respuesta = self.client.post(
            "/api/carro/", {"producto": self.producto.id, "cantidad": 4}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertFalse(respuesta.data["stock_descontado"])
        self.producto.refresh_from_db()
        self.assertEqual(
            self.producto.stock, stock_inicial,
            "Agregar al carro no debe modificar el stock.",
        )

    def test_rechaza_cantidad_mayor_al_stock(self):
        """Pedir más unidades de las que hay responde 400 con el detalle."""
        self.entrar()

        respuesta = self.client.post(
            "/api/carro/", {"producto": self.producto_escaso.id, "cantidad": 5}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(respuesta.data["error"])
        self.assertEqual(respuesta.data["detalle"]["solicitado"], 5)
        self.assertEqual(respuesta.data["detalle"]["disponible"], 1)

    def test_rechaza_producto_agotado(self):
        """Un producto sin stock no se puede agregar."""
        self.entrar()

        respuesta = self.client.post(
            "/api/carro/", {"producto": self.producto_agotado.id, "cantidad": 1}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rechaza_producto_dado_de_baja(self):
        """Un producto inactivo no se puede agregar."""
        self.producto.desactivar()
        self.entrar()

        respuesta = self.client.post(
            "/api/carro/", {"producto": self.producto.id, "cantidad": 1}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.producto.reactivar()

    def test_rechaza_cantidad_cero_o_negativa(self):
        """La cantidad mínima es 1."""
        self.entrar()

        for cantidad in [0, -3]:
            with self.subTest(cantidad=cantidad):
                respuesta = self.client.post(
                    "/api/carro/", {"producto": self.producto.id, "cantidad": cantidad}, format="json"
                )
                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rechaza_producto_inexistente(self):
        """Un id de producto que no existe responde 400 con mensaje claro."""
        self.entrar()

        respuesta = self.client.post(
            "/api/carro/", {"producto": 999999, "cantidad": 1}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)


# ============================================================
# BLOQUE 4 — MODIFICAR, QUITAR Y VACIAR
# El "eliminar" del carro es siempre una baja lógica.
# ============================================================
class PruebasModificarCarro(BaseCarro):
    """Cambiar cantidades y quitar ítems respeta la baja lógica."""

    def setUp(self):
        """Deja un ítem cargado antes de cada prueba."""
        self.entrar()
        self.client.post("/api/carro/", {"producto": self.producto.id, "cantidad": 2}, format="json")

    def test_actualizar_cantidad_fija_el_valor_exacto(self):
        """PATCH establece la cantidad, no la suma."""
        respuesta = self.client.patch(
            f"/api/carro/items/{self.producto.id}/", {"cantidad": 7}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        carro = Carro.objects.get(usuario=self.cliente)
        self.assertEqual(carro.items.get(producto=self.producto).cantidad, 7)

    def test_actualizar_a_una_cantidad_mayor_al_stock_se_rechaza(self):
        """No se puede dejar en el carro más unidades de las que existen."""
        respuesta = self.client.patch(
            f"/api/carro/items/{self.producto.id}/", {"cantidad": 999}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        carro = Carro.objects.get(usuario=self.cliente)
        self.assertEqual(carro.items.get(producto=self.producto).cantidad, 2)

    def test_quitar_item_es_baja_logica(self):
        """DELETE del ítem deja activo=False y conserva la fila."""
        respuesta = self.client.delete(f"/api/carro/items/{self.producto.id}/")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        carro = Carro.objects.get(usuario=self.cliente)
        item = carro.items.get(producto=self.producto)
        self.assertFalse(item.activo)
        self.assertTrue(
            ItemCarro.objects.filter(pk=item.pk).exists(),
            "La fila del ítem debe conservarse en la base de datos.",
        )

    def test_volver_a_agregar_reactiva_el_item_quitado(self):
        """Al reagregar un producto quitado, se reactiva la misma fila."""
        self.client.delete(f"/api/carro/items/{self.producto.id}/")
        carro = Carro.objects.get(usuario=self.cliente)
        identificador = carro.items.get(producto=self.producto).pk

        self.client.post("/api/carro/", {"producto": self.producto.id, "cantidad": 4}, format="json")

        item = ItemCarro.objects.get(pk=identificador)
        self.assertTrue(item.activo)
        self.assertEqual(item.cantidad, 4, "La cantidad parte de cero al reactivar.")
        self.assertEqual(carro.items.filter(producto=self.producto).count(), 1)

    def test_vaciar_carro_da_de_baja_todos_los_items(self):
        """DELETE /api/carro/ deja el carro vacío sin borrar filas."""
        self.client.post("/api/carro/", {"producto": self.producto_escaso.id, "cantidad": 1}, format="json")

        respuesta = self.client.delete("/api/carro/")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        carro = Carro.objects.get(usuario=self.cliente)
        self.assertEqual(carro.items.filter(activo=True).count(), 0)
        self.assertEqual(carro.items.count(), 2, "Las filas se conservan.")

    def test_vaciar_no_descuenta_ni_devuelve_stock(self):
        """Vaciar el carro no afecta el stock, porque nunca se descontó."""
        stock_inicial = self.producto.stock

        self.client.delete("/api/carro/")

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, stock_inicial)

    def test_quitar_un_producto_que_no_esta_en_el_carro(self):
        """Quitar un producto ausente responde 404 con mensaje claro."""
        respuesta = self.client.delete(f"/api/carro/items/{self.producto_agotado.id}/")

        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)


# ============================================================
# BLOQUE 5 — CÁLCULOS DEL CARRO
# total y subtotal se calculan con el precio vigente y no se
# guardan en ninguna columna (3.ª forma normal).
# ============================================================
class PruebasCalculosDelCarro(BaseCarro):
    """Los totales se calculan al leerlos, con el precio actual."""

    def test_total_y_subtotales(self):
        """El total es la suma de cantidad × precio vigente."""
        self.entrar()
        self.client.post("/api/carro/", {"producto": self.producto.id, "cantidad": 2}, format="json")
        self.client.post("/api/carro/", {"producto": self.producto_escaso.id, "cantidad": 1}, format="json")

        respuesta = self.client.get("/api/carro/")

        esperado = Decimal("49990") * 2 + Decimal("159990")
        self.assertEqual(Decimal(respuesta.data["total"]), esperado)

    def test_el_total_del_carro_sigue_el_precio_del_catalogo(self):
        """Si cambia el precio del producto, el total del carro cambia con él."""
        self.entrar()
        self.client.post("/api/carro/", {"producto": self.producto.id, "cantidad": 2}, format="json")

        self.producto.precio = Decimal("60000")
        self.producto.save()

        respuesta = self.client.get("/api/carro/")

        self.assertEqual(Decimal(respuesta.data["total"]), Decimal("120000"))

    def test_el_item_no_guarda_el_precio(self):
        """ItemCarro no tiene columna de precio: lo lee del producto (3FN)."""
        nombres = {campo.name for campo in ItemCarro._meta.get_fields()}

        self.assertNotIn("precio", nombres)
        self.assertNotIn("precio_unitario", nombres)
        self.assertNotIn("subtotal", nombres)

    def test_aviso_cuando_el_stock_baja_por_debajo_de_lo_pedido(self):
        """El carro advierte si el stock ya no alcanza, sin bloquear nada."""
        self.entrar()
        self.client.post("/api/carro/", {"producto": self.producto.id, "cantidad": 10}, format="json")

        self.producto.stock = 2
        self.producto.save()

        respuesta = self.client.get("/api/carro/")

        self.assertIn("avisos_de_stock", respuesta.data)
        self.assertEqual(respuesta.data["avisos_de_stock"][0]["solicitado"], 10)
        self.assertEqual(respuesta.data["avisos_de_stock"][0]["disponible"], 2)


# ============================================================
# BLOQUE 6 — CAPA DE SERVICIOS
# Se prueba directamente carro/servicios.py, que es el módulo que
# comparten la API y las pantallas HTML.
# ============================================================
class PruebasServiciosCarro(TestCase):
    """Las funciones de servicio aplican las reglas sin pasar por HTTP."""

    @classmethod
    def setUpTestData(cls):
        """Crea un cliente y dos productos para operar los servicios."""
        cls.cliente = Usuario.objects.create_user(
            username="servicio_carro", email="servicio_carro@hardpointpc.cl",
            password="Compra.Segura.2026", rol=Rol.CLIENTE,
        )
        cls.categoria = Categoria.objects.create(nombre="Placas Madre", icono="bi-motherboard")
        cls.marca = Marca.objects.create(nombre="ASUS")
        cls.producto = Producto.objects.create(
            sku="MB-SERVICIO-01", nombre="Placa madre de prueba",
            categoria=cls.categoria, marca=cls.marca, precio=Decimal("269990"), stock=6,
        )

    def test_obtener_carro_es_idempotente(self):
        """Llamar dos veces a obtener_carro devuelve el mismo carro."""
        primero = obtener_carro(self.cliente)
        segundo = obtener_carro(self.cliente)

        self.assertEqual(primero.pk, segundo.pk)
        self.assertEqual(Carro.objects.filter(usuario=self.cliente).count(), 1)

    def test_agregar_producto_suma_la_cantidad(self):
        """agregar_producto suma sobre el ítem existente."""
        carro = obtener_carro(self.cliente)

        agregar_producto(carro, self.producto, 2)
        item = agregar_producto(carro, self.producto, 1)

        self.assertEqual(item.cantidad, 3)
        self.assertEqual(carro.items.count(), 1)

    def test_cantidad_invalida_lanza_su_excepcion(self):
        """Una cantidad no entera o menor que 1 lanza CantidadInvalidaError."""
        carro = obtener_carro(self.cliente)

        with self.assertRaises(CantidadInvalidaError):
            agregar_producto(carro, self.producto, 0)
        with self.assertRaises(CantidadInvalidaError):
            agregar_producto(carro, self.producto, "dos")

    def test_stock_insuficiente_lanza_su_excepcion_con_detalle(self):
        """StockInsuficienteEnCarroError informa lo pedido y lo disponible."""
        carro = obtener_carro(self.cliente)

        with self.assertRaises(StockInsuficienteEnCarroError) as contexto:
            agregar_producto(carro, self.producto, 99)

        self.assertEqual(contexto.exception.solicitado, 99)
        self.assertEqual(contexto.exception.disponible, 6)

    def test_producto_inactivo_lanza_su_excepcion(self):
        """Un producto dado de baja no entra al carro."""
        carro = obtener_carro(self.cliente)
        self.producto.desactivar()

        with self.assertRaises(ProductoNoDisponibleError):
            agregar_producto(carro, self.producto, 1)

        self.producto.reactivar()

    def test_actualizar_un_producto_ausente_lanza_su_excepcion(self):
        """actualizar_cantidad exige que el producto ya esté en el carro."""
        carro = obtener_carro(self.cliente)

        with self.assertRaises(ItemNoEnCarroError):
            actualizar_cantidad(carro, self.producto, 3)

    def test_quitar_y_vaciar_usan_baja_logica(self):
        """quitar_producto y vaciar_carro no borran filas."""
        carro = obtener_carro(self.cliente)
        agregar_producto(carro, self.producto, 2)

        quitar_producto(carro, self.producto)
        self.assertEqual(carro.items.count(), 1)
        self.assertFalse(carro.items.first().activo)

        agregar_producto(carro, self.producto, 1)
        afectados = vaciar_carro(carro)

        self.assertEqual(afectados, 1)
        self.assertEqual(carro.items.count(), 1)
        self.assertTrue(carro.esta_vacio)


# ============================================================
# BLOQUE 7 — PANTALLA HTML DEL CARRO
# Las vistas HTML usan las mismas funciones de servicio, así que
# deben comportarse igual que la API.
# ============================================================
class PruebasHtmlCarro(TestCase):
    """La pantalla /panel/carros/ opera el carro con las mismas reglas.

    Se puede VER sin iniciar sesión, pero EDITAR (agregar, actualizar,
    quitar, vaciar) exige una sesión de Administrador de TI; por eso
    setUp() inicia sesión con cls.administrador antes de cada prueba.
    """

    @classmethod
    def setUpTestData(cls):
        """Crea un cliente, un administrador y dos productos para la pantalla de carros."""
        cls.cliente = Usuario.objects.create_user(
            username="html_carro", email="html_carro@hardpointpc.cl",
            password="Compra.Segura.2026", rol=Rol.CLIENTE,
        )
        cls.administrador = Usuario.objects.create_user(
            username="html_carro_admin", email="html_carro_admin@hardpointpc.cl",
            password="Llave.Segura.2026", rol=Rol.ADMINISTRADOR,
        )
        cls.categoria = Categoria.objects.create(nombre="Almacenamiento SSD", icono="bi-device-hdd")
        cls.marca = Marca.objects.create(nombre="Samsung")
        cls.producto = Producto.objects.create(
            sku="SSD-HTML-01", nombre="Unidad SSD de prueba",
            categoria=cls.categoria, marca=cls.marca, precio=Decimal("119990"), stock=15,
        )
        cls.producto_escaso = Producto.objects.create(
            sku="SSD-HTML-ESCASO", nombre="Unidad SSD con una unidad",
            categoria=cls.categoria, marca=cls.marca, precio=Decimal("379990"), stock=1,
        )

    def setUp(self):
        """Inicia sesión como administrador: las pruebas de este archivo escriben."""
        self.client.force_login(self.administrador)

    def test_pantalla_sin_cliente_elegido(self):
        """Sin el parámetro usuario, invita a elegir un cliente."""
        respuesta = self.client.get("/panel/carros/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Elija un cliente")

    def test_pantalla_con_cliente_elegido(self):
        """Con ?usuario=<id> muestra el carro de ese cliente."""
        respuesta = self.client.get("/panel/carros/", {"usuario": self.cliente.id})

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "html_carro")

    def test_agregar_desde_el_html(self):
        """El formulario agrega el producto llamando al servicio."""
        respuesta = self.client.post(
            "/panel/carros/agregar/",
            {"usuario": self.cliente.id, "producto": self.producto.id, "cantidad": 3},
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        carro = Carro.objects.get(usuario=self.cliente)
        self.assertEqual(carro.items.get(producto=self.producto).cantidad, 3)

    def test_agregar_dos_veces_desde_el_html_suma(self):
        """La regla de no duplicar también se aplica en el HTML."""
        for _ in range(2):
            self.client.post(
                "/panel/carros/agregar/",
                {"usuario": self.cliente.id, "producto": self.producto.id, "cantidad": 2},
                follow=True,
            )

        carro = Carro.objects.get(usuario=self.cliente)
        self.assertEqual(carro.items.filter(producto=self.producto).count(), 1)
        self.assertEqual(carro.items.get(producto=self.producto).cantidad, 4)

    def test_agregar_desde_el_html_no_descuenta_stock(self):
        """Tampoco por HTML se mueve el stock al agregar."""
        stock_inicial = self.producto.stock

        self.client.post(
            "/panel/carros/agregar/",
            {"usuario": self.cliente.id, "producto": self.producto.id, "cantidad": 5},
            follow=True,
        )

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, stock_inicial)

    def test_error_de_stock_se_muestra_en_pantalla(self):
        """Pedir más de lo disponible muestra un mensaje explicativo."""
        respuesta = self.client.post(
            "/panel/carros/agregar/",
            {"usuario": self.cliente.id, "producto": self.producto_escaso.id, "cantidad": 9},
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "solo hay 1 disponibles")

    def test_actualizar_quitar_y_vaciar_desde_el_html(self):
        """Las tres acciones funcionan y respetan la baja lógica."""
        self.client.post(
            "/panel/carros/agregar/",
            {"usuario": self.cliente.id, "producto": self.producto.id, "cantidad": 2},
            follow=True,
        )

        self.client.post(
            f"/panel/carros/actualizar/{self.producto.id}/",
            {"usuario": self.cliente.id, "cantidad": 6},
            follow=True,
        )
        carro = Carro.objects.get(usuario=self.cliente)
        self.assertEqual(carro.items.get(producto=self.producto).cantidad, 6)

        self.client.post(
            f"/panel/carros/quitar/{self.producto.id}/",
            {"usuario": self.cliente.id},
            follow=True,
        )
        self.assertFalse(carro.items.get(producto=self.producto).activo)
        self.assertEqual(carro.items.count(), 1, "La fila se conserva.")

        self.client.post(
            "/panel/carros/agregar/",
            {"usuario": self.cliente.id, "producto": self.producto.id, "cantidad": 1},
            follow=True,
        )
        self.client.post("/panel/carros/vaciar/", {"usuario": self.cliente.id}, follow=True)
        self.assertTrue(Carro.objects.get(usuario=self.cliente).esta_vacio)

    def test_usuario_inexistente_no_produce_error(self):
        """Un id de cliente que no existe lleva de vuelta con un aviso."""
        respuesta = self.client.get("/panel/carros/", {"usuario": 999999}, follow=True)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No existe un cliente")


# ============================================================
# BLOQUE 8 — SIN LOGIN SE VE, PERO NO SE EDITA
# Corrige el agujero de seguridad detectado en el panel: cualquiera
# podía vaciar o modificar el carro de cualquier cliente. Ahora GET
# sigue abierto a todos; POST exige una sesión de Administrador de TI.
# ============================================================
class PruebasSeguridadHtmlCarro(TestCase):
    """Sin iniciar sesión se puede ver el carro, pero no editarlo."""

    @classmethod
    def setUpTestData(cls):
        """Cliente, carro y producto para probar el carro sin sesión de administrador."""
        cls.cliente = Usuario.objects.create_user(
            username="seg_carro_cliente", email="seg_carro_cliente@hardpointpc.cl",
            password="Compra.Segura.2026", rol=Rol.CLIENTE,
        )
        cls.categoria = Categoria.objects.create(nombre="Fuentes de Poder", icono="bi-plug")
        cls.marca = Marca.objects.create(nombre="Corsair")
        cls.producto = Producto.objects.create(
            sku="PSU-SEG-01", nombre="Fuente de prueba de seguridad",
            categoria=cls.categoria, marca=cls.marca, precio=Decimal("99990"), stock=10,
        )

    def test_anonimo_puede_ver_el_carro_de_cualquier_cliente(self):
        """Ver el carro de otra persona sigue sin exigir sesión."""
        respuesta = self.client.get("/panel/carros/", {"usuario": self.cliente.id})

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "seg_carro_cliente")

    def test_anonimo_no_puede_agregar_al_carro_de_otro(self):
        """Sin sesión de administrador, agregar un producto no se ejecuta."""
        respuesta = self.client.post(
            "/panel/carros/agregar/",
            {"usuario": self.cliente.id, "producto": self.producto.id, "cantidad": 3},
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(
            Carro.objects.get(usuario=self.cliente).items.filter(producto=self.producto).exists()
        )

    def test_cliente_autenticado_sin_rol_administrador_tampoco_puede_vaciar(self):
        """Estar logueado no basta: el rol debe ser ADMINISTRADOR."""
        self.client.force_login(self.cliente)

        respuesta = self.client.post("/panel/carros/vaciar/", {"usuario": self.cliente.id})

        self.assertEqual(respuesta.status_code, 302)
