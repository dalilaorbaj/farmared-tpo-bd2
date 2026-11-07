"""
Contrato de q09.ejecutar().

Cada test fija ventas, llama a la consulta y verifica cuáles son libres, bajo
el monto y no anuladas. Mongo está reemplazado por una base en memoria.
"""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import mongomock

from farmared.consultas import q09_ventas_libres_menores as q09


def dia(texto):
    return datetime.strptime(texto, "%Y-%m-%d")


@contextmanager
def mongo_en_memoria():
    db = mongomock.MongoClient()["farmared"]
    with patch("farmared.consultas.q09_ventas_libres_menores.get_db", return_value=db):
        yield db


def venta(id_venta, tipo, total, fecha, estado, items=None):
    return {
        "_id": id_venta,
        "tipo": tipo,
        "total": total,
        "fecha": dia(fecha),
        "estado": estado,
        "id_cliente": "C001",
        "items": items or [{"id_producto": "PRD001", "cantidad": 1, "precio_unit": total}],
    }


def test_ventas_libres_bajo_el_monto_sin_anuladas_ordenadas_por_fecha():
    # Arrange
    with mongo_en_memoria() as db:
        db.ventas.insert_many([
            venta("V016", "Venta libre", 7800, "2026-10-07", "Completada"),
            venta("V014", "Venta libre", 4600, "2026-10-05", "Completada"),
            venta("V012", "Venta libre", 2000, "2026-10-11", "Pendiente"),
            venta("V015", "Venta libre", 3500, "2026-09-25", "Anulada"),
            venta("V011", "Con receta", 4800, "2026-10-12", "Pendiente"),
            venta("V009", "Venta libre", 3000, "2026-09-01", "Completada"),
        ])

        # Act
        resultado = q09.ejecutar()

    # Assert
    assert [fila["_id"] for fila in resultado] == ["V009", "V014", "V012"]
    assert all("items" not in fila for fila in resultado)
    assert resultado[0]["total"] == 3000
    assert resultado[0]["estado"] == "Completada"


def test_el_tope_es_estricto():
    # Arrange
    with mongo_en_memoria() as db:
        db.ventas.insert_many([
            venta("V1", "Venta libre", 5000, "2026-10-01", "Completada"),
            venta("V2", "Venta libre", 4999, "2026-10-02", "Completada"),
        ])

        # Act
        resultado = q09.ejecutar()

    # Assert
    assert [fila["_id"] for fila in resultado] == ["V2"]


def test_el_monto_llega_como_texto():
    # Arrange
    with mongo_en_memoria() as db:
        db.ventas.insert_many([
            venta("V1", "Venta libre", 900, "2026-10-01", "Completada"),
            venta("V2", "Venta libre", 1000, "2026-10-02", "Completada"),
        ])

        # Act
        resultado = q09.ejecutar("1000")

    # Assert
    assert [fila["_id"] for fila in resultado] == ["V1"]
