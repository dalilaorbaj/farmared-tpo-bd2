"""
Contrato de q10.ejecutar().

Cada test fija sucursales, farmacéuticos, ventas y clientes, llama a la
consulta y verifica quién aparece. Mongo está reemplazado por una base en
memoria; el pipeline es el que corre.
"""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import mongomock
import pytest

from farmared.consultas import q10_clientes_por_sucursal as q10


@contextmanager
def mongo_en_memoria():
    db = mongomock.MongoClient()["farmared"]
    with patch("farmared.consultas.q10_clientes_por_sucursal.get_db", return_value=db):
        yield db


def sucursal(id_sucursal, nombre, activo=True):
    return {"_id": id_sucursal, "nombre": nombre, "activo": activo}


def farmaceutico(id_farmaceutico, id_sucursal, activo=True):
    return {"_id": id_farmaceutico, "id_sucursal": id_sucursal, "activo": activo}


def cliente(id_cliente, nombre, apellido, dni, activo=True):
    return {
        "_id": id_cliente,
        "nombre": nombre,
        "apellido": apellido,
        "dni": dni,
        "activo": activo,
    }


def venta(id_venta, id_cliente, id_farmaceutico, estado="Completada", fecha=None):
    doc = {
        "_id": id_venta,
        "id_cliente": id_cliente,
        "id_farmaceutico": id_farmaceutico,
        "estado": estado,
    }
    if fecha is not None:
        doc["fecha"] = datetime.strptime(fecha, "%Y-%m-%d")
    return doc


def fila(id_cliente, nombre, apellido, dni, activo=True):
    return {
        "id_cliente": id_cliente,
        "nombre": nombre,
        "apellido": apellido,
        "dni": dni,
        "activo": activo,
    }


def atencion(id_venta, id_cliente, nombre, apellido, dni, fecha, estado, id_farmaceutico, activo=True):
    return {
        **fila(id_cliente, nombre, apellido, dni, activo),
        "id_venta": id_venta,
        "fecha": datetime.strptime(fecha, "%Y-%m-%d"),
        "estado": estado,
        "id_farmaceutico": id_farmaceutico,
    }


def test_sin_id_devuelve_error_y_no_consulta():
    # Arrange
    
    # Act
    resultado = q10.ejecutar()

    # Assert
    assert resultado == {
        "error": "Falta el id de la sucursal. Uso: python main.py q10 <id_sucursal> [contar_repetidos]",
    }


def test_sucursal_inexistente_devuelve_error():
    # Arrange
    with mongo_en_memoria() as db:
        db.sucursales.insert_one(sucursal("S001", "Farmacia Palermo"))

        # Act
        resultado = q10.ejecutar("S999")

    # Assert
    assert resultado == {"error": "No existe la sucursal 'S999'"}


def test_devuelve_los_clientes_distintos_de_esa_sucursal_ordenados():
    # Arrange
    with mongo_en_memoria() as db:
        db.sucursales.insert_many([
            sucursal("S001", "Farmacia Palermo"),
            sucursal("S002", "Farmacia Belgrano"),
        ])
        db.farmaceuticos.insert_many([
            farmaceutico("F001", "S001"),
            farmaceutico("F002", "S001"),
            farmaceutico("F003", "S002"),
        ])
        db.clientes.insert_many([
            cliente("C006", "Ricardo", "Paz", "14876543"),
            cliente("C001", "Lucía", "Fernández", "31245678"),
            cliente("C002", "Martín", "Gómez", "28765432"),
        ])
        db.ventas.insert_many([
            venta("V003", "C001", "F001"),
            venta("V013", "C001", "F001"),
            venta("V006", "C006", "F002"),
            venta("V016", "C001", "F002"),
            venta("V010", "C002", "F003"),
        ])

        # Act
        resultado = q10.ejecutar("S001")

    # Assert
    assert resultado == {
        "sucursal": {"id_sucursal": "S001", "nombre": "Farmacia Palermo", "activo": True},
        "clientes": [
            fila("C001", "Lucía", "Fernández", "31245678"),
            fila("C006", "Ricardo", "Paz", "14876543"),
        ],
    }


def test_cuenta_pendiente_y_anulada():
    # Arrange
    with mongo_en_memoria() as db:
        db.sucursales.insert_one(sucursal("S007", "Farmacia La Plata Centro"))
        db.farmaceuticos.insert_one(farmaceutico("F010", "S007"))
        db.clientes.insert_many([
            cliente("C004", "Federico", "Navarro", "33987654"),
            cliente("C011", "Agustina", "Molina", "41022987"),
        ])
        db.ventas.insert_many([
            venta("V031", "C004", "F010", estado="Anulada"),
            venta("V040", "C011", "F010", estado="Pendiente"),
        ])

        # Act
        resultado = q10.ejecutar("S007")

    # Assert
    assert resultado["clientes"] == [
        fila("C004", "Federico", "Navarro", "33987654"),
        fila("C011", "Agustina", "Molina", "41022987"),
    ]


def test_sucursal_cerrada_con_farmaceutico_inactivo_conserva_sus_clientes():
    # Arrange
    with mongo_en_memoria() as db:
        db.sucursales.insert_one(sucursal("S015", "Farmacia Flores", activo=False))
        db.farmaceuticos.insert_one(farmaceutico("F018", "S015", activo=False))
        db.clientes.insert_one(cliente("C002", "Martín", "Gómez", "28765432"))
        db.ventas.insert_one(venta("V034", "C002", "F018"))

        # Act
        resultado = q10.ejecutar("S015")

    # Assert
    assert resultado == {
        "sucursal": {"id_sucursal": "S015", "nombre": "Farmacia Flores", "activo": False},
        "clientes": [fila("C002", "Martín", "Gómez", "28765432")],
    }


def test_un_cliente_dado_de_baja_sigue_apareciendo():
    # Arrange
    with mongo_en_memoria() as db:
        db.sucursales.insert_one(sucursal("S001", "Farmacia Palermo"))
        db.farmaceuticos.insert_one(farmaceutico("F001", "S001"))
        db.clientes.insert_one(cliente("C016", "Gustavo", "Ibarra", "22345098", activo=False))
        db.ventas.insert_one(venta("V050", "C016", "F001"))

        # Act
        resultado = q10.ejecutar("S001")

    # Assert
    assert resultado["clientes"] == [
        fila("C016", "Gustavo", "Ibarra", "22345098", activo=False),
    ]


def test_sucursal_sin_ventas_devuelve_lista_vacia():
    # Arrange
    with mongo_en_memoria() as db:
        db.sucursales.insert_one(sucursal("S005", "Droguería Central"))
        db.farmaceuticos.insert_one(farmaceutico("F007", "S005"))

        # Act
        resultado = q10.ejecutar("S005")

    # Assert
    assert resultado == {
        "sucursal": {"id_sucursal": "S005", "nombre": "Droguería Central", "activo": True},
        "clientes": [],
    }


def test_contar_repetidos_repite_una_fila_por_venta():
    # Arrange
    with mongo_en_memoria() as db:
        db.sucursales.insert_one(sucursal("S001", "Farmacia Palermo"))
        db.farmaceuticos.insert_many([
            farmaceutico("F001", "S001"),
            farmaceutico("F002", "S001"),
            farmaceutico("F003", "S002"),
        ])
        db.clientes.insert_many([
            cliente("C001", "Lucía", "Fernández", "31245678"),
            cliente("C006", "Ricardo", "Paz", "14876543"),
        ])
        db.ventas.insert_many([
            venta("V016", "C001", "F002", fecha="2026-10-07"),
            venta("V003", "C001", "F001", fecha="2026-09-10"),
            venta("V013", "C001", "F001", fecha="2026-10-02"),
            venta("V006", "C006", "F002", fecha="2026-08-01"),
            venta("V010", "C002", "F003", fecha="2026-10-08"),
        ])

        # Act
        resultado = q10.ejecutar("S001", "true")

    # Assert
    assert resultado["clientes"] == [
        atencion("V003", "C001", "Lucía", "Fernández", "31245678", "2026-09-10", "Completada", "F001"),
        atencion("V013", "C001", "Lucía", "Fernández", "31245678", "2026-10-02", "Completada", "F001"),
        atencion("V016", "C001", "Lucía", "Fernández", "31245678", "2026-10-07", "Completada", "F002"),
        atencion("V006", "C006", "Ricardo", "Paz", "14876543", "2026-08-01", "Completada", "F002"),
    ]


def test_contar_repetidos_en_false_sigue_siendo_un_cliente():
    # Arrange
    with mongo_en_memoria() as db:
        db.sucursales.insert_one(sucursal("S001", "Farmacia Palermo"))
        db.farmaceuticos.insert_one(farmaceutico("F001", "S001"))
        db.clientes.insert_one(cliente("C001", "Lucía", "Fernández", "31245678"))
        db.ventas.insert_many([
            venta("V003", "C001", "F001", fecha="2026-09-10"),
            venta("V013", "C001", "F001", fecha="2026-10-02"),
        ])

        # Act
        resultado = q10.ejecutar("S001", "false")

    # Assert
    assert resultado["clientes"] == [
        fila("C001", "Lucía", "Fernández", "31245678"),
    ]


def test_contar_repetidos_rechaza_un_valor_desconocido():
    # Arrange
    argumento = "varias"

    # Act
    with pytest.raises(ValueError, match="contar_repetidos"):
        q10.ejecutar("S001", argumento)


def test_sin_ficha_de_cliente_aparece_con_datos_nulos():
    # Arrange
    with mongo_en_memoria() as db:
        db.sucursales.insert_one(sucursal("S001", "Farmacia Palermo"))
        db.farmaceuticos.insert_one(farmaceutico("F001", "S001"))
        db.ventas.insert_one(venta("V099", "C404", "F001"))

        # Act
        resultado = q10.ejecutar("S001")

    # Assert
    assert resultado["clientes"] == [
        fila("C404", None, None, None, activo=None),
    ]
