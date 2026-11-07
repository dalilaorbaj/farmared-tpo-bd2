"""
Contrato de q06.ejecutar().

Cada test fija un "hoy" y recetas, llama a la consulta y verifica cuáles están
atrasadas. Mongo está reemplazado por una base en memoria y hoy() está fijado;
el pipeline es el que corre.
"""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import mongomock

from farmared.consultas import q06_tratamientos_atrasados as q06


def dia(texto):
    return datetime.strptime(texto, "%Y-%m-%d")


@contextmanager
def mongo_en_memoria(hoy):
    db = mongomock.MongoClient()["farmared"]
    with (
        patch("farmared.consultas.q06_tratamientos_atrasados.get_db", return_value=db),
        patch("farmared.consultas.q06_tratamientos_atrasados.fechas.hoy", return_value=hoy),
    ):
        yield db


def test_solo_tratamientos_vigentes_con_dispensa_anterior_a_hoy():
    # Arrange
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.clientes.insert_many([
            {"_id": "C016", "nombre": "Gustavo", "apellido": "Ibarra", "telefono": "1156781122", "email": "g@mail.com", "activo": False},
            {"_id": "C003", "nombre": "Carla", "apellido": "Ruiz", "telefono": "3515334455", "email": "c@mail.com", "activo": True},
        ])
        db.recetas.insert_many([
            {
                "_id": "RC010", "tipo": "Tratamiento prolongado", "estado": "Vigente",
                "proxima_dispensa": dia("2026-11-01"), "fecha_emision": dia("2026-08-01"),
                "dispensas_autorizadas": 3, "dispensas_realizadas": 1, "id_cliente": "C016",
            },
            {
                "_id": "RC002", "tipo": "Tratamiento prolongado", "estado": "Vigente",
                "proxima_dispensa": dia("2026-10-15"), "fecha_emision": dia("2026-07-15"),
                "dispensas_autorizadas": 3, "dispensas_realizadas": 2, "id_cliente": "C003",
            },
        ])

        # Act
        resultado = q06.ejecutar()

    # Assert
    assert resultado == [
        {
            "id_receta": "RC002",
            "fecha_emision": dia("2026-07-15"),
            "proxima_dispensa": dia("2026-10-15"),
            "dispensas_autorizadas": 3,
            "dispensas_realizadas": 2,
            "cliente": {
                "id": "C003",
                "nombre": "Carla Ruiz",
                "telefono": "3515334455",
                "email": "c@mail.com",
                "activo": True,
            },
        },
        {
            "id_receta": "RC010",
            "fecha_emision": dia("2026-08-01"),
            "proxima_dispensa": dia("2026-11-01"),
            "dispensas_autorizadas": 3,
            "dispensas_realizadas": 1,
            "cliente": {
                "id": "C016",
                "nombre": "Gustavo Ibarra",
                "telefono": "1156781122",
                "email": "g@mail.com",
                "activo": False,
            },
        },
    ]


def test_hoy_simple_vencida_y_sin_fecha_no_entran():
    # Arrange
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.clientes.insert_one({
            "_id": "C001", "nombre": "Lucía", "apellido": "Fernández",
            "telefono": "1", "email": "l@mail.com", "activo": True,
        })
        db.recetas.insert_many([
            {"_id": "RC1", "tipo": "Tratamiento prolongado", "estado": "Vigente", "proxima_dispensa": dia("2026-11-07"), "id_cliente": "C001", "fecha_emision": dia("2026-01-01"), "dispensas_autorizadas": 3, "dispensas_realizadas": 0},
            {"_id": "RC2", "tipo": "Simple", "estado": "Vigente", "proxima_dispensa": dia("2026-10-01"), "id_cliente": "C001"},
            {"_id": "RC3", "tipo": "Tratamiento prolongado", "estado": "Vencida", "proxima_dispensa": dia("2026-10-01"), "id_cliente": "C001"},
            {"_id": "RC4", "tipo": "Tratamiento prolongado", "estado": "Vigente", "proxima_dispensa": None, "id_cliente": "C001"},
            {"_id": "RC5", "tipo": "Tratamiento prolongado", "estado": "Completada", "proxima_dispensa": dia("2026-10-01"), "id_cliente": "C001"},
        ])

        # Act
        resultado = q06.ejecutar()

    # Assert
    assert resultado == []
