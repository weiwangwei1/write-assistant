# -*- coding: utf-8 -*-
"""构造盲测 v5（同剧情仿写版，8 题）：原作段 vs 我们写手同剧情仿写段

v3 轮配置：
- 8 题全新场景（v1/v2 片段全部弃用）
- 含 2 题「丰盛组」对照（知识性展开段：构装骑士 / 绯月传说）
- 写手纪律升级：S1 信息点守恒 + 禁止逐句镜像 + 删解释句不删世界展开
- 问卷每题附「选择理由」栏，验证「读者记忆 vs 原作实际」假设
无情节泄露：两段讲同一件事，用户只能靠风格判断。
输出：blind_test.md（问卷）+ blind_answers.json（答案）
"""
import json, io, sys, random, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

random.seed(20260802)  # v3 轮：换 seed 重新混排
BASE = 'test/style_lab'

# ---- 读原作 8 段（blind_orig_v3.md，已提取干净） ----
with open(f'{BASE}/blind_orig_v3.md', encoding='utf-8') as f:
    orig_md = f.read()
orig_sections = re.split(r'^### ', orig_md, flags=re.M)[1:]
orig = []
for s in orig_sections:
    s = s.strip()
    # 去掉首行标题
    lines = s.split('\n')
    lines = lines[1:] if lines[0].startswith(('1_', '2_', '3_', '4_', '5_', '6_', '7_', '8_')) else lines
    text = '\n'.join(lines).strip()
    # 段5 卷入了「第十七章 毕业」章节标题行，裁掉
    text = re.sub(r'第十七章 毕业\n', '', text)
    orig.append(text)

# ---- 读仿写 8 段（去掉标题行） ----
with open(f'{BASE}/blind_imitations_v3.md', encoding='utf-8') as f:
    imit_md = f.read()
sections = re.split(r'^## \d+\.', imit_md, flags=re.M)[1:]
imit = []
for s in sections:
    s = s.strip()
    lines = s.split('\n')
    while lines and ('（仿写' in lines[0] or lines[0].strip() == ''):
        lines.pop(0)
    imit.append('\n'.join(lines).strip())

labels = ['lore_knight', 'lore_moon', 'battle', 'dialogue', 'psychology', 'environment', 'death', 'ending']
assert len(imit) == len(orig) == 8, (len(imit), len(orig))
for i in range(8):
    print(f'{labels[i]}: 仿写{len(imit[i])}字 vs 原作{len(orig[i])}字')

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
for i in range(8):
    if len(imit[i]) < len(orig[i]):
        a, b = normalize(imit[i], orig[i])
        pairs.append((a, b))
    else:
        a, b = normalize(orig[i], imit[i])
        pairs.append((b, a))

# ---- 混排 8 题 ----
items = []
order = list(range(8))
random.shuffle(order)
for idx, i in enumerate(order):
    flip = random.random() < 0.5
    im_t, or_t = pairs[i]
    items.append({
        'id': idx + 1,
        'orig_index': i,          # 原始 index：写问卷/对答案必须用它索引 pairs
        'scene': labels[i],
        'a_is_original': flip,
        'a_chars': len((or_t if flip else im_t).replace('\n', '')),
        'b_chars': len((im_t if flip else or_t).replace('\n', '')),
    })
    print(f"题{idx+1} [{labels[i]}]: 原作{'A' if flip else 'B'} | A={items[-1]['a_chars']}字 B={items[-1]['b_chars']}字")

# ---- 写问卷 ----
lines = ['# 盲测 v3：哪段是烟雨江南写的？（同剧情版）', '']
lines.append('> 每题两段（A/B）讲的是**同一件事**——一段是烟雨江南原笔，另一段是我们的 AI 写手按他的风格仿写。')
lines.append('> 剧情完全相同，只有文字不同。凭直觉选**更像是烟雨江南写的**那段。')
lines.append('> 规则：不要分析，凭第一感觉；每题限时约 30 秒；8 题一口气做完，中途不看答案。')
lines.append('> 每题下面附一行「为什么选它」——**答完再回想**，一句话即可（帮我们定位你的判断依据）。')
lines.append('')
for it in items:
    i = it['orig_index']
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
    lines.append(f'▸ 为什么选它（可选，一句话）：')
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

print(f'\n已生成 blind_test.md（{len(items)} 题，同剧情仿写版 v5）')
