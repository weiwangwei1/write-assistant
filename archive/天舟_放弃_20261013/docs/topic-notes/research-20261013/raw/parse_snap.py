# -*- coding: utf-8 -*-
"""解析 browser snapshot 日志 → 结构化书目（用 final_fontmap 解码）"""
import json
import re
import sys
import os

BASE = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw'
# 载入映射
fmap_raw = json.load(open(BASE + r'\fontmap.json', encoding='utf-8'))
PUA = {int(k, 16): v['char'] for k, v in fmap_raw.items() if v and v.get('char')}
# 词级修正
PHRASES = [
    ('领生', '领主'), ('玩成', '玩家'), ('他下城', '地下城'), ('加鲁鲁', '鲁鲁'),
    ('下可名状', '不可名状'), ('下仁', '不仁'), ('下是', '不是'), ('下下下', '不不不'),
    ('神为', '神力'), ('能为各异', '能力各异'), ('矢控', '失控'), ('座兴', '高兴'),
    ('菲尔得', '菲尔德'), ('之他', '之地'), ('女生', '女主'), ('都恃么', '都什么'),
    ('绐我', '给我'), ('力了', '为了'), ('于力', '于为'), ('战为', '战力'), ('为量', '力量'),
    ('这他', '这地'), ('他梦', '地梦'), ('他方', '地方'), ('他区', '地区'),
    ('冉己', '自己'), ('冉救', '自救'), ('中主', '中众'), ('主命', '生命'),
    ('主活', '生活'), ('主级', '升级'), ('蜀醒', '觉醒'), ('笕醒', '觉醒'),
    ('也界', '世界'), ('异也', '异世'), ('也纪', '世纪'),
    ('迭个', '这个'), ('迭样', '这样'), ('迭么', '这么'), ('迭群', '这群'),
    ('迭只', '这只'), ('迭些', '这些'), ('迭里', '这里'), ('迭日子', '这日子'),
    ('伴么', '什么'), ('两幻', '奇幻'), ('讦始', '开始'), ('讦局', '开局'),
    ('讦了挂', '开了挂'), ('牛存', '生存'), ('转牛', '转生'), ('求牛', '求生'),
    ('女武牛', '女武神'), ('一—', '一'), ('一一', '——'), ('圣高', '圣座'),
    ('巫扼', '巫祝'), ('奸消息', '好消息'), ('幸福美奸', '幸福美好'), ('攫为', '攫为'),
    ('蜀中', '梦中'), ('中纪', '世纪'), ('半知识', '半点知识'), ('半院', '学院'),
    ('半习', '学习'), ('耍送', '要送'), ('只耍', '只要'), ('耍绐', '要给'),
    ('耍找', '要找'), ('耍靠', '要靠'), ('本以力', '本以为'), ('以力', '以为'),
    ('成力', '成为'), ('就耍', '就要'), ('更耍', '更要'), ('首耍', '首要'),
    ('顶不', '顶上'), ('不阴', '不明'), ('阴也界', '阴影世界'), ('阴白', '明白'),
    ('阴光', '阳光'), ('一阴', '一明'), ('光暗', '光明'), ('聊', '哪'),
    ('眶前', '眼前'), ('坏笑', '坏笑'), ('两尔维娅', '西尔维娅'), ('拉图尔', '拉图尔'),
    ('芳', '岁'), ('主长', '生长'), ('主神云', '主神云'), ('目光无奈', '目光无奈'),
    ('地龙首', '他龙首'), ('地哈哈', '他哈哈'), ('地摇头', '他摇头'), ('地微笑', '他微笑'),
    ('地转身', '他转身'), ('地发现', '他发现'), ('地决定', '他决定'), ('地笑', '他笑'),
    ('地点头', '他点头'), ('地伸手', '他伸手'), ('地蹲', '他蹲'), ('地站', '他站'),
    ('台他', '台地'), ('贵地', '贵地'), ('大地', '大地'), ('地不城', '地下城'),
    ('地精', '地精'), ('地勤', '地勤'), ('基地', '基地'), ('夜里', '夜里'),
]
# 单字修正（仅当出现于词短语未覆盖时）
CHARFIX = {'畀': '界', '讦': '开', '幺': '么', '酉': '奇', '忡': '种', '—': '一', '凹': '四', '高': '座'}

def decode(s):
    out = []
    for c in s:
        o = ord(c)
        if 0xE000 <= o <= 0xF8FF:
            out.append(PUA.get(o, '?'))
        else:
            out.append(c)
    t = ''.join(out)
    for a, b in PHRASES:
        t = t.replace(a, b)
    return t

def parse_snapshot(path, url_tag):
    txt = open(path, encoding='utf-8').read()
    books = []
    # 每本书：heading → title link → author link + text → desc text → 状态/在读/更新
    pattern = re.compile(
        r'heading "(\d+)" \[e\d+\] level=1\s*\n'
        r'link "([^"]+)" \[e\d+\] url=/page/(\d+)\s*\n'
        r'link "([^"]+)" \[e\d+\] url=/author-page/\d+\s*\n'
        r'\s*text "([^"]+)" \[e\d+\]\s*\n'
        r'text "([^"]+)" \[e\d+\]'
    )
    for m in pattern.finditer(txt):
        books.append({
            'rank': int(m.group(1)),
            'title': decode(m.group(2)),
            'book_id': m.group(3),
            'author_pua': m.group(4),
            'author': decode(m.group(5)),
            'desc': decode(m.group(6)),
        })
    # 不足时用宽松模式补充（书名+链接）
    if not books:
        pat2 = re.compile(r'link "([^"]+)" \[e\d+\] url=/page/(\d+)')
        seen = set()
        for m in pat2.finditer(txt):
            t = decode(m.group(1))
            pid = m.group(2)
            if pid in seen:
                continue
            seen.add(pid)
            books.append({'rank': len(books)+1, 'title': t, 'book_id': pid, 'author': '', 'desc': ''})
    return {
        'url_tag': url_tag,
        'source': os.path.basename(path),
        'books': books,
    }

if __name__ == '__main__':
    path, tag = sys.argv[1], sys.argv[2]
    data = parse_snapshot(path, tag)
    out = BASE + r'\captures\parsed_' + tag + '.json'
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(data, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('books:', len(data['books']), '->', out)
    for b in data['books']:
        print(b['rank'], b['title'], '|', b['author'])