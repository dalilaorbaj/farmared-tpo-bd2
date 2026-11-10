"""
Contrato de q14.ejecutar().

Las validaciones (fase 1) se pueden probar en memoria con mongomock, como
q02 (ver tests/test_q02_ventas_pendientes.py). La integración con la
transacción y Redis necesita servicios reales.
"""
import pytest

pytestmark = pytest.mark.skip(reason="TODO: q14 sin implementar")


# --- Validaciones (no deben escribir nada) ---------------------------------

@pytest.mark.parametrize("caso", [
    "cliente inexistente",
    "cliente dado de baja (C016)",
    "farmacéutico inexistente",
    "farmacéutico inactivo (F004)",
    "farmacéutico de una droguería (F017)",
    "producto inexistente",
    "producto discontinuado (PRD025)",
    "bajo receta sin receta",
    "receta vencida (RC013)",
    "receta de otro cliente",
    "items vacíos / cantidad <= 0 / medio de pago inválido",
])
def test_rechazos_de_validacion_no_escriben_nada(caso):
    # TODO: un test por caso (o parametrizar con datos reales).
    ...


# --- Camino feliz -----------------------------------------------------------

def test_venta_libre_calcula_total_con_precios_del_catalogo():
    # TODO
    ...


def test_receta_simple_queda_completada():
    # TODO: C009 + F019 + RC015 + PRD003 x1
    ...


def test_tratamiento_prolongado_con_dispensas_restantes_proxima_dispensa_30_dias():
    # TODO
    ...


def test_tratamiento_prolongado_ultima_dispensa_queda_completada():
    # TODO
    ...


# --- Integración con q15 (servicios reales) ---------------------------------

def test_sin_stock_no_queda_venta_ni_receta_modificada_ni_redis_tocado():
    # TODO: PRD002 x120 en S001.
    ...


def test_falla_el_commit_compensa_el_stock_en_redis():
    # TODO: forzar el error del commit (monkeypatch) y verificar que Redis vuelve al estado previo.
    ...
