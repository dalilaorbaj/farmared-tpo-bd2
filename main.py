"""
Punto de entrada para correr las consultas desde la terminal.

    python main.py                 -> lista las consultas disponibles
    python main.py cargar          -> (re)carga los datos
    python main.py q01             -> corre la consulta 1
    python main.py q08 30          -> los argumentos extra se pasan a la función

Para agregar una consulta: crear el módulo en farmared/consultas y sumarlo
al diccionario CONSULTAS.
"""
import json
import sys
from datetime import datetime

from farmared import carga
from farmared.consultas import (
    q01_productos_activos,
    q02_ventas_pendientes,
    q04_clientes_varias_recetas,
    q06_tratamientos_atrasados,
    q08_lotes_stock_bajo,
    q09_ventas_libres_menores,
)

CONSULTAS = {
    "q01": (q01_productos_activos.ejecutar, "Productos activos con datos del proveedor"),
    "q02": (q02_ventas_pendientes.ejecutar, "Ventas pendientes con farmacéutico y total"),
    "q04": (q04_clientes_varias_recetas.ejecutar, "Clientes con más de una receta"),
    "q06": (q06_tratamientos_atrasados.ejecutar, "Tratamientos prolongados vigentes con dispensa atrasada"),
    "q08": (q08_lotes_stock_bajo.ejecutar, "Lotes con menos de 50 unidades  [limite]"),
    "q09": (q09_ventas_libres_menores.ejecutar, "Ventas libres con total < $5000  [monto_max]"),
}


def a_json(obj):
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d")
    return str(obj)


def mostrar(resultado):
    print(json.dumps(resultado, indent=2, ensure_ascii=False, default=a_json))
    if isinstance(resultado, list):
        print(f"\n({len(resultado)} resultados)")


def uso():
    print("Uso: python main.py <consulta> [argumentos]\n")
    print("  cargar   Carga/recarga los datos en Mongo y Redis")
    for nombre, (_, desc) in CONSULTAS.items():
        print(f"  {nombre}      {desc}")


def main():
    if len(sys.argv) < 2:
        uso()
        return

    nombre, args = sys.argv[1].lower(), sys.argv[2:]
    if nombre == "cargar":
        carga.main()
        return
    if nombre not in CONSULTAS:
        print(f"No existe la consulta '{nombre}'\n")
        uso()
        sys.exit(1)

    funcion, _ = CONSULTAS[nombre]
    mostrar(funcion(*args))


if __name__ == "__main__":
    main()
