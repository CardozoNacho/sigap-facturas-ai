"""Lectura y agrupación básica de facturas escaneadas desde PDF."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from pdf2image import convert_from_path, pdfinfo_from_path


@dataclass(frozen=True)
class PaginasFactura:
    """Páginas consecutivas que forman una factura (frente y dorso)."""

    numero: int
    pagina_frente: int
    pagina_dorso: int


def contar_paginas(pdf: Path) -> int:
    """Devuelve el total de páginas de un PDF."""
    info = pdfinfo_from_path(str(pdf))
    return int(info["Pages"])


def agrupar_paginas(cantidad: int) -> tuple[list[PaginasFactura], int | None]:
    """Agrupa desde la página 1 en pares; devuelve también una página sobrante."""
    facturas = [
        PaginasFactura(numero=i // 2 + 1, pagina_frente=i + 1, pagina_dorso=i + 2)
        for i in range(0, cantidad - 1, 2)
    ]
    sobrante = cantidad if cantidad % 2 else None
    return facturas, sobrante


def convertir_factura(pdf: Path, factura: PaginasFactura, destino: Path, dpi: int = 150, incluir_dorso: bool = True) -> tuple[Path, Path | None]:
    """Convierte el par o solo el frente; el par original conserva su numeración.

    Para tarifa 1, incluir_dorso=False evita renderizar su dorso. La siguiente
    factura sigue comenzando dos páginas después: no se reagrupa el PDF.
    """
    destino.mkdir(parents=True, exist_ok=True)
    paginas = convert_from_path(
        str(pdf),
        dpi=dpi,
        first_page=factura.pagina_frente,
        last_page=factura.pagina_dorso if incluir_dorso else factura.pagina_frente,
        fmt="png",
    )
    prefijo = f"factura_{factura.numero:03d}"
    frente = destino / f"{prefijo}_frente.png"
    dorso = destino / f"{prefijo}_dorso.png" if incluir_dorso else None
    paginas[0].save(frente)
    if dorso is not None:
        paginas[1].save(dorso)
    return frente, dorso


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspecciona o convierte páginas de un PDF en pares frente/dorso.")
    parser.add_argument("pdf", type=Path, help="PDF de entrada")
    parser.add_argument("--salida", type=Path, help="Carpeta para guardar las imágenes")
    parser.add_argument("--factura", type=int, help="Número de factura (empezando en 1) para convertir")
    parser.add_argument("--dpi", type=int, default=150, help="Resolución de conversión (predeterminado: 150)")
    parser.add_argument("--solo-frente", action="store_true", help="No convierte el dorso; conserva el agrupamiento por pares")
    args = parser.parse_args()

    if not args.pdf.is_file():
        parser.error(f"No existe el PDF: {args.pdf}")

    total = contar_paginas(args.pdf)
    facturas, sobrante = agrupar_paginas(total)
    print(f"PDF: {args.pdf}")
    print(f"Páginas: {total}; pares frente/dorso: {len(facturas)}")
    if sobrante is not None:
        print(f"Página sin pareja: {sobrante}")
    if args.factura is not None:
        if args.salida is None:
            parser.error("--salida es obligatorio al usar --factura")
        if not 1 <= args.factura <= len(facturas):
            parser.error(f"--factura debe estar entre 1 y {len(facturas)}")
        frente, dorso = convertir_factura(args.pdf, facturas[args.factura - 1], args.salida, args.dpi, incluir_dorso=not args.solo_frente)
        print(f"Frente: {frente}")
        print(f"Dorso:  {dorso if dorso is not None else 'omitido'}")


if __name__ == "__main__":
    main()
