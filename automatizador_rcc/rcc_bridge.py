"""Puente local RCC. Solo loopback, origen SIGAP configurado y trabajos autenticados."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import json
import re
import threading
from rcc_contract import VERSION
from rcc_vault import load

PORT = 8766
MAX_BODY = 16384
lock = threading.Lock()
status = {'version': VERSION, 'ocupado': False, 'mensaje': 'Listo'}
config = None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api(ticket, action, data=None):
    req = Request(config['sigap_url'] + '/FacturaRCCControler?accion=' + action,
                  data=json.dumps(data or {}).encode(), method='POST', headers={
                      'Authorization': 'Bearer ' + ticket['token'],
                      'X-RCC-Job': ticket['id'], 'Content-Type': 'application/json'})
    with build_opener(NoRedirect()).open(req, timeout=40) as response:
        raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise RuntimeError('Respuesta SIGAP demasiado grande')
        return json.loads(raw)


def worker(ticket):
    portal = None
    try:
        from playwright.sync_api import sync_playwright
        from rcc_browser import RCC, PortalError
        # SIGAP valida token, destino de base y trabajo antes de abrir el navegador.
        job = api(ticket, 'tomar')
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(20000)
            page.set_default_navigation_timeout(45000)
            portal = RCC(page, config)
            try:
                revisiones = 0
                for f in job['facturas']:
                    prior = job['resultados'].get(f['factura_id'], {}).get('estado', 'preparada')
                    if prior in ('guardada', 'ya_existente', 'confirmada'):
                        continue
                    status['mensaje'] = 'Procesando comprobante ' + f['comprobante']
                    def before():
                        api(ticket, 'resultado', {'factura_id': f['factura_id'], 'estado': 'en_curso', 'fila': []})
                    try:
                        result = portal.procesar(f, prior, before)
                    except Exception:
                        sent = portal.sent
                        try:
                            portal.login()
                            result = portal.procesar(f, 'incierto' if sent else prior, before)
                        except Exception as error:
                            # No registrar excepciones Playwright: pueden incluir datos del formulario.
                            result = portal.fallo(error, enviado=sent or portal.sent)
                    if result['estado'] == 'incierto':
                        try:
                            result = portal.procesar(f, 'incierto', before)
                        except Exception as error:
                            result = portal.fallo(error, enviado=True)
                    api(ticket, 'resultado', dict(result, factura_id=f['factura_id']))
                    if result['estado'] == 'revision':
                        revisiones += 1
                        continue
                    if result['estado'] not in ('guardada', 'ya_existente', 'confirmada'):
                        status['mensaje'] = result.get('mensaje') or 'Trabajo detenido: requiere revision en SIGAP'
                        return
                status['mensaje'] = ('Trabajo terminado con ' + str(revisiones) + ' factura(s) para revision. Consulte los motivos en SIGAP.'
                                     if revisiones else 'Trabajo terminado. Consulte resultados en SIGAP.')
            finally:
                context.close()
                browser.close()
    except Exception:
        status['mensaje'] = 'Trabajo interrumpido. Reconecte desde SIGAP para reconciliar resultados.'
        # La marca sigue false si SIGAP no confirmo. Al retomar se consulta RCC antes de cargar.
    finally:
        status['ocupado'] = False
        lock.release()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def allowed(self):
        origin = self.headers.get('Origin', '')
        u = urlsplit(config['sigap_url'])
        return (self.headers.get('Host') in ('127.0.0.1:' + str(PORT), 'localhost:' + str(PORT))
                and origin == u.scheme + '://' + u.netloc)

    def reply(self, code, data):
        self.send_response(code)
        if self.allowed():
            self.send_header('Access-Control-Allow-Origin', self.headers['Origin'])
            self.send_header('Vary', 'Origin')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        if not self.allowed():
            self.reply(403, {'error': 'Origen no permitido'}); return
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', self.headers['Origin'])
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Sigap-RCC')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Vary', 'Origin')
        self.end_headers()

    def do_GET(self):
        if not self.allowed() or self.path != '/estado':
            self.reply(403, {'error': 'Solicitud no permitida'}); return
        self.reply(200, status)

    def do_POST(self):
        if not self.allowed() or self.path != '/ejecutar' or self.headers.get('X-Sigap-RCC') != '1':
            self.reply(403, {'error': 'Solicitud no permitida'}); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                raise ValueError()
            ticket = json.loads(self.rfile.read(length))
            if set(ticket) != {'id', 'token'} or not re.fullmatch(r'[a-f0-9]{32}', ticket['id']) or not re.fullmatch(r'[a-f0-9]{64}', ticket['token']):
                raise ValueError()
        except (ValueError, TypeError):
            self.reply(400, {'error': 'Trabajo invalido'}); return
        if not lock.acquire(blocking=False):
            self.reply(409, {'error': 'Ya hay un trabajo en curso en esta PC'}); return
        status.update(ocupado=True, mensaje='Verificando trabajo con SIGAP')
        threading.Thread(target=worker, args=(ticket,), daemon=True).start()
        self.reply(202, {'aceptado': True})


def main():
    global config
    config = load()
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    server.serve_forever()


if __name__ == '__main__':
    main()
