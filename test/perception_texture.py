#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perception_texture.py — 感知织体诊断器 v6.0

v6.0 核心变更：
  1. 4维→3维（砍掉T4节律控制——固定预算不区分场景）
  2. T1 精简：删除四分类(embodied/partial/weak/plain)，只检测问题段
  3. T2 扩展：新增情绪直说+总结评论检测，打破v5.0天花板效应
  4. T3 重构：增加意象词筛选层，排除人名/场景词/术语（误报率73%→0%）
  5. 评分改为维度评级（A/B/C/D木桶效应），取消综合加权评分

  T1 场景具身度      [段落级]  段落是角色在感知还是作者在交代
  T2 叙述者介入度    [段落级]  作者在多大程度上"抢过话筒"
  T3 意象多样性      [词级]    关键意象词是否被多维度感知

用法:
  python perception_texture.py chapter_001.txt
  python perception_texture.py chapter_001.txt --json report.json
  python perception_texture.py ch1.txt --compare ch2.txt
  python perception_texture.py chapter_001.txt --dims T1,T2
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
class Issue:
    severity: str          # critical / warning / info
    location: str          # 位置描述
    excerpt: str           # 问题文本摘录
    diagnosis: str         # 诊断说明
    suggestion: str = ""   # 修改建议


@dataclass
class DimReport:
    dim: str
    dim_name: str
    score: float
    grade: str = ""        # v6.0: A/B/C/D 评级
    stats: Dict = field(default_factory=dict)
    issues: List[Issue] = field(default_factory=list)


@dataclass
class TextureReport:
    file: str
    total_chars: int
    total_paragraphs: int
    t1: DimReport
    t2: DimReport
    t3: DimReport
    overall_grade: str     # v6.0: 最低维度评级
    overall_score: float   # v6.0: 参考分（非主要指标）
    summary: str

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "total_chars": self.total_chars,
            "total_paragraphs": self.total_paragraphs,
            "overall_grade": self.overall_grade,
            "overall_score": round(self.overall_score, 1),
            "t1": _dim_to_dict(self.t1),
            "t2": _dim_to_dict(self.t2),
            "t3": _dim_to_dict(self.t3),
            "summary": self.summary,
        }


def _dim_to_dict(d: DimReport) -> dict:
    return {
        "dim": d.dim,
        "dim_name": d.dim_name,
        "score": round(d.score, 1),
        "grade": d.grade,
        "stats": d.stats,
        "issues": [asdict(i) for i in d.issues],
    }


def grade_score(score: float) -> str:
    """v6.0: 维度评级 A/B/C/D"""
    if score >= 85:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 55:
        return "C"
    else:
        return "D"


GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1}


# ============================================================
# 文本预处理
# ============================================================

def load_text(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def split_paragraphs(text: str) -> List[str]:
    raw = re.split(r"\n\s*\n", text)
    return [p.strip() for p in raw if p.strip()]


def count_chars(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def split_sentences(para: str) -> List[str]:
    """按句末标点分句，保留完整句"""
    parts = re.split(r"([。！？])", para)
    sentences = []
    for i in range(0, len(parts) - 1, 2):
        sentences.append(parts[i] + (parts[i + 1] if i + 1 < len(parts) else ""))
    if parts[-1].strip():
        sentences.append(parts[-1].strip())
    return [s.strip() for s in sentences if s.strip()]


def is_dialogue(para: str) -> bool:
    """检测段落是否为对话段"""
    return para.count('"') >= 2 or para.count('"') >= 2 or para.count('「') >= 2


# ============================================================
# T1: 场景具身度（v6.0 精简版）
# ============================================================

# --- 空间锚点（保留 D3 v2.0 双层锚点系统）---

STRONG_ANCHORS = [
    "左", "右", "前", "后", "上", "下", "旁", "对面",
    "身后", "面前", "头顶", "脚",
    "城墙", "地面", "空中", "裂缝", "雉堞", "城", "墙", "门",
    "通道", "角落", "石地", "门框", "膝上", "掌心",
    "半步", "两步", "三步", "一步",
]
WEAK_ANCHORS = [
    "手边", "身旁", "身边", "附近", "近处", "不远处",
    "一旁", "一侧", "边上", "旁边", "身侧",
]
SPATIAL_PATTERNS = [
    re.compile(r"[\u4e00-\u9fff](?:边|侧|旁)"),
    re.compile(r"(?:离|距)[^。！？]{1,6}步"),
    re.compile(r"(?:左|右|前|后)(?:侧|方|面)"),
]

# 动作动词（用于空间失锚检测）
ACTION_VERBS = ["跳", "扎", "劈", "砍", "冲", "退", "刺", "挡", "挥", "扑",
                "射", "掷", "推", "拉", "抽", "补", "转", "翻"]

# --- 信息交付段检测 ---

INFO_MARKERS = [
    "据说", "原来", "就是", "也就是说", "换句话说",
    "因为", "所以", "因此", "原因是",
    "规定", "制度", "编制", "条例",
    "叫了", "称为", "管这叫",
]
FACT_STATEMENT_PATTERN = re.compile(
    r"[^。！？]*?(?:是|有|管|叫|规定|编制|征调|征诏)[^。！？]*?[。！？]"
)

# 身体部位（用于排除信息交付段——有身体参与的段落不是纯信息交付）
BODY_PARTS = [
    "手", "指", "掌", "拳", "腕", "臂",
    "眼", "脸", "眉", "唇", "牙", "额", "头", "喉",
    "肩", "背", "腰", "脚", "膝", "腿",
    "心跳", "呼吸", "脉搏",
]

# 感官动词（同上，用于排除）
SENSORY_VERBS = [
    "看", "望", "盯", "瞧", "瞥", "凝视", "注视",
    "听", "闻", "嗅", "尝", "舔",
    "摸", "碰", "握", "攥", "捏", "按", "蹭",
    "感觉", "感到", "察觉", "觉察",
    "烫", "凉", "冷", "热", "疼", "痒", "麻", "酸",
    "听见", "看到", "闻到", "摸到",
]

# --- 专名锚定（保留 D7）---

PROPER_NOUNS = [
    "大徵", "征诏令", "征调者", "功勋", "界门", "壳", "半壳",
    "灵矢", "雉堞", "垛口", "征调", "第七营", "第六营",
    "暗紫色",
]
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
ANCHORING_PATTERNS = [
    re.compile(r"(?:是|叫|管|用|换|称|属于|来自|开|派)[^。！？]{0,10}"),
    re.compile(r"[^。！？]{0,15}(?:是|叫|管|用|换|称|属于|的)"),
    re.compile(r"(?:朝廷|帝国|王朝|制度|法令|规矩|命令|补给)"),
    re.compile(r"(?:进去|出来|回来|从|到|往|朝)"),
]

# --- 焦距起点（保留 D5）---

WORLD_LEVEL_ELEMENTS = ["大陆", "天空", "大地", "世界", "位面", "星", "月", "日",
                        "风", "云", "天", "地平线", "山河", "城", "国", "朝"]
BUILDING_LEVEL_ELEMENTS = ["城墙", "墙", "门", "塔", "楼", "院", "巷", "街", "营"]
CHARACTER_LEVEL_ELEMENTS = ["手", "脸", "眼", "脚", "头", "肩", "背", "指", "刀", "钱"]
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


def _count_anchors(para: str) -> Tuple[float, int, int, int]:
    """v2.0 锚点计数（搬迁自 D3）"""
    strong = sum(para.count(a) for a in STRONG_ANCHORS)
    weak = sum(para.count(a) for a in WEAK_ANCHORS)
    pattern_hits = sum(len(p.findall(para)) for p in SPATIAL_PATTERNS)
    weighted = strong * 1.0 + weak * 0.5 + pattern_hits * 0.3
    return weighted, strong, weak, pattern_hits


def _get_prev_context(paragraphs: List[str], idx: int) -> float:
    """前段上下文回溯2段（搬迁自 D3 v2.0）"""
    context_score = 0.0
    for lookback in range(1, min(3, idx + 1)):
        prev_para = paragraphs[idx - lookback]
        w, _, _, _ = _count_anchors(prev_para)
        decay = 0.5 / lookback
        context_score += w * decay
    return context_score


def _has_visual_image(text: str) -> Tuple[bool, int, int]:
    """画面检测（搬迁自 D5 v2.0）"""
    obj_count = sum(1 for e in VISUAL_OBJECTS if e in text)
    attr_count = sum(1 for e in VISUAL_ATTRIBUTES if e in text)
    return (obj_count >= 1 and attr_count >= 1), obj_count, attr_count


def _has_anchoring(text: str, noun: str, position: int, window: int = 20) -> bool:
    """专名锚定检测（搬迁自 D7）"""
    known = KNOWN_ANCHORS.get(noun, [])
    context_before = text[max(0, position - window):position]
    context_after = text[position:position + len(noun) + window]
    full_context = context_before + context_after
    for aw in known:
        if aw in full_context:
            return True
    for pattern in ANCHORING_PATTERNS:
        if pattern.search(full_context):
            return True
    return False


# --- v6.0 T1 核心检测函数 ---

def detect_info_dump(para: str) -> bool:
    """v6.0: 信息交付段检测——简化版

    v5.0 问题：四分类(embodied/partial/weak/plain)+梯度评分，
              本质是感官动词/身体部位/锚点的表面计数，分类不可靠。
    v6.0 修复：只检测"问题段"——信息密度高但无身体参与。

    判定条件（同时满足）：
      1. 信息信号 ≥ 4（陈述句式+数字+事实句）
      2. 身体部位 ≤ 1（角色身体不在场）
      3. 感官动词 ≤ 1（角色不在感知）
      4. 非对话段
    """
    cc = count_chars(para)
    if cc < 20:
        return False

    if is_dialogue(para):
        return False

    # 信息信号
    marker_count = sum(para.count(m) for m in INFO_MARKERS)
    number_count = len(re.findall(r"\d+", para))
    fact_count = len(FACT_STATEMENT_PATTERN.findall(para))
    info_signals = marker_count + number_count + fact_count * 0.5

    # 身体参与
    body_count = sum(para.count(b) for b in BODY_PARTS)
    sensory_count = sum(para.count(v) for v in SENSORY_VERBS)

    return info_signals >= 4 and body_count <= 1 and sensory_count <= 1


def check_spatial_drift(para: str, paragraphs: List[str], idx: int) -> Optional[Issue]:
    """空间失锚检测（保留 D3 v2.0，动作密集段）"""
    action_count = sum(para.count(v) for v in ACTION_VERBS)
    if action_count < 3:
        return None

    anchor_weighted, strong, weak, pattern = _count_anchors(para)
    prev_context = _get_prev_context(paragraphs, idx)
    anchor_action_ratio = anchor_weighted / max(action_count, 1)

    if anchor_weighted < 0.5 and prev_context < 0.5:
        return Issue(
            severity="warning",
            location=f"第{idx+1}段",
            excerpt=para[:80] + ("..." if len(para) > 80 else ""),
            diagnosis=f"动作段无空间锚（锚点={anchor_weighted:.1f}，前段上下文={prev_context:.2f}）",
            suggestion="在动作前补充空间基线：谁在哪、距离多远、什么方向"
        )
    elif anchor_action_ratio < 0.15 and prev_context < 0.3:
        return Issue(
            severity="info",
            location=f"第{idx+1}段",
            excerpt=para[:80] + ("..." if len(para) > 80 else ""),
            diagnosis=f"动作密集但空间稀疏（锚点-动作比={anchor_action_ratio:.2f}）",
            suggestion="适当补充空间坐标，让动作有落脚点"
        )
    return None


def check_focal_entry(paragraphs: List[str]) -> Tuple[str, Optional[Issue]]:
    """开篇焦距检测（保留 D5 v2.0）"""
    if not paragraphs:
        return "unknown", None

    first_para = paragraphs[0]
    first_3_sentences = re.findall(r"[^。！？\n]*[。！？]", first_para)
    opening_text = "".join(first_3_sentences[:3]) if first_3_sentences else first_para[:80]

    first_sentence_match = re.match(r"^([^。！？\n]*[。！？]?)", first_para)
    first_sentence = first_sentence_match.group(1).strip() if first_sentence_match else first_para[:50]

    world_hits = sum(1 for e in WORLD_LEVEL_ELEMENTS if e in first_sentence)
    building_hits = sum(1 for e in BUILDING_LEVEL_ELEMENTS if e in first_sentence)
    char_hits = sum(1 for e in CHARACTER_LEVEL_ELEMENTS if e in first_sentence)
    has_image, obj_count, attr_count = _has_visual_image(opening_text)

    if world_hits >= char_hits and world_hits > 0:
        if has_image:
            return "画面级广角", None
        else:
            return "概念级广角", Issue(
                severity="warning",
                location="第1段, 前3句",
                excerpt=opening_text[:60],
                diagnosis=f"开篇有世界级关键词但无画面（具体物{obj_count}+视觉属性{attr_count}）——读者'知道'但'看不见'",
                suggestion="在第一句中加入具体物+视觉属性：如'暗紫色的光从裂缝里渗出来'让读者看见画面"
            )
    elif building_hits >= char_hits and building_hits > 0:
        return "建筑级中景", Issue(
            severity="warning",
            location="第1段, 第1句",
            excerpt=first_sentence[:60],
            diagnosis="开篇焦距在建筑级，缺少世界级广角建立空间纵深感",
            suggestion="在第一句前加1-2句世界级广角"
        )
    else:
        return "人物级近景", Issue(
            severity="critical",
            location="第1段, 第1句",
            excerpt=first_sentence[:60],
            diagnosis="开篇焦距在人物级，读者进入场景时没有空间锚",
            suggestion="从世界级广角起笔，推到建筑级，再推到人物"
        )


def check_proper_noun_anchoring(paragraphs: List[str]) -> List[Issue]:
    """专名锚定检测（保留 D7）"""
    issues = []
    full_text = "\n".join(paragraphs)
    first_occurrences = {}

    for noun in PROPER_NOUNS:
        start = 0
        while True:
            idx = full_text.find(noun, start)
            if idx == -1:
                break
            if noun not in first_occurrences:
                first_occurrences[noun] = idx
            start = idx + len(noun)

    for noun, pos in first_occurrences.items():
        if not _has_anchoring(full_text, noun, pos):
            char_count = 0
            para_num = 1
            for idx, para in enumerate(paragraphs):
                if char_count + len(para) > pos:
                    para_num = idx + 1
                    break
                char_count += len(para) + 1

            context_start = max(0, pos - 15)
            context_end = min(len(full_text), pos + len(noun) + 15)
            context = full_text[context_start:context_end].replace("\n", " ")

            issues.append(Issue(
                severity="warning",
                location=f"第{para_num}段",
                excerpt=context,
                diagnosis=f"专名'{noun}'首次出现时无锚定信息——读者不知道'{noun}'是什么",
                suggestion=f"在'{noun}'首次出现时补一句锚定：如'{noun}是...的...'或用上下文暗示其性质"
            ))

    return issues


def detect_t1(paragraphs: List[str]) -> DimReport:
    """v6.0 T1: 场景具身度——只检测问题段"""
    issues = []
    info_dump_count = 0

    for idx, para in enumerate(paragraphs):
        # 1. 信息交付段
        if detect_info_dump(para):
            info_dump_count += 1
            excerpt = para[:80].replace("\n", " ")
            if len(para) > 80:
                excerpt += "..."
            issues.append(Issue(
                severity="warning",
                location=f"第{idx+1}段",
                excerpt=excerpt,
                diagnosis="信息密度高但无身体参与——作者在交代信息而非角色在感知",
                suggestion="让角色用身体感知这些信息：把'征诏令规定十二人'变成角色数人时手指划过名字"
            ))

        # 2. 空间失锚
        drift = check_spatial_drift(para, paragraphs, idx)
        if drift:
            issues.append(drift)

    # 3. 焦距起点
    focal_level, focal_issue = check_focal_entry(paragraphs)
    if focal_issue:
        issues.append(focal_issue)

    # 4. 专名锚定
    noun_issues = check_proper_noun_anchoring(paragraphs)
    issues.extend(noun_issues)

    # 评分
    score = 100
    score -= info_dump_count * 10
    score -= len([i for i in issues if i.severity == "warning" and "空间" in i.diagnosis]) * 5
    if focal_level == "人物级近景":
        score -= 10
    elif focal_level == "建筑级中景":
        score -= 5
    elif focal_level == "概念级广角":
        score -= 5
    score -= len(noun_issues) * 5
    score = max(0, min(100, score))

    return DimReport(
        dim="T1",
        dim_name="场景具身度",
        score=score,
        grade=grade_score(score),
        stats={
            "total_paragraphs": len(paragraphs),
            "info_dump": info_dump_count,
            "spatial_drift": len([i for i in issues if "空间" in i.diagnosis]),
            "focal_level": focal_level,
            "unanchored_nouns": len(noun_issues),
        },
        issues=issues[:20],
    )


# ============================================================
# T2: 叙述者介入度（v6.0 扩展版）
# ============================================================

# --- 动作后解释（保留 D2）---

EXPLANATION_MARKERS = [
    "这是", "那叫", "这比", "这说明", "这就叫", "管这叫",
    "不是A是B", "不是因为", "与其说是",
    "换句话说", "也就是说",
    "脸可以骗人", "手不行", "比任何", "更沉", "更重",
    "其实", "也没有用", "不能让",
    "不算", "不是因为", "倒不是", "与其说",
]

# --- 金句模式（保留 v5.0 语义过滤版）---

PUNCHLINE_PATTERNS = [
    re.compile(r"[^。！？]*(?:不.*?也|没.*?却|不.*?倒是)[^。！？]*[。！？]"),
    re.compile(r"[^。！？]*(?:是一样的|和.*?一样|跟.*?一样)[^。！？]*[。！？]"),
    re.compile(r"[^。！？]*(?:比.*?更|比.*?贵|比.*?重|比.*?难|比.*?好认)[^。！？]*[。！？]"),
    re.compile(r"[^。！？]*(?:的是|的东西|的事)[^。！？]*[。！？]"),
    re.compile(r"[^。！？]*(?:算得出.*?算不出|能.*?不能|会.*?不会)[^。！？]*[。！？]"),
    re.compile(r"[^。！？]*(?:不是.*?是|不叫.*?叫|没有.*?只有)[^。！？]*[。！？]"),
]

ABSTRACT_CONCEPTS = {"命", "意义", "代价", "规则", "选择", "重量", "重要",
                     "沉默", "疼", "贵", "难", "沉", "苦", "值", "算",
                     "麻烦", "消息", "好认", "认", "守"}
PHYSICAL_PROPERTIES = {"重", "热", "冷", "响", "亮", "暗", "大", "小",
                       "快", "慢", "多", "少", "远", "近", "粗", "细",
                       "碎", "哑", "干", "湿", "硬", "软", "糙", "滑",
                       "暖", "寒", "烫", "凉", "深", "浅"}
TEMPORAL_REFERENCES = ["昨天", "刚才", "以前", "之前", "上次", "前天", "现在",
                       "今天", "明天", "半分", "半寸", "一点"]

# --- v6.0 新增：情绪直说检测 ---

EMOTION_DIRECT_PATTERNS = [
    re.compile(r"(?:他|她|程铖|老周|沈缺|苏眠|赵三)(?:感到|觉得|知道|明白|察觉|意识到)(?:恐惧|害怕|不安|愤怒|悲伤|孤独|疲惫|绝望|紧张|焦虑|无奈|心慌|心悸)"),
    re.compile(r"(?:恐惧|害怕|不安|愤怒|悲伤|孤独|疲惫|绝望|紧张|焦虑|无奈)(?:涌上|袭来|爬上|漫过|压在|堵在|涌进)(?:心头|全身|胸口|心口|喉间|胸口|四肢)"),
    re.compile(r"心里(?:涌起|升起|泛起)(?:一阵|一股)?(?:恐惧|害怕|不安|愤怒|悲伤|孤独|疲惫|绝望|紧张|焦虑|无奈)"),
    re.compile(r"(?:一种|一股)(?:恐惧|害怕|不安|愤怒|悲伤|孤独|疲惫|绝望|紧张|焦虑|无奈)(?:袭来|涌上|升起)"),
]

# --- v6.0 新增：总结/评论句检测 ---

NARRATOR_SUMMARY_PATTERNS = [
    re.compile(r"就这样[，,。]"),
    re.compile(r"这便是"),
    re.compile(r"没有人知道"),
    re.compile(r"谁也不知道"),
    re.compile(r"谁也不曾"),
    re.compile(r"后来的事"),
    re.compile(r"很多年以后"),
    re.compile(r"这是他第[一二三四五六七八九十两]+次"),
    re.compile(r"事实上[，,]"),
    re.compile(r"说到底[，,]"),
    re.compile(r"总而言之"),
    re.compile(r"不管怎样"),
    re.compile(r"无论如何"),
    re.compile(r"这就是.*?的(?:命|代价|规则|选择|意义)"),
    re.compile(r"也许.*?就是.*?的命"),
]

# --- 世界自转（保留统计，不加分）---

WORLD_ENTITIES = ["风", "雨", "雪", "光", "暗", "云", "虫", "苔", "鸟", "鼠", "蚁",
                  "雾", "霜", "露", "月", "日", "星", "天", "地", "锁链"]
WORLD_ACTIONS = ["灌", "吹", "爬", "飞", "啃", "蠕动", "飘", "扫", "渗",
                 "亮", "灭", "变", "落", "升", "沉", "涌", "磕"]
CHARACTER_ACTIONS = ["看", "望", "盯", "听", "闻", "摸", "碰", "握", "攥",
                     "站", "蹲", "走", "转", "停", "抖", "翻", "磨", "跳",
                     "数", "想", "说", "问", "答", "笑", "靠", "坐", "碰"]


def _is_genuine_punchline(sentence: str) -> bool:
    """v5.0 金句语义过滤器（保留）"""
    if any(c in sentence for c in ABSTRACT_CONCEPTS):
        return True
    for ref in TEMPORAL_REFERENCES:
        if ref in sentence:
            return False
    if re.search(r"(?:和|跟|同).{1,10}?(?:一样|同样)", sentence):
        match = re.search(r"(?:一样|同样)(.{1,2})", sentence)
        if match and match.group(1) and match.group(1)[0] in PHYSICAL_PROPERTIES:
            return False
    if re.search(r"的话(?:和|的|是|，)", sentence):
        return False
    match = re.search(r"只有(.{1,4})", sentence)
    if match:
        concrete = ["疤", "墙", "风", "光", "暗", "石", "灰", "尘", "道",
                    "条", "痕", "影", "声", "桌", "床"]
        if any(n in match.group(1) for n in concrete):
            return False
    if re.search(r"的是(?:壳|暗|亮|光|色|空)", sentence):
        return False
    return True


def detect_narrator_translation(paragraphs: List[str]) -> List[Issue]:
    """动作后解释检测（保留 D2）"""
    issues = []
    for idx, para in enumerate(paragraphs):
        sentences = split_sentences(para)
        for si, sent in enumerate(sentences):
            if si == 0 or len(sent) < 5:
                continue
            is_explanation = any(m in sent for m in EXPLANATION_MARKERS)
            if not is_explanation:
                continue
            prev_sent = sentences[si - 1]
            action_words = ["手", "脸", "眼", "脚", "刀", "铜钱", "站", "蹲",
                            "走", "转", "握", "攥", "停", "抖", "翻", "磨", "跳", "碰"]
            if any(w in prev_sent for w in action_words):
                combined = (prev_sent + " → " + sent)[:80]
                issues.append(Issue(
                    severity="warning",
                    location=f"第{idx+1}段, 第{si+1}句",
                    excerpt=combined,
                    diagnosis="角色动作后紧跟叙述者解释，行为不自足",
                    suggestion="删掉解释句，看动作自己能否传达含义。如不能，补行为而非补解释"
                ))
    return issues


def detect_punchline_fixed(para: str) -> Tuple[bool, str]:
    """v5.0 金句检测（保留，v6.0降权为参考项）"""
    cc = count_chars(para)
    has_dialogue = is_dialogue(para)

    if cc > 50:
        sentences = re.findall(r"[^。！？\n]*[。！？]", para)
        for sent in sentences:
            sent_stripped = sent.strip()
            if len(sent_stripped) < 5:
                continue
            for pattern in PUNCHLINE_PATTERNS:
                if pattern.search(sent):
                    if sent_stripped.count('"') >= 2 or sent_stripped.count('"') >= 2:
                        continue
                    if not _is_genuine_punchline(sent):
                        continue
                    return True, sent_stripped[:60]
        return False, ""

    if has_dialogue:
        return False, ""

    conditions = 0
    if re.search(r"(?:不是.*?是|没有.*?只有|不.*?倒是)", para):
        conditions += 1
    if re.search(r"(?:比.*?更|算得出.*?算不出|能.*?不能)", para):
        conditions += 1
    if any(w in para for w in ["规则", "代价", "选择", "意义", "重量", "重要"]):
        conditions += 1
    if cc <= 15:
        conditions += 1

    if conditions >= 2:
        if not _is_genuine_punchline(para):
            return False, ""
        return True, para.strip()[:60]
    return False, ""


def detect_emotion_direct(paragraphs: List[str]) -> List[Issue]:
    """v6.0 新增：情绪直说检测

    检测叙述者直接告知角色情绪，而非通过行为展示。
    "他感到恐惧" → 应改为"手指攥紧，呼吸变浅"
    """
    issues = []
    for idx, para in enumerate(paragraphs):
        for pattern in EMOTION_DIRECT_PATTERNS:
            match = pattern.search(para)
            if match:
                matched_text = match.group()
                # 排除对话中的情绪表达
                if matched_text.count('"') >= 2 or matched_text.count('"') >= 2:
                    continue
                issues.append(Issue(
                    severity="warning",
                    location=f"第{idx+1}段",
                    excerpt=matched_text[:60],
                    diagnosis="情绪直说——叙述者贴标签而非通过行为展示",
                    suggestion="把'他感到恐惧'改成行为：手指攥紧、呼吸变浅、后背靠上墙"
                ))
    return issues


def detect_summary_comment(paragraphs: List[str]) -> List[Issue]:
    """v6.0 新增：总结/评论句检测

    检测叙述者跳出场景做总结、评论或全知交代。
    "就这样，一天过去了" → 叙述者收束
    "没有人知道他去了哪里" → 全知视角插入
    """
    issues = []
    for idx, para in enumerate(paragraphs):
        for pattern in NARRATOR_SUMMARY_PATTERNS:
            match = pattern.search(para)
            if match:
                matched_text = match.group()
                # 排除对话
                if matched_text.count('"') >= 2 or matched_text.count('"') >= 2:
                    continue
                issues.append(Issue(
                    severity="warning",
                    location=f"第{idx+1}段",
                    excerpt=matched_text[:60],
                    diagnosis="叙述者介入——总结/评论/全知交代，跳出场景视角",
                    suggestion="删掉总结句，让场景自己结束；或用角色视角替代全知视角"
                ))
    return issues


def detect_world_rotation(paragraphs: List[str]) -> int:
    """世界自转统计（保留v5.0主体性检测，v6.0只做统计不加分）"""
    rotation_count = 0
    for para in paragraphs:
        world_action_count = 0
        for entity in WORLD_ENTITIES:
            if entity in para:
                for action in WORLD_ACTIONS:
                    if action in para:
                        world_action_count += 1
                        break
        char_action_count = sum(1 for a in CHARACTER_ACTIONS if a in para)
        if world_action_count > 0 and world_action_count >= char_action_count:
            rotation_count += 1
    return rotation_count


def detect_t2(paragraphs: List[str], total_chars: int) -> DimReport:
    """v6.0 T2: 叙述者介入度——扩展检测维度"""
    issues = []

    # 1. 动作后翻译
    translation_issues = detect_narrator_translation(paragraphs)
    issues.extend(translation_issues)

    # 2. 情绪直说（v6.0新增）
    emotion_issues = detect_emotion_direct(paragraphs)
    issues.extend(emotion_issues)

    # 3. 总结/评论句（v6.0新增）
    summary_issues = detect_summary_comment(paragraphs)
    issues.extend(summary_issues)

    # 4. 金句密度（保留v5.0语义过滤，降权为参考项）
    punchline_count = 0
    punchline_texts = []
    for idx, para in enumerate(paragraphs):
        is_punch, text = detect_punchline_fixed(para)
        if is_punch:
            punchline_count += 1
            punchline_texts.append({"para": idx + 1, "text": text})

    punchline_density = punchline_count / max(total_chars / 1000, 1)

    if punchline_density > 3:
        for p in punchline_texts:
            issues.append(Issue(
                severity="info",
                location=f"第{p['para']}段",
                excerpt=p["text"],
                diagnosis=f"金句收尾（密度{punchline_density:.1f}/千字）——参考项",
                suggestion="减少哲理收尾句，让场景自己说话"
            ))

    # 5. 世界自转（只统计，不加分）
    rotation_count = detect_world_rotation(paragraphs)

    # v6.0 评分：纯扣分，无加分
    score = 100
    score -= len(translation_issues) * 10
    score -= len(emotion_issues) * 8
    score -= len(summary_issues) * 8
    if punchline_density > 4:
        score -= (punchline_density - 4) * 10
    elif punchline_density > 3:
        score -= (punchline_density - 3) * 5
    score = max(0, min(100, score))

    return DimReport(
        dim="T2",
        dim_name="叙述者介入度",
        score=score,
        grade=grade_score(score),
        stats={
            "translation_count": len(translation_issues),
            "emotion_direct_count": len(emotion_issues),
            "summary_comment_count": len(summary_issues),
            "punchline_count": punchline_count,
            "punchline_density": round(punchline_density, 2),
            "world_rotation_count": rotation_count,
        },
        issues=issues[:20],
    )


# ============================================================
# T3: 意象多样性（v6.0 重构版）
# ============================================================

# 感知通道定义（保留）
PERCEPTION_CHANNELS = {
    "视觉": {
        "keywords": ["光", "亮", "暗", "紫", "色", "看", "望", "盯", "瞧",
                      "影", "闪", "亮起", "发紫", "暗色", "纹路", "一收一放", "发亮"],
    },
    "听觉": {
        "keywords": ["声", "响", "磨", "碎", "哑", "咯吱", "听", "嗡",
                      "嘶", "劈", "碰", "刮", "嗡嗡", "磕", "又碎又哑"],
    },
    "嗅觉": {
        "keywords": ["味", "碱", "焦", "臭", "腥", "香", "闻", "气",
                      "烟", "炊烟", "泔水", "铁锈", "干涩", "干热"],
    },
    "触觉": {
        "keywords": ["烫", "凉", "冷", "热", "暖", "寒", "摸", "碰",
                      "握", "攥", "捏", "糙", "滑", "涩", "硬", "软",
                      "硌", "疼", "发紧"],
    },
    "效应": {
        "keywords": ["风", "灌", "吹", "渗", "爬", "蠕动", "收", "放",
                      "变", "裂", "合", "关", "开", "呼吸"],
    },
}

# 感官类别（保留 D4）
SENSORY_CATEGORIES = {
    "气味": ["味", "气", "臭", "腥", "香", "碱", "焦", "烧", "铁锈"],
    "温度": ["烫", "凉", "冷", "热", "冰", "暖", "寒", "干热", "湿"],
    "声音": ["声", "响", "磨", "嗡", "嘶", "咯吱", "碎", "哑", "劈"],
    "触感": ["糙", "滑", "涩", "硬", "软", "硌", "粗", "细"],
}

# 功能字符集（保留 v5.0）
FUNCTIONAL_CHARS = set(
    "的了是也在都有就还不没又才把被让叫想知给到过为"
    "他她我你它这那其之"
    "和与或但而则便即"
    "说看听走来去站立蹲"
    "上下里外中前后"
    "着起出进"
    "个只条道枚件步次"
    "一二三四五六七八九十"
    "已将"
)
STOP_WORDS = {
    "什么", "怎么", "这个", "那个", "自己", "他们", "我们",
    "知道", "没有", "不是", "不会", "不能",
}
VERB_SUFFIXES = ["着", "过", "起", "出", "进", "来", "去"]
PARTICLE_ENDINGS = ["的", "了", "是", "在", "也", "都", "就", "还", "又",
                    "才", "不", "没", "有", "和", "与", "但", "而", "则"]

# --- v6.0 新增：意象词筛选层 ---

# 非意象词排除集
NON_IMAGERY_NAMES = {"程铖", "老周", "沈缺", "沈老头", "苏眠", "赵三", "程母", "沈老", "老头"}
NON_IMAGERY_SCENE = {"城墙", "街道", "垛口", "雉堞", "营房", "门框"}
NON_IMAGERY_TERMS = {"大徵", "征诏令", "征调者", "功勋", "界门", "壳", "半壳", "位面",
                     "征调", "征诏", "第七营", "第六营", "灵矢"}
NON_IMAGERY_ADDRESS = {"师父", "老头", "将军", "大人", "先生"}

# 身体部位字（含这些字的词不是意象）
BODY_CHARS = set("手眼脚肩背指掌拳腕臂脸眉唇牙额头喉腰膝腿心")

# 常见姓氏（以这些字开头的2字词可能是人名）
SURNAMES = set("程周沈苏赵王李张刘陈杨黄吴徐孙胡朱高林何郭马罗")

# 已知意象词白名单（具象可感知名词）
IMAGERY_WHITELIST = {
    "风", "光", "暗", "暗光", "暗色", "裂缝", "口子", "铜钱", "纹路",
    "烟", "雾", "霜", "露", "雨", "雪", "云", "月", "星",
    "血", "灰", "尘", "锈", "苔", "虫", "鼠",
    "锁链", "刀", "箭", "火", "水", "石", "石头",
    "暗紫色", "紫光",
    "声", "响", "味", "气",
    "沙", "泥", "草", "木", "铁",
}


def is_imagery_word(word: str) -> bool:
    """v6.0: 判断一个高频词是否是意象词

    v5.0 问题：滑动窗口提取所有高频2字组合，人名"程铖"39次被判"感知单一"。
    v6.0 修复：多层过滤排除非意象词。

    排除规则：
    1. 已知人名/场景词/术语/称谓 → 排除
    2. 含身体部位字 → 排除
    3. 姓氏开头 → 可能是人名，排除
    4. 在白名单中 → 确定是意象词
    5. 其他 → 不进入意象分析（保守策略，宁可不报不可误报）
    """
    # 1. 已知非意象词
    if word in NON_IMAGERY_NAMES:
        return False
    if word in NON_IMAGERY_SCENE:
        return False
    if word in NON_IMAGERY_TERMS:
        return False
    if word in NON_IMAGERY_ADDRESS:
        return False

    # 2. 含身体部位字
    if any(c in BODY_CHARS for c in word):
        return False

    # 3. 姓氏开头（可能是人名）
    if word[0] in SURNAMES:
        return False

    # 4. 白名单
    if word in IMAGERY_WHITELIST:
        return True

    # 5. 保守策略：不在白名单中的词不进入意象分析
    return False


def discover_noun_groups(text: str, min_freq: int = 4) -> List[dict]:
    """高频名词自发现管道 v5.0（滑动窗口版，保留）"""
    segments = re.split(r"[^\u4e00-\u9fff]+", text)
    candidates = []
    for seg in segments:
        if len(seg) < 2:
            continue
        for i in range(len(seg) - 1):
            candidates.append(seg[i:i+2])

    filtered = [w for w in candidates
                if w not in STOP_WORDS
                and not any(w.endswith(suf) for suf in VERB_SUFFIXES)
                and not any(w.endswith(pe) for pe in PARTICLE_ENDINGS)
                and not (set(w) & FUNCTIONAL_CHARS)]

    freq = Counter(filtered)
    high_freq = {w: c for w, c in freq.items() if c >= min_freq}

    # v6.0: 取消变体分组——直接返回词频列表
    sorted_words = sorted(high_freq.items(), key=lambda x: -x[1])
    return [{"core": w, "total": c} for w, c in sorted_words[:30]]


def detect_channel_for_word(word: str, full_text: str, position: int) -> str:
    """v6.0: 通道检测——意象词前后20字窗口

    v5.0 问题：整句扫描，句中其他词干扰通道判定。
    v6.0 修复：只扫描意象词前后各20字，减少干扰。
    """
    window_start = max(0, position - 20)
    window_end = min(len(full_text), position + len(word) + 20)
    context = full_text[window_start:window_end]

    channel_hits = defaultdict(int)
    for channel, config in PERCEPTION_CHANNELS.items():
        for kw in config["keywords"]:
            if kw in context:
                channel_hits[channel] += 1

    if not channel_hits:
        return "未检测"
    return max(channel_hits, key=channel_hits.get)


def check_sensory_lingering(paragraphs: List[str]) -> Tuple[int, List[Issue]]:
    """感官萦绕检测（保留 D4 v1.1）"""
    issues = []
    oneoff_count = 0
    WINDOW = 5
    RECALL_THRESHOLD = 3

    for category, keywords in SENSORY_CATEGORIES.items():
        appearances = []
        for idx, para in enumerate(paragraphs):
            for kw in keywords:
                if kw in para:
                    appearances.append((idx, kw, para[:60]))

        total_appearances = len(appearances)
        if total_appearances >= RECALL_THRESHOLD:
            continue
        if not appearances:
            continue

        first_idx = appearances[0][0]
        has_nearby_recall = False
        for j in range(1, len(appearances)):
            if appearances[j][0] <= first_idx + WINDOW:
                has_nearby_recall = True
                break

        if not has_nearby_recall and first_idx < len(paragraphs) - 2:
            oneoff_count += 1
            kw = appearances[0][1]
            ctx = appearances[0][2]
            issues.append(Issue(
                severity="info",
                location=f"第{first_idx+1}段",
                excerpt=ctx + "...",
                diagnosis=f"'{category}'类感官（关键词'{kw}'）引入后，后续{WINDOW}段内未再现——沦为信息标签",
                suggestion=f"在后续段落中让'{kw}'再回来一次，让感官萦绕不散"
            ))

    return oneoff_count, issues


def detect_t3(paragraphs: List[str], full_text: str) -> DimReport:
    """v6.0 T3: 意象多样性——重构版"""
    issues = []

    # 1. 管道：滑动窗口发现高频词
    groups = discover_noun_groups(full_text, min_freq=4)

    # 2. v6.0 新增：意象词筛选
    imagery_words = []
    filtered_out = []
    for g in groups:
        if g["total"] < 5:
            continue
        if is_imagery_word(g["core"]):
            imagery_words.append(g)
        else:
            filtered_out.append(g["core"])

    # 3. 对每个意象词做通道检测
    word_details = []
    word_scores = []

    for group in imagery_words:
        word = group["core"]

        # 找所有出现位置
        positions = []
        start = 0
        while True:
            pos = full_text.find(word, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + len(word)

        if not positions:
            continue

        # 每个位置检测通道（v6.0: 20字窗口）
        channels = []
        for pos in positions:
            ch = detect_channel_for_word(word, full_text, pos)
            channels.append(ch)

        # 通道分布
        channel_dist = defaultdict(int)
        for ch in channels:
            channel_dist[ch] += 1

        non_visual_count = sum(1 for c in channels if c not in ("视觉", "未检测"))
        coverage = non_visual_count / max(len(channels), 1)

        # 评分
        if coverage >= 0.4:
            s = 100
        elif coverage >= 0.25:
            s = 80
        elif coverage >= 0.1:
            s = 50
        else:
            s = 20

        word_scores.append(s)

        # 诊断
        if coverage < 0.25:
            severity = "warning"
            top_channel = max(channel_dist, key=channel_dist.get)
            issues.append(Issue(
                severity=severity,
                location=f"全文（{group['total']}次出现）",
                excerpt=f"'{word}'",
                diagnosis=f"'{word}'共{group['total']}次出现，{top_channel}通道占{channel_dist[top_channel]}次，"
                          f"非视觉覆盖率{coverage:.0%}——感知维度{'严重单一' if coverage < 0.1 else '单一'}",
                suggestion=f"不换词，换感知方式：第5次写风声（听觉），第9次写温度（触觉），第13次写气味（嗅觉）"
            ))

        word_details.append({
            "word": word,
            "total": group["total"],
            "channel_distribution": dict(channel_dist),
            "coverage_ratio": round(coverage, 2),
            "score": s,
        })

    # 4. 感官萦绕
    oneoff_count, lingering_issues = check_sensory_lingering(paragraphs)
    issues.extend(lingering_issues)

    # 评分
    if word_scores:
        t3_score = sum(word_scores) / len(word_scores)
    else:
        t3_score = 85  # 无意象词时给默认分（少量意象词不扣分）
    t3_score -= oneoff_count * 5
    t3_score = max(0, min(100, t3_score))

    return DimReport(
        dim="T3",
        dim_name="意象多样性",
        score=t3_score,
        grade=grade_score(t3_score),
        stats={
            "discovered_words": len(groups),
            "imagery_words": len(imagery_words),
            "filtered_out": filtered_out[:10],
            "imagery_details": word_details[:10],
            "sensory_oneoff_count": oneoff_count,
        },
        issues=issues[:20],
    )


# ============================================================
# 主诊断流程
# ============================================================

def diagnose(text: str, filepath: str = "", dims: Optional[str] = None) -> TextureReport:
    """v6.0: 对文本执行完整诊断"""
    paragraphs = split_paragraphs(text)
    total_chars = count_chars(text)
    full_text = text

    run_dims = set(("T1", "T2", "T3")) if not dims else set(dims.split(","))

    t1 = DimReport("T1", "场景具身度", 0)
    t2 = DimReport("T2", "叙述者介入度", 0)
    t3 = DimReport("T3", "意象多样性", 0)

    if "T1" in run_dims:
        t1 = detect_t1(paragraphs)
    if "T2" in run_dims:
        t2 = detect_t2(paragraphs, total_chars)
    if "T3" in run_dims:
        t3 = detect_t3(paragraphs, full_text)

    # v6.0: 维度评级
    grades = {"T1": t1.grade or "D", "T2": t2.grade or "D", "T3": t3.grade or "D"}
    worst_grade = min(grades.values(), key=lambda g: GRADE_ORDER.get(g, 0))

    # 参考分（非主要指标）
    overall = t1.score * 0.35 + t2.score * 0.35 + t3.score * 0.30
    overall = max(0, min(100, overall))

    # 摘要
    parts = []
    if t1.stats.get("info_dump", 0) > 0:
        parts.append(f"信息交付段{t1.stats['info_dump']}处")
    if t1.stats.get("focal_level", "").startswith("概念") or t1.stats.get("focal_level", "").startswith("人物"):
        parts.append(f"焦距{t1.stats.get('focal_level', '')}")
    if t2.stats.get("translation_count", 0) > 0:
        parts.append(f"叙述者翻译{t2.stats['translation_count']}处")
    if t2.stats.get("emotion_direct_count", 0) > 0:
        parts.append(f"情绪直说{t2.stats['emotion_direct_count']}处")
    if t2.stats.get("summary_comment_count", 0) > 0:
        parts.append(f"总结评论{t2.stats['summary_comment_count']}处")
    if t3.stats.get("imagery_words", 0) > 0:
        low_cov = [g for g in t3.stats.get("imagery_details", []) if g["coverage_ratio"] < 0.25]
        if low_cov:
            parts.append(f"意象感知单一{len(low_cov)}组")
    if t3.stats.get("sensory_oneoff_count", 0) > 0:
        parts.append(f"感官一次性{t3.stats['sensory_oneoff_count']}处")

    if not parts:
        summary = f"三维检测均在合理范围（{worst_grade}级/{overall:.0f}分）"
    elif overall >= 70:
        summary = f"感知织体基本良好（{worst_grade}级/{overall:.0f}分），{', '.join(parts)}"
    elif overall >= 55:
        summary = f"感知织体中等（{worst_grade}级/{overall:.0f}分），{', '.join(parts)}，需优化"
    else:
        summary = f"感知织体不足（{worst_grade}级/{overall:.0f}分），{', '.join(parts)}，需重构写作思维"

    return TextureReport(
        file=filepath,
        total_chars=total_chars,
        total_paragraphs=len(paragraphs),
        t1=t1,
        t2=t2,
        t3=t3,
        overall_grade=worst_grade,
        overall_score=overall,
        summary=summary,
    )


# ============================================================
# 报告输出
# ============================================================

def print_report(report: TextureReport):
    """v6.0 控制台输出报告"""
    print("=" * 70)
    print(f"  感知织体诊断报告 v6.0")
    print(f"  文件: {report.file or '(stdin)'}")
    print(f"  字数: {report.total_chars} | 段落: {report.total_paragraphs}")
    print("=" * 70)

    print(f"\n  综合评级: {report.overall_grade}  (参考分: {report.overall_score:.1f})")
    print(f"  {report.summary}")
    print()

    for d in [report.t1, report.t2, report.t3]:
        bar_len = int(d.score / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        print(f"  {d.dim} {d.dim_name:<8s} {bar} {d.score:>5.1f} [{d.grade}]")

        for sk, sv in d.stats.items():
            if sk == "imagery_details":
                for g in sv[:5]:
                    ch_str = "/".join(f"{k}:{v}" for k, v in sorted(g["channel_distribution"].items(), key=lambda x: -x[1])[:3])
                    print(f"       {g['word']}({g['total']}次) 覆盖率={g['coverage_ratio']:.0%} [{ch_str}]")
            elif sk == "filtered_out":
                if sv:
                    print(f"       已过滤非意象词: {', '.join(sv[:8])}")
            elif isinstance(sv, (str, int, float)):
                print(f"       {sk}: {sv}")

        if d.issues:
            print(f"       问题 ({len(d.issues)}条):")
            for issue in d.issues[:5]:
                icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(issue.severity, "⚪")
                print(f"         {icon} [{issue.severity}] {issue.location}")
                print(f"            摘录: {issue.excerpt[:70]}")
                print(f"            诊断: {issue.diagnosis[:70]}")
                if issue.severity in ("critical", "warning"):
                    print(f"            建议: {issue.suggestion[:70]}")
            if len(d.issues) > 5:
                print(f"         ... 还有 {len(d.issues) - 5} 条")
        print()

    print("=" * 70)


def compare_reports(a: TextureReport, b: TextureReport):
    """v6.0 版本对比"""
    print()
    print("=" * 70)
    print("  版本对比")
    print("=" * 70)
    print(f"  {'维度':<14s} {'版本A':>10s} {'版本B':>10s} {'变化':>8s}")
    print(f"  {'-'*46}")
    print(f"  {'综合评级':<14s} {a.overall_grade:>10s} {b.overall_grade:>10s}")
    print(f"  {'参考分':<14s} {a.overall_score:>10.1f} {b.overall_score:>10.1f} {b.overall_score - a.overall_score:>+8.1f}")
    for da, db, name in [(a.t1, b.t1, "T1 场景具身"), (a.t2, b.t2, "T2 叙述介入"),
                          (a.t3, b.t3, "T3 意象多样")]:
        delta = db.score - da.score
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        print(f"  {name:<14s} {da.score:>7.1f}[{da.grade}] {db.score:>7.1f}[{db.grade}] {arrow}{abs(delta):>5.1f}")
    print()


# ============================================================
# CLI
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="感知织体诊断器 v6.0")
    parser.add_argument("file", help="待诊断的章节文本文件")
    parser.add_argument("--json", help="输出 JSON 报告到指定文件")
    parser.add_argument("--compare", help="对比另一版本文件")
    parser.add_argument("--dims", help="仅运行指定维度（逗号分隔，如 T1,T2）")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"错误：文件不存在 {args.file}")
        sys.exit(2)

    text = load_text(args.file)
    report = diagnose(text, args.file, dims=args.dims)
    print_report(report)

    if args.compare:
        if not os.path.exists(args.compare):
            print(f"错误：对比文件不存在 {args.compare}")
            sys.exit(2)
        text_b = load_text(args.compare)
        report_b = diagnose(text_b, args.compare, dims=args.dims)
        print_report(report_b)
        compare_reports(report, report_b)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"  JSON 报告已保存: {args.json}")


if __name__ == "__main__":
    main()
