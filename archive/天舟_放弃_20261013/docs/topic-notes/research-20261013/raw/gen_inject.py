import json
m = json.load(open(r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw\fontmap.json', encoding='utf-8'))
pairs = []
for k, v in m.items():
    if v and v.get('char'):
        pairs.append([int(k, 16), v['char']])
js = 'window.__FM = ' + json.dumps(pairs, ensure_ascii=False) + ';' + \
    'window.__dec = function(s){ var mm = {}; window.__FM.forEach(function(p){ mm[p[0]] = p[1]; });' \
    ' var out = ""; for (var i = 0; i < s.length; i++) { var c = s.charCodeAt(i); out += mm[c] || s[i]; } return out; };' \
    + "'FM_LOADED ' + window.__FM.length"
open(r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw\inject_fm.js', 'w', encoding='utf-8').write(js)
print('js length', len(js), 'pairs', len(pairs))