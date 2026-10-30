"""Raster checks for chord previews overlapping stationary neighbors."""
import copy,os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from lingfeng.ui.piano_roll import PianoRoll
from lingfeng.music.model import Project, Chord, PPQ
from lingfeng.ui.theme import apply_theme, color

APP=QApplication.instance() or QApplication([])

class ChordLayerTests(unittest.TestCase):
    def make_roll(self,role):
        p=Project();p.chords=[Chord(0,2*PPQ),Chord(2*PPQ,2*PPQ,57,'m'),Chord(4*PPQ,2*PPQ,55,'7')]
        r=PianoRoll(p,role=role);r.resize(900,500);r.zoom=100;r.update_ranges();r.lane.setFixedSize(900,62)
        self.addCleanup(r.deleteLater);return r

    def render(self,lane):
        image=QImage(lane.width(),lane.height(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(Qt.GlobalColor.transparent)
        painter=QPainter(image)
        try:lane.paint_content(painter)
        finally:painter.end()
        return image

    def assert_top(self,r,target,neighbors):
        lane=r.lane;before=r.project.to_dict();image=self.render(lane)
        for old in neighbors:
            a=max(old.start,target.start);b=min(old.end,target.end)
            if b-a<120:continue
            pos=QPointF(lane.x_at((a+b)/2),25)
            self.assertEqual(lane.chord_hit(pos)[1].id,target.id)
            # Removing a covered neighbor must not change the preview's interior:
            # its title, boundary and highlight may not bleed through the overlay.
            all_chords=r.project.chords
            try:
                r.project.chords=[c for c in all_chords if c.id!=old.id]
                reference=self.render(lane)
            finally:r.project.chords=all_chords
            left=round(lane.x_at(a))+5;right=round(lane.x_at(b))-5
            self.assertEqual(image.copy(left,9,right-left,44),reference.copy(left,9,right-left,44))
        self.assertEqual(r.project.to_dict(),before)

    def test_right_extension_covers_neighbor_in_both_roll_roles_and_themes(self):
        for dark in (False,True):
            apply_theme(dark)
            for role in ('melody','harmony'):
                with self.subTest(dark=dark,role=role):
                    r=self.make_roll(role);original=r.project.chords[0];target=copy.deepcopy(original);target.duration=3*PPQ
                    r.lane.preview=target;r.lane.previews={target.id:target};r.lane.drag_originals=[copy.deepcopy(original)];r.selected_chords={original.id}
                    self.assert_top(r,target,[r.project.chords[1]])

    def test_left_extension_and_copied_move_target_cover_left_neighbor(self):
        for action in ('left','move'):
            with self.subTest(action=action):
                r=self.make_roll('harmony');original=r.project.chords[1];target=copy.deepcopy(original);target.start=PPQ
                if action=='left':target.duration=3*PPQ
                r.lane.preview=target;r.lane.previews={target.id:target};r.lane.drag_originals=[copy.deepcopy(original)]
                r.selected_chords={original.id};self.assert_top(r,target,[r.project.chords[0]])

    def test_dragged_copy_covers_right_neighbor_and_hidden_text(self):
        r=self.make_roll('melody');original=r.project.chords[0];target=copy.deepcopy(original);target.start=2*PPQ
        r.lane.preview=target;r.lane.previews={target.id:target};r.lane.drag_originals=[copy.deepcopy(original)];r.selected_chords={original.id}
        self.assert_top(r,target,[r.project.chords[1]])

    def test_group_preview_is_above_all_stationary_cards_and_clears_cleanly(self):
        r=self.make_roll('harmony');originals=[r.project.chords[0],r.project.chords[2]];targets=copy.deepcopy(originals)
        for target in targets:target.start+=PPQ
        lane=r.lane;lane.preview=targets[0];lane.previews={c.id:c for c in targets};lane.drag_originals=copy.deepcopy(originals)
        self.render(lane);self.assertEqual([c.id for rect,c in lane.boxes][-2:],[c.id for c in targets])
        self.assert_top(r,targets[0],[r.project.chords[1]])
        lane.preview=None;lane.previews={};lane.drag_originals=[];self.render(lane)
        self.assertEqual([c.id for rect,c in lane.boxes],[c.id for c in r.project.chords])

    def test_neighbor_gutter_stays_clear_of_borders_and_ruler_at_multiple_dpi(self):
        for dark in (False,True):
            apply_theme(dark)
            for ratio in (1,1.25,1.5,2):
                for selected in (False,True):
                    with self.subTest(dark=dark,dpi=ratio,selected=selected):
                        r=self.make_roll('harmony');lane=r.lane
                        if selected:r.selected_chords={c.id for c in r.project.chords}
                        image=QImage(round(lane.width()*ratio),round(lane.height()*ratio),QImage.Format.Format_ARGB32_Premultiplied)
                        image.setDevicePixelRatio(ratio);painter=QPainter(image)
                        try:lane.paint_content(painter)
                        finally:painter.end()
                        for tick in (2*PPQ,4*PPQ):
                            x=int(lane.x_at(tick)*ratio)
                            for y in (6,12,30,50):self.assertEqual(image.pixelColor(x,round(y*ratio)),color('#FAFBFD'))

    def test_short_cards_and_hit_boxes_never_expand_into_neighbors(self):
        r=self.make_roll('melody');r.project.chords=[Chord(0,30),Chord(30,60),Chord(90,120)]
        for zoom in (24,31,78,333.5):
            r.zoom=zoom;self.render(r.lane)
            for rect,c in r.lane.boxes:
                self.assertGreater(rect.width(),0)
                self.assertGreaterEqual(rect.left(),r.lane.x_at(c.start));self.assertLessEqual(rect.right(),r.lane.x_at(c.end))
                self.assertEqual(r.lane.chord_hit(rect.center())[1].id,c.id)
            for (left,_),(right,_) in zip(r.lane.boxes,r.lane.boxes[1:]):self.assertLess(left.right(),right.left())

if __name__=='__main__':unittest.main()
