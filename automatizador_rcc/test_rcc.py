"""Pruebas sin conexion al portal real, sin facturas ni credenciales reales."""
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from pathlib import Path
import json
import re
from urllib.parse import parse_qs
import unittest
from unittest.mock import patch
from rcc_contract import factura, comparar
from rcc_browser import RCC, PortalError
from rcc_contract import VERSION
from rcc_vault import crypt

F = dict(factura_id='1', folio='62', nfact='123456789012', comprobante='00012345', fecha='2026-06-18',
         importe='1234.56', nexp='90001/26', exp_numero='90001', exp_anio='2026')


def cells(f):
    return ['', 'DIRECCCION GENERAL DE ALUMBRADO PUBLICO', 'LIQ-SP-B', '00018-' + f['comprobante'],
            'E.N.E.R.S.A.', 'ACACNI', '-'.join(reversed(f['fecha'].split('-'))), f['importe'],
            'EX-' + f['exp_numero'] + '/' + f['exp_anio'], 'Validado']


class ContractTests(unittest.TestCase):
    def test_decimales_y_ceros(self):
        self.assertEqual(factura(F)['comprobante'], '00012345')
        self.assertEqual(factura(dict(F, importe='0.10'))['importe'], '0.10')
        for value in ['1,20', '1e3', '1.001', '0', '-3', 'NaN']:
            with self.assertRaises(ValueError):
                factura(dict(F, importe=value))

    def test_expediente_sin_siglo_implicito(self):
        with self.assertRaises(ValueError):
            factura(dict(F, exp_anio='26'))
        with self.assertRaises(ValueError):
            factura(dict(F, exp_numero='9000'))
        self.assertEqual(factura(dict(F, nexp='90001/2026'))['exp_anio'], '2026')

    def test_validado_no_certifica_fecha_importe_expediente(self):
        self.assertTrue(comparar(cells(F), F))
        for key, value in [('fecha', '2026-06-19'), ('importe', '1234.57'), ('exp_numero', '1')]:
            changed = dict(F, **{key: value})
            if key == 'exp_numero': changed['nexp'] = '1/26'
            self.assertFalse(comparar(cells(changed), F))

    @unittest.skipUnless(__import__('os').name == 'nt', 'DPAPI solo Windows')
    def test_dpapi_roundtrip(self):
        raw = b'credential-sintetica-no-real'
        protected = crypt(raw)
        self.assertNotIn(raw, protected)
        self.assertEqual(crypt(protected, decrypt=True), raw)


class FakePortal(BaseHTTPRequestHandler):
    stored = {}
    pending = {}
    mode = ''
    expire = False
    saves = 0
    searches = 0
    first_confirms = 0
    available = 1
    jobs = []

    @classmethod
    def availability(cls):
        return {'facturas': [F] if cls.available else [], 'habilitado': bool(cls.available),
                'resumen': {'total': 6, 'con_comprobante': 4, 'disponibles': cls.available,
                            'ya_cargadas': 3 if not cls.available else 2, 'sin_comprobante': 1,
                            'comprobante_invalido': 1, 'comprobantes_repetidos': 0, 'otros_errores': 1}}

    def log_message(self, *args): pass
    def response(self, html, code=200, cookie=None):
        self.send_response(code)
        if cookie: self.send_header('Set-Cookie', cookie)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers(); self.wfile.write(html.encode())

    @classmethod
    def consulta(cls, msg='', number=''):
        rows = ''.join('<tr>' + ''.join('<td>' + str(v) + '</td>' for v in cells(f)) + '</tr>'
                       for f in cls.stored.values() if not number or number == f['comprobante'])
        return ('<p>' + msg + '</p><button onclick="document.getElementById(\'filters\').hidden=false">Filtros</button>'
                '<div id="filters" hidden><form id="formConsulta1" action="/search" method="post">'
                '<input id="cuit" name="cuit"><input id="puntoventa" name="punto"><input id="nrocomprobante" name="numero">'
                '<button>Buscar</button></form>'
                '<form id="formConsulta2"><input name="otro_filtro"><button>Buscar</button></form>'
                '</div><table id="miTabla"><tbody>' + rows + '</tbody></table>')

    def do_GET(self):
        cls = type(self)
        if self.path == '/vista' or self.path.split('?', 1)[0] == '/js/facturas-rcc.js':
            root = Path(__file__).resolve().parent.parent
            web = root / 'integracion_rcc' / 'web'
            if not web.exists(): web = root.parent / 'movimientos' / 'WebContent'
            path = web / ('facturasRcc.jsp' if self.path == '/vista' else 'js/facturas-rcc.js')
            raw = path.read_text(encoding='utf-8')
            raw = re.sub(r'<%.*?%>', '', raw, flags=re.S)
            self.response(raw); return
        resource=self.path.split('?',1)[0]
        if resource in ('/styles.css','/css/facturas-rcc.css'):
            root=Path(__file__).resolve().parent.parent
            web=root/'integracion_rcc/web'
            if not web.exists(): web=root.parent/'movimientos/WebContent'
            path=web/'css/facturas-rcc.css' if resource!='/styles.css' else root.parent/'SigapTesting/movimientos/WebContent/styles.css'
            raw=path.read_text(encoding='utf-8-sig') if path.exists() else ''
            raw=re.sub(r'@import[^;]+;','',raw,flags=re.S)
            self.send_response(200);self.send_header('Content-Type','text/css; charset=utf-8');self.end_headers();self.wfile.write(raw.encode());return
        if self.path == '/FacturaRCCControler?accion=listar':
            self.response(json.dumps({'expedientes': [{'nexp': F['nexp'], 'cantidad': 6, 'con_comprobante': 4}], 'trabajos': cls.jobs})); return
        if self.path == '/login':
            if cls.mode == 'login_externo':
                self.response('<form action="https://example.invalid/login"><input name="user"><input type="password"><button>Ingresar</button></form>'); return
            self.response('<form method="post" action="/login"><label>Usuario<input name="user"></label>'
                          '<label>Password<input type="password" name="password"></label><button>Ingresar</button></form>'); return
        if 'session=yes' not in self.headers.get('Cookie', ''):
            self.send_response(302); self.send_header('Location', '/login'); self.end_headers(); return
        if self.path == '/comprobante/Consulta': self.response(self.consulta()); return
        if self.path == '/comprobante/nuevo':
            if cls.expire:
                cls.expire = False
                self.response('Internal Server Error', 500, 'session=no'); return
            self.response('<form method="post" action="/step1">'
                          '<select id="alta_comprobante_Reparticion" name="rep"><option>062 - DIRECCCION GENERAL DE ALUMBRADO PUBLICO</option></select>'
                          '<select id="alta_comprobante_TipoFactura"><option>LIQUIDACION DE SERVICIOS PUBLICOS CLASE B</option></select>'
                          '<input id="alta_comprobante_PuntoVenta"><input id="alta_comprobante_NumeroComprobante" name="number">'
                          '<input id="alta_comprobante_CUIT"><button id="alta_comprobante_Confirmar">Confirmar</button></form>'); return
        self.response('Inicio')

    def do_POST(self):
        cls = type(self)
        data = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode(), keep_blank_values=True).items()}
        if self.path in ('/FacturaRCCControler?accion=revisar', '/FacturaRCCControler?accion=disponibles'):
            self.response(json.dumps(self.availability())); return
        if self.path == '/login':
            self.send_response(302); self.send_header('Set-Cookie', 'session=yes; Path=/'); self.send_header('Location', '/home'); self.end_headers(); return
        if self.path == '/search':
            cls.searches += 1
            if data.get('cuit') != '30709176672' or data.get('punto') != '18' or not data.get('numero'):
                self.response('Filtros incorrectos', 400); return
            num = data['numero']
            self.response(self.consulta('' if num in cls.stored else 'EL COMPROBANTE NO FUE ENCONTRADO', num)); return
        if self.path == '/step1':
            cls.first_confirms += 1
            if cls.mode == 'sesion_step1':
                self.send_response(302); self.send_header('Location', '/login'); self.end_headers(); return
            num = data['number']
            if num in cls.stored:
                self.response(self.consulta('EL COMPROBANTE YA EXISTE', num)); return
            cls.pending = dict(F, comprobante=num)
            self.response('ENERGIA DE ENTRE RIOS S. A. CUIT: 30709176672<form method="post" action="/save">'
                          '<label><input type="radio" id="alta_comprobante2_DocNroReceptor_0" checked>30-99910255-3</label>'
                          '<input type="radio" id="alta_comprobante2_caeCai_0" checked><input id="alta_comprobante2_nroCaiCae">'
                          '<input type="checkbox" id="check2" checked><input type="checkbox" id="alta_comprobante2_expediente">'
                          '<input type="checkbox" id="alta_comprobante2_orden"><input type="checkbox" id="alta_comprobante2_decreto">'
                          '<input id="alta_comprobante2_fechaEmicion" type="date" name="fecha">'
                          '<input id="alta_comprobante2_importe" name="importe"><input id="alta_comprobante2_nro" name="exp_numero">'
                          '<input id="alta_comprobante2_anio" name="exp_anio"><button id="alta_comprobante2_Confirmar">Confirmar</button></form>'); return
        if self.path == '/save':
            cls.saves += 1
            if cls.mode == 'error_antes': self.response('Internal Server Error', 500); return
            f = dict(cls.pending, **data)
            cls.stored[f['comprobante']] = f
            if cls.mode == 'error_despues': self.response('Internal Server Error', 500); return
            self.response(self.consulta('EL COMPROBANTE FUE GUARDADO', f['comprobante'])); return
        self.response('Error', 404)


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), FakePortal)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); cls.server.shutdown(); cls.server.server_close()

    def setUp(self):
        FakePortal.stored, FakePortal.saves, FakePortal.mode, FakePortal.expire = {}, 0, '', False
        FakePortal.available = 1
        FakePortal.jobs = []
        FakePortal.searches = FakePortal.first_confirms = 0
        self.context = self.browser.new_context()
        self.portal = RCC(self.context.new_page(), {'usuario': 'sintetico', 'password': 'sintetico'},
                          'http://127.0.0.1:' + str(self.server.server_port))
    def tearDown(self): self.context.close()

    def test_alta_y_duplicado_sin_segundo_post(self):
        events = []
        self.assertEqual(self.portal.procesar(F, before_send=lambda: events.append('antes'))['estado'], 'guardada')
        self.assertEqual(events, ['antes'])
        self.assertEqual(self.portal.procesar(F)['estado'], 'ya_existente')
        self.assertEqual(FakePortal.saves, 1)
        self.assertEqual(FakePortal.first_confirms, 2)
        self.assertEqual(FakePortal.searches, 0)

    def test_discrepancia_guardada_no_es_exito(self):
        FakePortal.stored[F['comprobante']] = dict(F, fecha='2026-06-19')
        result = self.portal.procesar(F)
        self.assertEqual(result['estado'], 'revision')
        self.assertIn('Fecha:', result['mensaje'])
        self.assertIn('18-06-2026', result['mensaje'])
        self.assertIn('19-06-2026', result['mensaje'])
        self.assertEqual(FakePortal.saves, 0)

    def test_worker_continua_tras_revision_y_envia_motivo(self):
        import rcc_bridge as bridge
        second = dict(F, factura_id='2', comprobante='00012346')
        third = dict(F, factura_id='3', comprobante='00012347')
        FakePortal.stored[F['comprobante']] = dict(F, fecha='2026-06-19')
        FakePortal.stored[third['comprobante']] = third
        results = []
        def api(ticket, action, data=None):
            if action == 'tomar':
                return {'facturas': [F, second, third], 'resultados': {}}
            results.append(data)
            return {'ok': True}
        bridge.lock.acquire()
        with patch('rcc_bridge.api', side_effect=api), patch('rcc_browser.RCC', return_value=self.portal), patch('playwright.sync_api.sync_playwright'):
            bridge.worker({'id': 'sintetico', 'token': 'sintetico'})
        final = [r for r in results if r['estado'] != 'en_curso']
        self.assertEqual([r['estado'] for r in final], ['revision', 'guardada', 'ya_existente'])
        self.assertIn('Fecha:', final[0]['mensaje'])
        self.assertEqual(FakePortal.saves, 1)
        self.assertIn('1 factura(s) para revision', bridge.status['mensaje'])
        self.assertFalse(bridge.status['ocupado'])

    def test_consulta_con_ids_y_nombres_reales_del_portal(self):
        FakePortal.stored[F['comprobante']] = dict(F)
        self.assertEqual(self.portal.consulta(F), cells(F))
        self.assertEqual(FakePortal.saves, 0)

    def test_filtros_incompatibles_informan_error_sin_alta(self):
        self.portal.page.set_default_timeout(500)
        # Simular un cambio del campo real, conservando el resto del formulario.
        self.portal.page.route('**/comprobante/Consulta', lambda route: route.fulfill(
            content_type='text/html', body=FakePortal.consulta().replace('id="puntoventa"', 'id="campo_cambiado"')))
        with self.assertRaisesRegex(PortalError, 'consulta previa en Filtros RCC'):
            self.portal.procesar(F, previous='incierto')
        self.assertEqual(FakePortal.saves, 0)
        self.assertFalse(self.portal.sent)

    def test_reconciliacion_existente_consulta_sin_abrir_alta(self):
        FakePortal.stored[F['comprobante']] = dict(F)
        result=self.portal.procesar(F, previous='incierto')
        self.assertEqual(result['estado'], 'confirmada')
        self.assertIn('despues de un envio sin confirmacion',result['mensaje'])
        self.assertEqual(FakePortal.searches, 1)
        self.assertEqual(FakePortal.first_confirms, 0)
        self.assertEqual(FakePortal.saves, 0)

    def test_duplicado_sin_fila_recurre_a_consulta(self):
        FakePortal.stored[F['comprobante']] = dict(F)
        self.portal.page.route('**/step1', lambda route: route.fulfill(
            content_type='text/html', body='<p>EL COMPROBANTE YA EXISTE</p>'))
        self.assertEqual(self.portal.procesar(F)['estado'], 'ya_existente')
        self.assertEqual(FakePortal.searches, 1)
        self.assertEqual(FakePortal.saves, 0)

    def test_sesion_expira_antes_primera_pantalla(self):
        FakePortal.expire = True
        self.assertEqual(self.portal.procesar(F)['estado'], 'guardada')
        self.assertEqual(self.portal.logins, 2)

    def test_renovaciones_exitosas_no_agotan_intentos(self):
        for _ in range(4): self.portal.login()
        self.assertEqual(self.portal.logins, 4)
        self.assertEqual(self.portal.login_failures, 0)

    def test_caida_despues_guardar_reconcilia(self):
        FakePortal.mode = 'error_despues'
        with self.assertRaises(PortalError) as caught:
            self.portal.procesar(F)
        self.assertEqual(self.portal.fallo(caught.exception)['estado'],'incierto')
        self.assertEqual(self.portal.procesar(F, previous='incierto')['estado'], 'confirmada')
        self.assertEqual(FakePortal.saves, 1)

    def test_caida_sin_guardado_no_reenvia(self):
        FakePortal.mode = 'error_antes'
        with self.assertRaises(PortalError) as caught:
            self.portal.procesar(F)
        self.assertEqual(self.portal.fallo(caught.exception)['estado'],'incierto')
        self.assertEqual(self.portal.procesar(F, previous='incierto')['estado'], 'incierto')
        self.assertEqual(FakePortal.saves, 1)

    def test_login_en_primera_confirmacion_informa_sesion_sin_enviar(self):
        FakePortal.mode='sesion_step1'
        with self.assertRaises(PortalError) as caught:
            self.portal.procesar(F)
        result=self.portal.fallo(caught.exception)
        self.assertEqual(result['estado'],'revision')
        self.assertEqual(result['codigo'],'sesion_rcc')
        self.assertEqual(result['etapa'],'primera confirmacion')
        self.assertIn('iniciar sesion',result['mensaje'])
        self.assertEqual(FakePortal.saves,0)
        self.assertFalse(self.portal.sent)

    def test_worker_reconcilia_guardado_sin_clasificar_como_preexistente(self):
        import rcc_bridge as bridge
        FakePortal.mode='error_despues'
        results=[]
        def api(ticket,action,data=None):
            if action=='tomar': return {'facturas':[F],'resultados':{}}
            results.append(data);return {'ok':True}
        bridge.lock.acquire()
        with patch('rcc_bridge.api',side_effect=api),patch('rcc_browser.RCC',return_value=self.portal),patch('playwright.sync_api.sync_playwright'):
            bridge.worker({'id':'sintetico','token':'sintetico'})
        self.assertEqual(results[-1]['estado'],'confirmada')
        self.assertEqual(FakePortal.saves,1)
        self.assertFalse(bridge.status['ocupado'])

    def test_worker_motiva_login_y_continua_con_siguiente(self):
        import rcc_bridge as bridge
        second=dict(F,factura_id='2',comprobante='00012346')
        results=[]
        def api(ticket,action,data=None):
            if action=='tomar': return {'facturas':[F,second],'resultados':{}}
            results.append(data);return {'ok':True}
        normal=self.portal.procesar
        def process(raw,previous='preparada',before_send=lambda:None):
            if raw['factura_id']=='1': raise PortalError('RCC solicito iniciar sesion.','sesion_rcc','primera confirmacion')
            return normal(raw,previous,before_send)
        bridge.lock.acquire()
        with patch('rcc_bridge.api',side_effect=api),patch('rcc_browser.RCC',return_value=self.portal),patch('playwright.sync_api.sync_playwright'),patch.object(self.portal,'procesar',side_effect=process):
            bridge.worker({'id':'sintetico','token':'sintetico'})
        final=[r for r in results if r['estado']!='en_curso']
        self.assertEqual([r['estado'] for r in final],['revision','guardada'])
        self.assertEqual(final[0]['codigo'],'sesion_rcc')
        self.assertIn('iniciar sesion',final[0]['mensaje'])
        self.assertEqual(FakePortal.saves,1)

    def test_si_no_persiste_inicio_no_confirma(self):
        def falla(): raise RuntimeError('SIGAP no disponible')
        with self.assertRaises(RuntimeError): self.portal.procesar(F, before_send=falla)
        self.assertEqual(FakePortal.saves, 0)

    def test_no_ingresa_clave_en_formulario_de_otro_origen(self):
        FakePortal.mode = 'login_externo'
        with self.assertRaises(PortalError): self.portal.login()
        self.assertEqual(self.portal.page.locator('input[type=password]').input_value(), '')

    def test_vista_exige_revision_antes_de_habilitar_carga(self):
        from playwright.sync_api import expect
        page = self.portal.page
        page.route('http://127.0.0.1:8766/**', lambda route: route.fulfill(
            status=200, content_type='application/json', body=json.dumps({'version': VERSION, 'ocupado': False, 'mensaje': 'Listo'})))
        page.goto(self.portal.base + '/vista')
        expect(page.locator('#expedienteRcc option')).to_have_count(2)
        expect(page.locator('#iniciarRcc')).to_be_disabled()
        page.locator('#expedienteRcc').select_option(F['nexp'])
        expect(page.locator('#resumenDisponiblesRcc')).to_contain_text('Disponibles para cargar: 1')
        expect(page.locator('#resumenDisponiblesRcc')).to_contain_text('Sin comprobante: 1')
        page.locator('#anioRcc').fill('2026')
        page.locator('#revisarRcc').click()
        expect(page.locator('#filasRcc tr')).to_have_count(1)
        expect(page.locator('#iniciarRcc')).to_be_enabled()
        page.locator('#anioRcc').fill('2025')
        expect(page.locator('#iniciarRcc')).to_be_disabled()

    def test_vista_sin_disponibles_no_habilita_y_muestra_cero(self):
        from playwright.sync_api import expect
        FakePortal.available = 0
        page = self.portal.page
        page.route('http://127.0.0.1:8766/**', lambda route: route.fulfill(
            status=200, content_type='application/json', body=json.dumps({'version': VERSION, 'ocupado': False})))
        page.goto(self.portal.base + '/vista')
        expect(page.locator('#expedienteRcc option')).to_have_count(2)
        page.locator('#expedienteRcc').select_option(F['nexp'])
        expect(page.locator('#resumenDisponiblesRcc')).to_contain_text('Disponibles para cargar: 0')
        page.locator('#anioRcc').fill('2026')
        page.locator('#revisarRcc').click()
        expect(page.locator('#mensajeRcc')).to_contain_text('No hay facturas disponibles')
        expect(page.locator('#iniciarRcc')).to_be_disabled()

    def test_vista_muestra_motivo_de_revision_como_texto(self):
        from playwright.sync_api import expect
        reason = 'Fecha: SIGAP 18-06-2026; RCC 19-06-2026. <img src=x>'
        FakePortal.jobs = [{'id': 'sintetico', 'nexp': F['nexp'], 'estado': 'completado_con_revision',
                            'usuario': 'operador', 'creado': '2026-11-11',
                            'resultados': {'1': {'estado': 'revision', 'fila': cells(F), 'mensaje': reason}}}]
        page = self.portal.page
        page.route('http://127.0.0.1:8766/**', lambda route: route.fulfill(
            content_type='application/json', body=json.dumps({'version': VERSION, 'ocupado': False})))
        page.goto(self.portal.base + '/vista')
        expect(page.locator('#trabajosRcc')).to_contain_text(reason)
        expect(page.locator('#trabajosRcc img')).to_have_count(0)

    def test_vista_distingue_confirmacion_sesion_y_motivo_ausente(self):
        from playwright.sync_api import expect
        FakePortal.jobs=[{'id':'sintetico','nexp':F['nexp'],'estado':'completado_con_revision',
            'usuario':'operador','creado':'2026-11-13','resultados':{
                '1':{'estado':'guardada','mensaje':'Guardado verificado.'},
                '2':{'estado':'confirmada','mensaje':'Se verifico el envio sin repetirlo.'},
                '3':{'estado':'revision','codigo':'sesion_rcc','etapa':'primera confirmacion','mensaje':'RCC solicito iniciar sesion.'},
                '4':{'estado':'revision','mensaje':''}}}]
        page=self.portal.page
        page.route('http://127.0.0.1:8766/**',lambda route:route.fulfill(content_type='application/json',body=json.dumps({'version':VERSION,'ocupado':False})))
        page.goto(self.portal.base+'/vista')
        area=page.locator('#trabajosRcc')
        expect(area).to_contain_text('Guardada en esta carga')
        expect(area).to_contain_text('Confirmada tras verificar el envio')
        expect(area).to_contain_text('Revisar acceso / sesion RCC')
        expect(area).to_contain_text('Momento: primera confirmacion.')
        expect(area).to_contain_text('Este resultado no contiene un motivo detallado')
        expect(area.locator('th')).to_have_count(4)

    def test_vista_muestra_folio_y_no_sustituye_faltante_por_id(self):
        from playwright.sync_api import expect
        FakePortal.jobs=[{'id':'sintetico','nexp':F['nexp'],'estado':'completado',
            'usuario':'operador','creado':'2026-11-13','folios':{'1':'0062','2':''},
            'resultados':{'1':{'estado':'guardada'},'2':{'estado':'confirmada'}}}]
        page=self.portal.page
        page.route('http://127.0.0.1:8766/**',lambda route:route.fulfill(content_type='application/json',body=json.dumps({'version':VERSION,'ocupado':False})))
        page.goto(self.portal.base+'/vista')
        page.locator('#expedienteRcc').select_option(F['nexp'])
        expect(page.locator('#filasRcc tr td').first).to_have_text('62')
        expect(page.locator('#trabajosRcc tbody tr').nth(0).locator('td').first).to_have_text('0062')
        expect(page.locator('#trabajosRcc tbody tr').nth(1).locator('td').first).to_have_text('Sin folio')
        expect(page.locator('#trabajosRcc th').first).to_have_text('Folio')


if __name__ == '__main__':
    unittest.main()
