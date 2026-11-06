"""
Q04 - Clientes con más de una receta registrada.

Motor: MongoDB. La receta guarda id_cliente como referencia, así que se agrupa
por ese campo y después se resuelve el cliente con un $lookup por _id. No hay
filtro previo porque se cuentan todas las recetas: el $group recorre la
colección completa y el índice que se aprovecha es el _id de clientes.

Criterio: se cuentan todas las recetas, sin importar su estado. Los empates en
la cantidad se ordenan por id_cliente para que el resultado sea siempre igual.

Parámetros: ninguno.
Retorna: lista de dict con id_cliente, nombre, apellido y cantidad_recetas,
ordenada por cantidad_recetas descendente.
"""
from farmared.db import get_db


def ejecutar():
    pipeline = [
        # cuenta las recetas de cada cliente
        {"$group": {"_id": "$id_cliente", "cantidad_recetas": {"$sum": 1}}},
        # deja solo a los que tienen más de una
        {"$match": {"cantidad_recetas": {"$gt": 1}}},
        # trae los datos del cliente
        {"$lookup": {
            "from": "clientes",
            "localField": "_id",
            "foreignField": "_id",
            "as": "cliente",
        }},
        {"$unwind": "$cliente"},
        # deja solo los campos del reporte
        {"$project": {
            "_id": 0,
            "id_cliente": "$_id",
            "nombre": "$cliente.nombre",
            "apellido": "$cliente.apellido",
            "cantidad_recetas": 1,
        }},
        # primero los que tienen más recetas
        {"$sort": {"cantidad_recetas": -1, "id_cliente": 1}},
    ]
    return list(get_db().recetas.aggregate(pipeline))
