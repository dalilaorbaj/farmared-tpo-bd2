"""
Q05 - Farmacéuticos activos con la cantidad de ventas de los últimos 60 días,
incluyendo a los que no tienen ninguna.

Motor: MongoDB. Se parte de farmaceuticos y no de ventas: el $lookup con let +
pipeline funciona como un left join, así que los que no vendieron quedan con
una lista vacía y cuentan 0. Las ventas de cada uno se buscan con el índice
(id_farmaceutico, fecha) y la sucursal con un $lookup por _id.

Criterio: el enunciado solo excluye las ventas 'Anulada', así que las
'Pendiente' cuentan. La ventana incluye el día de hoy - dias.

Parámetros:
    dias (int): tamaño de la ventana en días, por defecto 60. Depende de la
    fecha del sistema (fechas.hoy()).
Retorna: lista de dict con id_farmaceutico, nombre, matricula, sucursal y
cantidad_ventas, ordenada por cantidad_ventas descendente.
"""
from datetime import timedelta

from farmared import fechas
from farmared.db import get_db


def ejecutar(dias=60):
    desde = fechas.hoy() - timedelta(days=int(dias))
    pipeline = [
        # solo farmacéuticos activos
        {"$match": {"activo": True}},
        # left join: ventas de cada uno dentro de la ventana, sin las anuladas
        {"$lookup": {
            "from": "ventas",
            "let": {"id_farm": "$_id"},
            "pipeline": [
                {"$match": {
                    "$expr": {"$eq": ["$id_farmaceutico", "$$id_farm"]},
                    "fecha": {"$gte": desde},
                    "estado": {"$ne": "Anulada"},
                }},
            ],
            "as": "ventas",
        }},
        # trae el nombre de la sucursal
        {"$lookup": {
            "from": "sucursales",
            "localField": "id_sucursal",
            "foreignField": "_id",
            "as": "suc",
        }},
        {"$unwind": "$suc"},
        # cuenta las ventas y deja solo los campos del reporte
        {"$project": {
            "_id": 0,
            "id_farmaceutico": "$_id",
            "nombre": {"$concat": ["$nombre", " ", "$apellido"]},
            "matricula": 1,
            "sucursal": "$suc.nombre",
            "cantidad_ventas": {"$size": "$ventas"},
        }},
        # primero los que más vendieron
        {"$sort": {"cantidad_ventas": -1, "id_farmaceutico": 1}},
    ]
    return list(get_db().farmaceuticos.aggregate(pipeline))
