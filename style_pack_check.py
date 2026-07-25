#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
style_pack_check.py — 风格包入库验收清单（蒸馏体系改进 D4，v1.0）

风格包定稿登记前必须通过的验收。防止"缺 style_card 即入库""指纹口径过时"
"决策卡纯定性无量化无例句"等半成品流入流水线。

用法：
  python style_pack_check.py --all                    # 验收全部风格包
  python style_pack_check.py --style yanyujiangnan    # 验收单个包

退出码：0=全部通过（允许 WARN）  1=存在 FAIL  2=用法/路径错误

验收项：
  P1 三件套+词库齐全：fingerprint.json / vocabulary.json / lint_overlay.json / style_card.md
  P2 reference/SKILL-full.md 存在（WARN）
  P3 指纹基线：status=ready 且 metric_version=2.0（v2.0 口径+派生容差）；chapter_stats 为空给 WARN
  P4 lint_overlay：JSON 合法；custom_ban_words 每项含 word+reason；缺 rule_level_strategy 给 WARN
  P5 style_card 模板合规：量化指标 ≥5 处、原文例句 ≥3 处、含错误/正确对照（模板见 README）
  P6 README.md 已登记包名（WARN）
"""
import json, os, re, sys, argparse

def check_pack(root, name):
    results = []  # (level, item, detail)
    d = os.path.join(root, name)
    def add(level, item, detail=""):
        results.append((level, item, detail))

    # P1 三件套+词库
    required = ["fingerprint.json", "vocabulary.json", "lint_overlay.json", "style_card.md"]
    missing = [f for f in required if not os.path.isfile(os.path.join(d, f))]
    add("FAIL" if missing else "PASS", "P1 三件套+词库齐全",
        f"缺失: {', '.join(missing)}" if missing else "")

    # P2 完整蒸馏报告
    if os.path.isfile(os.path.join(d, "reference", "SKILL-full.md")):
        add("PASS", "P2 SKILL-full.md")
    else:
        add("WARN", "P2 SKILL-full.md", "缺失（人工查阅/修订不便）")

    # P3 指纹基线
    fp_path = os.path.join(d, "fingerprint.json")
    if os.path.isfile(fp_path):
        try:
            fp = json.load(open(fp_path, encoding="utf-8"))
            if fp.get("status") != "ready":
                add("FAIL", "P3 指纹基线状态", f"status={fp.get('status')}（应为 ready）")
            elif fp.get("metric_version") != "2.0":
                add("FAIL", "P3 指纹口径", f"metric_version={fp.get('metric_version', '1.x')}，需用 style_fingerprint v2.0 重建")
            elif not fp.get("chapter_stats"):
                add("WARN", "P3 章际分布", "chapter_stats 为空（容差为默认经验值，未经章际波动校准）")
            else:
                add("PASS", "P3 指纹基线", f"confidence={fp.get('confidence')}，分组 {fp.get('n_groups')}")
        except Exception as e:
            add("FAIL", "P3 指纹基线", f"JSON 解析失败: {e}")

    # P4 lint 覆盖层
    ov_path = os.path.join(d, "lint_overlay.json")
    if os.path.isfile(ov_path):
        try:
            ov = json.load(open(ov_path, encoding="utf-8"))
            bad = [w for w in ov.get("custom_ban_words", []) if not (w.get("word") and w.get("reason"))]
            if bad:
                add("FAIL", "P4 lint 覆盖层", f"{len(bad)} 条 custom_ban_words 缺 word/reason")
            elif "rule_level_strategy" not in ov:
                add("WARN", "P4 lint 覆盖层", "缺 rule_level_strategy 策略声明")
            else:
                add("PASS", "P4 lint 覆盖层")
        except Exception as e:
            add("FAIL", "P4 lint 覆盖层", f"JSON 解析失败: {e}")

    # P5 style_card 模板合规
    sc_path = os.path.join(d, "style_card.md")
    if os.path.isfile(sc_path):
        text = open(sc_path, encoding="utf-8").read()
        quant = len(re.findall(r"(?:≤|≥|\d+(?:\.\d+)?\s*(?:/千字|%|字|处|个))", text))
        quotes = len(re.findall(r"[「『\"“][^」』\"”\n]{4,60}[」』\"”]", text))
        contrast = bool(re.search(r"❌|✅|错误示范|正确示范|反例|正例", text))
        problems = []
        if quant < 5: problems.append(f"量化指标仅 {quant} 处（<5）")
        if quotes < 3: problems.append(f"原文例句仅 {quotes} 处（<3）")
        if not contrast: problems.append("缺错误/正确对照")
        add("FAIL" if problems else "PASS", "P5 style_card 模板",
            "；".join(problems) if problems else f"量化 {quant} 处 / 例句 {quotes} 处 / 有对照")

    # P6 README 登记
    readme = os.path.join(root, "README.md")
    if os.path.isfile(readme):
        if name not in open(readme, encoding="utf-8").read():
            add("WARN", "P6 README 登记", f"{name} 未在 README.md 登记")
        else:
            add("PASS", "P6 README 登记")
    return results

def main():
    ap = argparse.ArgumentParser(description="风格包入库验收清单（D4）")
    ap.add_argument("--all", action="store_true", help="验收 styles-root 下全部风格包")
    ap.add_argument("--style", help="验收单个风格包")
    ap.add_argument("--styles-root", default=".trae/skills/writer-styles", help="风格包根目录")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    if not os.path.isdir(args.styles_root):
        print(f"风格包根目录不存在：{args.styles_root}"); sys.exit(2)
    if args.all:
        packs = sorted(d for d in os.listdir(args.styles_root)
                       if os.path.isdir(os.path.join(args.styles_root, d)))
    elif args.style:
        packs = [args.style]
    else:
        print("请指定 --all 或 --style <包名>"); sys.exit(2)

    any_fail = False
    for name in packs:
        results = check_pack(args.styles_root, name)
        fails = sum(1 for r in results if r[0] == "FAIL")
        warns = sum(1 for r in results if r[0] == "WARN")
        any_fail = any_fail or fails > 0
        verdict = "FAIL" if fails else ("PASS(warn)" if warns else "PASS")
        print(f"\n{'='*56}\n{name}：{verdict}\n{'='*56}")
        for level, item, detail in results:
            mark = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}[level]
            line = f"  {mark} [{level:4s}] {item}"
            if detail: line += f"——{detail}"
            print(line)
    print(f"\n总结：{'存在 FAIL，禁止入库' if any_fail else '全部通过（WARN 可后续补齐）'}")
    sys.exit(1 if any_fail else 0)

if __name__ == "__main__":
    main()
