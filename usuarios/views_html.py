# ============================================================
# usuarios/views_html.py — PANTALLAS HTML DE USUARIOS
# Responsabilidad: CRUD completo de usuarios en /panel/usuarios/,
# con buscador, filtro por estado y por rol, y baja lógica.
#
# Particularidades frente a las entidades del catálogo:
#   · La baja lógica de un usuario se marca con is_active = False
#     (no con un campo "activo"), porque ese es el campo que Django
#     usa para impedir el inicio de sesión.
#   · El formulario permite elegir el rol y guarda la contraseña
#     con set_password.
#   · Al crear un CLIENTE, la señal post_save le genera su carro
#     persistente de inmediato.
# ============================================================

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render

from core.utilidades import obtener_o_redirigir, panel_solo_lectura_o_administrador

from .forms import UsuarioForm
from .models import Rol, Usuario

BASE_URL = "/panel/usuarios/"


# ============================================================
# BLOQUE 1 — LISTADO DE USUARIOS
# Filtros por estado (activos, inactivos o todos) y por rol, más
# buscador libre sobre usuario, nombre, apellido y correo.
# ============================================================
def usuarios_lista(request):
    """Listado de gestión de usuarios con buscador y filtros."""
    consulta = Usuario.objects.all()

    estado = request.GET.get("estado", "activos")
    if estado == "activos":
        consulta = consulta.filter(is_active=True)
    elif estado == "inactivos":
        consulta = consulta.filter(is_active=False)

    rol = request.GET.get("rol", "")
    if rol in Rol.values:
        consulta = consulta.filter(rol=rol)

    texto = (request.GET.get("buscar") or "").strip()
    if texto:
        consulta = consulta.filter(
            Q(username__icontains=texto)
            | Q(first_name__icontains=texto)
            | Q(last_name__icontains=texto)
            | Q(email__icontains=texto)
        )

    consulta = consulta.order_by("username")
    paginador = Paginator(consulta, 15)
    pagina = paginador.get_page(request.GET.get("page"))

    parametros = request.GET.copy()
    parametros.pop("page", None)

    contexto = {
        "titulo_pagina": "Usuarios",
        "pagina": pagina,
        "total_resultados": paginador.count,
        "estado_actual": estado,
        "rol_actual": rol,
        "roles": Rol.choices,
        "texto_busqueda": texto,
        "total_activos": Usuario.objects.filter(is_active=True).count(),
        "total_inactivos": Usuario.objects.filter(is_active=False).count(),
        "total_clientes": Usuario.objects.filter(rol=Rol.CLIENTE, is_active=True).count(),
        "total_administradores": Usuario.objects.filter(
            rol=Rol.ADMINISTRADOR, is_active=True
        ).count(),
        "parametros": parametros.urlencode(),
        "migas": [
            {"etiqueta": "Gestión", "url": "/panel/"},
            {"etiqueta": "Usuarios", "url": None},
        ],
    }
    return render(request, "usuarios/panel_usuarios.html", contexto)


# ============================================================
# BLOQUE 2 — FICHA DEL USUARIO
# Muestra los datos de la cuenta, su rol y un resumen de su
# actividad: carro persistido y órdenes por estado.
# ============================================================
def usuario_detalle(request, objeto_id):
    """Ficha de un usuario con su carro y sus órdenes."""
    usuario, redireccion = obtener_o_redirigir(
        Usuario,
        mensaje_error=f"No existe el usuario con el id {objeto_id}.",
        pk=objeto_id,
    )
    if redireccion is not None:
        return redireccion(request)

    carro = getattr(usuario, "carro", None)
    ordenes = usuario.ordenes.con_total().order_by("-creada_en")[:10]

    contexto = {
        "titulo_pagina": usuario.username,
        "objeto": usuario,
        "carro": carro,
        "items_carro": carro.items_activos if carro else [],
        "ordenes": ordenes,
        "total_ordenes": usuario.ordenes.count(),
        "migas": [
            {"etiqueta": "Gestión", "url": "/panel/"},
            {"etiqueta": "Usuarios", "url": BASE_URL},
            {"etiqueta": usuario.username, "url": None},
        ],
    }
    return render(request, "usuarios/panel_usuario_detalle.html", contexto)


# ============================================================
# BLOQUE 3 — ALTA Y EDICIÓN
# Usa UsuarioForm, que cifra la contraseña con set_password y
# permite elegir el rol. Al editar, dejar la contraseña vacía
# conserva la actual.
# ============================================================
@panel_solo_lectura_o_administrador
def usuario_formulario(request, objeto_id=None):
    """Crea o edita un usuario eligiendo su rol. Solo el administrador escribe."""
    usuario = None
    if objeto_id is not None:
        usuario, redireccion = obtener_o_redirigir(
            Usuario,
            mensaje_error=f"No existe el usuario con el id {objeto_id}.",
            pk=objeto_id,
        )
        if redireccion is not None:
            return redireccion(request)

    if request.method == "POST":
        formulario = UsuarioForm(request.POST, instance=usuario)
        if formulario.is_valid():
            guardado = formulario.save()
            verbo = "actualizado" if objeto_id else "creado"
            extra = ""
            if not objeto_id and guardado.rol == Rol.CLIENTE:
                extra = " Se creó también su carro de compras persistente."

            messages.success(
                request,
                f"Usuario «{guardado.username}» {verbo} correctamente.{extra}",
            )
            return redirect(f"{BASE_URL}{guardado.pk}/")

        messages.error(request, "Revise los datos del formulario: hay campos con errores.")
    else:
        formulario = UsuarioForm(instance=usuario)

    es_edicion = objeto_id is not None
    titulo = "Editar usuario" if es_edicion else "Nuevo usuario"

    contexto = {
        "titulo_pagina": titulo,
        "formulario": formulario,
        "objeto": usuario,
        "es_edicion": es_edicion,
        "icono": "bi-person-gear",
        "url_cancelar": BASE_URL,
        "texto_boton": "Guardar cambios" if es_edicion else "Crear usuario",
        "descripcion_formulario": (
            "Modifique los datos de la cuenta. Deje la contraseña vacía para conservar la actual."
            if es_edicion
            else "Complete los datos de la cuenta y elija su rol."
        ),
        "migas": [
            {"etiqueta": "Gestión", "url": "/panel/"},
            {"etiqueta": "Usuarios", "url": BASE_URL},
            {"etiqueta": titulo, "url": None},
        ],
    }
    return render(request, "parciales/formulario.html", contexto)


# ============================================================
# BLOQUE 4 — BAJA LÓGICA Y REACTIVACIÓN
# La baja deja is_active = False: la cuenta no puede iniciar sesión
# ni obtener un token, pero su historial de órdenes se conserva
# intacto (las órdenes usan PROTECT sobre el usuario).
# ============================================================
@panel_solo_lectura_o_administrador
def usuario_desactivar(request, objeto_id):
    """Da de baja una cuenta sin borrarla, previa confirmación. Solo el administrador escribe."""
    usuario, redireccion = obtener_o_redirigir(
        Usuario,
        mensaje_error=f"No existe el usuario con el id {objeto_id}.",
        pk=objeto_id,
    )
    if redireccion is not None:
        return redireccion(request)

    if request.method == "POST":
        usuario.is_active = False
        usuario.save(update_fields=["is_active", "actualizado_en"])
        messages.warning(
            request,
            f"El usuario «{usuario.username}» quedó dado de baja. "
            "Su historial de órdenes se conserva y la cuenta puede reactivarse.",
        )
        return redirect(BASE_URL)

    contexto = {
        "titulo_pagina": "Dar de baja el usuario",
        "objeto": usuario,
        "mensaje_confirmacion": f"¿Confirma dar de baja la cuenta «{usuario.username}»?",
        "explicacion": (
            "No se borra ninguna fila: la cuenta queda con «is_active = false», "
            "deja de poder iniciar sesión y obtener tokens, y su carro y sus "
            "órdenes se conservan. Puede reactivarla cuando quiera."
        ),
        "url_cancelar": f"{BASE_URL}{usuario.pk}/",
        "texto_boton": "Sí, dar de baja",
        "clase_boton": "btn-danger",
        "icono": "bi-person-dash",
        "migas": [
            {"etiqueta": "Gestión", "url": "/panel/"},
            {"etiqueta": "Usuarios", "url": BASE_URL},
            {"etiqueta": "Dar de baja", "url": None},
        ],
    }
    return render(request, "parciales/confirmar.html", contexto)


@panel_solo_lectura_o_administrador
def usuario_reactivar(request, objeto_id):
    """Vuelve a habilitar una cuenta dada de baja. Solo el administrador escribe."""
    if request.method != "POST":
        return redirect(f"{BASE_URL}{objeto_id}/")

    usuario, redireccion = obtener_o_redirigir(
        Usuario,
        mensaje_error=f"No existe el usuario con el id {objeto_id}.",
        pk=objeto_id,
    )
    if redireccion is not None:
        return redireccion(request)

    usuario.is_active = True
    usuario.save(update_fields=["is_active", "actualizado_en"])
    messages.success(request, f"El usuario «{usuario.username}» está activo otra vez.")
    return redirect(f"{BASE_URL}{usuario.pk}/")
