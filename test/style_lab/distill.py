#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
distill.py — 深度文风蒸馏脚本 v1.0

在 style_fingerprint.py v2.0（16标量+2向量）基础上，对6位作者原作进行8阶段递进分析：
  P1 基础指纹  P2 句式模式  P3 段落节奏  P4 意象通道
  P5 对话风格  P6 修辞比喻  P7 叙述技法  P8 跨作者对比

每阶段完成后立即写入 distill_state.json，面板可实时读取状态。

用法：
  cd d:\\personFile\\write-assist\\write-assistant
  python test/style_lab/distill.py                 # 全量运行
  python test/style_lab/distill.py --author yanyujiangnan  # 只跑一位作者
  python test/style_lab/distill.py --phase p4      # 只跑一个阶段
"""

import sys, os, re, json, math, time
from datetime import datetime
from collections import Counter, defaultdict

# 添加项目根目录到 path（复用 style_fingerprint.py）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from style_fingerprint import (
    extract_features, split_sents, split_paras, han_count,
    SENSORY_WORDS, FUNC_WORDS, CONJ_STARTERS, METAPHOR_MARKERS,
    SIMILE_EXCLUDE_FP, count_metaphors, count_dash, dialogue_char_count,
    extract_sensory_dist, sensory_cosine_dist, cosine_dist,
    extract_imagery_top, STOP_CHARS_NGRAM
)

# ============================================================
# 路径与状态管理
# ============================================================

LAB_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(LAB_DIR, "distill_config.json")
STATE_PATH = os.path.join(LAB_DIR, "distill_state.json")
REPORT_DIR = os.path.join(LAB_DIR, "reports")

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_state(state):
    state["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ============================================================
# 文本加载与采样
# ============================================================

def load_author_text(author_cfg):
    """加载作者原作并采样到指定字数"""
    target = author_cfg.get("sample_chars", 500000)
    chunks = []
    total = 0
    for rel_path in author_cfg["works"]:
        full_path = os.path.join(PROJECT_ROOT, rel_path)
        if not os.path.exists(full_path):
            print(f"  [skip] 文件不存在: {rel_path}")
            continue
        # 尝试 UTF-8，失败则 GBK
        text = None
        for enc in ("utf-8", "gbk", "utf-16"):
            try:
                with open(full_path, "r", encoding=enc) as f:
                    text = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        if text is None:
            print(f"  [skip] 编码失败: {rel_path}")
            continue
        # 去掉章节标题行等非正文
        lines = [l.strip() for l in text.splitlines()
                 if l.strip() and not re.match(r"^(第\d+章|字数|—{3,}|-{3,}| Chapter|CHAPTER)", l.strip())]
        cleaned = "\n".join(lines)
        chunks.append(cleaned)
        total += han_count(cleaned)
        if total >= target:
            break

    body = "\n".join(chunks)
    # 均匀采样到目标字数
    if han_count(body) > target:
        paras = split_paras(body)
        selected = []
        char_count = 0
        step = max(1, len(paras) // (target // 60))  # 大约每60字一段
        for i in range(0, len(paras), step):
            selected.append(paras[i])
            char_count += han_count(paras[i])
            if char_count >= target:
                break
        body = "\n".join(selected)

    return body, han_count(body)

# ============================================================
# P1: 基础指纹（复用 style_fingerprint.py）
# ============================================================

def phase1_fingerprint(text, author_cfg):
    """复用 extract_features 提取16标量+2向量+意象Top20"""
    feats = extract_features(
        text,
        author=author_cfg["display_name"],
        exclude_names=author_cfg.get("exclude_names", []),
        with_imagery=True
    )
    # 选取关键维度用于面板展示
    key_metrics = {
        "sent_len_mean": feats["sent_len_mean"],
        "sent_len_stdev": feats["sent_len_stdev"],
        "short_sent_ratio": feats["short_sent_ratio"],
        "long_sent_ratio": feats["long_sent_ratio"],
        "para_len_mean": feats["para_len_mean"],
        "short_para_ratio": feats["short_para_ratio"],
        "dialogue_ratio": feats["dialogue_ratio"],
        "comma_period_ratio": feats["comma_period_ratio"],
        "dash_per_1000": feats["dash_per_1000"],
        "ellipsis_per_1000": feats["ellipsis_per_1000"],
        "metaphor_per_1000": feats["metaphor_per_1000"],
        "conjunction_starter_ratio": feats["conjunction_starter_ratio"],
        "dialogue_guide_per_1000": feats["dialogue_guide_per_1000"],
        "le_ending_ratio": feats["le_ending_ratio"],
        "sensory_dist": feats["sensory_dist"],
        "imagery_top20": feats.get("imagery_top20", []),
        "func_words": {k: v for k, v in feats.get("func_words_per_1000", {}).items()
                       if k in ("的", "了", "是", "不", "他", "她", "我", "你", "就", "也")},
        "sample_chars": feats["sample_chars"],
        "sample_sents": feats["sample_sents"],
        "sample_paras": feats["sample_paras"],
    }
    return key_metrics

# ============================================================
# P2: 句式模式分析
# ============================================================

# 句子起始分类词表
SENT_OPENERS = {
    "连词起句": ("但", "而", "却", "只", "已", "曾", "将", "与", "不过", "然而",
                "虽然", "而且", "于是", "所以", "只是", "甚至", "毕竟", "反而",
                "可是", "因为", "如果", "除非", "尽管", "无论", "不管", "既然"),
    "代词起句": ("他", "她", "我", "你", "它", "这", "那", "其", "之", "此", "彼", "谁", "什么"),
    "时间起句": ("当", "时", "此刻", "那时", "天", "夜", "晨", "晚", "日", "月",
                "年", "春", "夏", "秋", "冬", "今", "明", "昨", "一", "正", "忽", "突", "骤"),
    "数字起句": ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "百", "千", "万"),
}

def classify_sent_opening(sent):
    """判断句子起始类型"""
    s = sent.lstrip()
    for cat, prefixes in SENT_OPENERS.items():
        for p in prefixes:
            if s.startswith(p):
                # 排除"一时"这种时间词被误判为数字
                if p == "一" and len(s) > 1 and s[1] in "二三四五六七八九十":
                    continue
                return cat
    # 检查是否对话起句
    if s.startswith(("“", "「", '"', '「')):
        return "对话起句"
    # 检查是否环境/感官起句
    for words in SENSORY_WORDS.values():
        for w in words:
            if s.startswith(w):
                return "环境起句"
    return "名词/动词起句"

def phase2_sentence(text):
    """句式模式分析"""
    sents = split_sents(text)
    sent_lens = [han_count(s) for s in sents]

    # 1. 起始类型分布
    opener_counts = Counter()
    for s in sents:
        opener_counts[classify_sent_opening(s)] += 1
    total_sents = max(1, len(sents))
    opener_dist = {k: round(v / total_sents * 100, 2) for k, v in opener_counts.items()}

    # 2. 句长分布直方图
    buckets = [(0, 8, "极短≤8"), (9, 15, "短9-15"), (16, 25, "中16-25"),
               (26, 40, "长26-40"), (41, 60, "极长41-60"), (61, 999, "超长>60")]
    hist = {}
    for lo, hi, label in buckets:
        cnt = sum(1 for l in sent_lens if lo <= l <= hi)
        hist[label] = round(cnt / total_sents * 100, 2)

    # 3. 句尾模式
    ending_counts = Counter()
    for s in sents:
        s_trim = s.rstrip("。！？!?，,；;")
        if s_trim.endswith("了"):
            ending_counts["了字收尾"] += 1
        elif s_trim.endswith(("着", "过")):
            ending_counts["着/过收尾"] += 1
        elif s_trim.endswith(("的", "地")):
            ending_counts["的/地收尾"] += 1
        elif s_trim.endswith(("”", "」")):
            ending_counts["对话收尾"] += 1
        elif any(s_trim.endswith(w) for w in SENSORY_WORDS["视觉"] + SENSORY_WORDS["听觉"]):
            ending_counts["感官收尾"] += 1
        else:
            ending_counts["动作/叙述收尾"] += 1
    ending_dist = {k: round(v / total_sents * 100, 2) for k, v in ending_counts.items()}

    # 4. 复句比例（含逗号≥2个的句子）
    multi_clause = sum(1 for s in sents if s.count("，") + s.count(",") >= 2)
    simple_ratio = round((total_sents - multi_clause) / total_sents * 100, 2)

    return {
        "opener_dist": opener_dist,
        "length_hist": hist,
        "ending_dist": ending_dist,
        "simple_sent_ratio": simple_ratio,
        "multi_clause_ratio": round(multi_clause / total_sents * 100, 2),
        "total_sents": total_sents,
    }

# ============================================================
# P3: 段落节奏画像
# ============================================================

# 动作动词
ACTION_VERBS = set("走跑跳冲撞劈砍刺射踢打抓握推拉转身倒摔倒爬起立坐蹲站停走飞扑闪避格挡挥抬迈跨迈踏")
# 心理词
PSYCH_WORDS = ("想", "觉得", "感到", "知道", "认为", "意识", "心中", "内心", "思绪", "记忆", "回忆", "忘记", "明白", "理解")

def classify_paragraph(para):
    """段落类型分类"""
    chars = han_count(para)
    if chars <= 0:
        return "空"
    if chars <= 12:
        return "过渡"

    has_dialogue = bool(re.search(r"[“\"「].{0,200}[”\"」]", para))
    if has_dialogue and han_count(re.findall(r"[“\"「].{0,200}[”\"」]", para)[0]) > chars * 0.5:
        return "对话"

    sensory_count = sum(para.count(w) for words in SENSORY_WORDS.values() for w in words)
    action_count = sum(1 for c in para if c in ACTION_VERBS)
    psych_count = sum(para.count(w) for w in PSYCH_WORDS)

    # 环境段：感官词密度高
    if sensory_count / max(1, chars) > 0.03 and sensory_count > 3:
        return "环境"

    # 心理段：心理词密度高
    if psych_count / max(1, chars) > 0.02 and psych_count >= 2:
        return "心理"

    # 动作段：动作动词密度高
    if action_count / max(1, chars) > 0.04 and action_count >= 3:
        return "动作"

    return "叙述"

def phase3_paragraph(text):
    """段落节奏画像"""
    paras = split_paras(text)
    total = max(1, len(paras))
    para_lens = [han_count(p) for p in paras]

    # 1. 段落类型分布
    type_counts = Counter()
    for p in paras:
        type_counts[classify_paragraph(p)] += 1
    type_dist = {k: round(v / total * 100, 2) for k, v in type_counts.items()}

    # 2. 段长分布
    p_buckets = [(0, 15, "极短≤15"), (16, 30, "短16-30"), (31, 60, "中31-60"),
                 (61, 120, "长61-120"), (121, 9999, "超长>120")]
    p_hist = {}
    for lo, hi, label in p_buckets:
        cnt = sum(1 for l in para_lens if lo <= l <= hi)
        p_hist[label] = round(cnt / total * 100, 2)

    # 3. 段落类型序列（转移概率）
    types = [classify_paragraph(p) for p in paras]
    transitions = defaultdict(Counter)
    for i in range(len(types) - 1):
        transitions[types[i]][types[i + 1]] += 1
    transition_probs = {}
    for src, dsts in transitions.items():
        src_total = sum(dsts.values())
        transition_probs[src] = {k: round(v / src_total * 100, 2) for k, v in dsts.most_common(5)}

    # 4. 单句段占比
    single_sent = sum(1 for p in paras if p.count("。") + p.count("！") + p.count("？") <= 1)
    single_ratio = round(single_sent / total * 100, 2)

    return {
        "type_dist": type_dist,
        "length_hist": p_hist,
        "transitions": transition_probs,
        "single_sent_ratio": single_ratio,
        "total_paras": total,
        "para_len_mean": round(sum(para_lens) / total, 2),
    }

# ============================================================
# P4: 意象通道深度分析
# ============================================================

def phase4_imagery(text, author_cfg):
    """意象通道深度分析"""
    paras = split_paras(text)
    body = "\n".join(paras)
    total = max(1, han_count(body))

    # 1. 感官通道分布（每千字）
    sensory = extract_sensory_dist(body, total)

    # 2. 通道占比
    sensory_total = sum(sensory.values()) or 1
    sensory_pct = {k: round(v / sensory_total * 100, 1) for k, v in sensory.items()}

    # 3. 通道叠加深度（每段含几类感官）
    layer_counts = Counter()
    for p in paras:
        channels = 0
        for ch_name, words in SENSORY_WORDS.items():
            if any(w in p for w in words):
                channels += 1
        layer_counts[channels] += 1
    total_paras = max(1, len(paras))
    layer_dist = {str(k): round(v / total_paras * 100, 2) for k, v in sorted(layer_counts.items())}

    # 4. 意象词Top15（排除人名）
    imagery_top = extract_imagery_top(body, total, top_n=15,
                                       exclude_names=author_cfg.get("exclude_names", []))

    # 5. 通道在段落中的位置分布
    position_counts = Counter()  # 前1/3, 中1/3, 后1/3
    for p in paras:
        p_len = len(p)
        if p_len < 10:
            continue
        for ch_name, words in SENSORY_WORDS.items():
            for w in words:
                idx = p.find(w)
                while idx != -1:
                    pos = idx / p_len
                    if pos < 0.33:
                        position_counts["前段"] += 1
                    elif pos < 0.67:
                        position_counts["中段"] += 1
                    else:
                        position_counts["后段"] += 1
                    idx = p.find(w, idx + 1)
    pos_total = max(1, sum(position_counts.values()))
    position_dist = {k: round(v / pos_total * 100, 2) for k, v in position_counts.items()}

    return {
        "sensory_per_1000": sensory,
        "sensory_pct": sensory_pct,
        "layer_dist": layer_dist,
        "imagery_top15": imagery_top,
        "position_dist": position_dist,
    }

# ============================================================
# P5: 对话风格画像
# ============================================================

def phase5_dialogue(text):
    """对话风格画像"""
    body = text
    total = max(1, han_count(body))

    # 1. 提取所有对话
    dialogues = re.findall(r"[""「].{1,300}[""」]", body)
    dial_count = len(dialogues)

    # 2. 对话长度分布
    dial_lens = [han_count(d) for d in dialogues] if dialogues else []
    dial_lens_stats = {
        "mean": round(sum(dial_lens) / max(1, len(dial_lens)), 1) if dial_lens else 0,
        "median": sorted(dial_lens)[len(dial_lens) // 2] if dial_lens else 0,
        "max": max(dial_lens) if dial_lens else 0,
        "min": min(dial_lens) if dial_lens else 0,
    }

    # 3. 对话长度直方图
    d_buckets = [(0, 5, "极短≤5"), (6, 10, "短6-10"), (11, 20, "中11-20"),
                 (21, 40, "长21-40"), (41, 999, "超长>40")]
    d_hist = {}
    for lo, hi, label in d_buckets:
        cnt = sum(1 for l in dial_lens if lo <= l <= hi)
        d_hist[label] = round(cnt / max(1, len(dial_lens)) * 100, 2)

    # 4. 引导模式分布
    guide_patterns = {
        "道：": len(re.findall(r"道\s*[:：]", body)),
        "说：": len(re.findall(r"说\s*[:：]", body)),
        "问：": len(re.findall(r"问\s*[:：]", body)),
        "答：": len(re.findall(r"答\s*[:：]", body)),
        "笑道：": len(re.findall(r"笑\s*[:：]", body)),
        "叹道：": len(re.findall(r"叹\s*[:：]", body)),
        "低声道：": len(re.findall(r"(?:低声|轻声|沉声|冷声|大声|厉声)\s*[:：]", body)),
    }
    guide_total = max(1, sum(guide_patterns.values()))

    # 5. 裸对话比例（前后无引导语）
    bare_count = 0
    for m in re.finditer(r"[""「]", body):
        # 检查引号前20字是否有引导语
        before = body[max(0, m.start() - 20):m.start()]
        if not re.search(r"(道|说|问|答|笑|叹|吼|喊|怒|冷|低声|轻声|沉声)\s*[:：]?\s*$", before):
            bare_count += 1
    bare_ratio = round(bare_count / max(1, dial_count) * 100, 2)

    # 6. 对话密度（每千字）
    dial_density = round(dial_count / total * 1000, 2)

    return {
        "total_dialogues": dial_count,
        "dial_density_per_1000": dial_density,
        "length_stats": dial_lens_stats,
        "length_hist": d_hist,
        "guide_patterns": {k: v for k, v in guide_patterns.items() if v > 0},
        "guide_total": guide_total,
        "bare_dialogue_ratio": bare_ratio,
        "dialogue_ratio": round(dialogue_char_count(body) / total, 4),
    }

# ============================================================
# P6: 修辞与比喻画像
# ============================================================

# 喻体域分类
VEHICLE_DOMAINS = {
    "自然域": ("山", "河", "风", "雨", "云", "雷", "星", "月", "日", "光", "海", "潮", "雾", "霜", "雪", "冰", "火", "焰", "天", "地"),
    "动物域": ("虎", "狼", "鹰", "蛇", "龙", "兽", "鸟", "鱼", "虫", "蛛", "蝎", "蚁", "蝇", "蜂", "蝶", "犬", "猫", "鼠", "鲸", "鲨"),
    "器物域": ("刀", "剑", "钟", "镜", "锁", "链", "网", "弓", "盾", "针", "线", "绳", "布", "纸", "书", "旗", "灯", "烛", "炉", "鼎"),
    "身体域": ("手", "眼", "心", "骨", "血", "肉", "头", "脸", "口", "齿", "指", "拳", "掌", "腕", "肩", "背", "胸", "足", "步", "息"),
    "建筑域": ("墙", "门", "窗", "塔", "桥", "城", "殿", "宫", "室", "廊", "阶", "柱", "瓦", "砖", "梁", "檐"),
}

def classify_metaphor_vehicle(sentence):
    """分类比喻喻体域"""
    for domain, words in VEHICLE_DOMAINS.items():
        for w in words:
            if w in sentence:
                return domain
    return "其他"

def phase6_metaphor(text):
    """修辞与比喻画像"""
    body = text
    total = max(1, han_count(body))

    # 1. 比喻标记分布
    marker_counts = {}
    for m in re.finditer(r"像", body):
        tail = body[m.start():m.start() + 3]
        if any(tail.startswith(w[:2]) for w in SIMILE_EXCLUDE_FP):
            continue
        marker_counts["像"] = marker_counts.get("像", 0) + 1
    for w in METAPHOR_MARKERS:
        cnt = body.count(w)
        if cnt > 0:
            marker_counts[w] = cnt

    # 2. 比喻密度
    total_metaphors = sum(marker_counts.values())
    metaphor_density = round(total_metaphors / total * 1000, 3)

    # 3. 喻体域分布
    # 找到比喻句（含比喻标记的句子）
    metaphor_sents = []
    for s in split_sents(body):
        has_metaphor = False
        for m in METAPHOR_MARKERS:
            if m in s:
                has_metaphor = True
                break
        if not has_metaphor:
            # 检查"像"字
            for m in re.finditer(r"像", s):
                tail = s[m.start():m.start() + 3]
                if not any(tail.startswith(w[:2]) for w in SIMILE_EXCLUDE_FP):
                    has_metaphor = True
                    break
        if has_metaphor:
            metaphor_sents.append(s)

    vehicle_counts = Counter()
    for s in metaphor_sents:
        vehicle_counts[classify_metaphor_vehicle(s)] += 1
    vehicle_total = max(1, sum(vehicle_counts.values()))
    vehicle_dist = {k: round(v / vehicle_total * 100, 2) for k, v in vehicle_counts.most_common()}

    # 4. 其他修辞
    rhetoric = {
        "排比_三连同": len(re.findall(r"[，。！？][^，。！？]{2,8}[，][^，。！？]{2,8}[，][^，。！？]{2,8}[。]", body)),
        "反问": len(re.findall(r"[难莫]道.{1,30}[？?]", body)),
        "设问": len(re.findall(r"[。！？][^。！？]{2,20}[？?][^。！？]{2,40}[。]", body)),
        "感叹": body.count("！") + body.count("!"),
    }
    rhetoric_per_1000 = {k: round(v / total * 1000, 3) for k, v in rhetoric.items()}

    # 5. 比喻句示例（取前5个）
    examples = []
    for s in metaphor_sents[:5]:
        s_clean = s.strip()
        if 10 <= len(s_clean) <= 80:
            examples.append(s_clean)

    return {
        "marker_dist": marker_counts,
        "total_metaphors": total_metaphors,
        "metaphor_density": metaphor_density,
        "vehicle_dist": vehicle_dist,
        "rhetoric_count": rhetoric,
        "rhetoric_per_1000": rhetoric_per_1000,
        "metaphor_examples": examples,
    }

# ============================================================
# P7: 叙述技法画像
# ============================================================

def phase7_narrative(text):
    """叙述技法画像"""
    paras = split_paras(text)
    total = max(1, han_count("\n".join(paras)))

    # 1. 章节开篇模式（按"第N章"切分后取首段）
    chapter_marks = [m.start() for m in re.finditer(r"(?m)^第[0-9零一二三四五六七八九十百千两]+章", text)]
    openings = []
    for i, st in enumerate(chapter_marks[:50]):  # 最多分析50章
        en = chapter_marks[i + 1] if i + 1 < len(chapter_marks) else len(text)
        chapter_text = text[st:en]
        chapter_paras = split_paras(chapter_text)
        if chapter_paras:
            first_para = chapter_paras[0][:60]
            # 分类开篇
            if re.match(r"[“\"「]", first_para):
                opening_type = "对话开篇"
            elif any(w in first_para[:10] for words in SENSORY_WORDS.values() for w in words):
                opening_type = "环境开篇"
            elif any(first_para.startswith(w) for w in CONJ_STARTERS):
                opening_type = "连词开篇"
            elif re.match(r"^(他|她|我|你|它)", first_para):
                opening_type = "人物开篇"
            else:
                opening_type = "叙述开篇"
            openings.append({"type": opening_type, "text": first_para[:40]})

    opening_counts = Counter(o["type"] for o in openings)
    opening_dist = {k: round(v / max(1, len(openings)) * 100, 2) for k, v in opening_counts.items()}

    # 2. 章末模式（每章最后一段）
    closings = []
    for i, st in enumerate(chapter_marks[:50]):
        en = chapter_marks[i + 1] if i + 1 < len(chapter_marks) else len(text)
        chapter_text = text[st:en]
        chapter_paras = [p for p in split_paras(chapter_text) if han_count(p) > 5]
        if chapter_paras:
            last_para = chapter_paras[-1][:60]
            if re.search(r"[？?]", last_para):
                closing_type = "悬念收尾"
            elif re.search(r"[“\"」]$", last_para):
                closing_type = "对话收尾"
            elif any(w in last_para for words in SENSORY_WORDS.values() for w in words):
                closing_type = "环境收尾"
            elif any(w in last_para for w in PSYCH_WORDS):
                closing_type = "心理收尾"
            else:
                closing_type = "动作/叙述收尾"
            closings.append({"type": closing_type, "text": last_para[:40]})

    closing_counts = Counter(c["type"] for c in closings)
    closing_dist = {k: round(v / max(1, len(closings)) * 100, 2) for k, v in closing_counts.items()}

    # 3. 世界自转频率（非角色中心的感官描写段）
    world_rotation = 0
    for p in paras:
        chars = han_count(p)
        if chars < 20 or chars > 100:
            continue
        # 不含人名/代词，但含感官词
        has_char_ref = any(w in p for w in ("他", "她", "我", "你", "它"))
        has_sensory = any(w in p for words in SENSORY_WORDS.values() for w in words)
        if not has_char_ref and has_sensory:
            world_rotation += 1
    world_rotation_density = round(world_rotation / total * 1000, 2)

    # 4. 物件叙事频率（旧物描写段）
    object_words = ("刀", "剑", "铜钱", "牌", "玉", "书", "镜", "锁", "链", "戒指", "项链", "徽章", "令牌")
    object_narrative = sum(1 for p in paras if any(w in p for w in object_words) and han_count(p) > 20)
    object_density = round(object_narrative / total * 1000, 2)

    # 5. 延迟兑现频率（情感词后接世界描写而非心理）
    emotion_words = ("死", "杀", "哭", "泪", "痛", "伤", "血")
    delay_count = 0
    for i, p in enumerate(paras):
        if any(w in p for w in emotion_words) and i + 1 < len(paras):
            next_p = paras[i + 1]
            next_has_psych = any(w in next_p for w in PSYCH_WORDS)
            next_has_sensory = any(w in next_p for words in SENSORY_WORDS.values() for w in words)
            if next_has_sensory and not next_has_psych:
                delay_count += 1
    delay_density = round(delay_count / total * 1000, 2)

    return {
        "opening_dist": opening_dist,
        "opening_examples": openings[:3],
        "closing_dist": closing_dist,
        "closing_examples": closings[:3],
        "world_rotation_density": world_rotation_density,
        "object_narrative_density": object_density,
        "delayed_gratification_density": delay_density,
        "chapters_analyzed": len(openings),
    }

# ============================================================
# P8: 跨作者对比
# ============================================================

def phase8_compare(authors_data):
    """跨作者对比——归一化+距离矩阵+雷达数据"""
    # 收集所有可对比的标量维度
    compare_dims = [
        "sent_len_mean", "short_sent_ratio", "long_sent_ratio",
        "para_len_mean", "short_para_ratio", "dialogue_ratio",
        "comma_period_ratio", "dash_per_1000", "ellipsis_per_1000",
        "metaphor_per_1000", "conjunction_starter_ratio",
        "dialogue_guide_per_1000", "le_ending_ratio",
    ]

    # 提取每位作者的值
    author_names = list(authors_data.keys())
    values = {}
    for name in author_names:
        p1 = authors_data[name].get("p1", {})
        if not p1:
            continue
        values[name] = {d: p1.get(d, 0) for d in compare_dims}

    if len(values) < 2:
        return {"error": "需要至少2位作者才能对比"}

    # 归一化到0-1（按最大值）
    max_vals = {d: max(v[d] for v in values.values()) or 1 for d in compare_dims}
    normalized = {}
    for name, vals in values.items():
        normalized[name] = {d: round(vals[d] / max_vals[d], 4) for d in compare_dims}

    # 风格距离矩阵（欧氏距离）
    distance_matrix = {}
    for n1 in author_names:
        if n1 not in normalized:
            continue
        distance_matrix[n1] = {}
        for n2 in author_names:
            if n2 not in normalized:
                continue
            if n1 == n2:
                distance_matrix[n1][n2] = 0.0
            else:
                dist = math.sqrt(sum((normalized[n1][d] - normalized[n2][d]) ** 2 for d in compare_dims))
                distance_matrix[n1][n2] = round(dist, 4)

    # 每位作者最 distinctive 的维度（偏离均值最远）
    avg_vals = {d: sum(normalized[n][d] for n in normalized) / len(normalized) for d in compare_dims}
    distinctive = {}
    for name in normalized:
        deviations = {d: round(abs(normalized[name][d] - avg_vals[d]), 4) for d in compare_dims}
        top3 = sorted(deviations.items(), key=lambda x: -x[1])[:3]
        distinctive[name] = [{"dim": d, "value": normalized[name][d], "avg": round(avg_vals[d], 4)} for d, _ in top3]

    # 对话风格对比
    dialogue_compare = {}
    for name in author_names:
        p5 = authors_data[name].get("p5", {})
        if p5:
            dialogue_compare[name] = {
                "bare_ratio": p5.get("bare_dialogue_ratio", 0),
                "dial_density": p5.get("dial_density_per_1000", 0),
                "dial_mean_len": p5.get("length_stats", {}).get("mean", 0),
            }

    # 感官通道对比
    sensory_compare = {}
    for name in author_names:
        p4 = authors_data[name].get("p4", {})
        if p4:
            sensory_compare[name] = p4.get("sensory_pct", {})

    return {
        "dimensions": compare_dims,
        "normalized": normalized,
        "distance_matrix": distance_matrix,
        "distinctive_features": distinctive,
        "dialogue_compare": dialogue_compare,
        "sensory_compare": sensory_compare,
        "radar_dims": compare_dims,
        "radar_data": {name: [normalized[name][d] for d in compare_dims] for name in normalized},
    }

# ============================================================
# 主流程
# ============================================================

def run_distill(config, filter_author=None, filter_phase=None):
    """运行完整蒸馏流程"""
    state = load_state()
    if state is None:
        state = {
            "lab_name": config["lab_name"], "version": config["version"],
            "status": "idle", "current_phase": None, "current_author": None,
            "progress": 0, "total_phases": 8, "total_authors": len(config["authors"]),
            "started_at": None, "completed_at": None, "error": None,
            "phases": {}, "authors": {}, "comparison": None, "last_updated": None,
        }

    # 初始化 phases
    for p in config["phases"]:
        if p["id"] not in state["phases"]:
            state["phases"][p["id"]] = {
                "name": p["name"], "status": "pending",
                "started_at": None, "completed_at": None
            }

    state["status"] = "running"
    state["started_at"] = state.get("started_at") or now_str()
    save_state(state)

    authors = config["authors"]
    if filter_author:
        authors = [a for a in authors if a["name"] == filter_author]
    phases = config["phases"]
    if filter_phase:
        phases = [p for p in phases if p["id"] == filter_phase]

    # 预加载文本（P1-P7 逐作者执行）
    author_texts = {}

    for phase in phases:
        pid = phase["id"]
        pname = phase["name"]
        state["phases"][pid]["status"] = "in_progress"
        state["phases"][pid]["started_at"] = now_str()
        state["current_phase"] = pname
        save_state(state)

        print(f"\n{'='*60}")
        print(f"  阶段 {pid}: {pname}")
        print(f"  {phase['desc']}")
        print(f"{'='*60}")

        try:
            if pid == "p8":
                # 跨作者对比——需要所有作者数据
                all_data = {}
                for a in config["authors"]:
                    if a["name"] in state.get("authors", {}):
                        all_data[a["name"]] = state["authors"][a["name"]].get("phases", {})
                result = phase8_compare(all_data)
                state["comparison"] = result
            else:
                # 逐作者分析
                phase_func = {
                    "p1": phase1_fingerprint, "p2": phase2_sentence,
                    "p3": phase3_paragraph, "p4": phase4_imagery,
                    "p5": phase5_dialogue, "p6": phase6_metaphor,
                    "p7": phase7_narrative,
                }[pid]

                for a in authors:
                    aname = a["name"]
                    state["current_author"] = a["display_name"]
                    save_state(state)

                    # 初始化作者条目
                    if aname not in state["authors"]:
                        state["authors"][aname] = {
                            "display_name": a["display_name"],
                            "label": a["label"],
                            "color": a.get("color", "#4a9eff"),
                            "phases": {}
                        }

                    # 加载文本（缓存）
                    if aname not in author_texts:
                        print(f"  [{aname}] 加载原作...")
                        body, chars = load_author_text(a)
                        author_texts[aname] = body
                        state["authors"][aname]["sample_chars"] = chars
                        save_state(state)
                        print(f"  [{aname}] 采样 {chars} 字")

                    body = author_texts[aname]
                    print(f"  [{aname}] 运行 {pname}...")

                    # 运行分析
                    if pid in ("p1", "p4"):
                        result = phase_func(body, a)
                    else:
                        result = phase_func(body)

                    state["authors"][aname]["phases"][pid] = result
                    state["progress"] = min(100, state["progress"] + int(100 / (len(phases) * len(authors))))
                    save_state(state)
                    print(f"  [{aname}] {pname} 完成")

            state["phases"][pid]["status"] = "completed"
            state["phases"][pid]["completed_at"] = now_str()
            save_state(state)
            print(f"  阶段 {pid} 完成")

        except Exception as e:
            state["phases"][pid]["status"] = "error"
            state["error"] = f"{pid}: {str(e)}"
            save_state(state)
            print(f"  [ERROR] {pid}: {e}")
            import traceback
            traceback.print_exc()
            return

    state["status"] = "completed"
    state["completed_at"] = now_str()
    state["progress"] = 100
    state["current_phase"] = None
    state["current_author"] = None
    save_state(state)
    print(f"\n{'='*60}")
    print("  蒸馏完成！")
    print(f"  状态文件: {STATE_PATH}")
    print(f"  面板: {os.path.join(LAB_DIR, 'distill_dashboard.html')}")
    print(f"{'='*60}")

    # 生成报告
    os.makedirs(REPORT_DIR, exist_ok=True)
    for aname, adata in state["authors"].items():
        report_path = os.path.join(REPORT_DIR, f"{aname}_deep.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(adata, f, ensure_ascii=False, indent=2)
        print(f"  报告: {report_path}")

    if state.get("comparison"):
        cmp_path = os.path.join(REPORT_DIR, "comparison.json")
        with open(cmp_path, "w", encoding="utf-8") as f:
            json.dump(state["comparison"], f, ensure_ascii=False, indent=2)
        print(f"  对比: {cmp_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="深度文风蒸馏")
    parser.add_argument("--author", help="只跑指定作者")
    parser.add_argument("--phase", help="只跑指定阶段 (p1-p8)")
    args = parser.parse_args()

    config = load_config()
    run_distill(config, filter_author=args.author, filter_phase=args.phase)
