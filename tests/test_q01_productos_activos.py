"""
Contrato de q01.ejecutar().

Cada test fija productos, proveedores y la cache, llama a la consulta y verifica
el catálogo activo. Mongo y Redis están reemplazados en memoria; el pipeline
y la cache son los que corren.
"""
from contextlib import contextmanager
from unittest.mock import patch

import fakeredis
import mongomock

from farmared.consultas import q01_productos_activos as q01


@contextmanager
def motores():
    db = mongomock.MongoClient()["farmared"]
    redis = fakeredis.FakeRedis(decode_responses=True)
    with (
        patch("farmared.consultas.q01_productos_activos.get_db", return_value=db),
        patch("farmared.consultas.q01_productos_activos.get_redis", return_value=redis),
    ):
        yield db, redis


def test_devuelve_solo_activos_con_su_proveedor_ordenados_por_id():
    # Arrange
    with motores() as (db, _redis):
        db.proveedores.insert_one({"_id": "PRV001", "razon_social": "Lab Norte", "activo": True})
        db.productos.insert_many([
            {"_id": "PRD002", "nombre": "Ibuprofeno", "activo": True, "id_proveedor": "PRV001", "precio_unit": 3500},
            {"_id": "PRD001", "nombre": "Paracetamol", "activo": False, "id_proveedor": "PRV001", "precio_unit": 2800},
            {"_id": "PRD003", "nombre": "Amoxicilina", "activo": True, "id_proveedor": "PRV001", "precio_unit": 9800},
        ])

        # Act
        resultado = q01.ejecutar()

    # Assert
    assert [p["_id"] for p in resultado] == ["PRD002", "PRD003"]
    assert resultado[0]["proveedor"]["_id"] == "PRV001"
    assert resultado[0]["proveedor"]["razon_social"] == "Lab Norte"


def test_un_producto_activo_sin_proveedor_igual_aparece():
    # Arrange
    with motores() as (db, _redis):
        db.productos.insert_one({
            "_id": "PRD009", "nombre": "Huérfano", "activo": True, "id_proveedor": "PRV999",
        })

        # Act
        resultado = q01.ejecutar()

    # Assert
    assert resultado == [{
        "_id": "PRD009", "nombre": "Huérfano", "activo": True, "id_proveedor": "PRV999",
    }]


def test_la_segunda_lectura_sale_de_cache():
    # Arrange
    with motores() as (db, redis):
        db.productos.insert_one({"_id": "PRD001", "nombre": "Paracetamol", "activo": True})
        q01.ejecutar()
        db.productos.update_one({"_id": "PRD001"}, {"$set": {"activo": False}})
        db.productos.insert_one({"_id": "PRD002", "nombre": "Ibuprofeno", "activo": True})

        # Act
        resultado = q01.ejecutar()

    # Assert
    assert [p["_id"] for p in resultado] == ["PRD001"]
    assert redis.ttl(q01.CLAVE_CACHE) == q01.TTL_SEGUNDOS


def test_sin_cache_vuelve_a_leer_mongo_y_la_refresca():
    # Arrange
    with motores() as (db, _redis):
        db.productos.insert_one({"_id": "PRD001", "nombre": "Paracetamol", "activo": True})
        q01.ejecutar()
        db.productos.insert_one({"_id": "PRD002", "nombre": "Ibuprofeno", "activo": True})

        # Act
        resultado = q01.ejecutar(usar_cache=False)
        siguiente = q01.ejecutar()

    # Assert
    assert [p["_id"] for p in resultado] == ["PRD001", "PRD002"]
    assert [p["_id"] for p in siguiente] == ["PRD001", "PRD002"]


def test_desde_la_terminal_false_llega_como_texto_y_no_usa_la_cache():
    with motores() as (db, _redis):
        db.productos.insert_one({"_id": "PRD001", "nombre": "Paracetamol", "activo": True})
        q01.ejecutar()
        db.productos.insert_one({"_id": "PRD002", "nombre": "Ibuprofeno", "activo": True})

        resultado = q01.ejecutar("false")

    assert [p["_id"] for p in resultado] == ["PRD001", "PRD002"]


def test_invalidar_cache_obliga_a_releer():
    # Arrange
    with motores() as (db, _redis):
        db.productos.insert_one({"_id": "PRD001", "nombre": "Paracetamol", "activo": True})
        q01.ejecutar()
        db.productos.update_one({"_id": "PRD001"}, {"$set": {"activo": False}})

        # Act
        q01.invalidar_cache()
        resultado = q01.ejecutar()

    # Assert
    assert resultado == []
