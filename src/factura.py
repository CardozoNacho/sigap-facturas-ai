"""Modelo de los campos de factura que SIGAP necesita cargar."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import IntEnum


class Tarifa(IntEnum):
    UNO = 1
    DOS = 2
    TRES = 3
    CUATRO = 4


@dataclass
class FacturaExtraida:
    """Campos extraíbles de una factura; los campos de tarifa son opcionales."""

    fecha: date | None = None
    nfact: str | None = None
    folio: str | None = None
    tarifa: Tarifa | None = None
    importepvenc: Decimal | None = None
    nisnu: str | None = None
    consactual: Decimal | None = None

    # Campos específicos de tarifa 1 y 2.
    factpot: Decimal | None = None
    recfactpot: Decimal | None = None
    ptapotconv: Decimal | None = None
    ptapotreg: Decimal | None = None

    # Campos específicos de tarifa 3.
    fptapotconv: Decimal | None = None
    fptapotreg: Decimal | None = None
    fptapotconve: Decimal | None = None
    fptapotregi: Decimal | None = None

    # Campo específico de tarifa 4.
    t4potconv: Decimal | None = None
