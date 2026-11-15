"""CLI: errores de uso vs. errores dentro de una consulta."""
from unittest.mock import patch

import pytest

import main


def correr(*argv):
    with patch("sys.argv", ["main.py", *argv]):
        main.main()


def test_argumentos_de_mas_es_error_de_uso(capsys):
    with pytest.raises(SystemExit):
        correr("q03", "C001", "sobra")
    assert "cantidad de argumentos incorrecta" in capsys.readouterr().out


def test_un_typeerror_de_adentro_de_la_consulta_no_se_disfraza_de_error_de_uso():
    def consulta_con_bug():
        return None + 1

    with patch.dict(main.CONSULTAS, {"qxx": (consulta_con_bug, "")}):
        with pytest.raises(TypeError):
            correr("qxx")


def test_texto_donde_va_un_numero(capsys):
    def consulta(dias=60):
        return int(dias)

    with patch.dict(main.CONSULTAS, {"qxx": (consulta, "")}):
        with pytest.raises(SystemExit):
            correr("qxx", "abc")
    assert "se esperaba un número" in capsys.readouterr().out
