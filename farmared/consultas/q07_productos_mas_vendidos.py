"""
Q07 - Top 5 productos más vendidos por unidades, solo ventas Completadas.

Motor: MongoDB. Se parte de ventas: el índice por estado deja afuera Pendiente
y Anulada antes de abrir los ítems. Cada ítem se suma con $unwind + $group y
el nombre se resuelve con un $lookup a productos.

Criterio: una venta cuenta solo si su estado es 'Completada'. Se suman las
cantidades de todos sus ítems, aunque el mismo producto aparezca más de una
vez o en ventas distintas. Si hay empate en unidades, queda primero el
id_producto menor, así el corte del top 5 no cambia entre ejecuciones.

Por defecto el ranking es de lo vendido: entra un producto inactivo y, si no
está en el catálogo, aparece con nombre null. Con solo_activos=True el filtro
se aplica antes del límite, así el top 5 se arma solo entre productos con
activo=True. Un producto sin ficha no cuenta como activo.

La consigna no exige este argumento. El default False es el resultado que
pide el enunciado. Desde la CLI llega como texto, igual que el resto de los
argumentos.

Parámetros:
    solo_activos (bool): si es True, el top 5 sale solo del catálogo activo.
    Por defecto False. Acepta True/False y los textos true, false, 1, 0, si y no.
Retorna: lista de hasta 5 dict con id_producto, nombre y unidades, ordenada
por unidades descendente.
"""
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
    raise ValueError("solo_activos debe ser true o false")


def _pipeline(solo_activos):
    etapas = [
        # el índice de estado descarta Pendiente y Anulada antes de abrir ítems
        {"$match": {"estado": "Completada"}},
        {"$unwind": "$items"},
        # un producto puede repetirse en la misma venta y en varias ventas
        {"$group": {
            "_id": "$items.id_producto",
            "unidades": {"$sum": "$items.cantidad"},
        }},
    ]
    lookup = {"$lookup": {
        "from": "productos",
        "localField": "_id",
        "foreignField": "_id",
        "as": "producto",
    }}
    if solo_activos:
        # el filtro va antes del límite: si no, el top 5 puede quedar corto
        etapas += [
            lookup,
            {"$unwind": "$producto"},
            {"$match": {"producto.activo": True}},
            {"$sort": {"unidades": -1, "_id": 1}},
            {"$limit": 5},
        ]
    else:
        etapas += [
            # el id desempató: con las mismas unidades, el id menor entra al top 5
            {"$sort": {"unidades": -1, "_id": 1}},
            {"$limit": 5},
            lookup,
            {"$unwind": {"path": "$producto", "preserveNullAndEmptyArrays": True}},
        ]
    etapas.append({"$project": {
        "_id": 0,
        "id_producto": "$_id",
        "nombre": {"$ifNull": ["$producto.nombre", None]},
        "unidades": 1,
    }})
    return etapas


def ejecutar(solo_activos=False):
    solo_activos = _a_bool(solo_activos)
    return list(get_db().ventas.aggregate(_pipeline(solo_activos)))
