#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
anchor_check.py — 结构锚点计数视图（只读报告 · 只报证据 · 不阻断）v1.0

用法：
  python anchor_check.py [--outline memory/outline.json] [--unit 10] [--config config/novel_config.json] [--out handoff/anchor_check_report.txt]

定位：与 emotion_curve.py / fix_auditor.py 同级——只产证据、不做判定、退出码恒为 0，不进门禁。
数据源：memory/outline.json 逐章 beats 的 beat_kind 字段（plot-architect v1.7 起标注）：
  · volume_N_chapters 各章 "beats"（本项目为 volume_1_chapters）；
  · Ch1-3 的 beat sheet 在 golden_three_chapters.rework_v2.ch{N}，卷纲条目无 beats 时回退取此处。
门禁口径（B2，只查有无、不查次数）：每个单元（默认 10 章）内 relational≥1、object≥1——
来源：《docs/写作体系优化计划_20261012.md》§四·B2；取值集合：relational/object/rule/worldview/payoff/hook/persona。
报告口径：单元内 beat 全部未标注 → 判"未标注（不可判定）"（与"缺失：已标注但无该拍"分开）；总章数取 config/novel_config.json 的 total_chapters（缺失回退 outline）。
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

KINDS = ("relational", "object", "rule", "worldview", "payoff", "hook", "persona")
REQUIRED = ("relational", "object")
CONFIG_DEFAULT = "config/novel_config.json"


def _reconf():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_beat_kinds(path):
    """返回 (outline_data, {chapter: [beats]})；卷纲优先，黄金三章 rework_v2 兜底。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    beats_by_ch = {}
    vkeys = sorted(
        [k for k in data.keys() if re.fullmatch(r"volume_\d+_chapters", k)],
        key=lambda k: int(re.findall(r"\d+", k)[0]),
    )
    for k in vkeys:
        for c in data.get(k, []):
            if isinstance(c, dict) and "chapter" in c and isinstance(c.get("beats"), list):
                beats_by_ch[c["chapter"]] = c["beats"]
    # Ch1-3 的实际 beat sheet 在 rework_v2（外层旧版 ch1/ch2/ch3 已废弃，不读）
    g3 = (data.get("golden_three_chapters") or {}).get("rework_v2") or {}
    for key, ch_data in g3.items():
        m = re.fullmatch(r"ch(\d+)", key)
        if m and isinstance(ch_data, dict) and isinstance(ch_data.get("beats"), list):
            beats_by_ch.setdefault(int(m.group(1)), ch_data["beats"])
    return data, beats_by_ch


def load_total_chapters(config_path, outline_data):
    """总章数：优先 config/novel_config.json 的 total_chapters，缺失时回退 outline。"""
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                n = json.load(f).get("total_chapters")
            if isinstance(n, int):
                return n
        except Exception:
            pass
    n = outline_data.get("total_chapters")
    return n if isinstance(n, int) else None


def render(title, beats_by_ch, unit, src, total_ch=None):
    out = []
    chs = sorted(beats_by_ch)
    span = f"有 beat 数据的章：{len(chs)}（Ch{chs[0]}-Ch{chs[-1]}）" if chs else "有 beat 数据的章：0"
    out.append(f"《{title}》结构锚点计数视图（只读报告 · 不阻断）")
    out.append(f"生成：{datetime.now().strftime('%Y-%m-%d %H:%M')} · 数据源：{src} · 单元={unit} 章 · {span}")
    out.append(f"门禁口径（B2，只查有无、不查次数）：每单元 relational≥1、object≥1 ｜ 取值：{'/'.join(KINDS)}")
    out.append("")
    if not chs:
        out.append("未找到任何带 beats 的章节（只读视图，exit=0）")
        return "\n".join(out)

    out.append(" 单元    | rel | obj | rule |  wv | pay | hook | pers | 未标注 | 有beat章")
    out.append("---------+-----+-----+------+-----+-----+------+------+--------+---------")
    totals = {k: 0 for k in KINDS}
    n_marked = 0
    n_unmarked = 0
    findings = []
    cur = ((chs[0] - 1) // unit) * unit + 1
    while cur <= chs[-1]:
        end = cur + unit - 1
        counts = {k: 0 for k in KINDS}
        no_kind = 0
        n_ch = 0
        for ch in range(cur, end + 1):
            beats = beats_by_ch.get(ch)
            if beats is None:
                continue
            n_ch += 1
            for b in beats:
                k = b.get("beat_kind") if isinstance(b, dict) else None
                if k in counts:
                    counts[k] += 1
                else:
                    no_kind += 1
        n_total_u = sum(counts.values()) + no_kind
        if n_total_u == 0:
            cur = end + 1
            continue
        for k in KINDS:
            totals[k] += counts[k]
        n_marked += sum(counts.values())
        n_unmarked += no_kind
        label = f"Ch{cur}-{end}"
        out.append(
            f" {label:<7} | {counts['relational']:>3} | {counts['object']:>3} | {counts['rule']:>4} |"
            f" {counts['worldview']:>3} | {counts['payoff']:>3} | {counts['hook']:>4} | {counts['persona']:>4} |"
            f" {no_kind:>6} | {n_ch:>7}"
        )
        miss = [k for k in REQUIRED if counts[k] == 0]
        if miss:
            findings.append((cur, end, miss, no_kind, n_total_u, sum(counts.values())))
        cur = end + 1

    out.append("")
    out.append("— 门禁结果（B2 口径：每单元 relational≥1 且 object≥1；只报证据、不做判定）—")
    if findings:
        for u_cur, u_end, miss, no_kind, n_total_u, n_marked_u in findings:
            if n_marked_u == 0:
                out.append(f"[未标注] Ch{u_cur}-{u_end}：本单元 {n_total_u} 个 beat 均未标注 beat_kind（不可判定；细化该单元时须同步标注）")
            else:
                miss_s = "、".join(miss)
                out.append(f"[缺失] Ch{u_cur}-{u_end}：无 {miss_s} 拍（本单元 {n_total_u} 个 beat，其中 {no_kind} 个未标注 beat_kind）")
    else:
        out.append("[通过] 全单元 relational≥1 且 object≥1")
    out.append("")
    out.append(
        f"— 统计 — 已标注 beat：{n_marked}（relational {totals['relational']} · object {totals['object']}）；"
        f"未标注 beat：{n_unmarked}；共 {len(chs)} 章有 beat 数据"
    )
    if isinstance(total_ch, int) and chs[-1] < total_ch:
        out.append(f"注：Ch{chs[-1] + 1}-{total_ch} 尚未生成逐章 beat（滚动生成），不在本次统计范围。")
    out.append("注：本报告只产证据（同 fix_auditor 定位），是否处理由评审/作者裁量；退出码恒为 0。")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="大纲结构锚点计数视图（只读报告，不阻断）")
    ap.add_argument("--outline", default="memory/outline.json")
    ap.add_argument("--unit", type=int, default=10, help="单元大小（默认 10 章）")
    ap.add_argument("--config", default=CONFIG_DEFAULT, help="总章数配置源（默认 config/novel_config.json）")
    ap.add_argument("--out", default="handoff/anchor_check_report.txt")
    args = ap.parse_args()
    _reconf()
    if not os.path.exists(args.outline):
        print(f"[anchor_check] 未找到大纲文件：{args.outline}（只读视图，退出码 0）")
        return 0
    data, beats_by_ch = load_beat_kinds(args.outline)
    total_ch = load_total_chapters(args.config, data)
    report = render(data.get("title", "（未命名）"), beats_by_ch, args.unit, args.outline, total_ch)
    print(report)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print(f"\n[anchor_check] 报告已写入：{args.out}（只报证据，不阻断；exit=0）")
    return 0


if __name__ == "__main__":
    sys.exit(main())