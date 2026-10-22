# ============================================================
# settings.py — CONFIGURACIÓN CENTRAL DEL PROYECTO
# Proyecto: HardPoint PC — E-commerce de componentes informáticos
# Alumna: Genesis Quezada Sanzana — Sección IEC-C4-N2 — 2026
#
# Responsabilidad: reunir en un solo lugar la configuración de
# Django, DRF, JWT, OpenAPI, PostgreSQL y localización chilena.
# Ningún dato sensible ni dato de la alumna está escrito a mano:
# todo se lee del archivo .env con python-decouple.
# ============================================================

import sys
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config
from django.contrib.messages import constants as mensajes

# ============================================================
# BLOQUE 1 — RUTAS BASE
# BASE_DIR apunta a la carpeta que contiene manage.py; todas las
# rutas del proyecto se construyen a partir de ella para que el
# proyecto funcione sin importar dónde se clone el repositorio.
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent


# ============================================================
# BLOQUE 2 — IDENTIFICACIÓN DE LA ALUMNA Y NOMBRE COMERCIAL
# Estos valores viven en .env y llegan a todas las plantillas a
# través de core.context_processors.datos_alumno. Se exigen en el
# footer de cada pantalla y en la documentación OpenAPI.
# ============================================================
ALUMNO_NOMBRE = config("ALUMNO_NOMBRE", default="Genesis Quezada Sanzana")
ALUMNO_SECCION = config("ALUMNO_SECCION", default="IEC-C4-N2")
ALUMNO_ANIO = config("ALUMNO_ANIO", default="2026")
NOMBRE_COMERCIAL = config("NOMBRE_COMERCIAL", default="HardPoint PC")


# ============================================================
# BLOQUE 3 — SEGURIDAD Y ENTORNO
# SECRET_KEY y DEBUG se leen del .env para no exponer secretos en
# el repositorio. ALLOWED_HOSTS acepta una lista separada por comas.
# ============================================================
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1,[::1],testserver",
    cast=Csv(),
)

# ============================================================
# BLOQUE 3-B — HTTPS DETRÁS DE UN PROXY (NGINX + LET'S ENCRYPT)
# En local DETRAS_DE_PROXY_HTTPS queda en False y nada cambia: el
# sitio sigue funcionando por HTTP, sin cookies "Secure" ni HSTS,
# igual que hoy.
#
# En el servidor (Nginx con "include proxy_params", que ya manda
# X-Forwarded-Proto) se activa esta variable. Sin ella, Django no
# tenía forma de saber que la conexión real del navegador era HTTPS
# (Gunicorn la recibe por HTTP desde Nginx) y los formularios
# fallaban con 403 CSRF: la cookie CSRF se pedía "Secure" para una
# petición que Django creía insegura.
# ============================================================
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())
DETRAS_DE_PROXY_HTTPS = config("DETRAS_DE_PROXY_HTTPS", default=False, cast=bool)

if DETRAS_DE_PROXY_HTTPS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Bajo a propósito y sin "preload": alcanza para la defensa sin
    # arriesgar dejar el dominio inaccesible por HSTS si algo falla.
    SECURE_HSTS_SECONDS = 3600


# ============================================================
# BLOQUE 4 — APLICACIONES INSTALADAS
# Se separan las de Django, las de terceros y las propias del
# negocio para que la arquitectura quede evidente en la defensa.
# token_blacklist es obligatoria para invalidar refresh tokens en
# el logout y tras la rotación.
# ============================================================
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

TERCEROS_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
]

APPS_NEGOCIO = [
    "usuarios.apps.UsuariosConfig",
    "catalogo.apps.CatalogoConfig",
    "carro.apps.CarroConfig",
    "ordenes.apps.OrdenesConfig",
    "pagos.apps.PagosConfig",
]

# El orden de esta lista no es decorativo: "core" va PRIMERO, antes de
# django.contrib.staticfiles, para que el comando runserver del proyecto
# (core/management/commands/runserver.py) tenga prioridad sobre el de
# staticfiles. Django resuelve los comandos recorriendo INSTALLED_APPS al
# revés, así que gana la aplicación que aparece primero.
#
# Ese runserver propio es el que evita que un archivo estático inexistente
# —por ejemplo /static/noexiste.css— muestre la página 404 de Django.
INSTALLED_APPS = ["core.apps.CoreConfig"] + DJANGO_APPS + TERCEROS_APPS + APPS_NEGOCIO

# Se conserva el nombre anterior por si alguna herramienta lo consulta.
APPS_PROPIAS = ["core.apps.CoreConfig"] + APPS_NEGOCIO


# ============================================================
# BLOQUE 5 — MIDDLEWARE
# RedireccionNoEncontradaMiddleware es propio del proyecto: captura
# cualquier Http404 o respuesta 404 y devuelve la pantalla de
# redirección, de modo que ninguna dirección muestre el 404 de
# Django (requisito crítico de la pauta). Se ubica al final para
# ver la respuesta ya construida por las vistas.
# ============================================================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.RedireccionNoEncontradaMiddleware",
]

ROOT_URLCONF = "tienda_hardware.urls"


# ============================================================
# BLOQUE 6 — PLANTILLAS
# DIRS incluye la carpeta templates/ del proyecto, que también
# sobrescribe las plantillas de la Browsable API de DRF y de
# Swagger UI para que muestren el footer con los datos de la alumna.
# ============================================================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.datos_alumno",
                "core.context_processors.navegacion",
            ],
        },
    },
]

WSGI_APPLICATION = "tienda_hardware.wsgi.application"
ASGI_APPLICATION = "tienda_hardware.asgi.application"


# ============================================================
# BLOQUE 7 — BASE DE DATOS POSTGRESQL
# Motor obligatorio django.db.backends.postgresql (la pauta
# penaliza SQLite con 0 puntos). Los parámetros de conexión se
# leen del .env, de modo que cambiar de servidor no exige tocar
# el código.
# ============================================================
DATABASES = {
    "default": {
        "ENGINE": config("DB_ENGINE", default="django.db.backends.postgresql"),
        "NAME": config("DB_NAME", default="tienda_hardware_db"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "ATOMIC_REQUESTS": False,
        "TEST": {"NAME": "test_" + config("DB_NAME", default="tienda_hardware_db")},
    }
}


# ============================================================
# BLOQUE 8 — MODELO DE USUARIO PERSONALIZADO
# Se reemplaza el usuario de Django por usuarios.Usuario, que
# agrega el campo "rol" (CLIENTE / ADMINISTRADOR) usado por los
# permisos y por los claims del token JWT.
# ============================================================
AUTH_USER_MODEL = "usuarios.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ============================================================
# BLOQUE 8-B — SESIÓN DEL PANEL DE ADMINISTRACIÓN
# El panel (/panel/...) se puede ver sin iniciar sesión; lo que
# exige login es EDITAR algo (ver core.utilidades.
# panel_solo_lectura_o_administrador). Es una sesión de Django
# (cookies), independiente del JWT que usa la API REST.
# ============================================================
LOGIN_URL = "core:panel-login"
LOGIN_REDIRECT_URL = "/panel/"
LOGOUT_REDIRECT_URL = "/"

# ============================================================
# BLOQUE 8-C — TRANSBANK WEBPAY PLUS (AMBIENTE DE INTEGRACIÓN)
# TRANSBANK_AMBIENTE acepta "integracion" (por omisión, sin dinero
# real) o "produccion". Los valores por omisión de código de
# comercio y API Key NO son un secreto propio: son las constantes
# públicas que el propio SDK de Transbank publica para el ambiente
# de integración (IntegrationCommerceCodes.WEBPAY_PLUS e
# IntegrationApiKeys.WEBPAY), documentadas también en la web oficial
# de Transbank. En producción estas tres variables SÍ deben venir
# del .env del servidor, con las credenciales reales del comercio.
# ============================================================
from transbank.common.integration_api_keys import IntegrationApiKeys
from transbank.common.integration_commerce_codes import IntegrationCommerceCodes

TRANSBANK_AMBIENTE = config("TRANSBANK_AMBIENTE", default="integracion")
TRANSBANK_CODIGO_COMERCIO = config(
    "TRANSBANK_CODIGO_COMERCIO", default=IntegrationCommerceCodes.WEBPAY_PLUS
)
TRANSBANK_API_KEY = config("TRANSBANK_API_KEY", default=IntegrationApiKeys.WEBPAY)


# ============================================================
# BLOQUE 9 — DJANGO REST FRAMEWORK
# Autenticación JWT por defecto, permiso restrictivo por defecto
# (cada endpoint público declara AllowAny explícitamente),
# filtros, paginación, esquema OpenAPI 3 de drf-spectacular y un
# manejador de excepciones propio que uniforma los errores en
# español como {"error": true, "mensaje": ..., "detalle": ...}.
# ============================================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "core.excepciones.manejador_excepciones_api",
    "DATETIME_FORMAT": "%d-%m-%Y %H:%M",
    # Títulos en español para la API navegable de DRF. Sin esto, DRF los
    # deriva del nombre de la clase y muestra textos como «Producto List».
    "VIEW_NAME_FUNCTION": "core.nombres.nombre_de_vista",
}


# ============================================================
# BLOQUE 10 — JWT (djangorestframework-simplejwt)
# Access de 30 minutos y refresh de 1 día. La rotación con lista
# negra permite que el logout invalide de verdad el refresh token.
# UPDATE_LAST_LOGIN deja registro de la última entrada.
# ============================================================
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_TYPE_CLAIM": "token_type",
}


# ============================================================
# BLOQUE 11 — DOCUMENTACIÓN OpenAPI 3 (drf-spectacular)
# La descripción incluye los datos de la alumna, el procedimiento
# de autenticación, la matriz de roles exigida por la pauta y las
# credenciales de prueba, para que el evaluador pueda probar la
# API completa desde /api/docs/ sin leer el README.
# ============================================================
DESCRIPCION_API = f"""
API REST del e-commerce **{NOMBRE_COMERCIAL}**, especializado en componentes
informáticos (procesadores, tarjetas de video, memorias RAM, placas madre,
almacenamiento y fuentes de poder).

**Alumna:** {ALUMNO_NOMBRE} · **Sección:** {ALUMNO_SECCION} · **Año:** {ALUMNO_ANIO}

---

## Cómo autenticarse

1. Ejecute `POST /api/auth/login/` con un usuario y contraseña de prueba.
2. Copie el valor de `access` que devuelve la respuesta.
3. Pulse el botón **Authorize** (arriba a la derecha) y pegue el token.
   El esquema es *Bearer*, así que basta con pegar el token: Swagger agrega
   por sí mismo el encabezado `Authorization: Bearer <token>`.
4. El token incluye el claim `rol`, que es el que evalúan los permisos.

## Matriz de roles y permisos

| Rol | Endpoints permitidos |
|---|---|
| **PÚBLICO** | `GET /api/productos/`, `GET /api/categorias/` |
| **CLIENTE** | `GET/POST/DELETE /api/carro/`, `POST /api/ordenes/checkout/`, `GET /api/mis-ordenes/` |
| **ADMINISTRADOR** | `POST/PUT/DELETE /api/productos/`, `PATCH /api/ordenes/{{id}}/estado/` |

Sin token la respuesta es **401**; con token de un rol incorrecto la respuesta
es **403**.

## Credenciales de prueba

Se crean con `python manage.py seed_data`.

| Usuario | Contraseña | Rol |
|---|---|---|
| `admin_ti` | `Admin.2026` | Administrador de TI |
| `cliente1` | `Cliente.2026` | Cliente |
| `cliente2` | `Cliente.2026` | Cliente |
| `cliente3` | `Cliente.2026` | Cliente |

## Flujo de negocio

`carro` → `checkout` (congela precios, **no** toca el stock) → `pagar`
(descuenta el stock de forma atómica) → `entregado` o `cancelado`
(la cancelación de una orden pagada **repone** el stock).

Si al pagar el stock no alcanza, la API responde **409 Conflict** con el
detalle de cada producto faltante (cantidad pedida frente a disponible) y
la orden permanece en `PENDIENTE`.
"""

SPECTACULAR_SETTINGS = {
    "TITLE": f"{NOMBRE_COMERCIAL} — API de componentes informáticos",
    "DESCRIPTION": DESCRIPCION_API,
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "SCHEMA_PATH_PREFIX": "/api",
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "docExpansion": "list",
        "filter": True,
    },
    "SWAGGER_UI_DIST": "//cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14",
    "SWAGGER_UI_FAVICON_HREF": "/static/img/favicon.svg",
    "REDOC_DIST": "//cdn.jsdelivr.net/npm/redoc@2.1.5/bundles",
    "CONTACT": {"name": ALUMNO_NOMBRE, "email": "contacto@hardpointpc.cl"},
    "LICENSE": {"name": "Uso académico — EVA-2 Desarrollo Backend"},
    "TAGS": [
        {
            "name": "Autenticación",
            "description": "Registro, login JWT con claim de rol, refresh, logout y perfil.",
        },
        {
            "name": "Catálogo",
            "description": "Categorías, marcas y productos. Lectura pública, escritura solo del administrador.",
        },
        {
            "name": "Carro",
            "description": "Carro de compras persistente en PostgreSQL, uno por cliente.",
        },
        {
            "name": "Órdenes",
            "description": "Checkout con precios congelados, pago con descuento atómico de stock y cambios de estado.",
        },
        {
            "name": "Usuarios",
            "description": "Administración de usuarios y consulta de sus carros. Solo administrador.",
        },
        {"name": "General", "description": "Raíz de la API con el índice de endpoints."},
    ],
    "ENUM_NAME_OVERRIDES": {
        "RolEnum": "usuarios.models.Rol.choices",
        "EstadoOrdenEnum": "ordenes.models.EstadoOrden.choices",
    },
}


# ============================================================
# BLOQUE 12 — LOCALIZACIÓN CHILENA
# Español de Chile, zona horaria de Santiago y fechas con
# soporte de zona horaria (USE_TZ), como exige la pauta.
# ============================================================
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True


# ============================================================
# BLOQUE 13 — ARCHIVOS ESTÁTICOS Y ALMACENAMIENTO
# Se usa el ajuste moderno STORAGES (DEFAULT_FILE_STORAGE y
# STATICFILES_STORAGE quedaron obsoletos en Django 5).
# ============================================================
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ============================================================
# BLOQUE 14 — MENSAJES FLASH CON CLASES DE BOOTSTRAP
# Traduce los niveles de django.contrib.messages a las clases de
# alerta de Bootstrap 5, para que las vistas HTML muestren avisos
# coherentes con el diseño sin lógica extra en las plantillas.
# ============================================================
MESSAGE_TAGS = {
    mensajes.DEBUG: "secondary",
    mensajes.INFO: "info",
    mensajes.SUCCESS: "success",
    mensajes.WARNING: "warning",
    mensajes.ERROR: "danger",
}


# ============================================================
# BLOQUE 15 — AJUSTES EXCLUSIVOS DEL ENTORNO DE PRUEBAS
# Detecta si el proceso actual es "manage.py test" y, solo en ese
# caso, sustituye el algoritmo de contraseñas.
#
# Por qué: PBKDF2 (el de producción) es lento a propósito, porque
# encarece un ataque de fuerza bruta. Las pruebas, en cambio, crean
# usuarios e inician sesión decenas de veces, y ese costo domina el
# tiempo total de la suite. Al ejecutar la aplicación de verdad
# —runserver, WSGI— esta rama no se aplica y las contraseñas se
# siguen guardando con PBKDF2.
# ============================================================
EJECUTANDO_PRUEBAS = "test" in sys.argv

if EJECUTANDO_PRUEBAS:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


# ============================================================
# BLOQUE 16 — REGISTRO DE ERRORES EN CONSOLA
# Detecta si el proceso actual es "manage.py test" para aplicar los
# ajustes que solo tienen sentido durante las pruebas automatizadas.
# sirven sin errores.
# ============================================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "[{levelname}] {asctime} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "consola": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["consola"], "level": "WARNING"},
    "loggers": {
        "django.request": {
            "handlers": ["consola"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
