"""
Contrato de q04.ejecutar().

Cada test fija recetas y clientes, llama a la consulta y verifica quién tiene
más de una. Mongo está reemplazado por una base en memoria; el pipeline es el
que corre.
"""
from contextlib import contextmanager
from unittest.mock import patch

import mongomock

from farmared.consultas import q04_clientes_varias_recetas as q04


@contextmanager
def mongo_en_memoria():
    db = mongomock.MongoClient()["farmared"]
    with patch("farmared.consultas.q04_clientes_varias_recetas.get_db", return_value=db):
        yield db


def cliente(id_cliente, nombre, apellido):
    return {"_id": id_cliente, "nombre": nombre, "apellido": apellido}


def receta(id_receta, id_cliente, estado="Vigente"):
    return {"_id": id_receta, "id_cliente": id_cliente, "estado": estado}


def fila(id_cliente, nombre, apellido, cantidad):
    return {
        "id_cliente": id_cliente,
        "nombre": nombre,
        "apellido": apellido,
        "cantidad_recetas": cantidad,
    }


def test_cuenta_todas_las_recetas_y_ordena_por_cantidad():
    # Arrange
    with mongo_en_memoria() as db:
        db.clientes.insert_many([
            cliente("C001", "Lucía", "Fernández"),
            cliente("C017", "Florencia", "Luna"),
            cliente("C010", "Tomás", "Herrera"),
        ])
        db.recetas.insert_many([
            receta("RC001", "C001", "Completada"),
            receta("RC008", "C001", "Vencida"),
            receta("RC011", "C017"),
            receta("RC012", "C017"),
            receta("RC018", "C017", "Vencida"),
            receta("RC020", "C010"),
        ])

        # Act
        resultado = q04.ejecutar()

    # Assert
    assert resultado == [
        fila("C017", "Florencia", "Luna", 3),
        fila("C001", "Lucía", "Fernández", 2),
    ]


def test_en_empate_de_cantidad_prioriza_el_id_menor():
    # Arrange
    with mongo_en_memoria() as db:
        db.clientes.insert_many([
            cliente("C010", "Tomás", "Herrera"),
            cliente("C002", "Martín", "Gómez"),
        ])
        db.recetas.insert_many([
            receta("RC1", "C010"),
            receta("RC2", "C010"),
            receta("RC3", "C002"),
            receta("RC4", "C002"),
        ])

        # Act
        resultado = q04.ejecutar()

    # Assert
    assert [fila["id_cliente"] for fila in resultado] == ["C002", "C010"]


def test_sin_clientes_con_mas_de_una_devuelve_lista_vacia():
    # Arrange
    with mongo_en_memoria() as db:
        db.clientes.insert_one(cliente("C010", "Tomás", "Herrera"))
        db.recetas.insert_one(receta("RC020", "C010"))

        # Act
        resultado = q04.ejecutar()

    # Assert
    assert resultado == []
