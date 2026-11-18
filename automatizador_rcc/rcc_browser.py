"""Adaptador determinista del RCC observado. Solo navega al dominio conocido."""
from urllib.parse import urlsplit, urljoin
from playwright.sync_api import Error as PlaywrightError
from rcc_contract import PORTAL, TIPO, PROVEEDOR, factura, diferencias


class PortalError(RuntimeError):
    def __init__(self, message, codigo='portal', etapa=''):
        super().__init__(message)
        self.codigo, self.etapa = codigo, etapa


class RCC:
    def __init__(self, page, credentials, base=PORTAL):
        self.page, self.credentials, self.base = page, credentials, base.rstrip('/')
        # base distinta solo para las pruebas locales, nunca configurable por un trabajo.
        if self.base != PORTAL and urlsplit(self.base).hostname not in ('127.0.0.1', 'localhost'):
            raise PortalError('Destino RCC no permitido')
        self.sent = False
        self.logins = 0
        self.login_failures = 0
        self.etapa = 'inicio'

    def comprobar_pantalla(self, etapa):
        self.etapa = etapa
        text = self.body()
        if '/login' in urlsplit(self.page.url).path or self.page.locator('input[type=password]').count():
            raise PortalError('RCC solicito iniciar sesion durante ' + etapa + '. No se pudo continuar con esta factura.', 'sesion_rcc', etapa)
        if 'Internal Server Error' in text:
            raise PortalError('RCC devolvio un error interno durante ' + etapa + '. No es una diferencia entre los datos de la factura.', 'error_portal', etapa)
        return text

    def fallo(self, error, enviado=None):
        sent = self.sent if enviado is None else enviado
        if isinstance(error, PortalError):
            mensaje, codigo = str(error), error.codigo
            etapa = error.etapa or self.etapa
        else:
            mensaje = 'No se pudo completar ' + self.etapa + ' en RCC. Revise disponibilidad o cambios del formulario.'
            codigo, etapa = 'recorrido_portal', self.etapa
            try:
                self.comprobar_pantalla(self.etapa)
            except PortalError as known:
                mensaje, codigo = str(known), known.codigo
            except Exception:
                pass
        if sent:
            mensaje += ' Hubo un intento de confirmacion final: se debe verificar RCC antes de repetir el envio.'
        return self.resultado('incierto' if sent else 'revision', mensaje=mensaje, codigo=codigo, etapa=etapa)

    def safe(self):
        u, expected = urlsplit(self.page.url), urlsplit(self.base)
        if (u.scheme, u.netloc) != (expected.scheme, expected.netloc):
            raise PortalError('RCC redirigio a un destino no permitido')

    def body(self):
        self.safe()
        return self.page.locator('body').inner_text()

    def goto(self, path):
        self.page.goto(self.base + path, wait_until='domcontentloaded')
        self.safe()

    def login(self):
        self.etapa = 'acceso al portal'
        if self.login_failures >= 2:
            raise PortalError('No se pudo renovar la sesion RCC; revisar acceso', 'sesion_rcc', self.etapa)
        self.logins += 1
        self.login_failures += 1
        self.goto('/login')
        fields = self.page.locator('input:not([type=hidden]):not([type=submit])')
        if fields.count() != 2 or self.page.locator('input[type=password]').count() != 1:
            raise PortalError('El acceso RCC cambio o requiere intervencion', 'sesion_rcc', self.etapa)
        form = self.page.locator('input[type=password]').locator('xpath=ancestor::form')
        action = urlsplit(urljoin(self.page.url, form.get_attribute('action') or self.page.url))
        expected = urlsplit(self.base)
        if (action.scheme, action.netloc) != (expected.scheme, expected.netloc):
            raise PortalError('El formulario de acceso apunta a un destino no permitido')
        fields.nth(0).fill(self.credentials['usuario'])
        self.page.locator('input[type=password]').fill(self.credentials['password'])
        self.page.get_by_role('button', name='Ingresar', exact=True).click()
        self.page.wait_for_load_state('domcontentloaded')
        self.safe()
        if '/login' in self.page.url or 'Internal Server Error' in self.body():
            raise PortalError('Acceso RCC rechazado; actualizar configuracion local', 'sesion_rcc', self.etapa)
        self.login_failures = 0

    def consulta(self, f):
        self.etapa = 'consulta de comprobante'
        self.goto('/comprobante/Consulta')
        if '/login' in self.page.url or 'Internal Server Error' in self.body():
            self.login(); self.goto('/comprobante/Consulta')
        self.comprobar_pantalla('consulta de comprobante')
        try:
            self.page.get_by_role('button', name='Filtros').click()
            form = self.page.locator('#formConsulta1')
            # RCC usa id=puntoventa/name=punto e id=nrocomprobante/name=numero.
            # Limitar la busqueda al primer formulario: hay otro Buscar en los filtros.
            for field, value in [('cuit', PROVEEDOR), ('puntoventa', '18'), ('nrocomprobante', f['comprobante'])]:
                control = form.locator('#' + field)
                control.fill(value)
                if control.input_value() != value:
                    raise PortalError('Los filtros de consulta RCC no conservaron los valores esperados.')
            form.get_by_role('button', name='Buscar', exact=True).click()
        except PlaywrightError:
            # No devolver la excepcion original: puede incluir valores del formulario.
            raise PortalError('No se pudo completar la consulta previa en Filtros RCC (CUIT, punto de venta y comprobante). Revise el formulario del portal.') from None
        text = self.comprobar_pantalla('resultado de consulta')
        if 'EL COMPROBANTE NO FUE ENCONTRADO' in text:
            return None
        return self.fila(f)

    def fila(self, f):
        matches = []
        for row in self.page.locator('#miTabla tbody tr').all():
            cells = row.locator('td').all_text_contents()
            if len(cells) >= 10 and cells[3].strip() == '00018-' + f['comprobante']:
                matches.append([c.strip() for c in cells[:10]])
        if len(matches) != 1:
            raise PortalError('No se identifica una unica fila RCC para el comprobante')
        return matches[0]

    def procesar(self, raw, previous='preparada', before_send=lambda: None):
        f = factura(raw)
        self.sent = False
        self.etapa = 'apertura del alta'
        if previous in ('en_curso', 'incierto'):
            # Un envio final incierto se consulta antes de volver a tocar el alta.
            existing = self.consulta(f)
            if existing is not None:
                return self.verificado('confirmada', existing, f)
            return self.resultado('incierto', mensaje='RCC no encontro el comprobante de un envio anterior incierto. Requiere revision manual.', codigo='envio_sin_confirmar', etapa='verificacion posterior al envio')
        # En una carga normal el primer Confirmar ya detecta los duplicados.
        # Reintentar solo esta navegacion GET cuando hay que renovar la sesion.
        for attempt in range(3):
            self.goto('/comprobante/nuevo')
            if '/login' not in self.page.url and 'Internal Server Error' not in self.body():
                break
            if attempt == 2:
                raise PortalError('No se pudo abrir el alta RCC despues de renovar la sesion.')
            self.login()
        p = self.page
        self.comprobar_pantalla('identificacion del comprobante')
        p.locator('#alta_comprobante_Reparticion').select_option(label='062 - DIRECCCION GENERAL DE ALUMBRADO PUBLICO')
        p.locator('#alta_comprobante_TipoFactura').select_option(label=TIPO)
        for key, value in [('PuntoVenta', '18'), ('NumeroComprobante', f['comprobante']), ('CUIT', PROVEEDOR)]:
            control = p.locator('#alta_comprobante_' + key)
            control.fill(value)
            if control.input_value() != value:
                raise PortalError('La identificacion visible difiere del trabajo SIGAP')
        p.locator('#alta_comprobante_Confirmar').click()
        text = self.comprobar_pantalla('primera confirmacion')
        if 'EL COMPROBANTE YA EXISTE' in text:
            try:
                cells = self.fila(f)
            except PortalError:
                # Solo consultar si el aviso no vino acompanado por la fila completa.
                cells = self.consulta(f)
            if cells is None:
                raise PortalError('RCC informo un duplicado pero no se pudieron verificar sus datos.')
            return self.verificado('ya_existente', cells, f)
        if 'ENERGIA DE ENTRE RIOS S. A.' not in text or PROVEEDOR not in text:
            raise PortalError('El portal no identifica al proveedor ENERSA esperado')
        receptor = p.get_by_role('radio', name='30-99910255-3', exact=True)
        self.etapa = 'datos de la factura'
        if receptor.count() != 1:
            raise PortalError('CUIT receptor inesperado')
        receptor.check()
        p.locator('#alta_comprobante2_caeCai_0').check()
        p.locator('#alta_comprobante2_nroCaiCae').fill('')
        p.locator('#check2').uncheck()
        p.locator('#alta_comprobante2_orden').uncheck()
        p.locator('#alta_comprobante2_decreto').uncheck()
        p.locator('#alta_comprobante2_expediente').check()
        for key, value in [('fechaEmicion', f['fecha']), ('importe', f['importe']), ('nro', f['exp_numero']), ('anio', f['exp_anio'])]:
            loc = p.locator('#alta_comprobante2_' + key)
            loc.fill(value)
            if loc.input_value() != value:
                raise PortalError('Los valores visibles difieren del trabajo SIGAP')
        before_send()  # Registrar el inicio temporal en SIGAP. Si falla, no enviar.
        self.sent = True
        self.etapa = 'confirmacion final'
        p.locator('#alta_comprobante2_Confirmar').click()
        if 'EL COMPROBANTE FUE GUARDADO' not in self.comprobar_pantalla('respuesta de confirmacion final'):
            # No repetir POST. La proxima ejecucion consulta y reconcilia.
            return self.resultado('incierto', mensaje='RCC no confirmo el resultado del envio; consultar antes de reintentar.', codigo='envio_sin_confirmar', etapa=self.etapa)
        self.etapa = 'verificacion del guardado'
        cells = self.fila(f)
        return self.verificado('guardada', cells, f)

    def verificado(self, estado, cells, f):
        reasons = diferencias(cells, f)
        mensajes = {
            'guardada': 'RCC confirmo el guardado y se verificaron los datos de la factura.',
            'ya_existente': 'RCC detecto el comprobante antes de enviar el alta final; sus datos coinciden con SIGAP.',
            'confirmada': 'El comprobante se encontro y verifico despues de un envio sin confirmacion. No se repitio el guardado; no se afirma que ya existiera antes de esta carga.'
        }
        result = self.resultado('revision' if reasons else estado, cells, ' '.join(reasons) if reasons else mensajes[estado],
                                codigo='diferencias_datos' if reasons else '', etapa='verificacion de datos')
        result['motivos'] = reasons
        return result

    @staticmethod
    def resultado(estado, cells=None, mensaje='', codigo='', etapa=''):
        return {'estado': estado, 'fila': cells or [], 'mensaje': mensaje, 'codigo': codigo, 'etapa': etapa}
