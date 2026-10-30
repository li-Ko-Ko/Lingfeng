"""Descending row-entry continuation, preserving full in-row tie arches."""
import copy,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QPainterPath
from lingfeng.music.model import Project, Note, demo_project
from lingfeng.engraving.notation import ScoreLayout, export_pdf, PAPER_W, PAPER_H
from lingfeng.engraving.presentation import apply_forced_row
from lingfeng.audio.midi import export_midi

APP=QApplication.instance() or QApplication([])

def render(p,page=0,dark=False):
    layout=ScoreLayout(p);im=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);im.fill(0xffffffff)
    painter=QPainter(im);layout.draw(painter,page,dark=dark);painter.end();return layout

class EntryTieTests(unittest.TestCase):
    def assertDescendingLine(self,path):
        self.assertEqual(path.elementCount(),4)
        self.assertEqual(path.elementAt(1).type,QPainterPath.ElementType.CurveToElement)
        a,b=path.pointAtPercent(0),path.pointAtPercent(1)
        self.assertGreater(b.x(),a.x());self.assertGreater(b.y(),a.y())
        points=[path.pointAtPercent(i/20) for i in range(21)]
        self.assertTrue(all(q.x()>p.x() and q.y()>=p.y() for p,q in zip(points,points[1:])))
        middle=path.pointAtPercent(.5)
        self.assertLess(middle.y(),a.y()+(b.y()-a.y())*(middle.x()-a.x())/(b.x()-a.x()))

    def test_demo_row_entry_descends_in_every_style_and_theme(self):
        for style in ('traditional','spatial','compact'):
            for dark in (False,True):
                p=demo_project();p.notation.update(style=style,per_line=4,font_size=12)
                incoming=[path for _,kind,path in render(p,dark=dark).tie_paths if kind=='incoming']
                self.assertTrue(incoming)
                for path in incoming:self.assertDescendingLine(path)

    def test_tiny_and_large_fonts_do_not_reverse_the_entry_line(self):
        for style in ('traditional','spatial','compact'):
            for size in (.1,1,4,12,26):
                p=Project();p.notation.update(style=style,per_line=4,font_size=size)
                p.notes=[Note(15120,480,60)]
                paths=[path for _,kind,path in render(p).tie_paths if kind=='incoming']
                self.assertEqual(len(paths),1);self.assertDescendingLine(paths[0])

    def test_full_same_row_tie_and_outgoing_arch_are_preserved(self):
        p=Project();p.notes=[Note(3600,480,60),Note(15120,480,67)]
        for style in ('traditional','spatial','compact'):
            p.notation['style']=style;layout=render(p)
            self.assertEqual([kind for _,kind,_ in layout.tie_paths],['continuous','outgoing','incoming'])
            for _,kind,path in layout.tie_paths:
                if kind=='incoming':continue
                self.assertEqual(path.elementCount(),4)
                self.assertEqual(path.elementAt(1).type,QPainterPath.ElementType.CurveToElement)
                self.assertLess(path.pointAtPercent(.5).y(),min(path.pointAtPercent(0).y(),path.pointAtPercent(1).y()))

    def test_page_and_forced_row_entries_remain_paired(self):
        p=Project();p.notation.update(per_line=2,row_gap=32)
        p.notes=[Note(i*3840,240,21 if i%2==0 else 108) for i in range(len(p.measures))]
        first=next(s for s in ScoreLayout(p).systems if s.page==1);tick=p.starts[first.bars[0]]
        sustain=Note(tick-120,240,60);p.notes.append(sustain)
        self.assertIn('outgoing',[kind for nid,kind,_ in render(p,0).tie_paths if nid==sustain.id])
        incoming=[path for nid,kind,path in render(p,1).tie_paths if nid==sustain.id and kind=='incoming']
        self.assertEqual(len(incoming),1);self.assertDescendingLine(incoming[0])
        q=Project();q.notes=[Note(6*3840-240,480,60)];apply_forced_row(q,list(range(6)))
        incoming=[path for _,kind,path in render(q).tie_paths if kind=='incoming']
        self.assertEqual(len(incoming),1);self.assertDescendingLine(incoming[0])

    def test_pdf_uses_the_same_descending_path_without_changing_midi(self):
        p=demo_project();before=copy.deepcopy(p.to_dict());midi=export_midi(p,None);seen=[];original=ScoreLayout.draw
        def record(layout,*args,**kwargs):
            original(layout,*args,**kwargs)
            seen.extend(path for _,kind,path in layout.tie_paths if kind=='incoming')
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            out=Path(folder)/'ties.pdf'
            with patch.object(ScoreLayout,'draw',record):self.assertGreater(export_pdf(p,out),0)
            self.assertTrue(out.read_bytes().startswith(b'%PDF'))
        self.assertTrue(seen)
        for path in seen:self.assertDescendingLine(path)
        self.assertEqual(p.to_dict(),before);self.assertEqual(export_midi(p,None),midi)

if __name__=='__main__':unittest.main()
