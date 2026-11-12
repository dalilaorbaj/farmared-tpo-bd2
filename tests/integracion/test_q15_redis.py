"""
Script Lua de q15 contra un Redis real.

El Lua no corre en memoria, así que estos tests necesitan un Redis (el del
Codespace, localhost:6379 o REDIS_HOST/REDIS_PORT). Si no hay, se saltean.
Usan la base 15 y la vacían antes y después de cada test, así que no tocan los
datos cargados en la base 0.

Los vencimientos son relativos a hoy: nada de fechas fijas.
"""
from datetime import timedelta

import pytest
import redis

from farmared import config, fechas
from farmared.consultas.q15_descontar_stock import StockInsuficiente, descontar_lotes

SUC = "S001"


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


def lote(r, id_lote, prod, unidades, dias, suc=SUC):
    """Crea un lote que vence dentro de `dias` días (negativo = ya vencido)."""
    venc = fechas.hoy() + timedelta(days=dias)
    r.hset(f"lote:{id_lote}", mapping={
        "id_lote": id_lote, "id_producto": prod, "id_sucursal": suc, "nro_lote": f"N-{id_lote}",
        "unidades": unidades, "vencimiento": fechas.a_texto(venc),
    })
    r.zadd(f"stock:{suc}:{prod}", {id_lote: fechas.a_score(venc)})
    r.zadd("lotes:unidades", {id_lote: unidades})


def unidades(r, id_lote):
    """Las unidades tienen que coincidir en el HASH y en lotes:unidades."""
    en_hash = int(r.hget(f"lote:{id_lote}", "unidades"))
    en_zset = int(r.zscore("lotes:unidades", id_lote))
    assert en_hash == en_zset
    return en_hash


def test_fefo_saltea_vencidos_y_consume_primero_el_que_vence_antes(r):
    lote(r, "L-vencido", "P1", 25, -10)
    lote(r, "L-proximo", "P1", 8, 5)
    lote(r, "L-lejano", "P1", 90, 300)

    descontado = descontar_lotes(r, SUC, [{"id_producto": "P1", "cantidad": 10}])

    assert descontado == [{"lote": "L-proximo", "unidades": 8}, {"lote": "L-lejano", "unidades": 2}]
    assert unidades(r, "L-vencido") == 25
    assert unidades(r, "L-proximo") == 0
    assert unidades(r, "L-lejano") == 88


def test_stock_insuficiente_no_toca_ningun_lote(r):
    lote(r, "L-vencido", "P1", 25, -10)
    lote(r, "L-a", "P1", 8, 5)
    lote(r, "L-b", "P1", 90, 300)

    with pytest.raises(StockInsuficiente):
        descontar_lotes(r, SUC, [{"id_producto": "P1", "cantidad": 120}])  # vigentes: 98

    assert [unidades(r, i) for i in ("L-vencido", "L-a", "L-b")] == [25, 8, 90]


def test_si_un_item_no_alcanza_los_demas_tampoco_se_descuentan(r):
    lote(r, "L-p1", "P1", 50, 100)
    lote(r, "L-p2", "P2", 3, 100)

    with pytest.raises(StockInsuficiente):
        descontar_lotes(r, SUC, [
            {"id_producto": "P1", "cantidad": 10},
            {"id_producto": "P2", "cantidad": 5},
        ])

    assert unidades(r, "L-p1") == 50
    assert unidades(r, "L-p2") == 3


def test_mismo_producto_en_dos_items_se_suma_y_no_descuenta_dos_veces_el_mismo_stock(r):
    lote(r, "L-a", "P1", 10, 5)
    lote(r, "L-b", "P1", 10, 50)

    descontado = descontar_lotes(r, SUC, [
        {"id_producto": "P1", "cantidad": 7},
        {"id_producto": "P1", "cantidad": 7},
    ])

    assert descontado == [{"lote": "L-a", "unidades": 10}, {"lote": "L-b", "unidades": 4}]
    assert unidades(r, "L-a") == 0
    assert unidades(r, "L-b") == 6


def test_lote_que_vence_hoy_todavia_se_puede_dispensar(r):
    lote(r, "L-hoy", "P1", 5, 0)

    assert descontar_lotes(r, SUC, [{"id_producto": "P1", "cantidad": 5}]) == [{"lote": "L-hoy", "unidades": 5}]


def test_producto_sin_stock_en_la_sucursal_se_rechaza(r):
    lote(r, "L-otra", "P1", 100, 100, suc="S002")

    with pytest.raises(StockInsuficiente):
        descontar_lotes(r, SUC, [{"id_producto": "P1", "cantidad": 1}])
    assert unidades(r, "L-otra") == 100


def test_compensacion_devolver_lo_descontado_restaura_el_estado(r):
    """Lo que devuelve el script alcanza para deshacer el descuento (q14)."""
    lote(r, "L-a", "P1", 8, 5)
    lote(r, "L-b", "P1", 90, 300)

    descontado = descontar_lotes(r, SUC, [{"id_producto": "P1", "cantidad": 10}])
    for d in descontado:
        nuevas = r.hincrby(f"lote:{d['lote']}", "unidades", d["unidades"])
        r.zadd("lotes:unidades", {d["lote"]: nuevas})

    assert unidades(r, "L-a") == 8
    assert unidades(r, "L-b") == 90
