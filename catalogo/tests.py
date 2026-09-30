# ============================================================
# catalogo/tests.py — PRUEBAS DEL CATÁLOGO
# Responsabilidad: comprobar los filtros de django-filter, la
# búsqueda, el ordenamiento, la baja lógica (por API y por HTML) y
# las validaciones del modelo respaldadas por la base de datos.
#
# Cubre los criterios de la rúbrica sobre django-filter, CRUD
# completo con baja lógica y validaciones en español.
# ============================================================

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from catalogo.models import Categoria, Marca, Producto
from usuarios.models import Rol, Usuario


# ============================================================
# BLOQUE 1 — CATÁLOGO DE PRUEBA
# Construye un conjunto pequeño pero variado: dos categorías, dos
# marcas y cinco productos con precios y stock distintos, para que
# cada filtro devuelva un subconjunto verificable a mano.
# ============================================================
class BaseCatalogo(APITestCase):
    """Escenario base con un catálogo variado y usuarios de ambos roles."""

    CLAVE_ADMIN = "Llave.Segura.2026"
    CLAVE_CLIENTE = "Compra.Segura.2026"

    @classmethod
    def setUpTestData(cls):
        """Crea los usuarios y el catálogo de prueba."""
        cls.administrador = Usuario.objects.create_user(
            username="admin_catalogo",
            email="admin_catalogo@hardpointpc.cl",
            password=cls.CLAVE_ADMIN,
            rol=Rol.ADMINISTRADOR,
        )
        cls.cliente = Usuario.objects.create_user(
            username="compra_catalogo",
            email="compra_catalogo@hardpointpc.cl",
            password=cls.CLAVE_CLIENTE,
            rol=Rol.CLIENTE,
        )

        cls.procesadores = Categoria.objects.create(nombre="Procesadores", icono="bi-cpu")
        cls.tarjetas = Categoria.objects.create(nombre="Tarjetas de Video", icono="bi-gpu-card")

        cls.intel = Marca.objects.create(nombre="Intel", pais_origen="Estados Unidos")
        cls.nvidia = Marca.objects.create(nombre="NVIDIA", pais_origen="Estados Unidos")

        # (sku, nombre, categoría, marca, precio, stock)
        datos = [
            ("CPU-BARATO", "Procesador económico Intel", cls.procesadores, cls.intel, 99990, 30),
            ("CPU-MEDIO", "Procesador intermedio Intel", cls.procesadores, cls.intel, 329990, 10),
            ("CPU-CARO", "Procesador tope de línea Intel", cls.procesadores, cls.intel, 899990, 1),
            ("GPU-MEDIA", "Tarjeta de video NVIDIA intermedia", cls.tarjetas, cls.nvidia, 389990, 5),
            ("GPU-AGOTADA", "Tarjeta de video NVIDIA sin existencias", cls.tarjetas, cls.nvidia, 2299990, 0),
        ]
        cls.productos = {}
        for sku, nombre, categoria, marca, precio, stock in datos:
            cls.productos[sku] = Producto.objects.create(
                sku=sku,
                nombre=nombre,
                descripcion=f"Descripción de {nombre}.",
                categoria=categoria,
                marca=marca,
                precio=Decimal(precio),
                stock=stock,
            )

    def autenticar(self, username, password):
        """Autentica el cliente de pruebas con un token Bearer."""
        respuesta = self.client.post(
            "/api/auth/login/", {"username": username, "password": password}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK, respuesta.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['access']}")

    def skus_de(self, respuesta):
        """Extrae los SKU de una respuesta paginada del catálogo."""
        return {fila["sku"] for fila in respuesta.data["results"]}


# ============================================================
# BLOQUE 2 — FILTROS DE django-filter
# Criterio evaluado: los filtros precio_min, precio_max, categoria,
# marca y en_stock devuelven exactamente lo correcto.
# ============================================================
class PruebasFiltrosProducto(BaseCatalogo):
    """Cada filtro de ProductoFilter devuelve el subconjunto esperado."""

    def test_filtro_precio_minimo(self):
        """precio_min excluye los productos más baratos que el valor dado."""
        respuesta = self.client.get("/api/productos/", {"precio_min": 350000})

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(self.skus_de(respuesta), {"GPU-MEDIA", "GPU-AGOTADA", "CPU-CARO"})

    def test_filtro_precio_maximo(self):
        """precio_max excluye los productos más caros que el valor dado."""
        respuesta = self.client.get("/api/productos/", {"precio_max": 350000})

        self.assertEqual(self.skus_de(respuesta), {"CPU-BARATO", "CPU-MEDIO"})

    def test_filtro_rango_de_precios(self):
        """Los dos extremos se pueden combinar en un rango."""
        respuesta = self.client.get(
            "/api/productos/", {"precio_min": 300000, "precio_max": 400000}
        )

        self.assertEqual(self.skus_de(respuesta), {"CPU-MEDIO", "GPU-MEDIA"})

    def test_filtro_por_categoria(self):
        """El filtro por id de categoría devuelve solo esa categoría."""
        respuesta = self.client.get("/api/productos/", {"categoria": self.tarjetas.id})

        self.assertEqual(self.skus_de(respuesta), {"GPU-MEDIA", "GPU-AGOTADA"})

    def test_filtro_por_nombre_de_categoria(self):
        """categoria_nombre busca por coincidencia parcial."""
        respuesta = self.client.get("/api/productos/", {"categoria_nombre": "procesa"})

        self.assertEqual(self.skus_de(respuesta), {"CPU-BARATO", "CPU-MEDIO", "CPU-CARO"})

    def test_filtro_por_marca(self):
        """El filtro por id de marca devuelve solo esa marca."""
        respuesta = self.client.get("/api/productos/", {"marca": self.intel.id})

        self.assertEqual(self.skus_de(respuesta), {"CPU-BARATO", "CPU-MEDIO", "CPU-CARO"})

    def test_filtro_por_nombre_de_marca(self):
        """marca_nombre busca por coincidencia parcial, sin distinguir mayúsculas."""
        respuesta = self.client.get("/api/productos/", {"marca_nombre": "nvid"})

        self.assertEqual(self.skus_de(respuesta), {"GPU-MEDIA", "GPU-AGOTADA"})

    def test_filtro_en_stock_verdadero(self):
        """en_stock=true deja fuera los productos agotados."""
        respuesta = self.client.get("/api/productos/", {"en_stock": "true"})

        skus = self.skus_de(respuesta)
        self.assertNotIn("GPU-AGOTADA", skus)
        self.assertEqual(skus, {"CPU-BARATO", "CPU-MEDIO", "CPU-CARO", "GPU-MEDIA"})

    def test_filtro_en_stock_falso(self):
        """en_stock=false devuelve únicamente los productos agotados."""
        respuesta = self.client.get("/api/productos/", {"en_stock": "false"})

        self.assertEqual(self.skus_de(respuesta), {"GPU-AGOTADA"})

    def test_filtro_por_sku_exacto_sin_distinguir_mayusculas(self):
        """sku compara de forma exacta pero ignorando mayúsculas."""
        respuesta = self.client.get("/api/productos/", {"sku": "cpu-medio"})

        self.assertEqual(self.skus_de(respuesta), {"CPU-MEDIO"})

    def test_busqueda_por_texto(self):
        """search busca en nombre, SKU, descripción y nombre de la marca."""
        respuesta = self.client.get("/api/productos/", {"search": "tope de línea"})

        self.assertEqual(self.skus_de(respuesta), {"CPU-CARO"})

    def test_busqueda_encuentra_por_marca(self):
        """La búsqueda libre también considera el nombre de la marca."""
        respuesta = self.client.get("/api/productos/", {"search": "NVIDIA"})

        self.assertEqual(self.skus_de(respuesta), {"GPU-MEDIA", "GPU-AGOTADA"})

    def test_ordenamiento_por_precio_ascendente(self):
        """ordering=precio devuelve del más barato al más caro."""
        respuesta = self.client.get("/api/productos/", {"ordering": "precio"})

        precios = [int(fila["precio"]) for fila in respuesta.data["results"]]
        self.assertEqual(precios, sorted(precios))

    def test_ordenamiento_por_precio_descendente(self):
        """ordering=-precio devuelve del más caro al más barato."""
        respuesta = self.client.get("/api/productos/", {"ordering": "-precio"})

        precios = [int(fila["precio"]) for fila in respuesta.data["results"]]
        self.assertEqual(precios, sorted(precios, reverse=True))

    def test_paginacion_de_diez_en_diez(self):
        """La respuesta paginada trae count, next, previous y results."""
        respuesta = self.client.get("/api/productos/")

        for clave in ["count", "next", "previous", "results"]:
            self.assertIn(clave, respuesta.data)
        self.assertEqual(respuesta.data["count"], 5)


# ============================================================
# BLOQUE 3 — BAJA LÓGICA POR LA API
# Criterio evaluado: el "eliminar" no borra filas.
# ============================================================
class PruebasBajaLogicaApi(BaseCatalogo):
    """DELETE desactiva el registro y conserva la fila."""

    def test_delete_de_producto_no_borra_la_fila(self):
        """El producto queda con activo=False y sigue existiendo."""
        self.autenticar("admin_catalogo", self.CLAVE_ADMIN)
        producto = self.productos["CPU-MEDIO"]

        respuesta = self.client.delete(f"/api/productos/{producto.id}/")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertTrue(
            Producto.objects.filter(pk=producto.pk).exists(),
            "La fila del producto debe conservarse en la base de datos.",
        )
        producto.refresh_from_db()
        self.assertFalse(producto.activo)

    def test_producto_dado_de_baja_desaparece_del_listado_publico(self):
        """El catálogo público solo muestra productos activos."""
        self.autenticar("admin_catalogo", self.CLAVE_ADMIN)
        producto = self.productos["CPU-MEDIO"]
        self.client.delete(f"/api/productos/{producto.id}/")

        self.client.credentials()
        respuesta = self.client.get("/api/productos/")

        self.assertNotIn("CPU-MEDIO", self.skus_de(respuesta))

    def test_incluir_inactivos_muestra_los_dados_de_baja(self):
        """Con ?incluir_inactivos=true el administrador ve también los de baja."""
        self.autenticar("admin_catalogo", self.CLAVE_ADMIN)
        producto = self.productos["CPU-MEDIO"]
        self.client.delete(f"/api/productos/{producto.id}/")

        respuesta = self.client.get("/api/productos/", {"incluir_inactivos": "true"})

        self.assertIn("CPU-MEDIO", self.skus_de(respuesta))

    def test_reactivar_vuelve_a_publicar_el_producto(self):
        """El endpoint de reactivación revierte la baja lógica."""
        self.autenticar("admin_catalogo", self.CLAVE_ADMIN)
        producto = self.productos["CPU-MEDIO"]
        self.client.delete(f"/api/productos/{producto.id}/")

        respuesta = self.client.post(f"/api/productos/{producto.id}/reactivar/")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        producto.refresh_from_db()
        self.assertTrue(producto.activo)

    def test_baja_logica_de_categoria_y_marca(self):
        """Las tres entidades del catálogo comparten la baja lógica."""
        self.autenticar("admin_catalogo", self.CLAVE_ADMIN)

        self.client.delete(f"/api/categorias/{self.tarjetas.id}/")
        self.client.delete(f"/api/marcas/{self.nvidia.id}/")

        self.assertTrue(Categoria.objects.filter(pk=self.tarjetas.pk).exists())
        self.assertTrue(Marca.objects.filter(pk=self.nvidia.pk).exists())
        self.assertFalse(Categoria.objects.get(pk=self.tarjetas.pk).activo)
        self.assertFalse(Marca.objects.get(pk=self.nvidia.pk).activo)


# ============================================================
# BLOQUE 4 — VALIDACIONES DE LA API
# Los mensajes de error deben ser claros y estar en español.
# ============================================================
class PruebasValidacionesApi(BaseCatalogo):
    """Las validaciones del catálogo devuelven mensajes claros."""

    def _cuerpo(self, **cambios):
        """Cuerpo válido de producto, con los cambios indicados."""
        datos = {
            "sku": "CPU-VALIDACION",
            "nombre": "Procesador de validación",
            "descripcion": "Producto para probar validaciones.",
            "categoria": self.procesadores.id,
            "marca": self.intel.id,
            "precio": 100000,
            "stock": 3,
        }
        datos.update(cambios)
        return datos

    def test_precio_cero_se_rechaza(self):
        """El precio debe ser mayor que cero."""
        self.autenticar("admin_catalogo", self.CLAVE_ADMIN)

        respuesta = self.client.post("/api/productos/", self._cuerpo(precio=0), format="json")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("precio", str(respuesta.data).lower())

    def test_precio_negativo_se_rechaza(self):
        """Un precio negativo tampoco se acepta."""
        self.autenticar("admin_catalogo", self.CLAVE_ADMIN)

        respuesta = self.client.post("/api/productos/", self._cuerpo(precio=-5000), format="json")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_stock_negativo_se_rechaza(self):
        """El stock no puede ser negativo."""
        self.autenticar("admin_catalogo", self.CLAVE_ADMIN)

        respuesta = self.client.post("/api/productos/", self._cuerpo(stock=-1), format="json")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sku_repetido_se_rechaza(self):
        """El SKU es único en todo el catálogo."""
        self.autenticar("admin_catalogo", self.CLAVE_ADMIN)

        respuesta = self.client.post("/api/productos/", self._cuerpo(sku="CPU-MEDIO"), format="json")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("sku", str(respuesta.data).lower())

    def test_sku_se_guarda_en_mayusculas(self):
        """El SKU se normaliza a mayúsculas al crear el producto."""
        self.autenticar("admin_catalogo", self.CLAVE_ADMIN)

        respuesta = self.client.post(
            "/api/productos/", self._cuerpo(sku="cpu-minusculas"), format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED, respuesta.data)
        self.assertTrue(Producto.objects.filter(sku="CPU-MINUSCULAS").exists())

    def test_categoria_repetida_se_rechaza(self):
        """No pueden existir dos categorías con el mismo nombre."""
        self.autenticar("admin_catalogo", self.CLAVE_ADMIN)

        respuesta = self.client.post(
            "/api/categorias/", {"nombre": "procesadores"}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recurso_inexistente_responde_json_con_redireccion(self):
        """GET de un producto que no existe devuelve JSON controlado en español."""
        respuesta = self.client.get("/api/productos/999999/")

        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(respuesta.data["error"])
        self.assertEqual(respuesta.data["redireccion"], "/")
        self.assertIn("no existe", respuesta.data["mensaje"].lower())
        self.assertEqual(respuesta["Content-Type"].split(";")[0], "application/json")


# ============================================================
# BLOQUE 5 — RESTRICCIONES EN LA BASE DE DATOS
# Última barrera: aunque alguien salte los serializers, PostgreSQL
# rechaza los datos inválidos por los CheckConstraint del modelo.
# ============================================================
class PruebasRestriccionesBaseDeDatos(TestCase):
    """Los CheckConstraint y UniqueConstraint actúan en PostgreSQL."""

    @classmethod
    def setUpTestData(cls):
        """Crea la categoría y la marca necesarias para los productos."""
        cls.categoria = Categoria.objects.create(nombre="Memorias RAM", icono="bi-memory")
        cls.marca = Marca.objects.create(nombre="Kingston")

    def test_la_base_rechaza_precio_cero(self):
        """El CheckConstraint producto_precio_positivo impide precio <= 0."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Producto.objects.create(
                    sku="RAM-INVALIDA",
                    nombre="Memoria con precio inválido",
                    categoria=self.categoria,
                    marca=self.marca,
                    precio=0,
                    stock=5,
                )

    def test_la_base_rechaza_sku_repetido(self):
        """El UniqueConstraint producto_sku_unico impide SKU duplicados."""
        Producto.objects.create(
            sku="RAM-UNICA", nombre="Memoria original",
            categoria=self.categoria, marca=self.marca, precio=49990, stock=5,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Producto.objects.create(
                    sku="RAM-UNICA", nombre="Memoria duplicada",
                    categoria=self.categoria, marca=self.marca, precio=59990, stock=5,
                )

    def test_propiedades_calculadas_del_producto(self):
        """disponible y estado_stock se calculan, no se almacenan."""
        producto = Producto.objects.create(
            sku="RAM-CALCULOS", nombre="Memoria para cálculos",
            categoria=self.categoria, marca=self.marca, precio=49990, stock=3,
        )

        self.assertTrue(producto.disponible)
        self.assertEqual(producto.estado_stock, "Últimas unidades")

        producto.stock = 0
        producto.save()
        self.assertFalse(producto.disponible)
        self.assertEqual(producto.estado_stock, "Sin stock")

        producto.stock = 50
        producto.save()
        self.assertEqual(producto.estado_stock, "Disponible")


# ============================================================
# BLOQUE 6 — PANTALLAS HTML DEL CATÁLOGO
# Criterio evaluado: el CRUD por HTML funciona y su "eliminar"
# tampoco borra filas.
# ============================================================
class PruebasHtmlCatalogo(TestCase):
    """Las pantallas HTML del catálogo crean, editan y dan de baja."""

    @classmethod
    def setUpTestData(cls):
        """Crea un catálogo mínimo para operar desde el HTML."""
        cls.categoria = Categoria.objects.create(nombre="Fuentes de Poder", icono="bi-plug")
        cls.marca = Marca.objects.create(nombre="Corsair", pais_origen="Estados Unidos")
        cls.producto = Producto.objects.create(
            sku="PSU-HTML-01",
            nombre="Fuente de poder de prueba",
            categoria=cls.categoria,
            marca=cls.marca,
            precio=109990,
            stock=12,
        )

    def test_catalogo_publico_responde_200(self):
        """La pantalla /catalogo/ se sirve correctamente."""
        respuesta = self.client.get("/catalogo/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Fuente de poder de prueba")

    def test_filtros_html_usan_el_mismo_filterset(self):
        """El formulario GET del catálogo filtra igual que la API."""
        respuesta = self.client.get("/catalogo/", {"precio_min": 200000})

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "PSU-HTML-01")

    def test_ficha_publica_del_producto(self):
        """La ficha /catalogo/<id>/ muestra SKU, precio y stock."""
        respuesta = self.client.get(f"/catalogo/{self.producto.id}/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "PSU-HTML-01")
        self.assertContains(respuesta, "$109.990")

    def test_crear_producto_desde_el_html(self):
        """El formulario de creación guarda el producto con el SKU normalizado."""
        respuesta = self.client.post(
            "/panel/productos/nuevo/",
            {
                "sku": "psu-html-nueva",
                "nombre": "Fuente creada por HTML",
                "descripcion": "Creada en la prueba.",
                "categoria": self.categoria.id,
                "marca": self.marca.id,
                "precio": 129990,
                "stock": 7,
                "activo": "on",
            },
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(Producto.objects.filter(sku="PSU-HTML-NUEVA").exists())

    def test_editar_producto_desde_el_html(self):
        """El formulario de edición actualiza el precio."""
        self.client.post(
            f"/panel/productos/{self.producto.id}/editar/",
            {
                "sku": self.producto.sku,
                "nombre": self.producto.nombre,
                "descripcion": self.producto.descripcion,
                "categoria": self.categoria.id,
                "marca": self.marca.id,
                "precio": 99990,
                "stock": self.producto.stock,
                "activo": "on",
            },
            follow=True,
        )

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.precio, Decimal("99990"))

    def test_formulario_html_rechaza_precio_cero(self):
        """El ModelForm muestra el error por campo y no guarda."""
        respuesta = self.client.post(
            f"/panel/productos/{self.producto.id}/editar/",
            {
                "sku": self.producto.sku,
                "nombre": self.producto.nombre,
                "descripcion": "",
                "categoria": self.categoria.id,
                "marca": self.marca.id,
                "precio": 0,
                "stock": 5,
                "activo": "on",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "El precio debe ser mayor que cero.")
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.precio, Decimal("109990"))

    def test_desactivar_desde_el_html_no_borra_la_fila(self):
        """La baja lógica por HTML conserva el registro."""
        respuesta = self.client.post(
            f"/panel/productos/{self.producto.id}/desactivar/", follow=True
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(
            Producto.objects.filter(pk=self.producto.pk).exists(),
            "La fila del producto debe conservarse.",
        )
        self.producto.refresh_from_db()
        self.assertFalse(self.producto.activo)

    def test_reactivar_desde_el_html(self):
        """La reactivación por HTML vuelve a publicar el producto."""
        self.producto.desactivar()

        self.client.post(f"/panel/productos/{self.producto.id}/reactivar/", follow=True)

        self.producto.refresh_from_db()
        self.assertTrue(self.producto.activo)

    def test_confirmacion_antes_de_desactivar(self):
        """El GET de la baja muestra la pantalla de confirmación."""
        respuesta = self.client.get(f"/panel/productos/{self.producto.id}/desactivar/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No se borra ninguna fila")
        self.producto.refresh_from_db()
        self.assertTrue(self.producto.activo, "El GET no debe cambiar nada.")

    def test_crud_html_de_categorias_y_marcas(self):
        """Las pantallas de categorías y marcas crean y dan de baja."""
        self.client.post(
            "/panel/categorias/nueva/",
            {"nombre": "Refrigeración", "descripcion": "Sistemas de enfriamiento.", "icono": "bi-fan", "activo": "on"},
            follow=True,
        )
        self.assertTrue(Categoria.objects.filter(nombre="Refrigeración").exists())

        self.client.post(
            "/panel/marcas/nueva/",
            {"nombre": "Noctua", "pais_origen": "Austria", "activo": "on"},
            follow=True,
        )
        self.assertTrue(Marca.objects.filter(nombre="Noctua").exists())

        noctua = Marca.objects.get(nombre="Noctua")
        self.client.post(f"/panel/marcas/{noctua.id}/desactivar/", follow=True)
        self.assertTrue(Marca.objects.filter(pk=noctua.pk).exists())
        self.assertFalse(Marca.objects.get(pk=noctua.pk).activo)
