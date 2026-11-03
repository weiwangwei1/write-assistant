# -*- coding: utf-8 -*-
"""v2: 合并字体映射 + 语义修正 → final_fontmap.json，并解码奇幻榜存为 json"""
import json
import re

BASE = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw'
m = json.load(open(BASE + r'\fontmap.json', encoding='utf-8'))
fmap = {int(k, 16): v['char'] for k, v in m.items() if v and v.get('char')}

# 单字符层修正：错误字符 → 正确字符
CF = {
    '凹': '四', '高': '座', '也': '世', '力': '为', '半': '学', '不': '下',
    '主': '生', '犬': '大', '两': '奇', '迭': '这', '冉': '自', '奸': '好',
    '恃': '是', '地': '他', '笕': '觉', '迸': '之', '佯': '作', '厘': '定',
    '焦': '信', '芳': '分', 'I': '1', 'i': '1', '氕': '气', '乩': '竞',
    '扼': '祝', '幺': '么', '屑': '废', '家': '成', '请': '情', '恸': '种',
    '忡': '种', '走': '定', '德': '得', '关': '天', '牛': '生', '讦': '开',
    '胀': '涨', '弟': '第', '图': '图', '畀': '界', '莽': '恭',
    # 冒号/引号等由原文保留
}
# 先建立"字符→字符"翻译：把 PUA 映射出的字再按 CF 修正
trans = {}
for cp, ch in fmap.items():
    trans[cp] = CF.get(ch, ch)
json.dump({str(k): v for k, v in sorted(trans.items())}, open(BASE + r'\final_fontmap.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def decode(s):
    return ''.join(trans.get(ord(c), c) if 0xE000 <= ord(c) <= 0xF8FF else c for c in s)

log = r'c:\Users\王伟\AppData\Local\Temp\trae\browser-logs\snapshot-2026-10-13T07-56-28-290Z.log'
txt = open(log, encoding='utf-8').read()
# 解析书本结构
blocks = re.findall(r'heading "(\d+)" \[e\d+\] level=1\nlink "([^"]+)" \[e\d+\] url=/page/(\d+)\nlink "([^"]+)" \[e\d+\] url=/author-page/(\d+)\n  text "([^"]+)" \[e\d+\]\ntext "([^"]+)" \[e\d+\]', txt)
print('blocks:', len(blocks))
books = []
for rank, title, pid, _, aid, author, _ in blocks:
    books.append({'rank': rank, 'title': decode(title), 'author': decode(author), 'book_id': pid})
for b in books:
    print(b['rank'], b['title'], '|', b['author'])
# 简介：紧跟 author 行后的长 text
descs = re.findall(r'text "([^"]{60,})" \[e\d+\]', txt)
dlist = []
for d in descs:
    dd = decode(d)
    dlist.append(dd)
json.dump({'books': books, 'descs': dlist}, open(BASE + r'\rank_western_decoded.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('saved rank_western_decoded.json')
for i, d in enumerate(dlist[:3]):
    print('---', i, '---')
    print(d[:260])