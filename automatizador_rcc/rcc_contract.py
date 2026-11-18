"""Contrato RCC. No convierte importes mediante float ni interpreta siglos."""
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

VERSION = '0.2.0'
PORTAL = 'https://rcc.parana.gob.ar'
PROVEEDOR = '30709176672'
TIPO = 'LIQUIDACION DE SERVICIOS PUBLICOS CLASE B'


def factura(raw):
    out = {k: str(raw[k]).strip() for k in
           ('factura_id', 'nfact', 'comprobante', 'fecha', 'importe', 'nexp', 'exp_numero', 'exp_anio')}
    if not re.fullmatch(r'[1-9][0-9]*', out['factura_id']):
        raise ValueError('ID SIGAP invalido')
    if not re.fullmatch(r'[0-9]{1,32}', out['comprobante']):
        raise ValueError('Comprobante invalido')
    date.fromisoformat(out['fecha'])
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,4})?', out['importe']):
        raise ValueError('Importe invalido')
    amount = Decimal(out['importe'])
    if amount <= 0 or amount != amount.quantize(Decimal('.01')):
        raise ValueError('RCC requiere importe positivo con precision de centavos')
    out['importe'] = format(amount, '.2f')
    if not re.fullmatch(r'[0-9]+', out['exp_numero']) or not re.fullmatch(r'[0-9]{4}', out['exp_anio']):
        raise ValueError('Expediente invalido')
    if not 1900 <= int(out['exp_anio']) <= 2199:
        raise ValueError('Anio fuera de rango')
    match = re.fullmatch(r'([0-9]+)/([0-9]{2}|[0-9]{4})', out['nexp'])
    if not match or int(match[1]) != int(out['exp_numero']) or not out['exp_anio'].endswith(match[2]):
        raise ValueError('Expediente y anio no coinciden')
    return out


def huella(raw):
    return hashlib.sha256(json.dumps(factura(raw), sort_keys=True).encode()).hexdigest()


def comparar(cells, raw):
    return not diferencias(cells, raw)


def diferencias(cells, raw):
    """Columnas visibles RCC: Of, Tipo, Nro, Proveedor, Sitfis, Fecha, Importe, Doc, Estado."""
    f = factura(raw)
    if len(cells) < 10:
        return ['RCC no devolvio una fila completa para verificar los datos.']
    errors = []
    expected = [(2, 'Tipo', 'LIQ-SP-B'), (3, 'Comprobante', '00018-' + f['comprobante']),
                (4, 'Proveedor', 'E.N.E.R.S.A.'),
                (6, 'Fecha', date.fromisoformat(f['fecha']).strftime('%d-%m-%Y')),
                (8, 'Expediente', 'EX-' + f['exp_numero'] + '/' + f['exp_anio']),
                (9, 'Estado', 'Validado')]
    for index, label, value in expected:
        actual = cells[index].strip()
        if index == 3:
            parts = actual.split('-')
            equal = len(parts) == 2 and parts[0].isdigit() and int(parts[0]) == 18 and parts[1] == f['comprobante']
        else:
            equal = actual == value
        if not equal:
            errors.append(label + ': SIGAP esperado ' + value + '; RCC ' + actual + '.')
    try:
        equal_amount = Decimal(cells[7].strip()) == Decimal(f['importe'])
    except (ValueError, InvalidOperation):
        equal_amount = False
    if not equal_amount:
        errors.append('Importe: SIGAP ' + f['importe'] + '; RCC ' + cells[7].strip() + '.')
    return errors
