"""
Q02 - Ventas en estado 'Pendiente' con el farmacéutico asignado (nombre,
matrícula y sucursal) y el total.

Motor: MongoDB. La venta guarda id_farmaceutico como referencia, así que se
resuelve con dos $lookup (venta -> farmacéutico -> sucursal). El índice por
estado en ventas hace que el $match inicial no recorra toda la colección.

Criterio: una venta pendiente cuyo farmacéutico (o su sucursal) no esté en la
base aparece igual, con esos datos en null, en vez de desaparecer del reporte
(mismo criterio que q11).

Parámetros: ninguno.
Retorna: lista de dict con id_venta, fecha, id_cliente, total y farmaceutico.
"""
from farmared.db import get_db


def ejecutar():
    pipeline = [
        {"$match": {"estado": "Pendiente"}},
        {"$lookup": {
            "from": "farmaceuticos",
            "localField": "id_farmaceutico",
            "foreignField": "_id",
            "as": "farm",
        }},
        {"$unwind": {"path": "$farm", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {
            "from": "sucursales",
            "localField": "farm.id_sucursal",
            "foreignField": "_id",
            "as": "suc",
        }},
        {"$unwind": {"path": "$suc", "preserveNullAndEmptyArrays": True}},
        {"$sort": {"fecha": 1, "_id": 1}},
        {"$project": {
            "_id": 0,
            "id_venta": "$_id",
            "fecha": 1,
            "id_cliente": 1,
            "total": 1,
            "farmaceutico": {
                "id": "$id_farmaceutico",
                "nombre": {"$ifNull": [{"$concat": ["$farm.nombre", " ", "$farm.apellido"]}, None]},
                "matricula": {"$ifNull": ["$farm.matricula", None]},
                "sucursal": {"$ifNull": ["$suc.nombre", None]},
            },
        }},
    ]
    return list(get_db().ventas.aggregate(pipeline))
