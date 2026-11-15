"""
Contrato de q02.ejecutar().

Cada test fija ventas, farmacéuticos y sucursales, llama a la consulta y
verifica las pendientes. Mongo está reemplazado por una base en memoria; el
pipeline es el que corre.
"""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import mongomock

from farmared.consultas import q02_ventas_pendientes as q02


def dia(texto):
    return datetime.strptime(texto, "%Y-%m-%d")


@contextmanager
def mongo_en_memoria():
    db = mongomock.MongoClient()["farmared"]
    with patch("farmared.consultas.q02_ventas_pendientes.get_db", return_value=db):
        yield db


def test_solo_pendientes_con_farmaceutico_y_sucursal_ordenadas_por_fecha():
    # Arrange
    with mongo_en_memoria() as db:
        db.sucursales.insert_many([
            {"_id": "S001", "nombre": "Farmacia Palermo"},
            {"_id": "S002", "nombre": "Farmacia Belgrano"},
        ])
        db.farmaceuticos.insert_many([
            {"_id": "F002", "nombre": "Sebastián", "apellido": "Ledesma", "matricula": "MN-18078", "id_sucursal": "S001"},
            {"_id": "F003", "nombre": "Carolina", "apellido": "Benítez", "matricula": "MN-18112", "id_sucursal": "S002"},
        ])
        db.ventas.insert_many([
            {"_id": "V012", "estado": "Pendiente", "fecha": dia("2026-10-11"), "id_cliente": "C002", "id_farmaceutico": "F003", "total": 9200},
            {"_id": "V011", "estado": "Pendiente", "fecha": dia("2026-10-12"), "id_cliente": "C007", "id_farmaceutico": "F002", "total": 4800},
            {"_id": "V013", "estado": "Completada", "fecha": dia("2026-10-02"), "id_cliente": "C001", "id_farmaceutico": "F002", "total": 4400},
            {"_id": "V015", "estado": "Anulada", "fecha": dia("2026-09-25"), "id_cliente": "C001", "id_farmaceutico": "F002", "total": 3500},
        ])

        # Act
        resultado = q02.ejecutar()

    # Assert
    assert resultado == [
        {
            "id_venta": "V012",
            "fecha": dia("2026-10-11"),
            "id_cliente": "C002",
            "total": 9200,
            "farmaceutico": {
                "id": "F003",
                "nombre": "Carolina Benítez",
                "matricula": "MN-18112",
                "sucursal": "Farmacia Belgrano",
            },
        },
        {
            "id_venta": "V011",
            "fecha": dia("2026-10-12"),
            "id_cliente": "C007",
            "total": 4800,
            "farmaceutico": {
                "id": "F002",
                "nombre": "Sebastián Ledesma",
                "matricula": "MN-18078",
                "sucursal": "Farmacia Palermo",
            },
        },
    ]


def test_sin_pendientes_devuelve_lista_vacia():
    # Arrange
    with mongo_en_memoria() as db:
        db.ventas.insert_one({
            "_id": "V013", "estado": "Completada", "fecha": dia("2026-10-02"),
            "id_cliente": "C001", "id_farmaceutico": "F001", "total": 4400,
        })

        # Act
        resultado = q02.ejecutar()

    # Assert
    assert resultado == []


def test_pendiente_con_farmaceutico_inexistente_aparece_igual_con_datos_nulos():
    # Arrange
    with mongo_en_memoria() as db:
        db.ventas.insert_one({
            "_id": "V040", "estado": "Pendiente", "fecha": dia("2026-11-01"),
            "id_cliente": "C001", "id_farmaceutico": "F999", "total": 1200,
        })

        # Act
        resultado = q02.ejecutar()

    # Assert
    assert resultado == [{
        "id_venta": "V040",
        "fecha": dia("2026-11-01"),
        "id_cliente": "C001",
        "total": 1200,
        "farmaceutico": {"id": "F999", "nombre": None, "matricula": None, "sucursal": None},
    }]
