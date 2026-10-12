#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emotion_curve.py — 大纲情感节奏曲线（只读视图 · 只报证据 · 不阻断）v1.0

用法：
  python emotion_curve.py [--outline memory/outline.json] [--out handoff/emotion_curve_report.txt]

定位：与 fix_auditor.py 同类——只产证据、不做判定、退出码恒为 0，不进门禁。
数据源：memory/outline.json 顶层 volume_*_chapters 的逐章 emotional_intensity / shuang_type。
渲染：卷级曲线（ASCII 条形）＋两类预警（均为既有口径的自动渲染，不新立规则）：
  ① 降温不足：峰值 ≥8 后下一章须降温 ≥3 档（口径源：conflict_rules 情感坡度规则）
  ② 断顿窗口：连续 ≥3 章无 A 级及以上（非 S/A）——skeptic 同款判据（Ch34-36 判例）
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

PEAK = 8           # 峰值阈值（≥ 视为峰）
VALLEY = 4         # 谷值阈值（≤ 视为谷）
COOLDOWN_DROP = 3  # 峰值后次章最少降温档数
GAP_RUN = 3        # 断顿窗口：连续非 A 级及以上章数阈值
A_PLUS = {"S", "A"}


def _reconf():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_chapters(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # 卷纲逐章细纲：volume_N_chapters（按 N 排序拼接；MVP 只读该族字段）
    vkeys = sorted(
        [k for k in data.keys() if re.fullmatch(r"volume_\d+_chapters", k)],
        key=lambda k: int(re.findall(r"\d+", k)[0]),
    )
    chapters = []
    for k in vkeys:
        for c in data.get(k, []):
            if isinstance(c, dict):
                chapters.append(c)
    # 爽点等级兜底表（逐章 shuang_type 缺失时回退）
    grade_map = {}
    for it in data.get("shuang_point_distribution", []):
        if isinstance(it, dict) and "chapter" in it:
            grade_map[it["chapter"]] = it.get("grade")
    rows = []
    for c in chapters:
        ch = c.get("chapter")
        if ch is None:
            continue
        rows.append({
            "chapter": ch,
            "title": c.get("title", ""),
            "intensity": c.get("emotional_intensity"),
            "grade": c.get("shuang_type") or grade_map.get(ch),
        })
    rows.sort(key=lambda r: r["chapter"])
    return data.get("title", "（未命名）"), rows


def render(title, rows, src):
    out = []
    out.append(f"《{title}》情感节奏曲线（只读报告 · 不阻断）")
    out.append(f"生成：{datetime.now().strftime('%Y-%m-%d %H:%M')} · 数据源：{src} · 共 {len(rows)} 章")
    out.append(
        f"图例：▲峰(≥{PEAK}) ▽谷(≤{VALLEY}) ｜ 预警口径（既有）：峰值后次章降温≥{COOLDOWN_DROP}档（conflict_rules）／"
        f"连续≥{GAP_RUN}章无A级及以上（skeptic 同款）"
    )
    out.append("")
    out.append(" Ch | 强度 | 等级 | 曲线")
    out.append("----+------+------+-----------------------------------")
    for r in rows:
        iv, g = r["intensity"], r["grade"] or "?"
        if isinstance(iv, (int, float)):
            n = max(0, min(10, int(round(iv))))
            bar = "█" * n + "·" * (10 - n)
            mark = " ▲" if iv >= PEAK else (" ▽" if iv <= VALLEY else "")
            iv_s = f"{iv:>2}"
        else:
            bar, mark, iv_s = "（缺强度）", "", " ?"
        out.append(f"{r['chapter']:>3} | {iv_s:>4} | {g:>4} | {bar}{mark}  {(r['title'] or '')[:6]}")
    # —— 预警区（只报证据，不做判定）——
    out.append("")
    out.append("— 预警（只报证据，不做判定）—")
    peaks = [r for r in rows if isinstance(r["intensity"], (int, float)) and r["intensity"] >= PEAK]
    idx = {r["chapter"]: i for i, r in enumerate(rows)}
    ok, bad = [], []
    for r in peaks:
        i = idx[r["chapter"]]
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        if nxt is None:
            ok.append(f"Ch{r['chapter']}={r['intensity']}→（卷末）")
            continue
        ni = nxt["intensity"]
        if not isinstance(ni, (int, float)):
            bad.append(f"Ch{r['chapter']}={r['intensity']}→Ch{nxt['chapter']}（次章缺强度，无法校验）")
        elif (r["intensity"] - ni) >= COOLDOWN_DROP:
            ok.append(f"Ch{r['chapter']}={r['intensity']}→Ch{nxt['chapter']}={ni}（降{r['intensity'] - ni}档✓）")
        else:
            bad.append(f"Ch{r['chapter']}={r['intensity']}→Ch{nxt['chapter']}={ni}（降温不足，需≥{COOLDOWN_DROP}档）")
    out.append(f"[降温] 峰值 {len(peaks)} 处：" + ("；".join(ok) if ok else "无"))
    for b in bad:
        out.append(f"[降温不足] {b}")
    # 断顿窗口
    gaps, run = [], []
    for r in rows:
        if (r["grade"] or "") not in A_PLUS:
            run.append(r)
        else:
            if len(run) >= GAP_RUN:
                gaps.append(run)
            run = []
    if len(run) >= GAP_RUN:
        gaps.append(run)
    if gaps:
        for run_ in gaps:
            rng = f"Ch{run_[0]['chapter']}-{run_[-1]['chapter']}"
            detail = "/".join(str(x["grade"] or "?") for x in run_)
            out.append(f"[断顿窗口] {rng}（连续{len(run_)}章无A级及以上：{detail}）")
    else:
        out.append("[断顿窗口] 无")
    # 统计
    n_valley = len([r for r in rows if isinstance(r["intensity"], (int, float)) and r["intensity"] <= VALLEY])
    n_aplus = len([r for r in rows if r["grade"] in A_PLUS])
    total = len(rows)
    pct = f"{n_aplus / total * 100:.0f}%" if total else "-"
    out.append("")
    out.append(f"— 统计 — 峰(▲){len(peaks)} · 谷(▽){n_valley} · A级及以上 {n_aplus}/{total}（{pct}）")
    out.append("注：本报告只产证据（同 fix_auditor 定位），是否处理由评审/作者裁量；退出码恒为 0。")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="大纲情感节奏曲线（只读视图，不阻断）")
    ap.add_argument("--outline", default="memory/outline.json")
    ap.add_argument("--out", default="handoff/emotion_curve_report.txt")
    args = ap.parse_args()
    _reconf()
    if not os.path.exists(args.outline):
        print(f"[emotion_curve] 未找到大纲文件：{args.outline}（只读视图，退出码 0）")
        return 0
    title, rows = load_chapters(args.outline)
    if not rows:
        print(f"[emotion_curve] {args.outline} 中未找到 volume_*_chapters 逐章数据（只读视图，退出码 0）")
        return 0
    report = render(title, rows, args.outline)
    print(report)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print(f"\n[emotion_curve] 报告已写入：{args.out}（只报证据，不阻断；exit=0）")
    return 0


if __name__ == "__main__":
    sys.exit(main())