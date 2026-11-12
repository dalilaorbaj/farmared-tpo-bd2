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
Retorna: TODO definir (ej. la venta insertada + estado final de la receta).
Errores: TODO definir (una excepción propia con el motivo de rechazo).
"""
import json

from farmared import fechas
from farmared.consultas import q15_descontar_stock
from farmared.db import get_db, get_mongo_client, get_redis
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


def _armar_venta(datos, productos):
    """Arma el documento de la venta (todavía sin insertar)."""
    # TODO [VIE 13 · venta y receta] 6: id_venta nuevo (¿cómo evitás choques entre ventas simultáneas?),
    #         precio_unit del catálogo en cada ítem, total = suma(cantidad*precio),
    #         fecha = fechas.hoy(), tipo ('Venta libre' / 'Con receta'),
    #         estado 'Completada', stock_descontado False (lo marca q15/q14).
    raise NotImplementedError


def _cambios_receta(receta):
    """Devuelve el $set para la receta tras la dispensa (según reglas 2.11)."""
    # TODO [VIE 13 · venta y receta] 7: Simple/Archivada -> Completada y proxima_dispensa None.
    #         Tratamiento prolongado: dispensas_realizadas + 1; si quedan
    #         dispensas -> proxima_dispensa = hoy + 30 días (timedelta);
    #         si llegó a las autorizadas -> Completada y proxima_dispensa None.
    raise NotImplementedError


def ejecutar(datos):
    if isinstance(datos, str):
        datos = json.loads(datos)

    # Fase 1: validar (no se escribió nada todavía)
    # TODO [VIE 13 · integración] 8: llamar a _validar.

    # Fase 2: transacción de Mongo + descuento en Redis
    client = get_mongo_client()
    db = get_db()
    r = get_redis()  # noqa: F841 (para compensar)

    # TODO [VIE 13 · integración] 9: abrir sesión y transacción (client.start_session(),
    #         start_transaction). Decidir: manual vs with_transaction
    #         (ojo: with_transaction reejecuta el callback -> ¿y Redis?).
    #   a) insertar la venta (session=...)
    #   b) actualizar la receta si corresponde (session=...)
    #   c) llamar a q15_descontar_stock.ejecutar(id_venta, session=...)
    #      -> si no hay stock: abort_transaction y re-lanzar como VentaRechazada.
    #   d) commit_transaction().

    # TODO [SÁB 14 · compensación] 10: si el commit falla DESPUÉS de que q15 descontó -> compensar en
    #          Redis (volver a sumar lo que q15 informó, HASH y lotes:unidades).
    #          ¿Qué pasa si la compensación también falla? (va al informe)

    # TODO [SÁB 14 · compensación] 11: devolver la venta registrada.
    raise NotImplementedError("q14 sin implementar")
