"""
Q14 - Registro de una nueva venta 'Completada' (cabecera e ítems), validando:
cliente existente y activo; farmacéutico existente, activo y de una sucursal
tipo 'Farmacia'; productos existentes y activos; y, para productos bajo receta,
receta existente, vigente y del mismo cliente. El total se calcula a partir de
los ítems y se actualiza la receta según las reglas de negocio. Integrado con
q15: si el descuento de stock falla, no queda venta ni receta modificadas.

Motores: MongoDB (venta + receta, en una transacción) + Redis (stock, vía q15).

Parámetros:
    datos (dict | str JSON):
        id_cliente, id_farmaceutico, medio_pago,
        items: [{"id_producto": ..., "cantidad": ...}, ...],
        id_receta (opcional)
    Ejemplo CLI:
        python main.py q14 '{"id_cliente": "C009", "id_farmaceutico": "F019",
          "medio_pago": "Efectivo", "id_receta": "RC015",
          "items": [{"id_producto": "PRD003", "cantidad": 1}]}'
Retorna: el documento de la venta registrada (con id_venta en "_id").
Errores: VentaRechazada con el motivo (validación, receta cambiada o stock
         insuficiente). En ese caso no queda nada escrito en Mongo ni en Redis.
"""
import json
from datetime import timedelta

from farmared import fechas
from farmared.consultas import q15_descontar_stock
from farmared.consultas.q15_descontar_stock import StockInsuficiente
from farmared.db import get_db, get_mongo_client, get_redis  # noqa: F401 (get_redis: compensación del sábado)
from farmared.esquema_mongo import VALIDADORES


class VentaRechazada(Exception):
    """Motivo de rechazo por validación o por falta de stock."""


MEDIOS_PAGO = VALIDADORES["ventas"]["$jsonSchema"]["properties"]["medio_pago"]["enum"]
BAJO_RECETA = ("Bajo receta", "Bajo receta archivada")


def _validar_estructura(datos):
    """Chequea la forma de la entrada (sin consultar la base)."""
    if not isinstance(datos, dict):
        raise VentaRechazada("Los datos de la venta tienen que ser un objeto JSON")
    for campo in ("id_cliente", "id_farmaceutico", "medio_pago", "items"):
        if not datos.get(campo):
            raise VentaRechazada(f"Falta el campo obligatorio '{campo}'")
    if datos["medio_pago"] not in MEDIOS_PAGO:
        raise VentaRechazada(f"Medio de pago inválido: {datos['medio_pago']} (válidos: {', '.join(MEDIOS_PAGO)})")
    if not isinstance(datos["items"], list):
        raise VentaRechazada("'items' tiene que ser una lista")
    for it in datos["items"]:
        if not isinstance(it, dict) or not it.get("id_producto"):
            raise VentaRechazada("Cada ítem necesita 'id_producto'")
        cant = it.get("cantidad")
        if isinstance(cant, bool) or not isinstance(cant, int) or cant <= 0:
            raise VentaRechazada(f"Cantidad inválida para {it['id_producto']}: tiene que ser un entero mayor a 0")


def _validar(datos):
    """Fase 1: SOLO lecturas. Si algo falla -> raise VentaRechazada(motivo).
    Si todo pasa devuelve lo que se necesita después:
    {"cliente", "farmaceutico", "sucursal", "productos": {id: doc}, "receta": doc | None}"""
    db = get_db()
    _validar_estructura(datos)

    cliente = db.clientes.find_one({"_id": datos["id_cliente"]})
    if cliente is None:
        raise VentaRechazada(f"El cliente {datos['id_cliente']} no existe")
    if not cliente["activo"]:
        raise VentaRechazada(f"El cliente {datos['id_cliente']} está dado de baja")

    farmaceutico = db.farmaceuticos.find_one({"_id": datos["id_farmaceutico"]})
    if farmaceutico is None:
        raise VentaRechazada(f"El farmacéutico {datos['id_farmaceutico']} no existe")
    if not farmaceutico["activo"]:
        raise VentaRechazada(f"El farmacéutico {datos['id_farmaceutico']} no está activo")
    sucursal = db.sucursales.find_one({"_id": farmaceutico["id_sucursal"]})
    if sucursal is None:
        raise VentaRechazada(f"La sucursal {farmaceutico['id_sucursal']} del farmacéutico no existe")
    if sucursal["tipo"] != "Farmacia":
        raise VentaRechazada(f"La sucursal {sucursal['_id']} es una {sucursal['tipo']}: no registra ventas minoristas")
    if not sucursal["activo"]:
        raise VentaRechazada(f"La sucursal {sucursal['_id']} está dada de baja")

    # un producto repetido en dos ítems es válido (q15 suma las cantidades)
    ids = {it["id_producto"] for it in datos["items"]}
    productos = {p["_id"]: p for p in db.productos.find({"_id": {"$in": list(ids)}})}
    for id_producto in sorted(ids):
        if id_producto not in productos:
            raise VentaRechazada(f"El producto {id_producto} no existe")
        if not productos[id_producto]["activo"]:
            raise VentaRechazada(f"El producto {id_producto} está discontinuado")

    necesita_receta = any(p["condicion_venta"] in BAJO_RECETA for p in productos.values())
    id_receta = datos.get("id_receta")
    receta = None
    if necesita_receta:
        if not id_receta:
            raise VentaRechazada("Hay productos bajo receta: hace falta 'id_receta'")
        receta = db.recetas.find_one({"_id": id_receta})
        if receta is None:
            raise VentaRechazada(f"La receta {id_receta} no existe")
        if receta["estado"] != "Vigente":
            raise VentaRechazada(f"La receta {id_receta} está {receta['estado']}: tiene que estar Vigente")
        if receta["id_cliente"] != datos["id_cliente"]:
            raise VentaRechazada(f"La receta {id_receta} no es del cliente {datos['id_cliente']}")
    elif id_receta:
        # decisión: no se ignora en silencio una receta que no se va a usar
        raise VentaRechazada(f"Se informó la receta {id_receta} pero ningún producto la requiere")

    return {"cliente": cliente, "farmaceutico": farmaceutico, "sucursal": sucursal,
            "productos": productos, "receta": receta}


def _proximo_id_venta(db):
    """V035 -> V036. Toma el mayor número existente (no el último por orden de
    texto, que fallaría al pasar de V999 a V1000)."""
    numeros = [int(i[1:]) for i in db.ventas.distinct("_id") if i[1:].isdigit()]
    return f"V{max(numeros, default=0) + 1:03d}"


def _armar_venta(datos, productos, db):
    """Arma el documento de la venta (todavía sin insertar).
    Los precios salen del catálogo (no de lo que mande el cliente) y el total es
    la suma de cantidad * precio de los ítems."""
    items = [{
        "id_producto": it["id_producto"],
        "cantidad": it["cantidad"],
        "precio_unit": productos[it["id_producto"]]["precio_unit"],
    } for it in datos["items"]]
    id_receta = datos.get("id_receta")
    return {
        "_id": _proximo_id_venta(db),
        "id_cliente": datos["id_cliente"],
        "id_farmaceutico": datos["id_farmaceutico"],
        "id_receta": id_receta,
        "fecha": fechas.hoy(),
        "tipo": "Con receta" if id_receta else "Venta libre",
        "medio_pago": datos["medio_pago"],
        "total": sum(it["cantidad"] * it["precio_unit"] for it in items),
        "estado": "Completada",
        "stock_descontado": False,  # lo marca q15 dentro de la transacción
        "items": items,
    }


def _cambios_receta(receta):
    """Devuelve el $set para la receta tras la dispensa (reglas 2.11)."""
    realizadas = receta["dispensas_realizadas"] + 1
    quedan = receta["tipo"] == "Tratamiento prolongado" and realizadas < receta["dispensas_autorizadas"]
    if quedan:
        # sigue Vigente; la próxima dispensa es a los 30 días
        return {"dispensas_realizadas": realizadas, "proxima_dispensa": fechas.hoy() + timedelta(days=30)}
    # Simple / Archivada (única dispensa) o última dispensa de un prolongado
    return {"dispensas_realizadas": realizadas, "estado": "Completada", "proxima_dispensa": None}


def ejecutar(datos):
    if isinstance(datos, str):
        datos = json.loads(datos)

    # Fase 1: validar. Solo lecturas: si algo falla no se escribió nada.
    contexto = _validar(datos)
    receta = contexto["receta"]

    client = get_mongo_client()
    db = get_db()
    venta = _armar_venta(datos, contexto["productos"], db)

    # Fase 2: transacción de Mongo (venta + receta) con el descuento de Redis adentro.
    # Se maneja a mano (start/commit/abort) y NO con with_transaction: éste
    # reejecuta el callback ante errores transitorios y repetiría el descuento
    # en Redis, que no participa de la transacción.
    #
    # Orden: lo que Mongo puede deshacer va primero y lo de Redis al final, justo
    # antes del commit. Si algo falla antes de q15, Redis ni se tocó; si falta
    # stock, el Lua no escribió nada.
    with client.start_session() as session:
        session.start_transaction()
        try:
            db.ventas.insert_one(venta, session=session)

            if receta is not None:
                # el filtro asegura que la receta siga igual que cuando se validó
                # (otra venta podría haberla usado en el medio)
                resultado = db.recetas.update_one(
                    {"_id": receta["_id"], "estado": "Vigente",
                     "dispensas_realizadas": receta["dispensas_realizadas"]},
                    {"$set": _cambios_receta(receta)},
                    session=session,
                )
                if resultado.matched_count == 0:
                    raise VentaRechazada(f"La receta {receta['_id']} cambió mientras se registraba la venta")

            q15_descontar_stock.ejecutar(venta["_id"], session=session)
            venta["stock_descontado"] = True  # q15 la marcó dentro de la transacción
        except StockInsuficiente as e:
            session.abort_transaction()
            raise VentaRechazada(str(e)) from e
        except BaseException:
            session.abort_transaction()
            raise

        # TODO [SÁB 14 · compensación] 10: si el commit falla acá, Redis ya descontó:
        #          compensar con q15_descontar_stock.devolver_lotes(r, descontado)
        #          (q15.ejecutar devuelve "descontado"; ahora no se está guardando).
        #          ¿Qué pasa si la compensación también falla? (va al informe)
        session.commit_transaction()

    # TODO [SÁB 14 · compensación] 11: revisar qué se devuelve (hoy: la venta registrada).
    return venta
