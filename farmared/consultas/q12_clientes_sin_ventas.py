"""
Q12 - Clientes sin ventas registradas en el último año.

Motor: MongoDB. Se parte de clientes, no de ventas: si no, los que nunca
compraron no aparecerían. El $lookup une por id_cliente, el prefijo del
índice (id_cliente, fecha). $filter deja, de esas ventas, las del último
año; si considerar_anuladas es False, también saca las Anulada. Quedan los
que tienen esa lista vacía.

Criterio: el último año es [hoy - 365 días, hoy], inclusive. Por defecto
una venta cuenta en cualquier estado: Completada, Pendiente o Anulada. El
enunciado dice "ventas registradas" y no excluye anuladas. Con considerar_anuladas=True, una anulada dentro del año alcanza
para sacar al cliente: C004 queda afuera por V031 (2026-10-26, Anulada)
aunque su única Completada sea de 2025-09-18. Con False, las anuladas se
ignoran y C004 entra. Pendiente y Completada siguen contando en los dos
modos. Entra un cliente dado de baja. Entra tanto el que nunca compró como
el que sí compró, pero hace más de 365 días.

La consigna no exige este argumento. El default True es el resultado de
"ventas registradas". Desde la CLI llega como texto, igual que en q07.

Parámetros:
    considerar_anuladas (bool): si es False, una Anulada no cuenta como venta
    del año. Por defecto True. Acepta True/False y los textos true, false,
    1, 0, si y no.
Retorna: lista de dict con id_cliente, nombre, apellido, dni y activo,
ordenada por id_cliente. Depende de la fecha del sistema (fechas.hoy()).
"""
from datetime import timedelta

from farmared import fechas
from farmared.db import get_db

_TRUE = {"true", "1", "si", "sí", "yes"}
_FALSE = {"false", "0", "no"}


def _a_bool(valor):
    if isinstance(valor, bool):
        return valor
    texto = str(valor).strip().lower()
    if texto in _TRUE:
        return True
    if texto in _FALSE:
        return False
    raise ValueError("considerar_anuladas debe ser true o false")


def _en_el_anio(desde, considerar_anuladas):
    en_el_anio = {"$gte": ["$$venta.fecha", desde]}
    if considerar_anuladas:
        return en_el_anio
    return {"$and": [en_el_anio, {"$ne": ["$$venta.estado", "Anulada"]}]}


def ejecutar(considerar_anuladas=True):
    considerar_anuladas = _a_bool(considerar_anuladas)
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
