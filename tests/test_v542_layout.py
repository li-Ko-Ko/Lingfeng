"""True font budgets and original-source triplet groups in all score styles."""
import copy
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPointF,QRectF,Qt
from PySide6.QtGui import QFontMetrics,QImage,QPainter,QPainterPath,QPainterPathStroker
from PySide6.QtTest import QSignalSpy,QTest
from PySide6.QtWidgets import QApplication
from lingfeng.audio.midi import event_list,export_midi
from lingfeng.engraving.notation import ScoreLayout,export_pdf,fragment_style,PAPER_W,PAPER_H,MARGIN
from lingfeng.engraving.presentation import apply_forced_row
from lingfeng.music.model import Chord,Context,Measure,Note,PPQ,Project
from lingfeng.ui.score_view import ScoreView

APP=QApplication.instance() or QApplication([])
STYLES=('traditional','spatial','compact')


def song(notes=(),bars=1,style='traditional',size=15,per_line=4):
    p=Project(measures=[Measure()for _ in range(bars)]);p.contexts=[Context(0,p.end,48)]
    p.notes=list(notes);p.chords=[]
    p.notation.update(style=style,font_size=size,per_line=per_line,circles=False,lyrics=False)
    return p


class InkPainter(QPainter):
    """Record un-clipped vector ink after every real painter transformation."""
    def __init__(self,device):super().__init__(device);self.ink=[];self.rows=[]
    def record(self,path,kind,filled=False,**details):
        center=self.worldTransform().map(path);ink=QPainterPath()
        if filled or self.brush().style()!=Qt.BrushStyle.NoBrush:ink.addPath(path)
        if not filled and self.pen().style()!=Qt.PenStyle.NoPen:
            stroker=QPainterPathStroker();stroker.setWidth(self.pen().widthF()or 1);ink.addPath(stroker.createStroke(path))
        if ink.isEmpty():return
        self.ink.append(dict(kind=kind,path=self.worldTransform().map(ink),center_path=center,
            base_bounds=ink.boundingRect(),color=self.pen().color().name(),**details))
    def drawText(self,*args):
        if len(args)==2 and isinstance(args[0],QPointF):
            point,text=args;path=QPainterPath();path.addText(point,self.font(),text)
            center=QPointF(point.x()+QFontMetrics(self.font()).horizontalAdvance(text)/2,point.y())
            self.record(path,'text',True,text=text,pixels=self.font().pixelSize(),center=self.worldTransform().map(center))
        return super().drawText(*args)
    def drawEllipse(self,*args):
        if len(args)==3 and isinstance(args[0],QPointF):
            point,rx,ry=args;path=QPainterPath();path.addEllipse(point,rx,ry)
            self.record(path,'ellipse',rx=rx,ry=ry,center=self.worldTransform().map(point))
        return super().drawEllipse(*args)
    def drawLine(self,*args):
        if len(args)==2 and all(isinstance(p,QPointF)for p in args):
            path=QPainterPath(args[0]);path.lineTo(args[1])
            self.record(path,'line',points=tuple(self.worldTransform().map(p)for p in args))
        return super().drawLine(*args)
    def drawPath(self,path):self.record(path,'path');return super().drawPath(path)


def paint(layout,play_tick=None):
    pages=[];original=layout.draw_system
    def row(painter,system,tick=None):
        begin=len(painter.ink);marks=len(layout.tuplet_marks);ties=len(layout.tie_paths)
        original(painter,system,tick)
        painter.rows.append(dict(system=system,ink=painter.ink[begin:],
            marks=list(layout.tuplet_marks[marks:]),ties=list(layout.tie_paths[ties:])))
    layout.draw_system=row
    try:
        for page in range(layout.pages):
            image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);image.fill(0xffffffff);painter=InkPainter(image)
            try:layout.draw(painter,page,play_tick);pages.append(dict(page=page,rows=painter.rows,ink=painter.ink))
            finally:painter.end()
    finally:layout.draw_system=original
    return pages


def close_rect(a,b,tolerance=1e-5):
    return all(abs(x-y)<tolerance for x,y in zip((a.x(),a.y(),a.width(),a.height()),(b.x(),b.y(),b.width(),b.height())))


class PageFitTests(unittest.TestCase):
    def dense(self,style='traditional',size=72):
        p=song(bars=8,style=style,size=size)
        p.notes=[Note(t,480,48)for t in range(0,p.end,480)];p.chords=[Chord(0,p.end,48)]
        p.notation['circles']=True;apply_forced_row(p,list(range(6)));return p

    def test_requested_and_forced_fonts_are_real_and_recommendation_fits_without_row_scaling(self):
        for style in STYLES:
            with self.subTest(style=style):
                p=self.dense(style);before=copy.deepcopy(p.to_dict());layout=ScoreLayout(p);pages=paint(layout)
                self.assertEqual((PAPER_W,PAPER_H),(900,1273));self.assertEqual(layout.systems[0].bars,list(range(6)))
                self.assertEqual(layout.font_size,72);self.assertAlmostEqual(layout.glyph_scale,72/15)
                self.assertTrue(all(s.layout_scale==1 for s in layout.systems))
                self.assertEqual({s.page for s in layout.systems},set(range(layout.pages)))
                for system in layout.systems:
                    if style=='traditional':self.assertAlmostEqual(system.cell_width,20.95*72/15*system.font_ratio)
                circles=[]
                for page in pages:
                    for item in page['ink']:
                        if item['kind']=='ellipse'and item['rx']!=item['ry']:circles.append(item)
                self.assertTrue(circles)
                for circle in circles:
                    physical=circle['path'].boundingRect();natural=circle['base_bounds']
                    self.assertAlmostEqual(physical.width()/natural.width(),physical.height()/natural.height())
                self.assertEqual(p.to_dict(),before)
                if style=='traditional':
                    p.notation['font_size']=layout.recommended_font_size;recommended=ScoreLayout(p)
                    self.assertTrue(all(s.layout_scale==1 for s in recommended.systems))
                    for page in paint(recommended):
                        for item in page['ink']:
                            box=item['path'].boundingRect()
                            self.assertGreaterEqual(box.left(),-.01);self.assertLessEqual(box.right(),PAPER_W+.01)
                            self.assertGreaterEqual(box.top(),-.01);self.assertLessEqual(box.bottom(),PAPER_H+.01)

    def test_sparse_and_dense_normal_rows_keep_one_true_font_without_whole_row_scaling(self):
        p=song(bars=5);p.notes=[Note(t,960,48)for t in range(0,3840,960)]
        p.notes += [Note(t,120,48)for t in range(3840,p.end,120)];p.measures[0].break_after=True
        layout=ScoreLayout(p);paint(layout)
        self.assertEqual(layout.systems[0].layout_scale,1)
        self.assertTrue(all(s.layout_scale==1 for s in layout.systems[1:]))
        self.assertEqual(len({s.cell_width for s in layout.systems}),1)
        self.assertGreater(sum(layout.systems[1].bar_widths),PAPER_W-2*MARGIN)
        p.notation['font_size']=layout.recommended_font_size;recommended=ScoreLayout(p)
        for s in recommended.systems:self.assertAlmostEqual(sum(s.bar_widths),PAPER_W-2*MARGIN)

    def test_recommended_font_playhead_hit_map_and_viewport_click_follow_one_position(self):
        p=self.dense();p.notation['font_size']=ScoreLayout(p).recommended_font_size
        view=ScoreView(p);view.resize(1000,650);view.show();view.set_zoom(4)
        try:
            APP.processEvents();canvas=view.canvas;canvas.grid=120;target=5*3840+480;layout=canvas.layout
            pages=paint(layout,target);page,x,top,bottom=layout.time_position(target)
            red=[i for data in pages for i in data['ink']if i['kind']=='line'and i['color']=='#d15f49']
            self.assertEqual(len(red),1);a,b=red[0]['points']
            self.assertAlmostEqual(a.x(),x);self.assertAlmostEqual(b.x(),x)
            self.assertAlmostEqual(a.y(),top);self.assertAlmostEqual(b.y(),bottom)
            hit=next(h for h in layout.hit_times if h[2]==p.measure_at(target))
            self.assertAlmostEqual(layout.interpolate(hit[3],hit[4],target),x)
            view.locate_tick(target);APP.processEvents();self.assertTrue(view.bar_visible(target))
            ox,oy=canvas.page_origin(page);point=QPointF(ox+x*canvas.scale,oy+(top+bottom)/2*canvas.scale)
            self.assertEqual(canvas.timeline_at(point),(5,target))
            spy=QSignalSpy(canvas.playheadChanged);QTest.mouseClick(canvas,Qt.MouseButton.LeftButton,pos=point.toPoint())
            self.assertEqual(spy.count(),1);self.assertEqual(spy.at(0),[target])
        finally:view.close();view.deleteLater();APP.processEvents()


class TupletGroupTests(unittest.TestCase):
    def assert_above_ink(self,layout,pages):
        groups={g['id']:g for g in layout.tuplet_groups};marks=[]
        for page in pages:
            for row in page['rows']:
                system=row['system'];fragments=[f for bar in system.bars for f in system.fragments[bar]]
                digits=[i for i in row['ink']if i['kind']=='text'and i['pixels']==18 and i['text']in tuple('01234567x')]
                self.assertEqual(len(digits),len(fragments))
                for mark in row['marks']:
                    marks.append(mark);group=groups[mark['group_id']];ids=set(group['source_ids'])
                    members=[digit for f,digit in zip(fragments,digits)if
                        (f.note is not None and f.note.id in ids)or(f.note is None and any(u['rest']and u['start']<=f.start and f.end<=u['end']for u in group['units']))]
                    self.assertTrue(members);ink=[m['path']for m in members]
                    centers=[m['center'].x()for m in members]
                    ink += [i['path']for i in row['ink']if i['kind']=='ellipse'and any(abs(i['center'].x()-x)<1e-5 for x in centers)]
                    for ident,_,tie in row['ties']:
                        if ident in ids:
                            matching=[i['path']for i in row['ink']if i['kind']=='path'and close_rect(i['center_path'].boundingRect(),tie.boundingRect())]
                            self.assertTrue(matching);ink.extend(matching)
                    lines=[i for i in row['ink']if i['kind']=='line'and
                        all(abs(point.y()-mark['top'])<1e-5 for point in i['points'])and
                        abs(i['points'][0].x()-mark['left'])<1e-5 and abs(i['points'][1].x()-mark['right'])<1e-5]
                    self.assertEqual(len(lines),1);self.assertGreater(mark['right'],mark['left'])
                    tips=[i for i in row['ink']if i['kind']=='line'and abs(i['points'][0].y()-mark['top'])<1e-5 and
                        any(abs(i['points'][0].x()-x)<1e-5 for x in (mark['left'],mark['right']))]
                    labels=[i for i in row['ink']if i['kind']=='text'and i['pixels']==11 and i['text']=='3'and
                        abs(i['center'].x()-(mark['left']+mark['right'])/2)<1e-5]
                    self.assertTrue(labels);label=min(labels,key=lambda i:abs(i['center'].y()-mark['top']))
                    bracket_bottom=max([label['path'].boundingRect().bottom(),*[i['path'].boundingRect().bottom()for i in tips]])
                    self.assertLess(bracket_bottom,min(path.boundingRect().top()for path in ink))
        return marks

    def test_real_160_and_320_groups_are_flat_above_each_groups_highest_note_and_octave_dots(self):
        notes=[Note(0,160,48),Note(160,160,108),Note(320,160,60),
               Note(960,320,84),Note(1280,320,48),Note(1600,320,96)]
        for style in STYLES:
            with self.subTest(style=style):
                p=song(copy.deepcopy(notes),style=style);layout=ScoreLayout(p);pages=paint(layout)
                self.assertEqual([(g['start'],g['end'],g['duration'])for g in layout.tuplet_groups],[(0,480,160),(960,1920,320)])
                self.assertTrue(all(g['complete']and len(g['units'])==3 for g in layout.tuplet_groups))
                self.assertEqual(len(self.assert_above_ink(layout,pages)),2)

    def test_beat_split_source_keeps_one_logical_group_above_the_real_tie(self):
        for style in STYLES:
            for duration,starts in ((320,(800,960,1120,1440)),(640,(800,960,1440,1920,2080))):
                with self.subTest(style=style,duration=duration):
                    p=song([Note(800+i*duration,duration,pitch)for i,pitch in enumerate((96,48,72))],style=style)
                    layout=ScoreLayout(p);pages=paint(layout);self.assertEqual(len(layout.tuplet_groups),1)
                    group=layout.tuplet_groups[0];self.assertEqual((group['start'],group['end']),(800,800+3*duration))
                    self.assertEqual(set(group['source_ids']),{n.id for n in p.notes})
                    marks=self.assert_above_ink(layout,pages);self.assertEqual(len(marks),1)
                    self.assertEqual(marks[0]['fragment_starts'],starts)
                    self.assertTrue(any(ident==p.notes[0].id for data in pages for row in data['rows']for ident,_,_ in row['ties']))

    def test_one_explicit_rest_still_completes_three_positions(self):
        for style in STYLES:
            for duration in (160,320):
                with self.subTest(style=style,duration=duration):
                    p=song([Note(0,duration,96),Note(2*duration,duration,48)],style=style)
                    layout=ScoreLayout(p);pages=paint(layout);self.assertEqual(len(layout.tuplet_groups),1)
                    group=layout.tuplet_groups[0];self.assertTrue(group['complete'])
                    self.assertEqual([u['rest']for u in group['units']],[False,True,False])
                    self.assertEqual(len(self.assert_above_ink(layout,pages)),1)

    def test_non_triplet_sources_do_not_acquire_fake_threes_from_80_or_160_fragments(self):
        for style in STYLES:
            for start,duration,context_split in ((800,480,False),(800,720,False),(0,960,True)):
                with self.subTest(style=style,start=start,duration=duration):
                    p=song([Note(start,duration,48)],style=style)
                    if context_split:p.contexts=[Context(0,160,48),Context(160,p.end,48)]
                    layout=ScoreLayout(p);pages=paint(layout)
                    self.assertTrue(any(fragment_style(f)[2]for s in layout.systems for fs in s.fragments.values()for f in fs if f.note))
                    self.assertEqual(layout.tuplet_groups,[])
                    self.assertFalse(any(row['marks']for page in pages for row in page['rows']))

    def test_crossbar_group_is_one_mark_on_one_row_and_one_per_visible_row_across_pages(self):
        for style in STYLES:
            with self.subTest(style=style):
                p=song([Note(t,320,48)for t in (3520,3840,4160)],bars=2,style=style)
                layout=ScoreLayout(p);pages=paint(layout);marks=self.assert_above_ink(layout,pages)
                self.assertEqual(len(layout.tuplet_groups),1);self.assertEqual(len(marks),1)
                p=song([Note(bar*3840+offset,320,48)for bar in range(1,20)for offset in (-320,0,320)],
                    bars=20,style=style,size=26,per_line=1)
                layout=ScoreLayout(p);pages=paint(layout);marks=self.assert_above_ink(layout,pages)
                self.assertEqual(len(layout.tuplet_groups),19);self.assertGreater(layout.pages,1)
                self.assertEqual(len(marks),38)
                self.assertTrue(any(len({m['page']for m in marks if m['group_id']==g['id']})>1 for g in layout.tuplet_groups))

    def test_screen_pdf_and_paper_fitting_preserve_original_events_ids_and_manual_font(self):
        for style in STYLES:
            with self.subTest(style=style):
                p=song([Note(800,320,96),Note(1120,320,48),Note(1440,320,72)],bars=2,style=style,size=72)
                before=copy.deepcopy(p.to_dict());events=event_list(p);midi=export_midi(p,None)
                layout=ScoreLayout(p);paint(layout)
                with tempfile.TemporaryDirectory(dir='tmp')as folder:
                    path=Path(folder)/'fitted-tuplets.pdf';self.assertGreater(export_pdf(p,path),0)
                    self.assertTrue(path.read_bytes().startswith(b'%PDF'))
                self.assertEqual(p.to_dict(),before);self.assertEqual(event_list(p),events);self.assertEqual(export_midi(p,None),midi)


if __name__=='__main__':unittest.main()
