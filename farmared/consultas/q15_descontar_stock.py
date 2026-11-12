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
Errores: StockInsuficiente (hecha). TODO definir el resto (venta inexistente, no Completada, ya
         descontada, stock insuficiente).
"""
import json

from farmared import fechas
from farmared.db import get_db, get_redis

class StockInsuficiente(Exception):
    """Algún ítem no alcanza con el stock vigente. No se tocó ningún lote."""


# Script Lua: Redis lo ejecuta entero de forma atómica (nadie se cuela en el
# medio). Dos fases:
#   1) PLANIFICAR: recorre cada ZSET stock:{suc}:{prod} desde el score de hoy
#      (los vencidos quedan afuera) en orden FEFO y arma qué sacar de cada lote.
#      Si algún producto no alcanza, devuelve el faltante SIN haber escrito nada.
#   2) APLICAR: recién si todo alcanza, descuenta (HINCRBY en el HASH del lote
#      y ZADD en lotes:unidades, siempre las dos cosas).
# Redis no hace rollback de un script que falla a mitad de camino, por eso la
# fase de escritura va después de verificar todo.
#
# KEYS[i]    = stock:{suc}:{prod}  (un producto por clave, SIN repetidos: si
#              llegara la misma clave dos veces, se planificaría dos veces el
#              mismo lote; por eso ejecutar() agrupa los ítems por producto)
# ARGV[1]    = score de hoy (AAAAMMDD); ARGV[i+1] = cantidad pedida de KEYS[i]
# Devuelve un JSON: {"ok": false, "clave": ..., "faltan": n}
#               o   {"ok": true, "descontado": [{"lote": ..., "unidades": n}, ...]}
# (el descontado sirve para compensar en q14 si falla el commit).
SCRIPT_DESCONTAR = """
local hoy = ARGV[1]
local plan = {}

for i, clave in ipairs(KEYS) do
  local necesario = tonumber(ARGV[i + 1])
  local lotes = redis.call('ZRANGEBYSCORE', clave, hoy, '+inf')
  for _, id_lote in ipairs(lotes) do
    if necesario <= 0 then break end
    local disponibles = tonumber(redis.call('HGET', 'lote:' .. id_lote, 'unidades')) or 0
    local tomar = math.min(disponibles, necesario)
    if tomar > 0 then
      plan[#plan + 1] = {lote = id_lote, unidades = tomar}
      necesario = necesario - tomar
    end
  end
  if necesario > 0 then
    return cjson.encode({ok = false, clave = clave, faltan = necesario})
  end
end

for _, p in ipairs(plan) do
  local nuevas = redis.call('HINCRBY', 'lote:' .. p.lote, 'unidades', -p.unidades)
  redis.call('ZADD', 'lotes:unidades', nuevas, p.lote)
end
return cjson.encode({ok = true, descontado = plan})
"""


def descontar_lotes(r, id_sucursal, items):
    """Ejecuta el script. items: lista de {"id_producto", "cantidad"}.
    Devuelve [{"lote", "unidades"}, ...] o lanza StockInsuficiente."""
    # el mismo producto en dos ítems se suma: el script necesita una clave por producto
    por_producto = {}
    for it in items:
        por_producto[it["id_producto"]] = por_producto.get(it["id_producto"], 0) + int(it["cantidad"])

    keys = [f"stock:{id_sucursal}:{prod}" for prod in por_producto]
    args = [fechas.a_score(fechas.hoy())] + list(por_producto.values())

    script = r.register_script(SCRIPT_DESCONTAR)
    respuesta = json.loads(script(keys=keys, args=args))
    if not respuesta["ok"]:
        raise StockInsuficiente(
            f"Stock insuficiente en {respuesta['clave']}: faltan {respuesta['faltan']} unidades vigentes")
    return respuesta["descontado"]


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

    # TODO [JUE 12 · wrapper] 4-5: llamar a descontar_lotes(r, id_sucursal, venta["items"])
    # (ya hecho el miércoles: agrupa por producto, corre el Lua y lanza StockInsuficiente).

    # TODO [JUE 12 · flag] 6: marcar stock_descontado = True en la venta (¿con session?).
    # Decidir quién lo marca: q15 o q14.

    # TODO [JUE 12 · wrapper] 7: devolver lo descontado por lote.
    raise NotImplementedError("q15 sin implementar")
