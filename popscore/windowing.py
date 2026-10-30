"""Windows taskbar identity and theme-aware frameless window integration."""
import sys
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication,QAbstractButton,QMenuBar,QScrollBar
from .theme import is_dark

APP_ID='Lingfeng.ForPopMusic'


def set_app_identity():
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def enable_frame(widget,taskbar=False):
    if sys.platform!='win32' or QApplication.platformName()!='windows':return
    import ctypes
    from ctypes import wintypes
    user=ctypes.windll.user32;hwnd=wintypes.HWND(int(widget.winId()))
    user.GetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int]
    user.SetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int,wintypes.LONG]
    widget._native_frame=True
    user.SetWindowLongW(hwnd,-16,user.GetWindowLongW(hwnd,-16)|0x00040000|0x00C00000)
    if taskbar:
        # Peer top-level windows expose separate previews under the process AppID.
        user.SetWindowLongW(hwnd,-20,(user.GetWindowLongW(hwnd,-20)|0x00040000)&~0x80)
    user.SetWindowPos(hwnd,None,0,0,0,0,0x0027)
    theme_frame(widget)


def theme_frame(widget):
    if sys.platform!='win32' or QApplication.platformName()!='windows' or not widget.isWindow():return
    import ctypes
    from ctypes import wintypes
    hwnd=wintypes.HWND(int(widget.winId()));dwm=ctypes.windll.dwmapi
    dark=ctypes.c_int(int(is_dark()))
    dwm.DwmSetWindowAttribute(hwnd,20,ctypes.byref(dark),ctypes.sizeof(dark))
    # COLORREF is 0x00BBGGRR. Unsupported attributes are ignored on older Windows.
    border=ctypes.c_uint(0x005B4635 if is_dark() else 0x00EAE1D8)
    dwm.DwmSetWindowAttribute(hwnd,34,ctypes.byref(border),ctypes.sizeof(border))


def resize_hit(widget,point):
    from .editor import ChordLane
    x,y=point.x(),point.y();edge=3
    if widget.isMaximized() or not 0<=x<widget.width() or not 0<=y<widget.height():return 0
    child=widget.childAt(point)
    while child and child is not widget:
        if isinstance(child,(QAbstractButton,QMenuBar,QScrollBar,ChordLane)):return 0
        child=child.parentWidget()
    left,right,top,bottom=x<edge,x>=widget.width()-edge,y<edge,y>=widget.height()-edge
    return 13 if top and left else 14 if top and right else 16 if bottom and left else 17 if bottom and right else 10 if left else 11 if right else 12 if top else 15 if bottom else 0


def native_frame_event(widget,message):
    if sys.platform!='win32' or not getattr(widget,'_native_frame',False) or not widget.isWindow():return None
    import ctypes
    from ctypes import wintypes
    msg=wintypes.MSG.from_address(int(message))
    if msg.message==0x0083 and msg.wParam:return True,0
    if msg.message==0x0084:
        pos=wintypes.POINT(ctypes.c_short(msg.lParam&0xffff).value,ctypes.c_short((msg.lParam>>16)&0xffff).value)
        ctypes.windll.user32.ScreenToClient(wintypes.HWND(int(widget.winId())),ctypes.byref(pos));ratio=widget.devicePixelRatioF()
        return True,resize_hit(widget,QPoint(round(pos.x/ratio),round(pos.y/ratio))) or 1
    return None
