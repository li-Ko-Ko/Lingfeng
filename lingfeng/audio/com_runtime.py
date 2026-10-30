"""Thread-local Windows COM lifetime for rendering and capture."""
import os
from contextlib import contextmanager

@contextmanager
def com_apartment():
    """Every export uses a fresh worker; COM initialization is thread-local.

    Use STA before importing SoundCard. Its module-level MTA initializer then
    leaves this apartment alone, so no initialization is owned by a dead worker.
    Accept an existing apartment, and balance both S_OK and S_FALSE ourselves.
    """
    if os.name!='nt':
        yield;return
    import ctypes
    ole=ctypes.WinDLL('ole32');ole.CoInitializeEx.argtypes=[ctypes.c_void_p,ctypes.c_uint32];ole.CoInitializeEx.restype=ctypes.c_long
    status=ole.CoInitializeEx(None,2)
    if status<0 and status&0xffffffff!=0x80010106:
        raise OSError(f'Windows audio initialization failed: 0x{status&0xffffffff:08X}')
    try:yield
    finally:
        if status in (0,1):ole.CoUninitialize()
