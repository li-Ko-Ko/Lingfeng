"""Score pointer queries reuse page geometry and static score pixels."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Chord, Note, Project
from lingfeng.ui.score_view import ScoreCanvas, ScoreView

APP=QApplication.instance() or QApplication([])


def song():
    p=Project();p.notation['per_line']=1
    p.notes=[Note(start+tick,480,60+index%5) for index,start in enumerate(p.starts[:-1]) for tick in (0,960,1920)]
    p.chords=[Chord(start,3840) for start in p.starts[:-1]]
    return p


class ScoreSelectionTests(unittest.TestCase):
    def test_marquee_matches_intersections_on_multiple_pages(self):
        canvas=ScoreCanvas(song());self.addCleanup(canvas.close)
        layout=canvas.layout
        image=QImage(1,1,QImage.Format.Format_ARGB32);painter=QPainter(image)
        try:
            for page in range(layout.pages):layout.draw(painter,page)
        finally:painter.end()
        self.assertGreater(layout.pages,1)
        canvas.resize_content();canvas.resize(canvas.minimumSize());canvas.index_layout()
        for unit in ('measure','beat','note'):
            with self.subTest(unit=unit):
                canvas.set_selection_unit(unit)
                canvas.press_pos=QPointF(240,150);canvas.marquee=None
                canvas.selection_before=set()
                end=QPointF(450,canvas.page_origin(1)[1]+240)
                canvas.update_marquee(end,Qt.KeyboardModifier.NoModifier)
                expected=set()
                for page,rect,key in canvas.selection_rects():
                    x,y=canvas.page_origin(page);scale=canvas.scale
                    screen=QRectF(x+rect.x()*scale,y+rect.y()*scale,rect.width()*scale,rect.height()*scale)
                    if screen.intersects(canvas.marquee):expected.add(key)
                self.assertEqual(canvas.selected_units(),expected)

    def test_selection_reuses_raster_and_raster_recrop_reuses_hits(self):
        view=ScoreView(song());self.addCleanup(view.close);view.resize(760,530);view.show();APP.processEvents()
        canvas=view.canvas;view.viewport().grab();original=canvas.cache_renders
        indexed=canvas.hit_pages[0]
        first_note=canvas.layout.hit_notes[0]
        canvas.set_selection_unit('note');canvas.select_all();view.viewport().grab()
        self.assertEqual(canvas.cache_renders,original)
        view.set_zoom(canvas.scale*1.1);view.viewport().grab()
        self.assertGreater(canvas.cache_renders,original)
        self.assertIs(canvas.hit_pages[0],indexed)
        self.assertIs(canvas.layout.hit_notes[0],first_note)
        self.assertEqual(len(canvas.layout.hit_notes),sum(len(hits.items['note']) for hits in canvas.hit_pages.values()))

    def test_repeated_chord_hover_and_snap_use_cached_queries(self):
        canvas=ScoreCanvas(song());self.addCleanup(canvas.close)
        canvas.resize(900,1040);canvas.show();canvas.grab()
        page,rect,_=canvas.layout.hit_chords[0];x,y=canvas.page_origin(page)
        pos=QPointF(x+rect.center().x()*canvas.scale,y+rect.center().y()*canvas.scale)
        from lingfeng.music.timing import grid_points
        with patch('lingfeng.music.timing.grid_points',wraps=grid_points) as points:
            expected=canvas.timeline_at(pos)
            self.assertIsNotNone(expected)
            for _ in range(12):self.assertEqual(canvas.timeline_at(pos),expected)
            self.assertEqual(points.call_count,1)
        from lingfeng.ui.score_view import chord_details
        with patch('lingfeng.ui.score_view.chord_details',wraps=chord_details) as details:
            QTest.mouseMove(canvas,pos.toPoint());QTest.mouseMove(canvas,pos.toPoint()+QPoint(1,0))
            self.assertEqual(details.call_count,1)

    def test_selection_signal_is_emitted_only_for_a_new_selection(self):
        canvas=ScoreCanvas(song());self.addCleanup(canvas.close)
        canvas.resize(900,1040);canvas.show();canvas.grab()
        spy=QSignalSpy(canvas.selectionChanged)
        canvas.select_all();canvas.select_all()
        self.assertEqual(spy.count(),1)
        QTest.keyClick(canvas,Qt.Key.Key_Escape);QTest.keyClick(canvas,Qt.Key.Key_Escape)
        self.assertEqual(spy.count(),2)


if __name__=='__main__':unittest.main()
