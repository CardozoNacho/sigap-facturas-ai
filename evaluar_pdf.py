"""Lote PDF reanudable; delega la extracción al lector PowerShell ya probado.

Los folios de referencia y el CSV se usan únicamente en la evaluación posterior.
El extractor recibe imágenes, el mes del expediente y la página de su dorso.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from PIL import Image, ImageDraw
from pdf2image import convert_from_path, pdfinfo_from_path

ROOT = Path(__file__).resolve().parent
LECTOR = ROOT / 'probar_qwen_por_etapas.ps1'
COMUNES = ('fecha', 'nfact', 'folio', 'tarifa', 'importepvenc', 'nisnu', 'consactual')
ESPECIFICOS = {
    1: ('factpot', 'recfactpot'),
    2: ('factpot', 'recfactpot', 'ptapotconv', 'ptapotreg'),
    3: ('factpot', 'recfactpot', 'fptapotconv', 'fptapotreg', 'fptapotconve', 'fptapotregi'),
    4: ('t4potconv',),
}
TARIFAS = {'UNO': 1, 'DOS': 2, 'TRES': 3, 'CUATRO': 4}


def leer_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def guardar_json(path, contenido):
    path = Path(path)
    temporal = path.with_suffix(path.suffix + '.tmp')
    temporal.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding='utf-8')
    temporal.replace(path)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b''):
            h.update(bloque)
    return h.hexdigest()


@contextmanager
def bloquear_lote(salida):
    """Bloqueo del sistema operativo: se libera incluso si termina el proceso."""
    with (salida / '.lock').open('a+b') as archivo:
        archivo.seek(0, 2)
        if not archivo.tell():
            archivo.write(b'0')
            archivo.flush()
        archivo.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError('Este lote ya está siendo procesado por otro proceso.') from error
        else:
            import fcntl
            fcntl.flock(archivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            archivo.seek(0)
            if os.name == 'nt':
                msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(archivo, fcntl.LOCK_UN)


def renderizar(pdf, pagina, destino, dpi=150):
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        with Image.open(destino) as imagen:
            imagen.verify()
        return
    imagen = convert_from_path(str(pdf), dpi=dpi, first_page=pagina, last_page=pagina, fmt='png')[0]
    temporal = destino.with_suffix('.tmp.png')
    imagen.save(temporal)
    temporal.replace(destino)
    imagen.close()


def carpeta_factura(salida, numero):
    carpeta = salida / f'factura_{numero:03d}'
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def preparar_frentes(pdf, salida, cantidad, dpi=150, paginas_frente=None):
    hoja = Image.new('RGB', (1500, ((cantidad + 4) // 5) * 210), 'white')
    dibujo = ImageDraw.Draw(hoja)
    for numero in range(1, cantidad + 1):
        carpeta = carpeta_factura(salida, numero)
        frente = carpeta / 'frente.png'
        pagina = paginas_frente[numero - 1] if paginas_frente is not None else 2 * numero - 1
        renderizar(pdf, pagina, frente, dpi)
        with Image.open(frente) as imagen:
            w, h = imagen.size
            encabezado = imagen.crop((round(.70 * w), round(.07 * h), round(.99 * w), round(.205 * h)))
            encabezado.thumbnail((300, 175))
            x, y = ((numero - 1) % 5) * 300, ((numero - 1) // 5) * 210
            hoja.paste(encabezado, (x, y))
            dibujo.text((x + 5, y + 178), f'Factura {numero:02d} / pagina {pagina}', fill='black')
        print(f'Preparado frente {numero}/{cantidad}, página {pagina}.', flush=True)
    hoja.save(salida / 'cabeceras.png')


def cargar_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as archivo:
        lector = csv.DictReader(archivo)
        requeridos = {'folio', 'nfact', 'tarifa', 'fecha', 'nisnu', 'importepvenc', 'consactual', 'factorpot', 'recfactpot'}
        if requeridos - set(lector.fieldnames or ()):
            raise ValueError('El CSV no contiene todas las columnas del piloto.')
        filas = list(lector)
    referencias = {}
    for fila in filas:
        folio = fila['folio'].strip()
        if folio in referencias:
            raise ValueError(f'Folio repetido en CSV: {folio}')
        referencias[folio] = fila
    return referencias


def normalizar(valor, campo, referencia=False):
    if valor is None or str(valor).strip().lower() in ('', 'null'):
        return None
    texto = str(valor).strip()
    if campo == 'fecha':
        for formato in ('%Y%m%d', '%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y'):
            try:
                return datetime.strptime(texto, formato).date().isoformat()
            except ValueError:
                pass
        raise ValueError('Fecha inválida')
    if campo == 'tarifa':
        return TARIFAS[texto.upper()] if texto.upper() in TARIFAS else int(texto)
    if campo in ('nfact', 'folio', 'nisnu'):
        texto = re.sub(r'[\s-]', '', texto)
        if not texto.isdigit():
            raise ValueError('Identificador no numérico')
        if campo == 'nisnu':
            if len(texto) not in (7, 9):
                raise ValueError('Longitud de NIS distinta de 7 o 9')
            texto = texto[:7]
        return texto
    if not referencia:
        texto = texto.replace('%', '').replace(' ', '')
        if ',' in texto:
            texto = texto.replace('.', '').replace(',', '.')
        elif campo in ('consactual', 'importepvenc') and re.fullmatch(r'[1-9]\d{0,2}(?:\.\d{3})+', texto):
            texto = texto.replace('.', '')
    numero = Decimal(texto)
    if not numero.is_finite():
        raise ValueError('Valor numérico no finito')
    return numero


def evaluar(salida, folios, referencias, cantidad):
    filas = []
    facturas = []
    estadisticas = {}
    for numero, folio in enumerate(folios, start=1):
        carpeta = carpeta_factura(salida, numero)
        estado = leer_json(carpeta / 'estado.json') if (carpeta / 'estado.json').exists() else {'estado': 'pendiente'}
        datos = leer_json(carpeta / 'lectura-sin-normalizar.json') if estado['estado'] == 'completada' else {}
        ref = referencias[folio]
        tarifa_ref = normalizar(ref['tarifa'], 'tarifa', True)
        facturas.append({'numero': numero, 'folio_referencia': folio, 'estado': estado['estado'], 'error': estado.get('error'), 'folio_leido': datos.get('folio')})
        for campo in COMUNES + ESPECIFICOS[tarifa_ref]:
            columna = 'factorpot' if campo == 'factpot' else campo
            obtenido, esperado = datos.get(campo), ref.get(columna)
            normal_obtenido, normal_esperado = None, None
            if estado['estado'] in ('pendiente', 'en_proceso'):
                resultado = 'pendiente'
            elif estado['estado'] != 'completada':
                resultado = 'sin_lectura'
            elif tarifa_ref == 1 and campo == 'recfactpot':
                resultado = 'sin_implementar'
            else:
                try:
                    normal_obtenido = normalizar(obtenido, campo)
                    normal_esperado = normalizar(esperado, campo, True)
                    if normal_esperado is None:
                        resultado = 'sin_referencia'
                    elif normal_obtenido is None:
                        resultado = 'no_extraido'
                    else:
                        resultado = 'coincide' if normal_obtenido == normal_esperado else 'difiere'
                except (ValueError, InvalidOperation, KeyError, TypeError):
                    resultado = 'formato_invalido'
            estadisticas.setdefault(campo, Counter())[resultado] += 1
            filas.append({'factura': numero, 'folio_referencia': folio, 'tarifa_referencia': tarifa_ref, 'campo': campo, 'columna_csv': columna, 'valor_extraido': obtenido, 'valor_referencia': esperado, 'normalizado_extraido': str(normal_obtenido) if normal_obtenido is not None else None, 'normalizado_referencia': str(normal_esperado) if normal_esperado is not None else None, 'resultado': resultado})
    metricas = {}
    for campo, conteos in estadisticas.items():
        evaluadas = sum(conteos.values()) - conteos['pendiente'] - conteos['sin_referencia']
        metricas[campo] = {**dict(conteos), 'evaluadas': evaluadas, 'porcentaje_acierto_sobre_evaluadas': round(100 * conteos['coincide'] / evaluadas, 2) if evaluadas else None}
    estado_facturas = Counter(f['estado'] for f in facturas)
    errores = [f for f in filas if f['resultado'] not in ('coincide', 'pendiente')]
    informe = {
        'total_facturas': cantidad,
        'estado_facturas': dict(estado_facturas),
        'por_campo': metricas,
        'facturas': facturas,
        'observaciones': [
            'Las referencias se vinculan por posición del PDF verificada visualmente; no se envían al extractor.',
            'Los denominadores incluyen los campos de la tarifa histórica, aunque la tarifa detectada sea errónea.',
            'recfactpot de tarifa 1 aún no se extrae: se informa sin_implementar y cuenta como falta de cobertura.',
            'El NIS extraído de nueve dígitos se compara usando sus primeros siete; se conservan los JSON originales.',
            'factpot se compara con factorpot del CSV; no se modifican las reglas ni la carga histórica.',
        ],
        'campos_con_error_o_sin_cobertura': len(errores),
    }
    guardar_json(salida / 'evaluacion.json', informe)
    for nombre, registros in (('evaluacion_campos.csv', filas), ('diferencias.csv', errores)):
        with (salida / nombre).open('w', encoding='utf-8-sig', newline='') as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=list(filas[0]))
            escritor.writeheader()
            escritor.writerows(registros)
    guardar_json(salida / 'progreso.json', {'total': cantidad, 'completadas': estado_facturas['completada'], 'errores': estado_facturas['error'], 'pendientes': estado_facturas['pendiente'] + estado_facturas['en_proceso'], 'actualizado': datetime.now().astimezone().isoformat()})
    return informe


def ejecutar_factura(pdf, salida, numero, mes, dpi=150, pagina_frente=None):
    carpeta = carpeta_factura(salida, numero)
    previo = leer_json(carpeta / 'estado.json') if (carpeta / 'estado.json').exists() else {}
    if previo.get('estado') == 'completada' and (carpeta / 'lectura-sin-normalizar.json').exists():
        print(f'Factura {numero}: ya completada; se conserva.', flush=True)
        return
    pagina_frente = pagina_frente if pagina_frente is not None else 2 * numero - 1
    pagina_dorso = pagina_frente + 1
    renderizar(pdf, pagina_frente, carpeta / 'frente.png', dpi)
    guardar_json(carpeta / 'estado.json', {'estado': 'en_proceso', 'numero': numero, 'pagina_frente': pagina_frente, 'pagina_dorso': pagina_dorso})
    comando = [str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(LECTOR), '-FrenteImagen', str(carpeta / 'frente.png'), '-DorsoImagen', str(carpeta / 'dorso.png'), '-DirectorioSalida', str(carpeta), '-PdfOrigen', str(pdf), '-PaginaDorso', str(pagina_dorso), '-PythonExe', sys.executable, '-MesExpediente', mes, '-Reanudar']
    comando += ['-Dpi', str(dpi)]
    inicio = time.perf_counter()
    print(f'Iniciando factura {numero}, páginas {pagina_frente}-{pagina_dorso}.', flush=True)
    proceso = None
    try:
        with (carpeta / 'ejecucion.log').open('a', encoding='utf-8') as log:
            proceso = subprocess.Popen(comando, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
            for linea in proceso.stdout:
                log.write(linea)
                log.flush()
                print(linea.rstrip(), flush=True)
            codigo = proceso.wait()
        if codigo != 0 or not (carpeta / 'lectura-sin-normalizar.json').exists():
            raise RuntimeError(f'El lector terminó con código {codigo}. Ver ejecucion.log y error.txt.')
        datos = leer_json(carpeta / 'lectura-sin-normalizar.json')
        if datos.get('tarifa') not in (1, 2, 3, 4):
            raise ValueError('La lectura combinada no tiene tarifa válida.')
        guardar_json(carpeta / 'estado.json', {'estado': 'completada', 'numero': numero, 'segundos_ultima_ejecucion': round(time.perf_counter() - inicio, 2), 'folio_leido': datos.get('folio'), 'tarifa_leida': datos['tarifa']})
    except KeyboardInterrupt:
        if proceso is not None and proceso.poll() is None:
            proceso.terminate()
            proceso.wait(timeout=15)
        guardar_json(carpeta / 'estado.json', {'estado': 'pendiente', 'numero': numero, 'nota': 'Interrumpida; las etapas finalizadas se conservan.'})
        raise
    except Exception as error:
        guardar_json(carpeta / 'estado.json', {'estado': 'error', 'numero': numero, 'error': str(error)})
        print(f'Error en factura {numero}: {error}. Se continúa con la siguiente.', flush=True)


def comprobar_ollama():
    with urllib.request.urlopen('http://localhost:11434/api/tags', timeout=10) as respuesta:
        modelos = json.loads(respuesta.read().decode('utf-8')).get('models', [])
    if not any(m.get('name') == 'qwen3-vl:2b-instruct' for m in modelos):
        raise RuntimeError('Ollama no tiene disponible qwen3-vl:2b-instruct. No se inicia el lote.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', nargs='?', type=Path)
    parser.add_argument('--mes')
    parser.add_argument('--csv', type=Path)
    parser.add_argument('--mapa', type=Path, default=ROOT / 'data' / 'dependencias_90001_folios.json')
    parser.add_argument('--salida', type=Path)
    parser.add_argument('--preparar', action='store_true')
    parser.add_argument('--solo-evaluar', action='store_true')
    parser.add_argument('--limite', type=int)
    parser.add_argument('--render-pagina', type=Path)
    parser.add_argument('--pagina', type=int)
    parser.add_argument('--destino', type=Path)
    parser.add_argument('--dpi', type=int, choices=(150, 300), default=150)
    args = parser.parse_args()
    if args.render_pagina:
        if not args.pagina or not args.destino:
            parser.error('--render-pagina requiere --pagina y --destino')
        renderizar(args.render_pagina, args.pagina, args.destino, args.dpi)
        return
    if not args.pdf or not args.mes or not args.csv:
        parser.error('Indica PDF, --mes MM/AAAA y --csv.')
    mes = datetime.strptime(args.mes, '%m/%Y')
    pdf = args.pdf.resolve(strict=True)
    referencias = cargar_csv(args.csv)
    mapa = leer_json(args.mapa)
    folios = mapa['folios']
    paginas_frente = mapa.get('paginas_frente')
    paginas = int(pdfinfo_from_path(str(pdf))['Pages'])
    if paginas % 2 or not folios or len(set(folios)) != len(folios):
        raise ValueError('Se necesitan páginas pares y folios de evaluación únicos.')
    if paginas_frente is None:
        if len(folios) != paginas // 2:
            raise ValueError('El PDF y el mapa de evaluación no tienen la misma cantidad de pares únicos.')
    elif (len(paginas_frente) != len(folios) or len(set(paginas_frente)) != len(paginas_frente)
          or paginas_frente != sorted(paginas_frente)
          or any(type(p) is not int or p < 1 or p % 2 != 1 or p + 1 > paginas for p in paginas_frente)):
        raise ValueError('La selección de páginas debe indicar frentes impares únicos, ordenados y con dorso, uno por folio.')
    if any(f not in referencias for f in folios):
        raise ValueError('Faltan folios de referencia en el CSV.')
    cantidad = len(folios)
    salida = (args.salida or ROOT / 'output' / 'lotes' / f'{pdf.stem}_{mes:%Y%m}').resolve()
    salida.mkdir(parents=True, exist_ok=True)
    manifiesto = {'pdf': str(pdf), 'sha256_pdf': sha256(pdf), 'paginas': paginas, 'mes_expediente': args.mes, 'dpi': args.dpi, 'modelo': 'qwen3-vl:2b-instruct', 'num_ctx': 8192, 'num_predict': 512, 'sha256_lector': sha256(LECTOR), 'folios_evaluacion': folios}
    if paginas_frente is not None:
        manifiesto['paginas_frente'] = paginas_frente
    with bloquear_lote(salida):
        manifest_path = salida / 'manifiesto.json'
        if manifest_path.exists() and leer_json(manifest_path) != manifiesto:
            raise ValueError('El PDF, el mes, el lector o el mapa cambió. Usa otra carpeta --salida para no mezclar pruebas.')
        guardar_json(manifest_path, manifiesto)
        print(f'PDF: {paginas} páginas, {cantidad} facturas. Salida: {salida}', flush=True)
        if args.preparar:
            preparar_frentes(pdf, salida, cantidad, args.dpi, paginas_frente)
            evaluar(salida, folios, referencias, cantidad)
            return
        evaluar(salida, folios, referencias, cantidad)
        if args.solo_evaluar:
            return
        comprobar_ollama()
        limite = min(args.limite or cantidad, cantidad)
        for numero in range(1, limite + 1):
            progreso = leer_json(salida / 'progreso.json')
            progreso.update({'estado': 'ejecutando', 'factura_actual': numero, 'pid_python': os.getpid()})
            guardar_json(salida / 'progreso.json', progreso)
            try:
                pagina_frente = paginas_frente[numero - 1] if paginas_frente is not None else None
                ejecutar_factura(pdf, salida, numero, args.mes, args.dpi, pagina_frente)
            finally:
                evaluar(salida, folios, referencias, cantidad)
        progreso = leer_json(salida / 'progreso.json')
        progreso.update({'estado': 'finalizado', 'factura_actual': None})
        guardar_json(salida / 'progreso.json', progreso)
        print(f'Lote recorrido. Consultar {salida / "evaluacion.json"}', flush=True)


if __name__ == '__main__':
    main()
