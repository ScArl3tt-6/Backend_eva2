# ============================================================
# core/tests.py — PRUEBAS TRANSVERSALES
# Responsabilidad: comprobar los criterios de la rúbrica que
# atraviesan todo el sitio:
#
#   1. NINGUNA ruta inexistente muestra un 404: todas terminan en la
#      pantalla de redirección. Se prueban más de ocho direcciones
#      absurdas distintas.
#   2. Una ruta sin barra final que sí existe con barra redirige a
#      ella (/catalogo → /catalogo/), no al inicio.
#   3. Todas las pantallas HTML principales responden 200 y muestran
#      el nombre de la alumna, su sección y el año en el footer, con
#      el enlace a la documentación.
#   4. La documentación OpenAPI (Swagger UI y ReDoc) se sirve y
#      también lleva el footer.
#   5. El filtro |clp da formato chileno a los precios.
# ============================================================

from decimal import Decimal

from django.conf import settings
from django.test import TestCase

from carro.servicios import agregar_producto, obtener_carro
from catalogo.models import Categoria, Marca, Producto
from core.templatetags.formato import (
    clase_estado,
    icono_estado,
    pesos_chilenos,
    separador_de_miles,
)
from core.utilidades import booleano_de_texto, entero_o_none, obtener_o_redirigir
from ordenes.servicios import realizar_checkout
from usuarios.models import Rol, Usuario


# ============================================================
# BLOQUE 1 — ESCENARIO CON DATOS
# Las pantallas se prueban con contenido real, para que también se
# ejerciten las tablas, las tarjetas y los cálculos, no solo los
# estados vacíos.
# ============================================================
class BaseSitio(TestCase):
    """Escenario con catálogo, cliente, carro y una orden."""

    @classmethod
    def setUpTestData(cls):
        """Crea un conjunto mínimo de datos para poblar las pantallas."""
        cls.cliente = Usuario.objects.create_user(
            username="sitio_cliente", email="sitio_cliente@hardpointpc.cl",
            password="Compra.Segura.2026", rol=Rol.CLIENTE,
        )
        cls.administrador = Usuario.objects.create_user(
            username="sitio_admin", email="sitio_admin@hardpointpc.cl",
            password="Llave.Segura.2026", rol=Rol.ADMINISTRADOR,
        )

        cls.categoria = Categoria.objects.create(nombre="Procesadores", icono="bi-cpu")
        cls.marca = Marca.objects.create(nombre="Intel", pais_origen="Estados Unidos")
        cls.producto = Producto.objects.create(
            sku="CPU-SITIO-01", nombre="Procesador del sitio",
            categoria=cls.categoria, marca=cls.marca,
            precio=Decimal("1299990"), stock=6,
        )

        carro = obtener_carro(cls.cliente)
        agregar_producto(carro, cls.producto, 1)
        cls.orden = realizar_checkout(cls.cliente)


# ============================================================
# BLOQUE 2 — CONTROL TOTAL DE RUTAS INEXISTENTES
# Requisito crítico: el 404 no debe existir en ninguna dirección.
# ============================================================
class PruebasRutasInexistentes(BaseSitio):
    """Ninguna dirección absurda muestra un 404 ni un error."""

    RUTAS_ABSURDAS = [
        "/asdf",
        "/asdf/",
        "/api/xyz",
        "/api/xyz/",
        "/panel/productos/999999/",
        "/panel/categorias/999999/",
        "/catalogo/abc/",
        "/catalogo/999999/",
        "/%%%",
        "/esto/no/existe/en/ninguna/parte/",
        "/panel/inventado/",
        "/documentacion/inventada/",
        "/index.php",
        "/wp-admin/",
    ]

    def test_ninguna_ruta_absurda_devuelve_404(self):
        """Las catorce rutas de prueba terminan en la pantalla de redirección."""
        for ruta in self.RUTAS_ABSURDAS:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta, follow=True)

                self.assertNotEqual(
                    respuesta.status_code, 404,
                    f"La ruta {ruta} devolvió 404; debería mostrar la redirección.",
                )
                self.assertEqual(respuesta.status_code, 200)

    def test_las_rutas_absurdas_muestran_la_pantalla_de_redireccion(self):
        """El contenido es el aviso del proyecto, con la ruta solicitada."""
        for ruta in ["/asdf", "/api/xyz", "/%%%", "/panel/inventado/"]:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta, follow=True)

                self.assertContains(respuesta, "La página que buscas no existe")
                self.assertContains(respuesta, "Volver al inicio")

    def test_la_pantalla_de_redireccion_incluye_la_cuenta_regresiva(self):
        """Hay meta refresh de 3 segundos y respaldo en JavaScript."""
        respuesta = self.client.get("/asdf", follow=True)

        self.assertContains(respuesta, 'http-equiv="refresh"')
        self.assertContains(respuesta, "3;url=/")
        self.assertContains(respuesta, 'id="cuenta-regresiva"')

    def test_la_pantalla_de_redireccion_muestra_la_ruta_pedida(self):
        """El aviso indica qué dirección se intentó abrir."""
        respuesta = self.client.get("/ruta-que-no-existe", follow=True)

        self.assertContains(respuesta, "/ruta-que-no-existe")

    def test_un_id_inexistente_en_el_panel_no_produce_error(self):
        """/panel/productos/999999/ muestra el aviso, no una traza."""
        respuesta = self.client.get("/panel/productos/999999/", follow=True)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No existe el producto con el id 999999")

    def test_la_raiz_siempre_carga_el_inicio(self):
        """La dirección raíz responde con la portada."""
        respuesta = self.client.get("/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, settings.NOMBRE_COMERCIAL)

    def test_ruta_sin_barra_redirige_a_la_version_con_barra(self):
        """Las rutas existentes sin barra final redirigen a la correcta."""
        casos = {
            "/catalogo": "/catalogo/",
            "/panel": "/panel/",
            "/documentacion": "/documentacion/",
            "/panel/productos": "/panel/productos/",
            "/panel/ordenes": "/panel/ordenes/",
        }

        for origen, destino in casos.items():
            with self.subTest(origen=origen):
                respuesta = self.client.get(origen)

                self.assertEqual(respuesta.status_code, 302)
                self.assertEqual(respuesta["Location"], destino)

    def test_la_redireccion_con_barra_conserva_los_parametros(self):
        """Los filtros no se pierden al agregar la barra final."""
        respuesta = self.client.get("/catalogo?precio_min=100000")

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta["Location"], "/catalogo/?precio_min=100000")

    def test_la_api_devuelve_json_para_un_recurso_inexistente(self):
        """En la API el aviso es JSON en español, no una página HTML."""
        respuesta = self.client.get("/api/productos/999999/")

        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(respuesta["Content-Type"].split(";")[0], "application/json")
        cuerpo = respuesta.json()
        self.assertTrue(cuerpo["error"])
        self.assertEqual(cuerpo["redireccion"], "/")


# ============================================================
# BLOQUE 3 — FOOTER CON LOS DATOS DE LA ALUMNA
# Criterio evaluado: el nombre, la sección y el año aparecen en
# TODAS las pantallas, junto al enlace a la documentación.
# ============================================================
class PruebasFooterEnTodasLasPantallas(BaseSitio):
    """Cada pantalla HTML lleva la firma de la alumna en el footer."""

    def rutas(self):
        """Devuelve todas las pantallas HTML principales del sitio."""
        return [
            "/",
            "/catalogo/",
            f"/catalogo/{self.producto.id}/",
            "/panel/",
            "/documentacion/",
            "/redireccion/",
            "/panel/categorias/",
            "/panel/categorias/nueva/",
            f"/panel/categorias/{self.categoria.id}/",
            f"/panel/categorias/{self.categoria.id}/editar/",
            f"/panel/categorias/{self.categoria.id}/desactivar/",
            "/panel/marcas/",
            "/panel/marcas/nueva/",
            f"/panel/marcas/{self.marca.id}/",
            f"/panel/marcas/{self.marca.id}/editar/",
            "/panel/productos/",
            "/panel/productos/nuevo/",
            f"/panel/productos/{self.producto.id}/",
            f"/panel/productos/{self.producto.id}/editar/",
            "/panel/usuarios/",
            "/panel/usuarios/nuevo/",
            f"/panel/usuarios/{self.cliente.id}/",
            f"/panel/usuarios/{self.cliente.id}/editar/",
            "/panel/carros/",
            f"/panel/carros/?usuario={self.cliente.id}",
            "/panel/ordenes/",
            f"/panel/ordenes/{self.orden.id}/",
        ]

    def test_todas_las_pantallas_responden_200(self):
        """Ninguna pantalla principal falla."""
        for ruta in self.rutas():
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 200, f"Falló {ruta}")

    def test_todas_las_pantallas_muestran_el_nombre_la_seccion_y_el_ano(self):
        """El footer aparece con los tres datos exigidos."""
        for ruta in self.rutas():
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)

                self.assertContains(respuesta, settings.ALUMNO_NOMBRE)
                self.assertContains(respuesta, settings.ALUMNO_SECCION)
                self.assertContains(respuesta, settings.ALUMNO_ANIO)

    def test_todas_las_pantallas_enlazan_la_documentacion_y_swagger(self):
        """El footer incluye los enlaces exigidos."""
        for ruta in self.rutas():
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)

                self.assertContains(respuesta, 'href="/documentacion/"')
                self.assertContains(respuesta, 'href="/api/docs/"')

    def test_el_nombre_comercial_esta_en_la_barra_de_navegacion(self):
        """La marca comercial se muestra en todas las pantallas."""
        for ruta in ["/", "/catalogo/", "/panel/", "/documentacion/"]:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertContains(respuesta, settings.NOMBRE_COMERCIAL)

    def test_la_pantalla_de_redireccion_tambien_lleva_footer(self):
        """Incluso el aviso de ruta inexistente muestra la firma."""
        respuesta = self.client.get("/ruta-inexistente", follow=True)

        self.assertContains(respuesta, settings.ALUMNO_NOMBRE)
        self.assertContains(respuesta, settings.ALUMNO_SECCION)
        self.assertContains(respuesta, settings.ALUMNO_ANIO)

    def test_el_idioma_del_documento_es_espanol(self):
        """Todas las pantallas declaran lang="es"."""
        for ruta in ["/", "/catalogo/", "/panel/", "/documentacion/"]:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertContains(respuesta, '<html lang="es">')


# ============================================================
# BLOQUE 4 — DOCUMENTACIÓN OpenAPI
# Swagger UI y ReDoc deben servirse y llevar el footer.
# ============================================================
class PruebasDocumentacionApi(BaseSitio):
    """El esquema OpenAPI, Swagger UI y ReDoc funcionan."""

    def test_el_esquema_openapi_se_genera(self):
        """GET /api/schema/ devuelve el esquema."""
        respuesta = self.client.get("/api/schema/")

        self.assertEqual(respuesta.status_code, 200)

    def test_swagger_ui_se_sirve_con_footer(self):
        """Swagger UI carga y muestra los datos de la alumna."""
        respuesta = self.client.get("/api/docs/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "swagger-ui")
        self.assertContains(respuesta, settings.ALUMNO_NOMBRE)
        self.assertContains(respuesta, settings.ALUMNO_SECCION)
        self.assertContains(respuesta, settings.ALUMNO_ANIO)

    def test_redoc_se_sirve_con_footer(self):
        """ReDoc carga y muestra los datos de la alumna."""
        respuesta = self.client.get("/api/redoc/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, settings.ALUMNO_NOMBRE)
        self.assertContains(respuesta, settings.ALUMNO_SECCION)

    def test_el_esquema_declara_la_seguridad_bearer(self):
        """El esquema incluye el esquema de seguridad JWT."""
        respuesta = self.client.get("/api/schema/", {"format": "json"})

        esquema = respuesta.json()
        seguridad = esquema["components"]["securitySchemes"]
        self.assertIn("jwtAuth", seguridad)
        self.assertEqual(seguridad["jwtAuth"]["scheme"], "bearer")

    def test_el_esquema_documenta_los_filtros_de_productos(self):
        """Los filtros de ProductoFilter aparecen como parámetros."""
        respuesta = self.client.get("/api/schema/", {"format": "json"})

        esquema = respuesta.json()
        parametros = esquema["paths"]["/api/productos/"]["get"]["parameters"]
        nombres = {parametro["name"] for parametro in parametros}

        for filtro in ["categoria", "marca", "precio_min", "precio_max", "en_stock", "sku"]:
            self.assertIn(filtro, nombres, f"Falta el parámetro {filtro} en Swagger.")

    def test_la_descripcion_incluye_los_datos_de_la_alumna(self):
        """La documentación identifica a la alumna, su sección y el año."""
        respuesta = self.client.get("/api/schema/", {"format": "json"})

        descripcion = respuesta.json()["info"]["description"]
        self.assertIn(settings.ALUMNO_NOMBRE, descripcion)
        self.assertIn(settings.ALUMNO_SECCION, descripcion)
        self.assertIn(settings.ALUMNO_ANIO, descripcion)

    def test_la_raiz_de_la_api_es_publica(self):
        """GET /api/ responde sin token e identifica el proyecto."""
        respuesta = self.client.get("/api/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["proyecto"], settings.NOMBRE_COMERCIAL)
        self.assertEqual(respuesta.data["alumna"]["nombre"], settings.ALUMNO_NOMBRE)
        self.assertEqual(respuesta.data["alumna"]["seccion"], settings.ALUMNO_SECCION)


# ============================================================
# BLOQUE 5 — CONTENIDO DE LAS PANTALLAS
# Se comprueba que las pantallas muestren datos reales y no
# estructuras vacías.
# ============================================================
class PruebasContenidoDeLasPantallas(BaseSitio):
    """Las pantallas muestran los datos que corresponden."""

    def test_el_inicio_muestra_estadisticas_reales(self):
        """La portada informa los conteos calculados con el ORM."""
        respuesta = self.client.get("/")

        self.assertContains(respuesta, "Productos publicados")
        self.assertContains(respuesta, "Órdenes por estado")
        self.assertContains(respuesta, "Procesador del sitio")

    def test_el_panel_lista_los_seis_modulos(self):
        """El panel ofrece acceso a los seis módulos de gestión."""
        respuesta = self.client.get("/panel/")

        for modulo in ["Categorías", "Marcas", "Productos", "Usuarios", "Carros", "Órdenes"]:
            self.assertContains(respuesta, modulo)

    def test_la_documentacion_muestra_la_matriz_de_roles(self):
        """La guía incluye la matriz de roles y las credenciales."""
        respuesta = self.client.get("/documentacion/")

        for texto in ["PÚBLICO", "CLIENTE", "ADMINISTRADOR", "admin_ti", "cliente1"]:
            self.assertContains(respuesta, texto)

    def test_la_documentacion_explica_el_flujo_y_las_transiciones(self):
        """La guía describe el flujo carro → orden → pago → entrega."""
        respuesta = self.client.get("/documentacion/")

        for texto in ["Checkout", "Pago", "Entrega o cancelación", "Transiciones permitidas"]:
            self.assertContains(respuesta, texto)

    def test_los_precios_se_muestran_en_formato_chileno(self):
        """El filtro |clp aplica el separador de miles chileno."""
        respuesta = self.client.get(f"/catalogo/{self.producto.id}/")

        self.assertContains(respuesta, "$1.299.990")

    def test_el_catalogo_muestra_el_formulario_de_filtros(self):
        """El catálogo público ofrece los filtros de ProductoFilter."""
        respuesta = self.client.get("/catalogo/")

        for campo in ["categoria", "marca", "precio_min", "precio_max", "en_stock", "sku"]:
            self.assertContains(respuesta, f'name="{campo}"')

    def test_estado_vacio_con_accion(self):
        """Cuando un filtro no devuelve nada, se ofrece una salida."""
        respuesta = self.client.get("/catalogo/", {"precio_min": 99999999})

        self.assertContains(respuesta, "Ningún componente coincide con esos filtros")
        self.assertContains(respuesta, "Ver todo el catálogo")


# ============================================================
# BLOQUE 6 — FILTROS DE PLANTILLA
# Se prueban directamente las funciones de formato.py.
# ============================================================
class PruebasFiltrosDeFormato(TestCase):
    """El filtro |clp y sus compañeros dan el formato correcto."""

    def test_formato_de_pesos_chilenos(self):
        """El separador de miles es el punto y no hay decimales."""
        casos = {
            0: "$0",
            990: "$990",
            49990: "$49.990",
            1299990: "$1.299.990",
            2299990: "$2.299.990",
            Decimal("329990"): "$329.990",
        }

        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(pesos_chilenos(entrada), esperado)

    def test_formato_con_valores_invalidos(self):
        """Un valor no numérico no rompe la plantilla."""
        for entrada in [None, "", "texto", []]:
            with self.subTest(entrada=entrada):
                self.assertEqual(pesos_chilenos(entrada), "$0")

    def test_formato_de_valor_negativo(self):
        """El signo se mantiene delante del símbolo de peso."""
        self.assertEqual(pesos_chilenos(-49990), "-$49.990")

    def test_separador_de_miles_sin_simbolo(self):
        """El filtro |miles formatea cantidades sin el peso."""
        self.assertEqual(separador_de_miles(1500), "1.500")
        self.assertEqual(separador_de_miles(0), "0")
        self.assertEqual(separador_de_miles("texto"), "0")

    def test_clase_e_icono_por_estado(self):
        """Cada estado tiene su clase CSS y su icono."""
        self.assertEqual(clase_estado("PAGADO"), "estado-pagado")
        self.assertEqual(clase_estado("pagado"), "estado-pagado")
        self.assertEqual(clase_estado("CANCELADO"), "estado-cancelado")
        self.assertEqual(clase_estado("INVENTADO"), "estado-pendiente")
        self.assertEqual(icono_estado("ENTREGADO"), "bi-box-seam")


# ============================================================
# BLOQUE 7 — HELPER obtener_o_redirigir
# Sustituye a get_object_or_404 en las vistas HTML.
# ============================================================
class PruebasUtilidades(TestCase):
    """El helper devuelve el objeto o una redirección, nunca un 404."""

    @classmethod
    def setUpTestData(cls):
        """Crea una categoría para buscar."""
        cls.categoria = Categoria.objects.create(nombre="Memorias RAM", icono="bi-memory")

    def test_devuelve_el_objeto_cuando_existe(self):
        """Si el registro existe, la redirección es None."""
        objeto, redireccion = obtener_o_redirigir(Categoria, pk=self.categoria.pk)

        self.assertEqual(objeto, self.categoria)
        self.assertIsNone(redireccion)

    def test_devuelve_una_redireccion_cuando_no_existe(self):
        """Si el registro no existe, entrega una función de redirección."""
        objeto, redireccion = obtener_o_redirigir(Categoria, pk=999999)

        self.assertIsNone(objeto)
        self.assertIsNotNone(redireccion)
        self.assertTrue(callable(redireccion))

    def test_conversion_de_parametros(self):
        """entero_o_none y booleano_de_texto toleran entradas inválidas."""
        self.assertEqual(entero_o_none("42"), 42)
        self.assertIsNone(entero_o_none("abc"))
        self.assertIsNone(entero_o_none(None))

        self.assertTrue(booleano_de_texto("true"))
        self.assertTrue(booleano_de_texto("sí"))
        self.assertTrue(booleano_de_texto("1"))
        self.assertFalse(booleano_de_texto("false"))
        self.assertFalse(booleano_de_texto(""))


# ============================================================
# BLOQUE 8 — CONTEXT PROCESSOR
# Los datos de la alumna llegan del .env, nunca escritos a mano.
# ============================================================
class PruebasContextProcessor(TestCase):
    """datos_alumno expone las cuatro variables desde la configuración."""

    def test_las_variables_llegan_a_la_plantilla(self):
        """El contexto de cualquier pantalla incluye los datos de la alumna."""
        respuesta = self.client.get("/")

        for clave, valor in [
            ("ALUMNO_NOMBRE", settings.ALUMNO_NOMBRE),
            ("ALUMNO_SECCION", settings.ALUMNO_SECCION),
            ("ALUMNO_ANIO", settings.ALUMNO_ANIO),
            ("NOMBRE_COMERCIAL", settings.NOMBRE_COMERCIAL),
        ]:
            with self.subTest(clave=clave):
                self.assertEqual(respuesta.context[clave], valor)

    def test_la_seccion_activa_se_calcula_desde_la_ruta(self):
        """El menú marca como activa la sección correspondiente."""
        casos = {"/": "inicio", "/catalogo/": "catalogo", "/panel/": "panel"}

        for ruta, esperado in casos.items():
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.context["SECCION_ACTUAL"], esperado)


# ============================================================
# BLOQUE 9 — NINGUNA PANTALLA FILTRA CÓDIGO DE PLANTILLA
# Responsabilidad: garantizar que lo que llega al navegador sea
# interfaz limpia, sin rastro de código, comentarios ni variables
# sin renderizar.
#
# Por qué existe esta prueba: Django solo admite los comentarios
# {# ... #} en UNA línea. Un comentario de varias líneas NO se
# descarta: el lexer no lo reconoce como token y lo imprime tal
# cual en la página. El proyecto tenía 31 comentarios de bloque de
# varias líneas y se veían como texto en el navegador. Se
# convirtieron a {% comment %} ... {% endcomment %}, que sí admite
# varias líneas, y esta prueba impide que el problema vuelva.
#
# La lección de método: las pruebas anteriores usaban assertContains,
# que solo comprueba que algo ESTÉ presente. Nunca detectaría texto
# sobrante. Esta prueba comprueba lo contrario: que ciertos textos
# NO aparezcan.
# ============================================================
class PruebasSinFugasDePlantilla(BaseSitio):
    """Ninguna pantalla debe mostrar código de plantilla ni texto técnico."""

    # Marcas que jamás deben llegar al navegador.
    MARCAS_PROHIBIDAS = [
        "{#", "#}",          # comentarios de plantilla
        "{%", "%}",          # etiquetas de plantilla
        "{{", "}}",          # variables sin renderizar
        "BLOQUE",            # encabezados de los comentarios de bloque
        "Responsabilidad:",  # primera línea de esos comentarios
        "====",              # separador de los bloques
    ]

    def pantallas(self):
        """Todas las pantallas HTML del sitio, incluidos los formularios."""
        return [
            # --- Públicas ---
            "/",
            "/catalogo/",
            f"/catalogo/{self.producto.id}/",
            "/documentacion/",
            "/redireccion/",
            # --- Panel ---
            "/panel/",
            # --- CRUD de categorías ---
            "/panel/categorias/",
            "/panel/categorias/nueva/",
            f"/panel/categorias/{self.categoria.id}/",
            f"/panel/categorias/{self.categoria.id}/editar/",
            f"/panel/categorias/{self.categoria.id}/desactivar/",
            # --- CRUD de marcas ---
            "/panel/marcas/",
            "/panel/marcas/nueva/",
            f"/panel/marcas/{self.marca.id}/",
            f"/panel/marcas/{self.marca.id}/editar/",
            f"/panel/marcas/{self.marca.id}/desactivar/",
            # --- CRUD de productos ---
            "/panel/productos/",
            "/panel/productos/nuevo/",
            f"/panel/productos/{self.producto.id}/",
            f"/panel/productos/{self.producto.id}/editar/",
            f"/panel/productos/{self.producto.id}/desactivar/",
            # --- CRUD de usuarios ---
            "/panel/usuarios/",
            "/panel/usuarios/nuevo/",
            f"/panel/usuarios/{self.cliente.id}/",
            f"/panel/usuarios/{self.cliente.id}/editar/",
            f"/panel/usuarios/{self.cliente.id}/desactivar/",
            # --- Carros ---
            "/panel/carros/",
            f"/panel/carros/?usuario={self.cliente.id}",
            # --- Órdenes ---
            "/panel/ordenes/",
            f"/panel/ordenes/{self.orden.id}/",
            # --- Documentación de la API ---
            "/api/docs/",
            "/api/redoc/",
            # --- Pantallas de redirección por rutas inexistentes ---
            "/asdf",
            "/api/xyz",
            "/panel/productos/999999/",
        ]

    def _revisar(self, ruta, cuerpo):
        """Comprueba que el cuerpo no contenga ninguna marca prohibida."""
        for marca in self.MARCAS_PROHIBIDAS:
            if marca in cuerpo:
                posicion = cuerpo.find(marca)
                contexto = cuerpo[max(0, posicion - 120) : posicion + 140]
                self.fail(
                    f"La pantalla {ruta} filtra «{marca}» al navegador.\n"
                    f"Contexto:\n...{contexto}..."
                )

    def test_ninguna_pantalla_filtra_codigo_de_plantilla(self):
        """Recorre todas las pantallas y falla si alguna muestra código."""
        for ruta in self.pantallas():
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta, follow=True)

                self.assertEqual(respuesta.status_code, 200, f"Falló {ruta}")
                self._revisar(ruta, respuesta.content.decode("utf-8", "replace"))

    def test_la_browsable_api_de_drf_no_filtra_codigo(self):
        """La API navegable de DRF usa una plantilla propia: también se revisa."""
        respuesta = self.client.get("/api/productos/", HTTP_ACCEPT="text/html")

        self.assertEqual(respuesta.status_code, 200)
        self._revisar("/api/productos/ (Browsable API)", respuesta.content.decode("utf-8", "replace"))

    def test_las_plantillas_no_tienen_comentarios_multilinea(self):
        """Ninguna plantilla debe usar {# #} en varias líneas: Django lo imprime."""
        import glob
        import io
        import re

        patron = re.compile(r"\{#(.*?)#\}", re.DOTALL)
        culpables = []

        for ruta in sorted(glob.glob("templates/**/*.html", recursive=True)):
            contenido = io.open(ruta, encoding="utf-8").read()
            for coincidencia in patron.finditer(contenido):
                if "\n" in coincidencia.group(0):
                    culpables.append(ruta)
                    break

        self.assertEqual(
            culpables,
            [],
            "Estas plantillas usan {# #} en varias líneas, que Django imprime "
            "como texto. Use {% comment %} ... {% endcomment %}: " + ", ".join(culpables),
        )


# ============================================================
# BLOQUE 10 — ARCHIVOS ESTÁTICOS INEXISTENTES
# Último hueco por el que se escapaba el 404 de Django: el
# runserver de staticfiles atiende las direcciones que empiezan por
# STATIC_URL antes de que Django resuelva la URL, así que el
# middleware del proyecto no las veía.
#
# La solución es el comando propio core/management/commands/
# runserver.py. Estas pruebas comprueban el comportamiento por la
# vía que sí pasa por el enrutado (el cliente de pruebas no usa el
# manejador de estáticos), y que el comando esté bien registrado.
# ============================================================
class PruebasEstaticosInexistentes(TestCase):
    """Un archivo estático ausente no muestra la página 404 de Django."""

    def test_el_comando_runserver_del_proyecto_tiene_prioridad(self):
        """El runserver que se ejecuta es el de core, no el de staticfiles."""
        from django.core.management import get_commands

        self.assertEqual(
            get_commands()["runserver"],
            "core",
            "core debe ir antes de django.contrib.staticfiles en INSTALLED_APPS.",
        )

    def test_core_va_antes_de_staticfiles_en_installed_apps(self):
        """El orden de INSTALLED_APPS es lo que da esa prioridad."""
        aplicaciones = list(settings.INSTALLED_APPS)
        posicion_core = next(i for i, a in enumerate(aplicaciones) if a.startswith("core"))
        posicion_static = aplicaciones.index("django.contrib.staticfiles")

        self.assertLess(posicion_core, posicion_static)

    def test_el_manejador_propio_devuelve_la_pantalla_de_redireccion(self):
        """Ante un archivo ausente, el manejador responde con la pantalla del sitio."""
        from django.test import RequestFactory

        from core.management.commands.runserver import ManejadorEstaticosConRedireccion

        manejador = ManejadorEstaticosConRedireccion(application=None)
        peticion = RequestFactory().get("/static/noexiste.css")

        respuesta = manejador.get_response(peticion)

        self.assertEqual(respuesta.status_code, 200)
        contenido = respuesta.content.decode("utf-8", "replace")
        self.assertIn("La página que buscas no existe", contenido)
        self.assertNotIn("{%", contenido)

    def test_el_manejador_propio_sigue_sirviendo_los_archivos_reales(self):
        """Un archivo que existe se entrega tal cual, no como pantalla HTML."""
        from django.test import RequestFactory

        from core.management.commands.runserver import ManejadorEstaticosConRedireccion

        manejador = ManejadorEstaticosConRedireccion(application=None)
        peticion = RequestFactory().get("/static/css/tema.css")

        respuesta = manejador.get_response(peticion)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("css", respuesta.headers.get("Content-Type", ""))

    def test_media_inexistente_no_muestra_404(self):
        """Una dirección de media ausente llega al middleware y muestra el aviso."""
        respuesta = self.client.get("/media/nada.jpg", follow=True)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "La página que buscas no existe")

    def test_una_ruta_con_extension_no_intenta_la_barra_final(self):
        """Evita el bucle /static/x.css -> /static/x.css/ -> ..."""
        respuesta = self.client.get("/static/noexiste.css", follow=False)

        self.assertNotEqual(
            respuesta.status_code, 302,
            "Una ruta con extensión de archivo no debe redirigir agregando barra.",
        )


# ============================================================
# BLOQUE 11 — CONFIGURACIÓN DEL PROYECTO
# Comprueba los ajustes que la pauta exige explícitamente.
# ============================================================
class PruebasConfiguracion(TestCase):
    """La configuración cumple los requisitos de la pauta."""

    def test_el_motor_de_base_de_datos_es_postgresql(self):
        """No se usa SQLite en ninguna circunstancia."""
        motor = settings.DATABASES["default"]["ENGINE"]

        self.assertEqual(motor, "django.db.backends.postgresql")
        self.assertNotIn("sqlite", motor)

    def test_configuracion_regional_chilena(self):
        """Idioma, zona horaria y uso de zona horaria."""
        self.assertEqual(settings.LANGUAGE_CODE, "es-cl")
        self.assertEqual(settings.TIME_ZONE, "America/Santiago")
        self.assertTrue(settings.USE_TZ)

    def test_modelo_de_usuario_y_clave_automatica(self):
        """AUTH_USER_MODEL y DEFAULT_AUTO_FIELD son los exigidos."""
        self.assertEqual(settings.AUTH_USER_MODEL, "usuarios.Usuario")
        self.assertEqual(settings.DEFAULT_AUTO_FIELD, "django.db.models.BigAutoField")

    def test_configuracion_de_jwt(self):
        """Los tiempos de vida y la rotación con lista negra."""
        jwt = settings.SIMPLE_JWT

        self.assertEqual(jwt["ACCESS_TOKEN_LIFETIME"].total_seconds(), 30 * 60)
        self.assertEqual(jwt["REFRESH_TOKEN_LIFETIME"].days, 1)
        self.assertTrue(jwt["ROTATE_REFRESH_TOKENS"])
        self.assertTrue(jwt["BLACKLIST_AFTER_ROTATION"])
        self.assertTrue(jwt["UPDATE_LAST_LOGIN"])
        self.assertEqual(jwt["AUTH_HEADER_TYPES"], ("Bearer",))

    def test_configuracion_de_drf(self):
        """Paginación, filtros, esquema y manejador de excepciones."""
        drf = settings.REST_FRAMEWORK

        self.assertEqual(drf["PAGE_SIZE"], 10)
        self.assertEqual(
            drf["DEFAULT_SCHEMA_CLASS"], "drf_spectacular.openapi.AutoSchema"
        )
        self.assertEqual(
            drf["EXCEPTION_HANDLER"], "core.excepciones.manejador_excepciones_api"
        )
        self.assertIn(
            "django_filters.rest_framework.DjangoFilterBackend",
            drf["DEFAULT_FILTER_BACKENDS"],
        )
        self.assertEqual(
            drf["DEFAULT_PERMISSION_CLASSES"],
            ("rest_framework.permissions.IsAuthenticated",),
        )

    def test_la_lista_negra_de_tokens_esta_instalada(self):
        """La app token_blacklist permite invalidar refresh tokens."""
        self.assertIn("rest_framework_simplejwt.token_blacklist", settings.INSTALLED_APPS)

    def test_el_middleware_de_redireccion_esta_registrado(self):
        """La tercera capa de protección de rutas está activa."""
        self.assertIn(
            "core.middleware.RedireccionNoEncontradaMiddleware", settings.MIDDLEWARE
        )

    def test_los_context_processors_propios_estan_registrados(self):
        """datos_alumno y navegacion llegan a todas las plantillas."""
        procesadores = settings.TEMPLATES[0]["OPTIONS"]["context_processors"]

        self.assertIn("core.context_processors.datos_alumno", procesadores)
        self.assertIn("core.context_processors.navegacion", procesadores)

    def test_se_usa_el_ajuste_moderno_storages(self):
        """STORAGES reemplaza a los ajustes obsoletos de almacenamiento."""
        self.assertIn("default", settings.STORAGES)
        self.assertIn("staticfiles", settings.STORAGES)
        self.assertFalse(hasattr(settings, "DEFAULT_FILE_STORAGE"))
        self.assertFalse(hasattr(settings, "STATICFILES_STORAGE"))
