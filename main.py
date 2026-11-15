"""
Punto de entrada para correr las consultas desde la terminal.

    python main.py                 -> lista las consultas disponibles
    python main.py cargar          -> (re)carga los datos
    python main.py q01             -> corre la consulta 1
    python main.py q08 30          -> los argumentos extra se pasan a la función

Para agregar una consulta: crear el módulo en farmared/consultas y sumarlo
al diccionario CONSULTAS.
"""
import inspect
import json
import sys
from datetime import datetime

from farmared import carga
from farmared.consultas import (
    q01_productos_activos,
    q02_ventas_pendientes,
    q03_historial_cliente,
    q04_clientes_varias_recetas,
    q05_ventas_por_farmaceutico,
    q06_tratamientos_atrasados,
    q07_productos_mas_vendidos,
    q08_lotes_stock_bajo,
    q09_ventas_libres_menores,
    q10_clientes_por_sucursal,
    q11_ingresos_por_farmaceutico,
    q12_clientes_sin_ventas,
    q13_abm_clientes,
    q14_registrar_venta,
    q15_descontar_stock,
)

CONSULTAS = {
    "q01": (q01_productos_activos.ejecutar, "Productos activos con datos del proveedor  [usar_cache]"),
    "q02": (q02_ventas_pendientes.ejecutar, "Ventas pendientes con farmacéutico y total"),
    "q03": (q03_historial_cliente.ejecutar, "Historial completo de un cliente  <id_cliente>"),
    "q04": (q04_clientes_varias_recetas.ejecutar, "Clientes con más de una receta"),
    "q05": (q05_ventas_por_farmaceutico.ejecutar, "Farmacéuticos activos y sus ventas en los últimos 60 días  [dias]"),
    "q06": (q06_tratamientos_atrasados.ejecutar, "Tratamientos prolongados vigentes con dispensa atrasada"),
    "q07": (q07_productos_mas_vendidos.ejecutar, "Top 5 productos más vendidos por unidades  [solo_activos]"),
    "q08": (q08_lotes_stock_bajo.ejecutar, "Lotes con menos de 50 unidades  [limite]"),
    "q09": (q09_ventas_libres_menores.ejecutar, "Ventas libres con total < $5000  [monto_max]"),
    "q10": (q10_clientes_por_sucursal.ejecutar, "Clientes atendidos en una sucursal  <id_sucursal> [contar_repetidos]"),
    "q11": (q11_ingresos_por_farmaceutico.ejecutar, "Ingresos por farmacéutico en el mes actual"),
    "q12": (q12_clientes_sin_ventas.ejecutar, "Clientes sin ventas en el último año  [considerar_anuladas]"),
    "q13": (q13_abm_clientes.ejecutar, "ABM de clientes  alta <json> | modificar <id_cliente> <json> | baja <id_cliente>"),
    "q14": (q14_registrar_venta.ejecutar, "Registrar una venta Completada (valida, actualiza la receta y descuenta stock)  <json>"),
    "q15": (q15_descontar_stock.ejecutar, "Descontar stock FEFO de una venta  <id_venta>"),
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


def error_de_uso(nombre, motivo):
    print(f"Argumentos inválidos para {nombre}: {motivo}\n")
    uso()
    sys.exit(1)


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
    # la cantidad de argumentos se valida contra la firma antes de llamar: así
    # un TypeError que salga de adentro de la consulta (un bug) no se confunde
    # con un error de uso
    try:
        inspect.signature(funcion).bind(*args)
    except TypeError:
        error_de_uso(nombre, "cantidad de argumentos incorrecta")
    try:
        resultado = funcion(*args)
    except ValueError as e:
        # int("abc") tira un mensaje en inglés; los nuestros ya vienen en castellano
        error_de_uso(nombre, "se esperaba un número" if "invalid literal" in str(e) else str(e))
    mostrar(resultado)


if __name__ == "__main__":
    main()
