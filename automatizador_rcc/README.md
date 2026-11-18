# Automatizador RCC

Ejecutor local de Windows que obtiene trabajos autorizados desde Java y usa Playwright para completar formularios y verificar el resultado. El conector es especifico de la estructura del portal municipal.

- `rcc_contract.py`: contrato de datos y comprobaciones.
- `rcc_browser.py`: navegacion, sesiones y resultados inciertos.
- `rcc_bridge.py`: comunicacion local entre navegador y ejecutor.
- `rcc_vault.py`: credenciales protegidas con Windows DPAPI.
- `configurar.py`: formulario de configuracion local.
- `test_rcc.py`: servidor simulado y datos sinteticos.

La distribucion integrada requiere Python de 64 bits con Tcl/Tk y Playwright. Los lanzadores corresponden al paquete entregado por la aplicacion Java. Para revisar el desarrollo sin esa aplicacion, ejecutar las [pruebas](../docs/PRUEBAS.md).

Las credenciales no forman parte de esta edicion. Los tests no ingresan al portal real ni utilizan una cuenta municipal.
