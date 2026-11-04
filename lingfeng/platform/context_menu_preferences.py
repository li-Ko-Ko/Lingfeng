"""Stable context-menu blocks with user ordering and optional grouping.

Every known block is retained. Common editing operations always stay directly
available; preferences can only change order and group eligible advanced blocks.
"""
import copy


BLOCKS = {
    'chord': (
        dict(id='edit', title='编辑与试听', labels=('编辑和弦…', '在和弦卷帘中编辑', '试听和弦'), groupable=False, grouped=False),
        dict(id='clipboard', title='复制与粘贴', labels=('复制所选和弦', '在此和弦开头覆盖粘贴', '在此粘贴和弦', '在定位线处粘贴和弦'), groupable=False, grouped=False),
        dict(id='split_merge', title='分割与合并', labels=('在定位线处分割和弦', '二等分和弦', '合并相邻和弦'), groupable=False, grouped=False),
        dict(id='dynamics', title='力度', labels=('修改力度',), groupable=True, grouped=False),
        dict(id='properties', title='和弦属性', labels=('和弦根音', '和弦性质', '替换低音', '和弦转位', '节奏型'), groupable=True, grouped=True),
        dict(id='movement', title='和弦移动', labels=('和弦移动',), groupable=False, grouped=False),
        dict(id='recognition', title='识别与标记', labels=('设置和弦标记…', '禁用和弦识别'), groupable=True, grouped=False),
        dict(id='progressions', title='和弦进行', labels=('从此和弦开始应用和弦进行…', '按顺序保存为和弦进行…', '检索和弦进行…'), groupable=True, grouped=True),
        dict(id='insertion', title='插入', labels=('插入空白和弦', '在定位线处插入空白和弦'), groupable=True, grouped=True),
        dict(id='display', title='显示', labels=('和弦轨力度窗格',), groupable=True, grouped=False),
        dict(id='delete', title='删除', labels=('删除所选和弦',), groupable=False, grouped=False),
    ),
    'note': (
        dict(id='edit', title='编辑', labels=('编辑音符…',), groupable=False, grouped=False),
        dict(id='dynamics', title='力度', labels=('修改力度',), groupable=True, grouped=False),
        dict(id='clipboard', title='复制与粘贴', labels=('复制所选音符', '复制变换', '在此粘贴音符', '在定位线处粘贴音符'), groupable=False, grouped=False),
        dict(id='split_merge', title='分割与合并', labels=('合并相邻音符', '二等分音符'), groupable=False, grouped=False),
        dict(id='pitch', title='音高变换', labels=('升高半音', '降低半音', '调内上移一级', '调内下移一级', '上移八度', '下移八度'), groupable=True, grouped=True),
        dict(id='quantize', title='量化', labels=('按当前格点量化',), groupable=False, grouped=False),
        dict(id='delete', title='删除', labels=('删除所选音符',), groupable=False, grouped=False),
    ),
}


def default_layout():
    return {kind: [dict(id=block['id'], grouped=block['grouped']) for block in definitions]
            for kind, definitions in BLOCKS.items()}


def normalize_layout(values):
    values = values if isinstance(values, dict) else {}
    result = {}
    for kind, definitions in BLOCKS.items():
        by_id = {block['id']: block for block in definitions}
        saved = values.get(kind)
        saved = saved if isinstance(saved, list) else []
        ordered = []
        used = set()
        for entry in saved:
            if not isinstance(entry, dict) or not isinstance(entry.get('id'), str):
                continue
            code = entry['id']
            if code in used or code not in by_id:
                continue
            definition = by_id[code]
            grouped = entry.get('grouped')
            grouped = grouped if type(grouped) is bool else definition['grouped']
            ordered.append(dict(id=code, grouped=grouped if definition['groupable'] else False))
            used.add(code)
        ordered.extend(dict(id=block['id'], grouped=block['grouped']) for block in definitions if block['id'] not in used)
        result[kind] = ordered
    return result


_layout = default_layout()


def load_preferences(values):
    global _layout
    values = values if isinstance(values, dict) else {}
    _layout = normalize_layout(values.get('context_menu_layout'))


def set_preferences(values):
    load_preferences(values)


def blocks(kind):
    definitions = {block['id']: block for block in BLOCKS[kind]}
    return [dict(copy.deepcopy(definitions[entry['id']]), grouped=entry['grouped']) for entry in _layout[kind]]


def settings_dict():
    return {'context_menu_layout': copy.deepcopy(_layout)}
