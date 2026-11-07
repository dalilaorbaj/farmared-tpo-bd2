"""
Contrato de q11.ejecutar().

Cada test fija un "hoy" y un conjunto de ventas, llama a la consulta y verifica
los ingresos del mes. Mongo está reemplazado por una base en memoria y hoy()
está fijado; el pipeline es el que corre.
"""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import mongomock

from farmared.consultas import q11_ingresos_por_farmaceutico as q11


def dia(texto):
    return datetime.strptime(texto, "%Y-%m-%d")


@contextmanager
def mongo_en_memoria(hoy):
    db = mongomock.MongoClient()["farmared"]
    with (
        patch("farmared.consultas.q11_ingresos_por_farmaceutico.get_db", return_value=db),
        patch("farmared.consultas.q11_ingresos_por_farmaceutico.fechas.hoy", return_value=hoy),
    ):
        yield db


def sucursal(id_sucursal, nombre):
    return {"_id": id_sucursal, "nombre": nombre}


def farmaceutico(id_farmaceutico, nombre, apellido, matricula, id_sucursal, activo=True):
    return {
        "_id": id_farmaceutico,
        "nombre": nombre,
        "apellido": apellido,
        "matricula": matricula,
        "id_sucursal": id_sucursal,
        "activo": activo,
    }


def venta(id_venta, id_farmaceutico, total, fecha, estado="Completada"):
    return {
        "_id": id_venta,
        "id_farmaceutico": id_farmaceutico,
        "total": total,
        "fecha": dia(fecha),
        "estado": estado,
    }


def fila(id_farmaceutico, nombre, matricula, sucursal, ingresos):
    return {
        "id_farmaceutico": id_farmaceutico,
        "nombre": nombre,
        "matricula": matricula,
        "sucursal": sucursal,
        "ingresos": ingresos,
    }


def test_suma_las_completadas_del_mes_y_ordena_por_ingresos():
    # Arrange
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.sucursales.insert_many([
            sucursal("S001", "Farmacia Palermo"),
            sucursal("S002", "Farmacia Belgrano"),
        ])
        db.farmaceuticos.insert_many([
            farmaceutico("F019", "Micaela", "Peralta", "MN-18850", "S001"),
            farmaceutico("F003", "Carolina", "Benítez", "MN-18112", "S002"),
        ])
        db.ventas.insert_many([
            venta("V017", "F019", 8100, "2026-11-02"),
            venta("V033", "F019", 1500, "2026-11-07"),
            venta("V032", "F003", 6300, "2026-11-04"),
            venta("V010", "F003", 7100, "2026-10-08"),
        ])

        # Act
        resultado = q11.ejecutar()

    # Assert
    assert resultado == [
        fila("F019", "Micaela Peralta", "MN-18850", "Farmacia Palermo", 9600),
        fila("F003", "Carolina Benítez", "MN-18112", "Farmacia Belgrano", 6300),
    ]


def test_pendiente_y_anulada_no_suman():
    # Arrange
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.sucursales.insert_one(sucursal("S001", "Farmacia Palermo"))
        db.farmaceuticos.insert_many([
            farmaceutico("F019", "Micaela", "Peralta", "MN-18850", "S001"),
            farmaceutico("F013", "Mercedes", "Castro", "MN-18644", "S001"),
        ])
        db.ventas.insert_many([
            venta("V017", "F019", 8100, "2026-11-02"),
            venta("V028", "F013", 12500, "2026-11-01", estado="Pendiente"),
            venta("V031", "F019", 4100, "2026-11-03", estado="Anulada"),
        ])

        # Act
        resultado = q11.ejecutar()

    # Assert
    assert resultado == [
        fila("F019", "Micaela Peralta", "MN-18850", "Farmacia Palermo", 8100),
    ]


def test_el_mes_es_un_intervalo_semiabierto():
    # Arrange
    with mongo_en_memoria(dia("2026-11-15")) as db:
        db.sucursales.insert_one(sucursal("S001", "Farmacia Palermo"))
        db.farmaceuticos.insert_many([
            farmaceutico("F001", "Mariana", "Quiroga", "MN-18041", "S001"),
            farmaceutico("F002", "Sebastián", "Ledesma", "MN-18078", "S001"),
            farmaceutico("F003", "Carolina", "Benítez", "MN-18112", "S001"),
            farmaceutico("F004", "Julián", "Pereyra", "MN-17955", "S001"),
        ])
        db.ventas.insert_many([
            venta("V1", "F001", 100, "2026-10-31"),
            venta("V2", "F002", 200, "2026-11-01"),
            venta("V3", "F003", 300, "2026-11-30"),
            venta("V4", "F004", 400, "2026-12-01"),
        ])

        # Act
        resultado = q11.ejecutar()

    # Assert
    assert resultado == [
        fila("F003", "Carolina Benítez", "MN-18112", "Farmacia Palermo", 300),
        fila("F002", "Sebastián Ledesma", "MN-18078", "Farmacia Palermo", 200),
    ]


def test_diciembre_cierra_en_enero_del_anio_siguiente():
    # Arrange
    with mongo_en_memoria(dia("2026-12-07")) as db:
        db.sucursales.insert_one(sucursal("S001", "Farmacia Palermo"))
        db.farmaceuticos.insert_many([
            farmaceutico("F001", "Mariana", "Quiroga", "MN-18041", "S001"),
            farmaceutico("F002", "Sebastián", "Ledesma", "MN-18078", "S001"),
        ])
        db.ventas.insert_many([
            venta("V1", "F001", 100, "2026-11-30"),
            venta("V2", "F001", 500, "2026-12-31"),
            venta("V3", "F002", 900, "2027-01-01"),
        ])

        # Act
        resultado = q11.ejecutar()

    # Assert
    assert resultado == [
        fila("F001", "Mariana Quiroga", "MN-18041", "Farmacia Palermo", 500),
    ]


def test_en_empate_de_ingresos_prioriza_el_id_menor():
    # Arrange
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.sucursales.insert_one(sucursal("S001", "Farmacia Palermo"))
        db.farmaceuticos.insert_many([
            farmaceutico("F010", "Gonzalo", "Duarte", "MN-18533", "S001"),
            farmaceutico("F002", "Sebastián", "Ledesma", "MN-18078", "S001"),
        ])
        db.ventas.insert_many([
            venta("V1", "F010", 4000, "2026-11-02"),
            venta("V2", "F002", 4000, "2026-11-03"),
        ])

        # Act
        resultado = q11.ejecutar()

    # Assert
    assert [fila["id_farmaceutico"] for fila in resultado] == ["F002", "F010"]


def test_un_farmaceutico_inactivo_entra_si_cobro_en_el_mes():
    # Arrange
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.sucursales.insert_one(sucursal("S015", "Farmacia Flores"))
        db.farmaceuticos.insert_one(
            farmaceutico("F018", "Hernán", "Funes", "MN-17890", "S015", activo=False),
        )
        db.ventas.insert_one(venta("V1", "F018", 2600, "2026-11-06"))

        # Act
        resultado = q11.ejecutar()

    # Assert
    assert resultado == [
        fila("F018", "Hernán Funes", "MN-17890", "Farmacia Flores", 2600),
    ]


def test_sin_completadas_en_el_mes_devuelve_lista_vacia():
    # Arrange
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.farmaceuticos.insert_one(
            farmaceutico("F001", "Mariana", "Quiroga", "MN-18041", "S001"),
        )
        db.ventas.insert_one(venta("V1", "F001", 4400, "2026-10-02"))

        # Act
        resultado = q11.ejecutar()

    # Assert
    assert resultado == []


def test_sin_ficha_de_farmaceutico_los_datos_son_nulos():
    # Arrange
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.ventas.insert_one(venta("V1", "F404", 1500, "2026-11-02"))

        # Act
        resultado = q11.ejecutar()

    # Assert
    assert resultado == [fila("F404", None, None, None, 1500)]
