"""
Carga inicial de datos.

Uso:  python -m farmared.carga

Lee los CSV de data/originales (los de la cátedra) y data/adicionales (los
nuestros), convierte los tipos y carga:

  - MongoDB: clientes, sucursales, farmaceuticos, proveedores, productos,
    recetas y ventas (con el detalle embebido en "items").
  - Redis: stock por lote (ver cargar_stock_redis).

Antes de cargar borra lo que había, así que se puede correr varias veces.
"""
import csv
from collections import defaultdict
from pathlib import Path

from farmared import fechas
from farmared.db import get_db, get_redis

DIR_DATA = Path(__file__).resolve().parent.parent / "data"
CARPETAS = ["originales", "adicionales"]

ARCHIVOS = ["clientes", "sucursales", "farmaceuticos", "proveedores", "productos",
            "stock_lotes", "recetas", "ventas", "detalle_ventas"]

CAMPOS_INT = {"precio_unit", "unidades", "dispensas_autorizadas", "dispensas_realizadas",
              "total", "cantidad"}
CAMPOS_FECHA = {"vencimiento", "fecha_emision", "proxima_dispensa", "fecha"}

# columna que es el id de cada archivo (pasa a ser el _id en Mongo)
ID = {
    "clientes": "id_cliente",
    "sucursales": "id_sucursal",
    "farmaceuticos": "id_farmaceutico",
    "proveedores": "id_proveedor",
    "productos": "id_producto",
    "stock_lotes": "id_lote",
    "recetas": "id_receta",
    "ventas": "id_venta",
    "detalle_ventas": "id_detalle",
}


def convertir(campo, valor):
    valor = valor.strip()
    if valor == "":
        return None
    if valor in ("True", "False"):
        return valor == "True"
    if campo in CAMPOS_INT:
        return int(valor)
    if campo in CAMPOS_FECHA:
        return fechas.parsear(valor)
    return valor


def leer_csv(nombre):
    filas = []
    for carpeta in CARPETAS:
        ruta = DIR_DATA / carpeta / f"{nombre}.csv"
        if not ruta.exists():
            continue
        with open(ruta, encoding="utf-8", newline="") as f:
            for fila in csv.DictReader(f):
                filas.append({k: convertir(k, v) for k, v in fila.items()})
    return filas


def a_documento(fila, campo_id):
    doc = dict(fila)
    doc["_id"] = doc.pop(campo_id)
    return doc


def cargar_mongo(db, datos):
    for nombre in ["clientes", "sucursales", "farmaceuticos", "proveedores", "productos", "recetas"]:
        db.drop_collection(nombre)
        docs = [a_documento(f, ID[nombre]) for f in datos[nombre]]
        db[nombre].insert_many(docs)
        print(f"  mongo  {nombre:<15} {len(docs):>3} docs")

    # el detalle va embebido en la venta: siempre se lee junto con la cabecera
    # y nunca se consulta un ítem suelto
    items = defaultdict(list)
    for d in datos["detalle_ventas"]:
        items[d["id_venta"]].append({
            "id_detalle": d["id_detalle"],
            "id_producto": d["id_producto"],
            "cantidad": d["cantidad"],
            "precio_unit": d["precio_unit"],
        })
    ventas = []
    for v in datos["ventas"]:
        doc = a_documento(v, "id_venta")
        doc["items"] = items[doc["_id"]]
        ventas.append(doc)
    db.drop_collection("ventas")
    db.ventas.insert_many(ventas)
    print(f"  mongo  {'ventas':<15} {len(ventas):>3} docs ({len(datos['detalle_ventas'])} items embebidos)")


def borrar_claves(r, patron):
    for clave in r.scan_iter(patron, count=500):
        r.delete(clave)


def cargar_stock_redis(r, lotes):
    """
    Estructura del stock en Redis:

      lote:{id_lote}                      HASH  id_producto, id_sucursal, nro_lote, unidades, vencimiento
      stock:{id_sucursal}:{id_producto}   ZSET  miembro = id_lote, score = vencimiento (AAAAMMDD)
      lotes:unidades                      ZSET  miembro = id_lote, score = unidades

    El ZSET por sucursal+producto deja los lotes ordenados por vencimiento,
    que es justo el orden FEFO en el que hay que consumirlos. lotes:unidades
    sirve para buscar lotes con poco stock sin recorrer todo.
    """
    borrar_claves(r, "lote:*")
    borrar_claves(r, "stock:*")
    r.delete("lotes:unidades")

    pipe = r.pipeline(transaction=True)
    for l in lotes:
        pipe.hset(f"lote:{l['id_lote']}", mapping={
            "id_lote": l["id_lote"],
            "id_producto": l["id_producto"],
            "id_sucursal": l["id_sucursal"],
            "nro_lote": l["nro_lote"],
            "unidades": l["unidades"],
            "vencimiento": fechas.a_texto(l["vencimiento"]),
        })
        pipe.zadd(f"stock:{l['id_sucursal']}:{l['id_producto']}", {l["id_lote"]: fechas.a_score(l["vencimiento"])})
        pipe.zadd("lotes:unidades", {l["id_lote"]: l["unidades"]})
    pipe.execute()
    print(f"  redis  {'stock_lotes':<15} {len(lotes):>3} lotes")


def main():
    datos = {nombre: leer_csv(nombre) for nombre in ARCHIVOS}

    print("Cargando MongoDB...")
    cargar_mongo(get_db(), datos)

    print("Cargando Redis...")
    cargar_stock_redis(get_redis(), datos["stock_lotes"])

    print("Listo.")


if __name__ == "__main__":
    main()
