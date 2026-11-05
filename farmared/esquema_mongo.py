"""
Definición de las colecciones de Mongo: validadores ($jsonSchema) e índices.

Mongo no tiene FKs, así que la integridad referencial se valida en la
aplicación (en la carga y en los servicios de escritura). Lo que sí podemos
pedirle a Mongo es que valide tipos/valores permitidos y unicidad.
"""
from pymongo import ASCENDING, DESCENDING

STR = {"bsonType": "string"}
STR_NULL = {"bsonType": ["string", "null"]}
BOOL = {"bsonType": "bool"}
INT = {"bsonType": ["int", "long"], "minimum": 0}
FECHA = {"bsonType": "date"}
FECHA_NULL = {"bsonType": ["date", "null"]}

OBRAS_SOCIALES = ["OSDE", "Swiss Medical", "PAMI", "IOMA", "Galeno", "Sin cobertura"]


def _schema(requeridos, propiedades):
    return {"$jsonSchema": {"bsonType": "object", "required": requeridos, "properties": propiedades}}


VALIDADORES = {
    "clientes": _schema(
        ["_id", "nombre", "apellido", "dni", "obra_social", "activo"],
        {
            "nombre": STR, "apellido": STR,
            "dni": {"bsonType": "string", "pattern": "^[0-9]{7,8}$"},
            "email": STR_NULL, "telefono": STR_NULL,
            "ciudad": STR_NULL, "provincia": STR_NULL,
            "obra_social": {"enum": OBRAS_SOCIALES},
            "nro_afiliado": STR_NULL,
            "activo": BOOL,
        },
    ),
    "sucursales": _schema(
        ["_id", "nombre", "tipo", "activo"],
        {"nombre": STR, "tipo": {"enum": ["Farmacia", "Droguería"]}, "activo": BOOL},
    ),
    "farmaceuticos": _schema(
        ["_id", "nombre", "apellido", "matricula", "cargo", "id_sucursal", "activo"],
        {
            "matricula": STR,
            "cargo": {"enum": ["Director Técnico", "Farmacéutico"]},
            "id_sucursal": STR,
            "activo": BOOL,
        },
    ),
    "proveedores": _schema(
        ["_id", "razon_social", "cuit", "tipo", "activo"],
        {"cuit": STR, "tipo": {"enum": ["Laboratorio", "Droguería"]}, "activo": BOOL},
    ),
    "productos": _schema(
        ["_id", "nombre", "condicion_venta", "precio_unit", "id_proveedor", "activo"],
        {
            "condicion_venta": {"enum": ["Venta libre", "Bajo receta", "Bajo receta archivada"]},
            "precio_unit": INT,
            "id_proveedor": STR,
            "activo": BOOL,
        },
    ),
    "recetas": _schema(
        ["_id", "id_cliente", "fecha_emision", "tipo", "dispensas_autorizadas",
         "dispensas_realizadas", "estado"],
        {
            "id_cliente": STR,
            "fecha_emision": FECHA,
            "tipo": {"enum": ["Simple", "Archivada", "Tratamiento prolongado"]},
            "dispensas_autorizadas": INT,
            "dispensas_realizadas": INT,
            "proxima_dispensa": FECHA_NULL,
            "estado": {"enum": ["Vigente", "Completada", "Vencida"]},
        },
    ),
    "ventas": _schema(
        ["_id", "id_cliente", "id_farmaceutico", "fecha", "tipo", "medio_pago", "total",
         "estado", "items"],
        {
            "id_cliente": STR,
            "id_farmaceutico": STR,
            "id_receta": STR_NULL,
            "fecha": FECHA,
            "tipo": {"enum": ["Venta libre", "Con receta"]},
            "medio_pago": {"enum": ["Efectivo", "Débito", "Crédito", "Transferencia", "Obra social"]},
            "total": INT,
            "estado": {"enum": ["Completada", "Pendiente", "Anulada"]},
            "items": {
                "bsonType": "array",
                "minItems": 1,
                "items": {
                    "bsonType": "object",
                    "required": ["id_producto", "cantidad", "precio_unit"],
                    "properties": {
                        "id_producto": STR,
                        "cantidad": {"bsonType": ["int", "long"], "minimum": 1},
                        "precio_unit": INT,
                    },
                },
            },
        },
    ),
}

INDICES = {
    "clientes": [([("dni", ASCENDING)], {"unique": True})],
    "farmaceuticos": [
        ([("matricula", ASCENDING)], {"unique": True}),
        ([("id_sucursal", ASCENDING)], {}),
    ],
    "proveedores": [([("cuit", ASCENDING)], {"unique": True})],
    "productos": [([("id_proveedor", ASCENDING)], {}), ([("activo", ASCENDING)], {})],
    "recetas": [
        ([("id_cliente", ASCENDING), ("fecha_emision", ASCENDING)], {}),
        ([("tipo", ASCENDING), ("estado", ASCENDING), ("proxima_dispensa", ASCENDING)], {}),
    ],
    # las ventas se consultan por cliente, por farmacéutico y por rango de fechas
    "ventas": [
        ([("id_cliente", ASCENDING), ("fecha", DESCENDING)], {}),
        ([("id_farmaceutico", ASCENDING), ("fecha", DESCENDING)], {}),
        ([("fecha", DESCENDING)], {}),
        ([("estado", ASCENDING)], {}),
    ],
}


def crear_colecciones(db):
    """Borra y vuelve a crear las colecciones con sus validadores e índices."""
    for nombre, validador in VALIDADORES.items():
        db.drop_collection(nombre)
        db.create_collection(nombre, validator=validador, validationAction="error")
        for campos, opciones in INDICES.get(nombre, []):
            db[nombre].create_index(campos, **opciones)
