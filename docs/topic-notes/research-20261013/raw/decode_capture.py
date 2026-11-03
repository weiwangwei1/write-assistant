# -*- coding: utf-8 -*-
"""把含 \uXXXX 转义的捕获文本解码为明文（用 fontmap 还原 PUA）"""
import json
import sys
import re

BASE = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw'

def load_map():
    m = json.load(open(BASE + r'\fontmap.json', encoding='utf-8'))
    return {int(k, 16): v['char'] for k, v in m.items() if v and v.get('char')}

def decode_file(path, out_path):
    raw = open(path, encoding='utf-8').read()
    # 先处理 \uXXXX（JS 转义）
    def sub_u(mo):
        return chr(int(mo.group(1), 16))
    text = re.sub(r'\\u([0-9a-fA-F]{4})', sub_u, raw)
    text = text.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
    fmap = load_map()
    out = []
    hit = 0
    for c in text:
        o = ord(c)
        if 0xE000 <= o <= 0xF8FF:
            out.append(fmap.get(o, c))
            hit += 1
        else:
            out.append(c)
    res = ''.join(out)
    open(out_path, 'w', encoding='utf-8').write(res)
    print('decoded', path, '->', out_path, '| pua replaced:', hit)

if __name__ == '__main__':
    decode_file(sys.argv[1], sys.argv[2])