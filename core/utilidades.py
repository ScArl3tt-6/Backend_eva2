# ============================================================
# core/utilidades.py — APOYO PARA LAS VISTAS HTML
# Responsabilidad: reemplazar get_object_or_404 en las pantallas
# HTML del proyecto.
#
# Por qué: la pauta prohíbe que una dirección termine mostrando el
# 404 de Django. get_object_or_404 lanza Http404, así que en su
# lugar las vistas HTML usan obtener_o_redirigir(), que cuando el
# objeto no existe deja un mensaje explicativo y devuelve una
# redirección a la pantalla de aviso del proyecto.
#
# El resultado es que /panel/productos/999999/ no muestra un error:
# muestra la pantalla de redirección con su cuenta regresiva.
# ============================================================

from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect


# ============================================================
# BLOQUE 1 — BÚSQUEDA SEGURA DE UN OBJETO
# Devuelve una tupla (objeto, respuesta_de_redireccion). La vista
# comprueba primero la redirección; si es None, puede usar el
# objeto con confianza. Es el patrón habitual en Go y evita tanto
# las excepciones como los None silenciosos.
# ============================================================
def obtener_o_redirigir(modelo, mensaje_error=None, destino="core:redireccion", **filtros):
    """Busca un objeto; si no existe, devuelve una redirección con aviso."""
    objeto = modelo.objects.filter(**filtros).first()

    if objeto is not None:
        return objeto, None

    nombre = modelo._meta.verbose_name
    texto = mensaje_error or f"No se encontró el registro de {nombre} que buscaba."

    def redireccion(request):
        """Deja el mensaje flash y envía a la pantalla indicada."""
        messages.error(request, texto)
        return redirect(destino)

    return None, redireccion


# ============================================================
# BLOQUE 2 — INTERPRETACIÓN DE PARÁMETROS DE LA URL
# Los formularios GET envían texto; estas funciones lo convierten
# con un valor por omisión seguro, de modo que un parámetro
# manipulado a mano (por ejemplo ?usuario=abc) no provoque un
# error 500 sino que simplemente se ignore.
# ============================================================
def entero_o_none(valor):
    """Convierte el texto a entero; devuelve None si no es posible."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def booleano_de_texto(valor, por_omision=False):
    """Interpreta 'true', '1', 'si' y 'sí' como verdadero."""
    if valor is None or valor == "":
        return por_omision
    return str(valor).strip().lower() in {"true", "1", "si", "sí", "on"}


# ============================================================
# BLOQUE 3 — LECTURA PÚBLICA, ESCRITURA SOLO DEL ADMINISTRADOR
# El panel de gestión (/panel/...) puede verlo cualquier visitante,
# sin iniciar sesión: ese fue siempre el criterio del proyecto para
# que la defensa se pudiera mostrar sin fricción. Lo que faltaba es
# que CUALQUIERA podía además editar: pagar una orden ajena, vaciar
# el carro de otra persona o dar de baja una cuenta, sin que nadie
# quedara identificado como responsable del cambio.
#
# Este decorador aplica a las pantallas HTML el mismo criterio que
# ya existe en la API (usuarios.permisos.EsAdministradorOSoloLectura):
# los métodos seguros (GET, HEAD, OPTIONS) quedan abiertos a todos;
# cualquier otro método exige una sesión de administrador de TI
# (is_staff, sincronizado con rol=ADMINISTRADOR en Usuario.save()).
# ============================================================
_METODOS_SEGUROS = ("GET", "HEAD", "OPTIONS")


def panel_solo_lectura_o_administrador(vista):
    """Permite ver la pantalla a cualquiera; exige administrador para escribir."""

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if request.method in _METODOS_SEGUROS:
            return vista(request, *args, **kwargs)

        if request.user.is_authenticated and request.user.is_staff:
            return vista(request, *args, **kwargs)

        messages.error(
            request,
            "Esa acción requiere una sesión de Administrador de TI. Inicie sesión "
            "para continuar.",
        )
        return redirect_to_login(request.get_full_path(), login_url="core:panel-login")

    return envoltura
