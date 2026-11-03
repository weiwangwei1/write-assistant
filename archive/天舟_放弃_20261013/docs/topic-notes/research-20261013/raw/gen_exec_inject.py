import json
m = json.load(open(r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw\fontmap.json', encoding='utf-8'))
pairs = [[int(k, 16), v['char']] for k, v in m.items() if v and v.get('char')]
# 生成紧凑 JS 字面量（数组对）供 Exec 注入
arr = ','.join('[%d,"%s"]' % (cp, ch.replace('\\', '\\\\').replace('"', '\\"')) for cp, ch in pairs)
js = 'window.__FM=[' + arr + '];window.__dec=(function(){var mm={};window.__FM.forEach(function(p){mm[p[0]]=p[1]});return function(s){var o="";for(var i=0;i<s.length;i++){var c=s.charCodeAt(i);o+=mm[c]||s[i]}return o}})();"FM_OK "+window.__FM.length'
open(r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw\exec_inject.txt', 'w', encoding='utf-8').write(js)
print(js[:200])
print('...len', len(js))