"""
Q01 - Productos activos con todos los datos de su proveedor.

Motor: MongoDB ($lookup productos -> proveedores) + Redis como cache.

El catálogo cambia poco y se lee mucho, así que el resultado se guarda en
Redis con un TTL. Si está en cache se devuelve directo sin ir a Mongo.
Cualquier servicio que modifique productos o proveedores tiene que llamar a
invalidar_cache().

Parámetros:
    usar_cache (bool): si es False va siempre a Mongo (y refresca la cache).
    Desde la terminal llega como texto ("false").
Retorna:
    lista de productos (dict) con el proveedor embebido en "proveedor".
"""
import json

from farmared.argumentos import a_bool
from farmared.db import get_db, get_redis

CLAVE_CACHE = "cache:q01:productos_activos"
TTL_SEGUNDOS = 600


def consultar_mongo():
    pipeline = [
        {"$match": {"activo": True}},
        {"$lookup": {
            "from": "proveedores",
            "localField": "id_proveedor",
            "foreignField": "_id",
            "as": "proveedor",
        }},
        {"$unwind": {"path": "$proveedor", "preserveNullAndEmptyArrays": True}},
        {"$sort": {"_id": 1}},
    ]
    return list(get_db().productos.aggregate(pipeline))


def invalidar_cache():
    get_redis().delete(CLAVE_CACHE)


def ejecutar(usar_cache=True):
    usar_cache = a_bool(usar_cache, "usar_cache")
    r = get_redis()
    if usar_cache:
        guardado = r.get(CLAVE_CACHE)
        if guardado:
            return json.loads(guardado)

    productos = consultar_mongo()
    r.set(CLAVE_CACHE, json.dumps(productos, ensure_ascii=False), ex=TTL_SEGUNDOS)
    return productos
