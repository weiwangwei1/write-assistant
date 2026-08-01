#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v6_experiment.py — v6 修复实验框架

功能：
1. 对 v5 章节文本应用多种修复策略，生成 v6 变体
2. 对每个变体运行 scene_perception_lint 诊断
3. 横向对比所有变体的六维分数
4. 输出最优策略推荐

用法:
  python v6_experiment.py
  python v6_experiment.py --chapter 2
  python v6_experiment.py --chapter 2 --json experiment_report.json
"""

import json
import os
import re
import sys
import copy
import tempfile
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

# 导入诊断器
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scene_perception_lint import (
    diagnose, split_paragraphs, count_chars,
    detect_info_dump, detect_narrator_translation, detect_spatial_drift,
    detect_sensory_oneoff, detect_focal_entry, detect_world_rotation,
)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class FixStrategy:
    """一个修复策略"""
    name: str
    description: str
    patches: List[Tuple[str, str]]  # (old_str, new_str) 列表


@dataclass
class VariantResult:
    """一个变体的诊断结果"""
    name: str
    description: str
    overall_score: float
    dim_scores: Dict[str, float]
    dim_issues_count: Dict[str, int]
    d3_issues: List[dict]
    text_length: int
    applied_patches: List[str]


# ============================================================
# 修复策略定义
# ============================================================

# Ch2 D3 修复策略：第42段 "老周把干粮往程铖手边推了推"
# 问题：动作动词=3（推×2+补×1），空间锚点=0（"手边"不在锚点词表里）
# 前段（第41段 "程铖没动。"）也没有空间锚点

CH2_D3_STRATEGIES = [
    FixStrategy(
        name="A_手边→身前",
        description="最小改动：将'手边'替换为'身前'，'前'是空间锚点词",
        patches=[
            ("老周把干粮往程铖手边推了推", "老周把干粮往程铖身前推了推"),
        ]
    ),
    FixStrategy(
        name="B_手边→面前",
        description="将'手边'替换为'面前'，'面'+'前'双锚点",
        patches=[
            ("老周把干粮往程铖手边推了推", "老周把干粮往程铖面前推了推"),
        ]
    ),
    FixStrategy(
        name="C_补空间基线",
        description="在第42段前补一句空间基线，建立老周与程铖的位置关系",
        patches=[
            (
                "程铖没动。\n\n\"你三天没吃够。\"",
                "程铖没动。\n\n老周蹲在他左侧，半步远。他把干粮放在两人之间的地上。\n\n\"你三天没吃够。\""
            ),
        ]
    ),
    FixStrategy(
        name="D_重写动作句",
        description="重写第42段，让推干粮的动作自带空间信息",
        patches=[
            (
                "老周把干粮往程铖手边推了推，声音放低了半分。",
                "老周从身侧把干粮推到程铖面前，声音放低了半分。"
            ),
        ]
    ),
    FixStrategy(
        name="E_前段补锚点",
        description="修改前一段（第41段），让'程铖没动'带上空间信息",
        patches=[
            (
                "程铖没动。",
                "程铖靠着墙，没动。"
            ),
        ]
    ),
    FixStrategy(
        name="F_组合方案",
        description="组合：前段补锚点 + 手边→身前",
        patches=[
            (
                "程铖没动。",
                "程铖靠着墙，没动。"
            ),
            (
                "老周把干粮往程铖手边推了推",
                "老周把干粮往程铖身前推了推",
            ),
        ]
    ),
]

# Ch1 D1 优化策略：第7段信息交付段（信息密度=4.0，感官动词=1）
# 该段是程铖翻铜钱的段落，含较多背景信息
CH1_D1_STRATEGIES = [
    FixStrategy(
        name="A_补感官动词",
        description="在信息密集段中增加感官动词，降低信息交付判定",
        patches=[
            (
                "这三枚铜钱跟了他九年，磨得发亮，边角圆了，字迹模糊得像长在手上。",
                "这三枚铜钱跟了他九年，指腹摩过边角，圆了，字迹模糊得像长在手上。"
            ),
        ]
    ),
]


# ============================================================
# 核心逻辑
# ============================================================

def apply_patches(text: str, patches: List[Tuple[str, str]]) -> tuple:
    """应用补丁列表，返回(修改后文本, 成功应用的补丁列表)"""
    result = text
    applied = []
    for old, new in patches:
        if old in result:
            result = result.replace(old, new, 1)
            applied.append(f"✓ {old[:40]}... → {new[:40]}...")
        else:
            applied.append(f"✗ 未找到: {old[:40]}...")
    return result, applied


def run_diagnostic(text: str) -> dict:
    """运行完整诊断，返回结构化结果"""
    paragraphs = split_paragraphs(text)
    
    d1 = detect_info_dump(paragraphs)
    d2 = detect_narrator_translation(paragraphs)
    d3 = detect_spatial_drift(paragraphs)
    d4 = detect_sensory_oneoff(paragraphs)
    d5 = detect_focal_entry(paragraphs)
    d6 = detect_world_rotation(paragraphs)
    
    dimensions = [d1, d2, d3, d4, d5, d6]
    weights = {"D1": 0.20, "D2": 0.20, "D3": 0.15, "D4": 0.15, "D5": 0.15, "D6": 0.15}
    overall = sum(d.score * weights[d.dim] for d in dimensions)
    
    dim_scores = {d.dim: round(d.score, 1) for d in dimensions}
    dim_issues_count = {d.dim: len(d.issues) for d in dimensions}
    
    # 提取 D3 问题详情
    d3_issues = []
    for issue in d3.issues:
        d3_issues.append({
            "location": issue.location,
            "excerpt": issue.excerpt,
            "diagnosis": issue.diagnosis,
        })
    
    return {
        "overall_score": round(overall, 1),
        "dim_scores": dim_scores,
        "dim_issues_count": dim_issues_count,
        "d3_issues": d3_issues,
        "text_length": count_chars(text),
    }


def experiment_chapter(
    chapter_num: int,
    v5_path: str,
    strategies: List[FixStrategy],
) -> List[VariantResult]:
    """对某一章运行所有修复策略实验"""
    with open(v5_path, "r", encoding="utf-8") as f:
        original_text = f.read()
    
    results = []
    
    # 基线：v5 原版
    baseline = run_diagnostic(original_text)
    results.append(VariantResult(
        name="v5_baseline",
        description="v5 原版（无修改）",
        overall_score=baseline["overall_score"],
        dim_scores=baseline["dim_scores"],
        dim_issues_count=baseline["dim_issues_count"],
        d3_issues=baseline["d3_issues"],
        text_length=baseline["text_length"],
        applied_patches=[],
    ))
    
    # 各策略变体
    for strategy in strategies:
        modified_text, applied = apply_patches(original_text, strategy.patches)
        diag = run_diagnostic(modified_text)
        
        results.append(VariantResult(
            name=strategy.name,
            description=strategy.description,
            overall_score=diag["overall_score"],
            dim_scores=diag["dim_scores"],
            dim_issues_count=diag["dim_issues_count"],
            d3_issues=diag["d3_issues"],
            text_length=diag["text_length"],
            applied_patches=applied,
        ))
    
    return results


def save_variant_text(
    v5_path: str,
    strategy: FixStrategy,
    output_path: str,
) -> bool:
    """将应用了某策略的文本保存为文件"""
    with open(v5_path, "r", encoding="utf-8") as f:
        text = f.read()
    
    modified, applied = apply_patches(text, strategy.patches)
    
    # 检查是否所有补丁都成功应用
    failed = [a for a in applied if a.startswith("✗")]
    if failed:
        print(f"  ⚠ 策略 {strategy.name} 有 {len(failed)} 个补丁未匹配:")
        for f in failed:
            print(f"    {f}")
        return False
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(modified)
    return True


def print_experiment_report(chapter_num: int, results: List[VariantResult]):
    """打印实验报告"""
    print()
    print("=" * 78)
    print(f"  v6 修复实验报告 — 第 {chapter_num} 章")
    print("=" * 78)
    print()
    
    # 基线信息
    baseline = results[0]
    print(f"  基线（v5）：总分 {baseline.overall_score} | 字数 {baseline.text_length}")
    print(f"  六维：", end="")
    for dim in ["D1", "D2", "D3", "D4", "D5", "D6"]:
        print(f" {dim}={baseline.dim_scores[dim]}", end="")
    print()
    if baseline.d3_issues:
        print(f"  D3 问题 ({len(baseline.d3_issues)} 处):")
        for issue in baseline.d3_issues:
            print(f"    - {issue['location']}: {issue['excerpt'][:50]}...")
    print()
    print("-" * 78)
    
    # 各策略对比表
    print(f"  {'策略':<20s} {'总分':>6s} {'D1':>6s} {'D2':>6s} {'D3':>6s} {'D4':>6s} {'D5':>6s} {'D6':>6s} {'D3问题':>6s} {'变化':>6s}")
    print(f"  {'-'*90}")
    
    for r in results:
        delta = r.overall_score - baseline.overall_score
        delta_str = f"{delta:+.1f}" if delta != 0 else "—"
        d3_issue_count = len(r.d3_issues)
        marker = " ★" if delta > 0 and d3_issue_count == 0 else ""
        
        print(f"  {r.name:<20s} {r.overall_score:>6.1f} "
              f"{r.dim_scores['D1']:>6.1f} {r.dim_scores['D2']:>6.1f} "
              f"{r.dim_scores['D3']:>6.1f} {r.dim_scores['D4']:>6.1f} "
              f"{r.dim_scores['D5']:>6.1f} {r.dim_scores['D6']:>6.1f} "
              f"{d3_issue_count:>6d} {delta_str:>6s}{marker}")
    
    print()
    print("-" * 78)
    
    # 各策略详情
    for r in results[1:]:  # 跳过基线
        print(f"\n  ▸ {r.name}")
        print(f"    说明: {r.description}")
        print(f"    总分: {r.overall_score} (Δ{r.overall_score - baseline.overall_score:+.1f})")
        print(f"    字数: {r.text_length} (Δ{r.text_length - baseline.text_length:+d})")
        
        # D3 变化
        d3_delta = r.dim_scores["D3"] - baseline.dim_scores["D3"]
        if d3_delta != 0:
            print(f"    D3 变化: {baseline.dim_scores['D3']} → {r.dim_scores['D3']} ({d3_delta:+.1f})")
        
        # 补丁应用情况
        print(f"    补丁:")
        for p in r.applied_patches:
            print(f"      {p}")
        
        # D3 残留
        if r.d3_issues:
            print(f"    D3 残留问题:")
            for issue in r.d3_issues:
                print(f"      - {issue['location']}: {issue['diagnosis']}")
        else:
            if baseline.d3_issues:
                print(f"    D3 问题: ✓ 全部清零")
    
    print()
    print("=" * 78)
    
    # 最优策略推荐
    best = max(results[1:], key=lambda r: (r.overall_score, -len(r.d3_issues)))
    all_d3_cleared = [r for r in results[1:] if len(r.d3_issues) == 0]
    
    print()
    print("  ★ 推荐方案")
    print("-" * 78)
    if all_d3_cleared:
        best_cleared = max(all_d3_cleared, key=lambda r: r.overall_score)
        print(f"  最优策略: {best_cleared.name}")
        print(f"  总分提升: {baseline.overall_score} → {best_cleared.overall_score} (Δ{best_cleared.overall_score - baseline.overall_score:+.1f})")
        print(f"  D3 修复: {baseline.dim_scores['D3']} → {best_cleared.dim_scores['D3']} ✓ 清零")
        print(f"  说明: {best_cleared.description}")
    else:
        print(f"  最高分策略: {best.name} (总分 {best.overall_score})")
        if best.d3_issues:
            print(f"  ⚠ D3 仍有 {len(best.d3_issues)} 处问题未解决")
        else:
            print(f"  D3 已清零")
    
    print()
    print("=" * 78)


def run_all_chapters():
    """运行所有章节的评估"""
    practice_dir = os.path.join(os.path.dirname(__file__), "practice")
    
    print()
    print("=" * 78)
    print("  全章评估快照（v5）")
    print("=" * 78)
    print()
    
    chapters = [
        (1, os.path.join(practice_dir, "chapter_001_v5.txt")),
        (2, os.path.join(practice_dir, "chapter_002_v5.txt")),
        (3, os.path.join(practice_dir, "chapter_003_v5.txt")),
    ]
    
    all_results = {}
    
    for ch_num, ch_path in chapters:
        if not os.path.exists(ch_path):
            print(f"  Ch{ch_num}: 文件不存在 {ch_path}")
            continue
        
        with open(ch_path, "r", encoding="utf-8") as f:
            text = f.read()
        
        diag = run_diagnostic(text)
        all_results[f"ch{ch_num}"] = diag
        
        print(f"  Ch{ch_num} v5: 总分 {diag['overall_score']:>5.1f} | 字数 {diag['text_length']:>5d} | "
              f"D1={diag['dim_scores']['D1']:>5.1f} D2={diag['dim_scores']['D2']:>5.1f} "
              f"D3={diag['dim_scores']['D3']:>5.1f} D4={diag['dim_scores']['D4']:>5.1f} "
              f"D5={diag['dim_scores']['D5']:>5.1f} D6={diag['dim_scores']['D6']:>5.1f}")
        
        # 标记短板
        for dim in ["D1", "D2", "D3", "D4", "D5", "D6"]:
            if diag["dim_scores"][dim] < 100:
                issue_count = diag["dim_issues_count"][dim]
                print(f"         ↳ {dim} 短板: {diag['dim_scores'][dim]}/100 ({issue_count} 处问题)")
    
    print()
    print("=" * 78)
    
    return all_results


# ============================================================
# 主流程
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="v6 修复实验框架")
    parser.add_argument("--chapter", type=int, default=2, help="实验章节号（默认2）")
    parser.add_argument("--json", help="输出 JSON 报告到指定文件")
    parser.add_argument("--save-variant", help="保存最优变体到指定路径")
    parser.add_argument("--all", action="store_true", help="运行全章评估")
    args = parser.parse_args()
    
    # 全章评估
    if args.all:
        run_all_chapters()
        return
    
    practice_dir = os.path.join(os.path.dirname(__file__), "practice")
    v5_path = os.path.join(practice_dir, f"chapter_{args.chapter:03d}_v5.txt")
    
    if not os.path.exists(v5_path):
        print(f"错误：文件不存在 {v5_path}")
        sys.exit(2)
    
    # 选择策略
    if args.chapter == 2:
        strategies = CH2_D3_STRATEGIES
    elif args.chapter == 1:
        strategies = CH1_D1_STRATEGIES
    else:
        print(f"第 {args.chapter} 章暂无预定义策略")
        sys.exit(0)
    
    # 运行实验
    results = experiment_chapter(args.chapter, v5_path, strategies)
    
    # 打印报告
    print_experiment_report(args.chapter, results)
    
    # 保存最优变体
    if args.save_variant:
        all_d3_cleared = [r for r in results[1:] if len(r.d3_issues) == 0]
        if all_d3_cleared:
            best = max(all_d3_cleared, key=lambda r: r.overall_score)
        else:
            best = max(results[1:], key=lambda r: r.overall_score)
        
        # 找到对应策略
        best_strategy = next(s for s in strategies if s.name == best.name)
        success = save_variant_text(v5_path, best_strategy, args.save_variant)
        if success:
            print(f"\n  ✓ 最优变体已保存: {args.save_variant}")
            print(f"    策略: {best.name}")
            print(f"    总分: {best.overall_score}")
    
    # JSON 报告
    if args.json:
        report = {
            "chapter": args.chapter,
            "baseline": {
                "name": results[0].name,
                "overall_score": results[0].overall_score,
                "dim_scores": results[0].dim_scores,
                "d3_issues": results[0].d3_issues,
            },
            "variants": [
                {
                    "name": r.name,
                    "description": r.description,
                    "overall_score": r.overall_score,
                    "dim_scores": r.dim_scores,
                    "d3_issues": r.d3_issues,
                    "text_length": r.text_length,
                    "applied_patches": r.applied_patches,
                }
                for r in results[1:]
            ],
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n  JSON 报告已保存: {args.json}")


if __name__ == "__main__":
    main()
