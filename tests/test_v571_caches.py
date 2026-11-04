"""Viewport raster memory is reusable, bounded and released when hidden."""
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QApplication,QWidget
from lingfeng.music.model import Context,Measure,Note,Project
from lingfeng.ui.painting import cached_layer
from lingfeng.ui.score_view import ScoreView

APP=QApplication.instance() or QApplication([])


class LayerWidget(QWidget):
    def __init__(self):
        super().__init__();self.revision=0;self.ink=QColor('red')

    def paintEvent(self,event):
        painter=QPainter(self)
        try:cached_layer(self,painter,self.revision,lambda p:p.fillRect(self.rect(),self.ink))
        finally:painter.end()


class RasterMemoryTests(unittest.TestCase):
    def test_same_size_repaints_reuse_storage_and_update_pixels(self):
        widget=LayerWidget();self.addCleanup(widget.close)
        widget.resize(640,400);widget.show();APP.processEvents()
        first=widget.layer_pixmap;allocations=widget.layer_allocations
        for revision in range(1,12):
            widget.revision=revision;widget.ink=QColor('blue' if revision%2 else 'red');widget.repaint()
            self.assertIs(widget.layer_pixmap,first)
            self.assertEqual(widget.layer_pixmap.toImage().pixelColor(30,30),widget.ink)
        self.assertEqual(widget.layer_allocations,allocations)
        renders=widget.cache_renders;widget.repaint();self.assertEqual(widget.cache_renders,renders)

    def test_resize_allocates_only_for_new_dimensions_and_hidden_surface_releases(self):
        widget=LayerWidget();self.addCleanup(widget.close)
        widget.resize(640,400);widget.show();APP.processEvents()
        allocations=widget.layer_allocations
        widget.resize(800,500);APP.processEvents()
        self.assertEqual(widget.layer_allocations,allocations+1)
        self.assertEqual(widget.layer_pixmap.width(),round(widget.width()*widget.devicePixelRatioF()))
        widget.hide();APP.processEvents()
        self.assertIsNone(widget.layer_pixmap);self.assertIsNone(widget.layer_key)
        widget.show();APP.processEvents()
        self.assertEqual(widget.layer_pixmap.toImage().pixelColor(30,30),widget.ink)
        self.assertEqual(widget.layer_allocations,allocations+2)

    def score(self):
        project=Project(measures=[Measure() for _ in range(64)])
        project.contexts=[Context(0,project.end)]
        project.notes=[Note(i*3840,480,60+i%5) for i in range(64)]
        project.notation.update(style='spatial',per_line=2)
        view=ScoreView(project);self.addCleanup(view.close)
        view.resize(900,700);view.show();view.set_zoom(2);APP.processEvents()
        return project,view

    def test_score_page_budget_evicts_old_rasters_and_rebuilds_correct_hits(self):
        project,view=self.score();canvas=view.canvas;before=project.to_dict()
        self.assertGreater(canvas.layout.pages,3)
        canvas.cache_budget_bytes=1024*1024
        for bar in (0,20,40,0,20,0):
            self.assertTrue(view.locate_bar(bar));APP.processEvents();view.viewport().repaint()
            self.assertLessEqual(len(canvas.page_cache),1)
            self.assertTrue(any(item[2]==bar for item in canvas.layout.hit_times))
            keys=[(item[0],item[2]) for item in canvas.layout.hit_times]
            self.assertEqual(len(keys),len(set(keys)))
            largest=max((p.width()*p.height()*max(1,p.depth()//8) for p,_ in canvas.page_cache.values()),default=0)
            self.assertLessEqual(canvas.page_cache_bytes,max(canvas.cache_budget_bytes,largest))
        self.assertEqual(project.to_dict(),before)

    def test_hidden_score_releases_rasters_without_discarding_music_or_layout(self):
        project,view=self.score();canvas=view.canvas
        self.assertTrue(canvas.page_cache);layout=canvas.layout;snapshot=canvas.project.to_dict()
        count=canvas.cache_renders
        view.hide();APP.processEvents()
        self.assertEqual(canvas.page_cache_bytes,0);self.assertIs(canvas.layout,layout)
        self.assertEqual(canvas.project.to_dict(),snapshot);self.assertEqual(canvas.cache_renders,count)
        view.show();APP.processEvents();view.viewport().repaint()
        self.assertTrue(canvas.page_cache);self.assertGreater(canvas.cache_renders,count)
        self.assertEqual(canvas.project.to_dict(),snapshot)


if __name__=='__main__':unittest.main()
