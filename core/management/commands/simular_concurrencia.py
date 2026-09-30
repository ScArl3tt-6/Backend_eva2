# ============================================================
# core/management/commands/simular_concurrencia.py
# DEMOSTRACIÓN DEL CONTROL DE STOCK EN CONDICIONES DE CARRERA
#
# Responsabilidad: probar en vivo que dos clientes NO pueden
# comprar la misma última unidad.
#
#   python manage.py simular_concurrencia
#
# Qué hace:
#   1. Crea un producto de demostración con stock = 1.
#   2. Crea dos clientes de demostración, cada uno con una orden
#      PENDIENTE por esa única unidad.
#   3. Lanza DOS HILOS que llaman a pagar_orden() al mismo tiempo,
#      sincronizados con una barrera para que arranquen juntos.
#   4. Imprime el resultado de cada hilo y el stock final.
#
# Resultado esperado, siempre:
#   · un pago queda PAGADO;
#   · el otro es rechazado por StockInsuficienteError;
#   · el stock final es 0, nunca -1.
#
# Por qué funciona: pagar_orden() abre una transacción y bloquea
# con select_for_update() las filas de los productos implicados. El
# segundo hilo se queda esperando en ese bloqueo; cuando el primero
# confirma y libera, el segundo relee el stock YA descontado, ve que
# no alcanza y lanza la excepción, que revierte su transacción.
#
# Detalle técnico importante: cada hilo usa su propia conexión a la
# base de datos y la cierra al terminar (connection.close()), porque
# Django asocia las conexiones al hilo que las abre y dejarlas
# abiertas produciría conexiones huérfanas.
# ============================================================

import threading
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from carro.servicios import agregar_producto, obtener_carro
from catalogo.models import Categoria, Marca, Producto
from ordenes.models import EstadoOrden, Orden
from ordenes.servicios import (
    StockInsuficienteError,
    pagar_orden,
    realizar_checkout,
)
from usuarios.models import Rol, Usuario

# ============================================================
# BLOQUE 1 — DATOS FIJOS DE LA DEMOSTRACIÓN
# Se usan nombres reconocibles y con el prefijo DEMO para que no se
# confundan con el catálogo real cargado por seed_data.
# ============================================================
SKU_DEMO = "DEMO-CONCURRENCIA-01"
NOMBRE_PRODUCTO = "Tarjeta de video DEMO (última unidad)"
CATEGORIA_DEMO = "Tarjetas de Video"
MARCA_DEMO = "NVIDIA"
PRECIO_DEMO = Decimal("1999990")

CLIENTES_DEMO = [
    ("demo_comprador_1", "Demo", "Comprador Uno", "demo1@hardpointpc.cl"),
    ("demo_comprador_2", "Demo", "Comprador Dos", "demo2@hardpointpc.cl"),
]


class Command(BaseCommand):
    """Comando que demuestra el control de stock con dos pagos simultáneos."""

    help = (
        "Lanza dos pagos simultáneos por la última unidad de un producto de "
        "demostración y muestra que solo uno queda PAGADO, que el otro es "
        "rechazado por falta de stock y que el stock final nunca queda negativo."
    )

    # ============================================================
    # BLOQUE 2 — PUNTO DE ENTRADA
    # La preparación se hace de forma secuencial; solo el pago se
    # ejecuta en paralelo, que es la parte que se quiere probar.
    # ============================================================
    def handle(self, *args, **opciones):
        """Prepara el escenario, lanza los dos hilos y muestra el resultado."""
        self._titulo("SIMULACIÓN DE CONCURRENCIA — DOS PAGOS SIMULTÁNEOS")

        producto = self._preparar_producto()
        ordenes = self._preparar_ordenes(producto)

        self.stdout.write("")
        self.stdout.write(f"  Producto: {producto.nombre}")
        self.stdout.write(f"  SKU: {producto.sku}")
        self.stdout.write(self.style.WARNING(f"  Stock inicial: {producto.stock} unidad"))
        self.stdout.write("")
        for username, orden in ordenes:
            self.stdout.write(
                f"  Orden {orden.codigo_corto} de {username}: estado {orden.estado}, "
                f"pide 1 unidad"
            )

        resultados = self._lanzar_pagos_simultaneos(ordenes)
        self._informar(producto, ordenes, resultados)

    # ============================================================
    # BLOQUE 3 — PREPARACIÓN DEL PRODUCTO
    # Reutiliza la categoría y la marca si ya existen (por ejemplo si
    # ya se ejecutó seed_data) y deja el stock en exactamente 1.
    # ============================================================
    def _preparar_producto(self) -> Producto:
        """Crea o repone el producto de demostración con stock = 1."""
        categoria, _ = Categoria.objects.get_or_create(
            nombre=CATEGORIA_DEMO,
            defaults={
                "descripcion": "Aceleradoras gráficas dedicadas.",
                "icono": "bi-gpu-card",
                "activo": True,
            },
        )
        marca, _ = Marca.objects.get_or_create(
            nombre=MARCA_DEMO,
            defaults={"pais_origen": "Estados Unidos", "activo": True},
        )

        producto, _ = Producto.objects.update_or_create(
            sku=SKU_DEMO,
            defaults={
                "nombre": NOMBRE_PRODUCTO,
                "descripcion": (
                    "Producto creado por el comando simular_concurrencia. "
                    "Su stock se fija en 1 para provocar la condición de carrera."
                ),
                "categoria": categoria,
                "marca": marca,
                "precio": PRECIO_DEMO,
                "stock": 1,
                "activo": True,
            },
        )
        return producto

    # ============================================================
    # BLOQUE 4 — PREPARACIÓN DE LAS DOS ÓRDENES
    # Cada cliente de demostración termina con una orden PENDIENTE
    # por una unidad del mismo producto. El checkout no descuenta
    # stock, así que al final de este paso el stock sigue siendo 1 y
    # hay DOS órdenes que lo reclaman.
    # ============================================================
    def _preparar_ordenes(self, producto) -> list[tuple[str, Orden]]:
        """Deja una orden PENDIENTE por cliente de demostración."""
        ordenes = []

        for username, nombre, apellido, correo in CLIENTES_DEMO:
            cliente, creado = Usuario.objects.get_or_create(
                username=username,
                defaults={
                    "email": correo,
                    "first_name": nombre,
                    "last_name": apellido,
                    "rol": Rol.CLIENTE,
                },
            )
            if creado:
                cliente.set_password("Demo.2026")
                cliente.save()

            # Se cancelan las órdenes pendientes de corridas anteriores para
            # que la demostración parta siempre desde el mismo escenario.
            Orden.objects.filter(
                usuario=cliente, estado=EstadoOrden.PENDIENTE
            ).update(estado=EstadoOrden.CANCELADO)

            carro = obtener_carro(cliente)
            carro.items.filter(activo=True).update(activo=False)
            agregar_producto(carro, producto, 1)

            orden = realizar_checkout(cliente)
            ordenes.append((username, orden))

        # El checkout no toca el stock: se comprueba aquí mismo.
        producto.refresh_from_db()
        if producto.stock != 1:
            self.stdout.write(
                self.style.ERROR(
                    f"  Aviso: el stock quedó en {producto.stock} tras el checkout; "
                    "debería seguir siendo 1."
                )
            )

        return ordenes

    # ============================================================
    # BLOQUE 5 — EJECUCIÓN EN PARALELO
    # La barrera (threading.Barrier) obliga a que ambos hilos lleguen
    # al punto de pago antes de continuar, de modo que el intento sea
    # realmente simultáneo y no uno después del otro.
    # ============================================================
    def _lanzar_pagos_simultaneos(self, ordenes) -> dict:
        """Ejecuta dos pagos al mismo tiempo en hilos separados."""
        self._titulo("Lanzando los dos pagos al mismo tiempo")

        resultados: dict[str, dict] = {}
        bloqueo_resultados = threading.Lock()
        barrera = threading.Barrier(len(ordenes))

        def pagar_en_hilo(username, orden_id):
            """Cuerpo de cada hilo: espera en la barrera y luego paga."""
            try:
                # Ambos hilos arrancan el pago en el mismo instante.
                barrera.wait(timeout=10)

                orden = Orden.objects.get(pk=orden_id)
                with transaction.atomic():
                    pagar_orden(orden, usuario=orden.usuario)

                orden.refresh_from_db()
                with bloqueo_resultados:
                    resultados[username] = {
                        "exito": True,
                        "estado": orden.estado,
                        "mensaje": "Pago aprobado: el stock se descontó.",
                    }

            except StockInsuficienteError as error:
                with bloqueo_resultados:
                    resultados[username] = {
                        "exito": False,
                        "estado": EstadoOrden.PENDIENTE,
                        "mensaje": str(error),
                        "faltantes": error.faltantes,
                    }

            except Exception as error:  # noqa: BLE001  (se informa cualquier fallo)
                with bloqueo_resultados:
                    resultados[username] = {
                        "exito": False,
                        "estado": "DESCONOCIDO",
                        "mensaje": f"{type(error).__name__}: {error}",
                    }

            finally:
                # Cada hilo cierra su propia conexión a PostgreSQL.
                connection.close()

        hilos = [
            threading.Thread(
                target=pagar_en_hilo,
                args=(username, orden.pk),
                name=f"pago-{username}",
            )
            for username, orden in ordenes
        ]

        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=30)

        return resultados

    # ============================================================
    # BLOQUE 6 — INFORME DEL RESULTADO
    # Imprime con claridad quién pagó, quién fue rechazado y cuál es
    # el stock final, e indica si la prueba se considera superada.
    # ============================================================
    def _informar(self, producto, ordenes, resultados):
        """Muestra el resultado de cada hilo y verifica las tres condiciones."""
        self._titulo("Resultado de cada intento de pago")

        pagadas = 0
        rechazadas = 0

        for username, _ in ordenes:
            resultado = resultados.get(username)

            if resultado is None:
                self.stdout.write(self.style.ERROR(f"  {username}: el hilo no devolvió resultado."))
                continue

            if resultado["exito"]:
                pagadas += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  {username}: PAGADO — {resultado['mensaje']}"
                    )
                )
            else:
                rechazadas += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  {username}: RECHAZADO — {resultado['mensaje']}"
                    )
                )
                for faltante in resultado.get("faltantes", []):
                    self.stdout.write(
                        f"      pedido: {faltante['solicitado']} · "
                        f"disponible: {faltante['disponible']} · {faltante['motivo']}"
                    )
                self.stdout.write(
                    "      La transacción se revirtió por completo y la orden "
                    "sigue en PENDIENTE."
                )

        # --- Estado final en la base de datos ---
        producto.refresh_from_db()
        estados_finales = []
        for username, orden in ordenes:
            orden.refresh_from_db()
            estados_finales.append((username, orden.codigo_corto, orden.estado))

        self._titulo("Estado final en la base de datos")

        for username, codigo, estado in estados_finales:
            self.stdout.write(f"  Orden {codigo} de {username}: {estado}")

        self.stdout.write("")
        self.stdout.write(f"  Stock final del producto: {producto.stock}")

        # --- Verificación de las tres condiciones de la prueba ---
        self._titulo("Verificación")

        condiciones = [
            ("Exactamente un pago quedó PAGADO", pagadas == 1),
            ("El otro pago fue rechazado por falta de stock", rechazadas == 1),
            ("El stock final es 0 (nunca -1)", producto.stock == 0),
        ]

        todo_bien = True
        for descripcion, cumplida in condiciones:
            if cumplida:
                self.stdout.write(self.style.SUCCESS(f"  [OK]    {descripcion}"))
            else:
                todo_bien = False
                self.stdout.write(self.style.ERROR(f"  [FALLA] {descripcion}"))

        self.stdout.write("")
        if todo_bien:
            self.stdout.write(
                self.style.SUCCESS(
                    "  DEMOSTRACIÓN SUPERADA: el bloqueo con select_for_update() y la "
                    "transacción atómica impidieron la venta duplicada del último producto."
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    "  La demostración no cumplió alguna condición. Revise "
                    "ordenes/servicios.py y la configuración de PostgreSQL."
                )
            )
        self.stdout.write("")

    # ============================================================
    # BLOQUE 7 — SALIDA POR CONSOLA
    # ============================================================
    def _titulo(self, texto):
        """Imprime un encabezado de sección en la consola."""
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"== {texto} =="))
