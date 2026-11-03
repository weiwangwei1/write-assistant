# -*- coding: utf-8 -*-
"""最终映射：fontmap + 语义修正（解析书名为金标准迭代）"""
import json

BASE = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw'
m = json.load(open(BASE + r'\fontmap.json', encoding='utf-8'))
fmap = {int(k, 16): v['char'] for k, v in m.items() if v and v.get('char')}

# 语义修正表（基于书名解码结果判定：正确字符 → 替换错误字符）
# 键是"当前错误字符"，值是"正确字符"
fix_char = {
    '圣高': '圣座',      # 登顶圣座
    '畀': '界',          # 世界/异世界/万界
    '半知识': '半点知识', # 你半点知识
    '讦': '开',          # 开局/开始/开挂
    '牛': '生',          # 牛存指南→生存指南; 转牛成→转生; 女武牛→? 待验证
    '幺': '么',          # 怎幺→怎么/什么
    '死': '定',          # 必死→必定（待验证：必死也通，看简介）
    '半院': '学院',      # 半院→学院
    '巫扼': '巫祝?',     # 待验证
    '酉幻': '奇幻',      # 酉→奇
    '—': '一',           # 我有—本→有一本; 绿龙的我屑—点→一点
    '屑': '废',          # 我屑—点→我废一点？待验证
    '太小姐': '大小姐',  # 贵族太小姐→大小姐
    '贵族太': '贵族大',
    '家': '成',          # 我俩家居然→我俩成居然？待验证。也可能是"我哥"
    '忡': '种',          # 忡出灾厄→种出
    '求牛': '求生',      # 永夜求生
    '女武牛': '女武神',
    '半': '学',          # 备用
}
# 字符级修正（更精确）
char_fix = str.maketrans({
    '畀': '界', '讦': '开', '牛': '生', '幺': '么', '酉': '奇',
    '—': '一', '太': '大', '忡': '种', '扼': '祝', '高': '座',
})
# 单字修正里先只保留高置信的：畀→界 讦→开 幺→么 酉→奇 忡→种 —→一
char_fix = str.maketrans({'畀': '界', '讦': '开', '幺': '么', '酉': '奇', '忡': '种', '—': '一'})

def decode(s):
    out = []
    for c in s:
        o = ord(c)
        out.append(fmap.get(o, '?') if 0xE000 <= o <= 0xF8FF else c)
    t = ''.join(out)
    return t.translate(char_fix)

import re
log = r'c:\Users\王伟\AppData\Local\Temp\trae\browser-logs\snapshot-2026-10-13T07-56-28-290Z.log'
txt = open(log, encoding='utf-8').read()
ties = re.findall(r'link "([^"]{2,40})" \[e\d+\] url=/page/(\d+)', txt)
# 简介文本（text "..."）
descs = re.findall(r'^text "([^"]{50,})" \[e\d+\]', txt, re.M)
print('--- titles ---')
for name, pid in ties:
    print(decode(name), '|', pid)
print()
print('--- desc sample (5) ---')
for d in descs[:5]:
    print(decode(d)[:200])
    print()