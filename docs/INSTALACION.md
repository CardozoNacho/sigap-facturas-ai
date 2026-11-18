# Instalación local

Requiere Windows, PowerShell 5.1 o posterior, Python 3.12 de 64 bits, Poppler completo y Ollama. Los binarios y pesos se instalan por separado.

Desde la raíz del proyecto, ajustar las rutas:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\instalar_entorno.ps1 -PythonExe "C:\Ruta\Python312\python.exe" -PopplerBin "C:\Herramientas\poppler\Library\bin" -EquiposPermitidos "127.0.0.1"
ollama pull qwen3-vl:2b-instruct
ollama list
```

El script crea `.venv`, instala los requisitos y genera `configuracion/lector.local.json`. No instala Poppler/Ollama ni reemplaza una configuración existente. La edición pública usa localhost; las direcciones reales de cada instalación se configuran localmente.

## Procesamiento por consola

Con Ollama activo y un PDF propio de la plantilla compatible:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\procesar_pdf.ps1 -Pdf "C:\Documentos\ejemplo.pdf" -MesExpediente "06/2026" -FechaEmision "18/06/2026" -NumeroExpediente "90001/26" -FolioInicial 1 -Salida ".\output\ejemplo"
```

El expediente del comando es sintético. `-Preparar` permite revisar detección y plan sin consultar al modelo. Los rangos manuales deben contener pares completos frente/dorso.

## Servicio HTTP

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\iniciar_servicio_lector.ps1
```

El servicio genera una clave local en `output/servicio/clave_api.txt`. El cliente Java la configura fuera del código. Puerto predeterminado: 8765; Ollama utiliza su API local en 11434.

El servicio usa Bearer y lista de equipos permitidos. El transporte y la red deben configurarse para el despliegue; este servidor no se expone directamente a Internet.

`configurar_inicio_servicio.ps1` registra la tarea de Windows. El inicio de Ollama es una dependencia separada. `crear_paquete_traslado.ps1` genera un paquete de fuentes sin datos, claves o entornos.

La inferencia por CPU puede tardar varios minutos por factura. Comenzar con una muestra pequeña. La aplicación Java completa y sus dependencias no se incluyen en esta edición.
