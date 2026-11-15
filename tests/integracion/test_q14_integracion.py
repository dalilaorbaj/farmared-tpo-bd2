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
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
import redis
from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError

from farmared import config, fechas
from farmared.consultas import q14_registrar_venta as q14
from farmared.consultas import q15_descontar_stock as q15
from farmared.consultas.q14_registrar_venta import CompensacionFallida, VentaRechazada
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
            patch.object(q14, "get_redis", return_value=r), \
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

    resultado = q14.registrar(pedido(cantidad=10))

    assert resultado["ok"] is True
    assert resultado["receta"] is None
    assert resultado["lotes_descontados"] == [{"lote": "L-a", "unidades": 8}, {"lote": "L-b", "unidades": 2}]
    guardada = db.ventas.find_one({"_id": resultado["venta"]["_id"]})
    assert guardada == resultado["venta"]
    assert guardada["total"] == 1000
    assert guardada["estado"] == "Completada"
    assert guardada["tipo"] == "Venta libre"
    assert guardada["stock_descontado"] is True
    assert lotes(r) == {"L-vencido": (25, 25), "L-a": (0, 0), "L-b": (88, 88), "L-p2": (10, 10)}


def test_venta_con_receta_simple_completa_la_receta(entorno):
    db, r = entorno

    resultado = q14.registrar(pedido(producto="P2", id_receta="R-simple"))

    receta = db.recetas.find_one({"_id": "R-simple"})
    assert resultado["receta"] == receta
    assert resultado["venta"]["tipo"] == "Con receta"
    assert receta["estado"] == "Completada"
    assert receta["dispensas_realizadas"] == 1
    assert receta["proxima_dispensa"] is None
    assert lotes(r)["L-p2"] == (9, 9)


def test_tratamiento_prolongado_con_dispensas_restantes_sigue_vigente_con_proxima_a_30_dias(entorno):
    db, r = entorno

    q14.registrar(pedido(producto="P2", id_receta="R-prol"))

    receta = db.recetas.find_one({"_id": "R-prol"})
    assert receta["estado"] == "Vigente"
    assert receta["dispensas_realizadas"] == 2
    assert receta["proxima_dispensa"] == fecha(30)


def test_dos_ventas_seguidas_tienen_ids_distintos(entorno):
    db, r = entorno

    a = q14.registrar(pedido())
    b = q14.registrar(pedido())

    assert a["venta"]["_id"] != b["venta"]["_id"]
    assert db.ventas.count_documents({}) == 2


# --- Rechazos: no queda nada escrito, ni en Mongo ni en Redis -------------------------

def test_sin_stock_no_queda_venta_ni_receta_modificada_ni_redis_tocado(entorno):
    db, r = entorno
    antes_mongo, antes_redis = foto(db), lotes(r)

    with pytest.raises(VentaRechazada, match="Stock insuficiente"):
        q14.registrar(pedido(cantidad=999))  # vigentes: 98

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
        q14.registrar(pedido(producto="P2", id_receta="R-simple"))

    assert foto(db) == antes_mongo
    assert db.recetas.find_one({"_id": "R-simple"})["estado"] == "Vigente"


def test_una_validacion_que_falla_no_escribe_nada(entorno):
    db, r = entorno
    antes_mongo, antes_redis = foto(db), lotes(r)

    with pytest.raises(VentaRechazada, match="cliente"):
        q14.registrar({**pedido(), "id_cliente": "C-no-existe"})

    assert foto(db) == antes_mongo
    assert lotes(r) == antes_redis


def test_error_inesperado_en_q15_aborta_la_transaccion(entorno):
    db, r = entorno
    antes_mongo, antes_redis = foto(db), lotes(r)

    with patch.object(q15, "descontar_lotes", side_effect=RuntimeError("se cayó Redis")):
        with pytest.raises(RuntimeError):
            q14.registrar(pedido(producto="P2", id_receta="R-simple"))

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
            q14.registrar(pedido(producto="P2", id_receta="R-simple"))

    assert db.ventas.count_documents({}) == 0
    assert lotes(r)["L-p2"] == (10, 10)


def test_la_ultima_dispensa_de_un_tratamiento_prolongado_completa_la_receta(entorno):
    db, r = entorno
    db.recetas.update_one({"_id": "R-prol"}, {"$set": {"dispensas_realizadas": 2}})

    q14.registrar(pedido(producto="P2", id_receta="R-prol"))

    receta = db.recetas.find_one({"_id": "R-prol"})
    assert (receta["estado"], receta["dispensas_realizadas"], receta["proxima_dispensa"]) == ("Completada", 3, None)
    with pytest.raises(VentaRechazada, match="Completada"):
        q14.registrar(pedido(producto="P2", id_receta="R-prol"))


def test_una_receta_simple_no_se_puede_usar_dos_veces(entorno):
    db, r = entorno
    q14.registrar(pedido(producto="P2", id_receta="R-simple"))

    with pytest.raises(VentaRechazada, match="Completada"):
        q14.registrar(pedido(producto="P2", id_receta="R-simple"))

    assert db.ventas.count_documents({}) == 1
    assert lotes(r)["L-p2"] == (9, 9)


def test_el_precio_guardado_es_el_del_catalogo_al_momento_de_la_venta(entorno):
    db, r = entorno
    q14.registrar(pedido(cantidad=2))
    db.productos.update_one({"_id": "P1"}, {"$set": {"precio_unit": 150}})

    segunda = q14.registrar(pedido(cantidad=2))["venta"]

    primera = db.ventas.find_one({"_id": {"$ne": segunda["_id"]}})
    assert (primera["items"][0]["precio_unit"], primera["total"]) == (100, 200)
    assert (segunda["items"][0]["precio_unit"], segunda["total"]) == (150, 300)


def test_la_venta_registrada_no_se_puede_volver_a_descontar_con_q15(entorno):
    db, r = entorno
    id_venta = q14.registrar(pedido(cantidad=3))["venta"]["_id"]
    antes = lotes(r)

    assert q15.ejecutar(id_venta)["ok"] is False
    assert lotes(r) == antes


# --- Commit: compensación y resultado incierto ------------------------------------------

def test_si_falla_el_commit_se_devuelve_el_stock_y_no_queda_venta_ni_receta(entorno):
    db, r = entorno
    antes_mongo, antes_redis = foto(db), lotes(r)

    with patch.object(q14, "_commit", side_effect=OperationFailure("se cayó el commit")):
        with pytest.raises(OperationFailure):
            q14.registrar(pedido(producto="P2", id_receta="R-simple"))

    assert foto(db) == antes_mongo
    assert lotes(r) == antes_redis


def test_si_el_commit_da_error_pero_la_venta_quedo_guardada_no_se_devuelve_el_stock(entorno):
    """Resultado incierto: el servidor commiteó pero el driver recibió un error.
    Devolver el stock dejaría una venta sin descontar."""
    db, r = entorno

    def commitea_y_despues_falla(session):
        session.commit_transaction()
        raise OperationFailure("se cortó la conexión después del commit")

    with patch.object(q14, "_commit", commitea_y_despues_falla):
        resultado = q14.registrar(pedido(cantidad=10))

    assert resultado["ok"] is True
    assert db.ventas.find_one({"_id": resultado["venta"]["_id"]})["stock_descontado"] is True
    assert lotes(r)["L-a"] == (0, 0)
    assert lotes(r)["L-b"] == (88, 88)


def test_si_falla_el_commit_y_tambien_la_compensacion_se_avisa_que_hay_que_reponer_a_mano(entorno):
    db, r = entorno

    with patch.object(q14, "_commit", side_effect=OperationFailure("commit")), \
            patch.object(q15, "devolver_lotes", side_effect=redis.ConnectionError("redis caído")):
        with pytest.raises(CompensacionFallida, match="L-a"):
            q14.registrar(pedido(cantidad=10))

    assert db.ventas.count_documents({}) == 0


# --- Concurrencia ------------------------------------------------------------------------

def test_si_otra_venta_tomo_el_mismo_id_se_reintenta_con_el_siguiente(entorno):
    db, r = entorno
    primera = q14.registrar(pedido())["venta"]["_id"]
    proximo_real = q14._proximo_id_venta
    devueltos = []

    def proximo_que_la_primera_vez_repite(db):
        devueltos.append(primera if not devueltos else proximo_real(db))
        return devueltos[-1]

    with patch.object(q14, "_proximo_id_venta", proximo_que_la_primera_vez_repite):
        segunda = q14.registrar(pedido())["venta"]["_id"]

    assert segunda != primera
    assert db.ventas.count_documents({}) == 2
    assert lotes(r)["L-a"] == (6, 6)  # se descontó una vez por venta, no por intento


def test_ventas_simultaneas_no_dejan_stock_negativo_ni_venden_de_mas(entorno):
    """20 ventas de 10 unidades a la vez con 98 vigentes: entran 9 y sobran 8."""
    db, r = entorno

    def vender(_):
        try:
            return q14.registrar(pedido(cantidad=10))["venta"]["_id"]
        except VentaRechazada as e:
            return e

    with ThreadPoolExecutor(max_workers=10) as hilos:
        resultados = list(hilos.map(vender, range(20)))

    registradas = [x for x in resultados if isinstance(x, str)]
    rechazadas = [x for x in resultados if isinstance(x, VentaRechazada)]
    assert len(registradas) == len(set(registradas))  # ids únicos
    assert db.ventas.count_documents({}) == len(registradas)
    estado = lotes(r)
    assert all(en_hash >= 0 and en_hash == en_zset for en_hash, en_zset in estado.values())
    assert estado["L-vencido"] == (25, 25)
    # lo que salió de Redis es exactamente lo vendido (cada venta son 10 unidades)
    assert (8 + 90) - (estado["L-a"][0] + estado["L-b"][0]) == 10 * len(registradas)
    # las que no entraron fue por stock o por choque agotado, nunca a medias
    assert len(registradas) + len(rechazadas) == 20
    assert len(registradas) <= 9


def test_dos_ventas_simultaneas_con_la_misma_receta_solo_entra_una(entorno):
    db, r = entorno

    def vender(_):
        try:
            return q14.registrar(pedido(producto="P2", id_receta="R-simple"))["venta"]["_id"]
        except VentaRechazada as e:
            return e

    with ThreadPoolExecutor(max_workers=6) as hilos:
        resultados = list(hilos.map(vender, range(6)))

    assert len([x for x in resultados if isinstance(x, str)]) == 1
    assert db.ventas.count_documents({}) == 1
    assert db.recetas.find_one({"_id": "R-simple"})["dispensas_realizadas"] == 1
    assert lotes(r)["L-p2"] == (9, 9)
