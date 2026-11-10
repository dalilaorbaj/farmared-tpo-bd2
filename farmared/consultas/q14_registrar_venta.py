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


class VentaRechazada(Exception):
    """Motivo de rechazo por validación o por falta de stock."""


def _validar(datos):
    """Fase 1: SOLO lecturas. Si algo falla -> raise VentaRechazada(motivo).
    Si todo pasa devuelve lo que se necesita después (receta, productos...)."""
    db = get_db()
    # TODO [JUE 12 · validaciones] 1: validar la estructura de la entrada (items no vacíos, cantidad > 0,
    #         medio_pago permitido; ver enums en farmared/esquema_mongo.py).
    # TODO [JUE 12 · validaciones] 2: cliente existe y activo.
    # TODO [JUE 12 · validaciones] 3: farmacéutico existe y activo; su sucursal existe, activa y tipo 'Farmacia'.
    # TODO [JUE 12 · validaciones] 4: productos existen y activos (¿y si un producto está repetido?).
    # TODO [JUE 12 · validaciones] 5: si algún producto es 'Bajo receta' / 'Bajo receta archivada':
    #         receta existente, estado 'Vigente' y del mismo cliente.
    #         ¿Y si mandan receta pero ningún producto la necesita?
    raise NotImplementedError


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
