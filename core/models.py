# ============================================================
# core/models.py — SIN MODELOS PROPIOS
# Responsabilidad: ninguna en cuanto a datos. La aplicación core
# es deliberadamente transversal y NO define modelos: aporta las
# vistas de inicio, panel y documentación, el middleware que
# controla las rutas inexistentes, el manejador de errores de la
# API, los context processors, el filtro de moneda chilena y los
# comandos de gestión.
#
# Las nueve entidades del negocio viven donde les corresponde:
#   · usuarios/models.py  → Usuario y Rol
#   · catalogo/models.py  → Categoria, Marca y Producto
#   · carro/models.py     → Carro e ItemCarro
#   · ordenes/models.py   → Orden, DetalleOrden e HistorialEstadoOrden
#
# El archivo se conserva porque Django lo espera en toda aplicación
# instalada; dejarlo vacío es lo correcto aquí.
# ============================================================
