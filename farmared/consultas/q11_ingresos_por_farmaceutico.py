"""
Q11 - Ingresos totales por farmacéutico en el mes actual.

Motor: MongoDB. Se parte de ventas: el $match deja solo las Completadas del
mes y usa el índice de fecha. Después se agrupa por id_farmaceutico y el
nombre y la sucursal se resuelven con dos $lookup por _id.

Criterio: solo ventas 'Completada'. Pendiente y Anulada no suman ingresos.
El mes es [día 1, día 1 del mes siguiente), calculado con fechas.hoy(); el
día 1 entra y el día 1 del mes siguiente no. No aparecen los farmacéuticos
con cero: el enunciado no lo pide (a diferencia de q05) y la vista es de
ingresos. Un farmacéutico inactivo entra igual si cobró una venta del mes.
Si no está en el padrón, igual aparece, con nombre, matrícula y sucursal
nulos. Empate de ingresos: queda primero el id menor.

Parámetros: ninguno. Depende de la fecha del sistema.
Retorna: lista de dict con id_farmaceutico, nombre, matricula, sucursal e
ingresos, ordenada por ingresos descendente.
"""
from datetime import datetime

from farmared import fechas
from farmared.db import get_db


def _rango_mes(hoy):
    """[día 1 de este mes, día 1 del mes siguiente)."""
    desde = datetime(hoy.year, hoy.month, 1)
    if hoy.month == 12:
        hasta = datetime(hoy.year + 1, 1, 1)
    else:
        hasta = datetime(hoy.year, hoy.month + 1, 1)
    return desde, hasta


def ejecutar():
    desde, hasta = _rango_mes(fechas.hoy())
    pipeline = [
        # Completadas del mes: el día 1 entra, el día 1 del mes siguiente no
        {"$match": {
            "estado": "Completada",
            "fecha": {"$gte": desde, "$lt": hasta},
        }},
        {"$group": {
            "_id": "$id_farmaceutico",
            "ingresos": {"$sum": "$total"},
        }},
        {"$lookup": {
            "from": "farmaceuticos",
            "localField": "_id",
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
        {"$project": {
            "_id": 0,
            "id_farmaceutico": "$_id",
            "nombre": {"$ifNull": [
                {"$concat": ["$farm.nombre", " ", "$farm.apellido"]},
                None,
            ]},
            "matricula": {"$ifNull": ["$farm.matricula", None]},
            "sucursal": {"$ifNull": ["$suc.nombre", None]},
            "ingresos": 1,
        }},
        # empate: el id menor queda primero
        {"$sort": {"ingresos": -1, "id_farmaceutico": 1}},
    ]
    return list(get_db().ventas.aggregate(pipeline))
