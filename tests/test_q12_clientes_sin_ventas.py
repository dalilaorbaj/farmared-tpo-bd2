"""
Contrato de q12.ejecutar().

Cada test fija un "hoy" y un conjunto de clientes y ventas, llama a la consulta
y verifica quién queda afuera del último año. Mongo está reemplazado por una
base en memoria y hoy() está fijado; el pipeline es el que corre.
"""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import mongomock
import pytest

from farmared.consultas import q12_clientes_sin_ventas as q12


def dia(texto):
    return datetime.strptime(texto, "%Y-%m-%d")


@contextmanager
def mongo_en_memoria(hoy):
    db = mongomock.MongoClient()["farmared"]
    with (
        patch("farmared.consultas.q12_clientes_sin_ventas.get_db", return_value=db),
        patch("farmared.consultas.q12_clientes_sin_ventas.fechas.hoy", return_value=hoy),
    ):
        yield db


def cliente(id_cliente, nombre, apellido, dni, activo=True):
    return {
        "_id": id_cliente,
        "nombre": nombre,
        "apellido": apellido,
        "dni": dni,
        "activo": activo,
    }


def venta(id_venta, id_cliente, fecha, estado="Completada"):
    return {
        "_id": id_venta,
        "id_cliente": id_cliente,
        "fecha": dia(fecha),
        "estado": estado,
    }


def fila(id_cliente, nombre, apellido, dni, activo=True):
    return {
        "id_cliente": id_cliente,
        "nombre": nombre,
        "apellido": apellido,
        "dni": dni,
        "activo": activo,
    }


def test_incluye_sin_ventas_y_con_la_ultima_anterior_al_anio():
    # Arrange
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.clientes.insert_many([
            cliente("C014", "Diego", "Ferreyra", "30112457"),
            cliente("C008", "Hugo", "Mansilla", "25678901", activo=False),
            cliente("C001", "Lucía", "Fernández", "31245678"),
            cliente("C010", "Tomás", "Herrera", "35667210"),
        ])
        db.ventas.insert_many([
            venta("V022", "C014", "2025-08-14"),
            venta("V013", "C001", "2026-10-02"),
        ])

        # Act
        resultado = q12.ejecutar()

    # Assert
    assert resultado == [
        fila("C008", "Hugo", "Mansilla", "25678901", activo=False),
        fila("C010", "Tomás", "Herrera", "35667210"),
        fila("C014", "Diego", "Ferreyra", "30112457"),
    ]


def test_una_anulada_del_anio_alcanza_para_excluirlo():
    # Arrange
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.clientes.insert_one(cliente("C004", "Federico", "Navarro", "33987654"))
        db.ventas.insert_many([
            venta("V001", "C004", "2025-09-18"),
            venta("V031", "C004", "2026-10-26", estado="Anulada"),
        ])

        # Act
        resultado = q12.ejecutar()

    # Assert
    assert resultado == []


def test_una_pendiente_del_anio_alcanza_para_excluirlo():
    # Arrange
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.clientes.insert_one(cliente("C007", "Julieta", "Cabrera", "39234567"))
        db.ventas.insert_one(venta("V011", "C007", "2026-10-12", estado="Pendiente"))

        # Act
        resultado = q12.ejecutar()

    # Assert
    assert resultado == []


def test_el_dia_del_corte_entra_en_el_anio_y_el_anterior_no():
    # Arrange
    # hoy 2026-11-07 → el corte es 2025-11-07
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.clientes.insert_many([
            cliente("C001", "Lucía", "Fernández", "31245678"),
            cliente("C002", "Martín", "Gómez", "28765432"),
        ])
        db.ventas.insert_many([
            venta("V1", "C001", "2025-11-07"),
            venta("V2", "C002", "2025-11-06"),
        ])

        # Act
        resultado = q12.ejecutar()

    # Assert
    assert resultado == [
        fila("C002", "Martín", "Gómez", "28765432"),
    ]


def test_sin_considerar_anuladas_c004_entra():
    # Arrange
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.clientes.insert_many([
            cliente("C004", "Federico", "Navarro", "33987654"),
            cliente("C001", "Lucía", "Fernández", "31245678"),
        ])
        db.ventas.insert_many([
            venta("V001", "C004", "2025-09-18"),
            venta("V031", "C004", "2026-10-26", estado="Anulada"),
            venta("V013", "C001", "2026-10-02"),
        ])

        # Act
        resultado = q12.ejecutar("false")

    # Assert
    assert resultado == [
        fila("C004", "Federico", "Navarro", "33987654"),
    ]


def test_sin_considerar_anuladas_una_pendiente_sigue_excluyendo():
    # Arrange
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.clientes.insert_one(cliente("C007", "Julieta", "Cabrera", "39234567"))
        db.ventas.insert_one(venta("V011", "C007", "2026-10-12", estado="Pendiente"))

        # Act
        resultado = q12.ejecutar(False)

    # Assert
    assert resultado == []


def test_considerar_anuladas_rechaza_un_valor_desconocido():
    # Arrange
    argumento = "quizas"

    # Act
    with pytest.raises(ValueError, match="considerar_anuladas"):
        q12.ejecutar(argumento)


def test_una_anulada_anterior_al_anio_no_lo_saca():
    # Arrange
    with mongo_en_memoria(dia("2026-11-07")) as db:
        db.clientes.insert_one(cliente("C009", "Valentina", "Ortiz", "42118733"))
        db.ventas.insert_one(venta("V1", "C009", "2025-06-01", estado="Anulada"))

        # Act
        resultado = q12.ejecutar()

    # Assert
    assert resultado == [
        fila("C009", "Valentina", "Ortiz", "42118733"),
    ]
