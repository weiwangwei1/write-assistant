import sys
p = r'c:\Users\王伟\AppData\Local\Temp\trae\browser-logs\evaluate-2026-10-13T08-12-17-135Z.log'
d = open(p, encoding='utf-8', errors='ignore').read()
print('len', len(d))
print('HEAD:', repr(d[:200]))
print('TAIL:', repr(d[-200:]))
idx = d.find('"tag"')
print('idx of "tag":', idx)
print('around:', repr(d[max(0,idx-30):idx+50]))
print('count tag:', d.count('"tag"'))
print('count backslash-tag:', d.count('\\"tag\\"'))