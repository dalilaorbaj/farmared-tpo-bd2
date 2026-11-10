"""
Q15 - Actualización masiva del stock: dada una venta registrada, descuenta las
unidades de cada ítem de los lotes de la sucursal del farmacéutico, aplicando
FEFO y omitiendo lotes vencidos. Si el stock vigente no alcanza para algún
ítem, se rechaza la operación completa sin modificar ningún lote.

Motores: Redis (stock, con un script Lua atómico) + MongoDB (leer la venta, el
farmacéutico y marcar la venta como descontada).

Parámetros:
    id_venta (str): venta cuyo stock se descuenta.
    session: sesión de Mongo si se llama desde la transacción de q14 (opcional).
Retorna: TODO definir (ej. dict con lo descontado de cada lote, para poder
         compensar en q14 si el commit falla).
Errores: TODO definir las excepciones (venta inexistente, no Completada, ya
         descontada, stock insuficiente).
"""
from farmared import fechas
from farmared.db import get_db, get_redis

# TODO [MIÉ 11 · Lua] 1 (Lua): escribir el script. Lo que tiene que hacer, en este orden:
#   a) para cada ítem, recorrer el ZSET stock:{suc}:{prod} desde el score de hoy
#      (así se saltean los vencidos) y sumar lo disponible, en orden FEFO;
#   b) si ALGÚN ítem no alcanza -> devolver un error/código SIN haber escrito nada;
#   c) si todo alcanza -> recién ahí descontar: HINCRBY lote:{id} unidades -n
#      y ZADD lotes:unidades con las unidades nuevas (¡las dos cosas!);
#   d) devolver qué se descontó de cada lote (lo necesita la compensación).
# Pistas: los argumentos llegan como string (tonumber); redis.call; ver README
# sección "Estructura en Redis". Guía: docs/consigna/guia-tiago-q14-q15.md §1.3
SCRIPT_DESCONTAR = """
-- TODO
"""


def _leer_venta_y_sucursal(id_venta, session=None):
    """Devuelve (venta, id_sucursal)."""
    # TODO [JUE 12 · wrapper] 2: leer la venta (pasando session=session) y el farmacéutico para
    # obtener la sucursal. Validar: ¿existe? ¿es Completada? ¿ya tiene
    # stock_descontado? Pregunta de diseño: ¿qué ve esta lectura si la venta
    # todavía no está commiteada?
    raise NotImplementedError


def ejecutar(id_venta, session=None):
    r = get_redis()
    db = get_db()

    # TODO [JUE 12 · wrapper] 3: llamar a _leer_venta_y_sucursal.

    # TODO [JUE 12 · wrapper] 4: armar keys/args para el script a partir de los ítems.
    # Ojo: ¿qué pasa si el mismo producto aparece en dos ítems?
    hoy_score = fechas.a_score(fechas.hoy())  # noqa: F841 (lo usa el script)

    # TODO [JUE 12 · wrapper] 5: registrar y ejecutar el script (r.register_script) y traducir
    # su respuesta: stock insuficiente -> excepción clara.

    # TODO [JUE 12 · flag] 6: marcar stock_descontado = True en la venta (¿con session?).
    # Decidir quién lo marca: q15 o q14.

    # TODO [JUE 12 · wrapper] 7: devolver lo descontado por lote.
    raise NotImplementedError("q15 sin implementar")
