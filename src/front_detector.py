"""Localizador geometrico del bloque rojo NIS de la plantilla ENERSA.

No lee el NIS ni utiliza Qwen/OCR. Una coincidencia de color es una
heuristica de plantilla, no una certificacion del contenido documental.
"""
from PIL import Image

VERSION = 'enersa-rojo-v1'


def localizar_bloque_rojo(imagen):
    # Normalizar la miniatura para que los umbrales no dependan del DPI.
    ancho = 600
    alto = round(imagen.height * ancho / imagen.width)
    rgb = imagen.convert('RGB').resize((ancho, alto), Image.Resampling.BILINEAR)
    x0, y0, x1, y1 = round(.52*ancho), 0, ancho, round(.25*alto)
    roi = rgb.crop((x0, y0, x1, y1))
    w, h = roi.size
    mascara = bytearray(r > 130 and r > g*1.35 and r > b*1.25
                        for r, g, b in roi.getdata())
    candidatos = []
    for inicio in range(w*h):
        if not mascara[inicio]:
            continue
        mascara[inicio] = 0
        pila = [inicio]
        cuenta = 0
        xmin = xmax = inicio % w
        ymin = ymax = inicio // w
        while pila:
            p = pila.pop()
            x, y = p % w, p // w
            cuenta += 1
            xmin, xmax = min(xmin, x), max(xmax, x)
            ymin, ymax = min(ymin, y), max(ymax, y)
            vecinos = []
            if x: vecinos.append(p-1)
            if x+1 < w: vecinos.append(p+1)
            if y: vecinos.append(p-w)
            if y+1 < h: vecinos.append(p+w)
            for vecino in vecinos:
                if mascara[vecino]:
                    mascara[vecino] = 0
                    pila.append(vecino)
        bw, bh = xmax-xmin+1, ymax-ymin+1
        caja = [(xmin+x0)/ancho, (ymin+y0)/alto,
                (xmax+x0+1)/ancho, (ymax+y0+1)/alto]
        densidad = cuenta/(bw*bh)
        if (.10 <= bw/ancho <= .40 and .009 <= bh/alto <= .07
                and 2.5 <= bw/bh <= 18 and densidad >= .38
                and caja[0] >= .55 and caja[1] <= .18):
            candidatos.append({'caja_relativa': caja,
                               'densidad_roja': round(densidad, 3),
                               'pixeles_rojos': cuenta})
    return {'frente_probable': bool(candidatos),
            'candidatos': candidatos, 'detector': VERSION}
