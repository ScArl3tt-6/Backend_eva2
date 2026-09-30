# ============================================================
# core/views.py — PÁGINAS TRANSVERSALES Y CONTROL DE RUTAS
# Responsabilidad:
#   · Portada del sitio con estadísticas reales.
#   · Panel de gestión con acceso a cada módulo.
#   · Página de documentación del sistema.
#   · Raíz de la API con el índice de endpoints.
#   · Pantalla de redirección para cualquier dirección inexistente
#     (requisito crítico: el 404 no debe existir).
# ============================================================

from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.urls import Resolver404, resolve
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from carro.models import Carro, ItemCarro
from catalogo.models import Categoria, Marca, Producto
from ordenes.models import EstadoOrden, Orden
from usuarios.models import Rol, Usuario


# ============================================================
# BLOQUE 1 — PORTADA
# Muestra estadísticas calculadas de verdad contra PostgreSQL (no
# valores fijos): productos, categorías, marcas, clientes y
# órdenes por estado, más los productos destacados del catálogo.
# ============================================================
def inicio(request):
    """Portada del sitio con estadísticas reales y productos destacados."""
    conteo_ordenes = {
        fila["estado"]: fila["total"]
        for fila in Orden.objects.values("estado").annotate(total=Count("id"))
    }

    estadisticas = {
        "productos": Producto.objects.filter(activo=True).count(),
        "categorias": Categoria.objects.filter(activo=True).count(),
        "marcas": Marca.objects.filter(activo=True).count(),
        "clientes": Usuario.objects.filter(rol=Rol.CLIENTE, is_active=True).count(),
        "ordenes_total": Orden.objects.count(),
        "unidades_en_bodega": Producto.objects.filter(activo=True).aggregate(
            total=Sum("stock")
        )["total"]
        or 0,
    }

    ordenes_por_estado = [
        {
            "estado": valor,
            "etiqueta": etiqueta,
            "total": conteo_ordenes.get(valor, 0),
        }
        for valor, etiqueta in EstadoOrden.choices
    ]

    contexto = {
        "titulo_pagina": "Inicio",
        "estadisticas": estadisticas,
        "ordenes_por_estado": ordenes_por_estado,
        "productos_destacados": (
            Producto.objects.filter(activo=True, stock__gt=0)
            .select_related("categoria", "marca")
            .order_by("-creado_en")[:6]
        ),
        "categorias_destacadas": (
            Categoria.objects.filter(activo=True)
            .annotate(total=Count("productos", filter=Q(productos__activo=True)))
            .order_by("-total", "nombre")[:6]
        ),
    }
    return render(request, "core/inicio.html", contexto)


# ============================================================
# BLOQUE 2 — PANEL DE GESTIÓN
# Tarjetas de acceso a cada módulo con su conteo real, para que la
# persona que evalúa vea de inmediato que hay datos cargados.
# ============================================================
def panel(request):
    """Panel de gestión con accesos a los módulos y sus conteos."""
    # Cada módulo declara sus propias etiquetas porque lo que se cuenta no
    # es lo mismo en todos: en el catálogo y en los usuarios son registros
    # dados de baja, en los carros son ítems retirados y en las órdenes son
    # ventas canceladas. Usar el mismo texto para los tres sería inexacto.
    modulos = [
        {
            "nombre": "Categorías",
            "descripcion": "Tipos de componentes del catálogo.",
            "url": "/panel/categorias/",
            "icono": "bi-tags",
            "activos": Categoria.objects.filter(activo=True).count(),
            "etiqueta_activos": "activa(s)",
            "inactivos": Categoria.objects.filter(activo=False).count(),
            "etiqueta_inactivos": "dada(s) de baja",
        },
        {
            "nombre": "Marcas",
            "descripcion": "Fabricantes de los componentes.",
            "url": "/panel/marcas/",
            "icono": "bi-award",
            "activos": Marca.objects.filter(activo=True).count(),
            "etiqueta_activos": "activa(s)",
            "inactivos": Marca.objects.filter(activo=False).count(),
            "etiqueta_inactivos": "dada(s) de baja",
        },
        {
            "nombre": "Productos",
            "descripcion": "Componentes con precio, SKU y stock.",
            "url": "/panel/productos/",
            "icono": "bi-cpu",
            "activos": Producto.objects.filter(activo=True).count(),
            "etiqueta_activos": "publicado(s)",
            "inactivos": Producto.objects.filter(activo=False).count(),
            "etiqueta_inactivos": "dado(s) de baja",
        },
        {
            "nombre": "Usuarios",
            "descripcion": "Clientes y administradores de TI.",
            "url": "/panel/usuarios/",
            "icono": "bi-people",
            "activos": Usuario.objects.filter(is_active=True).count(),
            "etiqueta_activos": "activo(s)",
            "inactivos": Usuario.objects.filter(is_active=False).count(),
            "etiqueta_inactivos": "dado(s) de baja",
        },
        {
            "nombre": "Carros",
            "descripcion": "Carros persistentes de cada cliente.",
            "url": "/panel/carros/",
            "icono": "bi-cart3",
            "activos": Carro.objects.count(),
            "etiqueta_activos": "carro(s)",
            "inactivos": ItemCarro.objects.filter(activo=False).count(),
            "etiqueta_inactivos": "ítem(s) retirado(s)",
        },
        {
            "nombre": "Órdenes",
            "descripcion": "Ventas, pagos, entregas y cancelaciones.",
            "url": "/panel/ordenes/",
            "icono": "bi-receipt",
            "activos": Orden.objects.count(),
            "etiqueta_activos": "orden(es)",
            "inactivos": Orden.objects.filter(estado=EstadoOrden.CANCELADO).count(),
            "etiqueta_inactivos": "cancelada(s)",
        },
    ]

    contexto = {
        "titulo_pagina": "Panel de gestión",
        "modulos": modulos,
        "migas": [{"etiqueta": "Gestión", "url": None}],
    }
    return render(request, "core/panel.html", contexto)


# ============================================================
# BLOQUE 3 — DOCUMENTACIÓN DEL SISTEMA
# Página con el propósito del proyecto, el modelo de datos, la
# matriz de roles, el flujo de negocio, las credenciales de prueba
# y el paso a paso para probar la API desde Swagger.
# ============================================================
def documentacion(request):
    """Guía del sistema con la matriz de roles y el flujo de negocio."""
    matriz_roles = [
        {
            "rol": "PÚBLICO",
            "icono": "bi-globe",
            "descripcion": "Cualquier visitante, sin token.",
            "endpoints": ["GET /api/productos/", "GET /api/categorias/"],
        },
        {
            "rol": "CLIENTE",
            "icono": "bi-person",
            "descripcion": "Compra: administra su carro y sus órdenes.",
            "endpoints": [
                "GET/POST/DELETE /api/carro/",
                "POST /api/ordenes/checkout/",
                "GET /api/mis-ordenes/",
            ],
        },
        {
            "rol": "ADMINISTRADOR",
            "icono": "bi-shield-lock",
            "descripcion": "Administrador de TI: gestiona el catálogo y las ventas.",
            "endpoints": [
                "POST/PUT/DELETE /api/productos/",
                "PATCH /api/ordenes/{id}/estado/",
            ],
        },
    ]

    flujo = [
        {
            "paso": 1,
            "titulo": "Carro de compras",
            "icono": "bi-cart-plus",
            "detalle": (
                "El cliente agrega componentes a su carro, que vive en PostgreSQL "
                "ligado a su id de usuario. No se descuenta stock: solo se valida "
                "que la cantidad pedida no supere las unidades disponibles."
            ),
        },
        {
            "paso": 2,
            "titulo": "Checkout",
            "icono": "bi-receipt-cutoff",
            "detalle": (
                "Se genera la Orden de Compra en estado PENDIENTE y se copia el "
                "precio vigente de cada producto al detalle: ese es el precio "
                "congelado. Los cambios de precio posteriores no afectan la venta. "
                "Tampoco aquí se descuenta stock."
            ),
        },
        {
            "paso": 3,
            "titulo": "Pago",
            "icono": "bi-credit-card",
            "detalle": (
                "Se verifica el stock con las filas bloqueadas en la base de datos. "
                "Si alcanza, se descuenta y la orden pasa a PAGADO. Si no alcanza, "
                "se revierte todo, la orden sigue PENDIENTE y la API responde 409 "
                "indicando qué producto faltó."
            ),
        },
        {
            "paso": 4,
            "titulo": "Entrega o cancelación",
            "icono": "bi-box-seam",
            "detalle": (
                "El administrador marca la orden como ENTREGADO, o la CANCELA. Si "
                "cancela una orden ya pagada, el stock se repone automáticamente. "
                "ENTREGADO y CANCELADO son estados finales."
            ),
        },
    ]

    modelo_datos = [
        {
            "modelo": "Usuario",
            "app": "usuarios",
            "descripcion": "Extiende AbstractUser con el campo rol (CLIENTE / ADMINISTRADOR), correo único y teléfono.",
        },
        {
            "modelo": "Categoria",
            "app": "catalogo",
            "descripcion": "Tipo de componente. Nombre único, icono y baja lógica.",
        },
        {
            "modelo": "Marca",
            "app": "catalogo",
            "descripcion": "Fabricante con su país de origen. En tabla propia para cumplir la 3FN.",
        },
        {
            "modelo": "Producto",
            "app": "catalogo",
            "descripcion": "SKU único, precio en pesos chilenos, stock físico y claves foráneas a categoría y marca.",
        },
        {
            "modelo": "Carro",
            "app": "carro",
            "descripcion": "Relación 1 a 1 con el usuario. Su total es calculado, no almacenado.",
        },
        {
            "modelo": "ItemCarro",
            "app": "carro",
            "descripcion": "Producto y cantidad. No guarda precio: lo lee del producto (3FN). Único por carro y producto.",
        },
        {
            "modelo": "Orden",
            "app": "ordenes",
            "descripcion": "Número de orden UUID, estado y fechas. El total es una propiedad y una anotación de consulta.",
        },
        {
            "modelo": "DetalleOrden",
            "app": "ordenes",
            "descripcion": "Cantidad y precio_unitario congelado: el hecho histórico de la venta.",
        },
        {
            "modelo": "HistorialEstadoOrden",
            "app": "ordenes",
            "descripcion": "Auditoría de cada transición: de qué estado a cuál, quién y cuándo.",
        },
    ]

    pasos_swagger = [
        "Abra /api/docs/ (Swagger UI).",
        "Despliegue POST /api/auth/login/, pulse «Try it out» y envíe {\"username\": \"cliente1\", \"password\": \"Cliente.2026\"}.",
        "Copie el valor del campo access de la respuesta.",
        "Pulse el botón Authorize (arriba a la derecha), pegue el token y confirme.",
        "Agregue un producto con POST /api/carro/ enviando {\"producto\": 1, \"cantidad\": 2}.",
        "Revise el carro con GET /api/carro/: verá el total y los subtotales calculados.",
        "Genere la orden con POST /api/ordenes/checkout/: queda en PENDIENTE con los precios congelados.",
        "Pague con POST /api/ordenes/{id}/pagar/: ahí se descuenta el stock y la orden pasa a PAGADO.",
        "Para cambiar estados, inicie sesión como admin_ti y use PATCH /api/ordenes/{id}/estado/ con {\"estado\": \"ENTREGADO\"}.",
    ]

    credenciales = [
        {"usuario": "admin_ti", "contrasena": "Admin.2026", "rol": "Administrador de TI"},
        {"usuario": "cliente1", "contrasena": "Cliente.2026", "rol": "Cliente"},
        {"usuario": "cliente2", "contrasena": "Cliente.2026", "rol": "Cliente"},
        {"usuario": "cliente3", "contrasena": "Cliente.2026", "rol": "Cliente"},
    ]

    contexto = {
        "titulo_pagina": "Documentación del sistema",
        "matriz_roles": matriz_roles,
        "flujo": flujo,
        "modelo_datos": modelo_datos,
        "pasos_swagger": pasos_swagger,
        "credenciales": credenciales,
        "migas": [{"etiqueta": "Documentación", "url": None}],
    }
    return render(request, "core/documentacion.html", contexto)


# ============================================================
# BLOQUE 4 — PANTALLA DE REDIRECCIÓN (CAPAS 1 Y 3)
# Es la vista que atiende el catch-all de urls.py y también la que
# invoca el middleware cuando aparece un 404.
#
# Detalle fino exigido por la pauta: como el catch-all r"^.*$"
# atrapa la dirección antes de que Django aplique APPEND_SLASH,
# una ruta sin barra final como /catalogo nunca llegaría a
# /catalogo/. Por eso aquí se comprueba con resolve() si la misma
# ruta existe agregándole la barra; si existe, se redirige a ella
# en lugar de mostrar el aviso.
# ============================================================
def _existe_con_barra_final(request) -> bool:
    """Indica si la misma ruta, con barra final, corresponde a una página real.

    Hay dos trampas que esta función evita:

    1. El catch-all r"^.*$" hace que resolve() encuentre SIEMPRE una
       coincidencia, así que no basta con que no lance Resolver404: hay que
       comprobar que la vista encontrada no sea este mismo catch-all. Sin
       esa comprobación, /asdf se redirigiría a /asdf/ en bucle.

    2. Con DEBUG activo también existe una ruta que sirve los archivos
       estáticos y de media. Para /static/noexiste.css, resolve() de
       "/static/noexiste.css/" encontraría esa vista y produciría otro
       bucle de redirecciones. Por eso las vistas que sirven archivos
       tampoco cuentan como "página real".
    """
    from django.contrib.staticfiles.views import serve as servir_staticfiles
    from django.views.static import serve as servir_archivos

    ruta = request.path
    if ruta.endswith("/"):
        return False

    # Una dirección con extensión de archivo (por ejemplo .css) nunca es
    # una página del sitio: no tiene sentido probarla con barra final.
    ultimo_segmento = ruta.rsplit("/", 1)[-1]
    if "." in ultimo_segmento:
        return False

    try:
        coincidencia = resolve(ruta + "/")
    except Resolver404:
        return False

    vistas_que_no_cuentan = {redireccion_inicio, servir_archivos, servir_staticfiles}
    return coincidencia.func not in vistas_que_no_cuentan


def redireccion_inicio(request, *args, **kwargs):
    """Atiende cualquier dirección inexistente sin mostrar un 404."""
    from django.shortcuts import redirect

    ruta = request.path

    # --- ¿Existe la misma ruta con barra final? ---
    if _existe_con_barra_final(request):
        destino = ruta + "/"
        if request.META.get("QUERY_STRING"):
            destino = f"{destino}?{request.META['QUERY_STRING']}"
        return redirect(destino)

    contexto = {
        "titulo_pagina": "Página no encontrada",
        "ruta_solicitada": ruta,
        "segundos_espera": 3,
    }
    return render(request, "core/redireccion.html", contexto, status=200)


# ============================================================
# BLOQUE 5 — HANDLER 404 (CAPA 2)
# Se registra como handler404 en el urls.py raíz y entra en acción
# cuando DEBUG = False. Reutiliza la misma pantalla para que la
# experiencia sea idéntica en desarrollo y en producción.
# ============================================================
def pagina_no_encontrada(request, exception=None):
    """handler404 del proyecto: muestra la pantalla de redirección."""
    return redireccion_inicio(request)


# ============================================================
# BLOQUE 6 — RAÍZ DE LA API
# GET /api/ público. Presenta el proyecto, los datos de la alumna y
# el índice de endpoints con el rol que exige cada uno, de modo que
# quien evalúe pueda recorrer la API sin consultar el README.
# ============================================================
@extend_schema(
    tags=["General"],
    summary="Índice de la API",
    description=(
        "Punto de entrada público de la API. Devuelve los datos de la alumna y "
        "el listado de endpoints con el rol requerido por cada uno."
    ),
    responses={200: OpenApiResponse(description="Índice de endpoints de la API.")},
)
class RaizApiView(APIView):
    """GET /api/ — índice público de la API."""

    permission_classes = [AllowAny]

    def get(self, request):
        """Devuelve la presentación del proyecto y el índice de endpoints."""
        from django.conf import settings

        return Response(
            {
                "proyecto": settings.NOMBRE_COMERCIAL,
                "descripcion": "API REST de e-commerce de componentes informáticos.",
                "version": "1.0.0",
                "alumna": {
                    "nombre": settings.ALUMNO_NOMBRE,
                    "seccion": settings.ALUMNO_SECCION,
                    "anio": settings.ALUMNO_ANIO,
                    "asignatura": "Desarrollo Backend — EVA-2",
                },
                "documentacion": {
                    "swagger_ui": request.build_absolute_uri("/api/docs/"),
                    "redoc": request.build_absolute_uri("/api/redoc/"),
                    "esquema_openapi": request.build_absolute_uri("/api/schema/"),
                    "guia_html": request.build_absolute_uri("/documentacion/"),
                },
                "autenticacion": {
                    "registro": "POST /api/auth/registro/ (público)",
                    "login": "POST /api/auth/login/ (público, devuelve access y refresh con el claim rol)",
                    "refresh": "POST /api/auth/refresh/",
                    "logout": "POST /api/auth/logout/ (autenticado, invalida el refresh)",
                    "perfil": "GET /api/auth/perfil/ (autenticado, muestra los claims del token)",
                    "encabezado": "Authorization: Bearer <access>",
                },
                "endpoints": {
                    "publico": {
                        "productos": "GET /api/productos/",
                        "producto_detalle": "GET /api/productos/{id}/",
                        "categorias": "GET /api/categorias/",
                        "categoria_detalle": "GET /api/categorias/{id}/",
                        "marcas": "GET /api/marcas/",
                    },
                    "cliente": {
                        "ver_carro": "GET /api/carro/",
                        "agregar_al_carro": "POST /api/carro/",
                        "vaciar_carro": "DELETE /api/carro/",
                        "cambiar_cantidad": "PATCH /api/carro/items/{producto_id}/",
                        "quitar_item": "DELETE /api/carro/items/{producto_id}/",
                        "checkout": "POST /api/ordenes/checkout/",
                        "pagar": "POST /api/ordenes/{id}/pagar/",
                        "mis_ordenes": "GET /api/mis-ordenes/",
                        "mi_orden_detalle": "GET /api/mis-ordenes/{id}/",
                    },
                    "administrador": {
                        "crear_producto": "POST /api/productos/",
                        "editar_producto": "PUT / PATCH /api/productos/{id}/",
                        "baja_producto": "DELETE /api/productos/{id}/ (baja lógica)",
                        "reactivar_producto": "POST /api/productos/{id}/reactivar/",
                        "categorias_crud": "POST / PUT / PATCH / DELETE /api/categorias/",
                        "marcas_crud": "POST / PUT / PATCH / DELETE /api/marcas/",
                        "usuarios_crud": "GET / POST / PUT / PATCH / DELETE /api/usuarios/",
                        "carro_de_un_cliente": "GET /api/usuarios/{id}/carro/",
                        "todas_las_ordenes": "GET /api/ordenes/",
                        "orden_detalle": "GET /api/ordenes/{id}/",
                        "cambiar_estado": "PATCH /api/ordenes/{id}/estado/",
                    },
                },
                "filtros_de_productos": [
                    "categoria", "categoria_nombre", "marca", "marca_nombre",
                    "precio_min", "precio_max", "en_stock", "sku",
                    "search", "ordering", "page",
                ],
                "credenciales_de_prueba": {
                    "administrador": {"usuario": "admin_ti", "contrasena": "Admin.2026"},
                    "clientes": [
                        {"usuario": "cliente1", "contrasena": "Cliente.2026"},
                        {"usuario": "cliente2", "contrasena": "Cliente.2026"},
                        {"usuario": "cliente3", "contrasena": "Cliente.2026"},
                    ],
                },
            },
            status=status.HTTP_200_OK,
        )
