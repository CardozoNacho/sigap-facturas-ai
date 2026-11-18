"""Proceso hijo con bloqueo que envuelve la CLI existente sin copiar el pipeline."""
from contextlib import contextmanager
import json
from pathlib import Path
import sys


@contextmanager
def bloqueo_lector(path):
    with path.open('a+b') as f:
        f.seek(0,2)
        if not f.tell(): f.write(b'0'); f.flush()
        f.seek(0)
        if sys.platform=='win32':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try: yield
        finally:
            f.seek(0)
            if sys.platform=='win32': msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(f,fcntl.LOCK_UN)


def main():
    job=Path(sys.argv[1]).resolve(strict=True)
    with bloqueo_lector(job/'lector.lock'):
        import procesar_pdf
        cfg=json.loads((job/'trabajo.json').read_text(encoding='utf-8'))['configuracion']
        sys.argv=[str(Path(__file__).parent/'procesar_pdf.py'),str(job/'entrada.pdf'),
                  '--mes',cfg['mes_expediente'],'--fecha-emision',cfg['fecha_emision'],
                  '--expediente',cfg['expediente'],'--folio-inicial',str(cfg['folio_inicial']),
                  '--salida',str(job/'salida')]
        procesar_pdf.main()


if __name__=='__main__': main()
