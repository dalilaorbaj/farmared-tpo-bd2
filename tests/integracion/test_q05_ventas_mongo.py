"""
Contrato de q05 contra Mongo real.

El left join usa $lookup con let y un subpipeline. Eso no corre en la base
en memoria, y es lo que deja en cero a quien no vendió.
"""
from datetime import datetime
from unittest.mock import patch

import pytest

from farmared.consultas import q05_ventas_por_farmaceutico as q05

pytestmark = pytest.mark.integracion


def dia(texto):
    return datetime.strptime(texto, "%Y-%m-%d")


HOY = dia("2026-11-07")


def farmaceutico(id_farmaceutico, nombre, apellido, matricula, id_sucursal, activo=True):
    return {
        "_id": id_farmaceutico,
        "nombre": nombre,
        "apellido": apellido,
        "matricula": matricula,
        "id_sucursal": id_sucursal,
        "activo": activo,
    }


def venta(id_venta, id_farmaceutico, fecha, estado="Completada"):
    return {
        "_id": id_venta,
        "id_farmaceutico": id_farmaceutico,
        "id_cliente": "C001",
        "fecha": dia(fecha),
        "estado": estado,
        "total": 1000,
    }


def correr(mongo, dias=60):
    with (
        patch("farmared.consultas.q05_ventas_por_farmaceutico.get_db", return_value=mongo),
        patch("farmared.consultas.q05_ventas_por_farmaceutico.fechas.hoy", return_value=HOY),
    ):
        return q05.ejecutar(dias)


def test_incluye_al_que_no_vendio_y_no_cuenta_anuladas_ni_inactivos(mongo):
    # Arrange
    mongo.sucursales.insert_many([
        {"_id": "S001", "nombre": "Farmacia Palermo"},
        {"_id": "S002", "nombre": "Farmacia Belgrano"},
    ])
    mongo.farmaceuticos.insert_many([
        farmaceutico("F001", "Mariana", "Quiroga", "MN-18041", "S001"),
        farmaceutico("F002", "Sebastián", "Ledesma", "MN-18078", "S001"),
        farmaceutico("F003", "Carolina", "Benítez", "MN-18112", "S002"),
        farmaceutico("F004", "Julián", "Pereyra", "MN-17955", "S002", activo=False),
    ])
    mongo.ventas.insert_many([
        venta("V1", "F001", "2026-10-02"),
        venta("V2", "F001", "2026-11-01", estado="Pendiente"),
        venta("V3", "F001", "2026-11-02", estado="Anulada"),
        venta("V4", "F001", "2026-08-01"),
        venta("V5", "F004", "2026-11-01"),
    ])

    # Act
    resultado = correr(mongo)

    # Assert
    assert resultado == [
        {
            "id_farmaceutico": "F001",
            "nombre": "Mariana Quiroga",
            "matricula": "MN-18041",
            "sucursal": "Farmacia Palermo",
            "cantidad_ventas": 2,
        },
        {
            "id_farmaceutico": "F002",
            "nombre": "Sebastián Ledesma",
            "matricula": "MN-18078",
            "sucursal": "Farmacia Palermo",
            "cantidad_ventas": 0,
        },
        {
            "id_farmaceutico": "F003",
            "nombre": "Carolina Benítez",
            "matricula": "MN-18112",
            "sucursal": "Farmacia Belgrano",
            "cantidad_ventas": 0,
        },
    ]


def test_la_ventana_incluye_el_dia_de_corte_y_dias_la_achica(mongo):
    # Arrange
    # hoy 2026-11-07. 60 días atrás es 2026-09-08. 30 días atrás es 2026-10-08.
    mongo.sucursales.insert_one({"_id": "S001", "nombre": "Farmacia Palermo"})
    mongo.farmaceuticos.insert_one(
        farmaceutico("F001", "Mariana", "Quiroga", "MN-18041", "S001"),
    )
    mongo.ventas.insert_many([
        venta("V1", "F001", "2026-09-07"),
        venta("V2", "F001", "2026-09-08"),
        venta("V3", "F001", "2026-10-08"),
    ])

    # Act
    en_60 = correr(mongo, 60)
    en_30 = correr(mongo, "30")

    # Assert
    assert en_60[0]["cantidad_ventas"] == 2
    assert en_30[0]["cantidad_ventas"] == 1


def test_en_empate_prioriza_el_id_menor(mongo):
    # Arrange
    mongo.sucursales.insert_one({"_id": "S001", "nombre": "Farmacia Palermo"})
    mongo.farmaceuticos.insert_many([
        farmaceutico("F010", "Gonzalo", "Duarte", "MN-18533", "S001"),
        farmaceutico("F002", "Sebastián", "Ledesma", "MN-18078", "S001"),
    ])
    mongo.ventas.insert_many([
        venta("V1", "F010", "2026-11-01"),
        venta("V2", "F002", "2026-11-02"),
    ])

    # Act
    resultado = correr(mongo)

    # Assert
    assert [fila["id_farmaceutico"] for fila in resultado] == ["F002", "F010"]


def test_sin_sucursal_el_farmaceutico_aparece_igual(mongo):
    # Arrange
    mongo.farmaceuticos.insert_one(
        farmaceutico("F007", "Romina", "Acuña", "MN-18401", "S404"),
    )

    # Act
    resultado = correr(mongo)

    # Assert
    assert resultado == [{
        "id_farmaceutico": "F007",
        "nombre": "Romina Acuña",
        "matricula": "MN-18401",
        "cantidad_ventas": 0,
    }]
