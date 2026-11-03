# -*- coding: utf-8 -*-
"""从快照日志解码榜单文本（用 fontmap.json + 语义修正补充）"""
import json
import re

BASE = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw'
# 合并：fontmap.json 为主体，应用已人工/语义判定修正
m = json.load(open(BASE + r'\fontmap.json', encoding='utf-8'))
fmap = {int(k, 16): v['char'] for k, v in m.items() if v and v.get('char')}

# 已知语义修正（基于解码结果上下文人工判定）
corrections = {
    0xE3EA: '我',   # 原"主" → 我
    0xE3EB: '什',   # 原"恃" → 什
    0xE3EC: '成',   # 原"家" → 成
    0xE3EE: '没',   # 原"然" → （待验证，暂不动）
}
# 暂不做未验证修正，改用第二版差异表高置信项
m3 = json.load(open(BASE + r'\fontmap3.json', encoding='utf-8'))
# 高置信修正（iou >= 0.65 且语义合理）：从 diff 列表精选
high_conf = {0xE40B: '失', 0xE40C: '世', 0xE423: '太', 0xE448: '丨', 0xE452: '难',
             0xE460: '好', 0xE47C: '作', 0xE48E: '他', 0xE4C6: '原', 0xE4DE: '—',
             0xE4E7: '自', 0xE4EF: '宾', 0xE50E: '分', 0xE50F: '牛', 0xE511: '冉',
             0xE515: '酉', 0xE517: '忡', 0xE51C: '情', 0xE51E: '这', 0xE525: '觉',
             0xE52C: '夫', 0xE530: '信', 0xE531: '下', 0xE534: '巳', 0xE542: '大',
             0xE544: 'O', 0xE545: '起', 0xE551: '四', 0xE554: '巾', 0xE555: 'C',
             0xE447: '怏', 0xE462: 'u', 0xE471: '为', 0xE4F8: '迸', 0xE4FF: '讦',
             0xE53B: '叼', 0xE53C: '之', 0xE4AB: '定', 0xE4C0: '打', 0xE475: '彐'}
final = dict(fmap)
final.update(high_conf)

src = open(BASE + r'\snap_western.txt', encoding='utf-8').read() if False else None

def decode(s):
    out = []
    for c in s:
        o = ord(c)
        if 0xE000 <= o <= 0xF8FF:
            out.append(final.get(o, '?'))
        else:
            out.append(c)
    return ''.join(out)

# 解码快照日志中的书本条目
log = r'c:\Users\王伟\AppData\Local\Temp\trae\browser-logs\snapshot-2026-10-13T07-56-28-290Z.log'
txt = open(log, encoding='utf-8').read()
ties = re.findall(r'link "([^"]{2,40})" \[e\d+\] url=/page/(\d+)', txt)
print('\n--- books found:', len(ties))
for name, pid in ties:
    print(decode(name), '|', pid)