"""Register the current portable installation as a Windows .lfs application."""
from pathlib import Path
import sys


def associate_project():
    if sys.platform!='win32' or not getattr(sys,'frozen',False):
        raise RuntimeError('请从打包后的 Lingfeng.exe 注册工程类型。')
    import ctypes
    import winreg
    exe=str(Path(sys.executable).resolve())
    values={
        r'Software\Classes\.lfs': ('','Lingfeng.Project'),
        r'Software\Classes\Lingfeng.Project': ('','伶风工程'),
        r'Software\Classes\Lingfeng.Project\DefaultIcon': ('',f'"{exe}",0'),
        r'Software\Classes\Lingfeng.Project\shell\open\command': ('',f'"{exe}" "%1"'),
        r'Software\Classes\.lfs\OpenWithProgids': ('Lingfeng.Project',''),
    }
    for path,(name,value) in values.items():
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,path) as key:winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
    ctypes.windll.shell32.SHChangeNotify(0x08000000,0,None,None)
