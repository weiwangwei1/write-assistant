# -*- coding: utf-8 -*-
"""宽容版快照解析：按 heading 区块切分，提取书目全字段"""
import json
import re
import os
import sys

BASE = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw'
fmap_raw = json.load(open(BASE + r'\fontmap.json', encoding='utf-8'))
PUA = {int(k, 16): v['char'] for k, v in fmap_raw.items() if v and v.get('char')}
CHARFIX = {'畀': '界', '讦': '开', '幺': '么', '酉': '奇', '忡': '种', '—': '一', '凹': '四',
           '也': '世', '力': '为', '主': '生', '犬': '大', '两': '奇', '迭': '这', '冉': '自',
           '奸': '好', '恃': '是', '地': '他', '笕': '觉', '迸': '之', '佯': '作', '厘': '定',
           '焦': '信', '芳': '分', '氕': '气', '乩': '竞', '扼': '祝', '屑': '废', '家': '成',
           '请': '情', '德': '得', '关': '天', '牛': '生', '高': '座', 'i': '1', 'I': '1'}

def decode(s):
    out = []
    for c in s:
        o = ord(c)
        out.append(PUA.get(o, c) if 0xE000 <= o <= 0xF8FF else c)
    t = ''.join(out)
    # 高频词修正（先词后字）
    for a, b in [('领生', '领主'), ('玩成', '玩家'), ('他下城', '地下城'), ('下可名状', '不可名状'),
                 ('下是', '不是'), ('下下下', '不不不'), ('神为', '神力'), ('矢控', '失控'),
                 ('座兴', '高兴'), ('之他', '之地'), ('女生', '女主'), ('绐我', '给我'),
                 ('力了', '为了'), ('于力', '于为'), ('战为', '战力'), ('为量', '力量'),
                 ('这他', '这地'), ('他梦', '地梦'), ('他方', '地方'), ('他区', '地区'),
                 ('主命', '生命'), ('主活', '生活'), ('主级', '升级'), ('主存', '生存'),
                 ('蜀醒', '觉醒'), ('也界', '世界'), ('异也', '异世'), ('也纪', '世纪'),
                 ('迭个', '这个'), ('迭样', '这样'), ('迭么', '这么'), ('迭群', '这群'),
                 ('迭只', '这只'), ('迭些', '这些'), ('迭里', '这里'), ('伴么', '什么'),
                 ('讦始', '开始'), ('讦局', '开局'), ('牛存', '生存'), ('转牛', '转生'),
                 ('求牛', '求生'), ('女武牛', '女武神'), ('一一', '——'), ('圣高', '圣座'),
                 ('巫扼', '巫祝'), ('奸消息', '好消息'), ('幸福美奸', '幸福美好'),
                 ('半知识', '半点知识'), ('半院', '学院'), ('半习', '学习'), ('耍送', '要送'),
                 ('只耍', '只要'), ('耍绐', '要给'), ('耍找', '要找'), ('耍靠', '要靠'),
                 ('本以力', '本以为'), ('以力', '以为'), ('成力', '成为'), ('就耍', '就要'),
                 ('首耍', '首要'), ('不阴', '不明'), ('阴白', '明白'), ('阴光', '阳光'),
                 ('眶前', '眼前'), ('目光无奈', '目光无奈'), ('地哈哈', '他哈哈'),
                 ('地摇头', '他摇头'), ('地微笑', '他微笑'), ('地转身', '他转身'),
                 ('地发现', '他发现'), ('地决定', '他决定'), ('地点头', '他点头'),
                 ('地伸手', '他伸手'), ('地蹲', '他蹲'), ('地站', '他站'), ('地龙首', '他龙首'),
                 ('地不城', '地下城'), ('制佯', '制作')]:
        t = t.replace(a, b)
    return t.translate(str.maketrans(CHARFIX))

def parse(path, tag):
    txt = open(path, encoding='utf-8').read()
    # 找书区块的起点（banner 之后）
    idx = txt.find('banner [e')
    if idx > 0:
        txt = txt[idx:]
    blocks = re.split(r'heading "(\d+)" \[e\d+\] level=1', txt)
    books = []
    for i in range(1, len(blocks) - 1, 2):
        rank = int(blocks[i])
        chunk = blocks[i + 1]
        m_title = re.search(r'link "([^"]+)" \[e\d+\] url=/page/(\d+)', chunk)
        if not m_title:
            continue
        title = decode(m_title.group(1))
        pid = m_title.group(2)
        m_author = re.search(r'url=/author-page/\d+\s*\n\s*text "([^"]+)"', chunk)
        author = decode(m_author.group(1)) if m_author else ''
        m_desc = re.search(r'text "([^"]{40,})"', chunk)
        desc = decode(m_desc.group(1)) if m_desc else ''
        m_read = re.search(r'在读：\s*([\d.]+万?)', chunk)
        read = m_read.group(1) if m_read else ''
        m_status = re.search(r'text "([^"]*?(?:连载中|已完结))"', chunk)
        status = m_status.group(1) if m_status else ''
        books.append({'rank': rank, 'title': title, 'book_id': pid,
                      'author': author, 'desc': desc, 'read': read, 'status': status})
    return {'tag': tag, 'source': os.path.basename(path), 'books': books}

if __name__ == '__main__':
    path, tag = sys.argv[1], sys.argv[2]
    data = parse(path, tag)
    os.makedirs(BASE + r'\captures', exist_ok=True)
    out = BASE + r'\captures\parsed_' + tag + '.json'
    json.dump(data, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('books:', len(data['books']))
    for b in data['books']:
        print(b['rank'], b['title'], '| 在读', b['read'], '|', b['status'])
    # 打印前2本简介
    for b in data['books'][:2]:
        print('--- desc ---')
        print(b['desc'][:350])