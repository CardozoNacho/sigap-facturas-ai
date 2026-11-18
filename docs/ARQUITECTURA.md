# Arquitectura y flujo de datos

## Responsabilidades

Java mantiene interfaz, reglas de alta y persistencia en PostgreSQL. El servicio Python recibe PDFs y organiza el trabajo. El lector PowerShell prepara recortes y solicita inferencia a Ollama. Qwen interpreta imágenes y devuelve datos estructurados.

Java y Python se comunican por HTTP. Java entrega el PDF y luego consulta el estado mediante el identificador del lote. Un trabajador secuencial procesa la cola mientras la API atiende consultas de progreso.

## Desde un PDF hasta una factura

1. El usuario aporta expediente, fecha, mes y folio inicial.
2. Se inspecciona el PDF a baja resolución, se busca el identificador rojo compatible con la plantilla y se comprueba la alternancia frente/dorso.
3. Se genera un plan con páginas y folios. Excluir una factura no renumera las siguientes.
4. Se renderiza el frente a 150 DPI y se prepara el recorte general. El original queda disponible para las otras zonas.
5. Una llamada POST a `http://localhost:11434/api/chat` envía modelo, instrucciones, imagen Base64, esquema JSON y opciones de generación.
6. Se verifica la tarifa con su recorte específico. Una discrepancia exige otra lectura; sin acuerdo no se selecciona una rama.
7. El número de factura también tiene lectura de comprobación y desempate condicional.
8. T1 obtiene consumo del frente y factor del pie, omitiendo el dorso. T2–T4 consultan el consumo del período solicitado y sus campos específicos del dorso.
9. Se guardan respuestas, tiempos, decisiones, resultado y progreso. Cada factura puede aparecer en la interfaz antes de terminar el lote.

## Recuperación y revisión

Los manifiestos registran configuración y hashes. Una versión diferente utiliza otra salida para evitar mezclar mediciones. Las etapas completas pueden recuperarse y los bloqueos impiden lectores simultáneos sobre el mismo trabajo.

Un `null` no se convierte en cero ni en una tarifa por defecto. La aplicación distingue falta de lectura, desacuerdo, fallo de ejecución y cero válido por reglas de negocio.

La instancia Java valida NIS, número de factura, duplicados, importes, consumo y campos por tarifa antes de confirmar el alta. El usuario puede revisar imágenes, corregir o excluir. El respaldo documental persistido y los temporales de extracción tienen ciclos de vida diferentes.

## Automatización del portal

Playwright usa selectores y contratos deterministas, sin un modelo para decidir qué botón pulsar. Se verifican filas y resultados para distinguir guardado, existencia previa, reconciliación de un envío incierto y revisión pendiente.

El ejecutor local recibe trabajos autorizados desde Java. Las credenciales del portal permanecen en el equipo del operador, protegidas mediante Windows DPAPI. Las pruebas usan un servidor simulado en localhost.

La edición pública incluye la implementación del lector y referencias del conector Java; la webapp anfitriona completa y su configuración de base de datos no se distribuyen.
