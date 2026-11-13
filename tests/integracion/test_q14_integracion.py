"""
q14 de punta a punta: transacción real de Mongo + descuento real en Redis.

Necesita un Mongo con **replica set** (las transacciones no existen en un
standalone) y un Redis. El Codespace los trae (MONGO_URI / REDIS_HOST); si no
hay, o el Mongo no es replica set, los tests se saltean.

Usa la base `farmared_test_q14` de Mongo (con los validadores reales de
esquema_mongo) y la base 15 de Redis; ninguna toca los datos cargados.
Vencimientos relativos a hoy.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
import redis
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from farmared import config, fechas
from farmared.consultas import q14_registrar_venta as q14
from farmared.consultas import q15_descontar_stock as q15
from farmared.consultas.q14_registrar_venta import VentaRechazada
from farmared.esquema_mongo import crear_colecciones

NOMBRE_DB = "farmared_test_q14"


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
def client():
    cliente = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=1500)
    try:
        if "setName" not in cliente.admin.command("hello"):
            pytest.skip("El Mongo no es un replica set: no hay transacciones")
    except PyMongoError:
        pytest.skip("No hay Mongo disponible")
    yield cliente
    cliente.drop_database(NOMBRE_DB)
    cliente.close()


def fecha(dias):
    return fechas.hoy() + timedelta(days=dias)


@pytest.fixture
def entorno(client, r):
    """Datos mínimos (válidos para los validadores reales) y stock de P1 en S001."""
    client.drop_database(NOMBRE_DB)
    db = client[NOMBRE_DB]
    crear_colecciones(db)
    db.clientes.insert_one({"_id": "C1", "nombre": "Ana", "apellido": "Paz", "dni": "30111222",
                            "obra_social": "OSDE", "nro_afiliado": "X1", "activo": True})
    db.sucursales.insert_one({"_id": "S001", "nombre": "Farmacia Uno", "tipo": "Farmacia", "activo": True})
    db.farmaceuticos.insert_one({"_id": "F1", "nombre": "Leo", "apellido": "Gil", "matricula": "MN-1",
                                 "cargo": "Farmacéutico", "id_sucursal": "S001", "activo": True})
    db.proveedores.insert_one({"_id": "PRV1", "razon_social": "Lab", "cuit": "30-1-1", "tipo": "Laboratorio",
                               "activo": True})
    db.productos.insert_many([
        {"_id": "P1", "nombre": "Libre", "condicion_venta": "Venta libre", "precio_unit": 100,
         "id_proveedor": "PRV1", "activo": True},
        {"_id": "P2", "nombre": "Con receta", "condicion_venta": "Bajo receta", "precio_unit": 500,
         "id_proveedor": "PRV1", "activo": True},
    ])
    db.recetas.insert_many([
        {"_id": "R-simple", "id_cliente": "C1", "fecha_emision": fecha(-3), "tipo": "Simple",
         "dispensas_autorizadas": 1, "dispensas_realizadas": 0, "proxima_dispensa": None, "estado": "Vigente"},
        {"_id": "R-prol", "id_cliente": "C1", "fecha_emision": fecha(-3), "tipo": "Tratamiento prolongado",
         "dispensas_autorizadas": 3, "dispensas_realizadas": 1, "proxima_dispensa": fecha(-1), "estado": "Vigente"},
    ])
    for id_lote, prod, unidades, dias in [("L-vencido", "P1", 25, -10), ("L-a", "P1", 8, 5), ("L-b", "P1", 90, 300),
                                          ("L-p2", "P2", 10, 100)]:
        r.hset(f"lote:{id_lote}", mapping={"unidades": unidades})
        r.zadd(f"stock:S001:{prod}", {id_lote: fechas.a_score(fecha(dias))})
        r.zadd("lotes:unidades", {id_lote: unidades})
    with patch.object(q14, "get_db", return_value=db), patch.object(q14, "get_mongo_client", return_value=client), \
            patch.object(q15, "get_db", return_value=db), patch.object(q15, "get_redis", return_value=r):
        yield db, r


def pedido(cantidad=1, producto="P1", **extra):
    return {"id_cliente": "C1", "id_farmaceutico": "F1", "medio_pago": "Efectivo",
            "items": [{"id_producto": producto, "cantidad": cantidad}], **extra}


def lotes(r):
    return {i: (int(r.hget(f"lote:{i}", "unidades")), int(r.zscore("lotes:unidades", i)))
            for i in ("L-vencido", "L-a", "L-b", "L-p2")}


def foto(db):
    """Todo el estado de Mongo que q14 podría modificar."""
    return {"ventas": list(db.ventas.find()), "recetas": list(db.recetas.find())}


# --- Camino feliz --------------------------------------------------------------------

def test_venta_libre_inserta_la_venta_y_descuenta_fefo_saltando_vencidos(entorno):
    db, r = entorno

    registrada = q14.ejecutar(pedido(cantidad=10))

    guardada = db.ventas.find_one({"_id": registrada["_id"]})
    assert guardada["total"] == 1000
    assert guardada["estado"] == "Completada"
    assert guardada["tipo"] == "Venta libre"
    assert guardada["stock_descontado"] is True
    assert lotes(r) == {"L-vencido": (25, 25), "L-a": (0, 0), "L-b": (88, 88), "L-p2": (10, 10)}


def test_venta_con_receta_simple_completa_la_receta(entorno):
    db, r = entorno

    q14.ejecutar(pedido(producto="P2", id_receta="R-simple"))

    receta = db.recetas.find_one({"_id": "R-simple"})
    assert receta["estado"] == "Completada"
    assert receta["dispensas_realizadas"] == 1
    assert receta["proxima_dispensa"] is None
    assert lotes(r)["L-p2"] == (9, 9)


def test_tratamiento_prolongado_con_dispensas_restantes_sigue_vigente_con_proxima_a_30_dias(entorno):
    db, r = entorno

    q14.ejecutar(pedido(producto="P2", id_receta="R-prol"))

    receta = db.recetas.find_one({"_id": "R-prol"})
    assert receta["estado"] == "Vigente"
    assert receta["dispensas_realizadas"] == 2
    assert receta["proxima_dispensa"] == fecha(30)


def test_dos_ventas_seguidas_tienen_ids_distintos(entorno):
    db, r = entorno

    a = q14.ejecutar(pedido())
    b = q14.ejecutar(pedido())

    assert a["_id"] != b["_id"]
    assert db.ventas.count_documents({}) == 2


# --- Rechazos: no queda nada escrito, ni en Mongo ni en Redis -------------------------

def test_sin_stock_no_queda_venta_ni_receta_modificada_ni_redis_tocado(entorno):
    db, r = entorno
    antes_mongo, antes_redis = foto(db), lotes(r)

    with pytest.raises(VentaRechazada, match="Stock insuficiente"):
        q14.ejecutar(pedido(cantidad=999))  # vigentes: 98

    assert foto(db) == antes_mongo
    assert lotes(r) == antes_redis


def test_sin_stock_con_receta_la_receta_vuelve_atras(entorno):
    """La receta se actualiza ANTES de descontar el stock; al fallar q15 la
    transacción tiene que deshacer ese update."""
    db, r = entorno
    antes_mongo = foto(db)
    r.hset("lote:L-p2", "unidades", 0)
    r.zadd("lotes:unidades", {"L-p2": 0})

    with pytest.raises(VentaRechazada):
        q14.ejecutar(pedido(producto="P2", id_receta="R-simple"))

    assert foto(db) == antes_mongo
    assert db.recetas.find_one({"_id": "R-simple"})["estado"] == "Vigente"


def test_una_validacion_que_falla_no_escribe_nada(entorno):
    db, r = entorno
    antes_mongo, antes_redis = foto(db), lotes(r)

    with pytest.raises(VentaRechazada, match="cliente"):
        q14.ejecutar({**pedido(), "id_cliente": "C-no-existe"})

    assert foto(db) == antes_mongo
    assert lotes(r) == antes_redis


def test_error_inesperado_en_q15_aborta_la_transaccion(entorno):
    db, r = entorno
    antes_mongo, antes_redis = foto(db), lotes(r)

    with patch.object(q15, "descontar_lotes", side_effect=RuntimeError("se cayó Redis")):
        with pytest.raises(RuntimeError):
            q14.ejecutar(pedido(producto="P2", id_receta="R-simple"))

    assert foto(db) == antes_mongo
    assert lotes(r) == antes_redis


def test_receta_consumida_por_otra_venta_entre_validar_y_escribir_se_rechaza(entorno):
    """Carrera: la receta pasa la validación pero otra venta la completa antes
    de la transacción. El filtro del update lo detecta y no se escribe nada."""
    db, r = entorno
    validar_original = q14._validar

    def validar_y_que_otro_consuma_la_receta(datos):
        contexto = validar_original(datos)
        db.recetas.update_one({"_id": "R-simple"}, {"$set": {"estado": "Completada", "dispensas_realizadas": 1}})
        return contexto

    with patch.object(q14, "_validar", validar_y_que_otro_consuma_la_receta):
        with pytest.raises(VentaRechazada, match="cambió"):
            q14.ejecutar(pedido(producto="P2", id_receta="R-simple"))

    assert db.ventas.count_documents({}) == 0
    assert lotes(r)["L-p2"] == (10, 10)
