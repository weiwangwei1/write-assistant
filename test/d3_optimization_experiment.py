#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
d3_optimization_experiment.py — D3 空间失锚检测器优化实验

问题背景：
  1. "手边"是有效空间表达但不被识别 → 误判为 drift
  2. prev_has_anchor 阈值≥2 太严格 → 单个明确锚点"靠着墙"不算基线
  3. 仅检查前1段 → 空间基线建立后隔1段就失效

改进方案：
  A. 双层锚点系统：STRONG(1.0) + WEAK(0.5)
  B. 前段基线阈值降低：≥1 即视为有基线
  C. 前段回溯窗口扩大：检查前2段（带衰减）
  D. 锚点-动作比检测：action多但anchor少时也预警

实验流程：
  1. 对三章 v5/v6 运行当前 D3 检测
  2. 对三章 v5/v6 运行改进 D3 检测
  3. 对比结果差异
"""

import re
import os
import sys
import json
from typing import List, Dict, Tuple
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scene_perception_lint import (
    load_text, split_paragraphs, count_chars, ACTION_VERBS,
    DimReport, Issue, SPATIAL_ANCHORS,
)


# ============================================================
# 当前 D3 检测（复制自 scene_perception_lint.py v1.1）
# ============================================================

def detect_spatial_drift_v1(paragraphs: List[str]) -> DimReport:
    """v1.1 当前版本"""
    issues = []
    drift_count = 0
    details = []

    for idx, para in enumerate(paragraphs):
        action_count = sum(para.count(v) for v in ACTION_VERBS)
        if action_count < 3:
            continue

        anchor_count = sum(para.count(a) for a in SPATIAL_ANCHORS)

        prev_has_anchor = False
        if idx > 0:
            prev_anchor = sum(paragraphs[idx-1].count(a) for a in SPATIAL_ANCHORS)
            prev_has_anchor = prev_anchor >= 2

        if anchor_count < 1 and not prev_has_anchor:
            drift_count += 1
            sentences = re.findall(r"[^。！？]*[跳扎劈砍冲退刺挡挥扑射掷推拉抽补转翻][^。！？]*[。！？]", para)
            excerpt = (sentences[0] if sentences else para)[:80]
            issues.append(Issue(
                dim="D3", dim_name="空间失锚", severity="warning",
                location=f"第{idx+1}段",
                excerpt=excerpt + ("..." if len(excerpt) >= 80 else ""),
                diagnosis=f"动作动词={action_count}，空间锚点={anchor_count}，前段基线={'有' if prev_has_anchor else '无'}",
                suggestion="在动作前补充空间基线图"
            ))

        details.append({
            "para": idx + 1,
            "action": action_count,
            "anchor": anchor_count,
            "prev_has": prev_has_anchor,
            "drift": anchor_count < 1 and not prev_has_anchor,
        })

    score = max(0, 100 - drift_count * 20)
    return score, drift_count, issues, details


# ============================================================
# 改进版 D3 检测
# ============================================================

# 双层锚点系统
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

WEAK_ANCHORS = [
    # 模糊但存在的空间表达
    "手边", "身旁", "身边", "附近", "近处", "不远处",
    "一旁", "一侧", "边上", "旁边", "身侧",
]

# 模式匹配：捕捉未列举的空间表达
SPATIAL_PATTERNS = [
    re.compile(r"[\u4e00-\u9fff](?:边|侧|旁)"),           # X边/X侧/X旁
    re.compile(r"(?:离|距)[^。！？]{1,6}步"),              # 离X两步
    re.compile(r"(?:左|右|前|后)(?:侧|方|面)"),             # 左侧/右方/后面
    re.compile(r"[\u4e00-\u9fff]上"),                       # X上（膝上/地上/肩上）
]


def count_anchors_v2(para: str) -> Tuple[float, int, int, int]:
    """v2 锚点计数：返回 (加权分, strong_count, weak_count, pattern_count)"""
    strong = sum(para.count(a) for a in STRONG_ANCHORS)
    weak = sum(para.count(a) for a in WEAK_ANCHORS)
    
    # 模式匹配（去重：已被 strong/weak 匹配的不重复计）
    pattern_hits = 0
    for pat in SPATIAL_PATTERNS:
        matches = pat.findall(para)
        pattern_hits += len(matches)
    
    # 加权：strong=1.0, weak=0.5, pattern=0.3（可能重复，权重低）
    weighted = strong * 1.0 + weak * 0.5 + pattern_hits * 0.3
    return weighted, strong, weak, pattern_hits


def get_prev_context_v2(paragraphs: List[str], idx: int) -> Tuple[float, dict]:
    """v2 前段上下文：检查前2段，带衰减"""
    context_score = 0.0
    details = {}
    
    for lookback in range(1, min(3, idx + 1)):  # 前1段 + 前2段
        prev_para = paragraphs[idx - lookback]
        w, s, wk, p = count_anchors_v2(prev_para)
        # 衰减：前1段×0.5，前2段×0.25
        decay = 0.5 / lookback
        contribution = w * decay
        context_score += contribution
        details[f"prev_{lookback}"] = {
            "weighted": round(w, 2),
            "strong": s, "weak": wk, "pattern": p,
            "contribution": round(contribution, 2),
        }
    
    return context_score, details


def detect_spatial_drift_v2(paragraphs: List[str]) -> tuple:
    """v2 改进版 D3 检测
    
    改进点：
    1. 双层锚点系统（strong=1.0 + weak=0.5 + pattern=0.3）
    2. 前段回溯2段（带衰减 0.5/0.25）
    3. 锚点-动作比检测（anchor/action < 0.25 时预警）
    4. 综合评分：当前段锚点 + 前段上下文
    """
    issues = []
    drift_count = 0
    details = []

    for idx, para in enumerate(paragraphs):
        action_count = sum(para.count(v) for v in ACTION_VERBS)
        if action_count < 3:
            continue

        # v2: 双层锚点计数
        anchor_weighted, strong, weak, pattern = count_anchors_v2(para)
        
        # v2: 前段上下文（回溯2段）
        prev_context, prev_details = get_prev_context_v2(paragraphs, idx)
        
        # v2: 综合空间分 = 当前段 + 前段上下文
        total_spatial = anchor_weighted + prev_context
        
        # v2: 锚点-动作比
        anchor_action_ratio = anchor_weighted / max(action_count, 1)
        
        # v2: drift 判定逻辑
        # 条件1：当前段锚点加权分 < 0.5 且前段上下文 < 0.5 → 严重失锚
        # 条件2：锚点-动作比 < 0.15 且前段上下文 < 0.5 → 动作在虚空中
        is_drift = False
        severity = "warning"
        diagnosis_parts = []
        
        if anchor_weighted < 0.5 and prev_context < 0.5:
            is_drift = True
            diagnosis_parts.append(f"当前段锚点={anchor_weighted:.1f}（strong={strong}/weak={weak}/pattern={pattern}），前段上下文={prev_context:.2f}")
        elif anchor_action_ratio < 0.15 and prev_context < 0.3:
            is_drift = True
            severity = "info"
            diagnosis_parts.append(f"锚点-动作比={anchor_action_ratio:.2f}（{anchor_weighted:.1f}/{action_count}），动作密集但空间稀疏")
        
        if is_drift:
            drift_count += 1
            sentences = re.findall(r"[^。！？]*[跳扎劈砍冲退刺挡挥扑射掷推拉抽补转翻][^。！？]*[。！？]", para)
            excerpt = (sentences[0] if sentences else para)[:80]
            issues.append(Issue(
                dim="D3", dim_name="空间失锚", severity=severity,
                location=f"第{idx+1}段",
                excerpt=excerpt + ("..." if len(excerpt) >= 80 else ""),
                diagnosis="；".join(diagnosis_parts),
                suggestion="在动作前补充空间基线图：谁在哪、距离多远、什么方向"
            ))

        details.append({
            "para": idx + 1,
            "action": action_count,
            "anchor_weighted": round(anchor_weighted, 2),
            "strong": strong,
            "weak": weak,
            "pattern": pattern,
            "prev_context": round(prev_context, 2),
            "total_spatial": round(total_spatial, 2),
            "anchor_action_ratio": round(anchor_action_ratio, 2),
            "drift": is_drift,
            "prev_details": prev_details,
        })

    score = max(0, 100 - drift_count * 20)
    return score, drift_count, issues, details


# ============================================================
# 实验主流程
# ============================================================

def run_comparison():
    """对三章 v5/v6 运行 v1 vs v2 对比"""
    practice_dir = os.path.join(os.path.dirname(__file__), "practice")
    
    test_files = [
        ("Ch1 v5", "chapter_001_v5.txt"),
        ("Ch2 v5", "chapter_002_v5.txt"),
        ("Ch2 v6", "chapter_002_v6.txt"),
        ("Ch3 v5", "chapter_003_v5.txt"),
    ]
    
    print()
    print("=" * 90)
    print("  D3 空间失锚检测器优化对比实验")
    print("  v1.1（当前） vs v2.0（改进：双层锚点+回溯2段+锚点动作比）")
    print("=" * 90)
    
    all_results = {}
    
    for label, filename in test_files:
        filepath = os.path.join(practice_dir, filename)
        if not os.path.exists(filepath):
            print(f"  {label}: 文件不存在，跳过")
            continue
        
        text = load_text(filepath)
        paragraphs = split_paragraphs(text)
        
        # v1 检测
        v1_score, v1_drift, v1_issues, v1_details = detect_spatial_drift_v1(paragraphs)
        
        # v2 检测
        v2_score, v2_drift, v2_issues, v2_details = detect_spatial_drift_v2(paragraphs)
        
        all_results[label] = {
            "v1": {"score": v1_score, "drift_count": v1_drift, "issues": v1_issues, "details": v1_details},
            "v2": {"score": v2_score, "drift_count": v2_drift, "issues": v2_issues, "details": v2_details},
        }
        
        print()
        print(f"  ▸ {label} ({filename})")
        print(f"    {'':20s} {'得分':>6s} {'drift数':>8s} {'差异':>8s}")
        print(f"    {'v1.1 当前版':<20s} {v1_score:>6.1f} {v1_drift:>8d} {'—':>8s}")
        print(f"    {'v2.0 改进版':<20s} {v2_score:>6.1f} {v2_drift:>8d} {v2_drift - v1_drift:>+8d}")
        
        # 打印被检测段落详情
        all_action_paras = [d for d in v2_details if d["action"] >= 3]
        if all_action_paras:
            print(f"    动作密集段详情（v2.0）：")
            print(f"      {'段':>4s} {'act':>4s} {'加权':>6s} {'strong':>7s} {'weak':>5s} {'patt':>5s} {'前段':>6s} {'总计':>6s} {'A/A比':>6s} {'drift':>6s}")
            for d in all_action_paras:
                drift_mark = " ←DRIFT" if d["drift"] else ""
                print(f"      {d['para']:>4d} {d['action']:>4d} {d['anchor_weighted']:>6.2f} "
                      f"{d['strong']:>7d} {d['weak']:>5d} {d['pattern']:>5d} "
                      f"{d['prev_context']:>6.2f} {d['total_spatial']:>6.2f} "
                      f"{d['anchor_action_ratio']:>6.2f} {'YES' if d['drift'] else 'no':>6s}{drift_mark}")
        
        # 打印问题对比
        if v1_issues or v2_issues:
            print(f"    问题对比：")
            if v1_issues:
                for i in v1_issues:
                    print(f"      v1: [{i.location}] {i.excerpt[:50]}...")
                    print(f"           {i.diagnosis}")
            else:
                print(f"      v1: 无问题")
            if v2_issues:
                for i in v2_issues:
                    print(f"      v2: [{i.location}] {i.excerpt[:50]}...")
                    print(f"           {i.diagnosis}")
            else:
                print(f"      v2: 无问题")
        
        # 差异分析
        if v1_drift != v2_drift:
            print(f"    ⚡ 检测结果变化：v1={v1_drift}处 → v2={v2_drift}处")
            if v2_drift < v1_drift:
                print(f"    ✓ v2 减少了 {v1_drift - v2_drift} 处误判")
            else:
                print(f"    ⚠ v2 新增了 {v2_drift - v1_drift} 处检测")
    
    # 总结
    print()
    print("=" * 90)
    print("  优化效果总结")
    print("=" * 90)
    print()
    
    v1_total = sum(r["v1"]["drift_count"] for r in all_results.values())
    v2_total = sum(r["v2"]["drift_count"] for r in all_results.values())
    
    print(f"  v1.1 总检测 drift 数：{v1_total}")
    print(f"  v2.0 总检测 drift 数：{v2_total}")
    print(f"  变化：{v2_total - v1_total:+d}")
    
    if v2_total < v1_total:
        print(f"  ✓ v2.0 减少了 {v1_total - v2_total} 处误判（通过识别弱锚点+前段回溯）")
    elif v2_total == v1_total:
        print(f"  → v2.0 检测数持平，但检测精度提升（双层锚点+锚点动作比）")
    else:
        print(f"  ⚠ v2.0 新增了 {v2_total - v1_total} 处检测（可能更严格）")
    
    print()
    
    # 验证：v6 是否被两个版本都正确处理
    if "Ch2 v6" in all_results:
        v6_v1 = all_results["Ch2 v6"]["v1"]["drift_count"]
        v6_v2 = all_results["Ch2 v6"]["v2"]["drift_count"]
        print(f"  Ch2 v6 验证：v1={v6_v1}处 drift, v2={v6_v2}处 drift")
        if v6_v1 == 0 and v6_v2 == 0:
            print(f"  ✓ 两个版本都正确识别 v6 修复（0处 drift）")
        elif v6_v1 == 0 and v6_v2 > 0:
            print(f"  ⚠ v2.0 对 v6 仍报 drift，可能需要调整阈值")
    
    print()
    print("=" * 90)
    
    return all_results


def main():
    results = run_comparison()
    
    # 保存 JSON 报告
    report_path = os.path.join(os.path.dirname(__file__), "practice", "d3_optimization_report.json")
    report = {}
    for label, data in results.items():
        report[label] = {
            "v1": {
                "score": data["v1"]["score"],
                "drift_count": data["v1"]["drift_count"],
                "issues": [{"location": i.location, "diagnosis": i.diagnosis, "excerpt": i.excerpt} for i in data["v1"]["issues"]],
            },
            "v2": {
                "score": data["v2"]["score"],
                "drift_count": data["v2"]["drift_count"],
                "issues": [{"location": i.location, "diagnosis": i.diagnosis, "excerpt": i.excerpt} for i in data["v2"]["issues"]],
                "details": data["v2"]["details"],
            },
        }
    
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  JSON 报告已保存: {report_path}")


if __name__ == "__main__":
    main()
