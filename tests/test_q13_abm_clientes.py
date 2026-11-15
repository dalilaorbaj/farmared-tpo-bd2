"""
Contrato de q13: alta, modificación y baja de clientes.

Mongo está reemplazado por una base en memoria con el mismo índice único
sobre dni que crea esquema_mongo.py. Cada test arma los clientes, llama al
servicio y verifica qué quedó escrito, o que no se escribió nada si la
validación falla.
"""
from contextlib import contextmanager
from unittest.mock import patch

import mongomock
import pytest

from farmared.consultas import q13_abm_clientes as q13


@contextmanager
def mongo_en_memoria(*clientes):
    db = mongomock.MongoClient()["farmared"]
    db.clientes.create_index("dni", unique=True)
    if clientes:
        db.clientes.insert_many(list(clientes))
    with patch("farmared.consultas.q13_abm_clientes.get_db", return_value=db):
        yield db


def cliente(id_cliente, dni, obra_social="OSDE", nro_afiliado="OS-1", activo=True, **extra):
    return {
        "_id": id_cliente, "nombre": "Nombre", "apellido": "Apellido", "dni": dni,
        "email": None, "telefono": None, "ciudad": None, "provincia": None,
        "obra_social": obra_social, "nro_afiliado": nro_afiliado, "activo": activo, **extra,
    }


ANA = {"nombre": "Ana", "apellido": "Suárez", "dni": "41234567",
       "obra_social": "OSDE", "nro_afiliado": "OS-412345"}


# ---------- alta ----------

def test_alta_genera_el_siguiente_id_y_queda_activo():
    # Arrange
    with mongo_en_memoria(cliente("C001", "31245678"), cliente("C020", "16443209")) as db:
        # Act
        resultado = q13.alta(dict(ANA, email="ana@mail.com"))
        guardado = db.clientes.find_one({"_id": "C021"})

    # Assert
    assert resultado["ok"] and resultado["mensaje"] == "alta OK: C021"
    assert guardado["dni"] == "41234567"
    assert guardado["activo"] is True
    assert guardado["email"] == "ana@mail.com"
    assert guardado["telefono"] is None


def test_alta_con_dni_repetido_se_rechaza_aunque_el_cliente_este_de_baja():
    # Arrange
    with mongo_en_memoria(cliente("C008", "41234567", activo=False)) as db:
        # Act
        with pytest.raises(q13.ErrorValidacion, match=r"DNI ya registrado \(C008\)"):
            q13.alta(ANA)

        # Assert
        assert db.clientes.count_documents({}) == 1


def test_alta_con_obra_social_fuera_de_la_lista_se_rechaza():
    with mongo_en_memoria() as db:
        with pytest.raises(q13.ErrorValidacion, match="obra social inválida: Medicus"):
            q13.alta(dict(ANA, obra_social="Medicus"))
        assert db.clientes.count_documents({}) == 0


def test_alta_con_cobertura_y_sin_nro_afiliado_se_rechaza():
    with mongo_en_memoria() as db:
        with pytest.raises(q13.ErrorValidacion, match="falta nro_afiliado"):
            q13.alta(dict(ANA, nro_afiliado="  "))
        assert db.clientes.count_documents({}) == 0


def test_alta_sin_cobertura_deja_nro_afiliado_en_null():
    with mongo_en_memoria() as db:
        q13.alta(dict(ANA, obra_social="Sin cobertura", nro_afiliado="X-1"))
        assert db.clientes.find_one({"_id": "C001"})["nro_afiliado"] is None


@pytest.mark.parametrize("datos, motivo", [
    ({"nombre": "Ana", "dni": "41234567", "obra_social": "OSDE"}, "faltan campos obligatorios: apellido"),
    (dict(ANA, dni="4123"), "DNI inválido"),
    (dict(ANA, activo=False), "campos no permitidos: activo"),
    (dict(ANA, _id="C999"), "campos no permitidos: _id"),
])
def test_alta_con_datos_invalidos_no_escribe(datos, motivo):
    with mongo_en_memoria() as db:
        with pytest.raises(q13.ErrorValidacion, match=motivo):
            q13.alta(datos)
        assert db.clientes.count_documents({}) == 0


def test_alta_acepta_dni_numerico_y_lo_guarda_como_texto():
    with mongo_en_memoria() as db:
        q13.alta(dict(ANA, dni=41234567))
        assert db.clientes.find_one({"_id": "C001"})["dni"] == "41234567"


# ---------- modificación ----------

def test_modificar_cambia_solo_los_campos_pedidos_y_devuelve_antes_y_despues():
    # Arrange
    with mongo_en_memoria(cliente("C010", "35667210", telefono="2215124455", ciudad="La Plata")) as db:
        # Act
        resultado = q13.modificar("C010", {"telefono": "2215550000"})
        guardado = db.clientes.find_one({"_id": "C010"})

    # Assert
    assert resultado["antes"]["telefono"] == "2215124455"
    assert resultado["cliente"]["telefono"] == "2215550000"
    assert guardado["telefono"] == "2215550000"
    assert guardado["ciudad"] == "La Plata"


def test_modificar_un_campo_no_permitido_se_rechaza():
    with mongo_en_memoria(cliente("C010", "35667210")) as db:
        with pytest.raises(q13.ErrorValidacion, match="no se puede modificar: dni"):
            q13.modificar("C010", {"dni": "11111111", "telefono": "1"})
        assert db.clientes.find_one({"_id": "C010"})["dni"] == "35667210"


def test_pasar_a_sin_cobertura_limpia_el_nro_afiliado():
    with mongo_en_memoria(cliente("C010", "35667210", "IOMA", "IO-503318")) as db:
        q13.modificar("C010", {"obra_social": "Sin cobertura"})
        guardado = db.clientes.find_one({"_id": "C010"})
    assert guardado["obra_social"] == "Sin cobertura"
    assert guardado["nro_afiliado"] is None


def test_pasar_a_una_cobertura_sin_nro_afiliado_se_rechaza():
    with mongo_en_memoria(cliente("C013", "43890112", "Sin cobertura", None)) as db:
        with pytest.raises(q13.ErrorValidacion, match="nro_afiliado"):
            q13.modificar("C013", {"obra_social": "PAMI"})
        assert db.clientes.find_one({"_id": "C013"})["obra_social"] == "Sin cobertura"


def test_cambiar_de_obra_social_sin_afiliado_nuevo_no_hereda_el_de_la_anterior():
    with mongo_en_memoria(cliente("C009", "42118733", "OSDE", "OS-411872")) as db:
        with pytest.raises(q13.ErrorValidacion, match="nro_afiliado nuevo"):
            q13.modificar("C009", {"obra_social": "PAMI"})
        guardado = db.clientes.find_one({"_id": "C009"})
    assert (guardado["obra_social"], guardado["nro_afiliado"]) == ("OSDE", "OS-411872")


def test_cambiar_de_obra_social_con_afiliado_nuevo():
    with mongo_en_memoria(cliente("C009", "42118733", "OSDE", "OS-411872")) as db:
        q13.modificar("C009", {"obra_social": "PAMI", "nro_afiliado": "PA-700100"})
        guardado = db.clientes.find_one({"_id": "C009"})
    assert (guardado["obra_social"], guardado["nro_afiliado"]) == ("PAMI", "PA-700100")


def test_mandar_la_misma_obra_social_no_obliga_a_repetir_el_afiliado():
    with mongo_en_memoria(cliente("C009", "42118733", "OSDE", "OS-411872")) as db:
        q13.modificar("C009", {"obra_social": "OSDE", "telefono": "1150000000"})
        guardado = db.clientes.find_one({"_id": "C009"})
    assert guardado["nro_afiliado"] == "OS-411872"


def test_no_se_modifica_un_cliente_dado_de_baja():
    with mongo_en_memoria(cliente("C008", "25678901", activo=False)):
        with pytest.raises(q13.ErrorValidacion, match="dado de baja"):
            q13.modificar("C008", {"telefono": "1"})


def test_modificar_un_cliente_inexistente_se_rechaza():
    with mongo_en_memoria():
        with pytest.raises(q13.ErrorValidacion, match="no existe el cliente C099"):
            q13.modificar("C099", {"telefono": "1"})


# ---------- baja ----------

def test_baja_es_logica_y_el_documento_sigue_existiendo():
    # Arrange
    with mongo_en_memoria(cliente("C010", "35667210")) as db:
        # Act
        resultado = q13.baja("C010")
        guardado = db.clientes.find_one({"_id": "C010"})

    # Assert
    assert resultado["mensaje"] == "C010 activo: false"
    assert resultado["antes"]["activo"] is True
    assert guardado is not None and guardado["activo"] is False


def test_baja_de_un_cliente_ya_dado_de_baja_se_rechaza():
    with mongo_en_memoria(cliente("C016", "22345098", activo=False)):
        with pytest.raises(q13.ErrorValidacion, match="ya estaba dado de baja"):
            q13.baja("C016")


# ---------- CLI ----------

def test_ejecutar_parsea_el_json_y_devuelve_el_error_sin_excepcion():
    with mongo_en_memoria(cliente("C001", "31245678")):
        ok = q13.ejecutar("alta", '{"nombre": "Ana", "apellido": "Suárez", "dni": "41234567", '
                                  '"obra_social": "OSDE", "nro_afiliado": "OS-1"}')
        repetido = q13.ejecutar("alta", '{"nombre": "X", "apellido": "Y", "dni": "31245678", '
                                        '"obra_social": "PAMI", "nro_afiliado": "PA-1"}')
        roto = q13.ejecutar("alta", "{no es json")
        sin_args = q13.ejecutar("baja")

    assert ok["mensaje"] == "alta OK: C002"
    assert repetido == {"ok": False, "error": "DNI ya registrado (C001)"}
    assert roto["ok"] is False and "JSON inválido" in roto["error"]
    assert sin_args["ok"] is False and sin_args["error"].startswith("uso:")
