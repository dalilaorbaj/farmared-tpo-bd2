"""Conversión de los argumentos que llegan como texto desde la terminal."""

VERDADEROS = {"true", "1", "si", "sí"}
FALSOS = {"false", "0", "no"}


def a_bool(valor, nombre):
    """True/False o los textos true, false, 1, 0, si y no."""
    if isinstance(valor, bool):
        return valor
    texto = str(valor).strip().lower()
    if texto in VERDADEROS:
        return True
    if texto in FALSOS:
        return False
    raise ValueError(f"{nombre} debe ser true o false")
