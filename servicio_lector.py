"""API privada SIGAP -> lector. Un trabajador secuencial y lotes en disco."""
import argparse
from datetime import datetime
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent
LOCK = threading.RLock()
COLA = queue.Queue()
ID = re.compile(r'^[a-f0-9]{32}$')
MAX_PDF = 1024 * 1024 * 1024


def ahora():
    return datetime.now().astimezone().isoformat()


def leer(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def guardar(path, obj):
    tmp = path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def validar_config(data):
    mes = data.get('mes_expediente', '')
    fecha = data.get('fecha_emision', '')
    if not isinstance(mes, str) or not re.fullmatch(r'\d{2}/\d{4}', mes):
        raise ValueError('Mes esperado: MM/AAAA.')
    if not isinstance(fecha, str) or not re.fullmatch(r'\d{2}/\d{2}/\d{4}', fecha):
        raise ValueError('Fecha esperada: DD/MM/AAAA.')
    datetime.strptime(mes, '%m/%Y')
    datetime.strptime(fecha, '%d/%m/%Y')
    exp = data.get('expediente')
    folio = data.get('folio_inicial')
    if not isinstance(exp, str) or not exp.strip() or len(exp) > 80 or any(ord(c)<32 for c in exp):
        raise ValueError('Numero de expediente invalido.')
    if type(folio) is not int or not 1 <= folio <= 2147483647:
        raise ValueError('Folio inicial invalido.')
    return {'mes_expediente':mes, 'fecha_emision':fecha,
            'expediente':exp.strip(), 'folio_inicial':folio}


def estado_publico(job):
    p = job/'trabajo.json'
    if not p.exists():
        raise FileNotFoundError('Lote inexistente.')
    info = leer(p)
    result = {k:v for k,v in info.items() if k not in ('sha256_pdf',)}
    progress = job/'salida/progreso.json'
    if progress.exists():
        result['progreso'] = leer(progress)
    return result


def trabajador(base):
    while True:
        identificador = COLA.get()
        job = base/identificador
        try:
            # Bloqueo por proceso: permanece tomado si el servicio se cierra
            # y el lector hijo sigue vivo. Permite detectar ese caso al reiniciar.
            with LOCK:
                info = leer(job/'trabajo.json')
                if info['estado'] != 'en_cola':
                    continue
                info.update(estado='procesando', iniciado=ahora())
                guardar(job/'trabajo.json',info)
            cfg = info['configuracion']
            cmd = [sys.executable, str(ROOT/'ejecutar_lote_servicio.py'), str(job)]
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            with (job/'ejecucion.log').open('ab') as log:
                process = subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env=env)
                with LOCK:
                    info = leer(job/'trabajo.json'); info['pid_lector']=process.pid
                    guardar(job/'trabajo.json',info)
                code = process.wait()
            with LOCK:
                info = leer(job/'trabajo.json')
                progress = leer(job/'salida/progreso.json') if (job/'salida/progreso.json').exists() else {}
                if code:
                    estado = 'requiere_revision_paginas' if progress.get('estado')=='requiere_revision_paginas' else 'error'
                elif progress.get('errores',0): estado='finalizado_con_errores'
                else: estado='finalizado'
                info.update(estado=estado, finalizado=ahora(), codigo_salida=code)
                if code: info['mensaje']='No se completo el lote. Revisar el diagnostico y el registro de ejecucion.'
                guardar(job/'trabajo.json',info)
        except Exception:
            with LOCK:
                info=leer(job/'trabajo.json')
                info.update(estado='error',mensaje='No se pudo ejecutar el lector. Consultar registro del servicio.',finalizado=ahora())
                guardar(job/'trabajo.json',info)
            import traceback
            traceback.print_exc()
        finally:
            COLA.task_done()


class ApiError(Exception):
    def __init__(self, code, message): self.code,self.message=code,message


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.0'
    server_version='SIGAPLector/1'

    def setup(self):
        super().setup()
        self.connection.settimeout(1800)

    def json_response(self,code,data):
        raw=json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(raw)

    def autenticar(self):
        ip=ipaddress.ip_address(self.client_address[0])
        if str(ip) not in self.server.allowed:
            raise ApiError(403,'Equipo no autorizado.')
        supplied=self.headers.get('Authorization','')
        if not hmac.compare_digest(supplied,'Bearer '+self.server.token):
            raise ApiError(401,'Credencial de servicio invalida.')

    def longitud(self,maximum):
        if self.headers.get('Transfer-Encoding'):
            raise ApiError(411,'Enviar Content-Length; no se acepta transferencia chunked.')
        try: size=int(self.headers.get('Content-Length','-1'))
        except ValueError: raise ApiError(400,'Content-Length invalido.')
        if not 0 < size <= maximum: raise ApiError(413,'Tamano de solicitud fuera de limite.')
        return size

    def body_json(self):
        size=self.longitud(16384)
        data=self.rfile.read(size)
        if len(data)!=size: raise ApiError(400,'Solicitud incompleta.')
        return json.loads(data.decode('utf-8'))

    def imagen_factura(self,job,numero,lado):
        """Sirve la pagina original. El dorso T1 se renderiza bajo demanda, sin IA."""
        if not numero.isdigit() or lado not in ('frente','dorso'):
            raise ApiError(400,'Imagen solicitada invalida.')
        numero=int(numero)
        plan_path=job/'salida/plan_paginas.json'
        if not plan_path.exists(): raise ApiError(409,'La seleccion de paginas aun no esta disponible.')
        plan=leer(plan_path)
        if not 1 <= numero <= len(plan): raise ApiError(404,'Factura inexistente en este lote.')
        item=plan[numero-1]
        if item['numero']!=numero: raise ApiError(409,'El plan de paginas no coincide con la factura.')
        imagen=job/f'salida/factura_{numero:03d}/{lado}.png'
        if not imagen.exists():
            # Cache separada: no competir con el PNG temporal que escribe el lector.
            imagen=job/f'visor/factura_{numero:03d}/{lado}.png'
            if not imagen.exists():
                from evaluar_pdf import renderizar
                renderizar(job/'entrada.pdf',item['pagina_'+lado],imagen,dpi=150)
        with imagen.open('rb') as stream:
            self.send_response(200)
            self.send_header('Content-Type','image/png')
            self.send_header('Content-Length',str(imagen.stat().st_size))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            shutil.copyfileobj(stream,self.wfile)

    def documento_factura(self,job,numero):
        """Extrae el par original a un PDF temporal; no duplica las imagenes PNG."""
        if not numero.isdigit(): raise ApiError(400,'Numero de factura invalido.')
        numero=int(numero)
        path=job/'salida/plan_paginas.json'
        if not path.exists(): raise ApiError(409,'El plan de paginas aun no esta disponible.')
        plan=leer(path)
        if not 1 <= numero <= len(plan): raise ApiError(404,'Factura inexistente en el lote.')
        item=plan[numero-1]
        if item['numero']!=numero: raise ApiError(409,'Plan de paginas inconsistente.')
        from pypdf import PdfReader, PdfWriter
        with (job/'entrada.pdf').open('rb') as source, tempfile.SpooledTemporaryFile(max_size=4194304,dir=job,mode='w+b') as output:
            reader=PdfReader(source)
            writer=PdfWriter()
            for key in ('pagina_frente','pagina_dorso'):
                page=item[key]
                if not 1 <= page <= len(reader.pages): raise ApiError(409,'Pagina fuera del PDF original.')
                writer.add_page(reader.pages[page-1])
            writer.write(output)
            size=output.tell()
            if not 0 < size <= 32*1024*1024: raise ApiError(413,'El documento individual supera 32 MB.')
            output.seek(0)
            self.send_response(200)
            self.send_header('Content-Type','application/pdf')
            self.send_header('Content-Length',str(size))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            shutil.copyfileobj(output,self.wfile)

    def run_request(self):
        self.autenticar()
        partes=self.path.split('?',1)[0].strip('/').split('/')
        with LOCK:
            if partes==['salud'] and self.command=='GET':
                self.json_response(200,{'estado':'disponible','version':1}); return
            if partes==['lotes'] and self.command=='GET':
                jobs=[]
                for job in self.server.base.iterdir():
                    if ID.fullmatch(job.name) and (job/'trabajo.json').exists(): jobs.append(estado_publico(job))
                jobs.sort(key=lambda j:j['creado'],reverse=True)
                self.json_response(200,{'lotes':jobs[:100]}); return
            if partes==['lotes'] and self.command=='POST':
                config=validar_config(self.body_json())
                uid=uuid.uuid4().hex; job=self.server.base/uid; job.mkdir()
                info={'id':uid,'estado':'esperando_pdf','creado':ahora(),'configuracion':config}
                guardar(job/'trabajo.json',info)
                self.json_response(201,info); return
            if len(partes)<2 or partes[0]!='lotes' or not ID.fullmatch(partes[1]):
                raise ApiError(404,'Recurso inexistente.')
            job=self.server.base/partes[1]
            info=estado_publico(job)
            if len(partes)==2 and self.command=='GET':
                self.json_response(200,info); return
            if len(partes)==5 and partes[2]=='imagenes' and self.command=='GET':
                self.imagen_factura(job,partes[3],partes[4]); return
            if len(partes)==4 and partes[2]=='documentos' and self.command=='GET':
                self.documento_factura(job,partes[3]); return
            recurso=partes[2] if len(partes)==3 else ''
            if recurso=='resultados' and self.command=='GET':
                p=job/'salida/resultados.json'
                self.json_response(200,leer(p) if p.exists() else {'facturas':[]}); return
            if recurso=='diagnostico' and self.command=='GET':
                p=job/'salida/deteccion_paginas.json'
                self.json_response(200,leer(p) if p.exists() else {}); return
            if recurso in ('iniciar','reanudar') and self.command=='POST':
                if info['estado'] in ('en_cola','procesando'):
                    self.json_response(202,info); return
                allowed=('pdf_recibido',) if recurso=='iniciar' else ('error','interrumpido','finalizado_con_errores')
                if info['estado'] not in allowed: raise ApiError(409,'El lote no admite esta operacion en su estado actual.')
                if (job/'lector.lock').exists() and not bloqueo_disponible(job/'lector.lock'):
                    raise ApiError(409,'El proceso lector anterior todavia esta activo.')
                data=leer(job/'trabajo.json'); data.update(estado='en_cola',encolado=ahora())
                guardar(job/'trabajo.json',data); COLA.put(data['id'])
                self.json_response(202,data); return
            if recurso=='pdf' and self.command=='PUT':
                if info['estado']!='esperando_pdf': raise ApiError(409,'El lote ya recibio su PDF.')
                # Marcar transferencia para impedir dos PUT concurrentes.
                data=leer(job/'trabajo.json'); data['estado']='recibiendo_pdf'; guardar(job/'trabajo.json',data)
            else: raise ApiError(404,'Operacion inexistente.')
        # No mantener el mutex global durante la transferencia de un PDF grande.
        tmp=job/'entrada.pdf.part'
        try:
            remaining=self.longitud(MAX_PDF)
            if shutil.disk_usage(job).free < remaining*2+512*1024*1024:
                raise ApiError(507,'Espacio insuficiente para recibir y procesar el PDF.')
            sha=hashlib.sha256(); first=True
            with tmp.open('wb') as stream:
                while remaining:
                    block=self.rfile.read(min(1024*1024,remaining))
                    if not block: raise ApiError(400,'PDF incompleto.')
                    if first and not block.startswith(b'%PDF-'): raise ApiError(400,'El contenido no comienza con una cabecera PDF.')
                    first=False; stream.write(block); sha.update(block); remaining-=len(block)
            tmp.replace(job/'entrada.pdf')
            with LOCK:
                data=leer(job/'trabajo.json'); data.update(estado='pdf_recibido',sha256_pdf=sha.hexdigest())
                guardar(job/'trabajo.json',data); self.json_response(200,estado_publico(job))
        except Exception:
            tmp.unlink(missing_ok=True)
            with LOCK:
                data=leer(job/'trabajo.json'); data['estado']='esperando_pdf'; guardar(job/'trabajo.json',data)
            raise

    def dispatch(self):
        try: self.run_request()
        except ApiError as error: self.json_response(error.code,{'error':error.message})
        except FileNotFoundError: self.json_response(404,{'error':'Lote inexistente.'})
        except (ValueError,TypeError,KeyError): self.json_response(400,{'error':'Parametros o JSON invalidos.'})
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception:
            import traceback
            traceback.print_exc()
            self.json_response(500,{'error':'Error interno; consultar registro del servicio.'})

    do_GET=dispatch
    do_POST=dispatch
    do_PUT=dispatch


def bloqueo_disponible(path):
    from ejecutar_lote_servicio import bloqueo_lector
    try:
        with bloqueo_lector(path): return True
    except OSError: return False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='0.0.0.0')
    parser.add_argument('--puerto',type=int,default=8765)
    parser.add_argument('--datos',type=Path,default=ROOT/'output/servicio')
    parser.add_argument('--permitir',default='127.0.0.1')
    args=parser.parse_args()
    base=args.datos.resolve(); base.mkdir(parents=True,exist_ok=True)
    clave=base/'clave_api.txt'
    if not clave.exists():
        with clave.open('x',encoding='ascii') as out: out.write(secrets.token_urlsafe(48))
    token=clave.read_text(encoding='ascii').strip()
    if len(token)<32: raise ValueError('La clave API debe tener al menos 32 caracteres.')
    server=ThreadingHTTPServer((args.host,args.puerto),Handler)
    server.daemon_threads=True
    server.base=base; server.token=token
    server.allowed={str(ipaddress.ip_address(ip.strip())) for ip in args.permitir.split(',')}
    # Recuperacion: no duplicar lectores que sobrevivieron al servicio.
    hay_hijo_activo=False
    for job in base.iterdir():
        if not ID.fullmatch(job.name) or not (job/'trabajo.json').exists(): continue
        info=leer(job/'trabajo.json')
        if info['estado']=='procesando':
            if not bloqueo_disponible(job/'lector.lock'):
                hay_hijo_activo=True
            else:
                info.update(estado='interrumpido',mensaje='El servicio se reinicio. Puede reanudar este lote.')
                guardar(job/'trabajo.json',info)
        elif info['estado']=='recibiendo_pdf':
            (job/'entrada.pdf.part').unlink(missing_ok=True)
            info['estado']='esperando_pdf'; guardar(job/'trabajo.json',info)
        if info['estado']=='en_cola': COLA.put(info['id'])
    if hay_hijo_activo:
        server.server_close()
        raise RuntimeError('Un lector anterior sigue activo. Esperar a que termine y reiniciar el servicio para evitar ejecuciones simultaneas.')
    threading.Thread(target=trabajador,args=(base,),daemon=True).start()
    print(f'Servicio SIGAP en {args.host}:{args.puerto}. Clave de conexion en {clave}. No publicar ese archivo.',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=='__main__': main()
