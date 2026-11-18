# Pruebas reproducibles

## Reglas y selección de ramas, sin Ollama

Desde la raíz del proyecto, en Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\experimentos\verificacion_tarifa\test_reglas.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\experimentos\verificacion_tarifa\test_flujo.ps1
```

Se cubren interpretación de tarifa, ambigüedad, nulos, desacuerdos, integridad del lector de referencia y nueve recorridos con respuestas simuladas. Las imágenes se generan sintéticamente: no se necesitan facturas reales ni inferencia. Se comprueban cambios de rama, campos específicos, consumo T1 y omisión de su dorso.

## Automatizador contra un portal simulado

```powershell
python -m pip install -r .\automatizador_rcc\requirements.txt
python -m playwright install chromium
Set-Location .\automatizador_rcc
python -m unittest test_rcc -v
```

Las pruebas utilizan un servidor local y datos sintéticos. Cubren contrato, guardado, duplicados, diferencias, sesiones, estados inciertos y presentación. La prueba DPAPI requiere Windows. No se accede al portal real.

Las pruebas Java de `integracion_rcc/` necesitan las clases de la aplicación anfitriona: no constituyen una compilación autónoma del sistema Java completo.

## Medición con documentos reales durante el desarrollo

Una muestra dirigida de ocho frentes de las cuatro tarifas confirmó las ocho referencias inspeccionadas, incluidos dos errores previos y una T3 real dentro de un lote de alumbrado. La verificación adicional tardó unos 107 segundos de media en la CPU utilizada.

La muestra no mide todos los campos ni estima la exactitud de otros lotes. Los PDFs y sus respuestas no se publican. Las pruebas sintéticas comprueban lógica y selección de ramas, no precisión visual del modelo.
