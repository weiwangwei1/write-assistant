#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
style_trend.py — 文风偏差趋势分析（P0-1 反馈闭环）

读取 memory/style_deviation_log.jsonl（由 style_fingerprint.py check 自动追加），
分析指纹校验的偏差趋势：

1. 连续3章某维度偏差上升  → warning（需关注，可能在漂移）
2. 连续5章某维度超标      → critical（系统性偏差，建议调整阈值/补充 style_card）
3. 输出最近章节的偏差摘要

用法：
  python style_trend.py                    # 分析全部记录
  python style_trend.py --recent 10        # 只看最近10章
  python style_trend.py --json out.json    # 输出 JSON 报告
  python style_trend.py --by-author        # 按基线分组分析

退出码：0=正常  1=有告警（critical）
"""
import json, os, sys, re, argparse
from collections import defaultdict

def load_log(path="memory/style_deviation_log.jsonl"):
    """加载偏差日志，返回记录列表"""
    if not os.path.exists(path):
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records

def chap_num(r):
    """从章节文件名提取数字用于排序"""
    m = re.search(r"\d+", r.get("chapter", ""))
    return int(m.group()) if m else 0

def analyze_group(records):
    """分析一组记录（同一基线）的趋势"""
    if len(records) < 2:
        return {"status": "insufficient", "message": f"仅{len(records)}条记录，需至少2条",
                "alerts": [], "summary": {}}

    # 去重：同一章节多次校验只保留最新一条
    seen = {}
    for r in records:
        seen[r["chapter"]] = r
    records = sorted(seen.values(), key=chap_num)

    alerts = []

    # 收集每个维度的历史序列
    dim_history = defaultdict(list)  # dim -> [(chap, deviation, pass), ...]
    for r in records:
        for d in r.get("dims", []):
            dim_history[d["dim"]].append((r["chapter"], d["deviation"], d["pass"]))

    # 1. 检测连续3章偏差上升
    for dim, history in dim_history.items():
        if len(history) < 3:
            continue
        recent = history[-3:]
        if recent[0][1] < recent[1][1] < recent[2][1]:
            alerts.append({
                "type": "rising_trend",
                "severity": "warning",
                "dim": dim,
                "message": f"维度「{dim}」连续3章偏差上升："
                           f"{recent[0][1]:.3f} -> {recent[1][1]:.3f} -> {recent[2][1]:.3f}",
                "chapters": [r[0] for r in recent],
            })

    # 2. 检测连续5章同一维度超标（系统性偏差）
    for dim, history in dim_history.items():
        if len(history) < 5:
            continue
        recent = history[-5:]
        if all(not r[2] for r in recent):
            alerts.append({
                "type": "systematic_deviation",
                "severity": "critical",
                "dim": dim,
                "message": f"维度「{dim}」连续5章超标——系统性偏差，"
                           f"建议调整阈值或补充 style_card 指导",
                "chapters": [r[0] for r in recent],
            })

    # 3. 最近章节摘要
    latest = records[-1]
    # 计算各维度最近偏差
    dim_latest = {}
    for dim, history in dim_history.items():
        dim_latest[dim] = {
            "deviation": history[-1][1],
            "pass": history[-1][2],
            "trend": "rising" if len(history) >= 2 and history[-1][1] > history[-2][1] else
                     "falling" if len(history) >= 2 and history[-1][1] < history[-2][1] else "stable",
        }

    summary = {
        "latest_chapter": latest["chapter"],
        "latest_status": latest["status"],
        "latest_max_deviation": latest.get("max_deviation", 0),
        "latest_failed_dims": latest.get("failed_dims", []),
        "total_records": len(records),
        "dim_summary": dim_latest,
    }

    status = "critical" if any(a["severity"] == "critical" for a in alerts) else \
             "warning" if alerts else "ok"

    return {"status": status, "summary": summary, "alerts": alerts}


def main():
    ap = argparse.ArgumentParser(description="文风偏差趋势分析（P0-1 反馈闭环）")
    ap.add_argument("--log", default="memory/style_deviation_log.jsonl", help="偏差日志路径")
    ap.add_argument("--recent", type=int, help="只分析最近N章")
    ap.add_argument("--json", help="输出 JSON 报告路径")
    ap.add_argument("--by-author", action="store_true", help="按基线分组分析")
    args = ap.parse_args()

    records = load_log(args.log)
    if not records:
        print("未找到偏差日志，请先运行 style_fingerprint.py check")
        sys.exit(0)

    if args.recent:
        records = records[-args.recent:]

    if args.by_author:
        # 按基线分组
        groups = defaultdict(list)
        for r in records:
            groups[r.get("baseline", "unknown")].append(r)
        results = {}
        overall_status = "ok"
        for baseline, group in sorted(groups.items()):
            results[baseline] = analyze_group(group)
            if results[baseline]["status"] == "critical":
                overall_status = "critical"
            elif results[baseline]["status"] == "warning" and overall_status != "critical":
                overall_status = "warning"
        result = {"status": overall_status, "groups": results}
    else:
        result = analyze_group(records)

    # 打印报告
    if args.by_author:
        print(f"\n{'='*56}")
        print(f"文风偏差趋势报告（按基线分组）：{result['status'].upper()}")
        print(f"{'='*56}")
        for baseline, r in result["groups"].items():
            s = r.get("summary", {})
            print(f"\n--- 基线：{baseline} ---")
            if not s:
                print(f"  {r.get('message', '无数据')}")
                continue
            print(f"  最近章节：{s['latest_chapter']}  状态：{s['latest_status']}  "
                  f"最大偏差：{s['latest_max_deviation']}")
            print(f"  总记录数：{s['total_records']}  最近失败维度：{s['latest_failed_dims'] or '无'}")
            if r["alerts"]:
                for a in r["alerts"]:
                    tag = "[!]" if a["severity"] == "critical" else "[~]"
                    print(f"  {tag} [{a['type']}] {a['message']}")
            else:
                print(f"  [OK] 无告警")
    else:
        s = result["summary"]
        print(f"\n{'='*56}")
        print(f"文风偏差趋势报告：{result['status'].upper()}")
        print(f"  最近章节：{s['latest_chapter']}  状态：{s['latest_status']}  "
              f"最大偏差：{s['latest_max_deviation']}")
        print(f"  总记录数：{s['total_records']}  最近失败维度：{s['latest_failed_dims'] or '无'}")
        print(f"{'='*56}")

        # 各维度趋势表
        if s.get("dim_summary"):
            print(f"\n  各维度最近偏差：")
            print(f"  {'维度':22s} {'偏差':>8s} {'状态':>6s} {'趋势':>8s}")
            print(f"  {'-'*48}")
            for dim, info in sorted(s["dim_summary"].items()):
                mark = "PASS" if info["pass"] else "FAIL"
                trend_icon = {"rising": "↑", "falling": "↓", "stable": "→"}.get(info["trend"], "?")
                print(f"  {dim:22s} {info['deviation']:8.3f} {mark:>6s} {trend_icon:>8s}")

        if result["alerts"]:
            print(f"\n告警（{len(result['alerts'])}条）：")
            for a in result["alerts"]:
                tag = "[!]" if a["severity"] == "critical" else "[~]"
                print(f"  {tag} [{a['type']}] {a['message']}")
                print(f"      涉及章节：{', '.join(a['chapters'])}")
        else:
            print("\n[OK] 无告警——偏差趋势正常")

    if args.json:
        json.dump(result, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n报告已写入：{args.json}")

    has_critical = (args.by_author and result["status"] == "critical") or \
                   (not args.by_author and result["status"] == "critical")
    sys.exit(1 if has_critical else 0)


if __name__ == "__main__":
    main()
