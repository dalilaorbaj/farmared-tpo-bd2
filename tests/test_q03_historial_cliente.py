"""
Contrato de q03.ejecutar() para los errores, sin Mongo.

Falta el id, o el cliente no existe: la consulta responde un error y no arma
el historial. La línea de tiempo está en tests/integracion, contra Mongo real.
"""
from contextlib import contextmanager
from unittest.mock import patch

import mongomock

from farmared.consultas import q03_historial_cliente as q03


@contextmanager
def mongo_en_memoria():
    db = mongomock.MongoClient()["farmared"]
    with patch("farmared.consultas.q03_historial_cliente.get_db", return_value=db):
        yield db


def test_sin_id_devuelve_error_y_no_consulta():
    # Arrange
    # Act
    resultado = q03.ejecutar()

    # Assert
    assert resultado == {
        "error": "Falta el id del cliente. Uso: python main.py q03 <id_cliente>",
    }


def test_cliente_inexistente_devuelve_error():
    # Arrange
    with mongo_en_memoria() as db:
        db.clientes.insert_one({"_id": "C001", "nombre": "Lucía"})

        # Act
        resultado = q03.ejecutar("C404")

    # Assert
    assert resultado == {"error": "No existe el cliente 'C404'"}
