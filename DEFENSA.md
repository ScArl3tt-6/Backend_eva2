# DEFENSA.md — Dónde está implementado cada indicador

**Alumna:** Genesis Quezada Sanzana · **Sección:** IEC-C4-N2 · **Año:** 2026
**Proyecto:** HardPoint PC — E-commerce de componentes informáticos
**Asignatura:** Desarrollo Backend — Evaluación EVA-2

Este documento indica, para cada indicador de la rúbrica, el **archivo**, la
**clase o función exacta** y el **número de línea** donde está implementado, más
una explicación breve para defenderlo oralmente.

> Los números de línea corresponden al estado del repositorio en la entrega. Si
> edita un archivo, busque el nombre de la clase o función: ese no cambia.

---

## Índice

1. [Arquitectura, base de datos y modelos](#1-arquitectura-base-de-datos-y-modelos)
2. [JWT, claims y permisos](#2-jwt-claims-y-permisos)
3. [Carro de compras persistente](#3-carro-de-compras-persistente)
4. [Checkout y control de stock](#4-checkout-y-control-de-stock)
5. [Filtros y documentación OpenAPI](#5-filtros-y-documentación-openapi)
6. [Calidad, comentarios y footer](#6-calidad-comentarios-y-footer)
7. [Guion de la demostración de 5 minutos](#7-guion-de-la-demostración-de-5-minutos)
8. [Preguntas probables y cómo responderlas](#8-preguntas-probables-y-cómo-responderlas)

---

## 1. Arquitectura, base de datos y modelos

### 1.1 PostgreSQL, nunca SQLite

| Qué | Dónde |
|---|---|
| Configuración de la base | `tienda_hardware/settings.py` → **L145**, `DATABASES` |
| Guion de creación | `crear_bd.sql` (crea `tienda_hardware_db` con `ENCODING 'UTF8'` y da `CREATEDB` al rol) |
| Prueba que lo verifica | `core/tests.py` → `PruebasConfiguracion.test_el_motor_de_base_de_datos_es_postgresql` |

**Qué decir:** el motor es `django.db.backends.postgresql` y los parámetros de
conexión se leen del `.env` con `python-decouple`, así que cambiar de servidor no
exige tocar el código. La prueba automatizada comprueba además que la cadena del
motor no contenga «sqlite».

### 1.2 Los nueve modelos y su normalización

| Modelo | Archivo | Línea |
|---|---|---|
| `Rol` (TextChoices) | `usuarios/models.py` | **L20** |
| `Usuario` (AbstractUser) | `usuarios/models.py` | **L33** |
| `ModeloActivable` (base de baja lógica) | `catalogo/models.py` | **L28** |
| `Categoria` | `catalogo/models.py` | **L63** |
| `Marca` | `catalogo/models.py` | **L115** |
| `Producto` | `catalogo/models.py` | **L169** |
| `Carro` | `carro/models.py` | **L33** |
| `ItemCarro` | `carro/models.py` | **L100** |
| `EstadoOrden` (TextChoices) | `ordenes/models.py` | **L36** |
| `Orden` | `ordenes/models.py` | **L75** |
| `DetalleOrden` | `ordenes/models.py` | **L181** |
| `HistorialEstadoOrden` | `ordenes/models.py` | **L248** |

**Cómo defender la 3.ª forma normal:**

- **1FN** — todos los campos son atómicos: no hay columnas con listas ni con varios
  valores separados por comas.
- **2FN** — cada tabla tiene clave primaria simple (`BigAutoField`) y todos sus
  campos dependen por completo de ella.
- **3FN** — `Producto` (`catalogo/models.py` L169) guarda `categoria_id` y
  `marca_id`, **no** el nombre de la categoría ni el de la marca. El
  `pais_origen` vive en `Marca` (L115) porque depende de la marca, no del
  producto: guardarlo en `Producto` sería una dependencia transitiva.
- **Nada calculable se almacena**: el `total` del carro es una propiedad
  (`carro/models.py` **L73**), el `subtotal` del ítem también
  (`carro/models.py` **L162**), y el `total` de la orden es propiedad y anotación
  (`ordenes/models.py` **L131** y **L54**).

**La pregunta difícil — «¿`precio_unitario` no viola la 3FN?»**
Está en `ordenes/models.py` **L200**. No la viola: es un **hecho histórico**, el
precio que el cliente aceptó ese día, no una copia redundante del catálogo. Si
mañana sube el precio del producto, la venta ya cerrada no cambia. Guardarlo es
justamente lo que hace correcta la orden; leerlo del producto sería el error.
Prueba que lo demuestra: `ordenes/tests.py` →
`PruebasCheckout.test_checkout_congela_el_precio`.

### 1.3 Borrado lógico: nada se borra

| Qué | Dónde |
|---|---|
| Métodos `desactivar()` y `reactivar()` | `catalogo/models.py` → **L43** y **L49** |
| `DELETE` de la API que desactiva | `catalogo/views.py` → `BajaLogicaMixin.destroy` **L87** |
| Baja lógica de usuarios | `usuarios/views.py` → `UsuarioViewSet.destroy` (dentro de `UsuarioViewSet`, **L323**) |
| Baja lógica por HTML | `catalogo/views_html.py` → `panel_desactivar` |
| Pruebas | `catalogo/tests.py` → `PruebasBajaLogicaApi` y `PruebasHtmlCatalogo.test_desactivar_desde_el_html_no_borra_la_fila` |

**Qué decir:** «eliminar» es `activo = False` (`is_active = False` en usuarios). Las
pruebas lo verifican con `Model.objects.filter(pk=...).exists()`, es decir,
comprobando que la fila **siga** en la base de datos después del DELETE.

### 1.4 Restricciones y relaciones

- `UniqueConstraint` y `CheckConstraint` (con `condition=`, no el obsoleto
  `check=`): `catalogo/models.py` **L228** y siguientes, `carro/models.py` **L137**.
- `on_delete=models.PROTECT` en todas las relaciones de negocio: un producto
  vendido o una categoría con productos no se pueden borrar.
- Verificación en la base real:
  ```sql
  SELECT conname FROM pg_constraint WHERE contype IN ('c','u');
  ```
  Devuelve `producto_precio_positivo`, `producto_stock_no_negativo`,
  `item_unico_por_carro`, `detalle_unico_por_orden`, etc.

---

## 2. JWT, claims y permisos

### 2.1 El claim de rol dentro del token

| Qué | Dónde |
|---|---|
| Serializer que inserta los claims | `usuarios/tokens.py` → `TokenConRolSerializer` **L26** |
| Método sobrescrito | `usuarios/tokens.py` → `get_token()` **L30**; el claim se agrega en **L35** |
| Vista de login | `usuarios/views.py` → `LoginConRolView` **L157** |
| Configuración de JWT | `tienda_hardware/settings.py` → `SIMPLE_JWT` **L207** |
| Pruebas | `usuarios/tests.py` → `PruebasLoginJWT.test_token_decodificado_contiene_el_claim_rol` |

**Qué decir:** `get_token()` agrega `rol`, `username`, `email` y `nombre_completo`.
Como el access token se deriva del refresh, el claim viaja en los dos. Sin ese
claim, cada petición tendría que consultar la base solo para saber si quien llama
es cliente o administrador.

**Evidencia en vivo** — el payload decodificado de un login real:

```json
{
  "token_type": "access",
  "user_id": "6",
  "rol": "CLIENTE",
  "username": "cliente1",
  "email": "cliente1@hardpointpc.cl",
  "nombre_completo": "Camila Rojas"
}
```

Se puede mostrar en el momento con `GET /api/auth/perfil/`
(`usuarios/views.py` → `PerfilView` **L269**), que devuelve los claims leídos de
`request.auth`.

### 2.2 Los cuatro permisos reutilizables

| Permiso | Archivo | Línea | Para qué |
|---|---|---|---|
| `_tiene_rol()` (apoyo común) | `usuarios/permisos.py` | **L34** | Compara el claim del token **y** el rol de la base |
| `EsAdministrador` | `usuarios/permisos.py` | **L61** | Gestión del catálogo, usuarios y estados |
| `EsCliente` | `usuarios/permisos.py` | **L77** | Carro, checkout, pago, mis órdenes |
| `EsAdministradorOSoloLectura` | `usuarios/permisos.py` | **L93** | Catálogo: GET abierto, escritura del administrador |
| `EsPropietarioDeLaOrden` | `usuarios/permisos.py` | **L112** | Permiso de objeto: nadie paga la orden de otro |

**El detalle que vale la nota:** `_tiene_rol()` (**L34**) exige que coincidan el
claim `rol` del token firmado **y** el rol guardado en la base, y que la cuenta
siga activa. Es defensa en profundidad: si un administrador es degradado o dado de
baja, su token vigente deja de autorizar **de inmediato**, sin esperar a que
expire. Prueba:
`usuarios/tests.py` → `test_token_de_usuario_desactivado_deja_de_servir`.

### 2.3 Matriz de roles verificada con peticiones reales

| Petición | Rol | HTTP |
|---|---|---|
| `GET /api/productos/` | sin token | **200** |
| `GET /api/categorias/` | sin token | **200** |
| `POST /api/productos/` | sin token | **401** |
| `POST /api/productos/` | CLIENTE | **403** |
| `POST /api/productos/` | ADMINISTRADOR | **201** |
| `GET /api/carro/` | sin token | **401** |
| `GET /api/carro/` | CLIENTE | **200** |
| `GET /api/carro/` | ADMINISTRADOR | **403** |
| `GET /api/ordenes/` (todas) | CLIENTE | **403** |
| `GET /api/ordenes/` (todas) | ADMINISTRADOR | **200** |
| `PATCH /api/ordenes/{id}/estado/` | CLIENTE | **403** |
| `GET /api/usuarios/` | CLIENTE | **403** |

Pruebas: `usuarios/tests.py` → `PruebasMatrizDePermisos` (9 pruebas).

### 2.4 Logout con lista negra

| Qué | Dónde |
|---|---|
| Vista | `usuarios/views.py` → `LogoutView` **L217** |
| App instalada | `settings.py` → `rest_framework_simplejwt.token_blacklist` en `TERCEROS_APPS` |
| Prueba | `usuarios/tests.py` → `PruebasLogout.test_logout_invalida_el_refresh_token` |

**Qué decir:** el logout no es decorativo: el refresh token entra en la lista negra
y un `POST /api/auth/refresh/` posterior responde 401. Esto es lo que permite
demostrar que el carro **no** depende de la sesión.

---

## 3. Carro de compras persistente

### 3.1 El carro vive en PostgreSQL, ligado al usuario

| Qué | Dónde |
|---|---|
| Modelo con `OneToOneField` | `carro/models.py` → `Carro` **L33** |
| Ítems con restricción de unicidad | `carro/models.py` → `ItemCarro` **L100**, `item_unico_por_carro` **L137** |
| Señal que crea el carro | `usuarios/signals.py` → `crear_carro_del_cliente` **L28** |
| Registro de la señal | `usuarios/apps.py` → `UsuariosConfig.ready()` |

**Qué decir:** el carro es una relación **1 a 1** con el usuario. No está en la
sesión, ni en cookies, ni en `localStorage`: está en una tabla de PostgreSQL
ligada al `usuario_id`. Por eso sobrevive al logout, al cierre del navegador, a la
caída del servidor y al cambio de dispositivo.

La señal `post_save` crea el carro al registrarse un cliente. Se usa una señal, y
no la vista de registro, porque un usuario puede crearse desde la API, desde el
panel HTML, desde `seed_data`, desde `createsuperuser` o desde el admin: la señal
es el único punto por el que pasan todos esos caminos.

### 3.2 Demostración de la persistencia

**Prueba automatizada:** `carro/tests.py` →
`test_el_carro_sobrevive_al_logout_y_a_un_nuevo_login` **L102**.

**Evidencia con peticiones reales ya ejecutada:**

```
A) Carro antes del logout:
   [('RAM-KIN-32GB-DDR5', 2), ('CPU-INT-14600K', 1), ('SSD-SAM-1TB-990', 1)]
   cantidad_items: 4   total: 769960

B) POST /api/auth/logout/  →  "El token de refresco quedó invalidado"
C) POST /api/auth/refresh/ con ese token  →  HTTP 401

D) Nuevo login y GET /api/carro/:
   [('RAM-KIN-32GB-DDR5', 2), ('CPU-INT-14600K', 1), ('SSD-SAM-1TB-990', 1)]
   cantidad_items: 4   total: 769960   ← idéntico
```

### 3.3 La capa de servicios compartida

| Función | Archivo | Línea |
|---|---|---|
| `obtener_carro()` | `carro/servicios.py` | **L67** |
| `agregar_producto()` | `carro/servicios.py` | **L111** |
| `actualizar_cantidad()` | `carro/servicios.py` | **L156** |
| `quitar_producto()` | `carro/servicios.py` | **L185** |
| `vaciar_carro()` | `carro/servicios.py` | **L206** |
| Consumidor API | `carro/views.py` → `CarroView` **L84**, `ItemCarroView` **L218** |
| Consumidor HTML | `carro/views_html.py` → `carro_agregar`, `carro_actualizar`, … |

**Qué decir:** la API y las pantallas HTML llaman a **las mismas funciones**. No hay
una segunda implementación de las reglas, así que es imposible que el carro se
comporte de una manera desde Swagger y de otra desde el navegador.

### 3.4 Validación de duplicados

`agregar_producto()` (**L111**): si el producto ya está en el carro, **suma** la
cantidad al ítem existente en lugar de crear otra fila; si el ítem estaba dado de
baja, lo reactiva. El `UniqueConstraint(carro, producto)` lo respalda en la base.

Pruebas: `carro/tests.py` →
`test_agregar_el_mismo_producto_suma_sin_duplicar_filas` y
`test_la_base_de_datos_impide_el_item_duplicado`.

### 3.5 Agregar al carro NO descuenta stock

`agregar_producto()` solo **consulta** `producto.stock` para validar; no lo
modifica. La respuesta de la API lo declara explícitamente con
`"stock_descontado": false`.

Prueba: `carro/tests.py` → `PruebasAgregarAlCarro.test_agregar_no_descuenta_stock`.

---

## 4. Checkout y control de stock

Todo en `ordenes/servicios.py`, el módulo más importante del proyecto.

### 4.1 Excepciones propias y máquina de estados

| Qué | Línea |
|---|---|
| `CarroVacioError` | **L54** |
| `StockInsuficienteError` (con la lista de faltantes) | **L62** |
| `TransicionInvalidaError` | **L76** |
| `TRANSICIONES_PERMITIDAS` | **L100** |

```python
TRANSICIONES_PERMITIDAS = {
    PENDIENTE: {PAGADO, CANCELADO},
    PAGADO:    {ENTREGADO, CANCELADO},
    ENTREGADO: set(),   # estado final
    CANCELADO: set(),   # estado final
}
```

### 4.2 `realizar_checkout()` — congela precios, no toca stock

**`ordenes/servicios.py` L151.** Endpoint: `POST /api/ordenes/checkout/`
(`ordenes/views.py` → `CheckoutView` **L156**).

1. Bloquea el carro con `select_for_update()` (**L155**) para evitar un doble
   checkout simultáneo.
2. Valida que el carro no esté vacío y que los productos sigan activos.
3. Crea la `Orden` en `PENDIENTE` y un `DetalleOrden` por ítem, copiando el precio
   vigente a `precio_unitario`: **ese es el precio congelado**.
4. Registra el historial (`None → PENDIENTE`) y vacía el carro.
5. **No toca el stock.**

**Por qué no reserva stock:** una orden pendiente puede no pagarse nunca, y
reservar ahí dejaría productos bloqueados sin venta.

### 4.3 `pagar_orden()` — la operación crítica

**`ordenes/servicios.py` L231.** Endpoints: `POST /api/ordenes/{id}/pagar/`
(`PagarOrdenView` **L248**) y `PATCH /api/ordenes/{id}/estado/` a `PAGADO`.

| Paso | Línea | Qué hace |
|---|---|---|
| 1 | **L234** | `select_for_update()` sobre la orden y revalida que siga `PENDIENTE` |
| 2 | **L251** | Bloquea todas las filas de productos: `select_for_update().filter(id__in=ids).order_by("id")` |
| 3 | **L~265** | Con las filas bloqueadas relee el stock real y verifica producto por producto |
| 4 | — | Si falta alguno, lanza `StockInsuficienteError` → rollback total, la orden sigue `PENDIENTE`, la API responde **409** |
| 5 | — | Si alcanza, descuenta con `F("stock") - cantidad`, marca `PAGADO` y guarda `pagada_en` |

**Las cuatro razones por las que el stock nunca queda negativo** (guion de
respuesta):

1. `transaction.atomic()` — o pasa todo, o no pasa nada.
2. `select_for_update()` — el segundo pago **espera** el bloqueo del primero, y
   luego relee el stock ya descontado.
3. `order_by("id")` al bloquear — orden fijo, así dos pagos que comparten productos
   no se interbloquean.
4. `F("stock") - cantidad` — la resta la resuelve PostgreSQL, sin leer y escribir
   desde Python.
5. Y como última barrera, el `CheckConstraint stock >= 0` de la tabla.

### 4.4 Reposición al cancelar

`_reponer_stock()` — **`ordenes/servicios.py` L330**. Usa el mismo patrón que el
pago: bloqueo en orden fijo (**L336**) y suma con `F("stock") + cantidad`.
Lo invoca `cambiar_estado_orden()` (**L366**) cuando la transición es
`PAGADO → CANCELADO`.

### 4.5 Evidencia de las cuatro reglas, con peticiones reales

```
Producto CPU-INT-14600K — stock inicial: 18

1) POST /api/ordenes/checkout/
   estado: PENDIENTE | stock_descontado: false
   precio congelado del detalle: 329990
   stock después del checkout: 18   ← sin cambios

2) POST /api/ordenes/{id}/pagar/
   estado: PAGADO | stock_descontado: true
   stock después del pago: 17       ← descontado

3) Prueba del precio congelado:
   el administrador cambia el precio del catálogo a 450000
   precio CONGELADO en la orden: 329990
   precio ACTUAL del catálogo  : 450000
   total de la orden: 769960        ← la venta no cambió

4) Rechazo por stock insuficiente (otra orden, RTX4090 con stock 0):
   HTTP 409
   faltantes: [{"sku": "GPU-NVD-RTX4090", "solicitado": 1, "disponible": 0}]
   estado_de_la_orden: PENDIENTE
   stock tras el rechazo: 0         ← nada se movió

5) Cancelación de una orden PAGADA:
   stock tras pagar: 0
   PATCH estado=CANCELADO → "el stock se repuso automáticamente"
   stock tras cancelar: 1           ← repuesto

6) Transición inválida (ENTREGADO → PAGADO):
   HTTP 400 — "ENTREGADO es un estado final: ya no admite cambios"
   transiciones_permitidas: []
```

### 4.6 Concurrencia demostrada

| Qué | Dónde |
|---|---|
| Comando | `core/management/commands/simular_concurrencia.py` → `Command` **L68** |
| Lanzamiento de los hilos | mismo archivo → `_lanzar_pagos_simultaneos` **L196** |
| Prueba automatizada | `ordenes/tests.py` → `PruebasConcurrencia` **L765** |
| Prueba concreta | `test_dos_pagos_simultaneos_solo_uno_queda_pagado` **L797** |

```powershell
python manage.py simular_concurrencia
```

Salida real:

```
Stock inicial: 1 unidad
Orden D8324B07 de demo_comprador_1: PENDIENTE, pide 1 unidad
Orden 1C96743F de demo_comprador_2: PENDIENTE, pide 1 unidad

demo_comprador_1: PAGADO — Pago aprobado: el stock se descontó.
demo_comprador_2: RECHAZADO — Stock insuficiente. «...»: pidió 1 y hay 0.
      La transacción se revirtió por completo y la orden sigue en PENDIENTE.

Stock final del producto: 0

[OK] Exactamente un pago quedó PAGADO
[OK] El otro pago fue rechazado por falta de stock
[OK] El stock final es 0 (nunca -1)
```

**Detalle técnico que conviene mencionar:** la prueba usa `TransactionTestCase` y no
`TestCase`, porque `TestCase` envuelve cada prueba en una transacción y los otros
hilos no verían los cambios. Y cada hilo cierra su conexión con
`connection.close()`, porque Django asocia las conexiones al hilo que las abre.

---

## 5. Filtros y documentación OpenAPI

### 5.1 django-filter

| Qué | Dónde |
|---|---|
| `ProductoFilter` | `catalogo/filtros.py` → **L27** |
| `precio_min` (`lookup_expr="gte"`) | **L61** |
| `precio_max` (`lookup_expr="lte"`) | **L67** |
| `en_stock` (método propio) | **L75**, método `filtrar_en_stock` **L119** |
| `OrdenFilter` | `ordenes/filtros.py` → **L25** |
| Uso en la API | `catalogo/views.py` → `ProductoViewSet` **L308** (`filterset_class`) |
| Uso en el HTML | `catalogo/views_html.py` → `catalogo_publico` (el **mismo** FilterSet) |

Filtros disponibles: `categoria`, `categoria_nombre`, `marca`, `marca_nombre`,
`precio_min`, `precio_max`, `en_stock`, `sku`, `buscar`, más `search` y `ordering`
de DRF.

`search_fields = ["nombre", "sku", "descripcion", "marca__nombre"]` y
`ordering_fields = ["precio", "nombre", "stock", "creado_en"]`.

**Qué decir:** el mismo `ProductoFilter` alimenta `GET /api/productos/` y el
formulario GET de `/catalogo/`. Está definido una sola vez, así que los filtros se
comportan igual por los dos caminos; cambiarlos es editar un archivo.

Pruebas: `catalogo/tests.py` → `PruebasFiltrosProducto` (14 pruebas, una por
filtro).

### 5.2 OpenAPI 3 con drf-spectacular

| Qué | Dónde |
|---|---|
| Configuración | `tienda_hardware/settings.py` → `SPECTACULAR_SETTINGS` **L281** |
| Esquema | `tienda_hardware/urls.py` → **L80**, `/api/schema/` |
| Swagger UI | `tienda_hardware/urls.py` → **L82**, `/api/docs/` |
| ReDoc | `tienda_hardware/urls.py` → **L90**, `/api/redoc/` |
| Plantilla de Swagger con footer | `templates/drf_spectacular/swagger_ui_hardpoint.html` |
| Plantilla de ReDoc con footer | `templates/drf_spectacular/redoc_hardpoint.html` |
| Browsable API con footer | `templates/rest_framework/api.html` |

Ajustes exigidos, todos presentes: `TITLE` con el nombre comercial, `DESCRIPTION`
en español con los datos de la alumna, la matriz de roles y las credenciales,
`VERSION`, `SERVE_INCLUDE_SCHEMA=False`, `COMPONENT_SPLIT_REQUEST=True` y
`SWAGGER_UI_SETTINGS={"persistAuthorization": True}`.

**El botón Authorize funciona**: el esquema declara `jwtAuth` con `scheme: bearer`.
Prueba: `core/tests.py` → `test_el_esquema_declara_la_seguridad_bearer`.

**Ejemplos con `OpenApiExample`**: login, agregar al carro, checkout, pago, cambio
de estado y el error 409 por stock insuficiente. Están en los decoradores
`@extend_schema` de `usuarios/views.py`, `carro/views.py`, `catalogo/views.py` y
`ordenes/views.py`.

**El esquema se genera sin advertencias:**

```powershell
python manage.py spectacular --file esquema.yaml
```

Pruebas: `core/tests.py` → `PruebasDocumentacionApi` (7 pruebas), incluida
`test_el_esquema_documenta_los_filtros_de_productos`, que comprueba que los seis
filtros aparezcan como parámetros en Swagger.

---

## 6. Calidad, comentarios y footer

### 6.1 Comentarios por bloques

Cada archivo Python empieza con un bloque que explica su responsabilidad, y cada
sección lógica lleva su propio bloque con el formato exigido:

```python
# ============================================================
# NOMBRE DEL BLOQUE / RESPONSABILIDAD
# Qué hace, por qué se hace así y qué regla de negocio cumple.
# ============================================================
```

Las plantillas usan `{# ===== BLOQUE ===== #}`. Todas las clases y funciones tienen
docstring en español.

Ejemplos que conviene abrir en la defensa:

- `ordenes/servicios.py` — encabezado que explica las cuatro razones por las que el
  stock nunca queda negativo, y nueve bloques numerados.
- `tienda_hardware/settings.py` — 16 bloques, uno por área de configuración.
- `tienda_hardware/urls.py` — explica las tres capas anti-404 y por qué el orden de
  las rutas importa.
- `catalogo/models.py` — explica la normalización aplicada, regla por regla.

### 6.2 Footer con los datos de la alumna en todas las pantallas

| Qué | Dónde |
|---|---|
| Context processor | `core/context_processors.py` → `datos_alumno` **L23** |
| Registro | `settings.py` → `TEMPLATES["OPTIONS"]["context_processors"]` |
| Plantilla del footer | `templates/parciales/footer.html` → **L24** |
| Inclusión | `templates/base.html` (bloque 4) |
| Origen de los datos | `.env` → `settings.py` (bloque 2) |

**Qué decir:** el nombre, la sección y el año **no** están escritos en ninguna
plantilla. Viven en `.env`, `settings.py` los lee con `python-decouple` y el
context processor los entrega a todas las pantallas. Cambiar la sección es editar
una línea del `.env`.

Aparecen también en Swagger UI, en ReDoc, en la Browsable API de DRF y en la
pantalla de redirección.

Pruebas: `core/tests.py` → `PruebasFooterEnTodasLasPantallas` **L184**, que recorre
**27 pantallas** y comprueba en cada una el nombre, la sección, el año y los
enlaces a `/documentacion/` y `/api/docs/`.

### 6.3 Control total de rutas inexistentes

| Capa | Dónde |
|---|---|
| **1** Catch-all | `tienda_hardware/urls.py` → **L137**, `re_path(r"^.*$", redireccion_inicio)` |
| **2** handler404 | `tienda_hardware/urls.py` → **L146** |
| **3** Middleware | `core/middleware.py` → `RedireccionNoEncontradaMiddleware` **L29**, `process_exception` **L56** |
| Vista de la pantalla | `core/views.py` → `redireccion_inicio` **L317** |
| Plantilla | `templates/core/redireccion.html` |
| Helper que evita `get_object_or_404` | `core/utilidades.py` → `obtener_o_redirigir` **L27** |

**El detalle fino que conviene contar:** el catch-all `^.*$` hace que `resolve()`
encuentre **siempre** una coincidencia. Por eso `redireccion_inicio` (**L317**) no
se limita a comprobar que `resolve()` no lance `Resolver404`: compara además la
vista encontrada con la del propio catch-all. Sin esa comparación, `/asdf` se
redirigiría a `/asdf/` en un bucle en lugar de mostrar el aviso. Fue un error real
detectado al ejecutar el proyecto.

Verificación con 12 direcciones absurdas, todas **HTTP 200** con la pantalla de
aviso: `/asdf`, `/asdf/`, `/api/xyz`, `/api/xyz/`,
`/panel/productos/999999/`, `/catalogo/abc/`, `/%%%`,
`/esto/no/existe/nunca/`, `/panel/inventado/`, `/index.php`, `/wp-admin/`, `/.env`.

Y las rutas que existen con barra final redirigen a ellas (302):
`/catalogo` → `/catalogo/`, `/panel` → `/panel/`, conservando los parámetros de
consulta.

Pruebas: `core/tests.py` → `PruebasRutasInexistentes` **L75**.

### 6.4 Diseño y paleta en un solo archivo

| Qué | Dónde |
|---|---|
| Toda la paleta | `static/css/tema.css` → bloque 1, `:root` |
| Sobrescritura de Bootstrap | mismo archivo, `--bs-primary`, `--bs-secondary`, … |
| Filtro de moneda chilena | `core/templatetags/formato.py` → `pesos_chilenos` **L30** |
| Badges de estado | mismo archivo, `clase_estado` e `icono_estado` |

Ninguna plantilla lleva un color escrito a mano: cambiar la paleta es editar el
bloque `:root` de `tema.css`. El filtro `|clp` da formato chileno
(`$1.299.990`), armado a mano para no depender de la configuración regional del
sistema operativo, que en Windows cambia de una máquina a otra.

### 6.5 Errores JSON uniformes

`core/excepciones.py` → `manejador_excepciones_api` **L78**, registrado en
`REST_FRAMEWORK["EXCEPTION_HANDLER"]`. Todas las respuestas de error tienen la
misma forma:

```json
{ "error": true, "codigo": 404, "mensaje": "...", "detalle": {...}, "redireccion": "/" }
```

Los 404 de la API se traducen al español: Django los genera en inglés
(«No Producto matches the given query.») y el manejador reemplaza el mensaje,
conservando el original en `detalle`.

---

## 7. Guion de la demostración de 5 minutos

**Antes de empezar:** tener el servidor levantado (`python manage.py runserver`),
la base con `seed_data` cargado, y abiertas dos pestañas:
`http://127.0.0.1:8000/` y `http://127.0.0.1:8000/api/docs/`.

### Minuto 1 — Presentación y arquitectura (0:00 – 1:00)

1. Abrir `/` y señalar el footer: **nombre, sección y año**, con el enlace a la
   documentación. Decir que vienen del `.env` por un context processor.
2. Señalar las estadísticas: son consultas reales al ORM, no valores fijos.
3. Abrir `/documentacion/` y mostrar la **matriz de roles** y el **flujo de negocio**.
4. Frase clave: *«La base está en tercera forma normal y nada de negocio se borra:
   eliminar es activo igual a falso.»*

### Minuto 2 — JWT y el claim de rol (1:00 – 2:00)

1. En Swagger, ejecutar `POST /api/auth/login/` con `cliente1` / `Cliente.2026`.
2. Copiar el `access` y pegarlo en **jwt.io** o ejecutar `GET /api/auth/perfil/`.
   Mostrar el claim **`"rol": "CLIENTE"`**.
3. Pulsar **Authorize**, pegar el token.
4. Intentar `POST /api/productos/` → **403**. Decir: *«El permiso
   `EsAdministradorOSoloLectura` compara el claim del token con el rol de la base
   de datos.»*
5. Sin token, `GET /api/productos/` → **200**; `POST` → **401**.

### Minuto 3 — El carro persistente (2:00 – 3:00)

1. `GET /api/carro/`: mostrar los ítems, los subtotales y el total.
2. `POST /api/carro/` con `{"producto": X, "cantidad": 2}` **dos veces**: señalar
   que la cantidad **se suma** y que no hay una segunda línea.
3. Señalar en la respuesta `"stock_descontado": false`.
4. `POST /api/auth/logout/` con el refresh → luego `POST /api/auth/refresh/` con ese
   mismo token → **401**.
5. Volver a iniciar sesión, `GET /api/carro/`: **el carro está idéntico**.
6. Frase clave: *«El carro es una relación uno a uno con el usuario en PostgreSQL.
   No está en la sesión ni en cookies, por eso sobrevive al logout.»*

### Minuto 4 — Checkout, pago y stock (3:00 – 4:00)

1. Anotar el stock del producto (por ejemplo 18).
2. `POST /api/ordenes/checkout/` → orden `PENDIENTE`, precios congelados,
   `stock_descontado: false`. Volver a consultar el producto: **el stock sigue en 18**.
3. `POST /api/ordenes/{id}/pagar/` → `PAGADO`. Consultar el producto: **17**.
4. **El momento fuerte:** cambiar el precio del catálogo con
   `PATCH /api/productos/{id}/` y `{"precio": 450000}`, y volver a abrir la orden:
   el `precio_unitario` sigue en 329990 y el total no cambió.
5. Entrar como `admin_ti`, `PATCH /api/ordenes/{id}/estado/` con `ENTREGADO`.
   Luego intentar pasarla a `PAGADO` → **400** con las transiciones permitidas.

### Minuto 5 — Concurrencia y cierre (4:00 – 5:00)

1. En la consola: `python manage.py simular_concurrencia`.
2. Leer la salida: uno `PAGADO`, uno `RECHAZADO`, **stock final 0, nunca -1**.
3. Explicar en una frase: *«`pagar_orden` abre una transacción, bloquea las filas
   de los productos con `select_for_update` en orden fijo por id, relee el stock ya
   descontado y descuenta con `F`. El segundo comprador espera el bloqueo y es
   rechazado limpiamente.»*
4. Mostrar `python manage.py test` → **212 pruebas, OK**.
5. Cerrar escribiendo `/asdf` en el navegador: aparece la pantalla de redirección
   con la cuenta regresiva. *«Ninguna dirección muestra un 404: hay tres capas de
   protección.»*

---

## 8. Preguntas probables y cómo responderlas

**«¿Por qué el carro no guarda el precio?»**
Porque el precio vigente depende del producto: duplicarlo en `ItemCarro` sería una
dependencia transitiva que la 3FN prohíbe, y además quedaría desactualizado al
cambiar el precio. El carro debe reflejar siempre el precio actual del catálogo. El
precio se congela recién en el checkout, en `DetalleOrden.precio_unitario`, porque
ahí pasa a ser un hecho histórico.

**«¿Y si dos clientes compran el último producto exactamente a la vez?»**
No puede ocurrir. `pagar_orden()` (`ordenes/servicios.py` L231) bloquea las filas de
los productos con `select_for_update()`. El segundo hilo se queda esperando en ese
bloqueo; cuando el primero confirma, el segundo relee el stock **ya descontado**,
ve que no alcanza y lanza `StockInsuficienteError`, que revierte su transacción. Lo
demuestra `python manage.py simular_concurrencia` y la prueba
`PruebasConcurrencia`.

**«¿Por qué el total no está guardado en la orden?»**
Porque es calculable a partir del detalle: guardarlo sería redundante (3FN) y podría
quedar inconsistente. Se expone como propiedad (`ordenes/models.py` L131) y como
anotación de consulta con `Sum(F("cantidad") * F("precio_unitario"))`
(`OrdenQuerySet.con_total`, L54), que es la que se usa en los listados para no
consultar el detalle de cada orden por separado.

**«¿Por qué las pantallas HTML no tienen login?»**
Porque así lo pide el enunciado: la seguridad por roles vive en la API JWT. Las
pantallas usan el ORM y llaman a las mismas funciones de servicio, de modo que el
control de stock y de concurrencia es idéntico por ambos caminos.

**«¿Qué pasa si alguien salta los serializers?»**
La base de datos lo rechaza. Los `CheckConstraint` (`precio > 0`, `stock >= 0`,
`cantidad >= 1`) y los `UniqueConstraint` están creados en PostgreSQL. Lo
comprueban las pruebas de `catalogo/tests.py` →
`PruebasRestriccionesBaseDeDatos`, que esperan un `IntegrityError`.

**«¿Por qué `is_staff` se sincroniza con el rol?»**
Para que un Administrador de TI funcione tanto con los permisos propios del
proyecto (que leen el claim `rol`) como con los de DRF basados en `is_staff`
(`IsAdminUser`), sin duplicar la fuente de verdad: esa sigue siendo el campo `rol`.
Está en `Usuario.save()` (`usuarios/models.py` L79).

**«¿Cómo se garantiza que un cliente no vea las órdenes de otro?»**
El filtro se aplica en `get_queryset()` (`MisOrdenesViewSet`, `ordenes/views.py`
L314), sobre `self.request.user`, **no** con un parámetro de la petición: es
imposible pedir las órdenes de otro. Para el pago existe además el permiso de
objeto `EsPropietarioDeLaOrden` (`usuarios/permisos.py` L112). Pruebas:
`PruebasMisOrdenes`.
