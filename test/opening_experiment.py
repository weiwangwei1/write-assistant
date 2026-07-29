#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
opening_experiment.py — 开篇优化实验

测试不同开篇版本在 D5（焦距起点）和 D7（专名锚定）上的表现。
"""

import os
import sys
import json
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scene_perception_lint import (
    split_paragraphs, detect_focal_entry, detect_proper_noun_anchoring,
    DimReport,
)


# ============================================================
# 开篇变体定义
# ============================================================

OPENINGS = {
    "v5_original": {
        "text": "大徵在别的位面开了裂缝。征诏令管着裂缝，能拿的都拿。拿的人叫征调者，拿够了叫功勋。",
        "note": "v5 原版：概念先行，无画面",
    },
    "A_画面先行": {
        "text": "城墙根上有一道裂缝，通到别的位面。暗紫色的光从石缝里渗出来，一收一放，像什么东西在呼吸。这道口子大徵开的。大徵是这片天下的朝廷，征诏令管着裂缝，派征调者进去，能拿的都拿。拿够了算功勋，换补给。",
        "note": "画面先行+背景交代+逻辑清晰",
    },
    "B_裂缝画面": {
        "text": "裂缝开在城墙根上。暗紫色的光从石缝里渗出来，一收一放，像什么东西在呼吸。大徵开的这道口子，从别的位面通到这里。征诏令管着裂缝，派征调者进去，能拿的都拿。拿够了算功勋，换补给。",
        "note": "裂缝画面起笔+大徵从别的位面",
    },
    "C_简洁交代": {
        "text": "城墙根上有一道裂缝，通到别的位面。这道裂缝大徵开的，大徵是这片天下的朝廷。征诏令管着裂缝，派征调者进去，能拿的都拿。拿够了算功勋，换补给。",
        "note": "清晰简洁交代背景逻辑",
    },
    "D_原版微调": {
        "text": "大徵在别的位面开了裂缝。大徵是这片天下的朝廷。征诏令管着裂缝，派征调者进去，能拿的都拿。拿够了算功勋，换补给。",
        "note": "保留原版结构+补大徵锚定",
    },
}


# ============================================================
# 实验逻辑
# ============================================================

def test_opening(name: str, text: str) -> dict:
    """对单个开篇运行 D5+D7 检测"""
    # 模拟为单段落文本
    paragraphs = split_paragraphs(text)

    d5 = detect_focal_entry(paragraphs)
    d7 = detect_proper_noun_anchoring(paragraphs)

    return {
        "name": name,
        "text": text,
        "d5_score": round(d5.score, 1),
        "d5_level": d5.stats.get("focal_level", "?"),
        "d5_has_image": d5.stats.get("has_visual_image", False),
        "d5_objects": d5.stats.get("visual_objects", 0),
        "d5_attributes": d5.stats.get("visual_attributes", 0),
        "d5_issues": [{"location": i.location, "diagnosis": i.diagnosis} for i in d5.issues],
        "d7_score": round(d7.score, 1),
        "d7_nouns_found": d7.stats.get("proper_nouns_found", 0),
        "d7_unanchored": d7.stats.get("unanchored_count", 0),
        "d7_anchored": d7.stats.get("anchored_count", 0),
        "d7_nouns": d7.stats.get("nouns_checked", []),
        "d7_issues": [{"location": i.location, "excerpt": i.excerpt, "diagnosis": i.diagnosis} for i in d7.issues],
    }


def run_experiment():
    print()
    print("=" * 90)
    print("  开篇优化实验 — D5 画面检测 + D7 专名锚定")
    print("=" * 90)
    print()

    results = []

    for name, info in OPENINGS.items():
        result = test_opening(name, info["text"])
        result["note"] = info["note"]
        results.append(result)

    # 对比表
    print(f"  {'版本':<16s} {'D5分':>6s} {'层级':<10s} {'画面':>4s} {'物':>3s}{'属':>3s} "
          f"{'D7分':>6s} {'专名':>4s} {'未锚':>4s} {'锚定':>4s} {'说明'}")
    print(f"  {'-'*100}")

    for r in results:
        img_mark = "✓" if r["d5_has_image"] else "✗"
        print(f"  {r['name']:<16s} {r['d5_score']:>6.1f} {r['d5_level']:<10s} "
              f"{img_mark:>4s} {r['d5_objects']:>3d}{r['d5_attributes']:>3d} "
              f"{r['d7_score']:>6.1f} {r['d7_nouns_found']:>4d} {r['d7_unanchored']:>4d} "
              f"{r['d7_anchored']:>4d}  {r['note']}")

    # 详细分析
    print()
    print("-" * 90)
    print("  详细分析")
    print("-" * 90)

    for r in results:
        print(f"\n  ▸ {r['name']}")
        print(f"    文本: {r['text'][:80]}...")
        print(f"    D5: {r['d5_score']}分 | 层级={r['d5_level']} | 画面={'有' if r['d5_has_image'] else '无'}"
              f"（物{r['d5_objects']}+属{r['d5_attributes']}）")
        if r["d5_issues"]:
            for i in r["d5_issues"]:
                print(f"      ⚠ {i['diagnosis']}")
        else:
            print(f"      ✓ 无 D5 问题")

        print(f"    D7: {r['d7_score']}分 | 专名{r['d7_nouns_found']}个 | 未锚定{r['d7_unanchored']}个 | 已锚定{r['d7_anchored']}个")
        print(f"      专名列表: {', '.join(r['d7_nouns'])}")
        if r["d7_issues"]:
            for i in r["d7_issues"]:
                print(f"      ⚠ [{i['excerpt'][:30]}] {i['diagnosis'][:60]}")
        else:
            print(f"      ✓ 全部专名已锚定")

    # 总结
    print()
    print("=" * 90)
    print("  总结")
    print("=" * 90)

    best = max(results, key=lambda r: (r["d5_score"] + r["d7_score"]))
    print(f"\n  最优方案: {best['name']} (D5={best['d5_score']}, D7={best['d7_score']})")
    print(f"  说明: {best['note']}")
    print(f"  文本: {best['text']}")
    print()

    # 各方案对比
    print("  方案对比:")
    for r in results:
        total = r["d5_score"] + r["d7_score"]
        print(f"    {r['name']:<16s} D5+D7={total:>5.1f} | {r['note']}")

    print()
    print("=" * 90)

    return results


def main():
    results = run_experiment()

    # 保存 JSON
    report_path = os.path.join(os.path.dirname(__file__), "practice", "opening_experiment_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  JSON 报告已保存: {report_path}")


if __name__ == "__main__":
    main()
