import json
from fontTools.ttLib import TTFont

f = TTFont(r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw\font_body.woff2')
print('tables:', sorted(f.keys()))
cmap = f.getBestCmap()
items = sorted(cmap.items())
print('cmap size:', len(items))
pua = [(hex(k), v) for k, v in items if 0xE000 <= k <= 0xF8FF]
print('PUA count:', len(pua))
print('first 40:', pua[:40])
# glyph name → order check
names = [v for k, v in items]
print('sample glyph names:', names[:20])
# check all codes
allcodes = [k for k, v in items]
print('min/max code:', hex(min(allcodes)), hex(max(allcodes)))
out = {str(k): v for k, v in items}
json.dump(out, open(r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw\cmap.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('saved cmap.json')