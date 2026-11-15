"""
q15.descontar(id_venta): venta en Mongo (en memoria, mongomock) + stock en un
Redis real (base 15). Si no hay Redis, se saltea. Vencimientos relativos a hoy.
"""
from datetime import timedelta
from unittest.mock import patch

import mongomock
import pytest
import redis

from farmared import config, fechas
from farmared.consultas import q15_descontar_stock as q15
from farmared.consultas.q15_descontar_stock import StockInsuficiente, VentaInvalida


@pytest.fixture
def r():
    cliente = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, db=15, decode_responses=True)
    try:
        cliente.ping()
    except redis.RedisError:
        pytest.skip("No hay Redis disponible")
    cliente.flushdb()
    yield cliente
    cliente.flushdb()


@pytest.fixture
def entorno(r):
    """Mongo en memoria + Redis real, con una venta V1 de 10 unidades de P1 en S001."""
    db = mongomock.MongoClient()["farmared"]
    db.farmaceuticos.insert_one({"_id": "F1", "id_sucursal": "S001"})
    db.ventas.insert_many([
        {"_id": "V1", "estado": "Completada", "id_farmaceutico": "F1", "stock_descontado": False,
         "items": [{"id_producto": "P1", "cantidad": 10, "precio_unit": 100}]},
        {"_id": "V-pend", "estado": "Pendiente", "id_farmaceutico": "F1", "stock_descontado": False,
         "items": [{"id_producto": "P1", "cantidad": 1, "precio_unit": 100}]},
        {"_id": "V-ya", "estado": "Completada", "id_farmaceutico": "F1", "stock_descontado": True,
         "items": [{"id_producto": "P1", "cantidad": 1, "precio_unit": 100}]},
    ])
    for id_lote, unidades, dias in [("L-a", 8, 5), ("L-b", 90, 300)]:
        venc = fechas.hoy() + timedelta(days=dias)
        r.hset(f"lote:{id_lote}", mapping={"unidades": unidades})
        r.zadd("stock:S001:P1", {id_lote: fechas.a_score(venc)})
        r.zadd("lotes:unidades", {id_lote: unidades})
    with patch.object(q15, "get_db", return_value=db), patch.object(q15, "get_redis", return_value=r):
        yield db, r


def stock(r):
    return [int(r.hget(f"lote:{i}", "unidades")) for i in ("L-a", "L-b")]


def test_descuenta_y_marca_la_venta(entorno):
    db, r = entorno

    resultado = q15.descontar("V1")

    assert resultado["ok"] is True
    assert (resultado["id_venta"], resultado["id_sucursal"]) == ("V1", "S001")
    assert resultado["descontado"] == [{"lote": "L-a", "unidades": 8}, {"lote": "L-b", "unidades": 2}]
    assert stock(r) == [0, 88]
    assert db.ventas.find_one({"_id": "V1"})["stock_descontado"] is True


def test_no_descuenta_dos_veces_la_misma_venta(entorno):
    db, r = entorno
    q15.descontar("V1")

    with pytest.raises(VentaInvalida):
        q15.descontar("V1")

    assert stock(r) == [0, 88]


@pytest.mark.parametrize("id_venta", ["V-pend", "V-ya", "V-no-existe"])
def test_venta_pendiente_ya_descontada_o_inexistente_no_toca_nada(entorno, id_venta):
    db, r = entorno

    with pytest.raises(VentaInvalida):
        q15.descontar(id_venta)

    assert stock(r) == [8, 90]


def test_stock_insuficiente_no_toca_lotes_ni_marca_la_venta(entorno):
    db, r = entorno
    db.ventas.update_one({"_id": "V1"}, {"$set": {"items": [{"id_producto": "P1", "cantidad": 999, "precio_unit": 1}]}})

    with pytest.raises(StockInsuficiente):
        q15.descontar("V1")

    assert stock(r) == [8, 90]
    assert db.ventas.find_one({"_id": "V1"})["stock_descontado"] is False


def test_si_otra_ejecucion_ya_marco_la_venta_se_devuelve_lo_descontado(entorno):
    """Carrera: las dos leyeron la venta sin marcar. La segunda no consigue
    marcarla y tiene que devolver lo que descontó."""
    db, r = entorno
    venta_vieja = db.ventas.find_one({"_id": "V1"})  # leída antes de que la otra la marque
    db.ventas.update_one({"_id": "V1"}, {"$set": {"stock_descontado": True}})

    with patch.object(q15, "_leer_venta_y_sucursal", return_value=(venta_vieja, "S001")):
        with pytest.raises(VentaInvalida):
            q15.descontar("V1")

    assert stock(r) == [8, 90]
    assert r.zscore("lotes:unidades", "L-a") == 8


def test_devolver_lotes_restaura_hash_y_zset(entorno):
    db, r = entorno
    resultado = q15.descontar("V1")

    q15.devolver_lotes(r, resultado["descontado"])

    assert stock(r) == [8, 90]
    assert r.zscore("lotes:unidades", "L-a") == 8
    assert r.zscore("lotes:unidades", "L-b") == 90


def test_venta_con_farmaceutico_inexistente_se_rechaza_sin_tocar_nada(entorno):
    db, r = entorno
    db.ventas.update_one({"_id": "V1"}, {"$set": {"id_farmaceutico": "F-no-existe"}})

    with pytest.raises(VentaInvalida, match="farmacéutico"):
        q15.descontar("V1")

    assert stock(r) == [8, 90]


def test_desde_la_terminal_el_rechazo_vuelve_como_ok_false_con_el_motivo(entorno):
    db, r = entorno

    assert q15.ejecutar("V1")["ok"] is True
    assert q15.ejecutar("V1") == {"ok": False, "error": "La venta V1 ya tiene el stock descontado"}
    assert q15.ejecutar("V-pend")["ok"] is False
    assert q15.ejecutar()["ok"] is False


def test_stock_insuficiente_desde_la_terminal(entorno):
    db, r = entorno
    db.ventas.update_one({"_id": "V1"}, {"$set": {"items": [{"id_producto": "P1", "cantidad": 999, "precio_unit": 1}]}})

    resultado = q15.ejecutar("V1")

    assert resultado["ok"] is False
    assert "Stock insuficiente" in resultado["error"]
    assert stock(r) == [8, 90]
