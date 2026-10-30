"""Shared application/painter colors. Printed score colors remain independent."""
from pathlib import Path
from PySide6.QtGui import QColor,QPalette
from PySide6.QtWidgets import QApplication,QWidget

CUSTOM_PALETTES={}
PAINT_REVISION=0
SHOW_NOTE_DEGREES=True
ACCIDENTAL_PREFERENCE='sharp'

def set_accidental_preference(value):
    global ACCIDENTAL_PREFERENCE,PAINT_REVISION
    ACCIDENTAL_PREFERENCE='flat' if value=='flat' else 'sharp';PAINT_REVISION+=1

def roll_pitch_name(pitch):
    from .model import FLAT,SHARP
    return (FLAT if ACCIDENTAL_PREFERENCE=='flat' else SHARP)[pitch%12]+str(pitch//12-1)

def roll_degree_text(pitch,tonic,mode=None,unicode=True):
    from .model import degree_text
    return degree_text(pitch,tonic,flat=ACCIDENTAL_PREFERENCE=='flat',unicode=unicode,mode=mode)

def pitch_class_choices(tonic,mode=None):
    """The same modal degrees as roll notes, ordered by pitch from the tonic."""
    from .model import FLAT,SHARP
    names=FLAT if ACCIDENTAL_PREFERENCE=='flat' else SHARP
    return [(roll_degree_text(tonic+offset,tonic,mode,unicode=False)+' · '+names[(tonic+offset)%12],
             (tonic+offset)%12) for offset in range(12)]

ROLL_COLORING={'melody':{'scale':True,'match':True},'harmony':{'scale':True,'match':True}}


def set_note_degrees(visible):
    global SHOW_NOTE_DEGREES,PAINT_REVISION
    SHOW_NOTE_DEGREES=visible is not False
    PAINT_REVISION+=1


def set_roll_coloring(values):
    global ROLL_COLORING,PAINT_REVISION
    values=values if isinstance(values,dict) else {}
    ROLL_COLORING={role:{key:values.get(role,{}).get(key,True) is not False for key in ('scale','match')} for role in ('melody','harmony')}
    PAINT_REVISION+=1


def colored_category(category,role):
    options=ROLL_COLORING[role]
    scale=options['scale'] and category in ('both','scale')
    match=options['match'] and category in ('both','chord')
    return 'both' if scale and match else 'scale' if scale else 'chord' if match else 'other'

def set_roll_palettes(palettes):
    global CUSTOM_PALETTES,PAINT_REVISION
    PAINT_REVISION+=1
    CUSTOM_PALETTES={}
    if not isinstance(palettes,dict):return
    for mode,groups in palettes.items():
        if mode not in ('light','dark') or not isinstance(groups,dict):continue
        CUSTOM_PALETTES[mode]={layer:{key:value for key,value in values.items() if key in ('both','scale','chord','other') and isinstance(value,str) and QColor(value).isValid()} for layer,values in groups.items() if layer in ('background','note') and isinstance(values,dict)}
    app=QApplication.instance()
    if app:
        for widget in app.allWidgets():QWidget.update(widget)

def roll_color(category,layer='background',dark=None):
    from .model import BACKGROUND_COLORS,NOTE_COLORS
    dark=is_dark() if dark is None else dark
    mode='dark' if dark else 'light'
    custom=CUSTOM_PALETTES.get(mode,{}).get(layer,{}).get(category)
    return QColor(custom) if custom else color((BACKGROUND_COLORS if layer=='background' else NOTE_COLORS)[category],dark)

def label_color(background):
    return QColor('#17202C' if background.lightnessF()>.57 else '#FFFFFF')

DARK_COLORS={
    '#c9d5e3':'#405168','#9aaec6':'#6B839E','#d2dce8':'#384B62',
    '#ffffff':'#17202C','#fafbfd':'#1B2533','#f9fbfd':'#1B2533','#fcfdfe':'#18212E',
    '#f8fafc':'#202C3B','#edf2f7':'#18222F','#edf1f6':'#263242','#e5edf6':'#30415A',
    '#edf5f2':'#263D3C','#c7d9d7':'#405F5C','#275d54':'#A7D8CB','#65827d':'#9DBBB7',
    '#247d6e':'#72C7AD','#7ba79c':'#76B6A4','#44786e':'#8DCAB8',
    '#66768b':'#ABB9CC','#8191a4':'#9CAEC4','#8a9aad':'#9CAEC4','#9ab4cb':'#657F9B',
    '#92a0b0':'#9EACC0','#4a5a6f':'#CBD6E6','#34465e':'#E2EAF4','#7a889b':'#A5B5CA',
    '#78879b':'#A5B5CA','#927241':'#D9BA85','#1d2d44':'#E2EAF4','#e9fff8':'#F1FFFA',
    '#d15f49':'#F5A678','#e3e8ee':'#344253','#e4e9ef':'#344253','#e8edf2':'#303D4D',
    '#dae2eb':'#445268','#eef1f5':'#303C4C','#9bacbf':'#71839B','#c4d0df':'#53677F',
    '#bbddd3':'#2A514B','#d3dff3':'#293D59','#eee3d2':'#35362F','#f7f8fa':'#1B2330',
    '#438f7e':'#84BAA9','#426baa':'#A0BCE8','#955e25':'#ECC58D','#7d2e48':'#FFB3CC',
    '#e9eef4':'#101721','#dae1e9':'#0B111A','#263345':'#D7E0EC','#8692a2':'#98A9BE',
    '#bc6542':'#F5B78D','#edf0f3':'#2E3B4D','#e9eef3':'#2E3B4D','#e7ecf2':'#2E3B4D',
    '#a4adba':'#697D95','#b6c2ce':'#7D91A8','#6b9c90':'#7BAE9F',
}

def is_dark():
    app=QApplication.instance()
    return bool(app and app.property('popscore_dark'))

def color(value,dark=None):
    source=QColor(value);dark=is_dark() if dark is None else dark
    return QColor(DARK_COLORS.get(source.name().lower(),source.name())) if dark else source

def stylesheet(dark=False):
    bg,surface,raised,text,muted,border,hover,active=('#111923','#1B2533','#243143','#DCE5F0','#A0B0C6','#35465B','#2C4055','#365A62') if dark else ('#F0F3F7','#FFFFFF','#F8FAFC','#27374D','#728399','#D8E1EA','#EDF3F8','#293F58')
    check=(Path(__file__).resolve().parent.parent/'assets'/'check.svg').as_posix()
    return f'''
    QWidget {{font-family:"Microsoft YaHei";font-size:12px;color:{text};}}
    QMainWindow,QWidget#shell,QDialog {{background:{bg};}}
    QFrame#header {{background:{surface};border-bottom:1px solid {border};}}
    QFrame#editorCard,QFrame#harmonyDock {{background:{surface};border:1px solid {border};border-radius:8px;}}
    QLabel#brand {{font-size:20px;font-weight:600;}}
    QLabel#subtitle,QLabel#legend {{color:{muted};font-size:11px;}}
    QPushButton,QToolButton {{background:{surface};border:1px solid {border};border-radius:6px;padding:5px 10px;min-height:22px;}}
    QPushButton:hover,QToolButton:hover {{background:{hover};}}
    QPushButton:checked,QToolButton:checked {{background:{active};color:#FFFFFF;}}
    QToolButton#play {{background:{'#346E62' if dark else '#247D6E'};border:0;}}
    QPushButton:disabled,QToolButton:disabled {{color:{muted};background:{raised};}}
    QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit,QPlainTextEdit {{background:{surface};border:1px solid {border};border-radius:5px;padding:4px 7px;min-height:22px;selection-background-color:{hover};}}
    QComboBox::drop-down {{border:0;width:20px;}}
    QComboBox QAbstractItemView {{background:{surface};selection-background-color:{hover};color:{text};}}
    QSpinBox::up-button,QDoubleSpinBox::up-button,QSpinBox::down-button,QDoubleSpinBox::down-button {{width:16px;border:0;background:{raised};}}
    QMenuBar {{background:transparent;border:0;font-family:"Microsoft YaHei";font-size:12px;font-weight:700;}}
    QMenuBar::item:disabled {{color:{text};}}
    QMenuBar::item {{background:transparent;border:0;border-radius:5px;padding:5px 10px;margin:0 1px;}}
    QMenuBar::item:selected,QMenuBar::item:pressed {{background:{hover};}}
    QMenu {{background:{surface};border:1px solid {border};padding:5px;}}
    QMenu::item {{padding:7px 24px;}} QMenu::item:selected {{background:{hover};}}
    QMenu::item:disabled {{color:{muted};}}
    QMenu::separator {{height:1px;background:{border};margin:4px 8px;}}
    QTabWidget::pane {{background:{surface};border:1px solid {border};border-radius:5px;}}
    QTabBar::tab {{background:{raised};color:{muted};padding:7px 13px;border:1px solid {border};border-bottom:0;margin-right:2px;}}
    QTabBar::tab:selected {{background:{surface};color:{text};border-top:2px solid #3C8F7D;}}
    QTabBar::tab:hover {{background:{hover};}}
    QScrollArea,QListWidget,QTextBrowser,QTreeWidget {{background:{surface};border:1px solid {border};}}
    QWidget#scoreLogic,QWidget#lyricsPanel {{background:{surface};}}
    QTreeWidget::item {{padding:3px 5px;}}
    QTreeWidget::item:selected {{background:{active};color:#FFFFFF;}}
    QHeaderView::section {{background:{raised};color:{text};padding:4px 7px;border:0;border-bottom:1px solid {border};font-weight:600;}}
    QListWidget::item {{padding:4px 7px;}}
    QListWidget::item:selected {{background:{active};color:#FFFFFF;}}
    QScrollBar:vertical {{background:{raised};width:11px;border:0;}}
    QScrollBar:horizontal {{background:{raised};height:11px;border:0;}}
    QScrollBar::handle {{background:{'#4C6078' if dark else '#C5D0DE'};border-radius:5px;min-height:30px;min-width:35px;}}
    QScrollBar::add-line,QScrollBar::sub-line {{width:0;height:0;}}
    QSplitter::handle {{background:{border};height:7px;}}
    QStatusBar {{background:{raised};border-top:1px solid {border};color:{muted};}}
    QCheckBox {{spacing:5px;}}
    QCheckBox::indicator {{width:13px;height:13px;border:1px solid {border};border-radius:3px;background:{surface};}}
    QCheckBox::indicator:checked {{background:#3C8F7D;border-color:#3C8F7D;image:url("{check}");}}
    QAbstractScrollArea::corner {{background:{raised};}}
    QSlider::groove:horizontal {{height:4px;background:{border};border-radius:2px;}}
    QSlider::sub-page:horizontal {{background:{'#67B6A3' if dark else '#4B8F81'};border-radius:2px;}}
    QSlider::handle:horizontal {{width:11px;margin:-4px 0;border-radius:3px;background:{'#A3B6CE' if dark else '#FFFFFF'};border:1px solid {border};}}
    QToolTip {{background:{surface};color:{text};border:1px solid {border};padding:6px;}}
    QToolButton#windowControl {{border:0;border-radius:4px;background:transparent;padding:0;}}
    QToolButton#windowControl:hover {{background:{border};}}
    '''

def apply_theme(dark):
    app=QApplication.instance();style=stylesheet(dark)
    if app.property('popscore_dark')==bool(dark) and app.styleSheet()==style:return
    app.setProperty('popscore_dark',bool(dark));app.setStyleSheet(style)
    palette=QPalette()
    for role,value in [(QPalette.ColorRole.Window,'#111923'),(QPalette.ColorRole.WindowText,'#DCE5F0'),
                       (QPalette.ColorRole.Base,'#1B2533'),(QPalette.ColorRole.AlternateBase,'#243143'),
                       (QPalette.ColorRole.Text,'#DCE5F0'),(QPalette.ColorRole.Button,'#243143'),
                       (QPalette.ColorRole.ButtonText,'#DCE5F0'),(QPalette.ColorRole.Highlight,'#3C6470'),
                       (QPalette.ColorRole.HighlightedText,'#FFFFFF'),(QPalette.ColorRole.ToolTipBase,'#1B2533'),
                       (QPalette.ColorRole.ToolTipText,'#DCE5F0')]:
        if dark:palette.setColor(role,QColor(value))
    app.setPalette(palette if dark else app.style().standardPalette())
    for widget in app.allWidgets():QWidget.update(widget)
