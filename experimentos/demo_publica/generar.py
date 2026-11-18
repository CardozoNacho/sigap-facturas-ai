"""Genera una captura de la interfaz con servidor y datos sinteticos."""
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'automatizador_rcc'))
from test_rcc import FakePortal, F, cells
from rcc_contract import VERSION


def main():
    data = [dict(F, factura_id=str(i + 1), folio=str(i + 1),
                 nfact=str(123456789010 + i), comprobante=f'0001234{i + 5}') for i in range(4)]
    FakePortal.availability = classmethod(lambda cls: {
        'facturas': data, 'habilitado': True,
        'resumen': {'total': 6, 'con_comprobante': 5, 'disponibles': 4,
                    'ya_cargadas': 1, 'sin_comprobante': 1,
                    'comprobante_invalido': 0, 'comprobantes_repetidos': 0, 'otros_errores': 0}})
    FakePortal.jobs = [{
        'id': 'demostracion-sintetica', 'nexp': F['nexp'], 'usuario': 'Operador de demostracion',
        'creado': '2026-01-01T10:30:00-03:00', 'estado': 'completado_con_revision',
        'folios': {row['factura_id']: row['folio'] for row in data},
        'resultados': {
            '1': {'estado': 'guardada', 'mensaje': 'Guardado confirmado y datos verificados.', 'fila': cells(data[0])},
            '2': {'estado': 'confirmada', 'mensaje': 'Envio reconciliado sin repetir el guardado.', 'fila': cells(data[1])},
            '3': {'estado': 'revision', 'codigo': 'sesion_rcc', 'etapa': 'primera confirmacion',
                  'mensaje': 'La sesion del portal requiere revision antes de reintentar.', 'fila': []}}}]
    class DemoPortal(FakePortal):
        def do_GET(self):
            if self.path == '/FacturaRCCControler?accion=listar':
                self.response(json.dumps({'expedientes': [{'nexp': F['nexp'], 'cantidad': 6,
                                                          'con_comprobante': 5}], 'trabajos': self.jobs}))
                return
            super().do_GET()

    server = ThreadingHTTPServer(('127.0.0.1', 0), DemoPortal)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    target = ROOT / 'docs/assets/demo-rcc.png'
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 1000}, color_scheme='light')
                page.route('http://127.0.0.1:8766/**', lambda route: route.fulfill(
                    content_type='application/json', body=json.dumps({'version': VERSION, 'ocupado': False})))
                page.goto(f'http://127.0.0.1:{server.server_port}/vista')
                page.locator('#expedienteRcc').select_option(F['nexp'])
                page.locator('#anioRcc').fill('2026')
                page.locator('#revisarRcc').click()
                page.locator('#iniciarRcc:enabled').wait_for()
                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                page.screenshot(path=str(target), full_page=True)
                page.locator('.rcc-panel').last.screenshot(path=str(target.with_name('seguimiento-rcc.png')))
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(target)


if __name__ == '__main__':
    main()
