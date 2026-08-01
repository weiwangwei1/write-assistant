#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_fix.py — 场景级对比修正工具（轻量 DPO 替代）

将生成段落与同场景类型的原文样本逐维度对比，找出偏差最大的维度，输出修正建议。

用法：
  cd d:\\personFile\\write-assist\\write-assistant
  python test/style_lab/compare_fix.py output/chapter_001.txt --author yanyujiangnan --scene battle
  python test/style_lab/compare_fix.py my_draft.txt --author yanyujiangnan --scene dialogue --json report.json
"""

import os, sys, re, json, math, argparse
from collections import Counter

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from style_fingerprint import (
    split_sents, split_paras, han_count,
    SENSORY_WORDS, FUNC_WORDS, CONJ_STARTERS,
    count_metaphors, dialogue_char_count, count_dash,
    extract_sensory_dist, sensory_cosine_dist, cosine_dist,
)

# 心理词表（本地定义，style_fingerprint 中无此变量）
PSYCH_WORDS = ("想", "觉得", "感到", "知道", "认为", "意识", "心中", "内心", "思绪",
               "记忆", "回忆", "忘记", "明白", "理解", "恐惧", "不安", "犹豫", "怀疑",
               "愤怒", "悲伤", "孤独", "渴望", "嫉妒", "悔恨", "无奈", "释然")

LAB_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(LAB_DIR, "few_shot_samples")

# ============================================================
# 特征提取（简化版——用于单段文本）
# ============================================================

def extract_segment_features(text):
    """提取段落级特征用于对比"""
    paras = split_paras(text)
    body = "\n".join(paras)
    total = max(1, han_count(body))
    sents = split_sents(body)
    sent_lens = [han_count(s) for s in sents]

    if not sent_lens:
        return None

    n = max(1, len(sents))
    mean_len = sum(sent_lens) / n
    var = sum((l - mean_len)**2 for l in sent_lens) / n
    stdev = math.sqrt(var)

    # 句长分布
    short_ratio = sum(1 for l in sent_lens if l <= 8) / n
    long_ratio = sum(1 for l in sent_lens if l > 40) / n

    # 段落
    para_lens = [han_count(p) for p in paras]
    pn = max(1, len(paras))
    para_mean = sum(para_lens) / pn
    single_sent = sum(1 for p in paras if p.count("。") + p.count("！") + p.count("？") <= 1) / pn

    # 对话
    dial_ratio = dialogue_char_count(body) / total

    # 感官
    sensory = extract_sensory_dist(body, total)
    sensory_total = sum(sensory.values()) or 1
    sensory_pct = {k: round(v / sensory_total * 100, 1) for k, v in sensory.items()}

    # 比喻
    metaphor_cnt = count_metaphors(body)
    metaphor_density = round(metaphor_cnt / total * 1000, 3)

    # 标点
    comma = body.count("，") + body.count(",")
    period = body.count("。")
    comma_period = round(comma / max(1, period), 3)
    dash = round(count_dash(body) / total * 1000, 3)
    ellipsis = round(body.count("……") / total * 1000, 3)

    # 连词起句
    conj_starters = sum(1 for p in paras if p.startswith(CONJ_STARTERS))
    conj_ratio = conj_starters / pn

    # 引前引导
    dial_guides = len(re.findall(r"(?:道|说|问|答)\s*[:：]\s*[""「]", body))
    guide_density = round(dial_guides / total * 1000, 3)

    # 了字收尾
    le_endings = sum(1 for s, l in zip(sents, sent_lens) if 0 < l <= 15 and s.rstrip().endswith("了"))
    le_ratio = le_endings / n

    # 心理词密度
    psych_count = sum(body.count(w) for w in PSYCH_WORDS)
    psych_density = round(psych_count / total * 1000, 3)

    # 动作词密度
    action_chars = set("走跑跳冲撞劈砍刺射踢打抓握推拉转身倒摔倒爬起立坐蹲站停飞扑闪避格挡挥抬迈跨踏")
    action_count = sum(1 for c in body if c in action_chars)
    action_density = round(action_count / total * 1000, 3)

    return {
        "sent_len_mean": round(mean_len, 2),
        "sent_len_stdev": round(stdev, 2),
        "short_sent_ratio": round(short_ratio, 4),
        "long_sent_ratio": round(long_ratio, 4),
        "para_len_mean": round(para_mean, 2),
        "single_sent_ratio": round(single_sent, 4),
        "dialogue_ratio": round(dial_ratio, 4),
        "sensory_pct": sensory_pct,
        "metaphor_per_1000": metaphor_density,
        "comma_period_ratio": comma_period,
        "dash_per_1000": dash,
        "ellipsis_per_1000": ellipsis,
        "conjunction_starter_ratio": round(conj_ratio, 4),
        "dialogue_guide_per_1000": guide_density,
        "le_ending_ratio": round(le_ratio, 4),
        "psych_density": psych_density,
        "action_density": action_density,
        "total_chars": total,
        "total_sents": n,
        "total_paras": pn,
    }

# ============================================================
# 对比分析
# ============================================================

# 对比维度定义（名称、标签、方向：higher=偏高好还是偏低好、权重）
COMPARE_DIMS = [
    ("sent_len_mean", "平均句长", "higher", 1.0),
    ("short_sent_ratio", "短句占比", "lower", 0.8),
    ("long_sent_ratio", "长句占比", "higher", 0.8),
    ("para_len_mean", "平均段长", "neutral", 0.6),
    ("single_sent_ratio", "单句段占比", "lower", 0.7),
    ("dialogue_ratio", "对话占比", "neutral", 0.6),
    ("metaphor_per_1000", "比喻密度", "neutral", 0.7),
    ("comma_period_ratio", "逗句比", "neutral", 0.5),
    ("dash_per_1000", "破折号密度", "neutral", 0.4),
    ("ellipsis_per_1000", "省略号密度", "neutral", 0.4),
    ("conjunction_starter_ratio", "连词起句率", "higher", 0.8),
    ("dialogue_guide_per_1000", "引前引导密度", "higher", 0.7),
    ("le_ending_ratio", "了字收尾率", "lower", 0.8),
    ("psych_density", "心理词密度", "lower", 0.6),
    ("action_density", "动作词密度", "neutral", 0.5),
]

def compare_features(gen_feats, orig_feats_list):
    """将生成段特征与原文样本特征列表对比"""
    if not orig_feats_list:
        return None

    # 计算原文样本的统计（均值+标准差）
    results = []
    for dim_name, label, direction, weight in COMPARE_DIMS:
        if dim_name not in gen_feats:
            continue

        orig_vals = [f[dim_name] for f in orig_feats_list if dim_name in f]
        if not orig_vals:
            continue

        orig_mean = sum(orig_vals) / len(orig_vals)
        orig_stdev = math.sqrt(sum((v - orig_mean)**2 for v in orig_vals) / len(orig_vals)) if len(orig_vals) > 1 else 0
        gen_val = gen_feats[dim_name]

        # 相对偏差
        denom = max(abs(orig_mean), 0.01)
        rel_dev = abs(gen_val - orig_mean) / denom

        # 偏差方向
        if gen_val > orig_mean:
            dir_label = "偏高"
        elif gen_val < orig_mean:
            dir_label = "偏低"
        else:
            dir_label = "一致"

        # 修正建议
        advice = generate_advice(dim_name, dir_label, gen_val, orig_mean)

        results.append({
            "dim": dim_name,
            "label": label,
            "gen_value": gen_val,
            "orig_mean": round(orig_mean, 4),
            "orig_stdev": round(orig_stdev, 4),
            "rel_deviation": round(rel_dev, 4),
            "direction": dir_label,
            "weight": weight,
            "weighted_deviation": round(rel_dev * weight, 4),
            "advice": advice,
            "in_range": abs(gen_val - orig_mean) <= max(orig_stdev * 1.5, denom * 0.2),
        })

    # 按加权偏差排序
    results.sort(key=lambda x: -x["weighted_deviation"])

    # 感官通道对比
    sensory_compare = None
    if "sensory_pct" in gen_feats:
        orig_sensory = [f.get("sensory_pct", {}) for f in orig_feats_list]
        sensory_compare = compare_sensory(gen_feats["sensory_pct"], orig_sensory)

    return {
        "dim_results": results,
        "sensory_compare": sensory_compare,
        "worst_dims": [r["dim"] for r in results[:3] if not r["in_range"]],
    }

def compare_sensory(gen_sensory, orig_sensory_list):
    """感官通道对比"""
    channels = ["视觉", "听觉", "嗅觉", "触觉", "味觉"]
    results = []
    for ch in channels:
        gen_v = gen_sensory.get(ch, 0)
        orig_vals = [s.get(ch, 0) for s in orig_sensory_list]
        orig_mean = sum(orig_vals) / max(1, len(orig_vals))
        dev = abs(gen_v - orig_mean) / max(1, orig_mean)
        results.append({
            "channel": ch,
            "gen_pct": gen_v,
            "orig_mean_pct": round(orig_mean, 1),
            "deviation": round(dev, 3),
        })
    results.sort(key=lambda x: -x["deviation"])
    return results

def generate_advice(dim_name, direction, gen_val, orig_mean):
    """生成修正建议"""
    advice_map = {
        "sent_len_mean": {
            "偏高": "句子过长，拆长句为短句+中句交替。检查是否有超长复合句需断开",
            "偏低": "句子偏短偏碎，用逗号串联分句形成流动长句。段首用连词起段",
        },
        "short_sent_ratio": {
            "偏高": "碎短句过多（原作短句是稀缺武器）。合并为复合长句，一章1-2次重锤即可",
            "偏低": "可适当增加短句作为节奏重锤，但不要超过原作比例",
        },
        "long_sent_ratio": {
            "偏高": "长句过多，需用短句断句制造节奏对比",
            "偏低": "长句不足，用书面连词串联分句形成绵长复合句铺陈",
        },
        "single_sent_ratio": {
            "偏高": "单句段过多，合并碎段为两句段",
            "偏低": "可适当增加单句段作为节奏重锤",
        },
        "dialogue_ratio": {
            "偏高": "对话占比过高，减少对话增加叙述铺陈",
            "偏低": "对话不足，增加角色互动。穿插引前引导保持对话现场感",
        },
        "metaphor_per_1000": {
            "偏高": "比喻过密（装饰性比喻是AI腔最露骨签名）。每个比喻先答'删掉读者失去什么'",
            "偏低": "可适当增加比喻，喻体取自故事世界本身",
        },
        "comma_period_ratio": {
            "偏高": "逗号过多，增加句号断句提升力度",
            "偏低": "句号过多偏碎，用逗号串联分句增加流动感",
        },
        "conjunction_starter_ratio": {
            "偏高": "连词起段过多，适当减少",
            "偏低": "段首连词不足。用'不过/然而/虽然'起段是长句风格的黏合剂",
        },
        "dialogue_guide_per_1000": {
            "偏高": "引前引导过多，适当增加裸对话",
            "偏低": "引前引导不足。增加'某某道：'引导保持对话现场感",
        },
        "le_ending_ratio": {
            "偏高": "'了'字收尾短句过多（典型AI腔）。改为连词衔接的流动句",
            "偏低": "可适当增加'了'字收尾作为语气标记",
        },
        "psych_density": {
            "偏高": "心理词过多（'想/觉得/感到'），改为行为暗示。演出来，别说出来",
            "偏低": "可适当增加心理描写，但保持克制",
        },
        "action_density": {
            "偏高": "动作词密度过高，检查是否有动作堆砌缺少结果",
            "偏低": "动作感不足，增加具体身体动作",
        },
        "dash_per_1000": {
            "偏高": "破折号过多（原作近乎为零）。用逗号/句号替代",
            "偏低": "可适当使用破折号做插入/转折",
        },
        "ellipsis_per_1000": {
            "偏高": "省略号过多，用动作节拍替代",
            "偏低": "可适当使用省略号做悬念/余韵",
        },
        "para_len_mean": {
            "偏高": "段落过长，拆分为中短段",
            "偏低": "段落偏碎，合并碎段",
        },
    }
    return advice_map.get(dim_name, {}).get(direction, f"{direction}，按原作方向调整")

# ============================================================
# Few-shot 样本加载
# ============================================================

def load_samples(author, scene_type):
    """加载指定作者和场景类型的原文样本"""
    path = os.path.join(SAMPLES_DIR, author, f"{scene_type}.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("samples", [])

def auto_detect_scene(text):
    """自动检测文本的主要场景类型"""
    paras = split_paras(text)
    body = "\n".join(paras)
    total = max(1, han_count(body))

    # 对话占比
    dial_ratio = dialogue_char_count(body) / total
    # 动作词密度
    action_chars = set("走跑跳冲撞劈砍刺射踢打抓握推拉转身倒摔倒爬起立坐蹲站停飞扑闪避格挡挥抬迈跨踏")
    action_count = sum(1 for c in body if c in action_chars)
    action_density = action_count / total
    # 感官密度
    sensory_count = sum(body.count(w) for words in SENSORY_WORDS.values() for w in words)
    sensory_density = sensory_count / total
    # 心理词密度
    psych_count = sum(body.count(w) for w in PSYCH_WORDS)
    psych_density = psych_count / total

    scores = {
        "battle": action_density * 50,
        "dialogue": dial_ratio * 3,
        "environment": sensory_density * 40,
        "psychology": psych_density * 60,
    }
    best = max(scores, key=scores.get)
    return best, scores

# ============================================================
# 主流程
# ============================================================

def run_compare(text, author, scene_type, json_output=None):
    """运行对比分析"""
    # 自动检测场景类型
    if not scene_type or scene_type == "auto":
        scene_type, scores = auto_detect_scene(text)
        print(f"自动检测场景类型: {scene_type}")
        print(f"场景得分: {scores}")
    else:
        print(f"指定场景类型: {scene_type}")

    # 提取生成段特征
    print(f"\n提取生成段特征...")
    gen_feats = extract_segment_features(text)
    if not gen_feats:
        print("错误：无法提取特征（文本太短或为空）")
        return

    print(f"  字数: {gen_feats['total_chars']}, 句数: {gen_feats['total_sents']}, 段数: {gen_feats['total_paras']}")

    # 加载原文样本
    print(f"\n加载 {author} 的 {scene_type} 原文样本...")
    samples = load_samples(author, scene_type)
    if not samples:
        print(f"错误：未找到 {author}/{scene_type}.json 样本文件")
        print(f"请先运行: python test/style_lab/few_shot_extractor.py --author {author}")
        return

    print(f"  加载 {len(samples)} 段原文样本")

    # 提取原文样本特征
    print(f"\n提取原文样本特征...")
    orig_feats_list = []
    for s in samples:
        feats = extract_segment_features(s["text"])
        if feats:
            orig_feats_list.append(feats)
    print(f"  成功提取 {len(orig_feats_list)} 段原文特征")

    # 对比
    print(f"\n{'='*60}")
    print(f"  对比分析结果")
    print(f"{'='*60}")

    result = compare_features(gen_feats, orig_feats_list)
    if not result:
        print("错误：对比失败")
        return

    # 打印结果
    print(f"\n场景类型: {scene_type} | 对比原文: {len(orig_feats_list)} 段")
    print(f"\n{'维度':<25} {'生成值':>10} {'原文均值':>10} {'偏差':>8} {'方向':>6} {'状态':>6}")
    print("-" * 75)
    for r in result["dim_results"]:
        status = "✓" if r["in_range"] else "✗"
        print(f"{r['label']:<25} {r['gen_value']:>10} {r['orig_mean']:>10} {r['rel_deviation']:>8.2%} {r['direction']:>6} {status:>6}")

    # 感官通道对比
    if result["sensory_compare"]:
        print(f"\n感官通道对比:")
        print(f"{'通道':<8} {'生成%':>8} {'原文%':>8} {'偏差':>8}")
        print("-" * 35)
        for s in result["sensory_compare"]:
            print(f"{s['channel']:<8} {s['gen_pct']:>8.1f} {s['orig_mean_pct']:>8.1f} {s['deviation']:>8.2%}")

    # 修正建议
    worst = result["worst_dims"]
    if worst:
        print(f"\n{'='*60}")
        print(f"  优先修正建议（偏差最大的3个维度）")
        print(f"{'='*60}")
        for r in result["dim_results"][:3]:
            if not r["in_range"]:
                print(f"\n● {r['label']} ({r['direction']})")
                print(f"  生成值: {r['gen_value']} | 原文均值: {r['orig_mean']} | 偏差: {r['rel_deviation']:.2%}")
                print(f"  建议: {r['advice']}")
    else:
        print(f"\n✓ 所有维度均在原文波动范围内，风格匹配良好！")

    # 保存 JSON
    if json_output:
        output = {
            "scene_type": scene_type,
            "author": author,
            "gen_features": gen_feats,
            "orig_sample_count": len(orig_feats_list),
            "dim_results": result["dim_results"],
            "sensory_compare": result["sensory_compare"],
            "worst_dims": result["worst_dims"],
        }
        with open(json_output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n报告已保存: {json_output}")

    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="场景级对比修正工具")
    parser.add_argument("text_file", help="生成文本文件路径")
    parser.add_argument("--author", default="yanyujiangnan", help="作者名（默认 yanyujiangnan）")
    parser.add_argument("--scene", default="auto",
                        help="场景类型（battle/dialogue/environment/psychology/auto）")
    parser.add_argument("--json", help="输出 JSON 报告路径")
    args = parser.parse_args()

    if not os.path.exists(args.text_file):
        print(f"错误：文件不存在 {args.text_file}")
        sys.exit(1)

    for enc in ("utf-8", "gbk"):
        try:
            with open(args.text_file, "r", encoding=enc) as f:
                text = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    run_compare(text, args.author, args.scene, args.json)
