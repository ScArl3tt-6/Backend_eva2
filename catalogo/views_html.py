# ============================================================
# catalogo/views_html.py — PANTALLAS HTML DEL CATÁLOGO
# Responsabilidad: catálogo público (listado con filtros y ficha
# del producto) y CRUD completo de categorías, marcas y productos
# en el panel de gestión.
#
# Decisiones que conviene poder explicar:
#   · Las pantallas usan el ORM y ModelForm, con mensajes flash de
#     django.contrib.messages. No tienen login: la seguridad por
#     roles vive en la API JWT, tal como pide el enunciado.
#   · El catálogo público reutiliza ProductoFilter, el MISMO
#     FilterSet de django-filter que usa GET /api/productos/, así
#     que los filtros se comportan igual en la API y en el HTML.
#   · No se usa get_object_or_404 en ninguna parte: se usa el
#     helper obtener_o_redirigir(), para que un id inexistente
#     lleve a la pantalla de redirección y nunca a un 404.
#   · "Eliminar" es siempre baja lógica (activo = False).
# ============================================================

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import redirect, render

from core.utilidades import booleano_de_texto, obtener_o_redirigir

from .filtros import ProductoFilter
from .forms import CategoriaForm, MarcaForm, ProductoForm
from .models import Categoria, Marca, Producto

# ============================================================
# BLOQUE 1 — CONFIGURACIÓN DE CADA ENTIDAD DEL CATÁLOGO
# Las tres entidades comparten el mismo patrón de gestión (listar,
# crear, ver, editar, desactivar y reactivar). En lugar de repetir
# el código tres veces, se describe cada una en este diccionario y
# las vistas genéricas de los bloques siguientes lo consultan.
# ============================================================
ENTIDADES = {
    "categorias": {
        "modelo": Categoria,
        "formulario": CategoriaForm,
        "singular": "categoría",
        "plural": "categorías",
        "articulo": "la",
        "icono": "bi-tags",
        "base_url": "/panel/categorias/",
        "plantilla_lista": "catalogo/panel_categorias.html",
        "plantilla_detalle": "catalogo/panel_categoria_detalle.html",
        "campos_busqueda": ["nombre__icontains", "descripcion__icontains"],
    },
    "marcas": {
        "modelo": Marca,
        "formulario": MarcaForm,
        "singular": "marca",
        "plural": "marcas",
        "articulo": "la",
        "icono": "bi-award",
        "base_url": "/panel/marcas/",
        "plantilla_lista": "catalogo/panel_marcas.html",
        "plantilla_detalle": "catalogo/panel_marca_detalle.html",
        "campos_busqueda": ["nombre__icontains", "pais_origen__icontains"],
    },
    "productos": {
        "modelo": Producto,
        "formulario": ProductoForm,
        "singular": "producto",
        "plural": "productos",
        "articulo": "el",
        "icono": "bi-cpu",
        "base_url": "/panel/productos/",
        "plantilla_lista": "catalogo/panel_productos.html",
        "plantilla_detalle": "catalogo/panel_producto_detalle.html",
        "campos_busqueda": [
            "nombre__icontains",
            "sku__icontains",
            "descripcion__icontains",
            "marca__nombre__icontains",
        ],
    },
}


def _consulta_filtrada(request, configuracion):
    """Aplica el buscador y el filtro activos/inactivos del listado."""
    modelo = configuracion["modelo"]
    consulta = modelo.objects.all()

    if modelo is Producto:
        consulta = consulta.select_related("categoria", "marca")
    else:
        consulta = consulta.annotate(
            total_productos=Count("productos", filter=Q(productos__activo=True))
        )

    # --- Filtro de estado: activos (por omisión), inactivos o todos ---
    estado = request.GET.get("estado", "activos")
    if estado == "activos":
        consulta = consulta.filter(activo=True)
    elif estado == "inactivos":
        consulta = consulta.filter(activo=False)

    # --- Buscador libre sobre los campos definidos por entidad ---
    texto = (request.GET.get("buscar") or "").strip()
    if texto:
        condicion = Q()
        for campo in configuracion["campos_busqueda"]:
            condicion |= Q(**{campo: texto})
        consulta = consulta.filter(condicion)

    return consulta, estado, texto


# ============================================================
# BLOQUE 2 — CATÁLOGO PÚBLICO
# Listado con el formulario de filtros de ProductoFilter, búsqueda,
# ordenamiento y paginación de 12 productos por página.
# ============================================================
def catalogo_publico(request):
    """Catálogo público con filtros, búsqueda, orden y paginación."""
    base = Producto.objects.filter(activo=True).select_related("categoria", "marca")

    # El mismo FilterSet que usa la API REST.
    filtro = ProductoFilter(request.GET, queryset=base)
    productos = filtro.qs

    # --- Ordenamiento controlado (solo campos permitidos) ---
    ordenes_validos = {
        "nombre": "Nombre (A-Z)",
        "-nombre": "Nombre (Z-A)",
        "precio": "Precio (menor a mayor)",
        "-precio": "Precio (mayor a menor)",
        "-stock": "Mayor stock",
        "-creado_en": "Más recientes",
    }
    orden = request.GET.get("ordering", "nombre")
    if orden not in ordenes_validos:
        orden = "nombre"
    productos = productos.order_by(orden)

    paginador = Paginator(productos, 12)
    pagina = paginador.get_page(request.GET.get("page"))

    # --- Cadena de consulta sin "page", para que la paginación conserve los filtros ---
    parametros = request.GET.copy()
    parametros.pop("page", None)

    contexto = {
        "titulo_pagina": "Catálogo de componentes",
        "filtro": filtro,
        "pagina": pagina,
        "total_resultados": paginador.count,
        "ordenes_validos": ordenes_validos,
        "orden_actual": orden,
        "parametros": parametros.urlencode(),
        "hay_filtros_activos": any(
            request.GET.get(clave) for clave in filtro.form.fields if clave != "page"
        ),
        "migas": [{"etiqueta": "Catálogo", "url": None}],
    }
    return render(request, "catalogo/lista.html", contexto)


def detalle_publico(request, producto_id):
    """Ficha pública de un componente con SKU, precio, stock y disponibilidad."""
    producto, redireccion = obtener_o_redirigir(
        Producto,
        mensaje_error=f"El producto solicitado (id {producto_id}) no existe en el catálogo.",
        pk=producto_id,
    )
    if redireccion is not None:
        return redireccion(request)

    relacionados = (
        Producto.objects.filter(activo=True, categoria=producto.categoria)
        .exclude(pk=producto.pk)
        .select_related("marca")[:4]
    )

    contexto = {
        "titulo_pagina": producto.nombre,
        "producto": producto,
        "relacionados": relacionados,
        "migas": [
            {"etiqueta": "Catálogo", "url": "/catalogo/"},
            {"etiqueta": producto.categoria.nombre, "url": f"/catalogo/?categoria={producto.categoria_id}"},
            {"etiqueta": producto.nombre, "url": None},
        ],
    }
    return render(request, "catalogo/detalle.html", contexto)


# ============================================================
# BLOQUE 3 — LISTADO DE GESTIÓN
# Una sola vista atiende las tres entidades gracias al diccionario
# ENTIDADES. Incluye buscador, filtro activos/inactivos y
# paginación, y muestra cuántos registros hay de cada tipo.
# ============================================================
def panel_lista(request, entidad):
    """Listado de gestión de una entidad del catálogo."""
    configuracion = ENTIDADES[entidad]
    consulta, estado, texto = _consulta_filtrada(request, configuracion)

    consulta = consulta.order_by("nombre")
    paginador = Paginator(consulta, 15)
    pagina = paginador.get_page(request.GET.get("page"))

    modelo = configuracion["modelo"]
    parametros = request.GET.copy()
    parametros.pop("page", None)

    contexto = {
        "titulo_pagina": configuracion["plural"].capitalize(),
        "entidad": entidad,
        "configuracion": configuracion,
        "pagina": pagina,
        "total_resultados": paginador.count,
        "estado_actual": estado,
        "texto_busqueda": texto,
        "total_activos": modelo.objects.filter(activo=True).count(),
        "total_inactivos": modelo.objects.filter(activo=False).count(),
        "parametros": parametros.urlencode(),
        "migas": [
            {"etiqueta": "Gestión", "url": "/panel/"},
            {"etiqueta": configuracion["plural"].capitalize(), "url": None},
        ],
    }
    return render(request, configuracion["plantilla_lista"], contexto)


# ============================================================
# BLOQUE 4 — FICHA DE GESTIÓN
# Muestra todos los campos del registro y sus relaciones, con los
# botones de editar, desactivar o reactivar según su estado.
# ============================================================
def panel_detalle(request, entidad, objeto_id):
    """Ficha de un registro del catálogo dentro del panel de gestión."""
    configuracion = ENTIDADES[entidad]

    objeto, redireccion = obtener_o_redirigir(
        configuracion["modelo"],
        mensaje_error=(
            f"No existe {configuracion['articulo']} {configuracion['singular']} "
            f"con el id {objeto_id}."
        ),
        pk=objeto_id,
    )
    if redireccion is not None:
        return redireccion(request)

    contexto = {
        "titulo_pagina": str(objeto),
        "entidad": entidad,
        "configuracion": configuracion,
        "objeto": objeto,
        "migas": [
            {"etiqueta": "Gestión", "url": "/panel/"},
            {"etiqueta": configuracion["plural"].capitalize(), "url": configuracion["base_url"]},
            {"etiqueta": str(objeto), "url": None},
        ],
    }

    if entidad != "productos":
        contexto["productos_relacionados"] = objeto.productos.select_related(
            "categoria", "marca"
        ).order_by("nombre")[:20]

    return render(request, configuracion["plantilla_detalle"], contexto)


# ============================================================
# BLOQUE 5 — ALTA Y EDICIÓN
# Una sola vista sirve para crear (objeto_id = None) y para editar.
# Al guardar deja un mensaje flash y vuelve al listado; si el
# formulario trae errores, se vuelven a mostrar campo por campo.
# ============================================================
def panel_formulario(request, entidad, objeto_id=None):
    """Crea o edita un registro del catálogo con validación completa."""
    configuracion = ENTIDADES[entidad]
    clase_formulario = configuracion["formulario"]

    objeto = None
    if objeto_id is not None:
        objeto, redireccion = obtener_o_redirigir(
            configuracion["modelo"],
            mensaje_error=(
                f"No existe {configuracion['articulo']} {configuracion['singular']} "
                f"con el id {objeto_id}."
            ),
            pk=objeto_id,
        )
        if redireccion is not None:
            return redireccion(request)

    if request.method == "POST":
        formulario = clase_formulario(request.POST, instance=objeto)
        if formulario.is_valid():
            guardado = formulario.save()
            verbo = "actualizada" if objeto_id else "creada"
            if configuracion["articulo"] == "el":
                verbo = "actualizado" if objeto_id else "creado"

            messages.success(
                request,
                f"{configuracion['singular'].capitalize()} «{guardado}» {verbo} correctamente.",
            )
            return redirect(f"{configuracion['base_url']}{guardado.pk}/")

        messages.error(request, "Revise los datos del formulario: hay campos con errores.")
    else:
        formulario = clase_formulario(instance=objeto)

    es_edicion = objeto_id is not None
    titulo = (
        f"Editar {configuracion['singular']}"
        if es_edicion
        else f"Nueva {configuracion['singular']}"
        if configuracion["articulo"] == "la"
        else f"Nuevo {configuracion['singular']}"
    )

    contexto = {
        "titulo_pagina": titulo,
        "formulario": formulario,
        "objeto": objeto,
        "es_edicion": es_edicion,
        "icono": configuracion["icono"],
        "url_cancelar": configuracion["base_url"],
        "texto_boton": "Guardar cambios" if es_edicion else "Crear",
        "descripcion_formulario": (
            f"Modifique los datos y guarde los cambios."
            if es_edicion
            else f"Complete los datos para registrar {configuracion['articulo']} {configuracion['singular']}."
        ),
        "migas": [
            {"etiqueta": "Gestión", "url": "/panel/"},
            {"etiqueta": configuracion["plural"].capitalize(), "url": configuracion["base_url"]},
            {"etiqueta": titulo, "url": None},
        ],
    }
    return render(request, "parciales/formulario.html", contexto)


# ============================================================
# BLOQUE 6 — BAJA LÓGICA CON CONFIRMACIÓN
# GET muestra la pantalla de confirmación; POST ejecuta la baja.
# Nunca se borra la fila: se deja activo = False, de modo que el
# historial de ventas y los carros que la referencian siguen
# siendo válidos.
# ============================================================
def panel_desactivar(request, entidad, objeto_id):
    """Da de baja lógicamente un registro, previa confirmación."""
    configuracion = ENTIDADES[entidad]

    objeto, redireccion = obtener_o_redirigir(
        configuracion["modelo"],
        mensaje_error=(
            f"No existe {configuracion['articulo']} {configuracion['singular']} "
            f"con el id {objeto_id}."
        ),
        pk=objeto_id,
    )
    if redireccion is not None:
        return redireccion(request)

    if request.method == "POST":
        objeto.desactivar()
        messages.warning(
            request,
            f"{configuracion['singular'].capitalize()} «{objeto}» quedó dada de baja. "
            "La fila se conserva en la base de datos y puede reactivarse.",
        )
        return redirect(configuracion["base_url"])

    contexto = {
        "titulo_pagina": f"Dar de baja {configuracion['articulo']} {configuracion['singular']}",
        "objeto": objeto,
        "mensaje_confirmacion": (
            f"¿Confirma dar de baja {configuracion['articulo']} {configuracion['singular']} «{objeto}»?"
        ),
        "explicacion": (
            "No se borra ninguna fila de la base de datos: el registro queda con "
            "«activo = false», deja de aparecer en el catálogo público y puede "
            "reactivarse cuando quiera."
        ),
        "url_cancelar": f"{configuracion['base_url']}{objeto.pk}/",
        "texto_boton": "Sí, dar de baja",
        "clase_boton": "btn-danger",
        "icono": "bi-exclamation-triangle",
        "migas": [
            {"etiqueta": "Gestión", "url": "/panel/"},
            {"etiqueta": configuracion["plural"].capitalize(), "url": configuracion["base_url"]},
            {"etiqueta": "Dar de baja", "url": None},
        ],
    }
    return render(request, "parciales/confirmar.html", contexto)


def panel_reactivar(request, entidad, objeto_id):
    """Revierte la baja lógica de un registro del catálogo."""
    configuracion = ENTIDADES[entidad]

    objeto, redireccion = obtener_o_redirigir(
        configuracion["modelo"],
        mensaje_error=(
            f"No existe {configuracion['articulo']} {configuracion['singular']} "
            f"con el id {objeto_id}."
        ),
        pk=objeto_id,
    )
    if redireccion is not None:
        return redireccion(request)

    objeto.reactivar()
    messages.success(
        request,
        f"{configuracion['singular'].capitalize()} «{objeto}» está activa otra vez.",
    )
    return redirect(f"{configuracion['base_url']}{objeto.pk}/")


# ============================================================
# BLOQUE 7 — VISTAS CONCRETAS POR ENTIDAD
# Envoltorios delgados que fijan la entidad. Existen para que las
# rutas queden legibles en urls.py y para que cada módulo del panel
# tenga un nombre propio en la defensa oral.
# ============================================================
def categorias_lista(request):
    """Listado de gestión de categorías."""
    return panel_lista(request, "categorias")


def categoria_detalle(request, objeto_id):
    """Ficha de gestión de una categoría."""
    return panel_detalle(request, "categorias", objeto_id)


def categoria_crear(request):
    """Alta de una categoría."""
    return panel_formulario(request, "categorias")


def categoria_editar(request, objeto_id):
    """Edición de una categoría."""
    return panel_formulario(request, "categorias", objeto_id)


def categoria_desactivar(request, objeto_id):
    """Baja lógica de una categoría."""
    return panel_desactivar(request, "categorias", objeto_id)


def categoria_reactivar(request, objeto_id):
    """Reactivación de una categoría."""
    return panel_reactivar(request, "categorias", objeto_id)


def marcas_lista(request):
    """Listado de gestión de marcas."""
    return panel_lista(request, "marcas")


def marca_detalle(request, objeto_id):
    """Ficha de gestión de una marca."""
    return panel_detalle(request, "marcas", objeto_id)


def marca_crear(request):
    """Alta de una marca."""
    return panel_formulario(request, "marcas")


def marca_editar(request, objeto_id):
    """Edición de una marca."""
    return panel_formulario(request, "marcas", objeto_id)


def marca_desactivar(request, objeto_id):
    """Baja lógica de una marca."""
    return panel_desactivar(request, "marcas", objeto_id)


def marca_reactivar(request, objeto_id):
    """Reactivación de una marca."""
    return panel_reactivar(request, "marcas", objeto_id)


def productos_lista(request):
    """Listado de gestión de productos."""
    return panel_lista(request, "productos")


def producto_detalle(request, objeto_id):
    """Ficha de gestión de un producto."""
    return panel_detalle(request, "productos", objeto_id)


def producto_crear(request):
    """Alta de un producto."""
    return panel_formulario(request, "productos")


def producto_editar(request, objeto_id):
    """Edición de un producto."""
    return panel_formulario(request, "productos", objeto_id)


def producto_desactivar(request, objeto_id):
    """Baja lógica de un producto."""
    return panel_desactivar(request, "productos", objeto_id)


def producto_reactivar(request, objeto_id):
    """Reactivación de un producto."""
    return panel_reactivar(request, "productos", objeto_id)
