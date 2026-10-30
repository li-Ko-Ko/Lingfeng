"""Bar-bounded lyric entry with an explicit onset template and live validation."""
from fractions import Fraction
from PySide6.QtCore import Signal,QTimer,Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,
    QPlainTextEdit,QSpinBox,QDialog,QDialogButtonBox,QTreeWidget,QTreeWidgetItem,QHeaderView,QScrollArea,QFrame)
from lingfeng.platform.i18n import tr
from lingfeng.music.model import PPQ, uid
from lingfeng.engraving.lyrics import sections, events, belongs, plan_range, apply_range, delete_section, matching_issues, melody_onsets, range_source, delete_range


class LyricsPanel(QWidget):
    changed=Signal()
    def __init__(self,owner):
        super().__init__();self.setObjectName('lyricsPanel');self.owner=owner;self.current_id=None;self.loading=False;self.dirty=False;self.plan=None;self.range_edit=False;self.autofill_valid=True
        root=QVBoxLayout(self);root.setContentsMargins(10,8,10,8);root.setSpacing(7)
        content=QWidget();content.setObjectName('lyricsPanel');box=QVBoxLayout(content);box.setContentsMargins(0,0,0,0);box.setSpacing(7)
        self.scroller=QScrollArea();self.scroller.setFrameShape(QFrame.Shape.NoFrame);self.scroller.setWidgetResizable(True);self.scroller.setWidget(content);root.addWidget(self.scroller,2)
        top=QHBoxLayout();self.section=QComboBox();self.section.setMinimumWidth(120);top.addWidget(self.section,1)
        fresh=QPushButton(tr('新增歌词段'));fresh.clicked.connect(self.new_section);top.addWidget(fresh);box.addLayout(top)
        row=QHBoxLayout();row.addWidget(QLabel(tr('起始小节')));self.start=QSpinBox();self.start.setRange(1,len(owner.project.measures));row.addWidget(self.start)
        row.addWidget(QLabel(tr('小节数量')));self.count=QSpinBox();self.count.setRange(1,len(owner.project.measures));self.count.setValue(min(4,len(owner.project.measures)));row.addWidget(self.count)
        cursor=QPushButton(tr('使用谱面选区'));cursor.clicked.connect(self.use_selection);row.addWidget(cursor)
        row.addWidget(QLabel(tr('歌词段次')));self.verse=QSpinBox();self.verse.setRange(1,32);row.addWidget(self.verse);row.addStretch();box.addLayout(row)
        info=QLabel(tr('每个 & 对应一个旋律 MIDI 起点；同刻多音合并。每小节一行，中文连写，英文词用空格分隔；标点不占起点。/s 跳过；/- 与前一个音符连音，连续两个写 /-/-，仅改变谱面。{0} 标记连续说唱。首次打开或改变范围会回填已有歌词，允许少填，不可超出范围。','/x{我是一个rapper}'));info.setWordWrap(True);box.addWidget(info)
        self.rhythm=QTreeWidget();self.rhythm.setHeaderLabels([tr('小节'),tr('拍内起点 / 节奏'),tr('歌词 / 占位'),tr('匹配')]);self.rhythm.setRootIsDecorated(False);self.rhythm.setMinimumHeight(90);self.rhythm.setMaximumHeight(180)
        self.rhythm.header().setMinimumSectionSize(60);self.rhythm.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents);self.rhythm.header().setStretchLastSection(True);box.addWidget(self.rhythm)
        self.text=QPlainTextEdit();self.text.setPlaceholderText(tr('每小节换行；/s 跳过，/- 与前音连音，{0} 标记说唱。中文连写，英文词间留空格。','/x{歌词}'));self.text.setMinimumHeight(90);root.addWidget(self.text,1)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setMinimumHeight(30);root.addWidget(self.status)
        buttons=QHBoxLayout();template=QPushButton(tr('生成 & 模板').replace('&','&&'));template.clicked.connect(self.template);buttons.addWidget(template)
        check=QPushButton(tr('检查匹配'));check.clicked.connect(self.check);buttons.addWidget(check)
        self.apply=QPushButton(tr('确认输入'));self.apply.clicked.connect(self.commit);buttons.addWidget(self.apply)
        self.remove=QPushButton(tr('删除此段'));self.remove.clicked.connect(self.delete);buttons.addWidget(self.remove);buttons.addStretch();root.addLayout(buttons)
        self.check_timer=QTimer(self);self.check_timer.setSingleShot(True);self.check_timer.setInterval(120);self.check_timer.timeout.connect(self.check)
        self.section.currentIndexChanged.connect(self.load_selected)
        self.text.textChanged.connect(self.edited)
        for field in (self.start,self.count,self.verse):field.valueChanged.connect(self.range_changed)
        self.refresh();self.new_section();self.initial_load_pending=True

    def open_editor(self):
        if not getattr(self,'initial_load_pending',False):return
        self.initial_load_pending=False
        if not self.dirty:self.use_selection()

    def reset_project(self):
        self.new_section();self.initial_load_pending=True;self.refresh()
        if self.owner.workspace=='score' and self.isVisible():self.open_editor()

    def limit_range(self):
        previous=self.loading;self.loading=True
        self.start.setMaximum(len(self.owner.project.measures));self.count.setMaximum(len(self.owner.project.measures)-self.start.value()+1)
        self.loading=previous

    def edited(self):
        if self.loading:return
        self.limit_range();self.dirty=True;self.autofill_valid=True;self.apply.setEnabled(False);self.check_timer.start();self.changed.emit()

    def range_changed(self):
        if self.loading:return
        self.limit_range();self.load_range()

    def load_range(self):
        """Selecting a range is a read-only load of that stanza's saved onsets."""
        self.initial_load_pending=False;self.loading=True;self.limit_range();p=self.owner.project
        first,count,verse=self.start.value()-1,self.count.value(),self.verse.value()-1
        a,b=p.starts[first],p.starts[first+count]
        text,self.autofill_valid=range_source(p,first,count,verse,self.owner.roll.grid)
        exact=next((s for s in sections(p) if s['verse']==verse and self.item_range(s)==(first+1,count)),None)
        self.current_id=exact['id'] if exact else None;self.range_edit=True
        blocked=self.section.blockSignals(True);self.section.setCurrentIndex(max(0,self.section.findData(self.current_id)));self.section.blockSignals(blocked)
        self.text.setPlainText(text);self.remove.setEnabled(any(e.get('verse',0)==verse and a<=e['tick']<b for e in events(p)))
        self.loading=False;self.dirty=False;self.check();self.changed.emit()

    def use_selection(self):
        bars=sorted(self.owner.score_view.canvas.selected_bars)
        self.loading=True
        if bars and bars==list(range(bars[0],bars[-1]+1)):
            self.start.setValue(bars[0]+1);self.limit_range();self.count.setValue(len(bars))
        else:self.start.setValue(self.owner.project.measure_at(self.owner.playhead)+1)
        self.loading=False;self.limit_range();self.load_range()

    def item_range(self,item):
        p=self.owner.project;first=p.measure_at(item['start']);items=[e for e in events(p) if belongs(e,item['id'])]
        end=item.get('end',max((e['tick']+max(1,e.get('duration',0)) for e in items),default=item['start']+1))
        return first+1,p.measure_at(min(p.end-1,end-1))-first+1

    def refresh(self):
        self.limit_range();current=self.current_id;items=sections(self.owner.project)
        self.section.blockSignals(True);self.section.clear();self.section.addItem(tr('新段落'),None)
        for item in items:
            first,count=self.item_range(item);preview=' '.join(item['text'].splitlines())[:18];self.section.addItem(tr('第 {0}–{1} 小节 · 第 {2} 段 · {3}',first,first+count-1,item['verse']+1,preview),item['id'])
        at=self.section.findData(current);self.section.setCurrentIndex(max(0,at));self.section.blockSignals(False);self.remove.setEnabled(current is not None and at>=0)
        if self.range_edit:
            _,first,count,verse=self.values();a,b=self.owner.project.starts[first],self.owner.project.starts[first+count]
            self.remove.setEnabled(any(e.get('verse',0)==verse and a<=e['tick']<b for e in events(self.owner.project)))
        if not self.dirty and self.range_edit:self.load_range()
        elif not self.dirty and current is not None:
            item=next((s for s in items if s['id']==current),None)
            if item:self.populate(item)
            else:self.new_section()
        if self.owner.workspace=='score':self.check()

    def populate(self,item):
        self.initial_load_pending=False;self.loading=True;self.range_edit=False;self.autofill_valid=item.get('autofill_valid',True);self.current_id=item['id'];first,count=self.item_range(item);self.start.setValue(first);self.limit_range();self.count.setValue(count);self.verse.setValue(item['verse']+1);self.text.setPlainText(item['text']);self.loading=False;self.dirty=False

    def export_state(self):return dict(id=self.current_id,text=self.text.toPlainText(),start=self.start.value(),count=self.count.value(),verse=self.verse.value(),dirty=self.dirty,range_edit=self.range_edit,autofill_valid=self.autofill_valid,initial_load_pending=self.initial_load_pending)

    def restore_state(self,state):
        self.loading=True;self.initial_load_pending=state.get('initial_load_pending',False);self.range_edit=state.get('range_edit',False);self.autofill_valid=state.get('autofill_valid',True);self.current_id=state['id'];self.dirty=state['dirty'];self.start.setValue(state['start']);self.limit_range();self.count.setValue(state.get('count',4));self.verse.setValue(state['verse']);self.text.setPlainText(state['text']);self.loading=False;self.refresh()

    def new_section(self):
        self.initial_load_pending=False;self.loading=True;self.range_edit=False;self.autofill_valid=True;self.current_id=None;self.section.setCurrentIndex(0);self.start.setValue(self.owner.project.measure_at(self.owner.playhead)+1);self.limit_range();self.text.clear();self.loading=False;self.dirty=False;self.remove.setEnabled(False);self.check();self.changed.emit()

    def load_selected(self):
        if self.loading:return
        ident=self.section.currentData()
        if ident is None:self.new_section();return
        item=next((s for s in sections(self.owner.project) if s['id']==ident),None)
        if item:self.populate(item);self.remove.setEnabled(True);self.check();self.changed.emit()

    def values(self):return self.text.toPlainText(),self.start.value()-1,self.count.value(),self.verse.value()-1

    def template(self):
        p=self.owner.project;first=self.start.value()-1;count=self.count.value()
        parts=['&'*len(melody_onsets(p,*p.starts[b:b+2])) for b in range(first,first+count)]
        self.text.selectAll();self.text.insertPlainText('\n'.join(parts));self.check()

    def draw_rhythm(self,planned):
        p=self.owner.project;first=self.start.value()-1;self.rhythm.clear();onsets=melody_onsets(p);assigned={e['tick']:e for e in planned}
        self.rhythm.setMaximumHeight(max(90,min(150,30+24*self.count.value())))
        for bar in range(first,first+self.count.value()):
            a,b=p.starts[bar:bar+2];beat=PPQ*4//p.measures[bar].denominator
            ticks=sorted({t for t in onsets if a<=t<b}|{e['tick'] for e in planned if a<=e['tick']<b})
            positions=[];words=[];done=0
            for tick in ticks:
                q=Fraction(tick-a,beat);whole=q.numerator//q.denominator+1;remainder=q-(whole-1)
                positions.append(str(whole)+(f'+{remainder}' if remainder else ''))
                e=assigned.get(tick);words.append((e['text'] or ('/-' if e.get('melisma') else '/s'))+(' [x]' if e['kind'] in ('rap','rap_note') else '') if e else '&')
                done+=bool(e and e['kind']!='pending')
            item=QTreeWidgetItem([str(bar+1), ' · '.join(positions) or '—',' '.join(words) or tr('无起点'),f'{done}/{len(ticks)}'])
            self.rhythm.addTopLevelItem(item)

    def check(self):
        self.check_timer.stop();self.limit_range()
        try:
            self.plan=plan_range(self.owner.project,*self.values(),self.current_id,self.owner.roll.grid,replace=self.range_edit)
            self.draw_rhythm(self.plan.events);issues=self.plan.issues
            if not self.autofill_valid:issues.append(tr('已有歌词包含无法按当前起点回填的内容，请检查并修改后再确认。'))
            if issues:self.status.setText('\n'.join(issues[:3]))
            else:self.status.setText(tr('范围匹配通过：{0} 个歌词起点，跳过 {1} 个，连音 {2} 个，含 {3} 个说唱起点。',sum(not e['skip'] and e['kind']!='pending' for e in self.plan.events),sum(e['skip'] and not e.get('melisma') for e in self.plan.events),sum(bool(e.get('melisma')) for e in self.plan.events),sum(e['kind'] in ('rap','rap_note') for e in self.plan.events)))
            self.apply.setEnabled(not issues);return not issues
        except ValueError as exc:self.status.setText(str(exc));self.apply.setEnabled(False);return False

    def commit(self):
        if not self.check():return
        ident=self.current_id or uid()
        values=self.values()
        if self.owner.mutate(tr('已确认歌词与起点匹配'),lambda p:apply_range(p,*values,ident,self.owner.roll.grid,replace=self.range_edit),source='lyrics'):
            self.current_id=ident;self.dirty=False;self.refresh();self.changed.emit()

    def delete(self):
        if self.range_edit:
            _,first,count,verse=self.values()
            if self.owner.mutate(tr('已删除歌词段'),lambda p:delete_range(p,first,count,verse,self.owner.roll.grid),source='lyrics'):
                self.dirty=False;self.refresh();self.changed.emit()
            return
        if self.current_id and self.owner.mutate(tr('已删除歌词段'),lambda p:delete_section(p,self.current_id)):
            self.new_section();self.refresh();self.changed.emit()


class LyricsGateDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.setWindowTitle(tr('歌词匹配检查'));self.resize(760,650)
        box=QVBoxLayout(self);intro=QLabel(tr('歌词与起点匹配存在错误。请调整歌词或小节范围，允许少填；用 /s 跳过起点、/- 与前音连音，或删除该段。'));intro.setWordWrap(True);box.addWidget(intro)
        self.panel=LyricsPanel(owner);box.addWidget(self.panel)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);self.enter=self.buttons.button(QDialogButtonBox.StandardButton.Ok);self.enter.setProperty('localizedLabel','进入制谱');self.enter.setText(tr('进入制谱'))
        self.buttons.accepted.connect(self.accept_checked);self.buttons.rejected.connect(self.reject);box.addWidget(self.buttons)
        self.panel.changed.connect(self.refresh);self.refresh()
        if self.panel.section.count()>1:self.panel.section.setCurrentIndex(1)

    def refresh(self):self.enter.setEnabled(not self.panel.dirty and not matching_issues(self.panel.owner.project))
    def accept_checked(self):
        if not self.panel.dirty and not matching_issues(self.panel.owner.project):self.accept()
