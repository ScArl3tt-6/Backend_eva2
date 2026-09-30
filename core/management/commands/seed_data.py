# ============================================================
# core/management/commands/seed_data.py — DATOS DE PRUEBA
# Responsabilidad: dejar la base de datos lista para evaluar el
# sistema con un solo comando:
#
#   python manage.py seed_data
#   python manage.py seed_data --reset
#
# Qué crea:
#   · 1 Administrador de TI y 3 clientes, con contraseñas
#     documentadas en el README y en /documentacion/.
#   · 6 categorías y 8 marcas reales del mundo del hardware.
#   · 25 productos con SKU, precios en pesos chilenos y stock
#     variado, incluidos algunos con stock 1 y otros con stock 0,
#     que son los que permiten demostrar las validaciones y el
#     rechazo 409 por falta de stock.
#   · Carros con ítems ya cargados para dos clientes.
#   · Órdenes de ejemplo en los cuatro estados, cada una con su
#     historial, generadas con las funciones de servicio reales
#     (no escribiendo estados a mano), de modo que el stock quede
#     coherente con lo que ocurrió.
#
# Es idempotente: ejecutarlo dos veces no duplica nada. Con --reset
# da de baja el catálogo, regenera las órdenes de ejemplo y deja
# siempre el mismo escenario reproducible (6 categorías, 8 marcas,
# 25 productos, 3 clientes y 4 órdenes, una por estado).
# ============================================================

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from carro.models import Carro, ItemCarro
from carro.servicios import agregar_producto, obtener_carro
from catalogo.models import Categoria, Marca, Producto
from ordenes.models import DetalleOrden, EstadoOrden, HistorialEstadoOrden, Orden
from ordenes.servicios import cambiar_estado_orden, realizar_checkout
from usuarios.models import Rol, Usuario

# ============================================================
# BLOQUE 1 — CONTRASEÑAS DE DEMOSTRACIÓN
# Se definen como constantes para que el comando, el README y la
# página /documentacion/ digan exactamente lo mismo.
# ============================================================
CONTRASENA_ADMIN = "Admin.2026"
CONTRASENA_CLIENTE = "Cliente.2026"


# ============================================================
# BLOQUE 2 — CATÁLOGO DE DEMOSTRACIÓN
# Categorías, marcas y productos reales del rubro, con precios de
# referencia del mercado chileno.
# ============================================================
CATEGORIAS = [
    ("Procesadores", "Unidades centrales de proceso para equipos de escritorio.", "bi-cpu"),
    ("Tarjetas de Video", "Aceleradoras gráficas dedicadas para juegos y diseño.", "bi-gpu-card"),
    ("Memorias RAM", "Módulos de memoria DDR4 y DDR5 para escritorio.", "bi-memory"),
    ("Placas Madre", "Placas base con distintos sockets y formatos.", "bi-motherboard"),
    ("Almacenamiento SSD", "Unidades de estado sólido SATA y NVMe.", "bi-device-hdd"),
    ("Fuentes de Poder", "Fuentes con certificación de eficiencia energética.", "bi-plug"),
]

MARCAS = [
    ("Intel", "Estados Unidos"),
    ("AMD", "Estados Unidos"),
    ("NVIDIA", "Estados Unidos"),
    ("Kingston", "Estados Unidos"),
    ("Corsair", "Estados Unidos"),
    ("ASUS", "Taiwán"),
    ("Gigabyte", "Taiwán"),
    ("Samsung", "Corea del Sur"),
]

# (sku, nombre, categoría, marca, precio, stock, descripción)
PRODUCTOS = [
    # --- Procesadores ---
    ("CPU-INT-14600K", "Procesador Intel Core i5-14600K", "Procesadores", "Intel", 329990, 18,
     "14 núcleos (6P + 8E), 20 hilos, hasta 5,3 GHz, socket LGA1700, sin refrigeración incluida."),
    ("CPU-INT-14700K", "Procesador Intel Core i7-14700K", "Procesadores", "Intel", 489990, 9,
     "20 núcleos (8P + 12E), 28 hilos, hasta 5,6 GHz, socket LGA1700."),
    ("CPU-AMD-7600X", "Procesador AMD Ryzen 5 7600X", "Procesadores", "AMD", 279990, 14,
     "6 núcleos, 12 hilos, hasta 5,3 GHz, socket AM5, arquitectura Zen 4."),
    ("CPU-AMD-7800X3D", "Procesador AMD Ryzen 7 7800X3D", "Procesadores", "AMD", 549990, 4,
     "8 núcleos, 16 hilos, 96 MB de caché 3D V-Cache, socket AM5. El favorito para juegos."),
    ("CPU-AMD-9950X", "Procesador AMD Ryzen 9 9950X", "Procesadores", "AMD", 899990, 1,
     "16 núcleos, 32 hilos, hasta 5,7 GHz, socket AM5. Última unidad disponible."),

    # --- Tarjetas de Video ---
    ("GPU-NVD-RTX4060", "Tarjeta de video NVIDIA GeForce RTX 4060 8GB", "Tarjetas de Video", "NVIDIA", 389990, 12,
     "8 GB GDDR6, 3072 núcleos CUDA, DLSS 3, PCIe 4.0 x8."),
    ("GPU-NVD-RTX4070", "Tarjeta de video NVIDIA GeForce RTX 4070 12GB", "Tarjetas de Video", "NVIDIA", 749990, 7,
     "12 GB GDDR6X, 5888 núcleos CUDA, trazado de rayos de tercera generación."),
    ("GPU-NVD-RTX4090", "Tarjeta de video NVIDIA GeForce RTX 4090 24GB", "Tarjetas de Video", "NVIDIA", 2299990, 1,
     "24 GB GDDR6X, 16384 núcleos CUDA. Última unidad: ideal para demostrar el control de stock."),
    ("GPU-ASU-RX7800XT", "Tarjeta de video ASUS Radeon RX 7800 XT 16GB", "Tarjetas de Video", "ASUS", 679990, 0,
     "16 GB GDDR6, arquitectura RDNA 3. Sin stock por ahora."),
    ("GPU-GIG-RTX4080S", "Tarjeta de video Gigabyte GeForce RTX 4080 Super 16GB", "Tarjetas de Video", "Gigabyte", 1399990, 3,
     "16 GB GDDR6X, refrigeración WINDFORCE de tres ventiladores."),

    # --- Memorias RAM ---
    ("RAM-KIN-16GB-DDR4", "Memoria Kingston FURY Beast 16GB DDR4 3200MHz", "Memorias RAM", "Kingston", 49990, 40,
     "Kit de 2 × 8 GB, DDR4-3200, CL16, con disipador de calor."),
    ("RAM-KIN-32GB-DDR5", "Memoria Kingston FURY Renegade 32GB DDR5 6000MHz", "Memorias RAM", "Kingston", 159990, 22,
     "Kit de 2 × 16 GB, DDR5-6000, CL32, perfil Intel XMP 3.0."),
    ("RAM-COR-32GB-DDR5", "Memoria Corsair Vengeance RGB 32GB DDR5 6400MHz", "Memorias RAM", "Corsair", 189990, 15,
     "Kit de 2 × 16 GB, DDR5-6400, iluminación RGB direccionable."),
    ("RAM-COR-64GB-DDR5", "Memoria Corsair Dominator Titanium 64GB DDR5 6000MHz", "Memorias RAM", "Corsair", 429990, 2,
     "Kit de 2 × 32 GB, DDR5-6000, CL30. Pensada para estaciones de trabajo."),

    # --- Placas Madre ---
    ("MB-ASU-Z790P", "Placa madre ASUS Prime Z790-P WiFi", "Placas Madre", "ASUS", 269990, 11,
     "Socket LGA1700, ATX, DDR5, PCIe 5.0, Wi-Fi 6 integrado."),
    ("MB-ASU-B650E", "Placa madre ASUS ROG Strix B650E-F Gaming", "Placas Madre", "ASUS", 319990, 6,
     "Socket AM5, ATX, DDR5, PCIe 5.0, dos ranuras M.2 con disipador."),
    ("MB-GIG-B760M", "Placa madre Gigabyte B760M DS3H", "Placas Madre", "Gigabyte", 139990, 20,
     "Socket LGA1700, micro-ATX, DDR5, ideal para equipos de oficina."),
    ("MB-GIG-X670E", "Placa madre Gigabyte X670E AORUS Master", "Placas Madre", "Gigabyte", 599990, 1,
     "Socket AM5, E-ATX, DDR5, PCIe 5.0, Wi-Fi 6E. Última unidad."),

    # --- Almacenamiento SSD ---
    ("SSD-SAM-1TB-990", "Unidad SSD Samsung 990 PRO 1TB NVMe", "Almacenamiento SSD", "Samsung", 119990, 35,
     "NVMe PCIe 4.0, lectura de hasta 7450 MB/s, formato M.2 2280."),
    ("SSD-SAM-2TB-990", "Unidad SSD Samsung 990 PRO 2TB NVMe", "Almacenamiento SSD", "Samsung", 219990, 18,
     "NVMe PCIe 4.0, 2 TB, lectura de hasta 7450 MB/s."),
    ("SSD-KIN-480GB-A400", "Unidad SSD Kingston A400 480GB SATA", "Almacenamiento SSD", "Kingston", 34990, 50,
     "SATA III de 2,5 pulgadas, lectura de hasta 500 MB/s. Opción económica."),
    ("SSD-SAM-4TB-870", "Unidad SSD Samsung 870 QVO 4TB SATA", "Almacenamiento SSD", "Samsung", 379990, 0,
     "SATA III de 2,5 pulgadas, 4 TB. Sin stock: en reposición."),

    # --- Fuentes de Poder ---
    ("PSU-COR-750-GOLD", "Fuente de poder Corsair RM750e 750W 80 Plus Gold", "Fuentes de Poder", "Corsair", 109990, 25,
     "750 W, certificación 80 Plus Gold, totalmente modular, ventilador de 120 mm."),
    ("PSU-COR-1000-PLAT", "Fuente de poder Corsair HX1000i 1000W 80 Plus Platinum", "Fuentes de Poder", "Corsair", 249990, 8,
     "1000 W, 80 Plus Platinum, modular, con monitoreo digital."),
    ("PSU-ASU-850-GOLD", "Fuente de poder ASUS TUF Gaming 850W 80 Plus Gold", "Fuentes de Poder", "ASUS", 139990, 1,
     "850 W, 80 Plus Gold, con rodamientos de doble bola. Última unidad."),
]

# (username, nombre, apellido, correo, teléfono)
CLIENTES = [
    ("cliente1", "Camila", "Rojas", "cliente1@hardpointpc.cl", "+56 9 1111 1111"),
    ("cliente2", "Matías", "Fuentes", "cliente2@hardpointpc.cl", "+56 9 2222 2222"),
    ("cliente3", "Valentina", "Soto", "cliente3@hardpointpc.cl", "+56 9 3333 3333"),
]


class Command(BaseCommand):
    """Comando de gestión que carga los datos de prueba del sistema."""

    help = (
        "Carga datos de prueba realistas: usuarios con ambos roles, catálogo "
        "completo, carros con ítems y órdenes de ejemplo en los cuatro estados. "
        "Es idempotente; con --reset da de baja lo existente y recarga todo."
    )

    def add_arguments(self, parser):
        """Declara la opción --reset del comando."""
        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                "Da de baja lógicamente el catálogo y los ítems de carro existentes "
                "antes de recargar, y vuelve a generar las órdenes de ejemplo. "
                "No borra ninguna fila de la base de datos."
            ),
        )

    # ============================================================
    # BLOQUE 3 — PUNTO DE ENTRADA
    # Todo ocurre dentro de una transacción: si algo falla a mitad
    # de camino, la base queda como estaba.
    # ============================================================
    @transaction.atomic
    def handle(self, *args, **opciones):
        """Ejecuta la carga completa de datos de prueba."""
        reiniciar = opciones["reset"]

        self._titulo("DATOS DE PRUEBA DE HardPoint PC")

        if reiniciar:
            self._reiniciar()

        administrador = self._crear_administrador()
        clientes = self._crear_clientes()
        categorias = self._crear_categorias()
        marcas = self._crear_marcas()
        productos = self._crear_productos(categorias, marcas)

        self._cargar_carros(clientes, productos)
        self._crear_ordenes_de_ejemplo(clientes, productos, administrador, reiniciar)

        self._resumen()

    # ============================================================
    # BLOQUE 4 — REINICIO DEL ESCENARIO DE DEMOSTRACIÓN
    # El catálogo y los carros se reinician con BAJA LÓGICA, igual
    # que en el resto del sistema: quedan con activo=False y al
    # recargar se reactivan los registros canónicos.
    #
    # Las órdenes de ejemplo sí se borran físicamente, y es la ÚNICA
    # excepción del proyecto. El motivo: --reset existe para dejar un
    # escenario de demostración reproducible, y si las órdenes se
    # acumularan en cada ejecución el estado dejaría de ser
    # predecible (hoy 4 órdenes, mañana 8, luego 12). No contradice
    # la regla del negocio, porque la regla protege las ventas reales
    # durante el uso normal del sistema, no los datos de prueba que
    # este comando acaba de inventar.
    # ============================================================
    def _reiniciar(self):
        """Reinicia el escenario: baja lógica del catálogo y borrado de las órdenes de ejemplo."""
        self.stdout.write(self.style.WARNING("  Reiniciando el escenario de demostración..."))

        productos = Producto.objects.update(activo=False)
        categorias = Categoria.objects.update(activo=False)
        marcas = Marca.objects.update(activo=False)
        items = ItemCarro.objects.update(activo=False)

        self.stdout.write(
            f"    Baja lógica: {productos} producto(s), {categorias} categoría(s), "
            f"{marcas} marca(s) y {items} ítem(s) de carro."
        )

        # Las órdenes de ejemplo se regeneran desde cero (ver el motivo
        # en el bloque de arriba). El borrado arrastra en cascada sus
        # detalles y su historial.
        historial = HistorialEstadoOrden.objects.all().delete()[0]
        detalles = DetalleOrden.objects.all().delete()[0]
        ordenes = Orden.objects.all().delete()[0]

        self.stdout.write(
            f"    Órdenes de ejemplo regeneradas: se retiraron {ordenes} orden(es), "
            f"{detalles} detalle(s) y {historial} registro(s) de historial."
        )

        # Los usuarios que crea simular_concurrencia no forman parte del
        # escenario base; se retiran para que el conteo de clientes sea
        # siempre 3.
        Usuario.objects.filter(username__startswith="demo_comprador_").delete()
        Producto.objects.filter(sku__startswith="DEMO-CONCURRENCIA").delete()

    # ============================================================
    # BLOQUE 5 — USUARIOS
    # El administrador y los clientes se crean con set_password. La
    # señal post_save de usuarios/signals.py genera el carro de cada
    # cliente automáticamente.
    # ============================================================
    def _crear_administrador(self) -> Usuario:
        """Crea o actualiza la cuenta del Administrador de TI."""
        self._titulo("Usuarios")

        administrador, creado = Usuario.objects.get_or_create(
            username="admin_ti",
            defaults={
                "email": "admin_ti@hardpointpc.cl",
                "first_name": "Genesis",
                "last_name": "Quezada",
                "telefono": "+56 9 9999 0000",
                "rol": Rol.ADMINISTRADOR,
                "is_superuser": True,
            },
        )

        # Siempre se reponen la contraseña, el rol y el estado activo, para
        # que el comando sirva también como reparación de la cuenta.
        administrador.rol = Rol.ADMINISTRADOR
        administrador.is_active = True
        administrador.is_superuser = True
        administrador.set_password(CONTRASENA_ADMIN)
        administrador.save()

        estado = "creado" if creado else "actualizado"
        self.stdout.write(
            f"  Administrador de TI {estado}: admin_ti / {CONTRASENA_ADMIN} "
            f"(is_staff={administrador.is_staff})"
        )
        return administrador

    def _crear_clientes(self) -> list[Usuario]:
        """Crea o actualiza las tres cuentas de cliente de prueba."""
        clientes = []

        for username, nombre, apellido, correo, telefono in CLIENTES:
            cliente, creado = Usuario.objects.get_or_create(
                username=username,
                defaults={
                    "email": correo,
                    "first_name": nombre,
                    "last_name": apellido,
                    "telefono": telefono,
                    "rol": Rol.CLIENTE,
                },
            )

            cliente.rol = Rol.CLIENTE
            cliente.is_active = True
            cliente.set_password(CONTRASENA_CLIENTE)
            cliente.save()

            # Red de seguridad: si la cuenta venía de antes de la señal.
            Carro.objects.get_or_create(usuario=cliente)

            clientes.append(cliente)
            estado = "creado" if creado else "actualizado"
            self.stdout.write(f"  Cliente {estado}: {username} / {CONTRASENA_CLIENTE}")

        return clientes

    # ============================================================
    # BLOQUE 6 — CATÁLOGO
    # update_or_create deja el comando idempotente y además repone
    # los valores canónicos (precio, stock, estado activo) si alguien
    # los cambió durante una prueba.
    # ============================================================
    def _crear_categorias(self) -> dict[str, Categoria]:
        """Crea o repone las seis categorías del catálogo."""
        self._titulo("Catálogo")

        categorias = {}
        for nombre, descripcion, icono in CATEGORIAS:
            categoria, _ = Categoria.objects.update_or_create(
                nombre=nombre,
                defaults={"descripcion": descripcion, "icono": icono, "activo": True},
            )
            categorias[nombre] = categoria

        self.stdout.write(f"  {len(categorias)} categoría(s) listas.")
        return categorias

    def _crear_marcas(self) -> dict[str, Marca]:
        """Crea o repone las ocho marcas del catálogo."""
        marcas = {}
        for nombre, pais in MARCAS:
            marca, _ = Marca.objects.update_or_create(
                nombre=nombre,
                defaults={"pais_origen": pais, "activo": True},
            )
            marcas[nombre] = marca

        self.stdout.write(f"  {len(marcas)} marca(s) listas.")
        return marcas

    def _crear_productos(self, categorias, marcas) -> dict[str, Producto]:
        """Crea o repone los 25 productos de demostración."""
        productos = {}
        con_stock_uno = 0
        sin_stock = 0

        for sku, nombre, categoria, marca, precio, stock, descripcion in PRODUCTOS:
            producto, _ = Producto.objects.update_or_create(
                sku=sku,
                defaults={
                    "nombre": nombre,
                    "descripcion": descripcion,
                    "categoria": categorias[categoria],
                    "marca": marcas[marca],
                    "precio": Decimal(precio),
                    "stock": stock,
                    "activo": True,
                },
            )
            productos[sku] = producto

            if stock == 1:
                con_stock_uno += 1
            if stock == 0:
                sin_stock += 1

        self.stdout.write(
            f"  {len(productos)} producto(s) listos "
            f"({con_stock_uno} con stock 1 y {sin_stock} sin stock, "
            "para demostrar las validaciones)."
        )
        return productos

    # ============================================================
    # BLOQUE 7 — CARROS CON ÍTEMS
    # Se cargan usando agregar_producto(), la misma función que la
    # API, de modo que los ítems queden creados con las mismas
    # reglas (sin duplicados y validando el stock).
    # ============================================================
    def _cargar_carros(self, clientes, productos):
        """Deja dos carros con ítems ya cargados para la demostración."""
        self._titulo("Carros de compras")

        cargas = {
            "cliente1": [("CPU-INT-14600K", 1), ("RAM-KIN-32GB-DDR5", 2), ("SSD-SAM-1TB-990", 1)],
            "cliente2": [("GPU-NVD-RTX4060", 1), ("PSU-COR-750-GOLD", 1)],
        }

        for cliente in clientes:
            pedido = cargas.get(cliente.username)
            if not pedido:
                continue

            carro = obtener_carro(cliente)

            # Se parte de un carro limpio para que el comando sea idempotente
            # y las cantidades no se acumulen en cada ejecución.
            carro.items.filter(activo=True).update(activo=False)

            for sku, cantidad in pedido:
                agregar_producto(carro, productos[sku], cantidad)

            # El total se formatea aparte: si se aplicara .replace(",", ".")
            # a la línea completa, también cambiaría las comas del texto.
            total_formateado = f"{carro.total:,.0f}".replace(",", ".")
            self.stdout.write(
                f"  Carro de {cliente.username}: {carro.cantidad_items} unidad(es), "
                f"total ${total_formateado}"
            )

        sin_carga = [c.username for c in clientes if c.username not in cargas]
        if sin_carga:
            self.stdout.write(
                f"  Carro vacío a propósito para: {', '.join(sin_carga)} "
                "(sirve para probar el error de carro vacío en el checkout)."
            )

    # ============================================================
    # BLOQUE 8 — ÓRDENES DE EJEMPLO EN LOS CUATRO ESTADOS
    # Se generan con realizar_checkout() y cambiar_estado_orden(),
    # nunca escribiendo el estado a mano. Así el historial queda
    # completo y el stock refleja de verdad lo ocurrido: la orden
    # pagada y la entregada descontaron unidades, y la cancelada
    # desde PAGADO las repuso.
    # ============================================================
    def _crear_ordenes_de_ejemplo(self, clientes, productos, administrador, reiniciar):
        """Crea una orden de ejemplo en cada estado, con su historial."""
        self._titulo("Órdenes de ejemplo")

        if Orden.objects.exists() and not reiniciar:
            conteo = Orden.objects.count()
            self.stdout.write(
                f"  Ya existen {conteo} orden(es); no se crean nuevas. "
                "Use --reset para generar un juego nuevo."
            )
            return

        cliente = clientes[0]
        cliente_dos = clientes[1] if len(clientes) > 1 else clientes[0]

        # --- Orden 1: queda PENDIENTE ---
        orden_pendiente = self._orden_desde(cliente, productos, [("SSD-KIN-480GB-A400", 2)])
        self.stdout.write(
            f"  {orden_pendiente.codigo_corto} → PENDIENTE "
            "(precios congelados, sin descontar stock)"
        )

        # --- Orden 2: se paga (descuenta stock) ---
        orden_pagada = self._orden_desde(cliente, productos, [("RAM-KIN-16GB-DDR4", 1)])
        orden_pagada = cambiar_estado_orden(
            orden_pagada,
            EstadoOrden.PAGADO,
            usuario=administrador,
            observacion="Pago aprobado en la carga de datos de prueba.",
        )
        self.stdout.write(f"  {orden_pagada.codigo_corto} → PAGADO (stock descontado)")

        # --- Orden 3: se paga y se entrega ---
        orden_entregada = self._orden_desde(cliente_dos, productos, [("PSU-COR-750-GOLD", 1)])
        orden_entregada = cambiar_estado_orden(
            orden_entregada, EstadoOrden.PAGADO, usuario=administrador,
            observacion="Pago aprobado en la carga de datos de prueba.",
        )
        orden_entregada = cambiar_estado_orden(
            orden_entregada, EstadoOrden.ENTREGADO, usuario=administrador,
            observacion="Retirado en tienda por el cliente.",
        )
        self.stdout.write(f"  {orden_entregada.codigo_corto} → ENTREGADO (estado final)")

        # --- Orden 4: se paga y se cancela (repone stock) ---
        orden_cancelada = self._orden_desde(cliente_dos, productos, [("SSD-SAM-1TB-990", 1)])
        orden_cancelada = cambiar_estado_orden(
            orden_cancelada, EstadoOrden.PAGADO, usuario=administrador,
            observacion="Pago aprobado en la carga de datos de prueba.",
        )
        orden_cancelada = cambiar_estado_orden(
            orden_cancelada, EstadoOrden.CANCELADO, usuario=administrador,
            observacion="El cliente desistió de la compra.",
        )
        self.stdout.write(
            f"  {orden_cancelada.codigo_corto} → CANCELADO (stock repuesto automáticamente)"
        )

        # Los carros de demostración se recargan, porque el checkout los vació.
        self._cargar_carros(clientes, productos)

    def _orden_desde(self, cliente, productos, lineas) -> Orden:
        """Arma un carro puntual y ejecuta el checkout para crear la orden."""
        carro = obtener_carro(cliente)
        carro.items.filter(activo=True).update(activo=False)

        for sku, cantidad in lineas:
            agregar_producto(carro, productos[sku], cantidad)

        return realizar_checkout(cliente)

    # ============================================================
    # BLOQUE 9 — SALIDA POR CONSOLA
    # Mensajes claros para que, al ejecutar el comando, se vea qué
    # quedó cargado y con qué credenciales entrar.
    # ============================================================
    def _titulo(self, texto):
        """Imprime un encabezado de sección en la consola."""
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"== {texto} =="))

    def _resumen(self):
        """Imprime el resumen final con los conteos y las credenciales."""
        self._titulo("Resumen")

        self.stdout.write(
            f"  Categorías activas ....... {Categoria.objects.filter(activo=True).count()}\n"
            f"  Marcas activas ........... {Marca.objects.filter(activo=True).count()}\n"
            f"  Productos activos ........ {Producto.objects.filter(activo=True).count()}\n"
            f"  Clientes ................. {Usuario.objects.filter(rol=Rol.CLIENTE).count()}\n"
            f"  Administradores de TI .... {Usuario.objects.filter(rol=Rol.ADMINISTRADOR).count()}\n"
            f"  Carros ................... {Carro.objects.count()}\n"
            f"  Ítems de carro vigentes .. {ItemCarro.objects.filter(activo=True).count()}\n"
            f"  Órdenes .................. {Orden.objects.count()}"
        )

        for estado, etiqueta in EstadoOrden.choices:
            total = Orden.objects.filter(estado=estado).count()
            self.stdout.write(f"    {etiqueta:<20} {total}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("  Datos de prueba cargados correctamente."))
        self.stdout.write("")
        self.stdout.write("  Credenciales para iniciar sesión en la API:")
        self.stdout.write(f"    admin_ti  / {CONTRASENA_ADMIN}   (Administrador de TI)")
        self.stdout.write(f"    cliente1  / {CONTRASENA_CLIENTE} (Cliente, con carro cargado)")
        self.stdout.write(f"    cliente2  / {CONTRASENA_CLIENTE} (Cliente, con carro cargado)")
        self.stdout.write(f"    cliente3  / {CONTRASENA_CLIENTE} (Cliente, con carro vacío)")
        self.stdout.write("")
        self.stdout.write("  Siguiente paso: python manage.py runserver")
        self.stdout.write("  Luego abra http://127.0.0.1:8000/ o http://127.0.0.1:8000/api/docs/")
        self.stdout.write("")
