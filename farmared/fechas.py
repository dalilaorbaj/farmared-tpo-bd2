"""
Helpers de fechas.

Todas las consultas que dependen de "hoy" tienen que usar hoy() y no una fecha
fija. En Mongo las fechas se guardan como Date (datetime sin hora) y en Redis
el vencimiento de los lotes se usa como score con formato AAAAMMDD.
"""
from datetime import date, datetime


def hoy():
    """Fecha de hoy a las 00:00 (datetime, para comparar contra Mongo)."""
    d = date.today()
    return datetime(d.year, d.month, d.day)


def parsear(texto):
    """'2026-10-13' -> datetime. Vacío -> None."""
    if not texto:
        return None
    return datetime.strptime(texto, "%Y-%m-%d")


def a_score(fecha):
    """datetime/date -> int AAAAMMDD (score de los ZSET de stock en Redis)."""
    return fecha.year * 10000 + fecha.month * 100 + fecha.day


def a_texto(fecha):
    if fecha is None:
        return None
    return fecha.strftime("%Y-%m-%d")
