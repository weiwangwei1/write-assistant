#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
framework_experiment.py v2.0 — 感知多样性框架

v1.0 问题：只检测词频，不检测感官通道多样性。结果：v7 把"碱味"换成"干涩的气"，
          重复问题没解决，只是换了个词重复。
v2.0 升级：从事后诊断出发，检测 5 个维度：
  P1. 意象感知多样性 — 词频 + 感官通道轮换 + 变体质量
  P2. 金句密度 — 哲理性收尾句的密度控制
  P3. 重复动作预算 — 情绪指标型动作（磨刀速度变化等）的频率控制
  P4. 替代词质量 — 替代词本身是否变成了新的高频词（"口子"18次 > "裂缝"2次）
  P5. 指代密度 — 代称/代词的频率与指代清晰度

设计原则：诊断而非约束。框架检测问题并报告，不告诉写手该怎么写。
         写手根据诊断结果和场景判断如何修复。

用法:
  python framework_experiment.py chapter_001_v7.txt
  python framework_experiment.py chapter_001_v7.txt --json report.json
  python framework_experiment.py ch1.txt --compare ch2.txt
"""

import json
import re
import sys
import os
from collections import defaultdict, Counter
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple, Optional


# ============================================================
# 数据结构
# ============================================================

@dataclass
class FrameworkReport:
    """框架实验报告 v2.0"""
    file: str
    total_chars: int
    total_paragraphs: int
    # P1: 意象感知多样性
    imagery_stats: List[Dict]
    imagery_score: float
    # P2: 金句密度
    para_functions: List[Dict]
    function_distribution: Dict
    punchline_count: int
    punchline_density: float
    punchline_score: float
    # P3: 重复动作预算
    recurring_actions: List[Dict]
    recurring_action_score: float
    # P4: 替代词质量
    substitution_issues: List[Dict]
    substitution_score: float
    # P5: 指代密度
    referential_stats: Dict
    referential_score: float
    # 综合
    framework_score: float
    summary: str

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "total_chars": self.total_chars,
            "total_paragraphs": self.total_paragraphs,
            "imagery_stats": self.imagery_stats,
            "imagery_score": round(self.imagery_score, 1),
            "para_functions": self.para_functions,
            "function_distribution": self.function_distribution,
            "punchline_count": self.punchline_count,
            "punchline_density": round(self.punchline_density, 2),
            "punchline_score": round(self.punchline_score, 1),
            "recurring_actions": self.recurring_actions,
            "recurring_action_score": round(self.recurring_action_score, 1),
            "substitution_issues": self.substitution_issues,
            "substitution_score": round(self.substitution_score, 1),
            "referential_stats": self.referential_stats,
            "referential_score": round(self.referential_score, 1),
            "framework_score": round(self.framework_score, 1),
            "summary": self.summary,
        }


# ============================================================
# P1: 意象感知多样性
# ============================================================

IMAGERY_GROUPS = {
    "暗紫色": {
        "core": ["暗紫色", "暗紫色光", "暗紫色的"],
        "variants": [
            "紫色的光", "紫光", "暗光",
            "纹路", "纹路蠕动",
            "暗紫", "发紫",
            "边缘发紫", "伤口边缘发紫",
        ],
        "max_budget": 8,
        "ideal_variation": 0.4,
    },
    "碱味": {
        "core": ["碱味", "碱的", "碱"],
        "variants": [
            "干的", "发涩", "发紧",
            "嗓子眼", "砂", "砂粒",
            "铁锈味", "焦糊味", "焦糊",
            "炊烟", "泔水",
            "干涩的气", "干热的气",
        ],
        "max_budget": 6,
        "ideal_variation": 0.4,
    },
    "铜钱": {
        "core": ["铜钱", "铜钱在"],
        "variants": [
            "铜面", "铜锈", "铜屑",
            "三枚", "四枚", "一枚",
            "旧铜钱", "新铜钱",
            "那几枚", "那枚", "掌中之物",
            "指间", "掌心", "旧物",
        ],
        "max_budget": 15,
        "ideal_variation": 0.5,
    },
    "磨刀": {
        "core": ["磨刀", "磨刀声"],
        "variants": [
            "磨石", "磨刀的手",
            "磨刀的速度", "磨刀的人",
        ],
        "max_budget": 6,
        "ideal_variation": 0.3,
    },
    "裂缝": {
        "core": ["裂缝", "裂缝在"],
        "variants": [
            "界门", "口子", "裂纹",
            "城墙根", "石缝",
        ],
        "max_budget": 10,
        "ideal_variation": 0.4,
    },
}

# 感官通道关键词（用于判断意象出现时走的是哪个通道）
SENSORY_CHANNEL_KEYWORDS = {
    "视觉": ["光", "亮", "暗", "紫", "色", "看", "望", "盯", "瞧", "影", "闪", "亮起"],
    "嗅觉": ["味", "碱", "焦", "臭", "腥", "香", "闻", "气", "烟"],
    "触觉": ["烫", "凉", "冷", "热", "暖", "寒", "摸", "碰", "握", "攥", "捏", "糙", "滑", "涩", "硬", "软", "硌", "疼"],
    "听觉": ["声", "响", "磨", "碎", "哑", "咯吱", "听", "碰", "嗡"],
    "反应": ["皱眉", "咳", "偏头", "皱了", "眯", "屏住", "吞了口", "别过脸"],
}


def detect_sensory_channel(para: str) -> str:
    """检测段落主要走哪个感官通道"""
    channel_hits = {}
    for channel, keywords in SENSORY_CHANNEL_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in para)
        if hits > 0:
            channel_hits[channel] = hits
    if not channel_hits:
        return "无感官"
    return max(channel_hits, key=channel_hits.get)


def analyze_imagery(paragraphs: List[str], total_chars: int) -> Tuple[List[Dict], float]:
    """P1: 分析意象重复率、变体使用、感官通道多样性"""
    stats = []
    full_text = "\n".join(paragraphs)

    for word, config in IMAGERY_GROUPS.items():
        core_count = sum(full_text.count(c) for c in config["core"])
        variant_counts = {}
        for v in config["variants"]:
            cnt = full_text.count(v)
            if cnt > 0:
                variant_counts[v] = cnt

        variant_total = sum(variant_counts.values())
        total = core_count + variant_total
        density = total / max(total_chars, 1) * 1000
        variation_ratio = variant_total / max(total, 1)

        # 找出现位置 + 感官通道
        occurrences = []
        for idx, para in enumerate(paragraphs):
            found_in_para = False
            for c in config["core"]:
                if c in para:
                    found_in_para = True
                    break
            if not found_in_para:
                for v in config["variants"]:
                    if v in para:
                        found_in_para = True
                        break
            if found_in_para:
                channel = detect_sensory_channel(para)
                occurrences.append({"para": idx + 1, "channel": channel})

        # 感官通道序列
        channel_sequence = [occ["channel"] for occ in occurrences]

        # 检测连续同通道
        consecutive_same = []
        if len(channel_sequence) >= 3:
            for i in range(len(channel_sequence) - 2):
                if (channel_sequence[i] == channel_sequence[i+1] == channel_sequence[i+2]
                        and channel_sequence[i] != "无感官"):
                    consecutive_same.append({
                        "start_para": occurrences[i]["para"],
                        "channel": channel_sequence[i],
                        "count": 3,
                    })

        over_budget = core_count > config["max_budget"]
        low_variation = variation_ratio < config["ideal_variation"]
        channel_monotony = len(consecutive_same) > 0

        stat = {
            "word": word,
            "core_count": core_count,
            "budget": config["max_budget"],
            "over_budget": over_budget,
            "variants": variant_counts,
            "variant_total": variant_total,
            "variation_ratio": round(variation_ratio, 2),
            "ideal_variation": config["ideal_variation"],
            "low_variation": low_variation,
            "total": total,
            "density_per_1k": round(density, 1),
            "occurrences": occurrences[:20],
            "channel_sequence": channel_sequence[:20],
            "consecutive_same_channel": consecutive_same,
            "channel_monotony": channel_monotony,
        }
        stats.append(stat)

    # 评分
    penalty = 0
    for s in stats:
        if s["over_budget"]:
            excess = s["core_count"] - s["budget"]
            penalty += min(excess * 3, 15)
        if s["low_variation"]:
            deficit = s["ideal_variation"] - s["variation_ratio"]
            penalty += min(deficit * 50, 10)
        if s["channel_monotony"]:
            penalty += len(s["consecutive_same_channel"]) * 8

    score = max(0, 100 - penalty)
    return stats, score


# ============================================================
# P2: 金句密度（保持 v1.0 逻辑）
# ============================================================

PUNCHLINE_PATTERNS = [
    re.compile(r"[^。！？]*(?:不.*?也|没.*?却|不.*?倒是)[^。！？]*[。！？]"),
    re.compile(r"[^。！？]*(?:是一样的|和.*?一样|跟.*?一样)[^。！？]*[。！？]"),
    re.compile(r"[^。！？]*(?:比.*?更|比.*?贵|比.*?重|比.*?难|比.*?好认)[^。！？]*[。！？]"),
    re.compile(r"[^。！？]*(?:的是|的东西|的事|的话)[^。！？]*[。！？]"),
    re.compile(r"[^。！？]*(?:算得出.*?算不出|能.*?不能|会.*?不会)[^。！？]*[。！？]"),
    re.compile(r"[^。！？]*(?:不是.*?是|不叫.*?叫|没有.*?只有)[^。！？]*[。！？]"),
]

SENSORY_VERBS_P = ["看", "望", "盯", "瞧", "听", "闻", "嗅", "摸", "碰", "握",
                   "攥", "捏", "烫", "凉", "冷", "热", "疼", "痒", "麻",
                   "感觉", "感到", "察觉", "看见", "听见", "闻到"]

ACTION_VERBS_P = ["跳", "扎", "劈", "砍", "冲", "退", "刺", "挡", "挥", "扑",
                  "射", "掷", "推", "拉", "抽", "补", "走", "跑", "蹲", "站",
                  "坐", "翻", "转", "磨", "蹭", "丢", "接", "塞", "掏"]


def count_chars(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def split_paragraphs(text: str) -> List[str]:
    raw = re.split(r"\n\s*\n", text)
    return [p.strip() for p in raw if p.strip()]


def detect_punchline(para: str) -> Tuple[bool, str]:
    sentences = re.findall(r"[^。！？\n]*[。！？]", para)
    for sent in sentences:
        sent_stripped = sent.strip()
        if len(sent_stripped) < 5:
            continue
        for pattern in PUNCHLINE_PATTERNS:
            if pattern.search(sent):
                if sent_stripped.count('"') >= 2 or sent_stripped.count('"') >= 2:
                    continue
                return True, sent_stripped[:60]
    char_count = count_chars(para)
    if char_count <= 30 and para.count('"') == 0 and para.count('"') == 0:
        philosophical_markers = [
            "空", "安静", "什么都没有", "什么都没",
            "不说", "不转", "不认", "没动",
            "像", "和", "跟",
        ]
        if any(m in para for m in philosophical_markers):
            return True, para.strip()[:60]
    return False, ""


def classify_paragraph(para: str, idx: int) -> dict:
    char_count = count_chars(para)
    if para.count('"') >= 2 or para.count('"') >= 2:
        has_punch, punch_text = detect_punchline(para)
        return {
            "para_num": idx + 1, "char_count": char_count,
            "function": "dialogue", "has_punchline": has_punch,
            "punchline_text": punch_text, "sensory_channels": [],
        }

    sensory_count = sum(para.count(v) for v in SENSORY_VERBS_P)
    action_count = sum(para.count(v) for v in ACTION_VERBS_P)
    sensory_channels = []
    if any(w in para for w in ["看", "望", "盯", "瞧", "光", "亮", "暗", "紫"]):
        sensory_channels.append("视觉")
    if any(w in para for w in ["听", "声", "响", "磨", "碎", "哑", "咯吱"]):
        sensory_channels.append("听觉")
    if any(w in para for w in ["闻", "味", "碱", "焦", "臭", "腥", "香"]):
        sensory_channels.append("嗅觉")
    if any(w in para for w in ["烫", "凉", "冷", "热", "暖", "寒"]):
        sensory_channels.append("温度")
    if any(w in para for w in ["摸", "碰", "握", "攥", "捏", "糙", "滑", "涩", "硬", "软", "硌"]):
        sensory_channels.append("触感")

    has_punch, punch_text = detect_punchline(para)

    if char_count <= 40 and has_punch:
        func = "heavy"
    elif has_punch and sensory_count <= 2:
        func = "heavy"
    elif sensory_count >= 3 and len(sensory_channels) >= 2:
        func = "sensory"
    elif action_count >= 3:
        func = "action"
    else:
        func = "plain"

    return {
        "para_num": idx + 1, "char_count": char_count,
        "function": func, "has_punchline": has_punch,
        "punchline_text": punch_text, "sensory_channels": sensory_channels,
    }


def analyze_para_functions(paragraphs: List[str]) -> Tuple[List[Dict], Dict, int, float, float]:
    functions = []
    func_counter = defaultdict(int)
    punchline_count = 0
    total_chars = sum(count_chars(p) for p in paragraphs)

    for idx, para in enumerate(paragraphs):
        pf = classify_paragraph(para, idx)
        functions.append(pf)
        func_counter[pf["function"]] += 1
        if pf["has_punchline"]:
            punchline_count += 1

    total_paras = len(paragraphs)
    distribution = {
        func: {"count": count, "ratio": round(count / max(total_paras, 1) * 100, 1)}
        for func, count in sorted(func_counter.items(), key=lambda x: -x[1])
    }
    density = punchline_count / max(total_chars / 1000, 1)

    if density <= 2:
        score = 100
    elif density <= 3:
        score = 90 - (density - 2) * 20
    elif density <= 4:
        score = 70 - (density - 3) * 20
    else:
        score = max(0, 50 - (density - 4) * 15)

    heavy_ratio = func_counter.get("heavy", 0) / max(total_paras, 1)
    if heavy_ratio > 0.15:
        score -= (heavy_ratio - 0.15) * 100

    return functions, distribution, punchline_count, density, max(0, score)


# ============================================================
# P3: 重复动作预算
# ============================================================

# 情绪指标型重复动作模式
RECURRING_ACTION_PATTERNS = {
    "磨刀速度变化": {
        "keywords": ["磨刀的手", "磨刀声", "刀刃碰磨石", "磨石",
                      "磨刀的速度", "磨刀的人", "磨刀的手顿",
                      "刀刃声", "速度慢了", "速度慢", "重了几分", "重一拍",
                      "慢了半拍", "慢一拍", "慢了", "顿了一拍", "顿了一下",
                      "又碎又哑", "又起"],
        "max_per_chapter": 4,
        "description": "磨刀速度变化作为老周情绪指标",
        "suggestion": "控制在4次以内，每次速度变化对应不同情绪。其余通过碰别针/咬唇/合眼泄露",
    },
    "铜钱翻转动作": {
        "keywords": ["铜钱在指间", "在指间转", "指缝间翻转", "三枚在",
                      "掌中之物", "在掌心转", "从左手转到右手", "又转回来",
                      "在指间停住", "翻转", "指间翻转"],
        "max_per_chapter": 8,
        "description": "程铖转铜钱作为精算/紧张指标",
        "suggestion": "控制在8次以内，超出时用其他行为替代（攥紧/停住/放下）",
    },
    "手抖/脸平静对比": {
        "keywords": ["手在发抖", "手在抖", "发抖", "脸很平静", "脸平静",
                      "平静", "抖了一下", "不抖了", "抖完"],
        "max_per_chapter": 3,
        "description": "手抖与脸平静的对比作为情感压抑指标",
        "suggestion": "控制在3次以内。展示一次就够了，重复会稀释力量",
    },
}


def analyze_recurring_actions(paragraphs: List[str]) -> Tuple[List[Dict], float]:
    """P3: 检测重复动作型情绪指标的频率"""
    full_text = "\n".join(paragraphs)
    results = []
    penalty = 0

    for name, config in RECURRING_ACTION_PATTERNS.items():
        occurrences = []
        for idx, para in enumerate(paragraphs):
            for kw in config["keywords"]:
                if kw in para:
                    occurrences.append({"para": idx + 1, "keyword": kw})
                    break

        count = len(occurrences)
        over_limit = count > config["max_per_chapter"]

        result = {
            "name": name,
            "count": count,
            "max": config["max_per_chapter"],
            "over_limit": over_limit,
            "occurrences": occurrences[:15],
            "description": config["description"],
            "suggestion": config["suggestion"] if over_limit else "",
        }
        results.append(result)

        if over_limit:
            excess = count - config["max_per_chapter"]
            penalty += min(excess * 8, 20)

    score = max(0, 100 - penalty)
    return results, score


# ============================================================
# P4: 替代词质量
# ============================================================

def analyze_substitution_quality(paragraphs: List[str]) -> Tuple[List[Dict], float]:
    """P4: 检测替代词本身是否变成了新的高频词

    核心逻辑：如果某个变体的出现次数 > 原词出现次数，说明"换词"只是
    把重复从 A 词转移到了 B 词，没有真正解决问题。

    典型案例：v7 把"裂缝"换成"口子"，结果"口子"出现 18 次 > "裂缝" 2 次
    """
    full_text = "\n".join(paragraphs)
    issues = []
    penalty = 0

    for word, config in IMAGERY_GROUPS.items():
        core_count = sum(full_text.count(c) for c in config["core"])

        for variant in config["variants"]:
            variant_count = full_text.count(variant)
            if variant_count == 0:
                continue

            # 变体出现次数 > 原词 → 替代词退化
            if variant_count > core_count and variant_count >= 5:
                ratio = variant_count / max(core_count, 1)
                severity = "critical" if ratio >= 3 else "warning"
                issues.append({
                    "imagery": word,
                    "original_word": config["core"][0],
                    "original_count": core_count,
                    "substitute": variant,
                    "substitute_count": variant_count,
                    "ratio": round(ratio, 1),
                    "severity": severity,
                    "diagnosis": f"'{variant}'出现{variant_count}次，是原词'{config['core'][0]}'({core_count}次)的{ratio:.1f}倍。"
                                 f"替代词本身变成了新的高频词，重复问题只是转移未解决。",
                    "suggestion": f"恢复'{config['core'][0]}'在叙述层面的使用，'{variant}'仅在对话中使用。"
                                  f"或换感官通道：不换词，换感知方式。",
                })
                if severity == "critical":
                    penalty += 12
                else:
                    penalty += 6

            # 变体出现次数 > 预算的 50% → 替代词接近饱和
            elif variant_count >= config["max_budget"] * 0.5 and variant_count >= 4:
                issues.append({
                    "imagery": word,
                    "original_word": config["core"][0],
                    "original_count": core_count,
                    "substitute": variant,
                    "substitute_count": variant_count,
                    "ratio": round(variant_count / max(core_count, 1), 1),
                    "severity": "info",
                    "diagnosis": f"'{variant}'出现{variant_count}次，接近饱和。注意不要让它成为下一个'{config['core'][0]}'。",
                    "suggestion": f"控制'{variant}'的使用频率，尝试其他变体或换感官通道。",
                })
                penalty += 3

    score = max(0, 100 - penalty)
    return issues, score


# ============================================================
# P5: 指代密度
# ============================================================

# 代称/代词模式
REFERENTIAL_PATTERNS = {
    "那几枚": {
        "keywords": ["那几枚"],
        "max_per_chapter": 6,
        "issue": "过度使用'那几枚'产生指代模糊：文中同时存在三枚旧铜钱、师父那枚、第五枚等",
        "suggestion": "大部分地方保留'铜钱'，只在情感浓度最高的段落用'那几枚'制造疏离感",
    },
    "那枚": {
        "keywords": ["那枚"],
        "max_per_chapter": 4,
        "issue": "'那枚'需要上下文明确指代对象",
        "suggestion": "确保使用'那枚'时上下文已明确是哪一枚",
    },
    "它（指铜钱）": {
        "keywords": ["它", "它不", "它在", "它没", "它会"],
        "max_per_chapter": 8,
        "issue": "'它'在文中可能指代铜钱、裂缝、壳等多种事物",
        "suggestion": "使用'它'时确保前一句的主语明确",
    },
    "掌中之物": {
        "keywords": ["掌中之物"],
        "max_per_chapter": 3,
        "issue": "'掌中之物'是高情感浓度表达，频繁使用会稀释",
        "suggestion": "仅在程铖算铜钱时使用，其余地方用'铜钱'或'三枚'",
    },
}


def analyze_referential_density(paragraphs: List[str]) -> Tuple[Dict, float]:
    """P5: 检测代称/代词的频率和潜在指代模糊"""
    full_text = "\n".join(paragraphs)
    stats = {}
    penalty = 0

    for name, config in REFERENTIAL_PATTERNS.items():
        count = sum(full_text.count(kw) for kw in config["keywords"])
        occurrences = []
        for idx, para in enumerate(paragraphs):
            for kw in config["keywords"]:
                if kw in para:
                    occurrences.append(idx + 1)
                    break

        over_limit = count > config["max_per_chapter"]
        stats[name] = {
            "count": count,
            "max": config["max_per_chapter"],
            "over_limit": over_limit,
            "occurrences_in_paras": occurrences[:15],
            "issue": config["issue"] if over_limit else "",
            "suggestion": config["suggestion"] if over_limit else "",
        }
        if over_limit:
            excess = count - config["max_per_chapter"]
            penalty += min(excess * 5, 15)

    score = max(0, 100 - penalty)
    return stats, score


# ============================================================
# 综合分析
# ============================================================

def analyze_file(filepath: str) -> FrameworkReport:
    """分析单个文件"""
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    paragraphs = split_paragraphs(text)
    total_chars = count_chars(text)

    # P1: 意象感知多样性
    imagery_stats, imagery_score = analyze_imagery(paragraphs, total_chars)

    # P2: 段落功能 + 金句密度
    para_funcs, dist, punch_count, punch_density, punch_score = analyze_para_functions(paragraphs)

    # P3: 重复动作预算
    recurring_actions, recurring_score = analyze_recurring_actions(paragraphs)

    # P4: 替代词质量
    substitution_issues, substitution_score = analyze_substitution_quality(paragraphs)

    # P5: 指代密度
    referential_stats, referential_score = analyze_referential_density(paragraphs)

    # 综合评分（加权）
    framework_score = (
        imagery_score * 0.20 +
        punch_score * 0.20 +
        recurring_score * 0.20 +
        substitution_score * 0.25 +
        referential_score * 0.15
    )

    # 生成摘要
    summary_parts = []

    # P1 摘要
    over_budget = [s["word"] for s in imagery_stats if s["over_budget"]]
    channel_monotony = [s["word"] for s in imagery_stats if s["channel_monotony"]]
    if over_budget:
        summary_parts.append(f"意象超预算：{', '.join(over_budget)}")
    if channel_monotony:
        summary_parts.append(f"感官通道单调：{', '.join(channel_monotony)}")

    # P2 摘要
    if punch_density > 3:
        summary_parts.append(f"金句密度过高（{punch_density:.1f}/千字）")

    # P3 摘要
    over_limit_actions = [a["name"] for a in recurring_actions if a["over_limit"]]
    if over_limit_actions:
        summary_parts.append(f"重复动作超限：{', '.join(over_limit_actions)}")

    # P4 摘要
    critical_subs = [f"'{i['substitute']}'({i['substitute_count']}次)" 
                     for i in substitution_issues if i["severity"] == "critical"]
    if critical_subs:
        summary_parts.append(f"替代词退化：{', '.join(critical_subs)}")

    # P5 摘要
    over_limit_refs = [name for name, s in referential_stats.items() if s["over_limit"]]
    if over_limit_refs:
        summary_parts.append(f"指代过密：{', '.join(over_limit_refs)}")

    if not summary_parts:
        summary_parts.append("五维检测均在合理范围")

    return FrameworkReport(
        file=filepath,
        total_chars=total_chars,
        total_paragraphs=len(paragraphs),
        imagery_stats=imagery_stats,
        imagery_score=imagery_score,
        para_functions=para_funcs,
        function_distribution=dist,
        punchline_count=punch_count,
        punchline_density=punch_density,
        punchline_score=punch_score,
        recurring_actions=recurring_actions,
        recurring_action_score=recurring_score,
        substitution_issues=substitution_issues,
        substitution_score=substitution_score,
        referential_stats=referential_stats,
        referential_score=referential_score,
        framework_score=framework_score,
        summary="；".join(summary_parts),
    )


def print_report(report: FrameworkReport):
    """打印报告"""
    print(f"\n{'='*60}")
    print(f"文件：{report.file}")
    print(f"总字数：{report.total_chars} | 段落数：{report.total_paragraphs}")
    print(f"{'='*60}")

    # P1
    print(f"\n【P1 意象感知多样性】得分：{report.imagery_score:.1f}")
    print(f"{'─'*50}")
    for s in report.imagery_stats:
        status = "✗" if s["over_budget"] else "✓"
        var_status = "✗" if s["low_variation"] else "✓"
        mono_status = f"⚠️连续同通道×{len(s['consecutive_same_channel'])}" if s["channel_monotony"] else "✓"
        print(f"  {s['word']}: 核心{s['core_count']}/{s['budget']} {status} | "
              f"变体{s['variant_total']}({s['variation_ratio']*100:.0f}%) {var_status} | "
              f"通道{mono_status} | 密度{s['density_per_1k']}/千字")
        if s["variants"]:
            top_variants = sorted(s["variants"].items(), key=lambda x: -x[1])[:3]
            print(f"    变体TOP3：{', '.join(f'{k}({v})' for k,v in top_variants)}")
        if s["consecutive_same_channel"]:
            for cs in s["consecutive_same_channel"]:
                print(f"    ⚠️ 第{cs['start_para']}段起连续3次走'{cs['channel']}'通道")

    # P2
    print(f"\n【P2 金句密度】得分：{report.punchline_score:.1f}")
    print(f"{'─'*50}")
    print(f"  金句数：{report.punchline_count} | 密度：{report.punchline_density:.2f}/千字")
    print(f"  功能分布：")
    for func, info in report.function_distribution.items():
        print(f"    {func}: {info['count']}段 ({info['ratio']}%)")
    punchlines = [p for p in report.para_functions if p["has_punchline"]]
    if punchlines:
        print(f"\n  金句列表：")
        for p in punchlines:
            print(f"    第{p['para_num']}段 [{p['function']}]: {p['punchline_text']}")

    # P3
    print(f"\n【P3 重复动作预算】得分：{report.recurring_action_score:.1f}")
    print(f"{'─'*50}")
    for a in report.recurring_actions:
        status = "✗" if a["over_limit"] else "✓"
        print(f"  {a['name']}: {a['count']}/{a['max']} {status}")
        if a["over_limit"]:
            print(f"    ⚠️ {a['suggestion']}")
            if a["occurrences"]:
                print(f"    出现位置：第{', '.join(str(o['para']) for o in a['occurrences'])}段")

    # P4
    print(f"\n【P4 替代词质量】得分：{report.substitution_score:.1f}")
    print(f"{'─'*50}")
    if report.substitution_issues:
        for issue in report.substitution_issues:
            icon = "❌" if issue["severity"] == "critical" else "⚠️" if issue["severity"] == "warning" else "ℹ️"
            print(f"  {icon} '{issue['substitute']}'({issue['substitute_count']}次) > "
                  f"'{issue['original_word']}'({issue['original_count']}次) "
                  f"[{issue['severity']}]")
            print(f"    {issue['diagnosis']}")
            if issue["suggestion"]:
                print(f"    → {issue['suggestion']}")
    else:
        print("  ✓ 无替代词退化")

    # P5
    print(f"\n【P5 指代密度】得分：{report.referential_score:.1f}")
    print(f"{'─'*50}")
    for name, s in report.referential_stats.items():
        status = "✗" if s["over_limit"] else "✓"
        print(f"  '{name}': {s['count']}/{s['max']} {status}")
        if s["over_limit"]:
            print(f"    ⚠️ {s['issue']}")
            print(f"    → {s['suggestion']}")

    # 综合
    print(f"\n{'='*60}")
    print(f"【综合】框架得分：{report.framework_score:.1f}")
    print(f"摘要：{report.summary}")
    print(f"{'='*60}")


def main():
    if len(sys.argv) < 2:
        print("用法：python framework_experiment.py <file> [--json out.json] [--compare file2]")
        sys.exit(1)

    filepath = sys.argv[1]
    json_out = None
    compare_file = None

    for i, arg in enumerate(sys.argv[2:], 2):
        if arg == "--json" and i + 1 < len(sys.argv):
            json_out = sys.argv[i + 1]
        elif arg == "--compare" and i + 1 < len(sys.argv):
            compare_file = sys.argv[i + 1]

    if not os.path.exists(filepath):
        print(f"文件不存在：{filepath}")
        sys.exit(1)

    report = analyze_file(filepath)
    print_report(report)

    if compare_file and os.path.exists(compare_file):
        report2 = analyze_file(compare_file)
        print(f"\n{'='*60}")
        print(f"对比：{os.path.basename(filepath)} vs {os.path.basename(compare_file)}")
        print(f"{'='*60}")
        print(f"  P1 感知多样性：{report.imagery_score:.1f} → {report2.imagery_score:.1f}")
        print(f"  P2 金句密度：  {report.punchline_score:.1f} → {report2.punchline_score:.1f}")
        print(f"  P3 重复动作：  {report.recurring_action_score:.1f} → {report2.recurring_action_score:.1f}")
        print(f"  P4 替代词质量：{report.substitution_score:.1f} → {report2.substitution_score:.1f}")
        print(f"  P5 指代密度：  {report.referential_score:.1f} → {report2.referential_score:.1f}")
        print(f"  综合：         {report.framework_score:.1f} → {report2.framework_score:.1f}")

    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"\n报告已保存：{json_out}")


if __name__ == "__main__":
    main()
