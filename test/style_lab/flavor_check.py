#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flavor_check.py — 韵味校验工具 v1.0

对指定文本运行 12 维韵味分析，并与烟雨江南原作基线对比。
支持单章分析（部分维度自动降级为 advisory）。

用法：
  cd d:\\personFile\\write-assist\\write-assistant
  python test/style_lab/flavor_check.py 原稿.txt 重写稿.txt --json report.json
  python test/style_lab/flavor_check.py 原稿.txt 重写稿.txt  # 只打印对比
"""

import os, sys, json, math
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flavor_distill import (
    analyze_desolate,        # F1
    analyze_restraint,       # F2
    analyze_violence,        # F3
    analyze_world_texture,   # F4
    analyze_temporal_depth,  # F5
    analyze_imagery_variation, # F6
    analyze_dialogue_undertow, # F7
    analyze_chapter_endings, # F8
    analyze_spatial_depth,   # F9
    analyze_cost_economics,  # F10
    analyze_narrative_breathing, # F11
    analyze_perspective,     # F12
)
from style_fingerprint import han_count

LAB_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(LAB_DIR, "reports")

ANALYZERS = [
    ("F1", "苍凉底色", analyze_desolate, "density_per_1000", "苍凉词/千字", "越高越好", 1.54),
    ("F2", "克制美学", analyze_restraint, "restraint_ratio", "克制比(%)", "越高越好", 99.24),
    ("F3", "暴力重量", analyze_violence, "violence_weight_ratio", "后果/伤口(%)", "越高越好", 303.65),
    ("F4", "世界质感", analyze_world_texture, "material_density_per_1000", "材质词/千字", "越高越好", 3.75),
    ("F5", "时间纵深", analyze_temporal_depth, "object_change_per_1000", "物件变化/千字", "越高越好", 0.02),
    ("F6", "意象变奏", analyze_imagery_variation, None, "意象数×2", "参考", 20),
    ("F7", "对话暗流", analyze_dialogue_undertow, "subtext_density_per_1000", "暗流词/千字", "越高越好", 0.96),
    ("F8", "章末余响", analyze_chapter_endings, "resonance_ratio", "余响型章末(%)", "越高越好", 71.67),
    ("F9", "空间纵深", analyze_spatial_depth, "scale_jump_rate", "镜头切换率(%)", "越高越好", 63.45),
    ("F10", "代价经济学", analyze_cost_economics, "cost_density_per_1000", "代价词/千字", "越高越好", 4.45),
    ("F11", "叙事呼吸", analyze_narrative_breathing, "length_cv", "句长变异系数", "越高越好", 0.544),
    ("F12", "视角策略", analyze_perspective, "bystander_para_ratio", "旁观者段落(%)", "越高越好", 17.59),
]

# 多指标维度（除了主指标外还值得关注的）
EXTRA_METRICS = {
    "F1": [("desolate_para_ratio", "苍凉段落占比%"), ("total_desolate_words", "苍凉词总数")],
    "F2": [("body_reaction_per_1000", "身体反应/千字"), ("emotion_to_world_ratio", "情绪→世界转场%"), ("silence_per_1000", "沉默词/千字")],
    "F3": [("wound_per_1000", "伤口词/千字"), ("consequence_per_1000", "后果词/千字"), ("cost_dispel_per_1000", "代价消解/千字")],
    "F4": [("wear_density_per_1000", "磨损词/千字"), ("economy_density_per_1000", "经济词/千字"), ("object_density_per_1000", "物件/千字")],
    "F7": [("action_beat_ratio", "动作打断%"), ("silence_beat_ratio", "沉默打断%"), ("short_dialogue_ratio", "短对话%"), ("bare_dialogue_ratio", "裸对话%")],
    "F9": [("push_count", "推近次数"), ("pull_count", "拉回次数")],
    "F10": [("price_density_per_1000", "价格词/千字"), ("cost_first_pattern_count", "代价先行次数"), ("kindness_cost_ratio", "善意标价率%")],
    "F11": [("mean_sent_len", "均句长"), ("breath_pattern_density", "呼吸模式/千句"), ("wave_density", "段落波浪%"), ("abrupt_transition_density", "急刹车%")],
}


def load_text(path):
    for enc in ("utf-8", "gbk", "utf-16"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""


def run_analysis(text, label):
    """对文本运行12维分析"""
    results = {}
    total = han_count(text)
    
    for key, name, func, metric_key, metric_label, direction, baseline_val in ANALYZERS:
        try:
            result = func(text)
            results[key] = result
        except Exception as e:
            results[key] = {"error": str(e)}
    
    return results, total


def extract_metric(result, metric_key):
    """从分析结果中提取主指标值"""
    if not metric_key or not isinstance(result, dict):
        return None
    if metric_key in result:
        return result[metric_key]
    return None


def compute_improvement(original_val, rewrite_val, baseline_val, direction):
    """计算改进度"""
    if original_val is None or rewrite_val is None:
        return None, None
    
    # 计算与基线的接近度（0-1，1=完全达到基线水平）
    if baseline_val and baseline_val > 0:
        orig_proximity = min(1.0, original_val / baseline_val) if direction == "越高越好" else min(1.0, baseline_val / max(original_val, 0.01))
        rewrite_proximity = min(1.0, rewrite_val / baseline_val) if direction == "越高越好" else min(1.0, baseline_val / max(rewrite_val, 0.01))
    else:
        orig_proximity = 0
        rewrite_proximity = 0
    
    improvement = rewrite_proximity - orig_proximity
    return orig_proximity, rewrite_proximity


def generate_comparison_report(orig_results, rewrite_results, orig_chars, rewrite_chars, orig_path, rewrite_path):
    """生成对比报告"""
    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "original": {"path": orig_path, "chars": orig_chars},
        "rewrite": {"path": rewrite_path, "chars": rewrite_chars},
        "dimensions": {},
        "summary": {
            "improved": 0,
            "regressed": 0,
            "unchanged": 0,
            "n_a": 0,
        }
    }
    
    for key, name, func, metric_key, metric_label, direction, baseline_val in ANALYZERS:
        orig_data = orig_results.get(key, {})
        rewrite_data = rewrite_results.get(key, {})
        
        orig_val = extract_metric(orig_data, metric_key)
        rewrite_val = extract_metric(rewrite_data, metric_key)
        
        orig_prox, rewrite_prox = compute_improvement(orig_val, rewrite_val, baseline_val, direction)
        
        if orig_prox is not None and rewrite_prox is not None:
            if rewrite_prox > orig_prox + 0.05:
                status = "improved"
                report["summary"]["improved"] += 1
            elif rewrite_prox < orig_prox - 0.05:
                status = "regressed"
                report["summary"]["regressed"] += 1
            else:
                status = "unchanged"
                report["summary"]["unchanged"] += 1
        else:
            status = "n/a"
            report["summary"]["n_a"] += 1
        
        dim_entry = {
            "name": name,
            "metric_label": metric_label,
            "baseline": baseline_val,
            "original": orig_val,
            "rewrite": rewrite_val,
            "orig_proximity": round(orig_prox, 3) if orig_prox is not None else None,
            "rewrite_proximity": round(rewrite_prox, 3) if rewrite_prox is not None else None,
            "improvement": round(rewrite_prox - orig_prox, 3) if orig_prox is not None and rewrite_prox is not None else None,
            "status": status,
            "direction": direction,
        }
        
        # 额外指标
        extra = []
        for ek, el in EXTRA_METRICS.get(key, []):
            ov = orig_data.get(ek) if isinstance(orig_data, dict) else None
            rv = rewrite_data.get(ek) if isinstance(rewrite_data, dict) else None
            if ov is not None or rv is not None:
                extra.append({"label": el, "original": ov, "rewrite": rv})
        if extra:
            dim_entry["extra_metrics"] = extra
        
        # observation
        dim_entry["orig_observation"] = orig_data.get("observation", "") if isinstance(orig_data, dict) else ""
        dim_entry["rewrite_observation"] = rewrite_data.get("observation", "") if isinstance(rewrite_data, dict) else ""
        
        report["dimensions"][key] = dim_entry
    
    return report


def print_report(report):
    """打印可读的对比报告"""
    print("\n" + "=" * 80)
    print("  韵味校验报告 — 原稿 vs 重写稿 vs 烟雨江南基线")
    print("=" * 80)
    
    orig = report["original"]
    rewrite = report["rewrite"]
    print(f"\n  原稿:   {os.path.basename(orig['path'])} ({orig['chars']} 字)")
    print(f"  重写稿: {os.path.basename(rewrite['path'])} ({rewrite['chars']} 字)")
    
    s = report["summary"]
    print(f"\n  总览: ↑{s['improved']}改进  ↓{s['regressed']}退步  ={s['unchanged']}持平  -{s['n_a']}不适用")
    
    print("\n" + "-" * 80)
    print(f"  {'维度':<8} {'指标':<16} {'基线':>8} {'原稿':>8} {'重写':>8} {'原稿接近度':>10} {'重写接近度':>10} {'改进':>8} {'状态':<6}")
    print("-" * 80)
    
    for key, name, func, metric_key, metric_label, direction, baseline_val in ANALYZERS:
        d = report["dimensions"].get(key, {})
        
        baseline_str = f"{baseline_val}" if baseline_val is not None else "-"
        orig_val = d.get("original")
        rewrite_val = d.get("rewrite")
        orig_str = f"{orig_val:.2f}" if isinstance(orig_val, (int, float)) else "-"
        rewrite_str = f"{rewrite_val:.2f}" if isinstance(rewrite_val, (int, float)) else "-"
        orig_prox = d.get("orig_proximity")
        rewrite_prox = d.get("rewrite_proximity")
        orig_prox_str = f"{orig_prox:.1%}" if orig_prox is not None else "-"
        rewrite_prox_str = f"{rewrite_prox:.1%}" if rewrite_prox is not None else "-"
        improvement = d.get("improvement")
        if improvement is not None:
            imp_str = f"{improvement:+.1%}"
        else:
            imp_str = "-"
        
        status = d.get("status", "n/a")
        status_icon = {"improved": "↑", "regressed": "↓", "unchanged": "=", "n/a": "-"}.get(status, "-")
        
        print(f"  {key:<8} {name:<16} {baseline_str:>8} {orig_str:>8} {rewrite_str:>8} {orig_prox_str:>10} {rewrite_prox_str:>10} {imp_str:>8} {status_icon:<6}")
    
    print("-" * 80)
    
    # 打印额外指标
    print("\n  详细指标对比:")
    for key, name, func, metric_key, metric_label, direction, baseline_val in ANALYZERS:
        d = report["dimensions"].get(key, {})
        extra = d.get("extra_metrics", [])
        if extra:
            print(f"\n  [{key}] {name}:")
            for em in extra:
                ov = em["original"]
                rv = em["rewrite"]
                ov_str = f"{ov:.2f}" if isinstance(ov, (int, float)) else str(ov) if ov is not None else "-"
                rv_str = f"{rv:.2f}" if isinstance(rv, (int, float)) else str(rv) if rv is not None else "-"
                print(f"    {em['label']:<20} 原稿:{ov_str:>10}  重写:{rv_str:>10}")
    
    # 打印 observation
    print("\n" + "=" * 80)
    print("  维度观察（重写稿）:")
    print("=" * 80)
    for key, name, func, metric_key, metric_label, direction, baseline_val in ANALYZERS:
        d = report["dimensions"].get(key, {})
        obs = d.get("rewrite_observation", "")
        if obs:
            print(f"\n  [{key}] {name}")
            print(f"  {obs[:200]}")
    
    print("\n" + "=" * 80)
    print("  校验完成！")
    print("=" * 80)


def main():
    if len(sys.argv) < 3:
        print("用法: python flavor_check.py 原稿.txt 重写稿.txt [--json report.json] [--html report.html]")
        sys.exit(1)
    
    orig_path = sys.argv[1]
    rewrite_path = sys.argv[2]
    
    json_out = None
    html_out = None
    if "--json" in sys.argv:
        idx = sys.argv.index("--json")
        json_out = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
    if "--html" in sys.argv:
        idx = sys.argv.index("--html")
        html_out = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
    
    print(f"加载原稿: {orig_path}")
    orig_text = load_text(orig_path)
    orig_chars = han_count(orig_text)
    print(f"  字数: {orig_chars}")
    
    print(f"加载重写稿: {rewrite_path}")
    rewrite_text = load_text(rewrite_path)
    rewrite_chars = han_count(rewrite_text)
    print(f"  字数: {rewrite_chars}")
    
    print("\n运行12维分析（原稿）...")
    orig_results, _ = run_analysis(orig_text, "原稿")
    
    print("运行12维分析（重写稿）...")
    rewrite_results, _ = run_analysis(rewrite_text, "重写稿")
    
    report = generate_comparison_report(orig_results, rewrite_results, orig_chars, rewrite_chars, orig_path, rewrite_path)
    
    print_report(report)
    
    if json_out:
        os.makedirs(os.path.dirname(json_out) or ".", exist_ok=True)
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 报告: {json_out}")


if __name__ == "__main__":
    main()
