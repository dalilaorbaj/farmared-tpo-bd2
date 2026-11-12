"""
Contrato de q15.ejecutar().

Necesita un Redis real (el script Lua no corre en memoria) y un Mongo con la
venta. Cada test arma el estado, ejecuta y verifica el HASH lote:x Y
lotes:unidades.
"""
import pytest

pytestmark = pytest.mark.skip(reason="TODO: q15 sin implementar")


# FEFO, vencidos, stock insuficiente y todo-o-nada ya están probados contra Redis real
# en tests/integracion/test_q15_redis.py. Acá van los que necesitan la venta en Mongo.


def test_no_descuenta_dos_veces_la_misma_venta():
    # TODO: usa el flag stock_descontado.
    ...


def test_venta_no_completada_o_inexistente_se_rechaza():
    # TODO
    ...
