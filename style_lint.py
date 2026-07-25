#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
style_lint.py — 网文章节文风校验器（write-assistant 流水线前置门禁）

用法：
  python style_lint.py 章节文件或目录 [--json 输出卡.json] [--config 阈值.json]
  python style_lint.py output/ --style chendong        # 加载风格包覆盖层
  python style_lint.py output/ --styles-root .trae/skills/writer-styles

退出码：0=通过  1=存在 critical（供流水线拦截）

风格覆盖层（.trae/skills/writer-styles/<name>/lint_overlay.json）：
  {
    "overrides":        {"simile_max_per_chapter": 12},       # 阈值覆盖
    "disabled_rules":   ["four_char"],                        # 签名手法豁免（附reason）
    "custom_ban_words": [{"word": "仙器", "severity": "minor", "reason": "命名通货"}]
  }
"""
import re, os, sys, json, argparse, unicodedata
from collections import Counter

DEFAULT_CONFIG = {
    # 一、句式红线
    "not_a_is_b_max_per_chapter": 2,
    "short_para_len": 15,
    "short_para_ratio_max": 0.45,
    "short_para_run_max": 6,
    # 二、比喻红线
    "simile_max_per_chapter": 8,
    "simile_max_per_para": 1,
    # 三、禁令清单
    "ban_yizhong_feeling": True,
    "ban_feeling_enum": True,
    "ban_summary_voice": True,
    "ranhou_max_per_chapter": 1,
    # 四、对话占比（H9）
    "dialogue_ratio_min": 0.35,
    "dialogue_ratio_max": 0.60,
    # 四b、标点指纹（风格包可覆盖；默认宽松，风格包按原作指纹收紧）
    "dash_max_per_1000": 20.0,        # 破折号"——"每千字上限
    "ellipsis_max_per_1000": 5.0,     # 省略号"……"每千字上限
    # 四c、功能词指纹（v2.1新增，风格包按原作指纹收紧；默认宽松近似不启用）
    "le_max_per_1000": 60.0,          # "了"每千字上限（minor）
    "zhe_max_per_1000": 25.0,         # "着"每千字上限（minor）
    "conjunction_min_per_1000": 0.0,  # 书面连词(而/却/但/已/将/与/不过/可是)合计每千字下限（minor，0=不启用）
    "dialogue_guide_min_per_1000": 0.0,  # 对话引前引导(某某道：/说：/问：)每千字下限（minor，0=不启用）
    "name_starter_run_max": 8,        # 同二字段首连续段落上限（minor）
    # 五、警告级
    "emotion_telling_words": ["不敢", "害怕", "悲伤", "震撼", "激动"],
    "four_char_cliches": ["不急不缓", "不紧不慢", "取而代之", "不约而同", "悄无声息"],
    "era_wrong_words": ["路灯", "火柴", "同频", "电话", "汽车", "手机"],
    # 六、跨章规则（仅目录模式）
    "ending_family_window": 4,
    "ending_family_max_in_window": 2,
    "opening_channel_max_run": 2,
    "dup_sentence_min_len": 6,
}

# P0-2: 规则分层（L0通用反AI红线 / L1作者身份 / L2签名手法 / L3偏好提示）
# L0=不可豁免不可降级 | L1=必须通过(critical) | L2=渐进达标(不阻断) | L3=仅提示
RULE_LEVELS = {
    # L0: 通用反AI红线 — 不可豁免，不可降级
    "not_a_is_b": "L0", "ban_yizhong": "L0", "ban_feeling_enum": "L0",
    "ban_summary_voice": "L0", "simile_stacked": "L0", "era_word": "L0",
    "style_ban_word": "L0",
    # L1: 作者身份规则 — 定义风格核心特征，必须通过
    "short_para_ratio": "L1", "short_para_run": "L1", "simile_total": "L1",
    "dialogue_ratio": "L1",
    # L2: 签名手法规则 — 渐进达标，不阻断但需关注
    "dash_overuse": "L2", "ellipsis_overuse": "L2",
    "le_overuse": "L2", "zhe_overuse": "L2",
    "conjunction_underuse": "L2", "dialogue_guide_underuse": "L2",
    # L3: 偏好规则 — 仅提示
    "name_starter_run": "L3", "ranhou": "L3",
    "four_char": "L3", "emotion_telling": "L3",
}
# 跨章规则分级
CROSS_RULE_LEVELS = {
    "ending_family": "L0", "opening_channel": "L1", "dup_sentence": "L3",
}
LEVEL_NAMES = {
    "L0": "通用反AI红线", "L1": "作者身份", "L2": "签名手法", "L3": "偏好提示",
}

SIMILE_EXCLUDE = ["画像", "雕像", "头像", "像样", "像话", "影像", "想像", "像章"]

ENDING_FAMILIES = {
    "光/灯族": re.compile(r"(光|亮|灯|焰|火色|灭|晃)"),
    "鳞/纹族": re.compile(r"(鳞|纹|颤|跳|烫|热)"),
    "醒/睡族": re.compile(r"(醒|睁|竖瞳|睡|瞳)"),
    "人/门族": re.compile(r"(脚步|门|人影|来了|身影|风停)"),
    "对话族":  re.compile(r"[“\"「].*[”\"」]"),
}
OPENING_CHANNELS = {
    "嗅觉": re.compile(r"(味|腥|香|臭|气息|烟味|焦)"),
    "听觉": re.compile(r"(声|响|音|砰|咔|嗒|吱|嗡)"),
    "视觉": re.compile(r"(光|亮|影|颜色|红|黑|金|灰)"),
    "触觉": re.compile(r"(凉|热|烫|冷|寒|温)"),
}

def han_len(s):
    return sum(1 for c in s if '一' <= c <= '鿿' or c.isdigit())

class Chapter:
    def __init__(self, path, text):
        self.path = path
        self.name = os.path.basename(path)
        self.lines = [l.rstrip() for l in text.splitlines()]
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

def lint_chapter(ch, cfg, disabled, custom_bans, rule_levels=None):
    issues = []
    rl = rule_levels or RULE_LEVELS
    def add(rule, sev, lineno, excerpt, msg):
        level = rl.get(rule, "L3")
        if rule in disabled and level != "L0": return  # L0 通用反AI红线不可豁免
        issues.append({"rule": rule, "severity": sev, "level": level,
                       "chapter": ch.name, "line": lineno, "excerpt": excerpt[:50], "message": msg})

    if "not_a_is_b" not in disabled:
        hits = []
        for ln, s in ch.body_lines:
            for m in re.finditer(r"不是[^。！？\n]{1,15}?[，,—\-]{0,2}是", s):
                seg = m.group(0)
                if re.match(r"不是(吗|吧|很|说)", seg): continue
                hits.append((ln, seg))
        if len(hits) > cfg["not_a_is_b_max_per_chapter"]:
            for ln, seg in hits:
                add("not_a_is_b", "critical", ln, seg,
                    f"“不是…是…”本章{len(hits)}处 > 上限{cfg['not_a_is_b_max_per_chapter']}")

    shorts = [p for p in ch.paras if han_len(p) <= cfg["short_para_len"]]
    ratio = len(shorts) / max(1, len(ch.paras))
    if ratio > cfg["short_para_ratio_max"]:
        add("short_para_ratio", "critical", 0, "",
            f"碎段占比{ratio*100:.0f}%（{len(shorts)}/{len(ch.paras)}）> 上限{cfg['short_para_ratio_max']*100:.0f}%")
    run = 0
    for i, (ln, s) in enumerate(ch.body_lines):
        run = run + 1 if han_len(s) <= cfg["short_para_len"] else 0
        if run == cfg["short_para_run_max"] + 1:
            add("short_para_run", "minor", ln, s, f"连续碎段超过{cfg['short_para_run_max']}段")

    total_sim = count_similes(ch.text)
    if total_sim > cfg["simile_max_per_chapter"]:
        add("simile_total", "critical", 0, "",
            f"“像”字比喻{total_sim}处 > 上限{cfg['simile_max_per_chapter']}")
    for ln, s in ch.body_lines:
        if count_similes(s) > cfg["simile_max_per_para"]:
            add("simile_stacked", "critical", ln, s, "单段多喻体堆叠（一段一喻）")

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
    ranhou = len(re.findall(r"[。，]\s*然后", ch.text))
    if ranhou > cfg["ranhou_max_per_chapter"]:
        add("ranhou", "minor", 0, "", f"叙事“然后”{ranhou}处 > 上限{cfg['ranhou_max_per_chapter']}")

    # 对话占比（H9）
    dia = sum(han_len(p) for p in ch.paras if re.search(r"[\"“「]", p))
    dr = dia / max(1, sum(han_len(p) for p in ch.paras))
    if dr < cfg["dialogue_ratio_min"]:
        add("dialogue_ratio", "minor", 0, "", f"对话占比{dr*100:.0f}% < 下限{cfg['dialogue_ratio_min']*100:.0f}%")
    elif dr > cfg["dialogue_ratio_max"]:
        add("dialogue_ratio", "minor", 0, "", f"对话占比{dr*100:.0f}% > 上限{cfg['dialogue_ratio_max']*100:.0f}%")

    # 标点指纹（破折号/省略号频率，风格包按原作指纹收紧）
    total_chars = max(1, sum(han_len(p) for p in ch.paras))
    dash_cnt = ch.text.count("——") + ch.text.count("—")
    dash_per_1k = round(dash_cnt / total_chars * 1000, 3)
    if dash_per_1k > cfg["dash_max_per_1000"]:
        add("dash_overuse", "critical", 0, "", f"破折号{dash_per_1k}/千字 > 上限{cfg['dash_max_per_1000']}")
    ellipsis_cnt = ch.text.count("……")
    ellipsis_per_1k = round(ellipsis_cnt / total_chars * 1000, 3)
    if ellipsis_per_1k > cfg["ellipsis_max_per_1000"]:
        add("ellipsis_overuse", "minor", 0, "", f"省略号{ellipsis_per_1k}/千字 > 上限{cfg['ellipsis_max_per_1000']}")

    # 功能词指纹（v2.1：了/着密度+书面连词下限+同段首连跑，风格包按原作指纹收紧）
    le_per_1k = round(ch.text.count("了") / total_chars * 1000, 2)
    if le_per_1k > cfg["le_max_per_1000"]:
        add("le_overuse", "minor", 0, "", f"“了”{le_per_1k}/千字 > 上限{cfg['le_max_per_1000']}（了字收尾碎句宜改连词衔接长句）")
    zhe_per_1k = round(ch.text.count("着") / total_chars * 1000, 2)
    if zhe_per_1k > cfg["zhe_max_per_1000"]:
        add("zhe_overuse", "minor", 0, "", f"“着”{zhe_per_1k}/千字 > 上限{cfg['zhe_max_per_1000']}")
    if cfg["conjunction_min_per_1000"] > 0:
        conj_cnt = sum(ch.text.count(w) for w in ("而", "却", "但", "已", "将", "与", "不过", "可是"))
        conj_per_1k = round(conj_cnt / total_chars * 1000, 2)
        if conj_per_1k < cfg["conjunction_min_per_1000"]:
            add("conjunction_underuse", "minor", 0, "", f"书面连词(而/却/但/已/将/与/不过/可是){conj_per_1k}/千字 < 下限{cfg['conjunction_min_per_1000']}（连词是长句黏合剂，缺失则句句短促）")
    if cfg["dialogue_guide_min_per_1000"] > 0:
        guide_cnt = len(re.findall(r"(?:道|说|问|答)\s*[:：]\s*[\"“「]", ch.text))
        guide_per_1k = round(guide_cnt / total_chars * 1000, 2)
        if guide_per_1k < cfg["dialogue_guide_min_per_1000"]:
            add("dialogue_guide_underuse", "minor", 0, "", f"对话引前引导(某某道：){guide_per_1k}/千字 < 下限{cfg['dialogue_guide_min_per_1000']}（全裸对话不符合该风格引导习惯，需穿插引前引导）")
    run_head, run_len = None, 0
    for ln, s in ch.body_lines:
        head = re.sub(r"^[\"“「\s]+", "", s)[:2]
        if head and head == run_head:
            run_len += 1
            if run_len == cfg["name_starter_run_max"] + 1:
                add("name_starter_run", "minor", ln, s, f"连续同段首“{head}…”超过{cfg['name_starter_run_max']}段（段首须换型：连词/感官/动作/对话）")
        else:
            run_head, run_len = head, 1

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
    for item in custom_bans:
        w, sev, reason = item["word"], item.get("severity", "critical"), item.get("reason", "风格包违禁词")
        for ln, s in ch.body_lines:
            if w in s:
                add("style_ban_word", sev, ln, w, f"“{w}”——{reason}")

    time_hits = []
    for ln, s in ch.body_lines:
        for m in re.finditer(r"([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]年|\d+年|二十年|三十年|六十年|三百年|半年|\d+年前|上一次献祭)", s):
            time_hits.append({"line": ln, "hit": m.group(0), "context": s[:40]})
    return issues, time_hits

def ending_family(ch):
    tail = "\n".join(ch.paras[-2:]) if ch.paras else ""
    for fam, rx in ENDING_FAMILIES.items():
        if rx.search(tail): return fam, ch.paras[-1] if ch.paras else ""
    return "其他", ch.paras[-1] if ch.paras else ""

def opening_channel(ch):
    head = "".join(ch.paras[:2])[:60]
    for chn, rx in OPENING_CHANNELS.items():
        if rx.search(head): return chn
    return "动作/其他"

def cross_chapter(chapters, cfg, disabled, rule_levels=None):
    issues = []
    rl = rule_levels or CROSS_RULE_LEVELS
    def add(rule, sev, chapter, excerpt, msg):
        level = rl.get(rule, "L3")
        if rule in disabled and level != "L0": return
        issues.append({"rule": rule, "severity": sev, "level": level, "chapter": chapter,
                       "line": 0, "excerpt": excerpt[:40], "message": msg})
    fams = [ending_family(c) for c in chapters]
    w, mx = cfg["ending_family_window"], cfg["ending_family_max_in_window"]
    for i in range(len(fams)):
        win = fams[i:i+w]
        for fam, cnt in Counter(f for f, _ in win).items():
            if fam != "其他" and cnt > mx:
                add("ending_family", "critical",
                    f"{chapters[i].name}~{chapters[min(i+w-1,len(chapters)-1)].name}",
                    fams[i][1], f"章尾意象族“{fam}”在{w}章窗口内出现{cnt}次 > 上限{mx}")
                break
    chans = [opening_channel(c) for c in chapters]
    run = 1
    for i in range(1, len(chans)):
        if chans[i] == "动作/其他":
            run = 1; continue
        run = run + 1 if chans[i] == chans[i-1] else 1
        if run > cfg["opening_channel_max_run"]:
            add("opening_channel", "critical", chapters[i].name, "",
                f"章首感官通道“{chans[i]}”已连续{run}章")
    sent_map = {}
    for c in chapters:
        for s in re.split(r"[。！？\n]", c.text):
            s = s.strip().strip("""”"'"「」""")
            if han_len(s) >= cfg["dup_sentence_min_len"]:
                sent_map.setdefault(s, set()).add(c.name)
    for s, where in sorted(sent_map.items()):
        if len(where) >= 2:
            add("dup_sentence", "minor", "/".join(sorted(where)), s,
                "跨章重复句（若为桥段复现，需有增量设计）")
    return issues

def main():
    ap = argparse.ArgumentParser(description="网文文风 lint（write-assistant 流水线前置校验）")
    ap.add_argument("path", help="章节文件或目录")
    ap.add_argument("--json", help="输出交接卡 JSON 路径")
    ap.add_argument("--config", help="阈值配置 JSON 路径")
    ap.add_argument("--style", help="风格包名（加载 lint_overlay.json）")
    ap.add_argument("--styles-root", default=".trae/skills/writer-styles", help="风格包根目录")
    args = ap.parse_args()

    cfg = dict(DEFAULT_CONFIG)
    if args.config and os.path.exists(args.config):
        cfg.update(json.load(open(args.config, encoding="utf-8")))
    disabled, custom_bans, style_note = set(), [], ""
    rule_levels = dict(RULE_LEVELS)
    cross_rule_levels = dict(CROSS_RULE_LEVELS)
    if args.style:
        ov_path = os.path.join(args.styles_root, args.style, "lint_overlay.json")
        if not os.path.exists(ov_path):
            print(f"风格覆盖层不存在：{ov_path}"); sys.exit(2)
        ov = json.load(open(ov_path, encoding="utf-8"))
        cfg.update(ov.get("overrides", {}))
        disabled = set(ov.get("disabled_rules", []))
        custom_bans = ov.get("custom_ban_words", [])
        rule_levels.update(ov.get("rule_level_overrides", {}))
        cross_rule_levels.update(ov.get("cross_rule_level_overrides", {}))
        style_note = f"（风格包：{args.style}，豁免 {sorted(disabled)}）"

    files = []
    if os.path.isdir(args.path):
        files = sorted(os.path.join(args.path, f) for f in os.listdir(args.path)
                       if f.endswith(".txt") and re.search(r"\d+", f))
    else:
        files = [args.path]
    chapters = [Chapter(f, open(f, encoding="utf-8-sig", errors="ignore").read()) for f in files]
    if not chapters:
        print("未找到章节文件"); sys.exit(2)

    all_issues, time_report = [], {}
    for ch in chapters:
        iss, th = lint_chapter(ch, cfg, disabled, custom_bans, rule_levels)
        all_issues += iss
        if th: time_report[ch.name] = th
    if len(chapters) > 1:
        all_issues += cross_chapter(chapters, cfg, disabled, cross_rule_levels)

    # P0-2: 退出码只看 L0+L1 的 critical（L2/L3 不阻断流水线）
    blocking = [i for i in all_issues if i.get("level") in ("L0", "L1") and i["severity"] == "critical"]
    non_blocking = [i for i in all_issues if i not in blocking]
    status = "fail" if blocking else "pass"

    # 按 level 分组统计
    by_level = {}
    for i in all_issues:
        lv = i.get("level", "L3")
        by_level.setdefault(lv, []).append(i)

    print(f"\n{'='*56}\n文风 lint 结果：{status.upper()}{style_note}")
    print(f"  阻断项（L0+L1 critical）：{len(blocking)}  |  非阻断项：{len(non_blocking)}\n{'='*56}")
    for lv in ["L0", "L1", "L2", "L3"]:
        items = by_level.get(lv, [])
        if not items: continue
        crit_n = sum(1 for i in items if i["severity"] == "critical")
        minor_n = sum(1 for i in items if i["severity"] == "minor")
        print(f"\n  [{lv} {LEVEL_NAMES[lv]}] critical {crit_n} / minor {minor_n}")
        for rule, n in sorted(Counter(i["rule"] for i in items).items(), key=lambda x: -x[1]):
            print(f"    {rule:22s} × {n}")
    print()
    for i in all_issues[:80]:
        loc = f"{i['chapter']}:L{i['line']}" if i['line'] else i['chapter']
        lv = i.get("level", "L3")
        print(f"[{lv} {i['severity']:8s}] {i['rule']:18s} {loc}  {i['message']}  {i['excerpt']}")
    if time_report:
        print(f"\n{'-'*56}\n时间线线索（请与设定圣经逐条比对）：")
        for cname, hits in time_report.items():
            print(f"  {cname}: {'、'.join(sorted({h['hit'] for h in hits}))}")

    if args.json:
        card = {"card_type": "style_lint", "from_agent": "style_lint(script)",
                "to_agent": "chapter-writer", "status": status, "style_pack": args.style,
                "blocking_count": len(blocking), "non_blocking_count": len(non_blocking),
                "issues": all_issues, "timeline_clues": time_report, "config": cfg}
        json.dump(card, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n交接卡已写入：{args.json}")
    sys.exit(1 if blocking else 0)

if __name__ == "__main__":
    main()
