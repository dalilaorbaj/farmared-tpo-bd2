"""
Contrato de q08.ejecutar().

Cada test carga lotes en el sorted set de unidades y sus fichas, llama a la
consulta y verifica cuáles están bajo el límite. Redis y Mongo están
reemplazados en memoria.
"""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import fakeredis
import mongomock

from farmared.consultas import q08_lotes_stock_bajo as q08


def dia(texto):
    return datetime.strptime(texto, "%Y-%m-%d")


@contextmanager
def motores(hoy="2026-11-07"):
    db = mongomock.MongoClient()["farmared"]
    redis = fakeredis.FakeRedis(decode_responses=True)
    with (
        patch("farmared.consultas.q08_lotes_stock_bajo.get_db", return_value=db),
        patch("farmared.consultas.q08_lotes_stock_bajo.get_redis", return_value=redis),
        patch("farmared.consultas.q08_lotes_stock_bajo.fechas.hoy", return_value=dia(hoy)),
    ):
        yield db, redis


def lote(redis, id_lote, unidades, vencimiento, id_producto, id_sucursal, nro_lote):
    redis.zadd("lotes:unidades", {id_lote: unidades})
    redis.hset(f"lote:{id_lote}", mapping={
        "id_lote": id_lote,
        "nro_lote": nro_lote,
        "unidades": str(unidades),
        "vencimiento": vencimiento,
        "id_producto": id_producto,
        "id_sucursal": id_sucursal,
    })


def test_trae_los_lotes_estrictamente_bajo_el_limite_ordenados_por_unidades():
    # Arrange
    with motores() as (db, redis):
        db.productos.insert_one({"_id": "PRD002", "nombre": "Ibuprofeno", "id_proveedor": "PRV001"})
        db.proveedores.insert_one({"_id": "PRV001", "razon_social": "Lab Norte", "telefono": "1148001001"})
        db.sucursales.insert_one({"_id": "S001", "nombre": "Farmacia Palermo", "tipo": "Farmacia"})
        lote(redis, "L029", 49, "2026-11-01", "PRD002", "S001", "B029")
        lote(redis, "L004", 10, "2026-12-01", "PRD002", "S001", "B004")
        lote(redis, "L001", 50, "2026-11-01", "PRD002", "S001", "B001")

        # Act
        resultado = q08.ejecutar()

    # Assert
    assert resultado == [
        {
            "id_lote": "L004",
            "nro_lote": "B004",
            "unidades": 10,
            "vencimiento": "2026-12-01",
            "vencido": False,
            "producto": {"id": "PRD002", "nombre": "Ibuprofeno"},
            "sucursal": {"id": "S001", "nombre": "Farmacia Palermo", "tipo": "Farmacia"},
            "proveedor": {"id": "PRV001", "razon_social": "Lab Norte", "telefono": "1148001001"},
        },
        {
            "id_lote": "L029",
            "nro_lote": "B029",
            "unidades": 49,
            "vencimiento": "2026-11-01",
            "vencido": True,
            "producto": {"id": "PRD002", "nombre": "Ibuprofeno"},
            "sucursal": {"id": "S001", "nombre": "Farmacia Palermo", "tipo": "Farmacia"},
            "proveedor": {"id": "PRV001", "razon_social": "Lab Norte", "telefono": "1148001001"},
        },
    ]


def test_el_limite_llega_como_texto_y_es_estricto():
    # Arrange
    with motores() as (db, redis):
        db.productos.insert_one({"_id": "PRD001", "nombre": "Paracetamol", "id_proveedor": "PRV001"})
        db.proveedores.insert_one({"_id": "PRV001", "razon_social": "Lab Norte", "telefono": "1"})
        db.sucursales.insert_one({"_id": "S001", "nombre": "Farmacia Palermo", "tipo": "Farmacia"})
        lote(redis, "L010", 10, "2027-01-01", "PRD001", "S001", "B010")
        lote(redis, "L009", 9, "2027-01-01", "PRD001", "S001", "B009")

        # Act
        resultado = q08.ejecutar("10")

    # Assert
    assert [fila["id_lote"] for fila in resultado] == ["L009"]


def test_sin_lotes_bajo_el_limite_devuelve_lista_vacia():
    # Arrange
    with motores() as (_db, redis):
        lote(redis, "L001", 50, "2027-01-01", "PRD001", "S001", "B001")

        # Act
        resultado = q08.ejecutar()

    # Assert
    assert resultado == []


def test_sin_ficha_de_producto_los_datos_de_catalogo_son_nulos():
    # Arrange
    with motores() as (_db, redis):
        lote(redis, "L404", 3, "2026-10-01", "PRD404", "S404", "B404")

        # Act
        resultado = q08.ejecutar()

    # Assert
    assert resultado[0]["producto"] == {"id": "PRD404", "nombre": None}
    assert resultado[0]["sucursal"] == {"id": "S404", "nombre": None, "tipo": None}
    assert resultado[0]["proveedor"] == {"id": None, "razon_social": None, "telefono": None}
    assert resultado[0]["vencido"] is True
