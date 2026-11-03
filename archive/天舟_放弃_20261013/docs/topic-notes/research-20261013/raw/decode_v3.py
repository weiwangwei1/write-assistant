# -*- coding: utf-8 -*-
"""v3: 词级修正 + 完整榜单解码"""
import json
import re

BASE = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw'
m = json.load(open(BASE + r'\fontmap.json', encoding='utf-8'))
fmap = {int(k, 16): v['char'] for k, v in m.items() if v and v.get('char')}
# 词级修正（错误短语 → 正确短语），按长度优先
PHRASES = [
    ('领生', '领主'), ('玩成', '玩家'), ('主存', '生存'), ('主人云', '主神云?'),
    ('他下城', '地下城'), ('加鲁鲁兽', '鲁鲁兽'), ('下可名状', '不可名状'), ('下仁', '不仁'),
    ('下是', '不是'), ('下下下', '不不不'), ('神为', '神力'), ('能为各异', '能力各异'),
    ('矢控', '失控'), ('座兴', '高兴'), ('菲尔得', '菲尔德'), ('之他', '之地'),
    ('女生', '女主'), ('都恃么', '都什么'), ('是么', '什么'), ('绐我', '给我'),
    ('力了', '为了'), ('于力', '于为'), ('战为', '战力'), ('为量', '力量'),
    ('这他', '这地'), ('他梦', '地梦'), ('他方', '地方'), ('他区', '地区'),
    ('冉己', '自己'), ('冉救', '自救'), ('中主', '众生'), ('主命', '生命'),
    ('主活', '生活'), ('主存', '生存'), ('主级', '升级'),
    ('就完', '就完'), ('半知识', '半点知识'), ('半院', '学院'), ('半习', '学习'),
    ('蜀醒', '觉醒'), ('笕醒', '觉醒'), ('还剩', '还剩'),
    ('也界', '世界'), ('异也', '异世'), ('也纪', '世纪'),
    ('迭个', '这个'), ('迭样', '这样'), ('迭么', '这么'), ('迭群', '这群'),
    ('迭只', '这只'), ('迭些', '这些'), ('迭里', '这里'), ('迭日子', '这日子'),
    ('伴么', '什么'), ('两幻', '奇幻'), ('讦始', '开始'), ('讦局', '开局'),
    ('讦了挂', '开了挂'), ('牛存', '生存'), ('转牛', '转生'), ('求牛', '求生'),
    ('女武牛', '女武神'), ('一—', '一'), ('一一', '——'),
    ('圣高', '圣座'), ('巫扼', '巫祝'), ('杀就', '杀就'),
    ('奸消息', '好消息'), ('幸福美奸', '幸福美好'),
]

def decode(s):
    out = []
    for c in s:
        o = ord(c)
        out.append(fmap.get(o, c) if 0xE000 <= o <= 0xF8FF else c)
    t = ''.join(out)
    for a, b in PHRASES:
        t = t.replace(a, b)
    return t

log = r'c:\Users\王伟\AppData\Local\Temp\trae\browser-logs\snapshot-2026-10-13T07-56-28-290Z.log'
txt = open(log, encoding='utf-8').read()
titles = re.findall(r'link "([^"]{2,60})" \[e\d+\] url=/page/(\d+)', txt)
names = []
for t, pid in titles:
    if 'author-page' in t:
        continue
    names.append((decode(t), pid))
print('titles:', len(names))
for n, p in names:
    print(n)
print()
descs = re.findall(r'text "([^"]{60,})" \[e\d+\]', txt)
print('descs:', len(descs))
allb = []
for i, d in enumerate(descs):
    allb.append(decode(d))
# 输出完整解码
json.dump({'titles': names, 'descs': allb}, open(BASE + r'\western_decoded_v3.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
for i, d in enumerate(allb):
    print(f'--- desc {i} ---')
    print(d[:400])