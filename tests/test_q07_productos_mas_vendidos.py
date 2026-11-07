"""
Contrato de q07.ejecutar().

Cada test fija un estado de ventas y productos, llama a la consulta y verifica
el resultado observable: qué entra al top 5, en qué orden y con qué campos.
Mongo está reemplazado por una base en memoria; el pipeline es el que corre.
"""
from contextlib import contextmanager
from unittest.mock import patch

import mongomock
import pytest

from farmared.consultas import q07_productos_mas_vendidos as q07


@contextmanager
def mongo_en_memoria():
    db = mongomock.MongoClient()["farmared"]
    with patch("farmared.consultas.q07_productos_mas_vendidos.get_db", return_value=db):
        yield db


def venta(id_venta, estado, *items):
    return {
        "_id": id_venta,
        "estado": estado,
        "items": [
            {"id_producto": id_producto, "cantidad": cantidad, "precio_unit": 1}
            for id_producto, cantidad in items
        ],
    }


def producto(id_producto, nombre, activo=True):
    return {"_id": id_producto, "nombre": nombre, "activo": activo}


def fila(id_producto, nombre, unidades):
    return {"id_producto": id_producto, "nombre": nombre, "unidades": unidades}


def test_solo_suma_unidades_de_ventas_completadas():
    # Arrange
    with mongo_en_memoria() as db:
        db.productos.insert_many([
            producto("PRD001", "Paracetamol"),
            producto("PRD002", "Ibuprofeno"),
        ])
        db.ventas.insert_many([
            venta("V001", "Completada", ("PRD001", 4)),
            venta("V002", "Pendiente", ("PRD002", 100)),
            venta("V003", "Anulada", ("PRD001", 50)),
        ])

        # Act
        resultado = q07.ejecutar()

    # Assert
    assert resultado == [fila("PRD001", "Paracetamol", 4)]


def test_acumula_el_mismo_producto_en_varios_items_y_ventas():
    # Arrange
    with mongo_en_memoria() as db:
        db.productos.insert_one(producto("PRD001", "Paracetamol"))
        db.ventas.insert_many([
            venta("V001", "Completada", ("PRD001", 2), ("PRD001", 3)),
            venta("V002", "Completada", ("PRD001", 4)),
            venta("V003", "Pendiente", ("PRD001", 100)),
        ])

        # Act
        resultado = q07.ejecutar()

    # Assert
    assert resultado == [fila("PRD001", "Paracetamol", 9)]


def test_devuelve_como_maximo_cinco_ordenados_por_unidades():
    # Arrange
    with mongo_en_memoria() as db:
        db.productos.insert_many([
            producto(f"PRD00{n}", f"Producto {n}") for n in range(1, 7)
        ])
        db.ventas.insert_many([
            venta("V001", "Completada", ("PRD003", 30)),
            venta("V002", "Completada", ("PRD001", 10)),
            venta("V003", "Completada", ("PRD006", 60)),
            venta("V004", "Completada", ("PRD002", 20)),
            venta("V005", "Completada", ("PRD005", 50)),
            venta("V006", "Completada", ("PRD004", 40)),
        ])

        # Act
        resultado = q07.ejecutar()

    # Assert
    assert resultado == [
        fila("PRD006", "Producto 6", 60),
        fila("PRD005", "Producto 5", 50),
        fila("PRD004", "Producto 4", 40),
        fila("PRD003", "Producto 3", 30),
        fila("PRD002", "Producto 2", 20),
    ]


def test_en_empate_de_unidades_prioriza_el_id_menor():
    # Arrange
    with mongo_en_memoria() as db:
        db.productos.insert_many([
            producto("PRD00A", "A"),
            producto("PRD00B", "B"),
            producto("PRD00C", "C"),
            producto("PRD00D", "D"),
            producto("PRD002", "Entra"),
            producto("PRD010", "Queda afuera"),
        ])
        db.ventas.insert_many([
            venta("V001", "Completada", ("PRD00A", 50)),
            venta("V002", "Completada", ("PRD00B", 40)),
            venta("V003", "Completada", ("PRD00C", 30)),
            venta("V004", "Completada", ("PRD00D", 20)),
            venta("V005", "Completada", ("PRD010", 10)),
            venta("V006", "Completada", ("PRD002", 10)),
        ])

        # Act
        resultado = q07.ejecutar()

    # Assert
    assert resultado == [
        fila("PRD00A", "A", 50),
        fila("PRD00B", "B", 40),
        fila("PRD00C", "C", 30),
        fila("PRD00D", "D", 20),
        fila("PRD002", "Entra", 10),
    ]


def test_devuelve_todos_cuando_hay_menos_de_cinco():
    # Arrange
    with mongo_en_memoria() as db:
        db.productos.insert_many([
            producto("PRD002", "Ibuprofeno"),
            producto("PRD001", "Paracetamol"),
        ])
        db.ventas.insert_many([
            venta("V001", "Completada", ("PRD002", 3)),
            venta("V002", "Completada", ("PRD001", 8)),
        ])

        # Act
        resultado = q07.ejecutar()

    # Assert
    assert resultado == [
        fila("PRD001", "Paracetamol", 8),
        fila("PRD002", "Ibuprofeno", 3),
    ]


def test_sin_ventas_completadas_devuelve_lista_vacia():
    # Arrange
    with mongo_en_memoria() as db:
        db.productos.insert_one(producto("PRD001", "Paracetamol"))
        db.ventas.insert_many([
            venta("V001", "Pendiente", ("PRD001", 5)),
            venta("V002", "Anulada", ("PRD001", 9)),
        ])

        # Act
        resultado = q07.ejecutar()

    # Assert
    assert resultado == []


def test_un_producto_inactivo_igual_entra_en_el_ranking():
    # Arrange
    with mongo_en_memoria() as db:
        db.productos.insert_many([
            producto("PRD009", "Discontinuado", activo=False),
            producto("PRD001", "Paracetamol", activo=True),
        ])
        db.ventas.insert_many([
            venta("V001", "Completada", ("PRD009", 12)),
            venta("V002", "Completada", ("PRD001", 2)),
        ])

        # Act
        resultado = q07.ejecutar()

    # Assert
    assert resultado == [
        fila("PRD009", "Discontinuado", 12),
        fila("PRD001", "Paracetamol", 2),
    ]


def test_sin_ficha_en_el_catalogo_el_nombre_es_nulo():
    # Arrange
    with mongo_en_memoria() as db:
        db.ventas.insert_one(venta("V001", "Completada", ("PRD404", 2)))

        # Act
        resultado = q07.ejecutar()

    # Assert
    assert resultado == [fila("PRD404", None, 2)]


def _catalogo_con_un_inactivo_al_tope(db):
    db.productos.insert_many([
        producto("PRD001", "Discontinuado", activo=False),
        producto("PRD002", "Activo 2"),
        producto("PRD003", "Activo 3"),
        producto("PRD004", "Activo 4"),
        producto("PRD005", "Activo 5"),
        producto("PRD006", "Activo 6"),
        producto("PRD007", "Activo 7"),
    ])
    db.ventas.insert_many([
        venta("V001", "Completada", ("PRD001", 100)),
        venta("V002", "Completada", ("PRD002", 60)),
        venta("V003", "Completada", ("PRD003", 50)),
        venta("V004", "Completada", ("PRD004", 40)),
        venta("V005", "Completada", ("PRD005", 30)),
        venta("V006", "Completada", ("PRD006", 20)),
        venta("V007", "Completada", ("PRD007", 10)),
        venta("V008", "Completada", ("PRD404", 200)),
    ])


def test_solo_activos_rearma_el_top_5_sin_el_inactivo():
    # Arrange
    with mongo_en_memoria() as db:
        _catalogo_con_un_inactivo_al_tope(db)

        # Act
        resultado = q07.ejecutar("true")

    # Assert
    assert resultado == [
        fila("PRD002", "Activo 2", 60),
        fila("PRD003", "Activo 3", 50),
        fila("PRD004", "Activo 4", 40),
        fila("PRD005", "Activo 5", 30),
        fila("PRD006", "Activo 6", 20),
    ]


def test_solo_activos_en_false_conserva_inactivos_y_sin_ficha():
    # Arrange
    with mongo_en_memoria() as db:
        _catalogo_con_un_inactivo_al_tope(db)

        # Act
        resultado = q07.ejecutar("false")

    # Assert
    assert resultado == [
        fila("PRD404", None, 200),
        fila("PRD001", "Discontinuado", 100),
        fila("PRD002", "Activo 2", 60),
        fila("PRD003", "Activo 3", 50),
        fila("PRD004", "Activo 4", 40),
    ]


def test_solo_activos_rechaza_un_valor_desconocido():
    # Arrange
    argumento = "vigentes"

    # Act
    with pytest.raises(ValueError, match="solo_activos"):
        q07.ejecutar(argumento)
