"""Adaptador pequeño para ejecutar Tesseract sobre una imagen local."""

import argparse
import shutil
import subprocess
from pathlib import Path


def extraer_texto(imagen: Path, idioma: str = "spa", ejecutable: str | None = None) -> str:
    """Devuelve el texto OCR de una imagen usando Tesseract instalado localmente."""
    motor = ejecutable or shutil.which("tesseract")
    if not motor:
        raise FileNotFoundError(
            "No se encontró Tesseract. Instala el motor y los datos del idioma español (spa)."
        )
    if not imagen.is_file():
        raise FileNotFoundError(f"No existe la imagen: {imagen}")

    resultado = subprocess.run(
        [motor, str(imagen), "stdout", "-l", idioma, "--psm", "6"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if resultado.returncode:
        detalle = resultado.stderr.strip() or f"código {resultado.returncode}"
        raise RuntimeError(f"Tesseract no pudo procesar {imagen.name}: {detalle}")
    return resultado.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrae texto impreso de una imagen con Tesseract local.")
    parser.add_argument("imagen", type=Path, help="Imagen PNG/JPEG de una página")
    parser.add_argument("--idioma", default="spa", help="Idioma de Tesseract (predeterminado: spa)")
    parser.add_argument("--salida", type=Path, help="Archivo TXT de salida; si se omite, imprime en pantalla")
    parser.add_argument("--tesseract", help="Ruta al ejecutable si no está en PATH")
    args = parser.parse_args()

    texto = extraer_texto(args.imagen, idioma=args.idioma, ejecutable=args.tesseract)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(texto + "\n", encoding="utf-8")
        print(f"Texto guardado en: {args.salida}")
    else:
        print(texto)


if __name__ == "__main__":
    main()
