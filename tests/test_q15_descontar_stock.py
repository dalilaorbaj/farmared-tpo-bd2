"""
Contrato de q15.ejecutar().

Necesita un Redis real (el script Lua no corre en memoria) y un Mongo con la
venta. Cada test arma el estado, ejecuta y verifica el HASH lote:x Y
lotes:unidades.
"""
import pytest

pytestmark = pytest.mark.skip(reason="TODO: q15 sin implementar")


def test_descuenta_en_orden_fefo_y_saltea_vencidos():
    # TODO: PRD002 x10 en S001 -> L020 (vencido) no se toca; L019 (8) y L004 (2).
    ...


def test_stock_insuficiente_rechaza_sin_tocar_ningun_lote():
    # TODO: PRD002 x120 en S001 (hay 98 vigentes) -> excepción y lotes intactos.
    ...


def test_un_item_sin_stock_no_descuenta_los_demas():
    # TODO: venta de dos ítems, el segundo no alcanza -> el primero tampoco se descuenta.
    ...


def test_no_descuenta_dos_veces_la_misma_venta():
    # TODO: usa el flag stock_descontado.
    ...


def test_venta_no_completada_o_inexistente_se_rechaza():
    # TODO
    ...
