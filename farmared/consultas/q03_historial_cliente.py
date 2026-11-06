"""
Q03 - Historial completo de un cliente: sus ventas y sus recetas en una sola
línea de tiempo.

Motor: MongoDB. Ventas y recetas guardan id_cliente como referencia, así que un
solo pipeline filtra ventas y suma recetas con $unionWith. Cada $match usa el
índice que empieza por id_cliente de su colección. El nombre de cada producto
se resuelve con un $lookup por _id.

Criterio: se muestran todas las ventas (Completada, Pendiente y Anulada) con su
estado. Un cliente dado de baja conserva su historial. Si falta el id o el
cliente no existe se devuelve un error, para no confundirlo con un cliente sin
movimientos. El orden es por fecha ascendente y, si coincide la fecha, la
receta va antes que la venta.

Parámetros:
    id_cliente (str): obligatorio, por ejemplo "C001".
Retorna: dict con "cliente" e "historial" (lista de ventas y recetas con
tipo_registro y fecha), o {"error": ...} si no se puede resolver el cliente.
"""
from farmared.db import get_db


def ejecutar(id_cliente=None):
    if not id_cliente:
        return {"error": "Falta el id del cliente. Uso: python main.py q03 <id_cliente>"}

    db = get_db()
    cliente = db.clientes.find_one({"_id": id_cliente})
    if cliente is None:
        return {"error": f"No existe el cliente '{id_cliente}'"}

    pipeline = [
        # ventas del cliente, en cualquier estado
        {"$match": {"id_cliente": id_cliente}},
        # trae los productos de los ítems de la venta
        {"$lookup": {
            "from": "productos",
            "localField": "items.id_producto",
            "foreignField": "_id",
            "as": "productos",
        }},
        # forma común: suma tipo_registro y agrega el nombre del producto a cada ítem
        {"$project": {
            "_id": 0,
            "tipo_registro": "venta",
            "id_registro": "$_id",
            "fecha": 1,
            "tipo": 1,
            "estado": 1,
            "id_farmaceutico": 1,
            "id_receta": 1,
            "medio_pago": 1,
            "total": 1,
            "items": {"$map": {
                "input": "$items",
                "as": "item",
                "in": {
                    "id_producto": "$$item.id_producto",
                    "producto": {"$arrayElemAt": [
                        "$productos.nombre",
                        {"$indexOfArray": ["$productos._id", "$$item.id_producto"]},
                    ]},
                    "cantidad": "$$item.cantidad",
                    "precio_unit": "$$item.precio_unit",
                },
            }},
        }},
        # suma las recetas del cliente con la misma forma común
        {"$unionWith": {
            "coll": "recetas",
            "pipeline": [
                {"$match": {"id_cliente": id_cliente}},
                {"$project": {
                    "_id": 0,
                    "tipo_registro": "receta",
                    "id_registro": "$_id",
                    "fecha": "$fecha_emision",
                    "tipo": 1,
                    "estado": 1,
                    "medico": 1,
                    "matricula_medico": 1,
                    "dispensas_autorizadas": 1,
                    "dispensas_realizadas": 1,
                    "proxima_dispensa": 1,
                }},
            ],
        }},
        # línea de tiempo: si coincide la fecha, la receta queda antes que la venta
        {"$sort": {"fecha": 1, "tipo_registro": 1, "id_registro": 1}},
    ]
    return {
        "cliente": {
            "id_cliente": cliente["_id"],
            "nombre": cliente["nombre"],
            "apellido": cliente["apellido"],
            "dni": cliente["dni"],
            "obra_social": cliente["obra_social"],
            "activo": cliente["activo"],
        },
        "historial": list(db.ventas.aggregate(pipeline)),
    }
