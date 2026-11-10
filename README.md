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

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

GitHub Actions corre esa misma suite en cada push y cada pull request. El workflow levanta un Mongo 7 y lo pasa por `MONGO_URI`, así q03, q05 y q13 también corren ahí.

La mayoría corre en memoria y no necesita Mongo ni Redis instalados. q03, q05 y q13 sí corren sobre un Mongo real: q03 y q05 porque usan `$unionWith` y un `$lookup` con subpipeline, y q13 para probar el `$jsonSchema` y el índice único de `dni`. Para eso el test busca un servidor en este orden:

1. `MONGO_URI`, si está definida (en el Codespace ya apunta al Mongo del compose).
2. `localhost:27017`.
3. Si no hay ninguno, levanta uno para la corrida: el binario `mongod`, o un contenedor `mongo:7`.

Usa una base aparte, `farmared_test`, y la borra al terminar cada test. Las otras bases del servidor no se tocan. Si el Mongo lo arrancó la corrida, también lo apaga al final.

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
tests/                tests en memoria y, en integracion/, q03, q05 y q13 contra Mongo
```

## Notas

- Las consultas que dependen de la fecha ("hoy", "mes actual", "últimos 60 días") usan la fecha del sistema (`farmared/fechas.py → hoy()`), no fechas fijas.
- Los datasets toman como referencia el 13/10/2026; los registros adicionales tienen fechas hasta principios de noviembre 2026.
- Integridad referencial: Mongo no tiene claves foráneas, se valida en la carga (`carga.validar`) y en los servicios de escritura antes de insertar/modificar. Además cada colección tiene un `$jsonSchema` que valida tipos y valores permitidos, e índices únicos en `dni`, `matricula` y `cuit`.
