"""
Q13 - ABM de clientes: alta, modificación y baja lógica.

Motor: MongoDB (colección clientes).

Mongo no tiene claves foráneas ni checks entre campos, así que las reglas de
negocio se validan acá antes de escribir. El índice único sobre dni (ver
esquema_mongo.py) cubre el caso de dos altas con el mismo DNI al mismo
tiempo: la segunda falla con DuplicateKeyError aunque las dos hayan pasado
el chequeo previo. El $jsonSchema de la colección es la última barrera de
tipos y valores.

    alta(datos)
        datos: dict con nombre, apellido, dni, obra_social y, opcionales,
        email, telefono, ciudad, provincia y nro_afiliado.
        - el DNI no puede estar registrado (aunque el cliente esté dado de baja)
        - la obra social tiene que ser una de las permitidas
        - si tiene cobertura, nro_afiliado es obligatorio; si es
          "Sin cobertura", nro_afiliado queda en null
        - el id es el siguiente al mayor existente (C021, C022, ...)

    modificar(id_cliente, cambios)
        Solo email, telefono, ciudad, provincia, obra_social y nro_afiliado.
        El cliente tiene que existir y estar activo. Después del cambio la
        cobertura tiene que seguir siendo coherente (mismas reglas que el alta).

    baja(id_cliente)
        Baja lógica: activo = False. No se borra porque sus ventas y recetas
        lo siguen referenciando (y las consultas 3, 10 y 12 lo usan).

Desde la terminal:
    python main.py q13 alta '{"nombre": "Ana", "apellido": "Suárez", "dni": "41234567", "obra_social": "OSDE", "nro_afiliado": "OS-412345"}'
    python main.py q13 modificar C010 '{"telefono": "2215550000"}'
    python main.py q13 baja C010

Retorna: dict con ok=True, un mensaje y el cliente (en modificar y baja,
también el estado anterior). Si una validación falla no se escribe nada:
alta, modificar y baja lanzan ErrorValidacion, y ejecutar (la entrada de la
terminal) la convierte en {"ok": False, "error": motivo}.
"""
import json
import re

from pymongo.errors import DuplicateKeyError

from farmared.db import get_db
from farmared.esquema_mongo import OBRAS_SOCIALES

SIN_COBERTURA = "Sin cobertura"
OBLIGATORIOS = ["nombre", "apellido", "dni", "obra_social"]
OPCIONALES = ["email", "telefono", "ciudad", "provincia", "nro_afiliado"]
MODIFICABLES = ["email", "telefono", "ciudad", "provincia", "obra_social", "nro_afiliado"]
REINTENTOS_ID = 5


class ErrorValidacion(Exception):
    pass


def _texto(valor):
    """Normaliza un valor de entrada: strip y vacío -> None."""
    if valor is None:
        return None
    valor = str(valor).strip()
    return valor or None


def _validar_cobertura(doc):
    """obra_social válida y nro_afiliado coherente. Modifica doc en el lugar."""
    if doc.get("obra_social") not in OBRAS_SOCIALES:
        raise ErrorValidacion(
            f"obra social inválida: {doc.get('obra_social')} (permitidas: {', '.join(OBRAS_SOCIALES)})")
    if doc["obra_social"] == SIN_COBERTURA:
        doc["nro_afiliado"] = None
    elif not doc.get("nro_afiliado"):
        raise ErrorValidacion("falta nro_afiliado")


def _siguiente_id(db):
    ids = [d["_id"] for d in db.clientes.find({"_id": {"$regex": r"^C\d+$"}}, {"_id": 1})]
    mayor = max((int(i[1:]) for i in ids), default=0)
    return f"C{mayor + 1:03d}"


def _dni_registrado(db, dni):
    existente = db.clientes.find_one({"dni": dni}, {"_id": 1})
    return existente["_id"] if existente else None


def alta(datos):
    db = get_db()
    desconocidos = set(datos) - set(OBLIGATORIOS) - set(OPCIONALES)
    if desconocidos:
        raise ErrorValidacion(f"campos no permitidos: {', '.join(sorted(desconocidos))}")

    doc = {campo: _texto(datos.get(campo)) for campo in OBLIGATORIOS + OPCIONALES}
    faltan = [campo for campo in OBLIGATORIOS if not doc[campo]]
    if faltan:
        raise ErrorValidacion(f"faltan campos obligatorios: {', '.join(faltan)}")
    if not re.fullmatch(r"\d{7,8}", doc["dni"]):
        raise ErrorValidacion(f"DNI inválido: {doc['dni']} (7 u 8 dígitos)")
    _validar_cobertura(doc)

    id_existente = _dni_registrado(db, doc["dni"])
    if id_existente:
        raise ErrorValidacion(f"DNI ya registrado ({id_existente})")

    doc = {"_id": None, **doc, "activo": True}
    # Si otra alta toma el mismo id entre el cálculo y el insert, el _id
    # choca y se reintenta con el siguiente. Si lo que choca es el DNI, se
    # rechaza: el índice único es el que garantiza que no haya dos.
    for _ in range(REINTENTOS_ID):
        doc["_id"] = _siguiente_id(db)
        try:
            db.clientes.insert_one(doc)
            break
        except DuplicateKeyError as e:
            if "dni" in (e.details or {}).get("keyPattern", {}):
                raise ErrorValidacion(f"DNI ya registrado ({_dni_registrado(db, doc['dni'])})")
    else:
        raise ErrorValidacion("no se pudo generar un id libre, reintentar")

    return {"ok": True, "mensaje": f"alta OK: {doc['_id']}", "cliente": doc}


def modificar(id_cliente, cambios):
    db = get_db()
    if not cambios:
        raise ErrorValidacion("no hay cambios")
    no_permitidos = set(cambios) - set(MODIFICABLES)
    if no_permitidos:
        raise ErrorValidacion(f"no se puede modificar: {', '.join(sorted(no_permitidos))}")

    antes = db.clientes.find_one({"_id": id_cliente})
    if antes is None:
        raise ErrorValidacion(f"no existe el cliente {id_cliente}")
    if not antes["activo"]:
        raise ErrorValidacion(f"el cliente {id_cliente} está dado de baja")

    nuevos = {campo: _texto(valor) for campo, valor in cambios.items()}
    resultado = {**antes, **nuevos}
    _validar_cobertura(resultado)
    # _validar_cobertura puede haber limpiado nro_afiliado (pasó a Sin cobertura)
    nuevos["nro_afiliado"] = resultado["nro_afiliado"]

    # el filtro por activo evita modificar un cliente al que dieron de baja
    # entre la lectura y la escritura
    escrito = db.clientes.update_one({"_id": id_cliente, "activo": True}, {"$set": nuevos})
    if escrito.matched_count == 0:
        raise ErrorValidacion(f"el cliente {id_cliente} está dado de baja")
    despues = db.clientes.find_one({"_id": id_cliente})
    return {"ok": True, "mensaje": f"modificación OK: {id_cliente}", "antes": antes, "cliente": despues}


def baja(id_cliente):
    db = get_db()
    antes = db.clientes.find_one({"_id": id_cliente})
    if antes is None:
        raise ErrorValidacion(f"no existe el cliente {id_cliente}")
    if not antes["activo"]:
        raise ErrorValidacion(f"el cliente {id_cliente} ya estaba dado de baja")

    escrito = db.clientes.update_one({"_id": id_cliente, "activo": True}, {"$set": {"activo": False}})
    if escrito.matched_count == 0:
        raise ErrorValidacion(f"el cliente {id_cliente} ya estaba dado de baja")
    despues = db.clientes.find_one({"_id": id_cliente})
    return {"ok": True, "mensaje": f"{id_cliente} activo: false", "antes": antes, "cliente": despues}


def _leer_json(texto):
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as e:
        raise ErrorValidacion(f"JSON inválido: {e.msg}")
    if not isinstance(datos, dict):
        raise ErrorValidacion("se esperaba un objeto JSON")
    return datos


USO = "uso: q13 alta '<json>' | q13 modificar <id_cliente> '<json>' | q13 baja <id_cliente>"


def ejecutar(accion=None, *args):
    try:
        if accion == "alta" and len(args) == 1:
            return alta(_leer_json(args[0]))
        if accion == "modificar" and len(args) == 2:
            return modificar(args[0], _leer_json(args[1]))
        if accion == "baja" and len(args) == 1:
            return baja(args[0])
        raise ErrorValidacion(USO)
    except ErrorValidacion as e:
        return {"ok": False, "error": str(e)}
