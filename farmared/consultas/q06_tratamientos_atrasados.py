"""
Q06 - Recetas de tratamiento prolongado en estado 'Vigente' cuya próxima
dispensa ya pasó, con los datos del cliente.

Motor: MongoDB. La receta guarda id_cliente como referencia, así que se
resuelve con un $lookup por _id. El índice (tipo, estado, proxima_dispensa) de
recetas cubre las tres condiciones del $match inicial.

Criterio: la próxima dispensa tiene que ser estrictamente anterior a hoy a las
00:00, así que una receta con dispensa hoy todavía no está atrasada. No se
filtran los clientes dados de baja: se informa "activo" para distinguirlos.
Las recetas con proxima_dispensa null no entran porque no tienen fecha.

Parámetros: ninguno. Depende de la fecha del sistema (fechas.hoy()).
Retorna: lista de dict con id_receta, fecha_emision, proxima_dispensa,
dispensas y cliente, ordenada por proxima_dispensa ascendente.
"""
from farmared import fechas
from farmared.db import get_db


def ejecutar():
    pipeline = [
        # recetas de tratamiento prolongado vigentes con la dispensa atrasada
        {"$match": {
            "tipo": "Tratamiento prolongado",
            "estado": "Vigente",
            "proxima_dispensa": {"$lt": fechas.hoy()},
        }},
        # trae los datos del cliente
        {"$lookup": {
            "from": "clientes",
            "localField": "id_cliente",
            "foreignField": "_id",
            "as": "cliente",
        }},
        {"$unwind": "$cliente"},
        # primero las más atrasadas
        {"$sort": {"proxima_dispensa": 1, "_id": 1}},
        # deja solo los campos del reporte, incluido si el cliente sigue activo
        {"$project": {
            "_id": 0,
            "id_receta": "$_id",
            "fecha_emision": 1,
            "proxima_dispensa": 1,
            "dispensas_autorizadas": 1,
            "dispensas_realizadas": 1,
            "cliente": {
                "id": "$cliente._id",
                "nombre": {"$concat": ["$cliente.nombre", " ", "$cliente.apellido"]},
                "telefono": "$cliente.telefono",
                "email": "$cliente.email",
                "activo": "$cliente.activo",
            },
        }},
    ]
    return list(get_db().recetas.aggregate(pipeline))
