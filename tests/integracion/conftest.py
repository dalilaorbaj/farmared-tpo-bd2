"""Mongo real para q03 y q05.

Usa, en este orden, el Mongo que ya esté disponible:

1. MONGO_URI, si está definida (en el Codespace apunta al mongo del compose).
2. El mongod de localhost:27017.
3. Uno levantado para la corrida: el binario mongod, o un contenedor mongo:7.

La base es siempre farmared_test. Se borra al final de cada test. Si el
servidor lo arrancó esta corrida, también se apaga al terminar.
"""
import os
import shutil
import socket
import subprocess
import tempfile
import time

import pytest
from pymongo import MongoClient
from pymongo.errors import PyMongoError

NOMBRE = "farmared_test"
_LOCAL = "mongodb://127.0.0.1:27017/?directConnection=true"


def _abrir(uri):
    cliente = MongoClient(uri, serverSelectionTimeoutMS=1500)
    try:
        cliente.admin.command("ping")
    except PyMongoError:
        cliente.close()
        return None
    return cliente


def _esperar(uri, segundos):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        cliente = _abrir(uri)
        if cliente is not None:
            return cliente
        time.sleep(0.3)
    return None


def _puerto_libre():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _levantar_mongod():
    binario = shutil.which("mongod")
    if binario is None:
        return None
    puerto = _puerto_libre()
    carpeta = tempfile.mkdtemp(prefix="farmared-mongo-")
    proceso = subprocess.Popen(
        [binario, "--port", str(puerto), "--dbpath", carpeta, "--bind_ip", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    uri = f"mongodb://127.0.0.1:{puerto}/?directConnection=true"
    cliente = _esperar(uri, segundos=20)
    if cliente is None or proceso.poll() is not None:
        _cerrar_proceso(proceso)
        shutil.rmtree(carpeta, ignore_errors=True)
        if cliente is not None:
            cliente.close()
        return None

    def parar():
        _cerrar_proceso(proceso)
        shutil.rmtree(carpeta, ignore_errors=True)

    return cliente, parar


def _levantar_docker():
    if shutil.which("docker") is None:
        return None
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        return None
    puerto = _puerto_libre()
    nombre = "farmared-test-mongo"
    subprocess.run(["docker", "rm", "-f", nombre], capture_output=True)
    creado = subprocess.run(
        ["docker", "run", "-d", "--name", nombre, "-p", f"{puerto}:27017", "mongo:7.0"],
        capture_output=True,
    )
    if creado.returncode != 0:
        return None
    cliente = _esperar(f"mongodb://127.0.0.1:{puerto}/?directConnection=true", segundos=40)

    def parar():
        subprocess.run(["docker", "rm", "-f", nombre], capture_output=True)

    if cliente is None:
        parar()
        return None
    return cliente, parar


def _cerrar_proceso(proceso):
    if proceso.poll() is not None:
        return
    proceso.terminate()
    try:
        proceso.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proceso.kill()
        proceso.wait(timeout=5)


def _conseguir():
    candidatos = []
    if os.environ.get("MONGO_URI"):
        candidatos.append(os.environ["MONGO_URI"])
    candidatos.append(_LOCAL)
    for uri in candidatos:
        cliente = _abrir(uri)
        if cliente is not None:
            return cliente, cliente.close
    for levantar in (_levantar_mongod, _levantar_docker):
        arranque = levantar()
        if arranque is None:
            continue
        cliente, parar = arranque

        def limpiar(cliente=cliente, parar=parar):
            cliente.close()
            parar()

        return cliente, limpiar
    return None


@pytest.fixture(scope="session")
def _mongo_de_testing():
    conseguido = _conseguir()
    if conseguido is None:
        pytest.skip("No había un Mongo y no se pudo levantar uno para los tests")
    cliente, limpiar = conseguido
    yield cliente
    limpiar()


@pytest.fixture
def mongo(_mongo_de_testing):
    _mongo_de_testing.drop_database(NOMBRE)
    yield _mongo_de_testing[NOMBRE]
    _mongo_de_testing.drop_database(NOMBRE)
