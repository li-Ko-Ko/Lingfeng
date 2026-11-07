"""Reusable viewport rasters; hidden surfaces retain no pixel buffers."""
import weakref
from PySide6.QtCore import QPointF,QObject,QEvent,Qt
from PySide6.QtGui import QPixmap,QPainter
import lingfeng.ui.theme as theme


def release_cached_layer(widget):
    widget.layer_pixmap=None;widget.layer_key=None


class _LayerVisibility(QObject):
    def __init__(self,owner,target):
        super().__init__(target);self.owner=weakref.ref(owner);target.installEventFilter(self)

    def eventFilter(self,target,event):
        if event.type()==QEvent.Type.Hide:
            owner=self.owner()
            if owner is not None:release_cached_layer(owner)
        return False


def cached_layer(widget,painter,key,draw,target=None):
    target=target or widget
    ratio=target.devicePixelRatioF()
    key=(target.width(),target.height(),ratio,theme.is_dark(),theme.PAINT_REVISION,key)
    if getattr(widget,'layer_key',None)!=key:
        if not hasattr(widget,'_layer_visibility'):widget._layer_visibility=_LayerVisibility(widget,target)
        width,height=max(1,round(target.width()*ratio)),max(1,round(target.height()*ratio))
        pixmap=getattr(widget,'layer_pixmap',None)
        if pixmap is None or pixmap.width()!=width or pixmap.height()!=height or pixmap.devicePixelRatioF()!=ratio:
            # Drop the old allocation before reserving a differently sized raster.
            release_cached_layer(widget);pixmap=None
            pixmap=QPixmap(width,height);pixmap.setDevicePixelRatio(ratio)
            widget.layer_allocations=getattr(widget,'layer_allocations',0)+1
        widget.layer_key=None;pixmap.fill(Qt.GlobalColor.transparent)
        cached=QPainter(pixmap)
        try:draw(cached)
        finally:cached.end()
        widget.layer_pixmap=pixmap;widget.layer_key=key
        widget.cache_renders=getattr(widget,'cache_renders',0)+1
    painter.drawPixmap(QPointF(0,0),widget.layer_pixmap)


def roll_view_key(roll):
    return (id(roll),getattr(roll,'paint_revision',0),roll.zoom,roll.row_height,
            roll.horizontalScrollBar().value(),roll.verticalScrollBar().value(),roll.ruler_height)


def time_view_key(roll):
    """Timeline layers do not depend on pitch scrolling or keyboard row size."""
    return (id(roll),getattr(roll,'time_revision',0),roll.zoom,
            roll.horizontalScrollBar().value(),roll.ruler_height)
