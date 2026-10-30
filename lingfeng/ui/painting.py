"""DPI-aware static layers; transport cursors are painted separately each frame."""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPixmap,QPainter
import lingfeng.ui.theme as theme


def cached_layer(widget,painter,key,draw,target=None):
    target=target or widget
    ratio=target.devicePixelRatioF()
    key=(target.width(),target.height(),ratio,theme.is_dark(),theme.PAINT_REVISION,key)
    if getattr(widget,'layer_key',None)!=key:
        pixmap=QPixmap(max(1,round(target.width()*ratio)),max(1,round(target.height()*ratio)))
        pixmap.setDevicePixelRatio(ratio)
        cached=QPainter(pixmap)
        try:draw(cached)
        finally:cached.end()
        widget.layer_pixmap=pixmap;widget.layer_key=key
        widget.cache_renders=getattr(widget,'cache_renders',0)+1
    painter.drawPixmap(QPointF(0,0),widget.layer_pixmap)


def roll_view_key(roll):
    return (id(roll),getattr(roll,'paint_revision',0),roll.zoom,roll.row_height,
            roll.horizontalScrollBar().value(),roll.verticalScrollBar().value(),roll.ruler_height)
