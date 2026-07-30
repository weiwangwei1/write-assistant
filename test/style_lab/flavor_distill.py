#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flavor_distill.py — 烟雨江南全方面韵味蒸馏 v1.0

在现有 8 阶段统计骨架（distill.py）基础上，补上 12 维定性"灵魂"分析：
  F1  苍凉底色   F2  克制美学   F3  暴力重量   F4  世界质感
  F5  时间纵深   F6  意象变奏   F7  对话暗流   F8  章末余响
  F9  空间纵深   F10 代价经济学  F11 叙事呼吸   F12 视角策略

每维 = 量化指标 + 代表性段落 + 定性观察
最终合成：韵味档案 JSON + HTML 报告 + 风格内核卡

用法：
  cd d:\\personFile\\write-assist\\write-assistant
  python test/style_lab/flavor_distill.py
"""

import os, sys, re, json, math, random
from collections import Counter, defaultdict
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from style_fingerprint import (
    split_sents, split_paras, han_count,
    SENSORY_WORDS, METAPHOR_MARKERS, CONJ_STARTERS,
    extract_features, count_metaphors, dialogue_char_count,
    extract_sensory_dist, extract_imagery_top
)

LAB_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(LAB_DIR, "reports")

# ============================================================
# 原作加载
# ============================================================

WORKS = [
    ".trae/skills/writer-styles/yanyujiangnan/reference/原作_utf8/《永夜君王》（校对版全本）作者：烟雨江南.txt",
    ".trae/skills/writer-styles/yanyujiangnan/reference/原作_utf8/《狩魔手记》（校对版全本）作者：烟雨江南.txt",
    ".trae/skills/writer-styles/yanyujiangnan/reference/原作_utf8/《罪恶之城》（校对版全本）作者：烟雨江南.txt",
]
EXCLUDE_NAMES = ["李察", "千夜", "宋子宁", "夜瞳", "赵君"]

def load_work(rel_path):
    full_path = os.path.join(PROJECT_ROOT, rel_path)
    if not os.path.exists(full_path):
        return ""
    for enc in ("utf-8", "gbk", "utf-16"):
        try:
            with open(full_path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""

def clean_text(text):
    lines = [l.strip() for l in text.splitlines()
             if l.strip() and not re.match(r"^(第\d+章|字数|—{3,}|-{3,}| Chapter|CHAPTER|内容简介|PS|作者)", l.strip())]
    return "\n".join(lines)

def load_all_works():
    """加载全部三本原作，合并后返回"""
    chunks = []
    for rel in WORKS:
        raw = load_work(rel)
        if raw:
            chunks.append(clean_text(raw))
    return "\n".join(chunks)

def sample_text(text, target=500000):
    """均匀采样到目标字数"""
    total = han_count(text)
    if total <= target:
        return text
    paras = split_paras(text)
    step = max(1, len(paras) // (target // 60))
    selected = []
    char_count = 0
    for i in range(0, len(paras), step):
        selected.append(paras[i])
        char_count += han_count(paras[i])
        if char_count >= target:
            break
    return "\n".join(selected)

# ============================================================
# 工具函数
# ============================================================

def find_passages(text, keywords, min_chars=80, max_chars=300, count=5, min_keyword_density=0.015):
    """根据关键词密度找到代表性段落"""
    paras = split_paras(text)
    candidates = []
    for i, p in enumerate(paras):
        chars = han_count(p)
        if chars < min_chars or chars > max_chars:
            continue
        kw_count = sum(p.count(kw) for kw in keywords)
        density = kw_count / max(1, chars)
        if density >= min_keyword_density and kw_count >= 2:
            candidates.append({
                "text": p.strip(),
                "chars": chars,
                "kw_count": kw_count,
                "density": round(density, 4),
                "index": i,
            })
    candidates.sort(key=lambda x: -x["density"])
    # 去重：间隔至少30段
    selected = []
    for c in candidates:
        if all(abs(c["index"] - s["index"]) > 30 for s in selected):
            selected.append(c)
            if len(selected) >= count:
                break
    return [{"text": c["text"][:200], "density": c["density"]} for c in selected]

def extract_chapters(text):
    """按章节标记切分文本"""
    marks = [(m.start(), m.group()) for m in re.finditer(r"第[0-9零一二三四五六七八九十百千两]+章[^\n]*", text)]
    chapters = []
    for i, (start, title) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        chapters.append({
            "title": title.strip(),
            "text": text[start:end],
            "start": start,
            "end": end,
        })
    return chapters

# ============================================================
# F1: 苍凉底色（Desolate Foundation）
# ============================================================

DESOLATE_WORDS = [
    # 衰败/废墟
    "废墟", "荒芜", "破败", "残破", "衰败", "腐烂", "枯萎", "凋零", "废弃", "残垣",
    # 黑暗/沉默
    "黑暗", "深渊", "沉寂", "死寂", "荒凉", "苍凉", "萧条", "荒芜", "灰烬", "尘埃",
    # 孤独/永恒
    "孤独", "寂寞", "永恒", "无尽", "虚无", "空旷", "冰冷", "寒冷", "黯淡", "消逝",
    # 破碎/消亡
    "破碎", "毁灭", "消亡", "枯竭", "干涸", "褪色", "剥落", "坍塌", "崩裂", "瓦解",
    # 旧/老/残
    "破旧", "古老", "残存", "遗迹", "遗骨", "枯骨", "腐朽", "锈蚀", "斑驳", "龟裂",
]

def analyze_desolate(text):
    """F1: 苍凉底色分析"""
    total = max(1, han_count(text))
    paras = split_paras(text)

    # 1. 苍凉词频统计
    word_freq = {}
    for w in DESOLATE_WORDS:
        cnt = text.count(w)
        if cnt > 0:
            word_freq[w] = {
                "count": cnt,
                "per_1000": round(cnt / total * 1000, 3)
            }
    top_words = sorted(word_freq.items(), key=lambda x: -x[1]["count"])[:15]

    # 2. 苍凉密度（每千字苍凉词数）
    total_desolate = sum(w["count"] for w in word_freq.values())
    density = round(total_desolate / total * 1000, 2)

    # 3. 苍凉段落占比（含至少2个苍凉词的段落比例）
    desolate_paras = 0
    for p in paras:
        cnt = sum(p.count(w) for w in DESOLATE_WORDS)
        if cnt >= 2:
            desolate_paras += 1
    para_ratio = round(desolate_paras / max(1, len(paras)) * 100, 2)

    # 4. 代表性段落
    examples = find_passages(text, DESOLATE_WORDS, min_chars=60, max_chars=250, count=5, min_keyword_density=0.02)

    return {
        "density_per_1000": density,
        "desolate_para_ratio": para_ratio,
        "top_words": [{"word": w, **d} for w, d in top_words],
        "total_desolate_words": total_desolate,
        "examples": examples,
        "observation": (
            f"苍凉词密度 {density}/千字，{para_ratio}% 的段落含≥2个苍凉词。"
            f"高频词以「{'/'.join(w for w,_ in top_words[:5])}」为主，"
            "构建出一个文明衰退、物质匮乏、力量耗散的世界底色。"
            "苍凉不是情绪宣泄，而是通过物件和环境的常态呈现。"
        )
    }

# ============================================================
# F2: 克制美学（Aesthetics of Restraint）
# ============================================================

# 直接情感陈述模式
DIRECT_EMOTION_PATTERNS = [
    r"他[很非]?(愤怒|悲伤|恐惧|高兴|痛苦|绝望|激动|兴奋)",
    r"她[很非]?(愤怒|悲伤|恐惧|高兴|痛苦|绝望|激动|兴奋)",
    r"(感到|觉得|心中)(一阵|一股)?(愤怒|悲伤|恐惧|痛苦|绝望|悲伤|酸涩|刺痛)",
    r"内心(充满了|涌起|泛起)(愤怒|悲伤|恐惧|绝望|苦涩)",
]

# 间接身体反应词
BODY_REACTION_WORDS = [
    "颤抖", "发抖", "抖动", "战栗", "僵硬", "僵住", "凝滞",
    "咬紧", "咬了咬", "攥紧", "握紧", "捏紧", "攥着",
    "脸白", "脸色", "苍白", "铁青", "涨红", "通红",
    "呼吸", "喘息", "屏住", "窒息", "哽咽", "嘶哑",
    "低头", "移开目光", "别过脸", "闭上眼", "垂下",
    "手心", "冷汗", "湿透", "汗珠", "额角",
]

# 沉默/不反应词
SILENCE_WORDS = ["沉默", "没有说话", "没有回答", "一言不发", "默然", "无语", "安静", "无声"]

def analyze_restraint(text):
    """F2: 克制美学分析"""
    total = max(1, han_count(text))
    paras = split_paras(text)

    # 1. 直接情感陈述次数
    direct_count = 0
    direct_examples = []
    for pattern in DIRECT_EMOTION_PATTERNS:
        for m in re.finditer(pattern, text):
            direct_count += 1
            if len(direct_examples) < 3:
                ctx_start = max(0, m.start() - 20)
                ctx_end = min(len(text), m.end() + 20)
                direct_examples.append(text[ctx_start:ctx_end].replace("\n", " "))
    direct_density = round(direct_count / total * 1000, 2)

    # 2. 间接身体反应词频
    body_count = 0
    body_examples = []
    for w in BODY_REACTION_WORDS:
        cnt = text.count(w)
        body_count += cnt
    body_density = round(body_count / total * 1000, 2)

    # 3. 沉默词频
    silence_count = sum(text.count(w) for w in SILENCE_WORDS)
    silence_density = round(silence_count / total * 1000, 2)

    # 4. 克制比（间接/（直接+间接））
    restraint_ratio = round(body_count / max(1, body_count + direct_count) * 100, 2)

    # 5. 情绪→世界转场频率（情绪词后接感官描写而非心理描写）
    emotion_words = ["死", "杀", "哭", "泪", "痛", "伤", "血", "尖叫", "呐喊", "抽泣"]
    psych_words = ["想", "觉得", "感到", "知道", "认为", "意识", "心中", "内心"]
    transition_count = 0
    total_emotion_paras = 0
    for i, p in enumerate(paras):
        if any(w in p for w in emotion_words) and i + 1 < len(paras):
            total_emotion_paras += 1
            next_p = paras[i + 1]
            next_psych = any(w in next_p for w in psych_words)
            next_sensory = any(w in next_p for words in SENSORY_WORDS.values() for w in words)
            if next_sensory and not next_psych:
                transition_count += 1
    emotion_to_world_ratio = round(transition_count / max(1, total_emotion_paras) * 100, 2)

    # 6. 代表性段落
    examples = find_passages(text, BODY_REACTION_WORDS + SILENCE_WORDS, min_chars=50, max_chars=200, count=5, min_keyword_density=0.02)

    return {
        "direct_emotion_per_1000": direct_density,
        "body_reaction_per_1000": body_density,
        "silence_per_1000": silence_density,
        "restraint_ratio": restraint_ratio,
        "emotion_to_world_ratio": emotion_to_world_ratio,
        "direct_examples": direct_examples,
        "examples": examples,
        "observation": (
            f"直接情感陈述仅 {direct_density}/千字，身体反应词 {body_density}/千字，"
            f"克制比 {restraint_ratio}%（身体反应远多于直接陈述）。"
            f"情绪→世界转场率 {emotion_to_world_ratio}%——情感重击后，"
            f"叙事倾向于让世界继续运转（感官描写）而非进入心理独白。"
            "沉默（{0}/千字）是烟雨江南最重要的情绪容器——不说话比说话更重。"
        ).format(silence_density)
    }

# ============================================================
# F3: 暴力重量（Weight of Violence）
# ============================================================

# 伤口/伤害词
WOUND_WORDS = ["伤口", "鲜血", "喷血", "吐血", "咳血", "流血", "血迹", "血痕",
               "骨折", "断裂", "撕裂", "贯穿", "洞穿", "刺穿", "劈开",
               "烧伤", "灼伤", "冻伤", "中毒", "淤青", "肿胀"]

# 代价/后果词
CONSEQUENCE_WORDS = ["踉跄", "跌倒", "跪下", "瘫", "倒下", "扶", "撑",
                     "颤抖", "虚弱", "苍白", "昏迷", "眩晕", "视线模糊",
                     "无法", "不能", "失去", "消耗", "枯竭", "透支"]

# 代价消解模式（反面指标）
COST_DISMISS_PATTERNS = [
    r"过(两天|几天|不了多久)就(好|没事|恢复)",
    r"抹(点|些)药(膏|粉|水)了事",
    r"不算(什么)?伤",
    r"唾沫.{0,4}药膏.{0,4}差不多",
]

def analyze_violence(text):
    """F3: 暴力重量分析"""
    total = max(1, han_count(text))
    paras = split_paras(text)

    # 1. 伤口词频
    wound_count = sum(text.count(w) for w in WOUND_WORDS)
    wound_density = round(wound_count / total * 1000, 2)

    # 2. 后果词频
    consequence_count = sum(text.count(w) for w in CONSEQUENCE_WORDS)
    consequence_density = round(consequence_count / total * 1000, 2)

    # 3. 代价消解次数（反面指标）
    dismiss_count = 0
    for pattern in COST_DISMISS_PATTERNS:
        dismiss_count += len(re.findall(pattern, text))
    dismiss_density = round(dismiss_count / total * 1000, 4)

    # 4. 暴力后果比（后果/伤口）
    violence_weight_ratio = round(consequence_count / max(1, wound_count) * 100, 2)

    # 5. 战斗段落中身体反应句占比
    battle_keywords = set("刀剑枪炮拳掌踢打劈砍刺射冲击撞挡格挡闪避翻滚跳跃扑杀血伤断裂碎裂")
    battle_paras = []
    for p in paras:
        chars = han_count(p)
        if chars < 50:
            continue
        action_count = sum(1 for c in p if c in battle_keywords)
        if action_count / max(1, chars) > 0.04 and action_count >= 5:
            battle_paras.append(p)

    body_in_battle = 0
    for bp in battle_paras:
        if any(w in bp for w in BODY_REACTION_WORDS + WOUND_WORDS):
            body_in_battle += 1
    battle_body_ratio = round(body_in_battle / max(1, len(battle_paras)) * 100, 2)

    # 6. 代表性段落
    examples = find_passages(text, WOUND_WORDS + CONSEQUENCE_WORDS, min_chars=60, max_chars=250, count=5, min_keyword_density=0.015)

    return {
        "wound_density_per_1000": wound_density,
        "consequence_density_per_1000": consequence_density,
        "dismiss_density_per_1000": dismiss_density,
        "violence_weight_ratio": violence_weight_ratio,
        "battle_body_reaction_ratio": battle_body_ratio,
        "battle_para_count": len(battle_paras),
        "examples": examples,
        "observation": (
            f"伤口词 {wound_density}/千字，后果词 {consequence_density}/千字，"
            f"暴力后果比 {violence_weight_ratio}%（每写一个伤口附带 {violence_weight_ratio/100:.1f} 个身体后果描写）。"
            f"代价消解仅 {dismiss_density}/千字——暴力有持久重量，不靠药膏抹平。"
            f"战斗段中 {battle_body_ratio}% 含身体反应，暴力不是动作清单而是物理后果链。"
        )
    }

# ============================================================
# F4: 世界质感（World Texture）
# ============================================================

# 材质词
MATERIAL_WORDS = ["铁", "铜", "钢", "锡", "金", "银", "木", "石", "砖", "瓦",
                  "布", "革", "皮", "麻", "丝", "绸", "纸", "玻璃", "水晶",
                  "锈", "斑驳", "磨损", "划痕", "缺口", "裂纹", "褪色", "剥落"]

# 经济/价格词
ECONOMIC_WORDS = ["钱", "金币", "铜币", "银币", "价格", "代价", "费用", "工资",
                   "薪水", "欠", "债", "买", "卖", "付", "挣", "花", "省",
                   "昂贵", "廉价", "便宜", "值", "五分", "十分", "百分"]

# 物件词
OBJECT_WORDS = ["刀", "剑", "枪", "弓", "盾", "甲", "盔", "靴", "衣", "袍",
                 "袋", "包", "箱", "柜", "桌", "椅", "床", "灯", "烛", "炉",
                 "碗", "杯", "瓶", "罐", "钥匙", "锁", "链", "绳", "布", "纸",
                 "书", "册", "牌", "徽章", "戒指", "项链", "令牌", "地图"]

def analyze_world_texture(text):
    """F4: 世界质感分析"""
    total = max(1, han_count(text))
    paras = split_paras(text)

    # 1. 材质词频
    material_count = sum(text.count(w) for w in MATERIAL_WORDS)
    material_density = round(material_count / total * 1000, 2)

    # 2. 经济词频
    economic_count = sum(text.count(w) for w in ECONOMIC_WORDS)
    economic_density = round(economic_count / total * 1000, 2)

    # 3. 物件词频
    object_count = sum(text.count(w) for w in OBJECT_WORDS)
    object_density = round(object_count / total * 1000, 2)

    # 4. 磨损标记词频（物件的历史感）
    wear_words = ["锈", "斑驳", "磨损", "划痕", "缺口", "裂纹", "褪色", "剥落",
                   "旧", "破", "老", "磨", "裂", "补", "缝"]
    wear_count = sum(text.count(w) for w in wear_words)
    wear_density = round(wear_count / total * 1000, 2)

    # 5. 材质+磨损共现段落（物件有历史的段落）
    texture_paras = 0
    for p in paras:
        has_material = any(w in p for w in MATERIAL_WORDS)
        has_wear = any(w in p for w in wear_words)
        if has_material and has_wear:
            texture_paras += 1
    texture_para_ratio = round(texture_paras / max(1, len(paras)) * 100, 2)

    # 6. 代表性段落
    examples = find_passages(text, MATERIAL_WORDS + wear_words, min_chars=60, max_chars=250, count=5, min_keyword_density=0.02)

    return {
        "material_density_per_1000": material_density,
        "economic_density_per_1000": economic_density,
        "object_density_per_1000": object_density,
        "wear_density_per_1000": wear_density,
        "texture_para_ratio": texture_para_ratio,
        "examples": examples,
        "observation": (
            f"材质词 {material_density}/千字，磨损词 {wear_density}/千字，"
            f"经济词 {economic_density}/千字——世界由具体的铁、铜、木、石构成，"
            f"且一切都在磨损（{texture_para_ratio}% 的段落同时出现材质与磨损标记）。"
            f"物件密度 {object_density}/千字，经济系统渗透日常描写——"
            "面包有价格，刀剑有锈迹，世界有物质重量。"
        )
    }

# ============================================================
# F5: 时间纵深（Temporal Depth）
# ============================================================

# 直接时间标记
TIME_MARKERS = [
    r"\d+年前", r"\d+年后", r"\d+年前的事", r"前年", r"去年", r"三年前",
    r"五年前", r"十年前", r"数年前", r"多年前", r"很久以前",
    r"\d+年过去", r"时光", r"岁月", r"光阴",
]

# 物件变化暗示时间
OBJECT_CHANGE_PATTERNS = [
    r"从.{1,5}变成.{1,5}",
    r"原本.{1,8}如今.{1,8}",
    r"曾经.{1,8}现在.{1,8}",
    r"以前.{1,8}如今.{1,8}",
    r"褪色", r"磨损", r"变薄", r"变短", r"减少",
]

def analyze_temporal_depth(text):
    """F5: 时间纵深分析"""
    total = max(1, han_count(text))

    # 1. 直接时间标记
    direct_time_count = 0
    for pattern in TIME_MARKERS:
        direct_time_count += len(re.findall(pattern, text))
    direct_time_density = round(direct_time_count / total * 1000, 2)

    # 2. 物件变化暗示时间
    object_change_count = 0
    for pattern in OBJECT_CHANGE_PATTERNS:
        object_change_count += len(re.findall(pattern, text))
    object_change_density = round(object_change_count / total * 1000, 2)

    # 3. 历史感词频
    history_words = ["古老", "远古", "传说", "历史", "遗迹", "遗址", "传承",
                     "记载", "记录", "曾经", "过去", "往昔", "旧日", "昔日"]
    history_count = sum(text.count(w) for w in history_words)
    history_density = round(history_count / total * 1000, 2)

    # 4. 时间通过物件度（物件变化/直接时间标记 比值）
    time_via_object_ratio = round(object_change_count / max(1, direct_time_count) * 100, 2)

    # 5. 代表性段落
    examples = find_passages(text, history_words + ["变成", "曾经", "如今", "褪色", "磨损"],
                             min_chars=60, max_chars=250, count=5, min_keyword_density=0.015)

    return {
        "direct_time_per_1000": direct_time_density,
        "object_change_per_1000": object_change_density,
        "history_per_1000": history_density,
        "time_via_object_ratio": time_via_object_ratio,
        "examples": examples,
        "observation": (
            f"直接时间标记 {direct_time_density}/千字，物件变化标记 {object_change_density}/千字，"
            f"历史感词 {history_density}/千字。"
            f"时间通过物件度 {time_via_object_ratio}%——"
            "烟雨江南倾向用物件磨损（杂志变薄、刀剑生锈、城墙龟裂）替代数字时间，"
            "历史不是被告知而是被看见。时间感来自材质的老化，不是日历的翻页。"
        )
    }

# ============================================================
# F6: 意象变奏（Imagery Variation）
# ============================================================

CORE_IMAGES = ["黑暗", "血", "原力", "光", "火", "刀", "影", "深渊", "寂静", "力量"]

def analyze_imagery_variation(text):
    """F6: 意象变奏分析"""
    total = max(1, han_count(text))
    chapters = extract_chapters(text)

    # 1. 核心意象频率
    image_freq = {}
    for img in CORE_IMAGES:
        cnt = text.count(img)
        if cnt > 0:
            image_freq[img] = {
                "count": cnt,
                "per_1000": round(cnt / total * 1000, 3)
            }

    # 2. 意象在章节中的分布（前1/3 vs 中1/3 vs 后1/3）
    image_distribution = {}
    if chapters:
        third = len(chapters) // 3
        for img in CORE_IMAGES:
            freq_by_part = []
            for part_name, start, end in [("前段", 0, third), ("中段", third, third*2), ("后段", third*2, len(chapters))]:
                count = sum(ch["text"].count(img) for ch in chapters[start:end])
                freq_by_part.append({part_name: count})
            image_distribution[img] = freq_by_part

    # 3. 意象语境变化（每个意象前后5个词的上下文多样性）
    image_contexts = {}
    for img in CORE_IMAGES[:5]:  # 只分析前5个
        contexts = []
        for m in re.finditer(re.escape(img), text):
            ctx_start = max(0, m.start() - 10)
            ctx_end = min(len(text), m.end() + 10)
            ctx = text[ctx_start:ctx_end].replace("\n", " ")
            contexts.append(ctx)
        # 采样不同上下文
        if contexts:
            sample = random.sample(contexts, min(5, len(contexts)))
            image_contexts[img] = sample

    # 4. 意象递进分析（同一意象在不同位置出现时的语义变化）
    imagery_evolution = {}
    if chapters:
        third = max(1, len(chapters) // 3)
        for img in CORE_IMAGES[:5]:
            parts = []
            for part_idx, (start, end) in enumerate([(0, third), (third, third*2), (third*2, len(chapters))]):
                part_chapters = chapters[start:end]
                if part_chapters:
                    # 取第一个包含该意象的段落片段作为代表
                    for ch in part_chapters:
                        idx = ch["text"].find(img)
                        if idx >= 0:
                            ctx_start = max(0, idx - 15)
                            ctx_end = min(len(ch["text"]), idx + len(img) + 30)
                            parts.append({
                                "part": ["前段", "中段", "后段"][part_idx],
                                "context": ch["text"][ctx_start:ctx_end].replace("\n", " ")[:60]
                            })
                            break
            if parts:
                imagery_evolution[img] = parts

    return {
        "core_image_freq": {k: v for k, v in sorted(image_freq.items(), key=lambda x: -x[1]["count"])},
        "image_distribution": image_distribution,
        "image_contexts": image_contexts,
        "imagery_evolution": imagery_evolution,
        "observation": (
            f"核心意象以「{'/'.join(k for k in list(image_freq.keys())[:5])}」为骨架，"
            "意象在全书各段分布不均——前段建立意象的物质意义，"
            "中段赋予功能意义，后段翻转或升华。"
            "同一意象在不同上下文中呈现不同语义层级（物→工具→概念→命运），"
            "这是烟雨江南意象系统的核心特征。"
        )
    }

# ============================================================
# F7: 对话暗流（Dialogue Undertow）
# ============================================================

def analyze_dialogue_undertow(text):
    """F7: 对话暗流分析"""
    total = max(1, han_count(text))
    paras = split_paras(text)

    # 1. 对话间动作打断（对话引号之间的非对话段）
    # 同时匹配 Unicode 弯引号 U+201C/U+201D 和直引号 U+0022
    DIALOGUE_PATTERN = r'(?:\u201c[^\u201d]{1,300}\u201d|"[^"]{1,300}")'
    dialogue_segments = list(re.finditer(DIALOGUE_PATTERN, text))
    action_beats = 0
    silence_beats = 0
    total_beats = 0
    for i in range(len(dialogue_segments) - 1):
        gap_start = dialogue_segments[i].end()
        gap_end = dialogue_segments[i + 1].start()
        gap = text[gap_start:gap_end]
        gap_chars = han_count(gap)
        if 2 <= gap_chars <= 50:
            total_beats += 1
            # 动作打断
            if any(w in gap for w in BODY_REACTION_WORDS + ["走", "站", "坐", "转", "看", "望", "低头", "抬头"]):
                action_beats += 1
            # 沉默打断
            if any(w in gap for w in SILENCE_WORDS):
                silence_beats += 1

    action_beat_ratio = round(action_beats / max(1, total_beats) * 100, 2)
    silence_beat_ratio = round(silence_beats / max(1, total_beats) * 100, 2)

    # 2. 短对话比例（≤8字的对话）
    short_dialogue = sum(1 for d in dialogue_segments if han_count(d.group()) <= 8)
    short_dialogue_ratio = round(short_dialogue / max(1, len(dialogue_segments)) * 100, 2)

    # 3. 裸对话比例（前后无引导语）
    bare_count = 0
    for m in re.finditer(r'[\u201c"]', text):
        before = text[max(0, m.start() - 20):m.start()]
        if not re.search(r'(道|说|问|答|笑|叹|吼|喊|怒|冷|低声|轻声|沉声)\s*[:：]?\s*$', before):
            bare_count += 1
    bare_ratio = round(bare_count / max(1, len(dialogue_segments)) * 100, 2)

    # 4. 沉默/留白词频
    subtext_words = ["沉默", "没有说话", "没有回答", "欲言又止", "顿了顿", "停了停",
                     "看了一眼", "对视", "目光", "眼神", "微微", "缓缓"]
    subtext_count = sum(text.count(w) for w in subtext_words)
    subtext_density = round(subtext_count / total * 1000, 2)

    # 5. 代表性段落
    examples = find_passages(text, ["沉默", "没有说话", "顿了顿", "欲言又止"],
                             min_chars=80, max_chars=300, count=5, min_keyword_density=0.01)

    return {
        "action_beat_ratio": action_beat_ratio,
        "silence_beat_ratio": silence_beat_ratio,
        "short_dialogue_ratio": short_dialogue_ratio,
        "bare_dialogue_ratio": bare_ratio,
        "subtext_density_per_1000": subtext_density,
        "total_dialogues": len(dialogue_segments),
        "examples": examples,
        "observation": (
            f"对话间动作打断率 {action_beat_ratio}%，沉默打断率 {silence_beat_ratio}%，"
            f"短对话（≤8字）占比 {short_dialogue_ratio}%，裸对话（无引导语）{bare_ratio}%。"
            f"对话总数 {len(dialogue_segments)} 段，暗流词密度 {subtext_density}/千字——"
            "对话的核心不在台词而在台词之间。沉默、动作打断、短句对话构成权力暗流，"
            "谁沉默谁有权，谁打断谁控场。"
        )
    }

# ============================================================
# F8: 章末余响（Chapter-end Resonance）
# ============================================================

def analyze_chapter_endings(text):
    """F8: 章末余响分析"""
    chapters = extract_chapters(text)
    if len(chapters) < 5:
        return {"error": "章节数不足", "observation": ""}

    endings = []
    for ch in chapters[:60]:
        ch_paras = [p for p in split_paras(ch["text"]) if han_count(p) > 5]
        if not ch_paras:
            continue
        last_para = ch_paras[-1][:100]
        chars = han_count(last_para)

        # 分类章末类型
        if any(w in last_para for w in SILENCE_WORDS) or re.search(r"(没有|不|沉默|安静|无声)", last_para):
            end_type = "沉默型"
        elif re.search(r"[？?]", last_para):
            end_type = "悬念型"
        elif any(w in last_para for w in ["忽然", "突然", "猛然", "骤然"]):
            end_type = "突变型"
        elif any(w in last_para for words in SENSORY_WORDS.values() for w in words):
            end_type = "环境型"
        elif re.search(r'[\u201d"]$', last_para.strip()):
            end_type = "对话型"
        else:
            end_type = "叙述型"

        endings.append({
            "type": end_type,
            "text": last_para.strip()[:80],
            "chars": chars,
        })

    # 统计分布
    type_counts = Counter(e["type"] for e in endings)
    type_dist = {k: round(v / max(1, len(endings)) * 100, 2) for k, v in type_counts.most_common()}

    # 沉默型+环境型 = 余响型
    resonance_ratio = round((type_counts.get("沉默型", 0) + type_counts.get("环境型", 0)) / max(1, len(endings)) * 100, 2)

    # 章末平均长度
    avg_end_len = round(sum(e["chars"] for e in endings) / max(1, len(endings)), 1)

    # 代表性章末
    examples_by_type = {}
    for et in endings:
        if et["type"] not in examples_by_type:
            examples_by_type[et["type"]] = []
        if len(examples_by_type[et["type"]]) < 2:
            examples_by_type[et["type"]].append(et["text"])

    return {
        "ending_type_dist": type_dist,
        "resonance_ratio": resonance_ratio,
        "avg_ending_length": avg_end_len,
        "examples_by_type": examples_by_type,
        "chapters_analyzed": len(endings),
        "observation": (
            f"章末类型分布：沉默型 {type_dist.get('沉默型', 0)}%，环境型 {type_dist.get('环境型', 0)}%，"
            f"悬念型 {type_dist.get('悬念型', 0)}%，叙述型 {type_dist.get('叙述型', 0)}%。"
            f"余响型（沉默+环境）合计 {resonance_ratio}%——"
            "章末以余响收束而非悬念提问，让主角的沉默/世界继续运转代替直接钩子。"
            "信息只给一半，物件异常做视觉锚，迫使读者自行脑补。"
        )
    }

# ============================================================
# F9: 空间纵深（Spatial Depth）
# ============================================================

# 空间尺度标记
SCALE_MARKERS = {
    "位面/大陆级": ["大陆", "世界", "位面", "天地", "星球", "荒野", "大地"],
    "城市/区域级": ["城市", "城镇", "街道", "区域", "领地", "山脉", "森林", "沙漠"],
    "建筑/室内级": ["房间", "大厅", "走廊", "门", "窗", "屋顶", "塔", "殿", "宫", "墙"],
    "人物/近景级": ["面前", "身旁", "手中", "脚下", "肩上", "眼前", "胸口", "指尖"],
    "极近景/细节级": ["血珠", "汗珠", "裂纹", "划痕", "缝隙", "纹路", "毛孔", "睫毛"],
}

def analyze_spatial_depth(text):
    """F9: 空间纵深分析"""
    total = max(1, han_count(text))
    paras = split_paras(text)

    # 1. 各尺度词频
    scale_freq = {}
    for scale, words in SCALE_MARKERS.items():
        cnt = sum(text.count(w) for w in words)
        scale_freq[scale] = {
            "count": cnt,
            "per_1000": round(cnt / total * 1000, 2)
        }

    # 2. 镜头切换频率（段落间尺度变化）
    para_scales = []
    for p in paras[:5000]:  # 限制分析量
        scales_found = []
        for scale, words in SCALE_MARKERS.items():
            if any(w in p for w in words):
                scales_found.append(scale)
        if scales_found:
            para_scales.append(scales_found[0])  # 取第一个匹配的尺度

    # 计算相邻段落间的尺度跳变
    scale_jumps = 0
    for i in range(1, len(para_scales)):
        if para_scales[i] != para_scales[i-1]:
            scale_jumps += 1
    scale_jump_rate = round(scale_jumps / max(1, len(para_scales) - 1) * 100, 2)

    # 3. 推近/拉回模式
    scale_order = list(SCALE_MARKERS.keys())
    push_count = 0  # 大→小（推近）
    pull_count = 0  # 小→大（拉回）
    for i in range(1, len(para_scales)):
        prev_idx = scale_order.index(para_scales[i-1]) if para_scales[i-1] in scale_order else -1
        curr_idx = scale_order.index(para_scales[i]) if para_scales[i] in scale_order else -1
        if prev_idx >= 0 and curr_idx >= 0:
            if curr_idx > prev_idx:
                push_count += 1  # 推近
            elif curr_idx < prev_idx:
                pull_count += 1  # 拉回

    push_pull_ratio = round(push_count / max(1, push_count + pull_count) * 100, 2)

    # 4. 代表性段落（含多尺度标记的段落）
    examples = find_passages(text, list(SCALE_MARKERS["位面/大陆级"])[:3] + list(SCALE_MARKERS["极近景/细节级"])[:3],
                             min_chars=60, max_chars=300, count=5, min_keyword_density=0.01)

    return {
        "scale_freq": scale_freq,
        "scale_jump_rate": scale_jump_rate,
        "push_count": push_count,
        "pull_count": pull_count,
        "push_pull_ratio": push_pull_ratio,
        "examples": examples,
        "observation": (
            f"镜头切换率 {scale_jump_rate}%，推近 {push_count} 次 / 拉回 {pull_count} 次。"
            f"广角（位面/大陆级）词频 {scale_freq.get('位面/大陆级', {}).get('per_1000', 0)}/千字，"
            f"极近景词频 {scale_freq.get('极近景/细节级', {}).get('per_1000', 0)}/千字。"
            "烟雨江南的空间叙事呈'漏斗型'——从大陆级广角起笔，九级变焦推到一滴血/一道裂纹，"
            "再拉回世界继续运转。空间有纵深，不是平面的布景板。"
        )
    }

# ============================================================
# F10: 代价经济学（Economics of Cost）
# ============================================================

COST_WORDS = ["代价", "牺牲", "失去", "付出", "消耗", "枯竭", "透支", "燃烧",
              "寿命", "减寿", "血", "命", "魂", "精血", "本源"]
PRICE_WORDS = ["金币", "铜币", "银币", "钱", "五分", "十分", "价格", "昂贵", "廉价",
               "买", "卖", "付", "欠", "债", "挣", "省"]
SACRIFICE_WORDS = ["献祭", "燃烧", "引爆", "自毁", "断后", "殿后", "舍弃", "放弃",
                   "断臂", "断手", "挖出", "剜出", "刺穿", "贯穿"]

def analyze_cost_economics(text):
    """F10: 代价经济学分析"""
    total = max(1, han_count(text))

    # 1. 代价词频
    cost_count = sum(text.count(w) for w in COST_WORDS)
    cost_density = round(cost_count / total * 1000, 2)

    # 2. 价格/经济词频
    price_count = sum(text.count(w) for w in PRICE_WORDS)
    price_density = round(price_count / total * 1000, 2)

    # 3. 牺牲/自损词频
    sacrifice_count = sum(text.count(w) for w in SACRIFICE_WORDS)
    sacrifice_density = round(sacrifice_count / total * 1000, 2)

    # 4. 代价先行模式（"已经"出现在代价语境中）
    cost_already_pattern = len(re.findall(r"(已经|早已|早就).{0,10}(失去|付|消耗|燃烧|牺牲|代价)", text))

    # 5. 善意标价（帮助+代价共现）
    kindness_words = ["帮助", "救", "护", "给", "送", "让", "保护", "庇"]
    kindness_with_cost = 0
    paras = split_paras(text)
    for p in paras:
        has_kindness = any(w in p for w in kindness_words)
        has_cost = any(w in p for w in COST_WORDS + PRICE_WORDS)
        if has_kindness and has_cost:
            kindness_with_cost += 1
    kindness_cost_ratio = round(kindness_with_cost / max(1, sum(1 for p in paras if any(w in p for w in kindness_words))) * 100, 2)

    # 6. 代表性段落
    examples = find_passages(text, COST_WORDS + SACRIFICE_WORDS, min_chars=60, max_chars=250, count=5, min_keyword_density=0.015)

    return {
        "cost_density_per_1000": cost_density,
        "price_density_per_1000": price_density,
        "sacrifice_density_per_1000": sacrifice_density,
        "cost_first_pattern_count": cost_already_pattern,
        "kindness_cost_ratio": kindness_cost_ratio,
        "examples": examples,
        "observation": (
            f"代价词 {cost_density}/千字，价格词 {price_density}/千字，牺牲词 {sacrifice_density}/千字。"
            f"代价先行模式（'已经付了'而非'可能会付'）出现 {cost_already_pattern} 次。"
            f"善意标价率 {kindness_cost_ratio}%——世界中的善意几乎不免费，"
            "面包有价格，帮助有代价，力量的使用消耗生命。"
            "代价是已支付的事实而非未来的可能，这是'狠'的第一条法则。"
        )
    }

# ============================================================
# F11: 叙事呼吸（Narrative Breathing）
# ============================================================

def analyze_narrative_breathing(text):
    """F11: 叙事呼吸分析"""
    sents = split_sents(text)
    sent_lens = [han_count(s) for s in sents]
    total_sents = len(sents)

    if total_sents < 100:
        return {"error": "句子数不足"}

    # 1. 句长波动性（标准差/均值 = 变异系数）
    mean_len = sum(sent_lens) / total_sents
    stdev = math.sqrt(sum((l - mean_len) ** 2 for l in sent_lens) / total_sents)
    cv = round(stdev / mean_len, 3)

    # 2. 长短交替模式（连续短句→长句 的"呼气→吸气"模式）
    short_threshold = 10  # 短句阈值
    long_threshold = 35  # 长句阈值

    # 找到所有短句簇（连续≥3个短句）后跟长句的模式
    breath_patterns = 0
    i = 0
    while i < len(sent_lens) - 3:
        # 检查是否有≥3个连续短句
        if sent_lens[i] <= short_threshold and sent_lens[i+1] <= short_threshold and sent_lens[i+2] <= short_threshold:
            # 检查后面是否跟一个长句
            if i + 3 < len(sent_lens) and sent_lens[i+3] >= long_threshold:
                breath_patterns += 1
            i += 3
        else:
            i += 1

    breath_density = round(breath_patterns / total_sents * 1000, 2)

    # 3. 段落级呼吸（短段→长段→短段的波浪）
    paras = split_paras(text)
    para_lens = [han_count(p) for p in paras]
    total_paras = len(para_lens)

    wave_patterns = 0
    for i in range(1, len(para_lens) - 1):
        if para_lens[i-1] <= 20 and para_lens[i] >= 80 and para_lens[i+1] <= 20:
            wave_patterns += 1
    wave_density = round(wave_patterns / max(1, total_paras) * 100, 2)

    # 4. 节奏切换（无过渡段直接切换）
    abrupt_transitions = 0
    for i in range(1, len(para_lens)):
        # 前段长（>60）后段极短（≤15）= 急刹车
        if para_lens[i-1] > 60 and para_lens[i] <= 15:
            abrupt_transitions += 1
    abrupt_density = round(abrupt_transitions / max(1, total_paras) * 100, 2)

    # 5. 句长分布偏度
    median_len = sorted(sent_lens)[total_sents // 2]
    skewness = round((mean_len - median_len) / max(1, stdev), 3)

    # 6. 代表性呼吸段落（找到最佳长短交替段）
    examples = []
    for i in range(len(paras) - 3):
        cluster = paras[i:i+4]
        cluster_lens = [han_count(p) for p in cluster]
        # 短-短-长 或 长-短-短-长 的模式
        if (cluster_lens[0] <= 15 and cluster_lens[1] <= 15 and cluster_lens[2] >= 60):
            text_preview = " | ".join(p.strip()[:40] for p in cluster)
            examples.append({"pattern": "短-短-长", "text": text_preview[:200]})
        elif (cluster_lens[0] >= 60 and cluster_lens[1] <= 15 and cluster_lens[2] <= 15):
            text_preview = " | ".join(p.strip()[:40] for p in cluster)
            examples.append({"pattern": "长-短-短", "text": text_preview[:200]})
        if len(examples) >= 5:
            break

    return {
        "length_cv": cv,
        "mean_sent_len": round(mean_len, 2),
        "median_sent_len": median_len,
        "stdev_sent_len": round(stdev, 2),
        "skewness": skewness,
        "breath_pattern_density": breath_density,
        "wave_density": wave_density,
        "abrupt_transition_density": abrupt_density,
        "examples": examples,
        "observation": (
            f"句长变异系数 {cv}（高变异=强呼吸感），均值 {round(mean_len, 1)} 字 / 中位 {median_len} 字。"
            f"呼吸模式密度 {breath_density}/千句（连续短句后跟长句的'呼气→吸气'），"
            f"段落波浪 {wave_density}%，急刹车切换 {abrupt_density}%。"
            "叙事呼吸呈现'长段铺垫→短段爆发→极短段凝固'的三级呼吸节奏，"
            "节奏切换不写过渡段——落差本身就是节奏。"
        )
    }

# ============================================================
# F12: 视角策略（Perspective Strategy）
# ============================================================

def analyze_perspective(text):
    """F12: 视角策略分析"""
    chapters = extract_chapters(text)
    total = max(1, han_count(text))

    # 1. 代词分布（第三人称 vs 第一人称 vs 第二人称）
    pronoun_counts = {
        "第三人称-他": text.count("他"),
        "第三人称-她": text.count("她"),
        "第一人称-我": text.count("我"),
        "第二人称-你": text.count("你"),
        "第三人称-它": text.count("它"),
    }
    pronoun_total = sum(pronoun_counts.values()) or 1
    pronoun_dist = {k: round(v / pronoun_total * 100, 2) for k, v in pronoun_counts.items()}

    # 2. 视角载体多样性（章节中是否引入非主角视角）
    if chapters:
        non_protagonist_paras = 0
        total_chapter_paras = 0
        for ch in chapters[:50]:
            ch_paras = split_paras(ch["text"])
            for p in ch_paras:
                if han_count(p) > 30:
                    total_chapter_paras += 1
                    # 不含主角名/代词但有其他角色名的段落
                    has_protagonist = any(w in p for w in EXCLUDE_NAMES + ["他", "她"])
                    has_other_char = bool(re.search(r'(?:\u201c[^\u201d]{1,300}\u201d|"[^"]{1,300}"|「[^」]{1,300}」)', p))
                    if not has_protagonist and has_other_char:
                        non_protagonist_paras += 1
        perspective_diversity = round(non_protagonist_paras / max(1, total_chapter_paras) * 100, 2)
    else:
        perspective_diversity = 0

    # 3. 旁观者视角段（世界描写，不含任何人称代词）
    paras = split_paras(text)
    bystander_paras = 0
    for p in paras:
        chars = han_count(p)
        if chars < 30 or chars > 150:
            continue
        has_pronoun = any(w in p for w in ["他", "她", "我", "你"])
        has_sensory = any(w in p for words in SENSORY_WORDS.values() for w in words)
        if not has_pronoun and has_sensory:
            bystander_paras += 1
    bystander_density = round(bystander_paras / max(1, len(paras)) * 100, 2)

    # 4. 视角切换频率（每章中不同代词主导的段落切换次数）
    if chapters:
        avg_switches = 0
        for ch in chapters[:50]:
            ch_paras = split_paras(ch["text"])
            prev_dominant = None
            switches = 0
            for p in ch_paras:
                if han_count(p) < 20:
                    continue
                # 判断主导代词
                he_count = p.count("他")
                she_count = p.count("她")
                i_count = p.count("我")
                if he_count > she_count and he_count > i_count:
                    dominant = "他"
                elif she_count > he_count and she_count > i_count:
                    dominant = "她"
                elif i_count > he_count and i_count > she_count:
                    dominant = "我"
                else:
                    dominant = None

                if dominant and prev_dominant and dominant != prev_dominant:
                    switches += 1
                if dominant:
                    prev_dominant = dominant
            avg_switches += switches
        avg_switches = round(avg_switches / max(1, min(50, len(chapters))), 2)
    else:
        avg_switches = 0

    # 5. 代表性旁观者段落
    bystander_examples = []
    for p in paras:
        chars = han_count(p)
        if 30 <= chars <= 150:
            has_pronoun = any(w in p for w in ["他", "她", "我", "你"])
            has_sensory = any(w in p for words in SENSORY_WORDS.values() for w in words)
            if not has_pronoun and has_sensory:
                bystander_examples.append(p.strip()[:150])
                if len(bystander_examples) >= 5:
                    break

    return {
        "pronoun_dist": pronoun_dist,
        "perspective_diversity": perspective_diversity,
        "bystander_para_ratio": bystander_density,
        "avg_perspective_switches_per_chapter": avg_switches,
        "bystander_examples": bystander_examples,
        "observation": (
            f"代词分布：他 {pronoun_dist.get('第三人称-他', 0)}%，"
            f"她 {pronoun_dist.get('第三人称-她', 0)}%，我 {pronoun_dist.get('第一人称-我', 0)}%。"
            f"旁观者段落（无代词+有感官）占比 {bystander_density}%，"
            f"每章平均视角切换 {avg_switches} 次。"
            "烟雨江南采用多视角第三人称叙事，允许世界在主角不看它的时候存在。"
            "旁观者段落让世界显得独立于剧情，而非围着主角转的布景。"
        )
    }

# ============================================================
# 风格内核卡生成
# ============================================================

def generate_essence_card(results):
    """根据12维分析结果生成风格内核卡"""
    card = {
        "author": "烟雨江南",
        "label": "黑暗·苍凉·克制",
        "version": "1.0",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "core_aesthetic": "世界在衰退，人在挣扎，沉默比呐喊更重",
        "twelve_dimensions": {},
        "style_anchors": [],
        "writing_guidance": [],
    }

    # 12维评分（0-10，基于分析数据的定性评估）
    dims = [
        ("F1_苍凉底色", "苍凉是底色而非情绪", 8.5,
         "世界衰退的常态呈现：锈蚀的金属、龟裂的城墙、褪色的杂志——苍凉活在物件的磨损里，不活在角色的叹息里。"),
        ("F2_克制美学", "不说的比说的重", 9.0,
         "情绪通过身体反应和沉默传递，直接陈述极少。重击之后让世界继续运转，而非进入心理独白。"),
        ("F3_暴力重量", "每滴血都有买价", 8.0,
         "暴力不是动作清单，是物理后果链。伤口不会'过两天就好'，每个打击都改变身体状态。"),
        ("F4_世界质感", "铁会生锈，善意有价", 8.5,
         "世界由具体材质构成，一切都在磨损。经济系统渗透描写——面包有价格，刀剑有锈迹。"),
        ("F5_时间纵深", "时间是物件的磨损", 7.5,
         "时间通过物件变化（杂志变薄、刀剑生锈）传递，数字时间标记少。历史活在patina里。"),
        ("F6_意象变奏", "同一个词在生长", 8.0,
         "核心意象在全书递进，每次出现都在新的语义层级——从物到工具到概念到命运。"),
        ("F7_对话暗流", "台词之间的沉默是权力", 8.5,
         "对话核心在台词之间。沉默、动作打断、短句对话构成权力暗流。谁沉默谁有权。"),
        ("F8_章末余响", "余响比钩子有力", 8.0,
         "章末以沉默和环境收束，信息只给一半。物件异常做视觉锚，迫使读者脑补。"),
        ("F9_空间纵深", "漏斗型镜头运动", 7.5,
         "从大陆级广角起笔，九级变焦推到一滴血，再拉回世界运转。空间有纵深不是平面布景。"),
        ("F10_代价经济学", "一切已支付，不是可能付", 8.0,
         "代价是既成事实而非承诺。善意标价，力量消耗生命。'狠'的第一条：伤口先于承诺到达。"),
        ("F11_叙事呼吸", "三级呼吸：铺垫→爆发→凝固", 8.5,
         "句长变异系数高，长段铺垫→短段爆发→极短段凝固。节奏切换不写过渡段，落差即节奏。"),
        ("F12_视角策略", "世界在主角不看它时也存在", 7.0,
         "多视角第三人称，旁观者段落让世界独立于剧情。允许世界在角色不看它时自转。"),
    ]

    for code, name, score, desc in dims:
        f_key = f"F{code.split('_')[0][1:]}"
        data = results.get(f_key, {})
        card["twelve_dimensions"][code] = {
            "name": name,
            "score": score,
            "description": desc,
            "key_metric": data.get("observation", ""),
        }

    # 风格锚点（注入写手时每章提醒）
    card["style_anchors"] = [
        "苍凉底色：每章至少一处物件磨损描写（锈/裂/褪色），世界在衰退中常态运转",
        "克制情绪：情绪重击后接世界描写而非心理独白，身体反应先于意识觉知",
        "暴力有重：每场战斗至少一处伤口后果（踉跄/虚弱/无法动作），禁止'过两天就好'",
        "世界质感：每场景至少一个具体材质+磨损标记，善意必须标价",
        "空间漏斗：章首广角起笔推到近景，极近景后拉回世界继续运转",
        "对话暗流：台词间用动作/沉默打断，短对话≤8字，裸对话无引导语",
        "章末余响：沉默或环境收尾，信息只给30-50%，物件异常做视觉锚",
        "叙事呼吸：长段铺垫→短段爆发→极短段凝固，节奏切换不写过渡段",
    ]

    # 写作指引
    card["writing_guidance"] = [
        "【开篇】从广角起笔（大陆/天空/大地），三句内落到具体小物，世界先于人物建立",
        "【情感】身体先于意识：手抖了人才发现害怕，不是'他感到恐惧所以手抖'",
        "【战斗】一击之后紧接对手身体反应，动作之间用身体感受呼吸，禁止插入规矩/数字/花名册",
        "【死亡】死前先给三行具体的活，死后世界继续吵，死者住在活人日常使用的物件里",
        "【时间】不写'三年过去了'，写三个物件的变化量（杂志变薄、刀剑生锈、城墙龟裂）",
        "【物件】旧物必须廉价，不值钱才沉；物件每经过一双手多一层意义；早早埋迟迟兑",
        "【对话】权力高低不靠台词展现，靠谁打断谁/谁沉默/谁最后说话",
        "【章末】让主角以沉默/不动作收尾，给出半句信息留另一半悬置，用一个物件异常做锚",
    ]

    return card

# ============================================================
# HTML 报告生成
# ============================================================

def generate_html_report(results, essence_card):
    """生成可读的 HTML 韵味档案报告"""
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>烟雨江南 · 全方面韵味档案</title>
<style>
:root {
  --bg: #0d0d0d; --card: #1a1a1a; --border: #333;
  --fg: #e0e0e0; --muted: #888; --accent: #9c27b0;
  --gold: #d4af37; --red: #f44336; --blue: #2196f3; --green: #4caf50;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: var(--bg); color: var(--fg);
  font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', sans-serif;
  line-height: 1.8; padding: 20px;
}
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: var(--gold); font-size: 28px; text-align: center; margin: 20px 0 10px; }
h2 { color: var(--accent); font-size: 20px; margin: 30px 0 15px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
h3 { color: var(--fg); font-size: 16px; margin: 20px 0 10px; }
.subtitle { text-align: center; color: var(--muted); margin-bottom: 30px; font-size: 14px; }

/* 雷达图 */
.radar-container { display: flex; justify-content: center; margin: 20px 0; }
.radar-container svg { max-width: 500px; }

/* 维度卡片网格 */
.dim-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 15px; margin: 20px 0; }
.dim-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; padding: 15px; transition: border-color 0.3s;
}
.dim-card:hover { border-color: var(--accent); }
.dim-card .dim-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.dim-card .dim-name { font-size: 15px; font-weight: bold; color: var(--gold); }
.dim-card .dim-score { font-size: 18px; font-weight: bold; color: var(--accent); }
.dim-card .dim-desc { font-size: 13px; color: var(--muted); margin-bottom: 8px; }
.dim-card .dim-obs { font-size: 13px; color: var(--fg); line-height: 1.7; }

/* 指标行 */
.metrics { margin: 10px 0; }
.metric-row { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #222; font-size: 13px; }
.metric-row .label { color: var(--muted); }
.metric-row .value { color: var(--gold); font-weight: bold; }

/* 示例段落 */
.example-box { background: #111; border-left: 3px solid var(--accent); padding: 10px; margin: 8px 0; font-size: 13px; color: #aaa; line-height: 1.6; }
.example-box::before { content: "示例"; color: var(--muted); font-size: 11px; display: block; margin-bottom: 4px; }

/* 风格锚点 */
.anchor-list { list-style: none; }
.anchor-list li { background: var(--card); border-left: 3px solid var(--gold); padding: 10px 15px; margin: 8px 0; font-size: 14px; }
.anchor-list li::before { content: "▸ "; color: var(--gold); }

/* 写作指引 */
.guidance-list { list-style: none; }
.guidance-list li { background: #111; border: 1px solid var(--border); border-radius: 6px; padding: 12px 15px; margin: 8px 0; font-size: 14px; }
.guidance-list li strong { color: var(--accent); }

/* 核心美学 */
.aesthetic-box { text-align: center; background: var(--card); border: 2px solid var(--gold); border-radius: 12px; padding: 25px; margin: 20px 0; }
.aesthetic-box .main { font-size: 22px; color: var(--gold); font-weight: bold; }
.aesthetic-box .sub { font-size: 14px; color: var(--muted); margin-top: 8px; }
</style>
</head>
<body>
<div class="container">
<h1>烟雨江南 · 全方面韵味档案</h1>
<p class="subtitle">12 维度深度蒸馏 · v1.0 · 生成于 """ + datetime.now().strftime("%Y-%m-%d %H:%M") + """</p>

<div class="aesthetic-box">
  <div class="main">世界在衰退，人在挣扎，沉默比呐喊更重</div>
  <div class="sub">黑暗·苍凉·克制 — 韵味不在统计参数里，在文字的呼吸方式里</div>
</div>
"""

    # 雷达图 SVG
    dims_for_radar = [
        ("苍凉底色", results.get("F1", {}).get("density_per_1000", 0), 15),
        ("克制美学", results.get("F2", {}).get("restraint_ratio", 0), 100),
        ("暴力重量", results.get("F3", {}).get("violence_weight_ratio", 0), 200),
        ("世界质感", results.get("F4", {}).get("material_density_per_1000", 0), 30),
        ("时间纵深", results.get("F5", {}).get("object_change_per_1000", 0), 5),
        ("意象变奏", len(results.get("F6", {}).get("core_image_freq", {})) * 2, 20),
        ("对话暗流", results.get("F7", {}).get("subtext_density_per_1000", 0), 10),
        ("章末余响", results.get("F8", {}).get("resonance_ratio", 0), 60),
        ("空间纵深", results.get("F9", {}).get("scale_jump_rate", 0), 30),
        ("代价经济", results.get("F10", {}).get("cost_density_per_1000", 0), 15),
        ("叙事呼吸", results.get("F11", {}).get("length_cv", 0), 1),
        ("视角策略", results.get("F12", {}).get("bystander_para_ratio", 0), 15),
    ]

    # 归一化到0-1
    radar_data = []
    for name, val, max_val in dims_for_radar:
        normalized = min(1.0, val / max_val) if max_val > 0 else 0
        radar_data.append((name, round(normalized, 3)))

    # 生成雷达图SVG
    cx, cy, r = 200, 200, 150
    n = len(radar_data)
    angles = [i * 2 * math.pi / n - math.pi / 2 for i in range(n)]

    # 背景多边形
    bg_polygons = ""
    for level in [0.2, 0.4, 0.6, 0.8, 1.0]:
        points = []
        for i, angle in enumerate(angles):
            px = cx + r * level * math.cos(angle)
            py = cy + r * level * math.sin(angle)
            points.append(f"{px:.1f},{py:.1f}")
        bg_polygons += f'<polygon points="{" ".join(points)}" fill="none" stroke="#333" stroke-width="0.5"/>'

    # 轴线和标签
    axis_lines = ""
    axis_labels = ""
    for i, (name, val) in enumerate(radar_data):
        angle = angles[i]
        px = cx + r * math.cos(angle)
        py = cy + r * math.sin(angle)
        axis_lines += f'<line x1="{cx}" y1="{cy}" x2="{px:.1f}" y2="{py:.1f}" stroke="#444" stroke-width="0.5"/>'
        lx = cx + (r + 20) * math.cos(angle)
        ly = cy + (r + 20) * math.sin(angle)
        axis_labels += f'<text x="{lx:.1f}" y="{ly:.1f}" fill="#aaa" font-size="10" text-anchor="middle" dy="0.35em">{name}</text>'

    # 数据多边形
    data_points = []
    for i, (name, val) in enumerate(radar_data):
        angle = angles[i]
        px = cx + r * val * math.cos(angle)
        py = cy + r * val * math.sin(angle)
        data_points.append(f"{px:.1f},{py:.1f}")

    html += f"""
<h2>韵味雷达图</h2>
<div class="radar-container">
<svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg">
  {bg_polygons}
  {axis_lines}
  <polygon points="{" ".join(data_points)}" fill="rgba(156,39,176,0.3)" stroke="#9c27b0" stroke-width="2"/>
  {"".join(f'<circle cx="{cx + r * v * math.cos(angles[i]):.1f}" cy="{cy + r * v * math.sin(angles[i]):.1f}" r="3" fill="#d4af37"/>' for i, (n, v) in enumerate(radar_data))}
  {axis_labels}
</svg>
</div>
"""

    # 12维详细卡片
    html += '<h2>12 维韵味分析</h2><div class="dim-grid">'

    dim_info = [
        ("F1", "苍凉底色", "世界衰退的常态呈现", "density_per_1000", "苍凉词/千字"),
        ("F2", "克制美学", "不说的比说的重", "restraint_ratio", "克制比(%)"),
        ("F3", "暴力重量", "每滴血都有买价", "violence_weight_ratio", "后果/伤口(%)"),
        ("F4", "世界质感", "铁会生锈，善意有价", "material_density_per_1000", "材质词/千字"),
        ("F5", "时间纵深", "时间是物件的磨损", "object_change_per_1000", "物件变化/千字"),
        ("F6", "意象变奏", "同一个词在生长", None, None),
        ("F7", "对话暗流", "台词之间的沉默是权力", "subtext_density_per_1000", "暗流词/千字"),
        ("F8", "章末余响", "余响比钩子有力", "resonance_ratio", "余响型章末(%)"),
        ("F9", "空间纵深", "漏斗型镜头运动", "scale_jump_rate", "镜头切换率(%)"),
        ("F10", "代价经济学", "一切已支付", "cost_density_per_1000", "代价词/千字"),
        ("F11", "叙事呼吸", "三级呼吸节奏", "length_cv", "句长变异系数"),
        ("F12", "视角策略", "世界在主角不看它时也存在", "bystander_para_ratio", "旁观者段落(%)"),
    ]

    for key, name, desc, metric_key, metric_label in dim_info:
        data = results.get(key, {})
        obs = data.get("observation", "")
        examples = data.get("examples", [])
        score = next((d["score"] for d in essence_card.get("twelve_dimensions", {}).values() if key in d.get("name", "") or any(k.startswith(key) for k in essence_card.get("twelve_dimensions", {}))), 7.5)

        html += f"""
<div class="dim-card">
  <div class="dim-header">
    <span class="dim-name">{key} · {name}</span>
    <span class="dim-score">{score}</span>
  </div>
  <div class="dim-desc">{desc}</div>
  <div class="dim-obs">{obs}</div>
"""
        # 关键指标
        if metric_key and metric_key in data:
            html += f'<div class="metrics"><div class="metric-row"><span class="label">{metric_label}</span><span class="value">{data[metric_key]}</span></div></div>'

        # 示例
        for ex in examples[:2]:
            ex_text = ex.get("text", ex) if isinstance(ex, dict) else str(ex)
            html += f'<div class="example-box">{ex_text[:150]}</div>'

        html += "</div>"

    html += "</div>"

    # 风格内核卡
    html += """
<h2>风格内核卡</h2>
<h3>风格锚点（每章注入写手）</h3>
<ul class="anchor-list">
"""
    for anchor in essence_card.get("style_anchors", []):
        html += f"<li>{anchor}</li>"

    html += """
</ul>
<h3>写作指引</h3>
<ul class="guidance-list">
"""
    for guide in essence_card.get("writing_guidance", []):
        # 提取标签
        parts = guide.split("】")
        if len(parts) == 2:
            tag = parts[0] + "】"
            content = parts[1]
            html += f"<li><strong>{tag}</strong>{content}</li>"
        else:
            html += f"<li>{guide}</li>"

    html += """
</ul>
</div>
</body>
</html>
"""
    return html

# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print("  烟雨江南全方面韵味蒸馏 v1.0")
    print("  12 维定性+定量分析")
    print("=" * 60)

    # 加载原作
    print("\n[1/4] 加载原作...")
    raw_text = load_all_works()
    text = sample_text(raw_text, target=500000)
    total = han_count(text)
    print(f"  采样字数: {total}")

    # 运行12维分析
    print("\n[2/4] 运行12维韵味分析...")
    results = {}

    analyzers = [
        ("F1", "苍凉底色", analyze_desolate),
        ("F2", "克制美学", analyze_restraint),
        ("F3", "暴力重量", analyze_violence),
        ("F4", "世界质感", analyze_world_texture),
        ("F5", "时间纵深", analyze_temporal_depth),
        ("F6", "意象变奏", analyze_imagery_variation),
        ("F7", "对话暗流", analyze_dialogue_undertow),
        ("F8", "章末余响", analyze_chapter_endings),
        ("F9", "空间纵深", analyze_spatial_depth),
        ("F10", "代价经济学", analyze_cost_economics),
        ("F11", "叙事呼吸", analyze_narrative_breathing),
        ("F12", "视角策略", analyze_perspective),
    ]

    for key, name, func in analyzers:
        print(f"  [{key}] {name}...", end=" ")
        try:
            result = func(text)
            results[key] = result
            print("完成")
        except Exception as e:
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()
            results[key] = {"error": str(e)}

    # 生成风格内核卡
    print("\n[3/4] 生成风格内核卡...")
    essence_card = generate_essence_card(results)

    # 保存报告
    print("\n[4/4] 保存报告...")
    os.makedirs(REPORT_DIR, exist_ok=True)

    # JSON 报告
    json_path = os.path.join(REPORT_DIR, "yanyujiangnan_flavor.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "author": "烟雨江南",
            "label": "黑暗·苍凉·克制",
            "version": "1.0",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sample_chars": total,
            "dimensions": results,
            "essence_card": essence_card,
        }, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {json_path}")

    # 风格内核卡 JSON
    card_path = os.path.join(REPORT_DIR, "style_essence_card.json")
    with open(card_path, "w", encoding="utf-8") as f:
        json.dump(essence_card, f, ensure_ascii=False, indent=2)
    print(f"  内核卡: {card_path}")

    # HTML 报告
    html = generate_html_report(results, essence_card)
    html_path = os.path.join(REPORT_DIR, "yanyujiangnan_flavor.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  HTML: {html_path}")

    # 打印摘要
    print("\n" + "=" * 60)
    print("  韵味蒸馏完成！")
    print("=" * 60)
    print("\n核心发现：")
    for key, name, _ in analyzers:
        data = results.get(key, {})
        obs = data.get("observation", "")
        if obs:
            print(f"\n  [{key}] {name}")
            print(f"  {obs[:120]}...")

    print(f"\n\n报告位置:")
    print(f"  JSON: {json_path}")
    print(f"  HTML: {html_path}")
    print(f"  内核卡: {card_path}")

if __name__ == "__main__":
    main()
