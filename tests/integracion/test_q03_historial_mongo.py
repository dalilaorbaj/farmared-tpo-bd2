"""
Contrato de q03 contra Mongo real.

El historial mezcla ventas y recetas con $unionWith y resuelve el nombre del
producto. Eso no corre en la base en memoria.
"""
from datetime import datetime
from unittest.mock import patch

import pytest

from farmared.consultas import q03_historial_cliente as q03

pytestmark = pytest.mark.integracion


def dia(texto):
    return datetime.strptime(texto, "%Y-%m-%d")


def test_mezcla_ventas_y_recetas_y_la_receta_va_antes_el_mismo_dia(mongo):
    # Arrange
    mongo.clientes.insert_one({
        "_id": "C016",
        "nombre": "Gustavo",
        "apellido": "Ibarra",
        "dni": "22345098",
        "obra_social": "PAMI",
        "activo": False,
    })
    mongo.productos.insert_many([
        {"_id": "PRD003", "nombre": "Amoxicilina"},
        {"_id": "PRD001", "nombre": "Paracetamol"},
    ])
    mongo.ventas.insert_many([
        {
            "_id": "V003",
            "id_cliente": "C016",
            "id_farmaceutico": "F001",
            "id_receta": "RC001",
            "fecha": dia("2026-09-10"),
            "tipo": "Con receta",
            "medio_pago": "Obra social",
            "total": 9800,
            "estado": "Completada",
            "items": [{"id_producto": "PRD003", "cantidad": 1, "precio_unit": 9800}],
        },
        {
            "_id": "V015",
            "id_cliente": "C016",
            "id_farmaceutico": "F002",
            "id_receta": None,
            "fecha": dia("2026-09-25"),
            "tipo": "Venta libre",
            "medio_pago": "Débito",
            "total": 3500,
            "estado": "Anulada",
            "items": [{"id_producto": "PRD001", "cantidad": 1, "precio_unit": 3500}],
        },
        {
            "_id": "V099",
            "id_cliente": "C002",
            "id_farmaceutico": "F005",
            "fecha": dia("2026-09-01"),
            "tipo": "Venta libre",
            "medio_pago": "Efectivo",
            "total": 1000,
            "estado": "Completada",
            "items": [{"id_producto": "PRD001", "cantidad": 1, "precio_unit": 1000}],
        },
    ])
    mongo.recetas.insert_many([
        {
            "_id": "RC001",
            "id_cliente": "C016",
            "medico": "Dra. Paz",
            "matricula_medico": "MN-100",
            "fecha_emision": dia("2026-09-10"),
            "tipo": "Simple",
            "dispensas_autorizadas": 1,
            "dispensas_realizadas": 1,
            "proxima_dispensa": None,
            "estado": "Completada",
        },
        {
            "_id": "RC008",
            "id_cliente": "C016",
            "medico": "Dr. Luna",
            "matricula_medico": "MN-200",
            "fecha_emision": dia("2026-10-01"),
            "tipo": "Tratamiento prolongado",
            "dispensas_autorizadas": 3,
            "dispensas_realizadas": 1,
            "proxima_dispensa": dia("2026-11-01"),
            "estado": "Vigente",
        },
    ])

    # Act
    with patch("farmared.consultas.q03_historial_cliente.get_db", return_value=mongo):
        resultado = q03.ejecutar("C016")

    # Assert
    assert resultado["cliente"] == {
        "id_cliente": "C016",
        "nombre": "Gustavo",
        "apellido": "Ibarra",
        "dni": "22345098",
        "obra_social": "PAMI",
        "activo": False,
    }
    assert [fila["id_registro"] for fila in resultado["historial"]] == [
        "RC001", "V003", "V015", "RC008",
    ]
    assert resultado["historial"][0]["tipo_registro"] == "receta"
    assert resultado["historial"][1]["tipo_registro"] == "venta"
    assert resultado["historial"][1]["estado"] == "Completada"
    assert resultado["historial"][1]["items"] == [{
        "id_producto": "PRD003",
        "producto": "Amoxicilina",
        "cantidad": 1,
        "precio_unit": 9800,
    }]
    assert resultado["historial"][2]["estado"] == "Anulada"
    assert resultado["historial"][2]["items"][0]["producto"] == "Paracetamol"


def test_un_cliente_sin_movimientos_devuelve_historial_vacio(mongo):
    # Arrange
    mongo.clientes.insert_one({
        "_id": "C010",
        "nombre": "Tomás",
        "apellido": "Herrera",
        "dni": "35667210",
        "obra_social": "IOMA",
        "activo": True,
    })

    # Act
    with patch("farmared.consultas.q03_historial_cliente.get_db", return_value=mongo):
        resultado = q03.ejecutar("C010")

    # Assert
    assert resultado["historial"] == []
    assert resultado["cliente"]["id_cliente"] == "C010"
