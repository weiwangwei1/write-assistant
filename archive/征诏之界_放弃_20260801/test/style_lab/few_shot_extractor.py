#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
few_shot_extractor.py — 从原作中按场景类型切分 Few-shot 样本

场景分类：battle（战斗）/ dialogue（对话）/ environment（环境）/ psychology（心理）/ full_chapter（整章）

算法：滑动窗口 + 场景分类器 → 选取高质量段落 → 去重 → 输出 JSON

用法：
  cd d:\\personFile\\write-assist\\write-assistant
  python test/style_lab/few_shot_extractor.py                    # 全部作者
  python test/style_lab/few_shot_extractor.py --author yanyujiangnan  # 指定作者
"""

import os, sys, re, json, math, random
from collections import Counter, defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from style_fingerprint import split_paras, han_count, split_sents, SENSORY_WORDS

# ============================================================
# 配置
# ============================================================

LAB_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(LAB_DIR, "few_shot_samples")

CONFIG = {
    "yanyujiangnan": {
        "display_name": "烟雨江南",
        "works": [
            ".trae/skills/writer-styles/yanyujiangnan/reference/原作_utf8/《永夜君王》（校对版全本）作者：烟雨江南.txt",
            ".trae/skills/writer-styles/yanyujiangnan/reference/原作_utf8/《狩魔手记》（校对版全本）作者：烟雨江南.txt",
            ".trae/skills/writer-styles/yanyujiangnan/reference/原作_utf8/《罪恶之城》（校对版全本）作者：烟雨江南.txt",
        ],
        "exclude_names": ["李察", "千夜", "宋子宁", "夜瞳", "赵君"],
    },
    "chendong": {
        "display_name": "辰东",
        "works": [
            ".trae/skills/writer-styles/chendong/reference/原作/完美世界.txt",
            ".trae/skills/writer-styles/chendong/reference/原作/遮天（精校版）.txt",
        ],
        "exclude_names": ["石昊", "叶凡"],
    },
    "jiangnan": {
        "display_name": "江南",
        "works": [
            ".trae/skills/writer-styles/jiangnan/reference/原作_utf8/《九州·缥缈录》作者：江南.txt",
            ".trae/skills/writer-styles/jiangnan/reference/原作_utf8/《龙族》作者：江南.txt",
        ],
        "exclude_names": ["吕归尘", "路明非"],
    },
    "maibao": {
        "display_name": "卖报小郎君",
        "works": [
            ".trae/skills/writer-styles/maibao/reference/原作_utf8/大奉打更人.txt",
            ".trae/skills/writer-styles/maibao/reference/原作_utf8/灵境行者.txt",
        ],
        "exclude_names": ["许七安", "张元清"],
    },
    "wuzei": {
        "display_name": "爱潜水的乌贼",
        "works": [
            ".trae/skills/writer-styles/wuzei/reference/原作_utf8/诡秘之主.txt",
            ".trae/skills/writer-styles/wuzei/reference/原作_utf8/一世之尊.txt",
        ],
        "exclude_names": ["克莱恩", "顾青山"],
    },
}

# 场景分类关键词
BATTLE_KEYWORDS = set("刀剑枪炮拳掌踢打劈砍刺射冲击撞挡格挡闪避翻滚跳跃扑杀血伤断裂碎裂爆破轰击横扫席卷撕裂绞碎震飞弹飞跌落怒吼嘶吼咆哮轰鸣炸裂贯穿洞穿穿透冲击波刀光剑影杀气战意杀意战",
                     )
BATTLE_THRESHOLD = 0.04  # 动作词密度阈值

DIALOGUE_RATIO_THRESHOLD = 0.30  # 对话占比阈值（降低：合并段落后对话被稀释）
DIALOGUE_MIN_CHARS = 200  # 对话场景最小字数（短于其他场景，因为对话本身精炼）

ENVIRONMENT_SENSORY_THRESHOLD = 0.04  # 感官词密度阈值

PSYCH_WORDS = ("想", "觉得", "感到", "知道", "认为", "意识", "心中", "内心", "思绪",
               "记忆", "回忆", "忘记", "明白", "理解", "恐惧", "不安", "犹豫", "怀疑",
               "愤怒", "悲伤", "孤独", "渴望", "嫉妒", "悔恨", "无奈", "释然")
PSYCH_THRESHOLD = 0.025  # 心理词密度阈值

# 动作动词集
ACTION_CHARS = set("走跑跳冲撞劈砍刺射踢打抓握推拉转身倒摔倒爬起立坐蹲站停飞扑闪避格挡挥抬迈跨踏射")

# 样本参数
SAMPLE_MIN_CHARS = 400    # 最小字数
SAMPLE_MAX_CHARS = 2000   # 最大字数
SAMPLES_PER_TYPE = 8      # 每类场景样本数
FULL_CHAPTER_SAMPLES = 3  # 整章样本数
FULL_CHAPTER_MIN_CHARS = 2000  # 整章最小字数

# ============================================================
# 文本加载
# ============================================================

def load_work(rel_path):
    full_path = os.path.join(PROJECT_ROOT, rel_path)
    if not os.path.exists(full_path):
        return ""
    for enc in ("utf-8", "gbk", "utf-16"):
        try:
            with open(full_path, "r", encoding=enc) as f:
                text = f.read()
            return text
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""

def clean_text(text):
    """去除章节标题、空行等"""
    lines = [l.strip() for l in text.splitlines()
             if l.strip() and not re.match(r"^(第\d+章|字数|—{3,}|-{3,}| Chapter|CHAPTER|内容简介|PS|作者)", l.strip())]
    return "\n".join(lines)

# ============================================================
# 场景分类器
# ============================================================

def classify_scene(para):
    """分类段落场景类型"""
    chars = han_count(para)
    if chars < 20:
        return "narration"

    # 对话检测
    dialogues = re.findall(r"[""「].{1,300}[""」]", para)
    dial_chars = sum(han_count(d) for d in dialogues)
    dial_ratio = dial_chars / max(1, chars)

    # 动作词检测
    action_count = sum(1 for c in para if c in ACTION_CHARS or c in BATTLE_KEYWORDS)
    action_density = action_count / max(1, chars)

    # 感官词检测
    sensory_count = sum(para.count(w) for words in SENSORY_WORDS.values() for w in words)
    sensory_density = sensory_count / max(1, chars)

    # 心理词检测
    psych_count = sum(para.count(w) for w in PSYCH_WORDS)
    psych_density = psych_count / max(1, chars)

    # 判断优先级：对话 > 战斗 > 心理 > 环境 > 叙述
    # （对话优先于战斗：对话场景常含动作词，但核心是对话而非打斗）
    if dial_ratio >= DIALOGUE_RATIO_THRESHOLD and dial_chars >= 30:
        return "dialogue"
    if action_density >= BATTLE_THRESHOLD and action_count >= 5 and chars >= 100 and dial_ratio < 0.2:
        return "battle"
    if psych_density >= PSYCH_THRESHOLD and psych_count >= 3:
        return "psychology"
    if sensory_density >= ENVIRONMENT_SENSORY_THRESHOLD and sensory_count >= 4 and dial_ratio < 0.2:
        return "environment"
    return "narration"

# ============================================================
# 样本提取
# ============================================================

def extract_dialogue_samples(text, min_chars, max_chars, count):
    """专门提取对话样本——智能合并：只合并含对话或短叙述的段落"""
    paras = split_paras(text)
    candidates = []

    i = 0
    while i < len(paras):
        # 检查当前段是否含对话
        matches = re.findall(r'[\u201c\u300c"].{1,300}[\u201d\u300d"]', paras[i])
        if not matches:
            i += 1
            continue

        # 从当前段开始，智能合并：只合并含对话或短叙述的段
        merged = paras[i]
        j = i + 1
        while j < len(paras) and j < i + 20 and han_count(merged) < min_chars:
            m2 = re.findall(r'[\u201c\u300c"].{1,300}[\u201d\u300d"]', paras[j])
            # 合并条件：有对话 或 段落很短（<60字的叙述作为对话间过渡）
            if m2 or han_count(paras[j]) < 60:
                merged += "\n" + paras[j]
                j += 1
            else:
                break

        chars = han_count(merged)
        if DIALOGUE_MIN_CHARS <= chars <= max_chars:
            # 验证对话占比
            all_m = re.findall(r'[\u201c\u300c"].{1,300}[\u201d\u300d"]', merged)
            dial_chars = sum(han_count(m) for m in all_m)
            dial_ratio = dial_chars / max(1, chars)
            if dial_ratio >= DIALOGUE_RATIO_THRESHOLD and dial_chars >= 30:
                quality = score_quality(merged, "dialogue")
                candidates.append({
                    "text": merged,
                    "type": "dialogue",
                    "chars": chars,
                    "quality": quality,
                    "index": i,
                    "dial_ratio": round(dial_ratio, 3),
                })
        elif chars > max_chars:
            # 太长，截取前 max_chars
            truncated = merged[:max_chars]
            all_m = re.findall(r'[\u201c\u300c"].{1,300}[\u201d\u300d"]', truncated)
            dial_chars = sum(han_count(m) for m in all_m)
            dial_ratio = dial_chars / max(1, han_count(truncated))
            if dial_ratio >= DIALOGUE_RATIO_THRESHOLD and dial_chars >= 30:
                quality = score_quality(truncated, "dialogue")
                candidates.append({
                    "text": truncated,
                    "type": "dialogue",
                    "chars": han_count(truncated),
                    "quality": quality,
                    "index": i,
                    "dial_ratio": round(dial_ratio, 3),
                })
        i = j

    # 按质量排序，去重
    candidates.sort(key=lambda x: -x["quality"])
    selected = []
    for c in candidates:
        too_close = any(abs(c["index"] - s["index"]) < 50 for s in selected)
        if not too_close:
            selected.append(c)
            if len(selected) >= count:
                break
    return selected

def extract_paragraphs_by_type(text, target_type, min_chars, max_chars, count):
    """从文本中提取指定类型的段落样本"""
    paras = split_paras(text)
    candidates = []

    # 对话场景使用更短的最小字数
    effective_min = DIALOGUE_MIN_CHARS if target_type == "dialogue" else min_chars

    # 用滑动窗口合并相邻段落到目标字数范围
    i = 0
    while i < len(paras):
        # 尝试从当前位置开始合并段落
        merged = paras[i]
        j = i + 1
        while j < len(paras) and han_count(merged) < effective_min:
            merged += "\n" + paras[j]
            j += 1

        chars = han_count(merged)
        if effective_min <= chars <= max_chars:
            scene_type = classify_scene(merged)
            if scene_type == target_type:
                # 计算质量分
                quality = score_quality(merged, scene_type)
                candidates.append({
                    "text": merged,
                    "type": scene_type,
                    "chars": chars,
                    "quality": quality,
                    "index": i,
                })
        elif chars > max_chars and min_chars <= max_chars:
            # 太长，截取前 max_chars 字
            truncated = merged[:max_chars]
            scene_type = classify_scene(truncated)
            if scene_type == target_type:
                quality = score_quality(truncated, scene_type)
                candidates.append({
                    "text": truncated,
                    "type": scene_type,
                    "chars": han_count(truncated),
                    "quality": quality,
                    "index": i,
                })

        i = j  # 跳到合并后的下一段

    # 按质量分排序，取前 count 个
    candidates.sort(key=lambda x: -x["quality"])

    # 去重：避免选取相邻的样本（内容太相似）
    selected = []
    used_indices = set()
    for c in candidates:
        # 检查与已选样本的索引距离
        too_close = False
        for s in selected:
            if abs(c["index"] - s["index"]) < 50:  # 至少间隔50段
                too_close = True
                break
        if not too_close:
            selected.append(c)
            if len(selected) >= count:
                break

    return selected

def score_quality(text, scene_type):
    """计算样本质量分（0-1）"""
    chars = max(1, han_count(text))
    sents = split_sents(text)
    sent_lens = [han_count(s) for s in sents]
    if not sent_lens:
        return 0

    # 句长多样性（标准差/均值，越大越好，但有上限）
    mean_len = sum(sent_lens) / len(sent_lens)
    if mean_len == 0:
        return 0
    stdev = math.sqrt(sum((l - mean_len)**2 for l in sent_lens) / len(sent_lens))
    cv = min(1.0, stdev / mean_len)  # 变异系数

    # 感官密度
    sensory_count = sum(text.count(w) for words in SENSORY_WORDS.values() for w in words)
    sensory_density = min(1.0, sensory_count / chars * 50)

    # 长短句交替
    short_count = sum(1 for l in sent_lens if l <= 10)
    long_count = sum(1 for l in sent_lens if l > 35)
    rhythm = min(1.0, (short_count + long_count) / max(1, len(sent_lens)) * 2)

    # 场景特定加分
    type_bonus = 0
    if scene_type == "battle":
        action_count = sum(1 for c in text if c in ACTION_CHARS)
        type_bonus = min(0.3, action_count / chars * 20)
    elif scene_type == "dialogue":
        dialogues = re.findall(r"[""「].{1,300}[""」]", text)
        dial_chars = sum(han_count(d) for d in dialogues)
        type_bonus = min(0.3, dial_chars / chars * 0.5)
    elif scene_type == "environment":
        type_bonus = min(0.3, sensory_count / chars * 20)
    elif scene_type == "psychology":
        psych_count = sum(text.count(w) for w in PSYCH_WORDS)
        type_bonus = min(0.3, psych_count / chars * 50)

    return round(cv * 0.3 + sensory_density * 0.2 + rhythm * 0.2 + type_bonus + 0.3, 3)

def extract_full_chapters(text, count, min_chars):
    """提取整章样本"""
    # 按"第N章"切分
    marks = [m.start() for m in re.finditer(r"(?m)^第[0-9零一二三四五六七八九十百千两]+章", text)]
    chapters = []
    for i, st in enumerate(marks):
        en = marks[i + 1] if i + 1 < len(marks) else len(text)
        chapter_text = text[st:en]
        # 提取章节标题
        title_match = re.match(r"(第[0-9零一二三四五六七八九十百千两]+章[^\n]*)", chapter_text)
        title = title_match.group(1).strip() if title_match else f"第{i+1}章"
        # 去掉标题行
        body = re.sub(r"^第[0-9零一二三四五六七八九十百千两]+章[^\n]*\n?", "", chapter_text).strip()
        body = clean_text(body)
        chars = han_count(body)
        if chars >= min_chars:
            chapters.append({
                "title": title,
                "text": body,
                "chars": chars,
                "quality": score_quality(body, "narration"),
            })

    # 按质量排序
    chapters.sort(key=lambda x: -x["quality"])

    # 均匀采样（避免选到相邻章节）
    if len(chapters) <= count:
        return chapters
    step = len(chapters) // count
    selected = [chapters[i * step] for i in range(count)]
    return selected

# ============================================================
# 输出
# ============================================================

def create_sample_entry(sample, work_name, author_display):
    """创建样本条目"""
    return {
        "source": author_display,
        "work": os.path.basename(work_name),
        "type": sample["type"],
        "chars": sample["chars"],
        "quality": sample["quality"],
        "text": sample["text"].strip(),
    }

def extract_author_samples(author_key, author_cfg):
    """提取一位作者的所有场景样本"""
    print(f"\n[{author_key}] 开始提取...")
    all_text = ""
    work_names = []

    for rel_path in author_cfg["works"]:
        full_path = os.path.join(PROJECT_ROOT, rel_path)
        if not os.path.exists(full_path):
            print(f"  [skip] 文件不存在: {rel_path}")
            continue
        print(f"  加载: {os.path.basename(rel_path)}")
        text = load_work(rel_path)
        if text:
            all_text += "\n" + clean_text(text)
            work_names.append(rel_path)
        # 限制总字数（避免处理太久）
        if han_count(all_text) > 800000:
            break

    total_chars = han_count(all_text)
    print(f"  总字数: {total_chars}")

    # 按场景类型提取
    scene_types = ["battle", "dialogue", "environment", "psychology"]
    all_samples = {}

    for st in scene_types:
        print(f"  提取 {st} 样本...")
        if st == "dialogue":
            # 对话场景使用专用提取器
            samples = extract_dialogue_samples(
                all_text, SAMPLE_MIN_CHARS, SAMPLE_MAX_CHARS, SAMPLES_PER_TYPE
            )
        else:
            samples = extract_paragraphs_by_type(
                all_text, st, SAMPLE_MIN_CHARS, SAMPLE_MAX_CHARS, SAMPLES_PER_TYPE
            )
        entries = []
        for s in samples:
            # 找来源作品
            work_name = work_names[0] if work_names else ""
            entries.append(create_sample_entry(s, work_name, author_cfg["display_name"]))
        all_samples[st] = entries
        print(f"    {st}: {len(entries)} 段")

    # 整章样本
    print(f"  提取 full_chapter 样本...")
    chapters = extract_full_chapters(all_text, FULL_CHAPTER_SAMPLES, FULL_CHAPTER_MIN_CHARS)
    chapter_entries = []
    for ch in chapters:
        work_name = work_names[0] if work_names else ""
        chapter_entries.append({
            "source": author_cfg["display_name"],
            "work": os.path.basename(work_name),
            "type": "full_chapter",
            "title": ch["title"],
            "chars": ch["chars"],
            "quality": ch["quality"],
            "text": ch["text"],
        })
    all_samples["full_chapter"] = chapter_entries
    print(f"    full_chapter: {len(chapter_entries)} 段")

    return all_samples

def save_samples(author_key, author_cfg, samples):
    """保存样本到 JSON"""
    author_dir = os.path.join(SAMPLES_DIR, author_key)
    os.makedirs(author_dir, exist_ok=True)

    # 保存为按场景分类的 JSON
    for scene_type, entries in samples.items():
        path = os.path.join(author_dir, f"{scene_type}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "author": author_cfg["display_name"],
                "author_key": author_key,
                "scene_type": scene_type,
                "sample_count": len(entries),
                "samples": entries,
            }, f, ensure_ascii=False, indent=2)
        print(f"  保存: {path} ({len(entries)} 段)")

# ============================================================
# 主流程
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Few-shot 样本提取")
    parser.add_argument("--author", help="只提取指定作者")
    args = parser.parse_args()

    os.makedirs(SAMPLES_DIR, exist_ok=True)

    authors = CONFIG
    if args.author:
        if args.author not in CONFIG:
            print(f"未知作者: {args.author}")
            print(f"可选: {', '.join(CONFIG.keys())}")
            return
        authors = {args.author: CONFIG[args.author]}

    summary = {}
    for author_key, author_cfg in authors.items():
        samples = extract_author_samples(author_key, author_cfg)
        save_samples(author_key, author_cfg, samples)

        # 统计
        total = sum(len(v) for v in samples.values())
        summary[author_key] = {
            "display_name": author_cfg["display_name"],
            "total_samples": total,
            "by_type": {k: len(v) for k, v in samples.items()},
        }

    # 保存索引
    index_path = os.path.join(SAMPLES_DIR, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({
            "description": "Few-shot 样本库 — 按场景类型分类的原文样本，供 LLM 上下文学习使用",
            "scene_types": ["battle", "dialogue", "environment", "psychology", "full_chapter"],
            "usage": "生成时按当前场景类型从对应 JSON 中选取 2-3 段原文作为风格锚点注入上下文",
            "authors": summary,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print("  Few-shot 样本提取完成！")
    print(f"  输出目录: {SAMPLES_DIR}")
    print(f"  索引: {index_path}")
    print(f"{'='*60}")
    for k, v in summary.items():
        print(f"  {v['display_name']}: {v['total_samples']} 段 ({v['by_type']})")

if __name__ == "__main__":
    main()
