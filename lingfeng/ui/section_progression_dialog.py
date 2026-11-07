"""Preview the named chord progression in each project section."""
from bisect import bisect_left, bisect_right
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
                               QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from lingfeng.music.chord_operations import contextual_chord_name
from lingfeng.platform.i18n import tr


@dataclass(frozen=True)
class SectionProgression:
    name: str
    first_bar: int
    end_bar: int
    context_tick: int
    chord_ids: frozenset[str]
    names: str
    roman: str
    save_issue: str = ''


def section_progressions(project):
    sections=project.sections()
    if not sections or sections[0][1]>0:
        sections.insert(0,(tr('未标记段落'),0,sections[0][1] if sections else len(project.measures)))
    chords=sorted((chord for chord in project.chords if not chord.empty),key=lambda chord:chord.start)
    onsets=[chord.start for chord in chords];ends=[chord.end for chord in chords];starts=project.starts
    rows=[]
    for name,first,end in sections:
        a,b=starts[first],starts[end]
        active=chords[bisect_right(ends,a):bisect_left(onsets,b)]
        anchor=max(a,active[0].start) if active else a
        context=project.context_at(anchor)
        names=' – '.join(contextual_chord_name(project,chord,project.context_at(max(a,chord.start))) for chord in active)
        roman=' – '.join(chord.roman(context.tonic,chord.flat,context.mode) for chord in active)
        if not active or any(chord.display_symbol is None for chord in active):
            issue=tr('只有名称可识别的和弦可以加入和弦进行。')
        elif len(active)>128:
            issue=tr('和弦进行须包含 1–128 个罗马数字和弦。')
        else:issue=''
        rows.append(SectionProgression(name,first,end,anchor,frozenset(chord.id for chord in active),names,roman,issue))
    return rows


class SectionProgressionDialog(QDialog):
    def __init__(self,project,save_progression,parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('和弦进行预览'))
        self.resize(770,490)
        self.jump_bar=None
        self.rows=section_progressions(project)
        layout=QVBoxLayout(self)
        scroll=QScrollArea();scroll.setWidgetResizable(True);layout.addWidget(scroll,1)
        content=QWidget();cards=QVBoxLayout(content);scroll.setWidget(content)
        for row in self.rows:
            card=QFrame();card.setObjectName('editorCard');cards.addWidget(card)
            body=QVBoxLayout(card);header=QHBoxLayout();body.addLayout(header)
            title=QLabel(row.name);title.setTextFormat(Qt.TextFormat.PlainText);title.setWordWrap(True)
            font=title.font();font.setBold(True);title.setFont(font)
            header.addWidget(title,1)
            interval_text=(tr('第 {0} 小节',row.end_bar) if row.first_bar+1==row.end_bar
                           else tr('第 {0}–{1} 小节',row.first_bar+1,row.end_bar))
            interval=QLabel(interval_text);interval.setObjectName('subtitle');header.addWidget(interval)
            save=QPushButton(tr('加入和弦进行库'));save.setObjectName('saveSectionProgression')
            save.setEnabled(not row.save_issue);save.setToolTip(row.save_issue)
            save.setAccessibleName(f'{row.name} · {save.text()}')
            save.clicked.connect(lambda checked=False,item=row:self.save_section(item,save_progression));header.addWidget(save)
            jump=QPushButton(tr('跳转到段落'));jump.setObjectName('jumpSectionProgression')
            jump.setAccessibleName(f'{row.name} · {jump.text()}')
            jump.clicked.connect(lambda checked=False,bar=row.first_bar:self.jump_to(bar));header.addWidget(jump)
            for text,object_name in ((row.names or tr('此段落暂无和弦'),'chordNames'),(row.roman,'subtitle')):
                if not text:continue
                label=QLabel(text);label.setObjectName(object_name);label.setTextFormat(Qt.TextFormat.PlainText)
                label.setWordWrap(True);label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);body.addWidget(label)
        cards.addStretch()
        self.feedback=QLabel();self.feedback.setObjectName('subtitle');layout.addWidget(self.feedback)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr('关闭'))
        buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def save_section(self,row,save_progression):
        if save_progression(row.chord_ids,parent=self,context_tick=row.context_tick):
            self.feedback.setText(tr('已保存和弦进行预设'))

    def jump_to(self,bar):
        self.jump_bar=bar
        self.accept()
