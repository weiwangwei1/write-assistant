#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scene_perception_lint.py — 场景感知诊断器 v1.0

检测章节文本中"信息交付模式" vs "场景感知模式"的分布。
回答：为什么指纹全对的章节，读起来仍像"在交代事情"而非"在经历场景"？

用法:
  python scene_perception_lint.py chapter_001.txt
  python scene_perception_lint.py chapter_001.txt --json report.json
  python scene_perception_lint.py chapter_001.txt --compare chapter_001_v4.txt

诊断维度:
  D1. 信息交付段 (info_dump)     — 高信息密度、低感官锚定的段落
  D2. 叙述者翻译 (narrator_trans) — 动作后紧跟解释性句子（"行为不自足"）
  D3. 空间失锚 (spatial_drift)   — 动作序列缺少空间坐标
  D4. 感官一次性 (sensory_oneoff) — 引入后消失的感官细节
  D5. 焦距起点 (focal_entry)     — 开篇焦距层级检测
  D6. 世界自转 (world_rotation)   — 世界独立于角色存在的痕迹
"""

import json
import re
import sys
import os
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple, Optional


# ============================================================
# 数据结构
# ============================================================

@dataclass
class Issue:
    """单条诊断问题"""
    dim: str           # 维度代号 D1-D6
    dim_name: str      # 维度名称
    severity: str      # critical / warning / info
    location: str      # 位置描述（段落号/行号/引用文本）
    excerpt: str       # 问题文本摘录（≤80字）
    diagnosis: str     # 诊断说明
    suggestion: str    # 修改建议


@dataclass
class DimReport:
    """单维度报告"""
    dim: str
    dim_name: str
    score: float       # 0-100, 越高越好
    issues: List[Issue] = field(default_factory=list)
    stats: Dict = field(default_factory=dict)


@dataclass
class FullReport:
    """完整诊断报告"""
    file: str
    total_chars: int
    total_paragraphs: int
    overall_score: float
    dimensions: List[DimReport]
    summary: str

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "total_chars": self.total_chars,
            "total_paragraphs": self.total_paragraphs,
            "overall_score": round(self.overall_score, 1),
            "dimensions": [
                {
                    "dim": d.dim,
                    "dim_name": d.dim_name,
                    "score": round(d.score, 1),
                    "stats": d.stats,
                    "issues": [asdict(i) for i in d.issues],
                }
                for d in self.dimensions
            ],
            "summary": self.summary,
        }


# ============================================================
# 文本预处理
# ============================================================

def load_text(filepath: str) -> str:
    """读取文本文件"""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def split_paragraphs(text: str) -> List[str]:
    """按空行分段，过滤空段"""
    raw = re.split(r"\n\s*\n", text)
    return [p.strip() for p in raw if p.strip()]


def count_chars(text: str) -> int:
    """非空白字符数"""
    return len(re.sub(r"\s", "", text))


# ============================================================
# D1: 信息交付段检测
# ============================================================

# 感官动词——角色通过身体感知世界的信号
SENSORY_VERBS = [
    "看", "望", "盯", "瞧", "瞥", "凝视", "注视",
    "听", "闻", "嗅", "尝", "舔",
    "摸", "碰", "握", "攥", "捏", "按", "蹭",
    "感觉", "感到", "察觉", "觉察",
    "烫", "凉", "冷", "热", "疼", "痒", "麻", "酸",
    "听见", "看到", "闻到", "摸到",
]

# 信息标记词——暗示叙述者在"交代"而非"展示"
INFO_MARKERS = [
    "据说", "原来", "就是", "也就是说", "换句话说",
    "因为", "所以", "因此", "原因是",
    "规定", "制度", "编制", "条例",
    "叫了", "称为", "管这叫",
]

# 专名/数字密度信号
PROPER_NOUN_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}[营城墙]")

# 事实陈述句模式："...是...""...有...""...管...""...叫..."
FACT_STATEMENT_PATTERN = re.compile(
    r"[^。！？]*?(?:是|有|管|叫|规定|编制|征调|征诏)[^。！？]*?[。！？]"
)


def detect_info_dump(paragraphs: List[str]) -> DimReport:
    """
    D1: 检测信息交付段
    信号：段落中事实陈述密度高，但感官动词少
    → 写手在"交代信息"而非"让角色感知"
    """
    issues = []
    info_dump_count = 0
    total_checked = 0

    for idx, para in enumerate(paragraphs):
        if count_chars(para) < 30:
            continue
        total_checked += 1

        # 统计感官动词
        sensory_count = sum(para.count(v) for v in SENSORY_VERBS)
        # 统计信息标记词
        marker_count = sum(para.count(m) for m in INFO_MARKERS)
        # 统计数字（年份/编制/人数等）
        number_count = len(re.findall(r"\d+", para))
        # 统计事实陈述
        fact_count = len(FACT_STATEMENT_PATTERN.findall(para))

        # 信息密度 = 标记词 + 数字 + 事实陈述
        info_density = marker_count + number_count + fact_count * 0.5

        # 判定：信息密度高且感官锚定低
        if info_density >= 4 and sensory_count <= 1:
            info_dump_count += 1
            severity = "warning" if info_density >= 6 else "info"
            # 提取前80字
            excerpt = para[:80].replace("\n", " ")
            if len(para) > 80:
                excerpt += "..."
            issues.append(Issue(
                dim="D1",
                dim_name="信息交付段",
                severity=severity,
                location=f"第{idx+1}段",
                excerpt=excerpt,
                diagnosis=f"信息密度={info_density:.1f}（标记词{marker_count}+数字{number_count}+事实句{fact_count}），感官动词={sensory_count}",
                suggestion="让角色用身体感知这些信息：把'征诏令规定十二人'变成角色数人时手指划过名字的动作"
            ))

    # 评分：信息交付段占比越低越好
    ratio = info_dump_count / max(total_checked, 1)
    score = max(0, 100 - ratio * 200)

    return DimReport(
        dim="D1",
        dim_name="信息交付段",
        score=score,
        issues=issues[:15],  # 限制输出数量
        stats={
            "total_paragraphs_checked": total_checked,
            "info_dump_count": info_dump_count,
            "ratio": f"{ratio:.1%}",
        }
    )


# ============================================================
# D2: 叙述者翻译检测
# ============================================================

# 动作→解释的模式
# 典型：动作句 → "这是...""这比...""这说明..."
# 或：微动作 → "脸可以骗人，手不行"
TRANSLATION_PATTERNS = [
    # "这是/那叫/这比/这说明/这就叫" 紧跟在动作句后
    re.compile(r"([。！？])\s*([^。！？]*(?:这是|那叫|这比|这说明|这就叫|不是.*?是)[^。！？]*[。！？])"),
    # 动作段末尾的总结性解释："——..."或"。..."解释含义
    re.compile(r"([^\n。]{5,30}[。])\s*(?:——|也就是说|换句话说|换言之)"),
]

# 情感/意义解释标记词
EXPLANATION_MARKERS = [
    "这是", "那叫", "这比", "这说明", "这就叫",
    "不是A是B", "不是因为", "与其说是",
    "换句话说", "也就是说",
    "脸可以骗人", "手不行", "比任何", "更沉", "更重",
]


def detect_narrator_translation(paragraphs: List[str]) -> DimReport:
    """
    D2: 检测叙述者翻译
    信号：角色动作后紧跟叙述者的解释/定义/点评
    → P051"行为自足，叙述者退场"的违反
    """
    issues = []
    translation_count = 0

    for idx, para in enumerate(paragraphs):
        sentences = re.split(r"([。！？])", para)
        # 重组为完整句
        full_sentences = []
        for i in range(0, len(sentences) - 1, 2):
            full_sentences.append(sentences[i] + (sentences[i+1] if i+1 < len(sentences) else ""))

        for si, sent in enumerate(full_sentences):
            sent_stripped = sent.strip()
            if not sent_stripped or len(sent_stripped) < 5:
                continue

            # 检查是否是解释句
            is_explanation = any(m in sent_stripped for m in EXPLANATION_MARKERS)

            if is_explanation and si > 0:
                # 检查前一句是否是动作/行为
                prev_sent = full_sentences[si - 1].strip()
                action_words = ["手", "脸", "眼", "脚", "刀", "铜钱", "站", "蹲", "走", "转",
                                "握", "攥", "停", "抖", "翻", "磨", "跳", "扎", "砍"]
                has_action = any(w in prev_sent for w in action_words)

                if has_action:
                    translation_count += 1
                    combined = (prev_sent + " → " + sent_stripped)[:80]
                    issues.append(Issue(
                        dim="D2",
                        dim_name="叙述者翻译",
                        severity="warning",
                        location=f"第{idx+1}段, 第{si+1}句",
                        excerpt=combined,
                        diagnosis="角色动作后紧跟叙述者解释，行为不自足（违反P051）",
                        suggestion="删掉解释句，看动作自己能否传达含义。如不能，补行为而非补解释"
                    ))

    # 评分
    score = max(0, 100 - translation_count * 12)

    return DimReport(
        dim="D2",
        dim_name="叙述者翻译",
        score=score,
        issues=issues[:15],
        stats={
            "translation_count": translation_count,
        }
    )


# ============================================================
# D3: 空间失锚检测
# ============================================================

# 战斗/动作动词
ACTION_VERBS = ["跳", "扎", "劈", "砍", "冲", "退", "刺", "挡", "挥", "扑",
                "射", "掷", "推", "拉", "抽", "补", "转", "翻"]

# v2.0 双层锚点系统
# 强锚点：精确空间坐标（权重 1.0）
STRONG_ANCHORS = [
    # 方位
    "左", "右", "前", "后", "上", "下", "旁", "侧面", "对面",
    "身后", "面前", "头顶", "脚",
    # 环境物
    "城墙", "地面", "空中", "裂缝", "雉堞", "城", "墙", "门",
    "通道", "角落", "石地", "门框", "膝上", "掌心",
    # 距离表达
    "半步", "两步", "三步", "一步",
]

# 弱锚点：模糊但存在的空间表达（权重 0.5）
WEAK_ANCHORS = [
    "手边", "身旁", "身边", "附近", "近处", "不远处",
    "一旁", "一侧", "边上", "旁边", "身侧",
]

# 模式匹配：捕捉未列举的空间表达（权重 0.3）
SPATIAL_PATTERNS = [
    re.compile(r"[\u4e00-\u9fff](?:边|侧|旁)"),           # X边/X侧/X旁
    re.compile(r"(?:离|距)[^。！？]{1,6}步"),              # 离X两步
    re.compile(r"(?:左|右|前|后)(?:侧|方|面)"),             # 左侧/右方/后面
]

# 兼容旧引用
SPATIAL_ANCHORS = STRONG_ANCHORS


def _count_anchors(para: str) -> Tuple[float, int, int, int]:
    """v2.0 锚点计数：返回 (加权分, strong_count, weak_count, pattern_count)"""
    strong = sum(para.count(a) for a in STRONG_ANCHORS)
    weak = sum(para.count(a) for a in WEAK_ANCHORS)
    pattern_hits = sum(len(p.findall(para)) for p in SPATIAL_PATTERNS)
    weighted = strong * 1.0 + weak * 0.5 + pattern_hits * 0.3
    return weighted, strong, weak, pattern_hits


def _get_prev_context(paragraphs: List[str], idx: int) -> Tuple[float, dict]:
    """v2.0 前段上下文：回溯2段，带衰减（前1段×0.5，前2段×0.25）"""
    context_score = 0.0
    details = {}
    for lookback in range(1, min(3, idx + 1)):
        prev_para = paragraphs[idx - lookback]
        w, s, wk, p = _count_anchors(prev_para)
        decay = 0.5 / lookback
        contribution = w * decay
        context_score += contribution
        details[f"prev_{lookback}"] = {
            "weighted": round(w, 2),
            "strong": s, "weak": wk, "pattern": p,
            "contribution": round(contribution, 2),
        }
    return context_score, details


def detect_spatial_drift(paragraphs: List[str]) -> DimReport:
    """
    D3: 检测空间失锚（v2.0 优化版）
    信号：连续动作动词缺少空间坐标
    → P054"战斗前先建空间基线图"的违反

    v2.0 改进（替代 v1.1）：
    1. 双层锚点系统：STRONG(1.0) + WEAK(0.5) + PATTERN(0.3)
       → 识别"手边""身旁"等模糊但有效的空间表达
    2. 前段回溯2段（带衰减 0.5/0.25）
       → 空间基线建立后隔1段仍有效
    3. 锚点-动作比检测（A/A < 0.15 且上下文 < 0.3 时预警）
       → 动作密集但空间稀疏的段落
    4. 综合评分：当前段锚点 + 前段上下文
    """
    issues = []
    drift_count = 0
    action_paras_checked = 0

    for idx, para in enumerate(paragraphs):
        action_count = sum(para.count(v) for v in ACTION_VERBS)
        if action_count < 3:
            continue
        action_paras_checked += 1

        # v2.0: 双层锚点计数
        anchor_weighted, strong, weak, pattern = _count_anchors(para)

        # v2.0: 前段上下文（回溯2段）
        prev_context, prev_details = _get_prev_context(paragraphs, idx)

        # v2.0: 锚点-动作比
        anchor_action_ratio = anchor_weighted / max(action_count, 1)

        # v2.0: drift 判定逻辑
        # 条件1：当前段锚点 < 0.5 且前段上下文 < 0.5 → 严重失锚
        # 条件2：锚点-动作比 < 0.15 且前段上下文 < 0.3 → 动作在虚空中
        is_drift = False
        severity = "warning"
        diagnosis_parts = []

        if anchor_weighted < 0.5 and prev_context < 0.5:
            is_drift = True
            diagnosis_parts.append(
                f"当前段锚点={anchor_weighted:.1f}（strong={strong}/weak={weak}/pattern={pattern}），"
                f"前段上下文={prev_context:.2f}，动作发生在虚空中"
            )
        elif anchor_action_ratio < 0.15 and prev_context < 0.3:
            is_drift = True
            severity = "info"
            diagnosis_parts.append(
                f"锚点-动作比={anchor_action_ratio:.2f}（{anchor_weighted:.1f}/{action_count}），"
                f"动作密集但空间稀疏"
            )

        if is_drift:
            drift_count += 1
            sentences = re.findall(
                r"[^。！？]*[跳扎劈砍冲退刺挡挥扑射掷推拉抽补转翻][^。！？]*[。！？]", para
            )
            excerpt = (sentences[0] if sentences else para)[:80]
            issues.append(Issue(
                dim="D3",
                dim_name="空间失锚",
                severity=severity,
                location=f"第{idx+1}段",
                excerpt=excerpt + ("..." if len(excerpt) >= 80 else ""),
                diagnosis="；".join(diagnosis_parts),
                suggestion="在动作前补充空间基线图：谁在哪、距离多远、什么方向"
            ))

    score = max(0, 100 - drift_count * 20)

    return DimReport(
        dim="D3",
        dim_name="空间失锚",
        score=score,
        issues=issues[:10],
        stats={
            "drift_count": drift_count,
            "action_paras_checked": action_paras_checked,
        }
    )


# ============================================================
# D4: 感官一次性检测
# ============================================================

# 感官类别及其关键词
SENSORY_CATEGORIES = {
    "气味": ["味", "气", "臭", "腥", "香", "碱", "焦", "烧", "铁锈"],
    "温度": ["烫", "凉", "冷", "热", "冰", "暖", "寒", "干热", "湿"],
    "声音": ["声", "响", "磨", "嗡", "嘶", "咯吱", "碎", "哑", "劈"],
    "触感": ["糙", "滑", "涩", "硬", "软", "硌", "粗", "细"],
}


def detect_sensory_oneoff(paragraphs: List[str]) -> DimReport:
    """
    D4: 检测感官一次性（v1.1 优化版）
    信号：感官细节引入后在后续段落消失
    → P045"气味的萦绕性"的违反

    v1.1 改进：
    - 检测窗口从3段扩大到5段
    - 评分考虑全文萦绕率而非仅首次出现
    - 出现≥3次的类别视为有萦绕（即使首次间隔>5段）
    """
    issues = []
    oneoff_count = 0
    recall_stats = {}

    WINDOW = 5  # 检测窗口：后续5段内需再现
    RECALL_THRESHOLD = 3  # 全文出现≥3次视为有萦绕

    for category, keywords in SENSORY_CATEGORIES.items():
        appearances = []  # [(段落号, 关键词, 上下文)]
        for idx, para in enumerate(paragraphs):
            for kw in keywords:
                if kw in para:
                    appearances.append((idx, kw, para[:60]))

        total_appearances = len(appearances)
        recall_stats[category] = {
            "total_appearances": total_appearances,
            "first_para": appearances[0][0] if appearances else None,
            "last_para": appearances[-1][0] if appearances else None,
            "spread": (appearances[-1][0] - appearances[0][0]) if len(appearances) >= 2 else 0,
        }

        # 如果全文出现≥3次，视为有萦绕，跳过oneoff检测
        if total_appearances >= RECALL_THRESHOLD:
            recall_stats[category]["status"] = "萦绕"
            continue

        # 检查首次引入后是否有近距再现
        if not appearances:
            recall_stats[category]["status"] = "未出现"
            continue

        first_idx = appearances[0][0]
        has_nearby_recall = False
        for j in range(1, len(appearances)):
            if appearances[j][0] <= first_idx + WINDOW:
                has_nearby_recall = True
                break

        if not has_nearby_recall and first_idx < len(paragraphs) - 2:
            oneoff_count += 1
            recall_stats[category]["status"] = "一次性"
            kw = appearances[0][1]
            ctx = appearances[0][2]
            issues.append(Issue(
                dim="D4",
                dim_name="感官一次性",
                severity="info",
                location=f"第{first_idx+1}段",
                excerpt=ctx[:60] + "...",
                diagnosis=f"'{category}'类感官（关键词'{kw}'）引入后，后续{WINDOW}段内未再现（全文仅{total_appearances}次）——沦为信息标签而非萦绕氛围（违反P045）",
                suggestion=f"在后续段落中让'{kw}'再回来一次（哪怕半句），让感官萦绕不散"
            ))

    # v1.1 评分：考虑 oneoff 数量 + 全文萦绕率
    categories_with_sensory = sum(1 for v in recall_stats.values() if v["total_appearances"] > 0)
    categories_with_recall = sum(1 for v in recall_stats.values() if v.get("status") == "萦绕")
    recall_rate = categories_with_recall / max(categories_with_sensory, 1)

    # 基础分 100，每个 oneoff 扣 10 分，萦绕率低于 50% 再扣分
    score = max(0, 100 - oneoff_count * 10 - (1 - recall_rate) * 20 if categories_with_sensory > 0 else 100)

    return DimReport(
        dim="D4",
        dim_name="感官一次性",
        score=score,
        issues=issues[:8],
        stats={
            "oneoff_count": oneoff_count,
            "categories_checked": len(SENSORY_CATEGORIES),
            "categories_with_sensory": categories_with_sensory,
            "categories_with_recall": categories_with_recall,
            "recall_rate": f"{recall_rate:.0%}",
            "recall_details": recall_stats,
        }
    )


# ============================================================
# D5: 焦距起点检测
# ============================================================

# 世界级元素
WORLD_LEVEL_ELEMENTS = ["大陆", "天空", "大地", "世界", "位面", "星", "月", "日",
                        "风", "云", "天", "地平线", "山河", "城", "国", "朝"]
# 建筑级元素
BUILDING_LEVEL_ELEMENTS = ["城墙", "墙", "门", "塔", "楼", "院", "巷", "街", "营"]
# 人物级元素
CHARACTER_LEVEL_ELEMENTS = ["手", "脸", "眼", "脚", "头", "肩", "背", "指", "刀", "钱"]


# v2.0 画面层元素：具体物 + 视觉属性
VISUAL_OBJECTS = [
    "裂缝", "城墙", "石缝", "苔", "光", "风", "云", "雨", "雪",
    "门", "墙", "塔", "楼", "街", "巷", "河", "山", "树",
    "铜钱", "刀", "锁链", "战袍", "血", "纹路",
]
VISUAL_ATTRIBUTES = [
    "暗紫色", "灰白色", "红色", "黑色", "发亮", "发暗", "亮", "灭",
    "渗", "灌", "爬", "蠕动", "飘", "扫", "磕", "碎", "闪",
    "一收一放", "呼吸", "发光", "微光",
]


def _has_visual_image(text: str) -> Tuple[bool, int, int]:
    """检测文本是否包含画面（具体物+视觉属性）
    返回 (has_image, object_count, attribute_count)
    """
    obj_count = sum(1 for e in VISUAL_OBJECTS if e in text)
    attr_count = sum(1 for e in VISUAL_ATTRIBUTES if e in text)
    has_image = obj_count >= 1 and attr_count >= 1
    return has_image, obj_count, attr_count


def detect_focal_entry(paragraphs: List[str]) -> DimReport:
    """
    D5: 检测开篇焦距层级（v2.0 优化版）
    信号：第一句话的焦距高度 + 画面是否成立
    → P048"广角先于人物出场"的检测

    v2.0 改进：
    - 区分"画面级广角"（有具体物+视觉属性）和"概念级广角"（只有概念关键词）
    - "大徵在别的位面开了裂缝"有"位面"但无画面 → 概念级广角（75分非95分）
    - "裂缝开在城墙根上，暗紫色的光从石缝里渗出来" → 画面级广角（95分）
    """
    issues = []

    if not paragraphs:
        return DimReport(dim="D5", dim_name="焦距起点", score=0,
                        stats={"error": "无段落"})

    # v2.0: 检查前3句（开篇可能由多句建立画面）
    first_para = paragraphs[0]
    first_3_sentences = re.findall(r"[^。！？\n]*[。！？]", first_para)
    opening_text = "".join(first_3_sentences[:3]) if first_3_sentences else first_para[:80]

    # 取第一句话
    first_sentence_match = re.match(r"^([^。！？\n]*[。！？]?)", first_para)
    first_sentence = first_sentence_match.group(1).strip() if first_sentence_match else first_para[:50]

    # 判断焦距层级
    world_hits = sum(1 for e in WORLD_LEVEL_ELEMENTS if e in first_sentence)
    building_hits = sum(1 for e in BUILDING_LEVEL_ELEMENTS if e in first_sentence)
    char_hits = sum(1 for e in CHARACTER_LEVEL_ELEMENTS if e in first_sentence)

    # v2.0: 画面检测（前3句范围内）
    has_image, obj_count, attr_count = _has_visual_image(opening_text)

    if world_hits >= char_hits and world_hits > 0:
        if has_image:
            level = "画面级广角"
            score = 95
            diagnosis = f"开篇从世界级广角开始且有画面（具体物{obj_count}+视觉属性{attr_count}），符合P048"
        else:
            level = "概念级广角"
            score = 75
            issues.append(Issue(
                dim="D5",
                dim_name="焦距起点",
                severity="warning",
                location="第1段, 前3句",
                excerpt=opening_text[:60],
                diagnosis=f"开篇有世界级关键词（{world_hits}个）但无画面（具体物{obj_count}+视觉属性{attr_count}）——读者'知道'但'看不见'（违反P048画面优先）",
                suggestion="在第一句中加入具体物+视觉属性：如'暗紫色的光从裂缝里渗出来'让读者看见画面"
            ))
    elif building_hits >= char_hits and building_hits > 0:
        level = "建筑级中景"
        score = 60
        issues.append(Issue(
            dim="D5",
            dim_name="焦距起点",
            severity="warning",
            location="第1段, 第1句",
            excerpt=first_sentence[:60],
            diagnosis=f"开篇焦距在建筑级（{level}），缺少世界级广角建立空间纵深感（违反P048）",
            suggestion="在第一句前加1-2句世界级广角：'大徵在别的位面开了裂缝'级别的宏观视野"
        ))
    else:
        level = "人物级近景"
        score = 30
        issues.append(Issue(
            dim="D5",
            dim_name="焦距起点",
            severity="critical",
            location="第1段, 第1句",
            excerpt=first_sentence[:60],
            diagnosis=f"开篇焦距在人物级（{level}），读者进入场景时没有空间锚（违反P048）",
            suggestion="从世界级广角起笔，推到建筑级，再推到人物——九级变焦的第一步"
        ))

    return DimReport(
        dim="D5",
        dim_name="焦距起点",
        score=score,
        issues=issues,
        stats={
            "first_sentence": first_sentence[:60],
            "opening_text": opening_text[:80],
            "focal_level": level,
            "world_hits": world_hits,
            "building_hits": building_hits,
            "character_hits": char_hits,
            "has_visual_image": has_image,
            "visual_objects": obj_count,
            "visual_attributes": attr_count,
        }
    )


# ============================================================
# D6: 世界自转检测
# ============================================================

def detect_world_rotation(paragraphs: List[str]) -> DimReport:
    """
    D6: 检测世界自转痕迹
    信号：存在与角色剧情无关的世界独立活动描写
    → P001"世界重量段"的检测（正面指标，有则加分）
    """
    issues = []
    rotation_count = 0

    # 世界自转信号：段落中包含与角色无关的生物/天气/物件变化
    rotation_signals = [
        ("生物活动", ["虫", "苔", "鸟", "鼠", "蚁", "爬", "啃", "飞", "蠕动"]),
        ("天气变化", ["风", "雨", "雪", "光", "暗", "亮", "灭", "云"]),
        ("物件自主变化", ["被吹", "滑落", "碰到", "发亮", "发暗", "变了"]),
    ]

    for idx, para in enumerate(paragraphs):
        # 检查是否包含世界自转信号
        for signal_name, keywords in rotation_signals:
            hits = [kw for kw in keywords if kw in para]
            if hits:
                # 检查是否与角色直接相关
                char_refs = sum(1 for c in ["程铖", "他", "老周", "主角"] if c in para)
                # 如果角色提及少，更像世界自转
                if char_refs <= 2:
                    rotation_count += 1
                    excerpt = para[:60].replace("\n", " ")
                    issues.append(Issue(
                        dim="D6",
                        dim_name="世界自转",
                        severity="info",
                        location=f"第{idx+1}段",
                        excerpt=excerpt + ("..." if len(para) > 60 else ""),
                        diagnosis=f"发现世界自转痕迹（{signal_name}：{','.join(hits[:3])}），与角色剧情关联度低",
                        suggestion="保留——世界独立存在感是正面指标"
                    ))
                    break

    # 评分：有世界自转痕迹是好的
    if rotation_count >= 3:
        score = 90
    elif rotation_count >= 1:
        score = 70
    else:
        score = 30
        issues.append(Issue(
            dim="D6",
            dim_name="世界自转",
            severity="warning",
            location="全文",
            excerpt="（未检测到世界自转段落）",
            diagnosis="全文未发现与角色剧情无关的世界独立活动描写（违反P001）",
            suggestion="加入1-2句世界自转：角色不看时，世界仍在运转（虫在爬、风在吹、物件在变）"
        ))

    return DimReport(
        dim="D6",
        dim_name="世界自转",
        score=score,
        issues=issues[:8],
        stats={
            "rotation_count": rotation_count,
        }
    )


# ============================================================
# D7: 专名首次锚定检测
# ============================================================

# 世界观新造专名（非通用汉语词）
PROPER_NOUNS = [
    "大徵", "征诏令", "征调者", "功勋", "界门", "壳", "半壳",
    "灵矢", "雉堞", "垛口", "征调", "第七营", "第六营",
    "暗紫色",  # 特定世界观色彩
]

# 锚定模式：专名前后有这些词/句式时视为有锚定
ANCHORING_PATTERNS = [
    re.compile(r"(?:是|叫|管|用|换|称|属于|来自|开|派)[^。！？]{0,10}"),
    re.compile(r"[^。！？]{0,15}(?:是|叫|管|用|换|称|属于|的)"),
    re.compile(r"(?:朝廷|帝国|王朝|制度|法令|规矩|命令|补给)"),
    re.compile(r"(?:进去|出来|回来|从|到|往|朝)"),  # 方向/动作锚定
]

# 已知锚定词组（专名+紧跟的锚定上下文）
KNOWN_ANCHORS = {
    "大徵": ["朝廷", "天下", "开的", "派", "从"],
    "征诏令": ["管", "管着"],
    "征调者": ["派", "进去", "拿"],
    "功勋": ["换", "算", "补给"],
    "界门": ["开", "亮", "关"],
    "壳": ["变成", "空的", "死了"],
    "半壳": ["比壳惨", "还知道"],
    "灵矢": ["剩", "支", "清点"],
    "雉堞": ["后面", "靠着"],
    "垛口": ["灌", "风"],
}


def _find_proper_noun_positions(text: str) -> List[Tuple[str, int]]:
    """找到所有专名的位置 [(name, position), ...]"""
    positions = []
    for noun in PROPER_NOUNS:
        start = 0
        while True:
            idx = text.find(noun, start)
            if idx == -1:
                break
            positions.append((noun, idx))
            start = idx + len(noun)
    return positions


def _has_anchoring(text: str, noun: str, position: int, window: int = 20) -> bool:
    """检查专名在 position 处是否有锚定信息（前后 window 字内）"""
    # 检查已知锚定词
    known = KNOWN_ANCHORS.get(noun, [])
    context_before = text[max(0, position - window):position]
    context_after = text[position:position + len(noun) + window]
    full_context = context_before + context_after

    for anchor_word in known:
        if anchor_word in full_context:
            return True

    # 检查锚定模式
    for pattern in ANCHORING_PATTERNS:
        if pattern.search(full_context):
            return True

    return False


def detect_proper_noun_anchoring(paragraphs: List[str]) -> DimReport:
    """
    D7: 专名首次锚定检测
    信号：新造专名第一次出现时，前后20字内是否有锚定信息
    → 读者能否理解这个专名是什么

    规则：
    - 专名首次出现时检查前后20字
    - 有锚定（是什么/属于谁/干什么用/方向动作）→ 通过
    - 无锚定 → warning，建议补锚定
    - 第二次及之后出现不检测（默认已锚定）
    """
    issues = []
    full_text = "\n".join(paragraphs)
    unanchored_count = 0
    first_occurrences = {}

    # 找到所有专名位置
    all_positions = _find_proper_noun_positions(full_text)

    # 按专名分组，取第一次出现
    for noun, pos in all_positions:
        if noun not in first_occurrences:
            first_occurrences[noun] = pos

    # 检查每个专名的首次出现
    for noun, pos in first_occurrences.items():
        has_anchor = _has_anchoring(full_text, noun, pos)

        # 找到段落号
        char_count = 0
        para_num = 1
        for idx, para in enumerate(paragraphs):
            if char_count + len(para) > pos:
                para_num = idx + 1
                break
            char_count += len(para) + 1  # +1 for \n

        # 提取上下文
        context_start = max(0, pos - 15)
        context_end = min(len(full_text), pos + len(noun) + 15)
        context = full_text[context_start:context_end].replace("\n", " ")

        if not has_anchor:
            unanchored_count += 1
            issues.append(Issue(
                dim="D7",
                dim_name="专名锚定",
                severity="warning",
                location=f"第{para_num}段",
                excerpt=context,
                diagnosis=f"专名'{noun}'首次出现时无锚定信息（前后20字内无'是什么/属于谁/干什么用'）——读者不知道'{noun}'是什么",
                suggestion=f"在'{noun}'首次出现时补一句锚定：如'{noun}是...的...'或用上下文暗示其性质"
            ))

    score = max(0, 100 - unanchored_count * 15)

    return DimReport(
        dim="D7",
        dim_name="专名锚定",
        score=score,
        issues=issues[:10],
        stats={
            "proper_nouns_found": len(first_occurrences),
            "unanchored_count": unanchored_count,
            "anchored_count": len(first_occurrences) - unanchored_count,
            "nouns_checked": list(first_occurrences.keys()),
        }
    )


# ============================================================
# 主诊断流程
# ============================================================

def diagnose(text: str, filepath: str = "") -> FullReport:
    """对文本执行完整诊断"""
    paragraphs = split_paragraphs(text)
    total_chars = count_chars(text)

    # 执行各维度检测
    d1 = detect_info_dump(paragraphs)
    d2 = detect_narrator_translation(paragraphs)
    d3 = detect_spatial_drift(paragraphs)
    d4 = detect_sensory_oneoff(paragraphs)
    d5 = detect_focal_entry(paragraphs)
    d6 = detect_world_rotation(paragraphs)
    d7 = detect_proper_noun_anchoring(paragraphs)

    dimensions = [d1, d2, d3, d4, d5, d6, d7]

    # 综合评分（加权）
    weights = {
        "D1": 0.17,  # 信息交付段
        "D2": 0.17,  # 叙述者翻译
        "D3": 0.13,  # 空间失锚
        "D4": 0.13,  # 感官一次性
        "D5": 0.13,  # 焦距起点
        "D6": 0.12,  # 世界自转
        "D7": 0.15,  # 专名锚定
    }
    overall = sum(d.score * weights[d.dim] for d in dimensions)

    # 生成摘要
    critical_count = sum(1 for d in dimensions for i in d.issues if i.severity == "critical")
    warning_count = sum(1 for d in dimensions for i in d.issues if i.severity == "warning")

    if overall >= 80:
        summary = f"场景感知度良好（{overall:.0f}分）。{warning_count}处待优化，无严重问题。"
    elif overall >= 60:
        summary = f"场景感知度中等（{overall:.0f}分）。{critical_count}处严重 + {warning_count}处待优化，存在信息交付模式残留。"
    else:
        summary = f"场景感知度不足（{overall:.0f}分）。{critical_count}处严重 + {warning_count}处待优化，信息交付模式主导，需重构写作思维。"

    return FullReport(
        file=filepath,
        total_chars=total_chars,
        total_paragraphs=len(paragraphs),
        overall_score=overall,
        dimensions=dimensions,
        summary=summary,
    )


def print_report(report: FullReport):
    """控制台输出报告"""
    print("=" * 70)
    print(f"  场景感知诊断报告")
    print(f"  文件: {report.file or '(stdin)'}")
    print(f"  字数: {report.total_chars} | 段落: {report.total_paragraphs}")
    print("=" * 70)
    print()

    # 总分
    score_color = "" if report.overall_score >= 80 else ""
    print(f"  综合评分: {report.overall_score:.1f} / 100")
    print(f"  {report.summary}")
    print()
    print("-" * 70)

    # 各维度
    for d in report.dimensions:
        bar = "█" * int(d.score / 5) + "░" * (20 - int(d.score / 5))
        print(f"  {d.dim} {d.dim_name:<8s} {bar} {d.score:>5.1f}")
        for stat_key, stat_val in d.stats.items():
            if stat_key != "error":
                print(f"       {stat_key}: {stat_val}")
        if d.issues:
            print(f"       问题 ({len(d.issues)}条):")
            for issue in d.issues[:3]:  # 每维度最多显示3条
                severity_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(issue.severity, "⚪")
                print(f"         {severity_icon} [{issue.severity}] {issue.location}")
                print(f"            摘录: {issue.excerpt}")
                print(f"            诊断: {issue.diagnosis}")
                if issue.severity in ("critical", "warning"):
                    print(f"            建议: {issue.suggestion}")
            if len(d.issues) > 3:
                print(f"         ... 还有 {len(d.issues) - 3} 条")
        print()

    print("=" * 70)


def compare_reports(report_a: FullReport, report_b: FullReport):
    """对比两个版本"""
    print()
    print("=" * 70)
    print("  版本对比")
    print("=" * 70)
    print(f"  {'维度':<12s} {'版本A':>8s} {'版本B':>8s} {'变化':>8s}")
    print(f"  {'-'*40}")
    print(f"  {'综合评分':<12s} {report_a.overall_score:>8.1f} {report_b.overall_score:>8.1f} {report_b.overall_score - report_a.overall_score:>+8.1f}")
    for da, db in zip(report_a.dimensions, report_b.dimensions):
        delta = db.score - da.score
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        print(f"  {da.dim} {da.dim_name:<8s} {da.score:>8.1f} {db.score:>8.1f} {arrow}{abs(delta):>7.1f}")
    print()


# ============================================================
# CLI
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="场景感知诊断器")
    parser.add_argument("file", help="待诊断的章节文本文件")
    parser.add_argument("--json", help="输出 JSON 报告到指定文件")
    parser.add_argument("--compare", help="对比另一版本文件")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"错误：文件不存在 {args.file}")
        sys.exit(2)

    text = load_text(args.file)
    report = diagnose(text, args.file)

    if args.compare:
        if not os.path.exists(args.compare):
            print(f"错误：对比文件不存在 {args.compare}")
            sys.exit(2)
        text_b = load_text(args.compare)
        report_b = diagnose(text_b, args.compare)
        print_report(report)
        print_report(report_b)
        compare_reports(report, report_b)
    else:
        print_report(report)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"  JSON 报告已保存: {args.json}")


if __name__ == "__main__":
    main()
