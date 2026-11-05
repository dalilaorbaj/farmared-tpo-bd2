"""
Q09 - Ventas de tipo 'Venta libre' con total menor a $5.000 (excluyendo anuladas).

Motor: MongoDB, find simple sobre ventas.

Parámetros:
    monto_max (int): tope del total (estricto), por defecto 5000.
Retorna: lista de ventas (sin los items) ordenadas por fecha.
"""
from farmared.db import get_db


def ejecutar(monto_max=5000):
    filtro = {
        "tipo": "Venta libre",
        "total": {"$lt": int(monto_max)},
        "estado": {"$ne": "Anulada"},
    }
    proyeccion = {"items": 0}
    return list(get_db().ventas.find(filtro, proyeccion).sort("fecha", 1))
