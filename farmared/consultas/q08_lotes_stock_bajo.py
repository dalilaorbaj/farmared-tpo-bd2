"""
Q08 - Lotes con menos de 50 unidades, indicando producto, sucursal y proveedor.

Motores: Redis (stock) + MongoDB (catálogo y sucursales).

1. Redis: ZRANGEBYSCORE sobre lotes:unidades trae directamente los lotes con
   unidades < limite, y después HGETALL de cada lote (en un pipeline).
2. Mongo: se buscan los productos, proveedores y sucursales involucrados
   con un find por _id ($in) y se combinan en la aplicación.

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

    ids = r.zrangebyscore("lotes:unidades", "-inf", f"({limite}")
    if not ids:
        return []

    pipe = r.pipeline()
    for id_lote in ids:
        pipe.hgetall(f"lote:{id_lote}")
    lotes = pipe.execute()

    productos = {p["_id"]: p for p in db.productos.find(
        {"_id": {"$in": list({l["id_producto"] for l in lotes})}})}
    proveedores = {p["_id"]: p for p in db.proveedores.find(
        {"_id": {"$in": list({p["id_proveedor"] for p in productos.values()})}})}
    sucursales = {s["_id"]: s for s in db.sucursales.find(
        {"_id": {"$in": list({l["id_sucursal"] for l in lotes})}})}

    hoy = fechas.a_texto(fechas.hoy())
    resultado = []
    for l in lotes:
        prod = productos.get(l["id_producto"], {})
        prov = proveedores.get(prod.get("id_proveedor"), {})
        suc = sucursales.get(l["id_sucursal"], {})
        resultado.append({
            "id_lote": l["id_lote"],
            "nro_lote": l["nro_lote"],
            "unidades": int(l["unidades"]),
            "vencimiento": l["vencimiento"],
            "vencido": l["vencimiento"] < hoy,
            "producto": {"id": l["id_producto"], "nombre": prod.get("nombre")},
            "sucursal": {"id": l["id_sucursal"], "nombre": suc.get("nombre"), "tipo": suc.get("tipo")},
            "proveedor": {"id": prov.get("_id"), "razon_social": prov.get("razon_social"),
                          "telefono": prov.get("telefono")},
        })
    return resultado
