"""
Q02 - Ventas en estado 'Pendiente' con el farmacéutico asignado (nombre,
matrícula y sucursal) y el total.

Motor: MongoDB. La venta guarda id_farmaceutico como referencia, así que se
resuelve con dos $lookup (venta -> farmacéutico -> sucursal). El índice por
estado en ventas hace que el $match inicial no recorra toda la colección.

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
        {"$unwind": "$farm"},
        {"$lookup": {
            "from": "sucursales",
            "localField": "farm.id_sucursal",
            "foreignField": "_id",
            "as": "suc",
        }},
        {"$unwind": "$suc"},
        {"$sort": {"fecha": 1}},
        {"$project": {
            "_id": 0,
            "id_venta": "$_id",
            "fecha": 1,
            "id_cliente": 1,
            "total": 1,
            "farmaceutico": {
                "id": "$farm._id",
                "nombre": {"$concat": ["$farm.nombre", " ", "$farm.apellido"]},
                "matricula": "$farm.matricula",
                "sucursal": "$suc.nombre",
            },
        }},
    ]
    return list(get_db().ventas.aggregate(pipeline))
