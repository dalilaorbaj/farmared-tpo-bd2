"""
Q10 - Clientes atendidos en una sucursal, a través del farmacéutico que
registró la venta.

Motor: MongoDB. La venta no guarda la sucursal: se llega por el farmacéutico.
Se parte de los farmacéuticos de esa sucursal (el índice es id_sucursal, sin
filtrar activo) y cada uno busca sus ventas con el índice (id_farmaceutico,
fecha). El cliente se resuelve con un $lookup por _id.

Criterio: cuentan COMPLETADA, PENDIENTE y ANULADA; el cliente fue atendido, independientemente de si
luego la venta fue anulada. El enunciado no excluye
anuladas, y el vínculo es "el farmacéutico que registró la venta": la venta
existe en los tres estados. Entran también el farmacéutico inactivo, la sucursal dada de baja y el
cliente dado de baja. Un cliente atendido por más de un farmacéutico de la
misma sucursal aparece una sola vez. La sucursal es la ACTUAL del
farmacéutico, que es la única que el modelo implementado guarda.

Parámetros:
    id_sucursal (str): obligatorio, por ejemplo "S001".
Retorna: dict con "sucursal" y "clientes" (id_cliente, nombre, apellido, dni
y activo), ordenados por id_cliente. {"error": ...} si falta el id o la
sucursal no existe, para no confundirlo con una sucursal sin clientes.
"""
from farmared.db import get_db


def ejecutar(id_sucursal=None):
    if not id_sucursal:
        return {"error": "Falta el id de la sucursal. Uso: python main.py q10 <id_sucursal>"}

    db = get_db()
    sucursal = db.sucursales.find_one({"_id": id_sucursal})
    if sucursal is None:
        return {"error": f"No existe la sucursal '{id_sucursal}'"}

    pipeline = [
        # activos e inactivos: la sucursal es la del farmacéutico, no de la venta
        {"$match": {"id_sucursal": id_sucursal}},
        {"$lookup": {
            "from": "ventas",
            "localField": "_id",
            "foreignField": "id_farmaceutico",
            "as": "ventas",
        }},
        {"$unwind": "$ventas"},
        # una fila por cliente, aunque tenga varias ventas o varios farmacéuticos
        {"$group": {"_id": "$ventas.id_cliente"}},
        {"$lookup": {
            "from": "clientes",
            "localField": "_id",
            "foreignField": "_id",
            "as": "cliente",
        }},
        {"$unwind": {"path": "$cliente", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 0,
            "id_cliente": "$_id",
            "nombre": {"$ifNull": ["$cliente.nombre", None]},
            "apellido": {"$ifNull": ["$cliente.apellido", None]},
            "dni": {"$ifNull": ["$cliente.dni", None]},
            "activo": {"$ifNull": ["$cliente.activo", None]},
        }},
        {"$sort": {"id_cliente": 1}},
    ]
    return {
        "sucursal": {
            "id_sucursal": sucursal["_id"],
            "nombre": sucursal["nombre"],
            "activo": sucursal["activo"],
        },
        "clientes": list(db.farmaceuticos.aggregate(pipeline)),
    }
