"""
Contrato de q14.registrar().

Lo que no necesita transacciones se prueba en memoria con mongomock, como q02:
validaciones, armado de la venta y cambios de la receta. La transacción y el
descuento en Redis están en tests/integracion/test_q14_integracion.py.
"""
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

import mongomock
import pytest
from pymongo.errors import OperationFailure

from farmared import fechas
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
        {"_id": "RC015", "id_cliente": "C009", "estado": "Vigente", "fecha_emision": dia("2026-11-02"),
         "tipo": "Simple", "dispensas_autorizadas": 1, "dispensas_realizadas": 0},
        {"_id": "RC013", "id_cliente": "C017", "estado": "Vencida", "fecha_emision": dia("2026-04-10"),
         "tipo": "Simple", "dispensas_autorizadas": 1, "dispensas_realizadas": 0},
        {"_id": "RC017", "id_cliente": "C017", "estado": "Completada", "fecha_emision": dia("2026-09-05"),
         "tipo": "Tratamiento prolongado", "dispensas_autorizadas": 3, "dispensas_realizadas": 3},
        # dato inconsistente: figura Vigente pero ya usó todas las dispensas
        {"_id": "RC-agotada", "id_cliente": "C009", "estado": "Vigente", "fecha_emision": dia("2026-09-05"),
         "tipo": "Tratamiento prolongado", "dispensas_autorizadas": 3, "dispensas_realizadas": 3},
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
    (con_receta(id_receta="RC-agotada"), "no tiene dispensas disponibles"),
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


# --- Armar la venta ----------------------------------------------------------------

def test_armar_venta_usa_precios_del_catalogo_y_calcula_el_total():
    with mongo_en_memoria() as db:
        datos = venta(items=[{"id_producto": "PRD002", "cantidad": 2}, {"id_producto": "PRD003", "cantidad": 1}],
                      id_receta="RC015")
        productos = {p["_id"]: p for p in db.productos.find()}

        doc = q14._armar_venta(datos, productos, db)

    assert doc["items"] == [
        {"id_detalle": "D001", "id_producto": "PRD002", "cantidad": 2, "precio_unit": 3500},
        {"id_detalle": "D002", "id_producto": "PRD003", "cantidad": 1, "precio_unit": 9800},
    ]
    assert doc["total"] == 2 * 3500 + 9800
    assert doc["estado"] == "Completada"
    assert doc["tipo"] == "Con receta"
    assert doc["stock_descontado"] is False
    assert doc["fecha"] == fechas.hoy()


def test_armar_venta_libre_no_lleva_receta():
    with mongo_en_memoria() as db:
        doc = q14._armar_venta(venta(), {"PRD002": db.productos.find_one({"_id": "PRD002"})}, db)

    assert doc["tipo"] == "Venta libre"
    assert doc["id_receta"] is None


def test_los_id_detalle_siguen_al_mayor_de_todas_las_ventas():
    with mongo_en_memoria() as db:
        db.ventas.insert_many([
            {"_id": "V001", "items": [{"id_detalle": "D043"}, {"id_detalle": "D044"}]},
            {"_id": "V002", "items": [{"id_detalle": "D009"}]},
        ])
        datos = venta(items=[{"id_producto": "PRD002", "cantidad": 1}, {"id_producto": "PRD002", "cantidad": 3}])

        doc = q14._armar_venta(datos, {"PRD002": db.productos.find_one({"_id": "PRD002"})}, db)

    assert [it["id_detalle"] for it in doc["items"]] == ["D045", "D046"]


def test_el_id_de_la_venta_es_el_siguiente_al_mayor_aunque_pase_de_tres_digitos():
    with mongo_en_memoria() as db:
        assert q14._proximo_id_venta(db) == "V001"
        db.ventas.insert_many([{"_id": "V999"}, {"_id": "V1000"}, {"_id": "V002"}])
        assert q14._proximo_id_venta(db) == "V1001"


# --- Cambios en la receta (reglas 2.11) ----------------------------------------------

def test_receta_simple_queda_completada_sin_proxima_dispensa():
    receta = {"tipo": "Simple", "dispensas_autorizadas": 1, "dispensas_realizadas": 0}

    assert q14._cambios_receta(receta) == {
        "dispensas_realizadas": 1, "estado": "Completada", "proxima_dispensa": None}


def test_receta_archivada_queda_completada():
    receta = {"tipo": "Archivada", "dispensas_autorizadas": 1, "dispensas_realizadas": 0}

    assert q14._cambios_receta(receta)["estado"] == "Completada"


def test_tratamiento_prolongado_con_dispensas_restantes_proxima_dispensa_a_30_dias():
    receta = {"tipo": "Tratamiento prolongado", "dispensas_autorizadas": 3, "dispensas_realizadas": 1}

    cambios = q14._cambios_receta(receta)

    assert cambios == {"dispensas_realizadas": 2, "proxima_dispensa": fechas.hoy() + timedelta(days=30)}
    assert "estado" not in cambios  # sigue Vigente


def test_tratamiento_prolongado_ultima_dispensa_queda_completada():
    receta = {"tipo": "Tratamiento prolongado", "dispensas_autorizadas": 3, "dispensas_realizadas": 2}

    assert q14._cambios_receta(receta) == {
        "dispensas_realizadas": 3, "estado": "Completada", "proxima_dispensa": None}


# --- Entrada desde la terminal: el rechazo vuelve como ok=False, igual que q13 ---------

def test_ejecutar_devuelve_el_motivo_del_rechazo_en_vez_de_lanzar():
    with mongo_en_memoria():
        assert q14.ejecutar(json.dumps(venta(id_cliente="C016"))) == {
            "ok": False, "error": "El cliente C016 está dado de baja"}


@pytest.mark.parametrize("entrada, motivo", [
    ("{esto no es json", "JSON inválido"),
    ("[1, 2]", "objeto JSON"),
    (None, "uso: q14"),
])
def test_ejecutar_con_entrada_mal_formada(entrada, motivo):
    with mongo_en_memoria():
        resultado = q14.ejecutar(entrada) if entrada is not None else q14.ejecutar()

    assert resultado["ok"] is False
    assert motivo in resultado["error"]


# --- Commit con resultado desconocido --------------------------------------------------

class _SesionFalsa:
    def __init__(self, errores):
        self.errores, self.intentos = list(errores), 0

    def commit_transaction(self):
        self.intentos += 1
        if self.errores:
            raise self.errores.pop(0)


def _error_con_etiqueta(etiqueta):
    return OperationFailure("x", details={"errorLabels": [etiqueta]})


def test_el_commit_se_reintenta_mientras_el_resultado_sea_desconocido():
    sesion = _SesionFalsa([_error_con_etiqueta("UnknownTransactionCommitResult")] * 2)

    q14._commit(sesion)

    assert sesion.intentos == 3


def test_el_commit_no_se_reintenta_ante_otro_error():
    sesion = _SesionFalsa([OperationFailure("otro")])

    with pytest.raises(OperationFailure):
        q14._commit(sesion)
    assert sesion.intentos == 1


def test_el_commit_deja_de_reintentar_despues_de_los_intentos_configurados():
    sesion = _SesionFalsa([_error_con_etiqueta("UnknownTransactionCommitResult")] * 50)

    with pytest.raises(OperationFailure):
        q14._commit(sesion)
    assert sesion.intentos == q14.REINTENTOS


# --- Integración con q15 y la transacción: ver tests/integracion/test_q14_integracion.py ---
