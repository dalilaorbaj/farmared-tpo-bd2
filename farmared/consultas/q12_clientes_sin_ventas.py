"""
Q12 - Clientes sin ventas registradas en el último año.

Motor: MongoDB. Se parte de clientes, no de ventas: si no, los que nunca
compraron no aparecerían. El $lookup une por id_cliente, el prefijo del
índice (id_cliente, fecha). $filter deja, de esas ventas, las del último
año; si considerar_anuladas es False, también saca las Anulada. Quedan los
que tienen esa lista vacía.

Criterio: cuentan las ventas desde hoy - 365 días (inclusive). El enunciado
habla de "ventas registradas", así que por defecto (True) una venta cuenta
en cualquier estado y una Anulada del último año alcanza para excluir al
cliente; con False las anuladas se ignoran. Entran los clientes dados de
baja, los que nunca compraron y los que compraron hace más de un año.

Parámetros:
    considerar_anuladas (bool): si es False, una Anulada no cuenta como venta
    del año. Por defecto True.
Retorna: lista de dict con id_cliente, nombre, apellido, dni y activo,
ordenada por id_cliente. Depende de la fecha del sistema (fechas.hoy()).
"""
from datetime import timedelta

from farmared import fechas
from farmared.argumentos import a_bool
from farmared.db import get_db


def _en_el_anio(desde, considerar_anuladas):
    en_el_anio = {"$gte": ["$$venta.fecha", desde]}
    if considerar_anuladas:
        return en_el_anio
    return {"$and": [en_el_anio, {"$ne": ["$$venta.estado", "Anulada"]}]}


def ejecutar(considerar_anuladas=True):
    considerar_anuladas = a_bool(considerar_anuladas, "considerar_anuladas")
    desde = fechas.hoy() - timedelta(days=365)
    pipeline = [
        # todas las ventas del cliente; el índice arranca por id_cliente
        {"$lookup": {
            "from": "ventas",
            "localField": "_id",
            "foreignField": "id_cliente",
            "as": "ventas",
        }},
        # alcanza con una venta del período para descartar al cliente
        {"$set": {
            "recientes": {"$filter": {
                "input": "$ventas",
                "as": "venta",
                "cond": _en_el_anio(desde, considerar_anuladas),
            }},
        }},
        {"$match": {"recientes": {"$size": 0}}},
        {"$project": {
            "_id": 0,
            "id_cliente": "$_id",
            "nombre": 1,
            "apellido": 1,
            "dni": 1,
            "activo": 1,
        }},
        {"$sort": {"id_cliente": 1}},
    ]
    return list(get_db().clientes.aggregate(pipeline))
