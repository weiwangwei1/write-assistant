#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_auditor.py — 修复差异证据生成器（框架升级 F4，v1.0）

定位：lint 修复后、detail-reviewer 审核前运行。对比「lint 修复前快照」（pre_lint）
与修复后版本，产出结构化 diff 证据，供 detail-reviewer 第 8 层（过度矫正检测）
实证判定。

设计原则：本脚本只生成证据，不做判定。
「删了功能词后句子是否语法残缺」「比喻删得对不对」是语义判断，脚本判不了——
硬判只会再造一个"误报→诱导矫正"的钝规则。判定由 detail-reviewer 完成，
本脚本让它从"猜"变成"看 diff 判"。

用法（在项目根目录运行）：
  python fix_auditor.py handoff/pre_lint_ch15.txt output/chapter_015.txt --json handoff/fix_audit_ch15.json
  python fix_auditor.py 修复前.txt 修复后.txt --style yanyujiangnan   # lint 对比加载风格包

退出码：0=证据已生成（无论差异多少——本脚本不是门禁）  2=文件/用法错误
"""
import re, os, sys, json, argparse, difflib
from collections import Counter

import style_lint

QUOTE_CHARS = '“”"「」'
FUNC_WORDS = ["了", "着", "的", "地"]
# 已知 hack 绕过模式的同义词对照（仅供审核员参考，不做判定）
SIMILE_SYNONYMS = ["如", "似", "仿佛", "宛如", "好比"]

def split_sentences(text):
    parts = re.split(r"(?<=[。！？!?])|\n", text)
    out = []
    for p in parts:
        s = p.strip()
        if not s: continue
        if re.match(r"^(第\d+章|字数|—{3,}|-{3,}|={3,}|#)", s): continue
        out.append(s)
    return out

def has_quote(s):
    return any(c in s for c in QUOTE_CHARS)

def func_word_counts(s):
    return {w: s.count(w) for w in FUNC_WORDS}

def audit(pre_text, post_text):
    pre_sents = split_sentences(pre_text)
    post_sents = split_sentences(post_text)
    sm = difflib.SequenceMatcher(a=pre_sents, b=post_sents, autojunk=False)
    simile_changes, func_reductions, dialogue_loss, removed = [], [], [], []

    def compare(old, new, ctx):
        # 比喻变化证据：旧句含"像"字比喻，新句不含
        if style_lint.count_similes(old) and not style_lint.count_similes(new):
            kind = "possible_synonym_swap" if any(w in new for w in SIMILE_SYNONYMS) else "removed"
            simile_changes.append({"kind": kind, "before": old, "after": new, "context": ctx})
        # 功能词减少证据：了/着/的/地 计数下降（语法残缺嫌疑，供审核员读句判断）
        oc, nc = func_word_counts(old), func_word_counts(new)
        reduced = {w: {"before": oc[w], "after": nc[w]} for w in FUNC_WORDS if oc[w] > nc[w]}
        if reduced:
            func_reductions.append({"reduced_words": reduced, "before": old, "after": new, "context": ctx})
        # 对话失现场感证据：旧句带引号，新句引号消失
        if has_quote(old) and not has_quote(new):
            dialogue_loss.append({"before": old, "after": new, "context": ctx})

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("equal", "insert"):
            continue
        if tag == "delete":
            for s in pre_sents[i1:i2]:
                removed.append({"sentence": s,
                                "had_simile": bool(style_lint.count_similes(s)),
                                "had_dialogue": has_quote(s)})
        else:  # replace
            olds, news = pre_sents[i1:i2], post_sents[j1:j2]
            for k in range(max(len(olds), len(news))):
                old = olds[k] if k < len(olds) else ""
                new = news[k] if k < len(news) else ""
                if old and new:
                    compare(old, new, f"replace块[{i1}:{i2}]→[{j1}:{j2}]")
                elif old:
                    removed.append({"sentence": old,
                                    "had_simile": bool(style_lint.count_similes(old)),
                                    "had_dialogue": has_quote(old)})
    return {
        "simile_changes": simile_changes,
        "function_word_reductions": func_reductions,
        "dialogue_loss_candidates": dialogue_loss,
        "removed_sentences": removed,
    }

def lint_diff(pre_path, post_path, style, styles_root):
    """对修复前后两版各跑一次 lint，输出规则计数差（修复了什么/新引入了什么）"""
    cfg = dict(style_lint.DEFAULT_CONFIG)
    disabled, custom_bans = set(), []
    if style:
        ov_path = os.path.join(styles_root, style, "lint_overlay.json")
        if not os.path.exists(ov_path):
            print(f"风格覆盖层不存在：{ov_path}"); sys.exit(2)
        ov = json.load(open(ov_path, encoding="utf-8"))
        cfg.update(ov.get("overrides", {}))
        disabled = set(ov.get("disabled_rules", []))
        custom_bans = ov.get("custom_ban_words", [])

    def run(path):
        ch = style_lint.Chapter(path, open(path, encoding="utf-8-sig", errors="ignore").read())
        issues, _ = style_lint.lint_chapter(ch, cfg, disabled, custom_bans)
        return Counter(i["rule"] for i in issues)

    before, after = run(pre_path), run(post_path)
    increased = {r: {"before": before.get(r, 0), "after": after[r]}
                 for r in after if after[r] > before.get(r, 0)}
    resolved = {r: {"before": before[r], "after": after.get(r, 0)}
                for r in before if before[r] > after.get(r, 0)}
    return {"before": dict(before), "after": dict(after),
            "increased_or_new": increased, "resolved": resolved}

def main():
    ap = argparse.ArgumentParser(description="修复差异证据生成器（只产证据，不做判定）")
    ap.add_argument("pre", help="lint 修复前快照（如 handoff/pre_lint_ch15.txt）")
    ap.add_argument("post", help="修复后版本（如 output/chapter_015.txt）")
    ap.add_argument("--json", help="证据卡 JSON 输出路径")
    ap.add_argument("--style", help="风格包名（lint 对比加载覆盖层）")
    ap.add_argument("--styles-root", default=".trae/skills/writer-styles", help="风格包根目录")
    args = ap.parse_args()

    for p in (args.pre, args.post):
        if not os.path.exists(p):
            print(f"文件不存在：{p}"); sys.exit(2)
    pre_text = open(args.pre, encoding="utf-8-sig", errors="ignore").read()
    post_text = open(args.post, encoding="utf-8-sig", errors="ignore").read()

    evidence = audit(pre_text, post_text)
    ld = lint_diff(args.pre, args.post, args.style, args.styles_root)

    card = {
        "card_type": "fix_audit",
        "from_agent": "fix_auditor(script)",
        "to_agent": "detail-reviewer",
        "note": "本卡只含 diff 证据，不做判定——是否构成过度矫正由 detail-reviewer 第8层判断",
        "pre_ref": args.pre, "post_ref": args.post,
        "summary": {
            "simile_changes": len(evidence["simile_changes"]),
            "function_word_reductions": len(evidence["function_word_reductions"]),
            "dialogue_loss_candidates": len(evidence["dialogue_loss_candidates"]),
            "removed_sentences": len(evidence["removed_sentences"]),
            "lint_issues_before": sum(ld["before"].values()),
            "lint_issues_after": sum(ld["after"].values()),
        },
        "evidence": evidence,
        "lint_diff": ld,
    }

    s = card["summary"]
    print(f"\n{'='*56}\n修复差异证据（非判定，供 detail-reviewer 第8层使用）\n{'='*56}")
    print(f"  比喻变化（旧有'像'新无）：{s['simile_changes']}  |  功能词减少句：{s['function_word_reductions']}")
    print(f"  引号消失句：{s['dialogue_loss_candidates']}  |  整句删除：{s['removed_sentences']}")
    print(f"  lint 问题数：修复前 {s['lint_issues_before']} → 修复后 {s['lint_issues_after']}")
    if ld["increased_or_new"]:
        print(f"  修复后新增/加重的规则：{json.dumps(ld['increased_or_new'], ensure_ascii=False)}")
    for cat, items in (("比喻变化", evidence["simile_changes"]),
                       ("功能词减少", evidence["function_word_reductions"]),
                       ("引号消失", evidence["dialogue_loss_candidates"])):
        for it in items[:10]:
            print(f"\n  [{cat}]")
            print(f"    前：{it['before'][:60]}")
            print(f"    后：{it['after'][:60]}")

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        json.dump(card, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n证据卡已写入：{args.json}")
    sys.exit(0)

if __name__ == "__main__":
    main()
