"""Lectura del CSV histórico para comparar el prototipo durante el piloto."""

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from factura import FacturaExtraida, Tarifa


_TARIFAS = {
    "UNO": Tarifa.UNO,
    "DOS": Tarifa.DOS,
    "TRES": Tarifa.TRES,
    "CUATRO": Tarifa.CUATRO,
}

_COLUMNAS_DECIMALES = {
    "importepvenc": "importepvenc",
    "consactual": "consactual",
    # El CSV histórico usa "factorpot"; el campo de salida acordado es "factpot".
    "factpot": "factorpot",
    "recfactpot": "recfactpot",
    "ptapotconv": "ptapotconv",
    "ptapotreg": "ptapotreg",
    "fptapotconv": "fptapotconv",
    "fptapotreg": "fptapotreg",
    "fptapotconve": "fptapotconve",
    "fptapotregi": "fptapotregi",
    "t4potconv": "t4potconv",
}


def _decimal_opcional(valor: str | None) -> Decimal | None:
    if valor is None or valor.strip().upper() in {"", "NULL", "-"}:
        return None
    try:
        return Decimal(valor.strip())
    except InvalidOperation as error:
        raise ValueError(f"Valor numérico inválido en el CSV: {valor!r}") from error


def _fecha_opcional(valor: str | None) -> date | None:
    if valor is None or not valor.strip():
        return None
    texto = valor.strip()
    if len(texto) == 8 and texto.isdigit():
        return date(int(texto[:4]), int(texto[4:6]), int(texto[6:8]))
    return date.fromisoformat(texto)


def cargar_referencias_csv(ruta: Path) -> dict[str, FacturaExtraida]:
    """Carga filas históricas indexadas por folio usando solo campos extraíbles."""
    requeridos = {"fecha", "nfact", "folio", "tarifa", "nisnu", *_COLUMNAS_DECIMALES.values()}
    referencias: dict[str, FacturaExtraida] = {}

    with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        faltantes = requeridos - set(lector.fieldnames or ())
        if faltantes:
            raise ValueError(f"Faltan columnas en el CSV: {', '.join(sorted(faltantes))}")

        for fila in lector:
            folio = (fila.get("folio") or "").strip()
            if not folio:
                continue
            if folio in referencias:
                raise ValueError(f"Folio duplicado en el CSV: {folio}")

            etiqueta_tarifa = (fila.get("tarifa") or "").strip().upper()
            if etiqueta_tarifa not in _TARIFAS:
                raise ValueError(f"Tarifa desconocida para el folio {folio}: {etiqueta_tarifa!r}")

            valores = {
                nombre: _decimal_opcional(fila.get(columna_csv))
                for nombre, columna_csv in _COLUMNAS_DECIMALES.items()
            }
            referencias[folio] = FacturaExtraida(
                fecha=_fecha_opcional(fila.get("fecha")),
                nfact=(fila.get("nfact") or "").strip() or None,
                folio=folio,
                tarifa=_TARIFAS[etiqueta_tarifa],
                nisnu=(fila.get("nisnu") or "").strip() or None,
                **valores,
            )

    return referencias


def seleccionar_una_por_tarifa(
    referencias: dict[str, FacturaExtraida],
    folios_piloto: set[str],
) -> dict[Tarifa, FacturaExtraida]:
    """Devuelve la factura de menor folio disponible para cada tarifa del piloto."""
    muestras: dict[Tarifa, FacturaExtraida] = {}
    for folio in sorted(folios_piloto, key=int):
        factura = referencias.get(folio)
        if factura is not None and factura.tarifa is not None:
            muestras.setdefault(factura.tarifa, factura)
    return muestras
