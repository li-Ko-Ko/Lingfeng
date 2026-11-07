"""Export the same categorized bilingual help shipped by the application."""
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from lingfeng.platform.help_content import HELP_CATEGORIES, TOPICS, ABOUT_ZH, ABOUT_EN


def export(path=ROOT/'docs/HELP.md'):
    topics={topic[0]:topic for topic in TOPICS}
    parts=['# 伶风操作帮助 / Lingfeng user guide',
           '首次使用可先读[从创作到导出](#topic-1-1)。下方按任务查找，也可在程序内搜索中英文标题和正文。',
           'Start with [From composition to export](#topic-1-1). Browse by task below or search titles and text in either language from the app.',
           '## 目录 / Contents']
    toc=[]
    for group,(zh,en,titles) in enumerate(HELP_CATEGORIES,1):
        toc.append(f'{group}. [{zh} / {en}](#category-{group})')
        for item,title in enumerate(titles,1):
            topic=topics[title];toc.append(f'    - [{group}.{item} {title} / {topic[1]}](#topic-{group}-{item})')
    parts.append('\n'.join(toc))
    for group,(zh,en,titles) in enumerate(HELP_CATEGORIES,1):
        parts.append(f'<a id="category-{group}"></a>\n\n## {group}. {zh} / {en}')
        if not titles:
            for language,body in (('中文',ABOUT_ZH),('English',ABOUT_EN)):
                body=re.sub(r'<(/?)h[1-6]>',r'<\1h4>',body);parts.append(f'**{language}**\n\n{body}')
        for item,title in enumerate(titles,1):
            topic=topics[title]
            parts.append(f'<a id="topic-{group}-{item}"></a>\n\n### {group}.{item} {title} / {topic[1]}')
            for language,body in zip(('中文','English'),topic[2:]):
                body=re.sub(r'<(/?)h[1-6]>',r'<\1h4>',body)
                parts.append(f'**{language}**\n\n{body}')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text('\n\n'.join(parts)+'\n','utf-8')
    return path


if __name__=='__main__':print(export())
