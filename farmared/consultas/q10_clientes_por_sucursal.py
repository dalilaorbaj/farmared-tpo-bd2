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
cliente dado de baja. La sucursal es la ACTUAL del
farmacéutico, que es la única que el modelo implementado guarda.

Por defecto cada cliente aparece una sola vez, aunque tenga varias ventas o
lo hayan atendido varios farmacéuticos de la sucursal. Con
contar_repetidos=True hay una fila por venta: la misma persona se repite
tantas veces como la atendieron, y cada fila trae la venta que la cuenta.
La consigna pide clientes distintos; el default False es ese resultado.
Desde la CLI el booleano llega como texto, igual que en q07.

Parámetros:
    id_sucursal (str): obligatorio, por ejemplo "S001".
    contar_repetidos (bool): si es True, una fila por venta. Por defecto
    False. Acepta True/False y los textos true, false, 1, 0, si y no.
Retorna: dict con "sucursal" y "clientes". {"error": ...} si falta el id o
la sucursal no existe, para no confundirlo con una sucursal sin clientes.
Con contar_repetidos=False cada cliente tiene id_cliente, nombre, apellido,
dni y activo, ordenados por id_cliente. Con True se suman id_venta, fecha,
estado e id_farmaceutico, ordenados por id_cliente, fecha e id_venta.
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
    raise ValueError("contar_repetidos debe ser true o false")


def _datos_cliente():
    return {
        "nombre": {"$ifNull": ["$cliente.nombre", None]},
        "apellido": {"$ifNull": ["$cliente.apellido", None]},
        "dni": {"$ifNull": ["$cliente.dni", None]},
        "activo": {"$ifNull": ["$cliente.activo", None]},
    }


def _pipeline(id_sucursal, contar_repetidos):
    etapas = [
        # activos e inactivos: la sucursal es la del farmacéutico, no de la venta
        {"$match": {"id_sucursal": id_sucursal}},
        {"$lookup": {
            "from": "ventas",
            "localField": "_id",
            "foreignField": "id_farmaceutico",
            "as": "ventas",
        }},
        {"$unwind": "$ventas"},
    ]
    if contar_repetidos:
        etapas += [
            {"$lookup": {
                "from": "clientes",
                "localField": "ventas.id_cliente",
                "foreignField": "_id",
                "as": "cliente",
            }},
            {"$unwind": {"path": "$cliente", "preserveNullAndEmptyArrays": True}},
            {"$project": {
                "_id": 0,
                "id_cliente": "$ventas.id_cliente",
                **_datos_cliente(),
                "id_venta": "$ventas._id",
                "fecha": {"$ifNull": ["$ventas.fecha", None]},
                "estado": "$ventas.estado",
                "id_farmaceutico": "$_id",
            }},
            {"$sort": {"id_cliente": 1, "fecha": 1, "id_venta": 1}},
        ]
    else:
        etapas += [
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
                **_datos_cliente(),
            }},
            {"$sort": {"id_cliente": 1}},
        ]
    return etapas


def ejecutar(id_sucursal=None, contar_repetidos=False):
    if not id_sucursal:
        return {"error": "Falta el id de la sucursal. Uso: python main.py q10 <id_sucursal> [contar_repetidos]"}
    contar_repetidos = _a_bool(contar_repetidos)

    db = get_db()
    sucursal = db.sucursales.find_one({"_id": id_sucursal})
    if sucursal is None:
        return {"error": f"No existe la sucursal '{id_sucursal}'"}

    return {
        "sucursal": {
            "id_sucursal": sucursal["_id"],
            "nombre": sucursal["nombre"],
            "activo": sucursal["activo"],
        },
        "clientes": list(db.farmaceuticos.aggregate(_pipeline(id_sucursal, contar_repetidos))),
    }
