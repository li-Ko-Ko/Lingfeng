"""Explain why the selected melody tracks cannot use traditional jianpu."""
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout

from lingfeng.engraving.compatibility import traditional_conflicts
from lingfeng.music.model import PPQ
from lingfeng.platform.i18n import tr


def _location(project,tick):
    bar=project.measure_at(tick)
    measure=project.measures[bar]
    beat=1+(tick-project.starts[bar])*measure.denominator/(4*PPQ)
    return tr('第 {0} 小节，第 {1} 拍',bar+1,f'{beat:g}')


def traditional_compatibility_report(project):
    conflicts=traditional_conflicts(project)
    lines=[tr('传统简谱要求已勾选的每条旋律均为单声部。'),
           tr('仅检查谱面选项中已勾选的旋律轨道，和弦符号不参与检查。')]
    if conflicts:
        lines+=['',tr('必须修改')]
        for track,overlaps in conflicts.items():
            lines.append(tr('{0} 有 {1} 处音符重叠，首处在{2}。',
                            project.melody_name(track),len(overlaps),_location(project,overlaps[0].start)))
        lines+=['',tr('请在谱面选项中取消勾选有重叠音符的旋律，或修正该轨后重试；也可使用立体简谱或立体简谱 · 紧凑。')]
    else:lines+=['',tr('所选旋律符合传统简谱的单声部要求。')]
    return '\n'.join(lines)


def show_traditional_compatibility(parent,project):
    dialog=QDialog(parent)
    dialog.setWindowTitle(tr('传统简谱兼容性检查'))
    dialog.resize(660,380)
    layout=QVBoxLayout(dialog)
    report=QPlainTextEdit(traditional_compatibility_report(project),dialog)
    report.setReadOnly(True)
    layout.addWidget(report)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close,parent=dialog)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()
