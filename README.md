# FarmaRed - TPO Bases de Datos II

Sistema de backoffice para una red de farmacias con persistencia políglota (MongoDB + Redis).
2do cuatrimestre 2026.

**Integrantes**
- Florencia Cecotto
- Facundo Ignacio Krens Licitra
- Dalila Orbaj
- Tiago Heras

## Motores

| Motor | Qué guarda | Por qué |
|---|---|---|
| MongoDB 7 | clientes, sucursales, farmacéuticos, proveedores, productos, recetas y ventas (con el detalle embebido) | las ventas son jerárquicas (cabecera + ítems variables) y se leen siempre completas; el resto son entidades con atributos propios que se consultan, modifican y dan de baja lógica. Aggregation pipeline para los reportes y transacciones multi-documento para registrar ventas. |
| Redis 7 | stock por lote + cache del catálogo | el stock se actualiza todo el tiempo y en forma concurrente; los lotes de cada sucursal/producto se guardan en un sorted set ordenado por vencimiento (orden FEFO) y el descuento se puede hacer atómico. El catálogo se lee mucho y cambia poco, se cachea con TTL. |

Mongo corre como replica set de un nodo (`rs0`) porque si no, no permite transacciones.

### Estructura en Redis

```
lote:{id_lote}                      HASH  id_lote, id_producto, id_sucursal, nro_lote, unidades, vencimiento
stock:{id_sucursal}:{id_producto}   ZSET  id_lote -> vencimiento (AAAAMMDD)
lotes:unidades                      ZSET  id_lote -> unidades
cache:q01:productos_activos         STRING (JSON, TTL 10 min)
```

## Cómo levantarlo

### GitHub Codespaces (recomendado)

1. En el repo: **Code → Codespaces → Create codespace on main**.
2. Esperar a que termine de construir. El devcontainer levanta Mongo y Redis con docker compose, instala las dependencias y **carga los datos automáticamente** (`postCreateCommand`).
3. Ya se pueden correr las consultas (ver abajo).

Si por algún motivo la carga falló o se quiere volver al estado inicial:

```bash
python main.py cargar
```

### Local (sin Codespaces)

Requiere Docker y Python 3.12.

```bash
docker compose -f .devcontainer/docker-compose.yml up -d mongo redis
pip install -r requirements.txt
cp .env.example .env
python main.py cargar
```

## Carga de datos

`python main.py cargar` (o `python -m farmared.carga`) lee los CSV de:

- `data/originales/` → los datasets provistos por la cátedra (sin modificar).
- `data/adicionales/` → nuestros registros extra (mínimo 10 por archivo).

Antes de insertar valida que no haya ids repetidos, que todas las referencias existan (ej. que el `id_cliente` de una venta exista en clientes) y que el total de cada venta sea igual a la suma de sus ítems. Si algo falla no carga nada.

La carga es idempotente: borra y recrea las colecciones (con sus validadores e índices) y las claves de stock, así que se puede correr las veces que haga falta.

Algunos casos que agregamos en los datos adicionales para probar las consultas:

- lotes vencidos (L020, L031), próximos a vencer (L019, L025) y con stock bajo o en cero (L029, L034)
- varios lotes del mismo producto en la misma sucursal con distinto vencimiento (ibuprofeno en Palermo) para probar FEFO
- recetas vencidas, recetas de tratamiento prolongado atrasadas y una receta vigente de un cliente dado de baja
- clientes sin compras (C010, C013) y con su última compra hace más de un año (C014)
- ventas pendientes, una anulada, ventas del mes actual y una venta hecha por un farmacéutico que ya no está activo
- una droguería extra con su director técnico (no puede registrar ventas)
- una sucursal y un proveedor dados de baja

## Ejecutar las consultas

```bash
python main.py            # lista las consultas disponibles
python main.py q01
python main.py q08 30     # argumentos opcionales
```

| # | Comando | Descripción | Motor |
|---|---|---|---|
| 1 | `python main.py q01 [usar_cache]` | Productos activos con datos del proveedor | Mongo + cache Redis |
| 2 | `python main.py q02` | Ventas pendientes con farmacéutico y total | Mongo |
| 3 | `python main.py q03 <id_cliente>` | Historial completo de un cliente | Mongo |
| 4 | `python main.py q04` | Clientes con más de una receta | Mongo |
| 5 | `python main.py q05 [dias]` | Farmacéuticos activos y sus ventas en los últimos 60 días | Mongo |
| 6 | `python main.py q06` | Tratamientos prolongados vigentes con dispensa atrasada | Mongo |
| 7 | `python main.py q07 [solo_activos]` | Top 5 productos más vendidos por unidades | Mongo |
| 8 | `python main.py q08 [limite]` | Lotes con menos de 50 unidades | Redis + Mongo |
| 9 | `python main.py q09 [monto_max]` | Ventas libres con total < $5000 | Mongo |
| 10 | `python main.py q10 <id_sucursal> [contar_repetidos]` | Clientes atendidos en una sucursal | Mongo |
| 11 | `python main.py q11` | Ingresos por farmacéutico en el mes actual | Mongo |
| 12 | `python main.py q12 [considerar_anuladas]` | Clientes sin ventas en el último año | Mongo |
| 13 | `python main.py q13 alta '<json>'`<br>`python main.py q13 modificar <id_cliente> '<json>'`<br>`python main.py q13 baja <id_cliente>` | ABM de clientes (alta validada, modificación de contacto y cobertura, baja lógica) | Mongo |
| 14 | `python main.py q14 '<json>'` | Registrar venta Completada con validaciones, receta y stock | Mongo (transacción) + Redis |
| 15 | `python main.py q15 <id_venta>` | Descontar stock de una venta (FEFO, todo o nada) | Redis (Lua) + Mongo |

Cada consulta está en su propio módulo en `farmared/consultas/qXX_*.py`, con un docstring que explica qué hace, parámetros, qué devuelve y qué motor usa.

### Registrar una venta (q14) y descontar su stock (q15)

```bash
# venta con receta: descuenta del lote que vence antes y completa la receta RC015
python main.py q14 '{"id_cliente": "C009", "id_farmaceutico": "F019", "medio_pago": "Obra social", "id_receta": "RC015", "items": [{"id_producto": "PRD003", "cantidad": 1}]}'

# venta libre: saltea el lote vencido (L020) y consume primero el que vence antes (L019, después L004)
python main.py q14 '{"id_cliente": "C009", "id_farmaceutico": "F019", "medio_pago": "Efectivo", "items": [{"id_producto": "PRD002", "cantidad": 10}]}'

# rechazo por stock: no queda venta, la receta no cambia y no se toca ningún lote
python main.py q14 '{"id_cliente": "C009", "id_farmaceutico": "F019", "medio_pago": "Efectivo", "items": [{"id_producto": "PRD002", "cantidad": 120}]}'

# q15 sobre una venta ya descontada: se rechaza, no descuenta dos veces
python main.py q15 V017
```

Los precios y el total no se mandan: salen del catálogo. Si la venta se rechaza, la salida es `{"ok": false, "error": "<motivo>"}` y no queda nada escrito.

q14 y q15 funcionan integrados aunque Mongo y Redis no comparten transacción:

1. q14 valida todo con lecturas (cliente, farmacéutico y sucursal, productos, receta).
2. Abre una transacción de Mongo: inserta la venta y actualiza la receta.
3. Dentro de la transacción llama a q15, que descuenta el stock en Redis con un script Lua. El script primero verifica que alcance para todos los ítems y recién después descuenta, todo en un solo paso atómico. Si no alcanza, no escribió nada: q14 aborta la transacción y no queda ni la venta ni el cambio en la receta.
4. Commit. Si falla después de que Redis ya descontó, q14 devuelve a cada lote lo que q15 informó (compensación).

Redis va último porque es lo único que la transacción de Mongo no puede deshacer. Cada venta guarda `stock_descontado` para que q15 no la descuente dos veces; las Completadas de los CSV se cargan con el flag en `true` porque ese stock ya es el actual, así que q15 sola solo aplica a una venta Completada que haya quedado sin descontar.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

GitHub Actions corre esa misma suite en cada push y cada pull request. El workflow levanta un Mongo 7 (lo pasa por `MONGO_URI`) y un Redis 7, así q03, q05, q13 y q15 también corren ahí.

La mayoría corre en memoria y no necesita Mongo ni Redis instalados. q03, q05 y q13 sí corren sobre un Mongo real: q03 y q05 porque usan `$unionWith` y un `$lookup` con subpipeline, y q13 para probar el `$jsonSchema` y el índice único de `dni`. Para eso el test busca un servidor en este orden:

1. `MONGO_URI`, si está definida (en el Codespace ya apunta al Mongo del compose).
2. `localhost:27017`.
3. Si no hay ninguno, levanta uno para la corrida: el binario `mongod`, o un contenedor `mongo:7`.

Usa una base aparte, `farmared_test`, y la borra al terminar cada test. Las otras bases del servidor no se tocan. Si el Mongo lo arrancó la corrida, también lo apaga al final.

q14 y q15 se prueban contra servicios reales, porque el script Lua y las transacciones no existen en memoria:

- q15 necesita un Redis (`REDIS_HOST`/`REDIS_PORT`, por defecto `localhost:6379`). Usa la base 15 y la vacía en cada test; el stock cargado está en la base 0 y no se toca.
- La integración de q14 necesita además un Mongo con replica set (el del Codespace lo es). Usa la base `farmared_test_q14` con los validadores reales. Incluye ventas simultáneas, la falla del commit con su compensación y dos ventas compitiendo por la misma receta.

Si falta alguno de los dos servicios esos tests se saltean, no fallan. El Mongo de GitHub Actions no es replica set, así que la integración de q14 corre en el Codespace y no en el workflow.

## Estructura del repo

```
.devcontainer/        devcontainer + docker-compose (app, mongo, redis)
.github/workflows/    tests en cada push y pull request
data/originales/      CSV de la cátedra
data/adicionales/     nuestros registros
farmared/
  config.py           variables de entorno
  db.py               conexiones
  fechas.py           helpers de fechas (hoy, scores de vencimiento)
  argumentos.py       convierte los argumentos que llegan como texto (true/false)
  esquema_mongo.py    validadores e índices de cada colección
  carga.py            script de carga
  consultas/          una consulta/servicio por archivo (q01 ... q15)
main.py               CLI para correr las consultas
tests/                tests en memoria y, en integracion/, q03, q05, q13, q14 y q15 contra Mongo y Redis
```

## Notas

- Las consultas que dependen de la fecha ("hoy", "mes actual", "últimos 60 días") usan la fecha del sistema (`farmared/fechas.py → hoy()`), no fechas fijas.
- Los datasets toman como referencia el 13/10/2026; los registros adicionales tienen fechas hasta principios de noviembre 2026.
- Integridad referencial: Mongo no tiene claves foráneas, se valida en la carga (`carga.validar`) y en los servicios de escritura antes de insertar/modificar. Además cada colección tiene un `$jsonSchema` que valida tipos y valores permitidos, e índices únicos en `dni`, `matricula` y `cuit`.
