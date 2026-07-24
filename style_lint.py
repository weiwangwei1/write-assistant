#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
style_lint.py — 网文章节文风校验器（对接 write-assistant 流水线）

设计原则：
  可量化的规则全部脚本化，不依赖 LLM 自觉。
  在 chapter-writer 提交交接卡之前运行，critical 未清零即打回。

用法：
  python style_lint.py 章节文件或目录 [--json 输出卡.json] [--config 阈值.json]
  python style_lint.py output/                      # 整书跨章检查
  python style_lint.py output/chapter_001.txt       # 单章检查
退出码：0=通过  1=存在 critical（供流水线拦截）
"""
import re, os, sys, json, argparse, unicodedata
from collections import Counter

# ---------------- 默认阈值（可用 --config 覆盖） ----------------
DEFAULT_CONFIG = {
    # 一、句式红线
    "not_a_is_b_max_per_chapter": 2,        # “不是A——是B”每章上限（设定级反转需人工豁免）
    "short_para_len": 15,                    # ≤N字视为碎段
    "short_para_ratio_max": 0.45,            # 碎段占比上限（对话密集章天然偏高，0.45 是宽严平衡点）
    "short_para_run_max": 6,                 # 连续碎段落数上限
    # 二、比喻红线
    "simile_max_per_chapter": 8,             # “像”字比喻每章上限
    "simile_max_per_para": 1,                # 单段喻体上限（禁止一段多喻）
    # 三、禁令清单（出现即报 critical）
    "ban_yizhong_feeling": True,             # “一种…感觉/东西/热/情绪”
    "ban_feeling_enum": True,                # “第三种热/第四种声音”式感觉编号
    "ban_summary_voice": True,               # “他明白了/原来如此”式总结心声
    "ranhou_max_per_chapter": 1,             # 叙事转折“然后”每章上限
    # 四、警告级（minor，不拦截）
    "emotion_telling_words": ["不敢", "害怕", "悲伤", "震撼", "激动"],
    "four_char_cliches": ["不急不缓", "不紧不慢", "取而代之", "不约而同", "悄无声息"],
    "era_wrong_words": ["路灯", "火柴", "同频", "电话", "汽车", "手机"],
    # 五、跨章规则（仅目录模式）
    "ending_family_window": 4,               # 章尾意象：连续N章内同族意象上限
    "ending_family_max_in_window": 2,
    "opening_channel_max_run": 2,            # 章首感官通道：最多连续N章相同
    "dup_sentence_min_len": 6,               # 跨章重复句（桥段复用）最小长度
}

SIMILE_EXCLUDE = ["画像", "雕像", "头像", "像样", "像话", "影像", "想像", "像章"]

# 章尾意象族
ENDING_FAMILIES = {
    "光/灯族": re.compile(r"(光|亮|灯|焰|火色|灭|晃)"),
    "鳞/纹族": re.compile(r"(鳞|纹|颤|跳|烫|热)"),
    "醒/睡族": re.compile(r"(醒|睁|竖瞳|睡|瞳)"),
    "人/门族": re.compile(r"(脚步|门|人影|来了|身影|风停)"),
    "对话族":  re.compile(r"[“\"「].*[”\"」]"),
}
# 章首感官通道
OPENING_CHANNELS = {
    "嗅觉": re.compile(r"(味|腥|香|臭|气息|烟味|焦)"),
    "听觉": re.compile(r"(声|响|音|砰|咔|嗒|吱|嗡)"),
    "视觉": re.compile(r"(光|亮|影|颜色|红|黑|金|灰)"),
    "触觉": re.compile(r"(凉|热|烫|冷|寒|温)"),
}

def han_len(s):
    return sum(1 for c in s if unicodedata.category(c).startswith(("Lo", "Lu")) or c.isdigit() or '一' <= c <= '鿿')

class Chapter:
    def __init__(self, path, text):
        self.path = path
        self.name = os.path.basename(path)
        self.lines = [l.rstrip() for l in text.splitlines()]
        # 过滤：章标题/分隔线/字数统计行
        self.body_lines = []
        for i, l in enumerate(self.lines, 1):
            s = l.strip()
            if not s: continue
            if re.match(r"^第\d+章", s): continue
            if re.match(r"^(字数|—{3,}|-{3,}|={3,})", s): continue
            if s.startswith("#"): continue
            self.body_lines.append((i, s))
        self.text = "\n".join(s for _, s in self.body_lines)
        self.paras = [s for _, s in self.body_lines]

def count_similes(text):
    cnt = 0
    for m in re.finditer(r"像", text):
        tail = text[m.start():m.start()+3]
        if any(tail.startswith(w[:2]) for w in SIMILE_EXCLUDE): continue
        cnt += 1
    return cnt

def lint_chapter(ch, cfg):
    issues = []
    def add(rule, sev, lineno, excerpt, msg):
        issues.append({"rule": rule, "severity": sev, "chapter": ch.name,
                       "line": lineno, "excerpt": excerpt[:50], "message": msg})

    # 1. 不是A——是B
    hits = []
    for ln, s in ch.body_lines:
        for m in re.finditer(r"不是[^。！？\n]{1,15}?[，,—\-]{0,2}是", s):
            seg = m.group(0)
            if re.match(r"不是(吗|吧|很|说)", seg): continue      # 口语疑问豁免
            hits.append((ln, seg))
    if len(hits) > cfg["not_a_is_b_max_per_chapter"]:
        for ln, seg in hits:
            add("not_a_is_b", "critical", ln, seg,
                f"“不是…是…”本章{len(hits)}处 > 上限{cfg['not_a_is_b_max_per_chapter']}")

    # 2. 碎段率
    shorts = [p for p in ch.paras if han_len(p) <= cfg["short_para_len"]]
    ratio = len(shorts) / max(1, len(ch.paras))
    if ratio > cfg["short_para_ratio_max"]:
        add("short_para_ratio", "critical", 0, "",
            f"碎段占比{ratio*100:.0f}%（{len(shorts)}/{len(ch.paras)}）> 上限{cfg['short_para_ratio_max']*100:.0f}%")
    # 连续碎段落
    run = 0
    for i, (ln, s) in enumerate(ch.body_lines):
        run = run + 1 if han_len(s) <= cfg["short_para_len"] else 0
        if run == cfg["short_para_run_max"] + 1:
            add("short_para_run", "minor", ln, s, f"连续碎段超过{cfg['short_para_run_max']}段")

    # 3. 比喻
    total_sim = count_similes(ch.text)
    if total_sim > cfg["simile_max_per_chapter"]:
        add("simile_total", "critical", 0, "",
            f"“像”字比喻{total_sim}处 > 上限{cfg['simile_max_per_chapter']}")
    for ln, s in ch.body_lines:
        if count_similes(s) > cfg["simile_max_per_para"]:
            add("simile_stacked", "critical", ln, s, "单段多喻体堆叠（一段一喻）")

    # 4. 禁令清单
    if cfg["ban_yizhong_feeling"]:
        for ln, s in ch.body_lines:
            for m in re.finditer(r"一种[^。，\n]{0,8}(?:感觉|东西|热|情绪|味道|声音)", s):
                add("ban_yizhong", "critical", ln, m.group(0), "违禁：冗余分类词“一种+感觉类”")
    if cfg["ban_feeling_enum"]:
        for ln, s in ch.body_lines:
            for m in re.finditer(r"第[一二三四五六七八九]+种(?:热|声音|感觉|东西|情绪|味道)", s):
                add("ban_feeling_enum", "critical", ln, m.group(0), "违禁：感觉编号（第N种…）")
    if cfg["ban_summary_voice"]:
        for ln, s in ch.body_lines:
            for m in re.finditer(r"(他明白了|他懂了|她明白了|原来如此|瞬间明白|终于明白)", s):
                add("ban_summary_voice", "critical", ln, m.group(0), "违禁：总结式心声")
    for ln, s in ch.body_lines:
        for m in re.finditer(r"(?:^|[。！？\n])\s*然后", s):
            pass  # 行首“然后”少见，改全文计数
    ranhou = len(re.findall(r"[。，]\s*然后", ch.text))
    if ranhou > cfg["ranhou_max_per_chapter"]:
        add("ranhou", "minor", 0, "", f"叙事“然后”{ranhou}处 > 上限{cfg['ranhou_max_per_chapter']}")

    # 5. 警告级
    for w in cfg["emotion_telling_words"]:
        n = ch.text.count(w)
        if n >= 3:
            add("emotion_telling", "minor", 0, w, f"情绪直说词“{w}”出现{n}次")
    for w in cfg["four_char_cliches"]:
        for ln, s in ch.body_lines:
            if w in s:
                add("four_char", "minor", ln, w, f"四字书面词组“{w}”")
    for w in cfg["era_wrong_words"]:
        for ln, s in ch.body_lines:
            if w in s:
                add("era_word", "critical", ln, w, f"时代错词“{w}”（确认世界观背景）")

    # 6. 时间线线索（报告项，供跨章事实表比对）
    time_hits = []
    for ln, s in ch.body_lines:
        for m in re.finditer(r"([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]年|\d+年|二十年|三十年|六十年|三百年|半年|\d+年前|上一次献祭)", s):
            time_hits.append({"line": ln, "hit": m.group(0), "context": s[:40]})
    return issues, time_hits

def ending_family(ch):
    tail = "\n".join(ch.paras[-2:]) if ch.paras else ""   # 看末两段，收束意象常在倒数第二段
    for fam, rx in ENDING_FAMILIES.items():
        if rx.search(tail): return fam, ch.paras[-1] if ch.paras else ""
    return "其他", ch.paras[-1] if ch.paras else ""

def opening_channel(ch):
    head = "".join(ch.paras[:2])[:60]
    for chn, rx in OPENING_CHANNELS.items():
        if rx.search(head): return chn
    return "动作/其他"

def cross_chapter(chapters, cfg):
    issues = []
    # 章尾意象族滑窗
    fams = [ending_family(c) for c in chapters]
    w, mx = cfg["ending_family_window"], cfg["ending_family_max_in_window"]
    for i in range(len(fams)):
        win = fams[i:i+w]
        for fam, cnt in Counter(f for f, _ in win).items():
            if fam != "其他" and cnt > mx:
                issues.append({"rule": "ending_family", "severity": "critical",
                    "chapter": f"{win[0][1][:0] or ''}{chapters[i].name}~{chapters[min(i+w-1,len(chapters)-1)].name}",
                    "line": 0, "excerpt": fams[i][1][:40],
                    "message": f"章尾意象族“{fam}”在{w}章窗口内出现{cnt}次 > 上限{mx}"})
                break
    # 章首感官通道连跑
    chans = [opening_channel(c) for c in chapters]
    run = 1
    for i in range(1, len(chans)):
        if chans[i] == "动作/其他":            # 非感官通道不参与连跑判定
            run = 1; continue
        run = run + 1 if chans[i] == chans[i-1] else 1
        if run > cfg["opening_channel_max_run"]:
            issues.append({"rule": "opening_channel", "severity": "critical",
                "chapter": chapters[i].name, "line": 0, "excerpt": "",
                "message": f"章首感官通道“{chans[i]}”已连续{run}章"})
    # 跨章重复句（桥段复用检测）
    sent_map = {}
    for c in chapters:
        for s in re.split(r"[。！？\n]", c.text):
            s = s.strip().strip("""”"'"「」""")
            if han_len(s) >= cfg["dup_sentence_min_len"]:
                sent_map.setdefault(s, set()).add(c.name)
    for s, where in sorted(sent_map.items()):
        if len(where) >= 2:
            issues.append({"rule": "dup_sentence", "severity": "minor",
                "chapter": "/".join(sorted(where)), "line": 0, "excerpt": s[:40],
                "message": "跨章重复句（若为桥段复现，需有增量设计）"})
    return issues

def main():
    ap = argparse.ArgumentParser(description="网文文风 lint（write-assistant 流水线前置校验）")
    ap.add_argument("path", help="章节文件或目录")
    ap.add_argument("--json", help="输出交接卡 JSON 路径")
    ap.add_argument("--config", help="阈值配置 JSON 路径")
    args = ap.parse_args()
    cfg = dict(DEFAULT_CONFIG)
    if args.config and os.path.exists(args.config):
        cfg.update(json.load(open(args.config, encoding="utf-8")))

    files = []
    if os.path.isdir(args.path):
        files = sorted(os.path.join(args.path, f) for f in os.listdir(args.path)
                       if f.endswith(".txt") and re.search(r"\d+", f))
    else:
        files = [args.path]
    chapters = []
    for f in files:
        chapters.append(Chapter(f, open(f, encoding="utf-8-sig", errors="ignore").read()))
    if not chapters:
        print("未找到章节文件"); sys.exit(2)

    all_issues, time_report = [], {}
    for ch in chapters:
        iss, th = lint_chapter(ch, cfg)
        all_issues += iss
        if th: time_report[ch.name] = th
    if len(chapters) > 1:
        all_issues += cross_chapter(chapters, cfg)

    crit = [i for i in all_issues if i["severity"] == "critical"]
    minor = [i for i in all_issues if i["severity"] == "minor"]
    status = "fail" if crit else "pass"

    # 控制台报告
    print(f"\n{'='*56}\n文风 lint 结果：{status.upper()}  （critical {len(crit)} / minor {len(minor)}）\n{'='*56}")
    by_rule = Counter(i["rule"] for i in all_issues)
    for rule, n in sorted(by_rule.items(), key=lambda x: -x[1]):
        print(f"  {rule:20s} × {n}")
    print()
    for i in all_issues[:80]:
        loc = f"{i['chapter']}:L{i['line']}" if i['line'] else i['chapter']
        print(f"[{i['severity']:8s}] {i['rule']:18s} {loc}  {i['message']}  {i['excerpt']}")
    if time_report:
        print(f"\n{'-'*56}\n时间线线索（请与设定圣经逐条比对）：")
        for cname, hits in time_report.items():
            joined = "、".join(sorted({h['hit'] for h in hits}))
            print(f"  {cname}: {joined}")

    if args.json:
        card = {"card_type": "style_lint", "from_agent": "style_lint(script)",
                "to_agent": "chapter-writer", "status": status,
                "critical_count": len(crit), "minor_count": len(minor),
                "issues": all_issues, "timeline_clues": time_report,
                "config": cfg}
        json.dump(card, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n交接卡已写入：{args.json}")
    sys.exit(1 if crit else 0)

if __name__ == "__main__":
    main()
