# -*- coding: utf-8 -*-
"""番茄深读样本的章节结构统计"""
import os
import re

BASE = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw\captures'
p = BASE + r'\fanqie_city_rebirth.txt'
txt = open(p, encoding='utf-8').read()
chs = txt.split('=' * 40)
print('章节数:', len(chs))
for i, c in enumerate(chs, 1):
    c = c.strip()
    print('第%d章 字数=%d' % (i, len(c)))
print()
print('=== 第1章开篇前两段 ===')
paras = [x for x in chs[0].strip().split('\n') if x.strip()]
for x in paras[:2]:
    print(x[:200])
print()
print('=== 第1章结尾（章末钩子）===')
print(paras[-1][:200])
print()
print('=== 第10章结尾 ===')
p10 = [x for x in chs[-1].strip().split('\n') if x.strip()]
print(p10[-1][:200])