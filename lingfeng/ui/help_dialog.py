"""Searchable help and theme-color dialogs; content lives in platform.help_content."""
import copy
from html import escape
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QListWidget,QTextBrowser,QLineEdit,
    QComboBox,QPushButton,QLabel,QDialogButtonBox,QColorDialog,QGridLayout)
import lingfeng.platform.i18n as i18n
import lingfeng.ui.theme as theme
from lingfeng.platform.i18n import tr
from lingfeng.platform.help_content import (
    ABOUT_ZH, ABOUT_EN, HELP_CATEGORIES, TOPICS, category_for, plain_text,
)

class HelpDialog(QDialog):
    def __init__(self,parent=None,about=False):
        super().__init__(parent);self.setWindowTitle(tr('关于伶风') if about else tr('伶风帮助'));self.resize(880,640);self.setMinimumSize(580,420)
        root=QVBoxLayout(self);self.search=QLineEdit();self.search.setPlaceholderText(tr('搜索中英文标题与正文…'));root.addWidget(self.search)
        self.category=QComboBox();self.category.addItem(tr('全部分类'),-1)
        en=i18n.LANGUAGE=='en'
        for index,(zh,en_title,_) in enumerate(HELP_CATEGORIES):self.category.addItem(f'{index+1}. {en_title if en else zh}',index)
        root.addWidget(self.category)
        row=QHBoxLayout();self.list=QListWidget();self.list.setMaximumWidth(250);self.list.setMinimumWidth(160);self.list.setWordWrap(True);self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.browser=QTextBrowser();self.browser.setOpenExternalLinks(False);row.addWidget(self.list);row.addWidget(self.browser,1);root.addLayout(row)
        self.list.setStyleSheet('QListWidget::item {padding:7px 8px;}');self.browser.setStyleSheet('QTextBrowser {font-size:14px;padding:12px;}')
        self.pages=[(t[1 if en else 0],t[3 if en else 2]) for t in TOPICS]
        self.page_categories=[category_for(t[0]) for t in TOPICS]
        self.search_text=[plain_text(' '.join(t)).casefold() for t in TOPICS]
        from lingfeng import __version__
        details=f'<p>{"Version" if en else "版本"} {__version__} · Windows<br>{"Project format: " if en else "工程格式："}.lfs — Lingfeng Lead Sheet</p><hr>'
        body=ABOUT_EN if en else ABOUT_ZH;split=body.index('</p>')+4
        self.pages.append((tr('关于伶风'),body[:split]+details+body[split:]))
        self.page_categories.append(len(HELP_CATEGORIES)-1);self.search_text.append(plain_text(ABOUT_ZH+ABOUT_EN).casefold())
        for index,(title,_) in enumerate(self.pages):
            self.list.addItem(title);self.list.item(index).setToolTip(self.category.itemText(self.page_categories[index]+1))
        self.results=QLabel();root.addWidget(self.results)
        self.list.currentRowChanged.connect(self.show_page);self.search.textChanged.connect(self.filter_pages);self.category.currentIndexChanged.connect(lambda:self.filter_pages(self.search.text()))
        self.list.setCurrentRow(len(self.pages)-1 if about else 0);self.filter_pages('')
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(self.reject);root.addWidget(buttons)
    def filter_pages(self,text):
        query=text.strip().casefold();category=self.category.currentData();visible=[]
        for i in range(len(self.pages)):
            group=self.page_categories[i];labels=' '.join(HELP_CATEGORIES[group][:2]).casefold()
            show=(category==-1 or group==category) and query in (self.search_text[i]+' '+labels)
            self.list.item(i).setHidden(not show)
            if show:visible.append(i)
        self.results.setText(tr('{0} 个帮助主题',len(visible)))
        if not visible:
            self.list.setCurrentRow(-1);self.browser.setHtml('<p>'+tr('没有匹配的帮助主题，请更换关键词或分类。')+'</p>')
        elif self.list.currentRow() not in visible:self.list.setCurrentRow(visible[0])
        if self.list.currentItem():self.list.scrollToItem(self.list.currentItem())
    def show_page(self,index):
        if index<0:return
        title,body=self.pages[index]
        category=self.page_categories[index];zh,en_title,_=HELP_CATEGORIES[category]
        breadcrumb=f'<p>{category+1}. {escape(en_title if i18n.LANGUAGE=="en" else zh)} &gt; {escape(title)}</p>'
        if title in ('颜色与可视区域','Colors and visibility'):
            labels=[tr('调内且匹配'),tr('仅调内'),tr('仅匹配'),tr('其他音')]
            body+='<table cellspacing="8">'
            for key,label in zip(('both','scale','chord','other'),labels):
                bg=theme.roll_color(key);note=theme.roll_color(key,'note');fg=theme.label_color(note)
                body+=f'<tr><td bgcolor="{bg.name()}">&nbsp;&nbsp;&nbsp;</td><td bgcolor="{note.name()}"><font color="{fg.name()}">&nbsp;1&nbsp;</font></td><td>{label}</td></tr>'
            body+='</table>'
        heading='' if index==len(self.pages)-1 else f'<h2>{escape(title)}</h2>'
        self.browser.setHtml(f'<style>h1 {{margin:2px 0 12px;}} h3 {{margin:16px 0 6px;}} p {{margin:8px 0;}}</style>{breadcrumb}{heading}<div style="line-height:1.6">{body}</div>')


class ColorSettingsDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle(tr('自定义色彩方案'));self.resize(540,380);self.values=copy.deepcopy(theme.CUSTOM_PALETTES)
        root=QVBoxLayout(self);self.mode=QComboBox();self.mode.addItem(tr('浅色'),'light');self.mode.addItem(tr('深色'),'dark');self.mode.setCurrentIndex(1 if theme.is_dark() else 0);root.addWidget(self.mode)
        grid=QGridLayout();root.addLayout(grid);grid.addWidget(QLabel(tr('背景色')),0,1);grid.addWidget(QLabel(tr('音符色')),0,2);self.buttons={}
        for row,(key,label) in enumerate(zip(('both','scale','chord','other'),(tr('调内且匹配'),tr('仅调内'),tr('仅匹配'),tr('其他音'))),1):
            grid.addWidget(QLabel(label),row,0)
            for col,layer in enumerate(('background','note'),1):
                button=QPushButton();button.clicked.connect(lambda checked=False,k=key,l=layer:self.pick(k,l));grid.addWidget(button,row,col);self.buttons[key,layer]=button
        reset=QPushButton(tr('恢复当前主题默认色'));reset.clicked.connect(self.reset);root.addWidget(reset)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self.mode.currentIndexChanged.connect(self.refresh);self.refresh()
    def refresh(self):
        for (key,layer),button in self.buttons.items():
            value=self.values.get(self.mode.currentData(),{}).get(layer,{}).get(key)
            from lingfeng.music.model import BACKGROUND_COLORS, NOTE_COLORS
            color=theme.color(value or (BACKGROUND_COLORS if layer=='background' else NOTE_COLORS)[key],self.mode.currentData()=='dark') if not value else theme.QColor(value)
            button.setText(color.name());button.setStyleSheet(f'background:{color.name()};color:{theme.label_color(color).name()};')
    def pick(self,key,layer):
        color=QColorDialog.getColor(theme.QColor(self.buttons[key,layer].text()),self,tr('选择颜色'))
        if color.isValid():self.values.setdefault(self.mode.currentData(),{}).setdefault(layer,{})[key]=color.name();self.refresh()
    def reset(self):
        self.values.pop(self.mode.currentData(),None);self.refresh()
