"""
Contrato de q13 contra Mongo real, con los validadores ($jsonSchema) y los
índices de esquema_mongo.py.

Cubre lo que la base en memoria no garantiza: que el documento del alta pase
el $jsonSchema, que el índice único de dni frene un duplicado aunque el
chequeo previo no lo haya visto (dos altas simultáneas) y que un choque de
_id se resuelva tomando el siguiente.
"""
from unittest.mock import patch

import pytest

from farmared.consultas import q13_abm_clientes as q13
from farmared.esquema_mongo import crear_colecciones

pytestmark = pytest.mark.integracion

ANA = {"nombre": "Ana", "apellido": "Suárez", "dni": "41234567",
       "obra_social": "OSDE", "nro_afiliado": "OS-412345"}


def cliente(id_cliente, dni):
    return {"_id": id_cliente, "nombre": "N", "apellido": "A", "dni": dni,
            "obra_social": "PAMI", "nro_afiliado": "PA-1", "activo": True}


@pytest.fixture
def db(mongo):
    crear_colecciones(mongo)
    with patch("farmared.consultas.q13_abm_clientes.get_db", return_value=mongo):
        yield mongo


def test_el_alta_pasa_el_json_schema_de_la_coleccion(db):
    resultado = q13.alta(dict(ANA, obra_social="Sin cobertura"))
    assert resultado["mensaje"] == "alta OK: C001"
    assert db.clientes.find_one({"_id": "C001"})["nro_afiliado"] is None


def test_si_el_chequeo_previo_no_ve_el_dni_lo_frena_el_indice_unico(db):
    # Arrange: simula otra alta con el mismo DNI que entró entre el chequeo y el insert
    db.clientes.insert_one(cliente("C001", "41234567"))

    # Act
    with patch.object(q13, "_dni_registrado", side_effect=[None, "C001"]):
        with pytest.raises(q13.ErrorValidacion, match=r"DNI ya registrado \(C001\)"):
            q13.alta(ANA)

    # Assert
    assert db.clientes.count_documents({}) == 1


def test_si_el_id_ya_lo_tomo_otra_alta_usa_el_siguiente(db):
    # Arrange: el id calculado (C001) lo ocupó otra alta concurrente
    db.clientes.insert_one(cliente("C001", "30000000"))

    # Act
    with patch.object(q13, "_siguiente_id", side_effect=["C001", "C002"]):
        resultado = q13.alta(ANA)

    # Assert
    assert resultado["mensaje"] == "alta OK: C002"
    assert db.clientes.find_one({"_id": "C002"})["dni"] == "41234567"
