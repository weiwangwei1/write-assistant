# -*- coding: utf-8 -*-
"""解析 evaluate 落盘日志 → 汇总榜单（解码 PUA）"""
import json
import re
import os
import sys

BASE = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw'
fmap_raw = json.load(open(BASE + r'\fontmap.json', encoding='utf-8'))
PUA = {int(k, 16): v['char'] for k, v in fmap_raw.items() if v and v.get('char')}

PHRASES = [
    ('领生', '领主'), ('玩成', '玩家'), ('他下城', '地下城'), ('加鲁鲁', '鲁鲁兽'),
    ('下可名状', '不可名状'), ('下仁', '不仁'), ('下是', '不是'), ('下下下', '不不不'),
    ('神为', '神力'), ('能为各异', '能力各异'), ('矢控', '失控'), ('座兴', '高兴'),
    ('菲尔得', '菲尔德'), ('之他', '之地'), ('女生', '女主'), ('绐我', '给我'),
    ('力了', '为了'), ('于力', '于为'), ('战为', '战力'), ('为量', '力量'),
    ('这他', '这地'), ('他方', '地方'), ('他区', '地区'), ('冉己', '自己'), ('冉救', '自救'),
    ('主命', '生命'), ('主活', '生活'), ('主级', '升级'), ('主存', '生存'), ('主神', '主神'),
    ('蜀醒', '觉醒'), ('也界', '世界'), ('异也', '异世'), ('也纪', '世纪'), ('世畀', '世界'),
    ('迭个', '这个'), ('迭样', '这样'), ('迭么', '这么'), ('迭群', '这群'), ('迭只', '这只'),
    ('迭些', '这些'), ('迭里', '这里'), ('迭本', '这本'), ('伴么', '什么'), ('讦始', '开始'),
    ('讦局', '开局'), ('牛存', '生存'), ('转牛', '转生'), ('求牛', '求生'), ('女武牛', '女武神'),
    ('一一', '——'), ('圣高', '圣座'), ('巫扼', '巫祝'), ('奸消息', '好消息'),
    ('半知识', '半点知识'), ('半院', '学院'), ('半习', '学习'), ('耍送', '要送'), ('只耍', '只要'),
    ('耍绐', '要给'), ('耍找', '要找'), ('耍靠', '要靠'), ('耍求', '要求'), ('耍去', '要去'),
    ('本以力', '本以为'), ('以力', '以为'), ('成力', '成为'), ('就耍', '就要'), ('首耍', '首要'),
    ('更耍', '更要'), ('不阴', '不明'), ('阴白', '明白'), ('阴光', '阳光'), ('阴也界', '阴影世界'),
    ('眶前', '眼前'), ('目光无奈', '目光无奈'), ('地哈哈', '他哈哈'), ('地摇头', '他摇头'),
    ('地微笑', '他微笑'), ('地转身', '他转身'), ('地发现', '他发现'), ('地决定', '他决定'),
    ('地点头', '他点头'), ('地伸手', '他伸手'), ('地蹲', '他蹲'), ('地站', '他站'),
    ('地龙首', '他龙首'), ('地不城', '地下城'), ('制佯', '制作'), ('佯力', '作为'),
    ('逞威', '逞威'), ('世间', '世间'), ('半师傅', '半师傅'), ('杨帆', '杨帆'),
]
CHARFIX = {'畀': '界', '讦': '开', '幺': '么', '酉': '奇', '忡': '种', '—': '一', '凹': '四',
           '也': '世', '力': '为', '主': '生', '犬': '大', '两': '奇', '迭': '这', '冉': '自',
           '奸': '好', '恃': '是', '地': '他', '笕': '觉', '迸': '之', '佯': '作', '厘': '定',
           '焦': '信', '芳': '分', '氕': '气', '乩': '竞', '扼': '祝', '屑': '废', '家': '成',
           '请': '情', '德': '得', '关': '天', '牛': '生',
           '妇': '如', '眶': '眼', '罗': '岁', '耍': '要', '悝': '被', '闽': '哪'}

def decode(s):
    out = []
    for c in s:
        o = ord(c)
        out.append(PUA.get(o, c) if 0xE000 <= o <= 0xF8FF else c)
    t = ''.join(out)
    for a, b in PHRASES:
        t = t.replace(a, b)
    return t.translate(str.maketrans(CHARFIX))

def main():
    path = sys.argv[1]
    raw = open(path, encoding='utf-8').read()
    # 落盘文件是「JSON 字符串」：先外层 decode 再内层
    try:
        inner = json.loads(raw)
    except Exception:
        inner = raw
    if isinstance(inner, str):
        data = json.loads(inner)
    else:
        data = inner
    if isinstance(data, dict):
        data = [data]
    all_books = []
    for grp in data:
        tag = grp['tag']
        for it in grp['items']:
            ctx = it.get('c', '')
            # 从 ctx 解析：desc / read / status
            m_read = re.search(r'在读：\s*([\d.]+万?)', ctx)
            read = m_read.group(1) if m_read else ''
            m_status = re.search(r'(连载中|已完结)', ctx)
            status = m_status.group(1) if m_status else ''
            # desc = ctx 去掉 "NN-" 前缀与尾部 连载中在读... 段
            body = re.sub(r'^\d+[-]?', '', ctx)
            body = re.sub(r'(连载中|已完结)在读：.*$', '', body, flags=re.S)
            body = re.sub(r'最近更新：.*$', '', body, flags=re.S)
            all_books.append({
                'tag': tag, 'rank': it.get('r'), 'title': decode(it.get('t', '')),
                'book_id': (it.get('h', '') or '').split('/')[-1],
                'desc': decode(body).strip(), 'read': read, 'status': status,
            })
    out = BASE + r'\captures\rank_all.json'
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(all_books, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('books:', len(all_books))
    tags = {}
    for b in all_books:
        tags[b['tag']] = tags.get(b['tag'], 0) + 1
    print('by tag:', tags)
    for b in all_books[:6]:
        print(b['tag'], b['rank'], b['title'], '|', b['read'], b['status'])
        print('   ', b['desc'][:120])

if __name__ == '__main__':
    main()