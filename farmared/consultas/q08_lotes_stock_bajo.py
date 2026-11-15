"""
Q08 - Lotes con menos de 50 unidades, indicando producto, sucursal y proveedor.

Motores: Redis (stock) + MongoDB (catálogo y sucursales).

1. Redis: ZRANGEBYSCORE sobre lotes:unidades trae directamente los lotes con
   unidades < limite, y después HGETALL de cada lote (en un pipeline).
2. Mongo: se buscan los productos, proveedores y sucursales involucrados
   con un find por _id ($in) y se combinan en la aplicación.

Si un lote figura en lotes:unidades pero le falta su HASH (o algún campo), se
informa igual con lo que se sabe (el id y las unidades del ZSET) y el resto
en null, en vez de cortar la consulta.

Parámetros:
    limite (int): umbral de unidades, por defecto 50 (estricto, < limite).
Retorna: lista de lotes ordenada por unidades ascendente.
"""
from farmared import fechas
from farmared.db import get_db, get_redis


def ejecutar(limite=50):
    limite = int(limite)
    r = get_redis()
    db = get_db()

    con_unidades = r.zrangebyscore("lotes:unidades", "-inf", f"({limite}", withscores=True)
    if not con_unidades:
        return []

    pipe = r.pipeline()
    for id_lote, _ in con_unidades:
        pipe.hgetall(f"lote:{id_lote}")
    lotes = []
    for (id_lote, unidades), datos in zip(con_unidades, pipe.execute()):
        # el ZSET manda en id y unidades; el HASH completa el resto si está
        lotes.append({"id_lote": id_lote, "unidades": int(unidades), "id_producto": None,
                      "id_sucursal": None, "nro_lote": None, "vencimiento": None,
                      **{k: v for k, v in datos.items() if k not in ("id_lote", "unidades")}})

    productos = {p["_id"]: p for p in db.productos.find(
        {"_id": {"$in": list({l["id_producto"] for l in lotes if l["id_producto"]})}})}
    proveedores = {p["_id"]: p for p in db.proveedores.find(
        {"_id": {"$in": list({p["id_proveedor"] for p in productos.values()})}})}
    sucursales = {s["_id"]: s for s in db.sucursales.find(
        {"_id": {"$in": list({l["id_sucursal"] for l in lotes if l["id_sucursal"]})}})}

    hoy = fechas.a_texto(fechas.hoy())
    resultado = []
    for l in lotes:
        prod = productos.get(l["id_producto"], {})
        prov = proveedores.get(prod.get("id_proveedor"), {})
        suc = sucursales.get(l["id_sucursal"], {})
        resultado.append({
            "id_lote": l["id_lote"],
            "nro_lote": l["nro_lote"],
            "unidades": l["unidades"],
            "vencimiento": l["vencimiento"],
            "vencido": l["vencimiento"] < hoy if l["vencimiento"] else None,
            "producto": {"id": l["id_producto"], "nombre": prod.get("nombre")},
            "sucursal": {"id": l["id_sucursal"], "nombre": suc.get("nombre"), "tipo": suc.get("tipo")},
            "proveedor": {"id": prov.get("_id"), "razon_social": prov.get("razon_social"),
                          "telefono": prov.get("telefono")},
        })
    return resultado
