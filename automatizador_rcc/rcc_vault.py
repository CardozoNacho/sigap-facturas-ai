"""Secretos locales protegidos por DPAPI CurrentUser. Nunca imprime valores."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path

HOME = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'SIGAP' / 'RCC'


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def crypt(data, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('Las credenciales RCC requieren Windows/DPAPI')
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    api = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    fn = api.CryptUnprotectData if decrypt else api.CryptProtectData
    fn.restype = wintypes.BOOL
    # UI_FORBIDDEN=1; no LOCAL_MACHINE.
    ok = fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise RuntimeError('No se pudo acceder a la configuracion protegida de esta cuenta Windows')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def save(config):
    HOME.mkdir(parents=True, exist_ok=True)
    temp = HOME / 'config.tmp'
    temp.write_bytes(crypt(json.dumps(config).encode('utf-8')))
    os.replace(temp, HOME / 'config.dpapi')


def load():
    return json.loads(crypt((HOME / 'config.dpapi').read_bytes(), decrypt=True))
