"""Initially closed score tabs and display-only multi-note phrase annotations."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage,QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from lingfeng.audio.midi import export_midi
from lingfeng.engraving.presentation import add_slur,validate_presentation
from lingfeng.engraving.notation import ScoreLayout,export_pdf,PAPER_W,PAPER_H
from lingfeng.engraving.lyrics import apply_range
from lingfeng.music.model import Project,Note,Measure,Context
from lingfeng.ui.main_window import MainWindow

APP=QApplication.instance() or QApplication([])


def song(bars=4):
    p=Project(measures=[Measure() for _ in range(bars)],contexts=[Context(0,bars*3840)])
    p.notes=[Note(bar*3840+tick,480,60+((bar+tick//480)%7)) for bar in range(bars) for tick in (0,480,960)]
    p.notation.update(per_line=1,font_size=13,lyrics=False,circles=False)
    return p


def render(layout,page=0):
    image=QImage(int(PAPER_W),int(PAPER_H),QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.white)
    painter=QPainter(image);layout.draw(painter,page);painter.end();return image


class SlurTests(unittest.TestCase):
    def test_single_annotation_spans_whole_selection_without_changing_midi(self):
        p=song();before=copy.deepcopy(p.notes);midi=export_midi(p,None)
        ids=[n.id for n in p.notes[:6]]
        add_slur(p,reversed(ids));add_slur(p,ids)
        self.assertEqual(len(p.notation['symbols']),1)
        self.assertEqual(p.notation['symbols'][0]['note_ids'],ids)
        self.assertEqual(p.notes,before);self.assertEqual(export_midi(p,None),midi);p.validate()
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            file=Path(folder)/'phrase.lfs';p.save(file);q=Project.load(file)
            self.assertEqual(q.notation['symbols'],p.notation['symbols']);self.assertEqual(export_midi(q,None),midi)

    def test_invalid_or_duplicate_anchors_are_rejected(self):
        p=song()
        with self.assertRaises(ValueError):add_slur(p,[p.notes[0].id])
        add_slur(p,[n.id for n in p.notes[:3]])
        p.notation['symbols'][0]['note_ids']=[p.notes[0].id,p.notes[0].id]
        with self.assertRaises(ValueError):validate_presentation(p)

    def test_all_styles_have_outgoing_through_incoming_arcs_and_hit_targets(self):
        for style in ('traditional','spatial','compact'):
            with self.subTest(style=style):
                p=song();p.notation['style']=style;add_slur(p,[p.notes[0].id,p.notes[-1].id]);before=p.to_dict()
                layout=ScoreLayout(p);render(layout)
                self.assertEqual([kind for _,kind,_ in layout.manual_slur_paths],['outgoing','through','through','incoming'])
                self.assertEqual(len([h for h in layout.hit_symbols if h[2]==('symbols',0)]),4)
                for _,_,path in layout.manual_slur_paths:
                    self.assertGreater(path.boundingRect().width(),0);self.assertGreaterEqual(path.boundingRect().top(),0)
                self.assertEqual(p.to_dict(),before)

    def test_long_phrase_crosses_pages_and_pdf_keeps_midi(self):
        p=song(16);add_slur(p,[p.notes[0].id,p.notes[-1].id]);midi=export_midi(p,None);layout=ScoreLayout(p)
        self.assertGreater(layout.pages,1);kinds=[]
        for page in range(layout.pages):
            render(layout,page);kinds.extend(kind for _,kind,_ in layout.manual_slur_paths)
        self.assertEqual(kinds[0],'outgoing');self.assertEqual(kinds[-1],'incoming');self.assertIn('through',kinds)
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            target=Path(folder)/'phrase.pdf';self.assertEqual(export_pdf(p,target),layout.pages);self.assertGreater(target.stat().st_size,1000)
        self.assertEqual(export_midi(p,None),midi)

    def test_existing_lyric_melismas_remain_independent_and_deleted_anchors_are_inactive(self):
        from lingfeng.engraving.lyrics import delete_range
        p=song(1);p.notation['lyrics']=True;add_slur(p,[n.id for n in p.notes])
        original=copy.deepcopy(p.notation['symbols']);apply_range(p,'春/-/-',0,1,replace=True)
        layout=ScoreLayout(p);render(layout)
        self.assertTrue(layout.melisma_paths);self.assertFalse(layout.manual_slur_paths)
        self.assertEqual(p.notation['symbols'],original)
        delete_range(p,0,1);layout=ScoreLayout(p);render(layout)
        self.assertFalse(layout.melisma_paths);self.assertEqual(len(layout.manual_slur_paths),1)
        p.notes=p.notes[:1];p.validate();layout=ScoreLayout(p);render(layout);self.assertFalse(layout.manual_slur_paths)


class ScorePanelTests(unittest.TestCase):
    def setUp(self):
        self.save=patch.object(MainWindow,'save_preferences');self.save.start();self.addCleanup(self.save.stop)
        self.w=MainWindow(song());self.w.timer.stop();self.w.autosave.stop();self.w.change_language('zh',False)
        self.w.show();APP.processEvents();self.addCleanup(self.close)

    def close(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents()

    def test_first_entry_hides_all_four_then_preserves_independent_visibility_and_floating(self):
        w=self.w;w.switch_workspace('score')
        self.assertEqual(set(w.score_pages),{'melody','harmony','lyrics','annotations'})
        self.assertEqual(w.score_tabs.count(),0);self.assertFalse(w.score_tools.isVisible())
        self.assertTrue(all(not state['visible'] for state in w.score_panel_state.values()))
        w.show_score_panel('annotations');w.show_score_panel('melody');w.toggle_score_panel_floating('annotations')
        state=copy.deepcopy(w.score_panel_state);w.switch_workspace('compose');w.switch_workspace('score');APP.processEvents()
        self.assertEqual(w.score_panel_state,state);self.assertEqual(w.score_tabs.count(),1)
        self.assertTrue(w.score_floats['annotations'].isVisible())
        w.change_language('en',False);APP.processEvents();self.assertEqual(w.score_panel_state,state)

    def test_panel_add_remove_undo_redo_do_not_change_music(self):
        w=self.w;w.switch_workspace('score');w.show_score_panel('annotations');panel=w.annotation_panel;canvas=w.score_view.canvas
        before=export_midi(w.project,None);canvas.set_selection_unit('note');canvas.selected_notes={n.id for n in w.project.notes[:3]}
        panel.kind.setCurrentIndex(panel.kind.findData('slur'));panel.refresh();self.assertTrue(panel.add_button.isEnabled());panel.add()
        self.assertEqual(len(w.project.notation['symbols']),1);self.assertEqual(export_midi(w.project,None),before)
        w.undo();self.assertFalse(w.project.notation.get('symbols'));w.redo();self.assertEqual(len(w.project.notation['symbols']),1)
        panel.items.setCurrentRow(0);panel.remove();self.assertFalse(w.project.notation['symbols']);w.undo()
        self.assertEqual(len(w.project.notation['symbols']),1);self.assertEqual(export_midi(w.project,None),before)

    def test_multi_note_shift_selection_and_context_delete_use_same_annotation(self):
        w=self.w;w.switch_workspace('score');canvas=w.score_view.canvas;canvas.set_selection_unit('note');canvas.grab();APP.processEvents()
        def position(note):
            page,rect,_=next(hit for hit in canvas.layout.hit_notes if hit[2]==note.id)
            x,y=canvas.page_origin(page);return QPoint(round(x+rect.center().x()*canvas.scale),round(y+rect.center().y()*canvas.scale))
        first,last=w.project.notes[:3][::2]
        QTest.mouseClick(canvas,Qt.MouseButton.LeftButton,pos=position(first))
        QTest.mouseClick(canvas,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier,pos=position(last))
        self.assertEqual(canvas.selected_notes,{n.id for n in w.project.notes[:3]})
        payload=dict(bars=[],ranges=[],note_ids=list(canvas.selected_notes));w.score_command('slur',payload);canvas.grab()
        page,rect,key=next(hit for hit in canvas.layout.hit_symbols if hit[2]==('symbols',0));x,y=canvas.page_origin(page)
        menu=canvas.context_menu(QPoint(round(x+rect.center().x()*canvas.scale),round(y+rect.center().y()*canvas.scale)))
        action=next(a for a in menu.actions() if a.text()=='删除此标识');action.trigger()
        self.assertFalse(w.project.notation['symbols'])

    def test_panel_adds_display_only_regular_symbol(self):
        w=self.w;w.switch_workspace('score');w.show_score_panel('annotations');canvas=w.score_view.canvas
        canvas.selected_bars={0};panel=w.annotation_panel;panel.kind.setCurrentIndex(panel.kind.findData('rit'));panel.refresh()
        before=export_midi(w.project,None);self.assertTrue(panel.add_button.isEnabled());panel.add()
        self.assertEqual(w.project.notation['symbols'][0]['kind'],'rit');self.assertEqual(export_midi(w.project,None),before)


if __name__=='__main__':unittest.main()
