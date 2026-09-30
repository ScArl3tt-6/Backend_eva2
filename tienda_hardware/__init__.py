# ============================================================
# tienda_hardware/__init__.py — ARRANQUE DEL PAQUETE DE CONFIGURACIÓN
# Responsabilidad: garantizar que el driver PostgreSQL (psycopg 3)
# pueda cargarse antes de que Django abra la conexión.
#
# Por qué existe este bloque: en Windows, las políticas de Control
# de aplicaciones (Smart App Control / WDAC) pueden bloquear la
# librería binaria que trae la rueda "psycopg[binary]". En ese caso
# psycopg ofrece una implementación alternativa en Python puro que
# usa la libpq.dll firmada que instala PostgreSQL. Aquí se detecta
# el bloqueo y se activa ese respaldo de forma transparente, sin
# que la alumna tenga que modificar variables de entorno a mano.
# ============================================================

import os
import sys
from pathlib import Path


# ============================================================
# BLOQUE 1 — LOCALIZACIÓN DE libpq.dll
# Lee PG_BIN_DIR del archivo .env (sin depender todavía de Django)
# y, si no está definido, prueba las rutas habituales de
# instalación de PostgreSQL en Windows.
# ============================================================
def _directorios_candidatos_libpq() -> list[Path]:
    """Devuelve las carpetas donde puede vivir la libpq.dll del sistema."""
    candidatos: list[Path] = []

    archivo_env = Path(__file__).resolve().parent.parent / ".env"
    if archivo_env.is_file():
        for linea in archivo_env.read_text(encoding="utf-8").splitlines():
            if linea.strip().startswith("PG_BIN_DIR="):
                valor = linea.split("=", 1)[1].strip()
                if valor:
                    candidatos.append(Path(valor))

    valor_entorno = os.environ.get("PG_BIN_DIR", "").strip()
    if valor_entorno:
        candidatos.append(Path(valor_entorno))

    raiz_postgres = Path("C:/Program Files/PostgreSQL")
    if raiz_postgres.is_dir():
        for version in sorted(raiz_postgres.iterdir(), reverse=True):
            candidatos.append(version / "bin")

    return [ruta for ruta in candidatos if (ruta / "libpq.dll").is_file()]


# ============================================================
# BLOQUE 2 — VERIFICACIÓN Y RESPALDO DEL DRIVER
# Intenta importar psycopg tal cual. Si falla por el bloqueo del
# binario, registra la carpeta de libpq en el buscador de DLL,
# fuerza la implementación "python" y reintenta la importación.
# ============================================================
def _asegurar_driver_postgresql() -> None:
    """Deja psycopg 3 en condiciones de conectarse a PostgreSQL."""
    try:
        import psycopg  # noqa: F401  (solo se comprueba que importe)
        return
    except ImportError:
        pass

    if sys.platform != "win32":
        return

    for directorio in _directorios_candidatos_libpq():
        texto_directorio = str(directorio)
        os.environ["PATH"] = texto_directorio + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(texto_directorio)
        except (OSError, AttributeError):
            continue

        os.environ["PSYCOPG_IMPL"] = "python"
        for nombre_modulo in [m for m in sys.modules if m.startswith("psycopg")]:
            del sys.modules[nombre_modulo]

        try:
            import psycopg  # noqa: F401
            return
        except ImportError:
            continue


_asegurar_driver_postgresql()
