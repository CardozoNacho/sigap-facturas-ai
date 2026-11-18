"""Entrada general para PDF ENERSA, sin CSV ni mapa historico obligatorio."""
import argparse
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image, ImageDraw
from src.front_detector import localizar_bloque_rojo, VERSION

ROOT = Path(__file__).resolve().parent
LECTOR = ROOT/'lectores/general/lector_qwen_tarifa_verificada.ps1'
spec = importlib.util.spec_from_file_location('utilidades_lote', ROOT/'evaluar_pdf.py')
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def revisar_fechas(mes, fecha):
    datetime.strptime(mes, '%m/%Y')
    return datetime.strptime(fecha, '%d/%m/%Y').strftime('%d/%m/%Y')


def inspeccionar_pdf(pdf, salida, total, inicial, final):
    """Inspeccion completa a baja resolucion; sin llamadas de inferencia."""
    paginas = []
    preview = salida/'deteccion'
    preview.mkdir(exist_ok=True)
    for inicio in range(1, total+1, 20):
        imagenes = convert_from_path(str(pdf), dpi=60, first_page=inicio,
                                    last_page=min(inicio+19, total), fmt='ppm')
        for numero, imagen in enumerate(imagenes, inicio):
            hallazgo = localizar_bloque_rojo(imagen)
            hallazgo['pagina'] = numero
            paginas.append(hallazgo)
            if hallazgo['frente_probable']:
                # Evidencia de cabecera de cada candidato, sin leer manuscritos.
                w, h = imagen.size
                imagen.crop((round(w*.5), 0, w, round(h*.32))).save(
                    preview/f'pagina_{numero:04d}.png')
            imagen.close()
        print(f'Inspeccion visual automatica: {min(inicio+19,total)}/{total} paginas.', flush=True)
    candidatos = [p['pagina'] for p in paginas if p['frente_probable']]
    primera = inicial or (candidatos[0] if candidatos else None)
    ultima = final or total
    informe = {'detector': VERSION, 'paginas': paginas,
               'candidatos_frente': candidatos, 'pagina_inicial': primera,
               'pagina_final': ultima, 'seleccion_manual': inicial is not None,
               'errores': [], 'advertencias': []}
    errores = informe['errores']
    if primera is None:
        errores.append('No se detecto un bloque rojo compatible. Indicar --pagina-inicial tras revisar el PDF.')
    elif not (1 <= primera <= ultima <= total):
        errores.append('Rango de paginas fuera del PDF.')
    elif (ultima-primera+1) % 2:
        errores.append('El rango seleccionado no contiene pares completos frente/dorso. Revisar --pagina-final.')
    else:
        frentes = list(range(primera, ultima+1, 2))
        dorsos = list(range(primera+1, ultima+1, 2))
        faltantes = [p for p in frentes if p not in candidatos]
        inesperados = [p for p in dorsos if p in candidatos]
        if faltantes or inesperados:
            mensaje = f'Patron frente/dorso dudoso: frentes sin bloque {faltantes}; bloques en dorsos {inesperados}.'
            if inicial is None:
                errores.append(mensaje+' Revisar las paginas antes de asignar folios; no se inicia inferencia.')
            else:
                informe['advertencias'].append(mensaje+' Se respeta el rango confirmado manualmente.')
        informe['paginas_frente'] = frentes
    ev.guardar_json(salida/'deteccion_paginas.json', informe)
    if errores:
        raise ValueError(' '.join(errores))
    # Hoja de control con los primeros 20 candidatos del rango seleccionado.
    elegidos = [p for p in candidatos if primera <= p <= ultima][:20]
    hoja = Image.new('RGB', (1200, max(1, (len(elegidos)+3)//4)*220), 'white')
    draw = ImageDraw.Draw(hoja)
    for i, pagina in enumerate(elegidos):
        with Image.open(preview/f'pagina_{pagina:04d}.png') as img:
            img.thumbnail((295,190))
            x,y = (i%4)*300,(i//4)*220
            hoja.paste(img, (x,y))
            draw.text((x+5,y+195),f'Pagina {pagina}',fill='black')
    hoja.save(salida/'cabeceras_deteccion.png')
    return informe


def resumen(salida, plan, configuracion, estado, actual=None):
    registros = []
    for item in plan:
        carpeta = salida/f"factura_{item['numero']:03d}"
        registro = dict(item)
        registro['estado'] = 'pendiente'
        if (carpeta/'estado.json').exists():
            registro.update(ev.leer_json(carpeta/'estado.json'))
        if registro['estado'] == 'completada':
            registro['lectura'] = ev.leer_json(carpeta/'lectura-con-nfact-validado.json')
        registros.append(registro)
    ev.guardar_json(salida/'resultados.json', {'configuracion': configuracion, 'facturas': registros})
    ev.guardar_json(salida/'progreso.json', {
        'total': len(plan),
        'completadas': sum(r['estado']=='completada' for r in registros),
        'errores': sum(r['estado']=='error' for r in registros),
        'pendientes': sum(r['estado'] in ('pendiente','en_proceso') for r in registros),
        'requieren_revision': sum(bool(r.get('motivos_revision')) for r in registros),
        'estado': estado, 'factura_actual': actual, 'pid_python': os.getpid(),
        'actualizado': datetime.now().astimezone().isoformat()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--mes', required=True, help='Mes del expediente MM/AAAA')
    parser.add_argument('--fecha-emision', required=True, help='Fecha asignada DD/MM/AAAA')
    parser.add_argument('--expediente', required=True)
    parser.add_argument('--folio-inicial', type=int, required=True)
    parser.add_argument('--pagina-inicial', type=int, help='Confirmacion manual del primer frente, base 1')
    parser.add_argument('--pagina-final', type=int, help='Ultima pagina incluida, debe ser dorso')
    parser.add_argument('--salida', type=Path, help='Para reanudar indicar la misma carpeta')
    parser.add_argument('--preparar', action='store_true', help='Detectar y preparar sin consultar Ollama')
    args = parser.parse_args()
    fecha = revisar_fechas(args.mes, args.fecha_emision)
    if args.folio_inicial < 1 or not args.expediente.strip():
        parser.error('Indicar folio inicial positivo y expediente no vacio.')
    pdf = args.pdf.resolve(strict=True)
    identificador = re.sub(r'[^\w.-]+','_',args.expediente.strip())[:80]
    salida = (args.salida or ROOT/'output/lotes'/f'{identificador}_{pdf.stem}_{datetime.now():%Y%m%d_%H%M%S}').resolve()
    salida.mkdir(parents=True, exist_ok=True)
    configuracion = {'pdf': str(pdf), 'sha256_pdf': ev.sha256(pdf),
                     'mes_expediente': args.mes, 'fecha_emision': fecha,
                     'expediente': args.expediente.strip(), 'folio_inicial': args.folio_inicial,
                     'pagina_inicial_manual': args.pagina_inicial, 'pagina_final_manual': args.pagina_final,
                     'dpi':150, 'modelo':'qwen3-vl:2b-instruct', 'num_ctx':8192, 'num_predict':512,
                     'lector_sha256':ev.sha256(LECTOR), 'detector':VERSION,
                     'origen_fecha':'usuario', 'origen_folio':'secuencia_desde_entrada_usuario'}
    print(f'Salida del lote: {salida}', flush=True)
    with ev.bloquear_lote(salida):
        manifiesto = salida/'manifiesto.json'
        if manifiesto.exists() and ev.leer_json(manifiesto) != configuracion:
            raise ValueError('La configuracion cambio. Usar otra salida; no se mezclan lecturas.')
        ev.guardar_json(manifiesto, configuracion)
        total = int(pdfinfo_from_path(str(pdf))['Pages'])
        deteccion_path = salida/'deteccion_paginas.json'
        try:
            if deteccion_path.exists() and not ev.leer_json(deteccion_path).get('errores'):
                deteccion = ev.leer_json(deteccion_path)
            else:
                deteccion = inspeccionar_pdf(pdf, salida, total, args.pagina_inicial, args.pagina_final)
        except Exception as error:
            ev.guardar_json(salida/'progreso.json', {'estado':'requiere_revision_paginas','error':str(error)})
            raise
        plan = [{'numero':i, 'pagina_frente':p, 'pagina_dorso':p+1,
                 'folio_asignado':str(args.folio_inicial+i-1)}
                for i,p in enumerate(deteccion['paginas_frente'],1)]
        ev.guardar_json(salida/'plan_paginas.json', plan)
        for archivo,nombre in ((LECTOR,'lector_usado.ps1'),(Path(__file__),'ejecutor_usado.py'),
                                (ROOT/'src/front_detector.py','detector_usado.py')):
            target = salida/nombre
            if target.exists() and ev.sha256(target)!=ev.sha256(archivo):
                raise ValueError(f'Version diferente de {nombre}; usar otra salida.')
            if not target.exists(): shutil.copy2(archivo,target)
        print(f'Primer frente: pagina {plan[0]["pagina_frente"]}. Facturas: {len(plan)}. Folios: {plan[0]["folio_asignado"]} a {plan[-1]["folio_asignado"]}.',flush=True)
        resumen(salida,plan,configuracion,'preparado')
        if args.preparar:
            print('Preparacion terminada; no se consulto al modelo.',flush=True)
            return
        ev.comprobar_ollama()
        for item in plan:
            n = item['numero']
            carpeta = ev.carpeta_factura(salida,n)
            if (carpeta/'estado.json').exists() and ev.leer_json(carpeta/'estado.json').get('estado')=='completada':
                continue
            ev.guardar_json(carpeta/'estado.json',{'estado':'en_proceso'})
            resumen(salida,plan,configuracion,'ejecutando',n)
            started = time.perf_counter()
            proc = None
            try:
                ev.renderizar(pdf,item['pagina_frente'],carpeta/'frente.png',150)
                comando = ['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(LECTOR),
                    '-FrenteImagen',str(carpeta/'frente.png'),'-DorsoImagen',str(carpeta/'dorso.png'),
                    '-DirectorioSalida',str(carpeta),'-PdfOrigen',str(pdf),
                    '-PaginaDorso',str(item['pagina_dorso']),'-PythonExe',sys.executable,
                    '-MesExpediente',args.mes,'-FechaEmision',fecha,
                    '-NumeroExpediente',args.expediente.strip(),'-FolioAsignado',item['folio_asignado'],
                    '-Dpi','150','-Reanudar']
                print(f'Factura {n}/{len(plan)}; folio asignado {item["folio_asignado"]}.',flush=True)
                with (carpeta/'ejecucion.log').open('a',encoding='utf-8') as log:
                    proc = subprocess.Popen(comando,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                            text=True,encoding='utf-8',errors='replace')
                    for linea in proc.stdout:
                        log.write(linea); log.flush(); print(linea.rstrip(),flush=True)
                    code = proc.wait()
                if code or not (carpeta/'lectura-con-nfact-validado.json').exists():
                    raise RuntimeError(f'Llector finalizo con codigo {code}; consultar ejecucion.log.')
                lectura = ev.leer_json(carpeta/'lectura-con-nfact-validado.json')
                motivos = [f'Campo obligatorio nulo: {campo}' for campo in
                           ('numero_comprobante','nfact','nisnu','importepvenc','consactual','tarifa')
                           if lectura.get(campo) is None]
                for campo in ev.ESPECIFICOS.get(lectura.get('tarifa'),()):
                    if campo=='recfactpot' and lectura['tarifa']==1: continue
                    if lectura.get(campo) is None: motivos.append(f'Campo especifico nulo: {campo}')
                ev.guardar_json(carpeta/'procedencia.json',{
                    'expediente':{'valor':args.expediente.strip(),'origen':'usuario'},
                    'fecha':{'valor':fecha,'origen':'usuario'},
                    'folio':{'valor':item['folio_asignado'],'origen':'secuencia','folio_inicial':args.folio_inicial,
                             'indice_factura_base_uno':n}})
                ev.guardar_json(carpeta/'estado.json',{'estado':'completada',
                    'segundos':round(time.perf_counter()-started,2),'motivos_revision':motivos})
            except KeyboardInterrupt:
                if proc and proc.poll() is None:
                    proc.terminate(); proc.wait(timeout=15)
                ev.guardar_json(carpeta/'estado.json',{'estado':'pendiente','nota':'Interrumpida; respuestas completas conservadas.'})
                resumen(salida,plan,configuracion,'interrumpido',n)
                raise
            except Exception as error:
                ev.guardar_json(carpeta/'estado.json',{'estado':'error','error':str(error),
                                  'motivos_revision':['Fallo de ejecucion; revisar registro.']})
                print(f'Error de factura {n}: {error}. Se continua con la siguiente.',flush=True)
            resumen(salida,plan,configuracion,'ejecutando',n)
        resumen(salida,plan,configuracion,'finalizado')
        print('Lote recorrido. Revisar progreso.json y resultados.json; no se cargo nada en SIGAP.',flush=True)


if __name__ == '__main__':
    main()
