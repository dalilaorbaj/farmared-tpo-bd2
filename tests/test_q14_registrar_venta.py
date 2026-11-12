"""
Contrato de q14.ejecutar().

Las validaciones (fase 1) se prueban en memoria con mongomock, como q02. La
integración con la transacción y con Redis (más abajo) necesita servicios
reales y todavía no está implementada.
"""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import mongomock
import pytest

from farmared.consultas import q14_registrar_venta as q14
from farmared.consultas.q14_registrar_venta import VentaRechazada


def dia(texto):
    return datetime.strptime(texto, "%Y-%m-%d")


@contextmanager
def mongo_en_memoria():
    db = mongomock.MongoClient()["farmared"]
    db.clientes.insert_many([
        {"_id": "C009", "activo": True},
        {"_id": "C016", "activo": False},
        {"_id": "C017", "activo": True},
    ])
    db.sucursales.insert_many([
        {"_id": "S001", "tipo": "Farmacia", "activo": True},
        {"_id": "S014", "tipo": "Droguería", "activo": True},
        {"_id": "S015", "tipo": "Farmacia", "activo": False},
    ])
    db.farmaceuticos.insert_many([
        {"_id": "F019", "id_sucursal": "S001", "activo": True},
        {"_id": "F004", "id_sucursal": "S001", "activo": False},
        {"_id": "F017", "id_sucursal": "S014", "activo": True},
        {"_id": "F018", "id_sucursal": "S015", "activo": True},
    ])
    db.productos.insert_many([
        {"_id": "PRD002", "condicion_venta": "Venta libre", "precio_unit": 3500, "activo": True},
        {"_id": "PRD003", "condicion_venta": "Bajo receta", "precio_unit": 9800, "activo": True},
        {"_id": "PRD015", "condicion_venta": "Bajo receta archivada", "precio_unit": 6800, "activo": True},
        {"_id": "PRD025", "condicion_venta": "Bajo receta", "precio_unit": 14200, "activo": False},
    ])
    db.recetas.insert_many([
        {"_id": "RC015", "id_cliente": "C009", "estado": "Vigente", "fecha_emision": dia("2026-11-02")},
        {"_id": "RC013", "id_cliente": "C017", "estado": "Vencida", "fecha_emision": dia("2026-04-10")},
        {"_id": "RC017", "id_cliente": "C017", "estado": "Completada", "fecha_emision": dia("2026-09-05")},
    ])
    with patch("farmared.consultas.q14_registrar_venta.get_db", return_value=db):
        yield db


def venta(**cambios):
    """Una venta válida (libre) a la que se le pisan campos para armar cada caso."""
    base = {"id_cliente": "C009", "id_farmaceutico": "F019", "medio_pago": "Efectivo",
            "items": [{"id_producto": "PRD002", "cantidad": 2}]}
    base.update(cambios)
    return base


def con_receta(**cambios):
    return venta(**{"id_receta": "RC015", "items": [{"id_producto": "PRD003", "cantidad": 1}], **cambios})


# --- Validaciones: cada una rechaza con un motivo claro ------------------------

@pytest.mark.parametrize("datos, motivo", [
    (venta(id_cliente="C999"), "no existe"),
    (venta(id_cliente="C016"), "dado de baja"),
    (venta(id_farmaceutico="F999"), "no existe"),
    (venta(id_farmaceutico="F004"), "no está activo"),
    (venta(id_farmaceutico="F017"), "Droguería"),
    (venta(id_farmaceutico="F018"), "dada de baja"),
    (venta(items=[{"id_producto": "PRD999", "cantidad": 1}]), "no existe"),
    (venta(items=[{"id_producto": "PRD025", "cantidad": 1}]), "discontinuado"),
    (venta(items=[{"id_producto": "PRD003", "cantidad": 1}]), "hace falta 'id_receta'"),
    (con_receta(id_receta="RC999"), "no existe"),
    (con_receta(id_cliente="C017", id_receta="RC013"), "Vencida"),
    (con_receta(id_cliente="C017", id_receta="RC017"), "Completada"),
    (con_receta(id_cliente="C017"), "no es del cliente"),  # RC015 es vigente pero de C009
    (venta(id_receta="RC015"), "ningún producto la requiere"),
    (venta(items=[]), "items"),
    (venta(items=[{"id_producto": "PRD002", "cantidad": 0}]), "Cantidad inválida"),
    (venta(items=[{"id_producto": "PRD002", "cantidad": -3}]), "Cantidad inválida"),
    (venta(items=[{"id_producto": "PRD002", "cantidad": 1.5}]), "Cantidad inválida"),
    (venta(items=[{"id_producto": "PRD002"}]), "Cantidad inválida"),
    (venta(medio_pago="Bitcoin"), "Medio de pago inválido"),
    (venta(medio_pago=None), "medio_pago"),
])
def test_rechazos_de_validacion(datos, motivo):
    with mongo_en_memoria():
        with pytest.raises(VentaRechazada, match=motivo):
            q14._validar(datos)


def test_las_validaciones_no_escriben_nada():
    with mongo_en_memoria() as db:
        antes = {c: list(db[c].find()) for c in db.list_collection_names()}
        with pytest.raises(VentaRechazada):
            q14._validar(venta(id_cliente="C016"))
        q14._validar(venta())
        assert {c: list(db[c].find()) for c in db.list_collection_names()} == antes


# --- Validaciones OK: devuelven el contexto para las fases siguientes ---------------

def test_venta_libre_valida_devuelve_contexto_sin_receta():
    with mongo_en_memoria():
        ctx = q14._validar(venta())

    assert ctx["cliente"]["_id"] == "C009"
    assert ctx["sucursal"]["_id"] == "S001"
    assert set(ctx["productos"]) == {"PRD002"}
    assert ctx["receta"] is None


def test_venta_con_receta_valida_devuelve_la_receta():
    with mongo_en_memoria():
        ctx = q14._validar(con_receta())

    assert ctx["receta"]["_id"] == "RC015"


def test_mismo_producto_repetido_en_dos_items_es_valido():
    with mongo_en_memoria():
        q14._validar(venta(items=[{"id_producto": "PRD002", "cantidad": 1}, {"id_producto": "PRD002", "cantidad": 2}]))


# --- Todavía sin implementar (viernes y sábado) -------------------------------------

@pytest.mark.skip(reason="TODO viernes: _armar_venta")
def test_venta_libre_calcula_total_con_precios_del_catalogo():
    ...


@pytest.mark.skip(reason="TODO viernes: _cambios_receta")
def test_receta_simple_queda_completada():
    ...


@pytest.mark.skip(reason="TODO viernes: _cambios_receta")
def test_tratamiento_prolongado_con_dispensas_restantes_proxima_dispensa_30_dias():
    ...


@pytest.mark.skip(reason="TODO viernes: _cambios_receta")
def test_tratamiento_prolongado_ultima_dispensa_queda_completada():
    ...


@pytest.mark.skip(reason="TODO viernes: integración con transacción")
def test_sin_stock_no_queda_venta_ni_receta_modificada_ni_redis_tocado():
    ...


@pytest.mark.skip(reason="TODO sábado: compensación")
def test_falla_el_commit_compensa_el_stock_en_redis():
    ...
