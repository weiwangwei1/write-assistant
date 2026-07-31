# -*- coding: utf-8 -*-
"""构造盲测 v4（同剧情仿写版）：6 题，原作段 vs 我们写手同剧情仿写段

无情节泄露：两段讲同一件事，用户只能靠风格判断。
输出：blind_test.md（问卷）+ blind_answers.json（答案）
"""
import json, io, sys, random, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

random.seed(20260731)
BASE = 'test/style_lab'

def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)

def load_book(name):
    path = {
        '狩魔': '.trae/skills/writer-styles/yanyujiangnan/reference/原作/《狩魔手记》（校对版全本）作者：烟雨江南.txt',
        '罪恶': '.trae/skills/writer-styles/yanyujiangnan/reference/原作/《罪恶之城》（校对版全本）作者：烟雨江南.txt',
        '永夜': '.trae/skills/writer-styles/yanyujiangnan/reference/原作/《永夜君王》（校对版全本）作者：烟雨江南.txt',
    }[name]
    with open(path, 'rb') as f:
        raw = f.read()
    for enc in ['utf-8', 'gbk', 'gb18030']:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise RuntimeError('decode failed')

# ---- 读仿写 6 段（去掉标题行） ----
with open(f'{BASE}/blind_imitations.md', encoding='utf-8') as f:
    imit_md = f.read()
sections = re.split(r'^## \d+\.', imit_md, flags=re.M)[1:]
imit = []
for s in sections:
    s = s.strip()
    # 去掉首行的标题（如 "battle（仿写：狼人 vs 宋子宁）"）
    lines = s.split('\n')
    while lines and ('（仿写' in lines[0] or lines[0].strip() == '' or not lines[0].strip()):
        lines.pop(0)
    imit.append('\n'.join(lines).strip())

# ---- 读原作 6 段 ----
sm, ez, yy = load_book('狩魔'), load_book('罪恶'), load_book('永夜')

def cut_book(text, marker, max_len=620):
    i = text.find(marker)
    if i < 0:
        raise ValueError('marker not found: ' + marker)
    j = text.rfind('\n', 0, i)
    seg = text[j:j + max_len]
    k = seg.rfind('。', 0, len(seg))
    if k > max_len * 0.7:
        seg = seg[:k + 1]
    return seg.strip()

samples = {}
for scene in ['battle', 'dialogue', 'environment', 'psychology']:
    d = load(f'{BASE}/few_shot_samples/yanyujiangnan/{scene}.json')
    samples[scene] = d['samples']

orig = [
    samples['battle'][5]['text'].strip(),                     # 1. 狼人刺宋子宁
    samples['psychology'][0]['text'].strip(),                 # 2. 夜瞳/青之君王
    cut_book(sm, '这样一片地方，五十年前叫做废墟', 600),      # 3. 废墟萤火
    samples['psychology'][2]['text'].strip(),                 # 4. 朱姬走神
    cut_book(sm, '女人冲了进来', 620),                        # 5. 母亲之死
    cut_book(ez, '伊兰妮忽然站了起来，说', 560),              # 6. 歌顿篝火
]

labels = ['battle', 'dialogue', 'environment', 'psychology', 'death', 'ending']
assert len(imit) == len(orig) == 6, (len(imit), len(orig))

# ---- 长度均衡：两段截到相近长度（消除长度干扰变量） ----
def normalize(short_text, long_text):
    """short 保持，long 截到 short 的 1.05-1.15 倍"""
    s = len(short_text.replace('\n', ''))
    l = len(long_text.replace('\n', ''))
    if l <= s * 1.25:
        return short_text, long_text
    target = int(s * 1.1)
    seg = long_text[:target]
    k = seg.rfind('。')
    if k > target * 0.6:
        seg = seg[:k + 1]
    return short_text, seg.strip()

pairs = []
for i in range(6):
    a, b = normalize(imit[i], orig[i]) if len(imit[i]) < len(orig[i]) else normalize(orig[i], imit[i])
    if len(imit[i]) < len(orig[i]):
        pairs.append((a, b))
    else:
        pairs.append((b, a))

# ---- 混排 6 题 ----
items = []
order = list(range(6))
random.shuffle(order)
for idx, i in enumerate(order):
    flip = random.random() < 0.5
    im_t, or_t = pairs[i]
    items.append({
        'id': idx + 1,
        'scene': labels[i],
        'a_is_original': flip,
        'a_chars': len((or_t if flip else im_t).replace('\n', '')),
        'b_chars': len((im_t if flip else or_t).replace('\n', '')),
    })
    print(f"题{idx+1} [{labels[i]}]: 原作{'A' if flip else 'B'} | A={items[-1]['a_chars']}字 B={items[-1]['b_chars']}字")

# ---- 写问卷 ----
lines = ['# 盲测：哪段是烟雨江南写的？（同剧情版）', '']
lines.append('> 每题两段（A/B）讲的是**同一件事**——一段是烟雨江南原笔，另一段是我们的 AI 写手按他的风格仿写。')
lines.append('> 剧情完全相同，只有文字不同。凭直觉选**更像是烟雨江南写的**那段。')
lines.append('> 规则：不要分析，凭第一感觉；每题限时约 30 秒；6 题一口气做完，中途不看答案。')
lines.append('')
for it in items:
    i = it['id'] - 1
    im_t, or_t = pairs[i]
    text_a, text_b = (or_t, im_t) if it['a_is_original'] else (im_t, or_t)
    lines.append(f"## 第 {it['id']} 题")
    lines.append('')
    lines.append(f'**A（{len(text_a.replace(chr(10),""))}字）**：')
    lines.append('')
    lines.append('> ' + text_a.replace('\n', '\n> '))
    lines.append('')
    lines.append(f'**B（{len(text_b.replace(chr(10),""))}字）**：')
    lines.append('')
    lines.append('> ' + text_b.replace('\n', '\n> '))
    lines.append('')
    lines.append('---')
    lines.append('')

lines.append('## 答案（对完再看）')
lines.append('')
lines.append('<details>')
lines.append('<summary>点击展开</summary>')
lines.append('')
for it in items:
    lines.append(f"- 第{it['id']}题（{it['scene']}）：原作是 {'A' if it['a_is_original'] else 'B'}")
lines.append('</details>')

with open(f'{BASE}/blind_test.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
with open(f'{BASE}/blind_answers.json', 'w', encoding='utf-8') as f:
    json.dump(items, f, ensure_ascii=False, indent=2)

print(f'\n已生成 blind_test.md（{len(items)} 题，同剧情仿写版）')
