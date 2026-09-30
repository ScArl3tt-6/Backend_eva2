# ============================================================
# usuarios/tests.py — PRUEBAS DE AUTENTICACIÓN Y PERMISOS
# Responsabilidad: comprobar que el login JWT entrega los tokens con
# el claim de rol, que la matriz de permisos de la pauta se cumple
# exactamente y que el "eliminar" de un usuario es una baja lógica.
#
# Estas pruebas cubren los criterios de la rúbrica sobre JWT, claims
# y permisos por rol.
# ============================================================

import jwt
from django.conf import settings
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from catalogo.models import Categoria, Marca, Producto
from usuarios.models import Rol, Usuario


# ============================================================
# BLOQUE 1 — APOYO COMÚN A LAS PRUEBAS
# Crea un administrador, un cliente y un producto mínimo, y ofrece
# un método para autenticarse por la API como cualquiera de ellos.
# Las contraseñas son deliberadamente distintas del nombre de
# usuario, porque el validador de similitud de Django rechazaría
# una contraseña demasiado parecida al username.
# ============================================================
class BaseAutenticacion(APITestCase):
    """Escenario base con usuarios de ambos roles y un producto."""

    CLAVE_ADMIN = "Llave.Segura.2026"
    CLAVE_CLIENTE = "Compra.Segura.2026"

    @classmethod
    def setUpTestData(cls):
        """Crea los usuarios y el catálogo mínimo una sola vez por clase."""
        cls.administrador = Usuario.objects.create_user(
            username="admin_prueba",
            email="admin_prueba@hardpointpc.cl",
            password=cls.CLAVE_ADMIN,
            rol=Rol.ADMINISTRADOR,
            first_name="Ada",
            last_name="Gestora",
        )
        cls.cliente = Usuario.objects.create_user(
            username="compra_prueba",
            email="compra_prueba@hardpointpc.cl",
            password=cls.CLAVE_CLIENTE,
            rol=Rol.CLIENTE,
            first_name="Clara",
            last_name="Compradora",
        )

        cls.categoria = Categoria.objects.create(nombre="Procesadores", icono="bi-cpu")
        cls.marca = Marca.objects.create(nombre="Intel", pais_origen="Estados Unidos")
        cls.producto = Producto.objects.create(
            sku="CPU-PRUEBA-01",
            nombre="Procesador de prueba",
            categoria=cls.categoria,
            marca=cls.marca,
            precio=199990,
            stock=10,
        )

    def obtener_tokens(self, username, password):
        """Inicia sesión por la API y devuelve el cuerpo de la respuesta."""
        respuesta = self.client.post(
            "/api/auth/login/",
            {"username": username, "password": password},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK, respuesta.data)
        return respuesta.data

    def autenticar(self, username, password):
        """Deja el cliente de pruebas autenticado con el token Bearer."""
        datos = self.obtener_tokens(username, password)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {datos['access']}")
        return datos

    def cerrar_sesion(self):
        """Quita el encabezado de autenticación del cliente de pruebas."""
        self.client.credentials()


# ============================================================
# BLOQUE 2 — LOGIN Y CLAIMS DEL TOKEN
# Criterio evaluado: el login devuelve access y refresh, y el token
# decodificado contiene el claim rol.
# ============================================================
class PruebasLoginJWT(BaseAutenticacion):
    """El login entrega ambos tokens y el rol viaja dentro del JWT."""

    def test_login_devuelve_access_y_refresh(self):
        """La respuesta del login incluye los dos tokens y los datos del usuario."""
        datos = self.obtener_tokens("compra_prueba", self.CLAVE_CLIENTE)

        self.assertIn("access", datos)
        self.assertIn("refresh", datos)
        self.assertEqual(datos["rol"], Rol.CLIENTE)
        self.assertEqual(datos["usuario"]["username"], "compra_prueba")
        self.assertFalse(datos["usuario"]["es_administrador"])

    def test_token_decodificado_contiene_el_claim_rol(self):
        """El access token lleva los claims rol, username, email y nombre completo."""
        datos = self.obtener_tokens("admin_prueba", self.CLAVE_ADMIN)

        contenido = jwt.decode(
            datos["access"],
            settings.SECRET_KEY,
            algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
        )

        self.assertEqual(contenido["rol"], Rol.ADMINISTRADOR)
        self.assertEqual(contenido["username"], "admin_prueba")
        self.assertEqual(contenido["email"], "admin_prueba@hardpointpc.cl")
        self.assertEqual(contenido["nombre_completo"], "Ada Gestora")

    def test_refresh_token_tambien_lleva_el_rol(self):
        """El claim viaja también en el refresh, porque el access se deriva de él."""
        datos = self.obtener_tokens("compra_prueba", self.CLAVE_CLIENTE)

        contenido = jwt.decode(
            datos["refresh"],
            settings.SECRET_KEY,
            algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
        )
        self.assertEqual(contenido["rol"], Rol.CLIENTE)

    def test_credenciales_incorrectas_responden_401(self):
        """Una contraseña equivocada no entrega token."""
        respuesta = self.client.post(
            "/api/auth/login/",
            {"username": "compra_prueba", "password": "clave-equivocada"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_perfil_expone_los_claims_recibidos(self):
        """GET /api/auth/perfil/ devuelve el contenido del token usado."""
        self.autenticar("admin_prueba", self.CLAVE_ADMIN)

        respuesta = self.client.get("/api/auth/perfil/")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["rol_en_el_token"], Rol.ADMINISTRADOR)
        self.assertEqual(respuesta.data["claims_del_token"]["rol"], Rol.ADMINISTRADOR)

    def test_refrescar_el_token_entrega_un_access_nuevo(self):
        """El endpoint de refresco devuelve un access válido."""
        datos = self.obtener_tokens("compra_prueba", self.CLAVE_CLIENTE)

        respuesta = self.client.post(
            "/api/auth/refresh/", {"refresh": datos["refresh"]}, format="json"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertIn("access", respuesta.data)


# ============================================================
# BLOQUE 3 — REGISTRO PÚBLICO
# El rol no se puede elegir desde fuera: siempre queda CLIENTE.
# ============================================================
class PruebasRegistro(BaseAutenticacion):
    """El registro público crea clientes y nunca administradores."""

    def test_registro_crea_un_cliente(self):
        """Una cuenta nueva queda con rol CLIENTE y con su carro creado."""
        respuesta = self.client.post(
            "/api/auth/registro/",
            {
                "username": "persona_nueva",
                "email": "persona_nueva@hardpointpc.cl",
                "password": "Ingreso.Fuerte.2026",
                "password2": "Ingreso.Fuerte.2026",
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED, respuesta.data)

        usuario = Usuario.objects.get(username="persona_nueva")
        self.assertEqual(usuario.rol, Rol.CLIENTE)
        self.assertFalse(usuario.is_staff)
        self.assertTrue(hasattr(usuario, "carro"), "La señal debe crear el carro del cliente.")

    def test_el_rol_enviado_en_el_json_se_ignora(self):
        """Aunque el JSON pida ser administrador, la cuenta queda como cliente."""
        respuesta = self.client.post(
            "/api/auth/registro/",
            {
                "username": "intruso",
                "email": "intruso@hardpointpc.cl",
                "password": "Ingreso.Fuerte.2026",
                "password2": "Ingreso.Fuerte.2026",
                "rol": Rol.ADMINISTRADOR,
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Usuario.objects.get(username="intruso").rol, Rol.CLIENTE)

    def test_contrasenas_distintas_se_rechazan(self):
        """Si las dos contraseñas no coinciden, no se crea la cuenta."""
        respuesta = self.client.post(
            "/api/auth/registro/",
            {
                "username": "descuidada",
                "email": "descuidada@hardpointpc.cl",
                "password": "Ingreso.Fuerte.2026",
                "password2": "Otra.Clave.2026",
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Usuario.objects.filter(username="descuidada").exists())

    def test_correo_repetido_se_rechaza(self):
        """El correo electrónico es único en el sistema."""
        respuesta = self.client.post(
            "/api/auth/registro/",
            {
                "username": "otra_persona",
                "email": "compra_prueba@hardpointpc.cl",
                "password": "Ingreso.Fuerte.2026",
                "password2": "Ingreso.Fuerte.2026",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)


# ============================================================
# BLOQUE 4 — MATRIZ DE PERMISOS
# Criterio evaluado: anónimo lee el catálogo (200) y no puede
# escribir (401); el cliente no puede crear productos (403); el
# administrador sí puede.
# ============================================================
class PruebasMatrizDePermisos(BaseAutenticacion):
    """Comprueba la matriz de roles exigida por la pauta."""

    def _cuerpo_producto(self, sku="CPU-NUEVO-01"):
        """Datos válidos para crear un producto."""
        return {
            "sku": sku,
            "nombre": "Procesador creado en la prueba",
            "descripcion": "Producto de prueba.",
            "categoria": self.categoria.id,
            "marca": self.marca.id,
            "precio": 149990,
            "stock": 5,
        }

    def test_anonimo_puede_leer_el_catalogo(self):
        """PÚBLICO: GET /api/productos/ y GET /api/categorias/ responden 200."""
        self.assertEqual(self.client.get("/api/productos/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/categorias/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/marcas/").status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.get(f"/api/productos/{self.producto.id}/").status_code,
            status.HTTP_200_OK,
        )

    def test_anonimo_no_puede_escribir_en_el_catalogo(self):
        """Sin token, cualquier escritura responde 401."""
        for metodo, ruta in [
            ("post", "/api/productos/"),
            ("post", "/api/categorias/"),
            ("post", "/api/marcas/"),
        ]:
            with self.subTest(ruta=ruta):
                respuesta = getattr(self.client, metodo)(ruta, self._cuerpo_producto(), format="json")
                self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

        for metodo in ["put", "patch", "delete"]:
            with self.subTest(metodo=metodo):
                respuesta = getattr(self.client, metodo)(
                    f"/api/productos/{self.producto.id}/", {}, format="json"
                )
                self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cliente_no_puede_crear_productos(self):
        """CLIENTE: la escritura del catálogo responde 403."""
        self.autenticar("compra_prueba", self.CLAVE_CLIENTE)

        respuesta = self.client.post("/api/productos/", self._cuerpo_producto(), format="json")

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Producto.objects.filter(sku="CPU-NUEVO-01").exists())

    def test_cliente_no_puede_dar_de_baja_productos(self):
        """CLIENTE: DELETE sobre un producto responde 403."""
        self.autenticar("compra_prueba", self.CLAVE_CLIENTE)

        respuesta = self.client.delete(f"/api/productos/{self.producto.id}/")

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        self.producto.refresh_from_db()
        self.assertTrue(self.producto.activo)

    def test_cliente_no_puede_listar_usuarios(self):
        """CLIENTE: la administración de usuarios responde 403."""
        self.autenticar("compra_prueba", self.CLAVE_CLIENTE)
        self.assertEqual(
            self.client.get("/api/usuarios/").status_code, status.HTTP_403_FORBIDDEN
        )

    def test_administrador_puede_crear_productos(self):
        """ADMINISTRADOR: POST /api/productos/ responde 201."""
        self.autenticar("admin_prueba", self.CLAVE_ADMIN)

        respuesta = self.client.post("/api/productos/", self._cuerpo_producto(), format="json")

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED, respuesta.data)
        self.assertTrue(Producto.objects.filter(sku="CPU-NUEVO-01").exists())

    def test_administrador_puede_editar_y_dar_de_baja(self):
        """ADMINISTRADOR: PATCH y DELETE funcionan sobre el catálogo."""
        self.autenticar("admin_prueba", self.CLAVE_ADMIN)

        respuesta = self.client.patch(
            f"/api/productos/{self.producto.id}/", {"precio": 175000}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK, respuesta.data)

        respuesta = self.client.delete(f"/api/productos/{self.producto.id}/")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_administrador_no_tiene_carro(self):
        """El carro es exclusivo del rol CLIENTE: un administrador recibe 403."""
        self.autenticar("admin_prueba", self.CLAVE_ADMIN)
        self.assertEqual(self.client.get("/api/carro/").status_code, status.HTTP_403_FORBIDDEN)

    def test_token_de_usuario_desactivado_deja_de_servir(self):
        """Si la cuenta se da de baja, su token vigente ya no autoriza."""
        self.autenticar("admin_prueba", self.CLAVE_ADMIN)
        self.assertEqual(self.client.get("/api/usuarios/").status_code, status.HTTP_200_OK)

        self.administrador.is_active = False
        self.administrador.save()

        respuesta = self.client.get("/api/usuarios/")
        self.assertIn(
            respuesta.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

        # Se restaura para no afectar a otras pruebas de la clase.
        self.administrador.is_active = True
        self.administrador.save()


# ============================================================
# BLOQUE 5 — LOGOUT CON LISTA NEGRA
# El refresh token invalidado no puede volver a usarse.
# ============================================================
class PruebasLogout(BaseAutenticacion):
    """El logout envía el refresh token a la lista negra."""

    def test_logout_invalida_el_refresh_token(self):
        """Tras el logout, el refresh token deja de servir."""
        datos = self.autenticar("compra_prueba", self.CLAVE_CLIENTE)

        respuesta = self.client.post(
            "/api/auth/logout/", {"refresh": datos["refresh"]}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

        # Reintentar el refresco con el token invalidado debe fallar.
        self.cerrar_sesion()
        reintento = self.client.post(
            "/api/auth/refresh/", {"refresh": datos["refresh"]}, format="json"
        )
        self.assertEqual(reintento.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_requiere_autenticacion(self):
        """Sin token no se puede cerrar sesión."""
        respuesta = self.client.post("/api/auth/logout/", {"refresh": "cualquiera"}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)


# ============================================================
# BLOQUE 6 — CRUD DE USUARIOS CON BAJA LÓGICA
# Criterio evaluado: el "eliminar" de la API no borra filas.
# ============================================================
class PruebasCrudUsuarios(BaseAutenticacion):
    """La administración de usuarios usa baja lógica, no borrado físico."""

    def test_delete_no_borra_la_fila(self):
        """DELETE deja is_active=False y conserva el registro."""
        self.autenticar("admin_prueba", self.CLAVE_ADMIN)
        identificador = self.cliente.id

        respuesta = self.client.delete(f"/api/usuarios/{identificador}/")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertTrue(
            Usuario.objects.filter(pk=identificador).exists(),
            "La fila del usuario debe seguir en la base de datos.",
        )
        self.assertFalse(Usuario.objects.get(pk=identificador).is_active)

    def test_reactivar_vuelve_a_habilitar_la_cuenta(self):
        """El endpoint de reactivación revierte la baja lógica."""
        self.autenticar("admin_prueba", self.CLAVE_ADMIN)
        self.client.delete(f"/api/usuarios/{self.cliente.id}/")

        respuesta = self.client.post(f"/api/usuarios/{self.cliente.id}/reactivar/")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertTrue(Usuario.objects.get(pk=self.cliente.id).is_active)

    def test_administrador_crea_usuarios_eligiendo_el_rol(self):
        """Desde la administración sí se puede crear otro administrador."""
        self.autenticar("admin_prueba", self.CLAVE_ADMIN)

        respuesta = self.client.post(
            "/api/usuarios/",
            {
                "username": "segundo_admin",
                "email": "segundo_admin@hardpointpc.cl",
                "rol": Rol.ADMINISTRADOR,
                "password": "Gestion.Total.2026",
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED, respuesta.data)
        creado = Usuario.objects.get(username="segundo_admin")
        self.assertEqual(creado.rol, Rol.ADMINISTRADOR)
        self.assertTrue(creado.is_staff, "El rol ADMINISTRADOR sincroniza is_staff.")
        self.assertTrue(creado.check_password("Gestion.Total.2026"))

    def test_administrador_ve_el_carro_de_un_cliente(self):
        """GET /api/usuarios/{id}/carro/ devuelve el carro persistido."""
        self.autenticar("admin_prueba", self.CLAVE_ADMIN)

        respuesta = self.client.get(f"/api/usuarios/{self.cliente.id}/carro/")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["usuario_username"], "compra_prueba")


# ============================================================
# BLOQUE 7 — MODELO USUARIO
# Comprueba la sincronización de is_staff con el rol, que es la
# regla declarada en Usuario.save().
# ============================================================
class PruebasModeloUsuario(TestCase):
    """El campo is_staff se mantiene alineado con el rol."""

    def test_administrador_queda_como_staff(self):
        """Crear un administrador deja is_staff en True."""
        usuario = Usuario.objects.create_user(
            username="gestor", email="gestor@hardpointpc.cl",
            password="Clave.Larga.2026", rol=Rol.ADMINISTRADOR,
        )
        self.assertTrue(usuario.is_staff)
        self.assertTrue(usuario.es_administrador)

    def test_cliente_no_es_staff(self):
        """Crear un cliente deja is_staff en False."""
        usuario = Usuario.objects.create_user(
            username="compradora", email="compradora@hardpointpc.cl",
            password="Clave.Larga.2026", rol=Rol.CLIENTE,
        )
        self.assertFalse(usuario.is_staff)
        self.assertTrue(usuario.es_cliente)

    def test_cambiar_el_rol_actualiza_is_staff(self):
        """Ascender a un cliente a administrador lo convierte en staff."""
        usuario = Usuario.objects.create_user(
            username="ascendida", email="ascendida@hardpointpc.cl",
            password="Clave.Larga.2026", rol=Rol.CLIENTE,
        )
        self.assertFalse(usuario.is_staff)

        usuario.rol = Rol.ADMINISTRADOR
        usuario.save()

        usuario.refresh_from_db()
        self.assertTrue(usuario.is_staff)

    def test_la_senal_crea_el_carro_de_cada_cliente(self):
        """Todo cliente nace con su carro; un administrador no."""
        cliente = Usuario.objects.create_user(
            username="con_carro", email="con_carro@hardpointpc.cl",
            password="Clave.Larga.2026", rol=Rol.CLIENTE,
        )
        administrador = Usuario.objects.create_user(
            username="sin_carro", email="sin_carro@hardpointpc.cl",
            password="Clave.Larga.2026", rol=Rol.ADMINISTRADOR,
        )

        self.assertTrue(hasattr(cliente, "carro"))
        self.assertFalse(hasattr(administrador, "carro"))
