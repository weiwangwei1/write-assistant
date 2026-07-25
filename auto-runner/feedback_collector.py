#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
feedback_collector.py — 反馈→规则回流管线（RC6 解决方案）

解决根因 RC6「反馈不回流」：人工反馈只修当前章，同一错误章章重犯。
本脚本扫描 detail_review JSON 中的过度矫正问题，统计重复模式，
生成规则更新建议，写入 memory/feedback_rules.json 供 chapter-writer 读取。

工作流定位：
  chapter-writer → detail-reviewer（含过度矫正检测 v1.8）→ ... → memory-manager
       ↑                                                                    ↓
       └──────────── feedback_collector（采集+回流）←──────────────────────┘
  下一章 chapter-writer 启动前读取 feedback_rules.json，避免重犯已知模式

用法：
  python auto-runner/feedback_collector.py                     # 扫描并更新 feedback_rules.json
  python auto-runner/feedback_collector.py --threshold 2       # 设置触发阈值（默认2章）
  python auto-runner/feedback_collector.py --report            # 仅输出报告不写文件
  python auto-runner/feedback_collector.py --add-manual        # 交互式追加手动反馈
"""
import json, os, re, sys, argparse
from collections import defaultdict
from datetime import datetime

HANDOFF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "handoff")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory", "feedback_rules.json")

# 过度矫正问题分类（与 detail-reviewer v1.8 第8层对应）
OVERCORRECTION_TYPES = {
    "grammar_residue": {
        "desc": "语法残缺（删功能词导致句子不完整）",
        "guidance": "修 lint 时不得删除语法必需的功能词（了/着/的/地）。语法残缺影响阅读体验，比 lint minor 更严重。正确做法：换用更精确的动词，而非删除功能词。",
        "example_bad": "老灯累（缺了→语法残缺）",
        "example_good": "老灯乏了 / 老灯暗了",
    },
    "metaphor_regression": {
        "desc": "比喻退步（精准比喻被换成平叙）",
        "guidance": "不得删除精准比喻换成平叙。优质比喻有信息增量（温度/状态/张力），平叙没有。如果比喻超限，删陈词比喻，保留精准比喻，接受 lint minor。",
        "example_bad": "「喧嚣拢成一团」替代「像一锅将开未开的水」",
        "example_good": "保留「像一锅将开未开的水」，删其他陈词比喻",
    },
    "dialogue_loss": {
        "desc": "对话失现场感（直接对话转叙述摘要）",
        "guidance": "面对面交锋场景不得将直接对话转成叙述摘要。对话有语气/距离感/节奏，转述是摘要。修对话占比低应增加有信息的直接对话（带引号+动作），而非删减现有对话。",
        "example_bad": "「霍东来问许愿说没有」替代直接对话",
        "example_good": "「没有。」许愿摇头。霍东来盯着他看了半秒。",
    },
    "hack_bypass": {
        "desc": "Hack绕过（同义词替换骗计数器）",
        "guidance": "禁止通过同义词替换骗 lint 计数器（像→如/似，了→已/曾）。lint 看不到了但问题还在，且引入新的 AI 腔。要么删除要么保留并接受 minor。",
        "example_bad": "「像一片旧鳞甲」→「如一片旧鳞甲」（骗比喻计数器）",
        "example_good": "保留「像」字比喻并接受 minor，或删除该比喻",
    },
    "connector_loss": {
        "desc": "连接词缺失（删的/了导致不自然）",
        "guidance": "减少碎段时不得删除的/了等连接词。泛暗光不如泛了层暗光自然。正确做法：用逗号/连词衔接短句成长句。",
        "example_bad": "「泛暗光」/「密一层」",
        "example_good": "「泛了层暗光」/「密了一层」",
    },
    "certainty_drift": {
        "desc": "确定性漂移（角色首次遭遇用确定语气）",
        "guidance": "角色首次遭遇某事物时应用推测语气（像是/似乎/倒像是），确证后才升级为确定语气（就是/分明是）。不得为修 lint 而把所有描写都改成似乎。",
        "example_bad": "「看着就是专门候着谁的」（首次见公会的人，不该用确定语气）",
        "example_good": "「倒像是专门候着谁的」",
    },
    "false_positive": {
        "desc": "规则误报（正则太宽泛导致）",
        "guidance": "此规则存在误报，检测精度已改进。如仍有误报，请在 detail_review 中标注 source=lint_false_positive，触发规则更新。",
        "example_bad": "narrative_dialogue 误匹配「总说」「公道」「知道」",
        "example_good": "改进后用「代词+对话动词」模式，0 误报",
    },
}

def classify_issue(issue_text):
    """根据问题描述自动分类过度矫正类型"""
    text = issue_text
    if any(k in text for k in ["语法", "残缺", "缺了", "缺\"了\"", "不完整", "打字漏"]):
        return "grammar_residue"
    if any(k in text for k in ["比喻", "退步", "平叙", "意象", "将开未开"]):
        return "metaphor_regression"
    if any(k in text for k in ["对话", "现场感", "转述", "叙述摘要", "直接对话"]):
        return "dialogue_loss"
    if any(k in text for k in ["hack", "骗", "替换", "如字", "似字", "如一片", "似一片"]):
        return "hack_bypass"
    if any(k in text for k in ["连接词", "泛暗", "密一", "不自然"]):
        return "connector_loss"
    if any(k in text for k in ["确定", "语气", "就是", "倒像是", "首次", "确定性"]):
        return "certainty_drift"
    if any(k in text for k in ["误报", "误判", "误匹配", "false_positive"]):
        return "false_positive"
    return None


def scan_detail_reviews(handoff_dir):
    """扫描所有 detail_review JSON，提取过度矫正问题"""
    issues = []
    scanned = 0
    for fname in sorted(os.listdir(handoff_dir)):
        if not fname.startswith("detail_review_") or not fname.endswith(".json"):
            continue
        fpath = os.path.join(handoff_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue
        scanned += 1

        chapter_num = data.get("chapter_num", 0)

        # 从 consistency_check.overcorrection_check 提取（v1.8 结构化字段）
        oc_text = data.get("consistency_check", {}).get("overcorrection_check", "")
        if oc_text and isinstance(oc_text, str) and oc_text.strip():
            otype = classify_issue(oc_text)
            if otype:
                issues.append({
                    "chapter": chapter_num,
                    "type": otype,
                    "source": "overcorrection_check",
                    "detail": oc_text[:200],
                    "source_file": fname,
                })

        # 从 sentence_level 中提取与过度矫正相关的问题
        for item in data.get("sentence_level", []):
            issue_text = item.get("issue", "") + " " + item.get("suggestion", "")
            otype = classify_issue(issue_text)
            if otype:
                issues.append({
                    "chapter": chapter_num,
                    "type": otype,
                    "source": "sentence_level",
                    "detail": item.get("issue", "")[:200],
                    "original": item.get("original", "")[:100],
                    "suggestion": item.get("suggestion", "")[:100],
                    "source_file": fname,
                })

    return issues, scanned


def aggregate_patterns(issues, threshold=2):
    """统计问题模式，当同一类型在≥threshold章中出现时触发"""
    by_type = defaultdict(list)
    for iss in issues:
        by_type[iss["type"]].append(iss)

    patterns = []
    for otype, items in by_type.items():
        chapters = set(it["chapter"] for it in items)
        is_active = len(chapters) >= threshold
        type_info = OVERCORRECTION_TYPES.get(otype, {"desc": otype, "guidance": ""})
        patterns.append({
            "type": otype,
            "type_desc": type_info["desc"],
            "chapter_count": len(chapters),
            "chapters": sorted(list(chapters)),
            "total_occurrences": len(items),
            "status": "active" if is_active else "monitoring",
            "writing_guidance": type_info["guidance"],
            "example_bad": type_info.get("example_bad", ""),
            "example_good": type_info.get("example_good", ""),
            "first_seen": min(it["chapter"] for it in items) if items else 0,
            "last_seen": max(it["chapter"] for it in items) if items else 0,
            "samples": [
                {"chapter": it["chapter"], "detail": it.get("detail", "")[:120]}
                for it in items[:3]
            ],
        })

    patterns.sort(key=lambda x: (x["chapter_count"], x["total_occurrences"]), reverse=True)
    return patterns


def merge_with_existing(new_patterns, existing_file):
    """与已有的 feedback_rules.json 合并——保留手动预填充和 resolved 模式"""
    if not os.path.exists(existing_file):
        return new_patterns

    try:
        with open(existing_file, "r", encoding="utf-8") as f:
            existing = json.load(f)
    except (json.JSONDecodeError, IOError):
        return new_patterns

    # 构建已有 patterns 的字典（含 active/monitoring/resolved）
    existing_by_type = {}
    for p in existing.get("active_patterns", []):
        existing_by_type[p["type"]] = p
    for p in existing.get("monitoring_patterns", []):
        existing_by_type[p["type"]] = p
    for p in existing.get("resolved_patterns", []):
        existing_by_type[p["type"]] = p

    new_by_type = {p["type"]: p for p in new_patterns}

    # 合并：新检测到的优先，但保留已有但未检测到的（可能是手动预填充的）
    merged = []
    all_types = set(existing_by_type.keys()) | set(new_by_type.keys())
    for otype in all_types:
        if otype in new_by_type:
            p = new_by_type[otype].copy()
            # 如果之前已标记为 resolved，保持 resolved 状态
            if otype in existing_by_type and existing_by_type[otype].get("status") == "resolved":
                p["status"] = "resolved"
            merged.append(p)
        else:
            # 已有但本次未检测到的：保留原状态（手动预填充或历史记录）
            merged.append(existing_by_type[otype])

    return merged


def generate_feedback_rules(patterns, existing_file=None):
    """生成规则更新建议"""
    if existing_file:
        patterns = merge_with_existing(patterns, existing_file)

    active = [p for p in patterns if p["status"] == "active"]
    monitoring = [p for p in patterns if p["status"] == "monitoring"]
    resolved = [p for p in patterns if p["status"] == "resolved"]

    rules = {
        "schema_version": "1.0",
        "updated_at": datetime.now().isoformat(),
        "description": "反馈→规则回流管线产出：从历史审核中提取的反复出现的过度矫正模式。chapter-writer 写作前必读，避免重犯。",
        "pipeline": "auto-runner/feedback_collector.py",
        "threshold_chapters": 2,
        "summary": {
            "active_count": len(active),
            "monitoring_count": len(monitoring),
            "resolved_count": len(resolved),
        },
        "active_patterns": active,
        "monitoring_patterns": monitoring,
        "resolved_patterns": resolved,
    }
    return rules


def print_report(patterns, scanned):
    """控制台报告"""
    print(f"\n扫描了 {scanned} 个 detail_review 文件")
    active = [p for p in patterns if p["status"] == "active"]
    monitoring = [p for p in patterns if p["status"] == "monitoring"]

    print(f"活跃模式：{len(active)} 个（≥2章重复出现）")
    print(f"监控模式：{len(monitoring)} 个（仅1章出现，持续观察）")

    if active:
        print("\n" + "=" * 60)
        print("活跃过度矫正模式（chapter-writer 必读）")
        print("=" * 60)
        for p in active:
            print(f"\n[{p['type']}] {p['type_desc']}")
            print(f"  出现章节：{p['chapters']}（共{p['chapter_count']}章/{p['total_occurrences']}处）")
            print(f"  写作指导：{p['writing_guidance']}")
            if p.get("example_bad"):
                print(f"  反例：{p['example_bad']}")
            if p.get("example_good"):
                print(f"  正例：{p['example_good']}")
    else:
        print("\n无活跃的过度矫正模式。")


def main():
    parser = argparse.ArgumentParser(description="反馈→规则回流管线（RC6 解决方案）")
    parser.add_argument("--threshold", type=int, default=2, help="触发阈值：同一模式在≥N章中出现才标为active（默认2）")
    parser.add_argument("--json", default=OUTPUT_FILE, help="JSON 输出路径")
    parser.add_argument("--handoff-dir", default=HANDOFF_DIR, help="handoff 目录路径")
    parser.add_argument("--report", action="store_true", help="仅输出报告不写文件")
    args = parser.parse_args()

    # 1. 采集
    issues, scanned = scan_detail_reviews(args.handoff_dir)
    print(f"采集到 {len(issues)} 条过度矫正问题")

    # 2. 分类 + 3. 统计
    patterns = aggregate_patterns(issues, args.threshold)

    # 4. 回流
    rules = generate_feedback_rules(patterns, args.json if not args.report else None)

    # 控制台报告
    print_report(patterns, scanned)

    # 写入 JSON
    if not args.report:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        print(f"\n规则更新建议已写入：{args.json}")
        print(f"chapter-writer 写作前应读取此文件的 active_patterns 字段")


if __name__ == "__main__":
    main()
