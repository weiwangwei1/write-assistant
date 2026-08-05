#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
style_lint.py — 网文章节文风校验器（write-assistant 流水线前置门禁）

用法：
  python style_lint.py 章节文件或目录 [--json 输出卡.json] [--config 阈值.json]
  python style_lint.py output/ --style chendong        # 加载风格包覆盖层
  python style_lint.py output/ --styles-root .trae/skills/writer-styles

退出码：0=通过  1=存在 L0 critical（供流水线拦截；v2.3 起 L1 降级为顾问，报告但不阻断）

v2.8：新增三项章内重复检测（L1 顾问项），针对"高级AI痕迹——重复模式"：
  ① phrase_repeat：章内短语重复（同一4-8字片段出现3+次→意象/句式自我繁殖）
  ② dialogue_tag_repeat：对话标签重复（同一"X道/X说"出现4+次→应用动作节拍替代）
  ③ rhythm_monotony：节奏单调（短句占比>80%且无≥50字长句→逗号节奏全程不变化）
  三项均为 L1 minor，报告但不阻断，由 detail-reviewer 逐条裁定。
  动机：《第三纪元》黄金三章读者反馈"写法太重复，一眼AI"——lint 抓句子级AI痕迹，
  但抓不到跨句/跨段的重复模式，而这些恰恰是更高级的AI痕迹。

v2.7：撤回 distant_recall 规则（v2.6 引入，2026-07-28 撤回）——实战中 2 次标记全是同段落
  false positive、0 次回应、0 次真实拦截；其覆盖的回指过远问题仅占真人反馈 3.8%，ROI 为负。
  检测职责移交真人读者（入库前随口反馈制，见 chief-editor 章节循环 8b）。

v2.3（框架升级 F1）：L1 作者身份规则从阻断降级为顾问——退出码只看 L0 critical；
  L1 critical 仍作为 advisory 报告，由 detail-reviewer 逐条回应（接受超阈值附理由/需修复）；
  OVERRIDE 覆写对 L0 不再生效（修复越级豁免漏洞），L1 顾问化后覆写机制废弃。

风格覆盖层（.trae/skills/writer-styles/<name>/lint_overlay.json）：
  {
    "overrides":        {"simile_max_per_chapter": 12},       # 阈值覆盖
    "disabled_rules":   ["four_char"],                        # 签名手法豁免（附reason）
    "custom_ban_words": [{"word": "仙器", "severity": "minor", "reason": "命名通货"}]
  }
"""
import re, os, sys, json, argparse, unicodedata, glob
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
    # 四d、篇幅硬检（v2.4新增；0=不启用。书籍级标准经 --config 注入，如 wanwenshi/lint_config.json）
    "chapter_len_min": 0,
    "chapter_len_max": 0,
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
    # 六、文学质量检测（v2.2新增——解决钝规则导致过度矫正的问题）
    "tell_marker_words": ["习惯性地", "不由得", "下意识地", "情不自禁", "自然而然地", "本能地", "条件反射般", "潜意识里"],
    "cliche_vehicles": ["山", "风", "火", "水", "刀", "剑", "雷", "电", "铁", "石", "雾", "冰", "蛇", "虎", "龙", "潮", "浪", "云", "雨", "雪"],
    "short_le_ending_max": 3,       # 短句(≤15字)以"了"收尾的上限（AI腔特征）
    "narrative_dialogue_max": 1,    # 叙述化对话(无引号的X问Y说模式)上限，从2降至1——旁白替爽检测
    "certain_markers": ["就是", "分明是", "肯定是", "无疑是", "确实是"],
    # 六、跨章规则（仅目录模式）
    "ending_family_window": 4,
    "ending_family_max_in_window": 2,
    "opening_channel_max_run": 2,
    "dup_sentence_min_len": 6,
    # 六b、跨章短语重复检测（v2.5新增——黄金三章复盘修复）
    "recurring_phrase_min_len": 8,        # 重复短语最小长度（汉字数）
    "recurring_phrase_max_across": 2,     # 同一短语跨章出现的最大次数（超过报minor）
    "signature_line_max_per_5ch": 2,      # 角色签名台词每5章窗口内最大使用次数
    # 六c、章内重复检测（v2.8新增——高级AI痕迹：重复模式）
    "phrase_repeat_min_len": 4,           # 章内重复短语最小长度（汉字数）
    "phrase_repeat_max_len": 8,           # 章内重复短语最大长度
    "phrase_repeat_max_in_chapter": 3,    # 同一片段章内最大出现次数（超过报minor）
    "phrase_repeat_name_threshold": 8,    # 4字以下短语出现此次数以上判定为角色名，跳过
    "dialogue_tag_max_repeat": 4,         # 同一对话标签（X道/X说）章内最大重复次数
    "short_sentence_ratio_max": 0.80,     # 短句(≤15字)占比上限（节奏单调检测）
    "long_sentence_min_len": 50,          # 长句最小字数（至少1句≥此值，否则报rhythm_monotony）
    # 七b、旁白式设定解释检测（v2.5新增，L2级）
    "tell_exposition_patterns": [
        r"是.{2,10}的命脉", r"是.{2,10}的命根", r"意味着",
        r"对于.{1,8}来说.{2,15}就是", r"换句话说", r"也就是说",
    ],
}

# P0-2: 规则分层（L0通用反AI红线 / L1作者身份 / L2签名手法 / L3偏好提示）
# L0=不可豁免不可降级(阻断) | L1=作者身份(v2.3起顾问制:critical仍报告但不阻断) | L2=渐进达标(不阻断) | L3=仅提示
RULE_LEVELS = {
    # L0: 通用反AI红线 — 不可豁免，不可降级
    "not_a_is_b": "L0", "ban_yizhong": "L0", "ban_feeling_enum": "L0",
    "ban_summary_voice": "L0", "simile_stacked": "L0", "era_word": "L0",
    "style_ban_word": "L0",
    # L1: 作者身份规则 — 定义风格核心特征，v2.3 起顾问制（critical 报告但不再阻断，审核员逐条回应）
    "short_para_ratio": "L1", "short_para_run": "L1", "simile_total": "L1",
    "dialogue_ratio": "L1", "chapter_length": "L1",
    # L2: 签名手法规则 — 渐进达标，不阻断但需关注
    "dash_overuse": "L2", "ellipsis_overuse": "L2",
    "le_overuse": "L2", "zhe_overuse": "L2",
    "conjunction_underuse": "L2", "dialogue_guide_underuse": "L2",
    # v2.2 新增：文学质量检测（L2，不阻断但提醒写手区分好坏实例）
    "le_pattern": "L2", "tell_marker": "L2",
    "narrative_dialogue": "L2", "certain_marker_mismatch": "L2",
    # v2.5 新增：旁白式设定解释（L2，顾问项）
    "tell_exposition": "L2",
    # v2.8 新增：章内重复检测（L1，顾问项——高级AI痕迹）
    "phrase_repeat": "L1", "dialogue_tag_repeat": "L1", "rhythm_monotony": "L1",
    # L3: 偏好规则 — 仅提示
    "name_starter_run": "L3", "ranhou": "L3",
    "four_char": "L3", "emotion_telling": "L3",
    "override_limit": "L3",
}
# 跨章规则分级
CROSS_RULE_LEVELS = {
    "ending_family": "L0", "opening_channel": "L1", "dup_sentence": "L3",
    # v2.5 新增：跨章短语重复 + 签名台词频率（L1 顾问项）
    "recurring_phrase": "L1", "signature_line_freq": "L1",
}
LEVEL_NAMES = {
    "L0": "通用反AI红线", "L1": "作者身份", "L2": "签名手法", "L3": "偏好提示",
}

SIMILE_EXCLUDE = ["画像", "雕像", "头像", "像样", "像话", "影像", "想像", "像章"]

# v2.2: 陈词喻体表——命中则计为劣质比喻（权重1.0），未命中计为优质（权重0.5）
CLICHE_VEHICLES = {"山", "风", "火", "水", "刀", "剑", "雷", "电", "铁", "石", "雾", "冰", "蛇", "虎", "龙", "潮", "浪", "云", "雨", "雪"}

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
        self.overrides = []  # v2.2: 合理覆写列表 [{"rule": str, "reason": str, "line": int, "text": str}]
        pending_override = None
        for i, l in enumerate(self.lines, 1):
            s = l.strip()
            if not s: continue
            # v2.2: 解析覆写标记 <!-- OVERRIDE: rule_name reason -->
            if s.startswith("<!--") and "OVERRIDE:" in s:
                m = re.search(r"OVERRIDE:\s*(\S+)\s*(.*)", s)
                if m:
                    pending_override = {"rule": m.group(1), "reason": m.group(2).rstrip("-->").strip(), "line": i}
                continue
            if re.match(r"^第\d+章", s): continue
            if re.match(r"^(字数|—{3,}|-{3,}|={3,})", s): continue
            if s.startswith("#"): continue
            # 如果有待处理的覆写标记，关联到当前段落
            if pending_override:
                pending_override["text"] = s
                pending_override["line"] = i  # 更新为实际段落行号
                self.overrides.append(pending_override)
                pending_override = None
            self.body_lines.append((i, s))
        self.text = "\n".join(s for _, s in self.body_lines)
        self.paras = [s for _, s in self.body_lines]
        # v2.2: 构建覆写字典 {rule_name: [paragraph_text, ...]} 和覆写行号集合
        self.override_rules = {}  # {rule_name: set of line_numbers}
        for ov in self.overrides:
            self.override_rules.setdefault(ov["rule"], set()).add(ov["line"])
        # 被覆写的段落文本（用于从全章计数中排除）
        self.override_texts = set(ov.get("text", "") for ov in self.overrides if ov.get("text"))

def count_similes(text):
    cnt = 0
    for m in re.finditer(r"像", text):
        tail = text[m.start():m.start()+3]
        if any(tail.startswith(w[:2]) for w in SIMILE_EXCLUDE): continue
        cnt += 1
    return cnt

def classify_similes(text):
    """v2.2: 比喻质量分级——返回 (total, quality_count, cliche_count)
    优质比喻（喻体具体、不在陈词表中）权重0.5，陈词比喻（喻体在CLICHE_VEHICLES中）权重1.0
    优质占比≥70%时，超限从critical降级为minor——允许保留有效比喻"""
    quality_count = 0
    cliche_count = 0
    for m in re.finditer(r"像", text):
        tail = text[m.start():m.start()+3]
        if any(tail.startswith(w[:2]) for w in SIMILE_EXCLUDE): continue
        vehicle = text[m.end():m.end()+6]
        is_cliche = any(cv in vehicle for cv in CLICHE_VEHICLES)
        if is_cliche:
            cliche_count += 1
        else:
            quality_count += 1
    return quality_count + cliche_count, quality_count, cliche_count

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

    # 比喻红线（v2.2：质量分级——优质比喻占比≥70%时超限降级为minor）
    sim_total, sim_quality, sim_cliche = classify_similes(ch.text)
    if sim_total > cfg["simile_max_per_chapter"]:
        quality_ratio = sim_quality / max(1, sim_total)
        sev = "minor" if quality_ratio >= 0.7 else "critical"
        add("simile_total", sev, 0, "",
            f"“像”字比喻{sim_total}处 > 上限{cfg['simile_max_per_chapter']}（优质{sim_quality}/陈词{sim_cliche}，优质占比{quality_ratio*100:.0f}%）")
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
    dia = sum(han_len(p) for p in ch.paras if re.search(r"[\"“」「]", p))
    dr = dia / max(1, sum(han_len(p) for p in ch.paras))
    if dr < cfg["dialogue_ratio_min"]:
        add("dialogue_ratio", "minor", 0, "", f"对话占比{dr*100:.0f}% < 下限{cfg['dialogue_ratio_min']*100:.0f}%")
    elif dr > cfg["dialogue_ratio_max"]:
        add("dialogue_ratio", "minor", 0, "", f"对话占比{dr*100:.0f}% > 上限{cfg['dialogue_ratio_max']*100:.0f}%")
    # v2.2.1 改进：叙述化对话检测——用"代词+对话动词"模式替代宽泛正则
    # v2.2 原正则 (?:问|说|答|道)[^。！？]{5,40}(?:说|答|道|回) 会误匹配
    # "总说""公道""知道""一道"等非对话用法，导致 9 处误报→写手过度矫正
    # 改进：只有段落中出现≥2次"他说/她问/他答/她道"模式时才认定为叙述化对话
    narrative_dia_cnt = 0
    for ln, s in ch.body_lines:
        if not re.search(r'[""「]', s):
            pronoun_verbs = len(re.findall(r'(?:他|她)(?:说|问|答|道)', s))
            if pronoun_verbs >= 2:
                narrative_dia_cnt += 1
                add("narrative_dialogue", "minor", ln, s[:50],
                    f"叙述化对话（{pronoun_verbs}处代词+对话动词）——面对面场景建议用直接对话格式保留现场感")
    if narrative_dia_cnt > cfg.get("narrative_dialogue_max", 1):
        add("narrative_dialogue", "minor", 0, "",
            f"叙述化对话{narrative_dia_cnt}处 > 上限{cfg.get('narrative_dialogue_max', 1)}——大量对话被转成摘要")

    # 标点指纹（破折号/省略号频率，风格包按原作指纹收紧）
    total_chars = max(1, sum(han_len(p) for p in ch.paras))
    # v2.4: 篇幅硬检（L1 advisory，提交前必须清零；初稿写长，宁删勿补）
    if cfg.get("chapter_len_min", 0) > 0 and total_chars < cfg["chapter_len_min"]:
        add("chapter_length", "critical", 0, "",
            f"篇幅{total_chars}字 < 下限{cfg['chapter_len_min']}字——初稿写长，宁删勿补，扩场景/加冲突，不凑字")
    if cfg.get("chapter_len_max", 0) > 0 and total_chars > cfg["chapter_len_max"]:
        add("chapter_length", "critical", 0, "",
            f"篇幅{total_chars}字 > 上限{cfg['chapter_len_max']}字")

    dash_cnt = ch.text.count("——") + ch.text.count("—")
    dash_per_1k = round(dash_cnt / total_chars * 1000, 3)
    if dash_per_1k > cfg["dash_max_per_1000"]:
        add("dash_overuse", "critical", 0, "", f"破折号{dash_per_1k}/千字 > 上限{cfg['dash_max_per_1000']}")
    ellipsis_cnt = ch.text.count("……")
    ellipsis_per_1k = round(ellipsis_cnt / total_chars * 1000, 3)
    if ellipsis_per_1k > cfg["ellipsis_max_per_1000"]:
        add("ellipsis_overuse", "minor", 0, "", f"省略号{ellipsis_per_1k}/千字 > 上限{cfg['ellipsis_max_per_1000']}")

    # 功能词指纹（v2.2：了/着密度保留作指纹参考，lint 新增模式检测）
    le_per_1k = round(ch.text.count("了") / total_chars * 1000, 2)
    if le_per_1k > cfg["le_max_per_1000"]:
        add("le_overuse", "minor", 0, "", f"“了”{le_per_1k}/千字 > 上限{cfg['le_max_per_1000']}（参考指标——重点看 le_pattern 是否为 AI 腔模式）")
    # v2.2 新增：AI 腔"了"模式检测——短句(≤15字)以"了"收尾（真正的 AI 腔特征，而非语法必需的"了"）
    short_le_endings = []
    for ln, s in ch.body_lines:
        for sent in re.split(r"[。！？]", s):
            sent = sent.strip()
            if 0 < han_len(sent) <= 15 and sent.endswith("了"):
                short_le_endings.append((ln, sent))
    if len(short_le_endings) > cfg.get("short_le_ending_max", 3):
        for ln, sent in short_le_endings[:5]:
            add("le_pattern", "minor", ln, sent, f"短句以“了”收尾（共{len(short_le_endings)}处 > 上限{cfg.get('short_le_ending_max', 3)}）——AI腔特征：建议用连词衔接为长句，而非删除语法必需的“了”")
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
    # v2.2 新增：Tell 标记词检测——描述动作心理机制而非展示动作本身
    for w in cfg.get("tell_marker_words", []):
        for ln, s in ch.body_lines:
            if w in s:
                add("tell_marker", "minor", ln, w, f"Tell标记词'{w}'——告诉而非展示，建议删除让动作本身说话")
    # v2.5 新增：旁白式设定解释检测——定义式句式而非角色自然认知
    for pat in cfg.get("tell_exposition_patterns", []):
        for ln, s in ch.body_lines:
            for m in re.finditer(pat, s):
                add("tell_exposition", "minor", ln, m.group(0),
                    f"旁白式设定解释'{m.group(0)}'——建议通过角色行为/对话/感官自然释放设定信息")
    for w in cfg["four_char_cliches"]:
        for ln, s in ch.body_lines:
            if w in s:
                add("four_char", "minor", ln, w, f"四字书面词组“{w}”")
    # v2.2 新增：确定性语气检测——首次观察场景用确定语气时提醒视角漂移
    for ln, s in ch.body_lines:
        for cm in cfg.get("certain_markers", []):
            for m in re.finditer(r"(?:看[到见]?|注意[到]?|瞧[见]?)[^。！？]{0,10}" + cm, s):
                add("certain_marker_mismatch", "minor", ln, m.group(0),
                    f"观察+确定语气“{cm}”——角色首次遭遇时建议用推测语气（像是/倒像是/似乎）")
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

    # v2.8 新增：章内重复模式检测（意象繁殖/标签重复/节奏单调）——高级AI痕迹
    
    # 1. 章内短语重复（catches "一圈套一圈" × 3+ within one chapter）
    ngram_min = cfg.get("phrase_repeat_min_len", 4)
    ngram_max = cfg.get("phrase_repeat_max_len", 8)
    ngram_threshold = cfg.get("phrase_repeat_max_in_chapter", 3)
    bad_starts_local = set("的了着过在地")
    bad_ends_local = set("的他她它在地")
    ngram_counts = {}
    for seq_match in re.finditer(r"[\u4e00-\u9fff]+", ch.text):
        seq = seq_match.group()
        if len(seq) < ngram_min:
            continue
        for length in range(ngram_min, min(ngram_max, len(seq)) + 1):
            for i in range(len(seq) - length + 1):
                ng = seq[i:i+length]
                if ng[0] in bad_starts_local or ng[-1] in bad_ends_local:
                    continue
                ngram_counts[ng] = ngram_counts.get(ng, 0) + 1
    reported_ngrams = set()
    name_threshold = cfg.get("phrase_repeat_name_threshold", 8)
    for ng, cnt in sorted(ngram_counts.items(), key=lambda x: (-x[1], -len(x[0]))):
        if cnt <= ngram_threshold:
            continue
        # 启发式：4字以下短语出现8次以上判定为角色名，跳过（"守军头目"等）
        if len(ng) <= 4 and cnt >= name_threshold:
            continue
        if any(ng in r and r != ng for r in reported_ngrams):
            continue
        reported_ngrams.add(ng)
        add("phrase_repeat", "minor", 0, ng,
            f"章内重复'{ng}'×{cnt} > 上限{ngram_threshold}（意象/句式自我繁殖——高级AI痕迹）")

    # 2. 对话标签重复（catches "顾衡道" × 4+ within one chapter）
    tag_counts = {}
    for m in re.finditer(r"([\u4e00-\u9fff]{2,4})(?:道|说|问|答)[：:，,]", ch.text):
        tag = m.group(1) + m.group(0)[-2]
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
    for tag, cnt in tag_counts.items():
        if cnt > cfg.get("dialogue_tag_max_repeat", 4):
            add("dialogue_tag_repeat", "minor", 0, tag,
                f"对话标签'{tag}'×{cnt} > 上限{cfg.get('dialogue_tag_max_repeat', 4)}（用动作节拍替代标签）")

    # 3. 节奏单调（catches "all short choppy sentences, no long sentence breathing"）
    sentences = [s.strip() for s in re.split(r"[。！？]", ch.text) if s.strip()]
    sent_lens = [han_len(s) for s in sentences if han_len(s) > 0]
    if sent_lens:
        short_count = sum(1 for l in sent_lens if l <= 15)
        short_ratio = short_count / len(sent_lens)
        max_sent_len = max(sent_lens)
        if short_ratio > cfg.get("short_sentence_ratio_max", 0.80) and max_sent_len < cfg.get("long_sentence_min_len", 50):
            add("rhythm_monotony", "minor", 0, "",
                f"短句占比{short_ratio*100:.0f}%（{short_count}/{len(sent_lens)}），最长句{max_sent_len}字 < {cfg.get('long_sentence_min_len', 50)}字——逗号节奏单调，需在情感节点放长句")

    # v2.2: 合理覆写过滤——被覆写的行级问题从 issues 中移除
    if ch.overrides:
        # 检查覆写数量上限（每章最多 3 处）
        if len(ch.overrides) > 3:
            add("override_limit", "minor", 0, "",
                f"合理覆写{len(ch.overrides)}处 > 上限3——超出部分不生效")
        # 过滤：如果问题的行号在被覆写的行号集合中，且规则名匹配，则移除；v2.3：L0 红线不可覆写（修复越级豁免漏洞）
        filtered_issues = []
        for iss in issues:
            rule = iss["rule"]
            line = iss.get("line", 0)
            if iss.get("level") != "L0" and line > 0 and rule in ch.override_rules and line in ch.override_rules[rule]:
                continue  # 被覆写，跳过
            filtered_issues.append(iss)
        issues = filtered_issues

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

def cross_chapter(chapters, cfg, disabled, rule_levels=None, characters_dir=None):
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
    # v2.5 新增：跨章重复短语检测（8-20字片段，按逗号/顿号/分号切分）
    phrase_map = {}
    for c in chapters:
        for seg in re.split(r"[，、；,;]", c.text):
            seg = seg.strip().strip("""”"'"「」""")
            if cfg["recurring_phrase_min_len"] <= han_len(seg) <= 20:
                phrase_map.setdefault(seg, set()).add(c.name)
    for phrase, where in sorted(phrase_map.items()):
        total = sum(1 for c in chapters if phrase in c.text)
        if total > cfg["recurring_phrase_max_across"]:
            add("recurring_phrase", "minor",
                "/".join(sorted(where)), phrase,
                f"跨章重复短语'{phrase}'在{len(where)}章中出现{total}次 > 上限{cfg['recurring_phrase_max_across']}")
    # v2.5b 新增：N-gram 跨章重复检测（4-10字连续汉字序列，补充短短语检测）
    # 解决按标点切分无法检测"手没抖""一声压着一声"等短短语跨章重复的问题
    ngram_min = cfg.get("recurring_ngram_min_len", 4)
    ngram_max_across = cfg.get("recurring_ngram_max_across", 2)
    ngram_map = {}
    for c in chapters:
        seen_in_ch = set()
        for m in re.finditer(r"[\u4e00-\u9fff]{%d,10}" % ngram_min, c.text):
            ng = m.group()
            if ng not in seen_in_ch:
                seen_in_ch.add(ng)
                ngram_map.setdefault(ng, set()).add(c.name)
    # 过滤常见虚词开头/结尾的无意义片段
    bad_starts = set("的了着过在地")
    bad_ends = set("的他她它在地")
    for ngram, where in sorted(ngram_map.items(), key=lambda x: -len(x[0])):
        if ngram[0] in bad_starts or ngram[-1] in bad_ends:
            continue
        total = sum(1 for c in chapters if ngram in c.text)
        if total > ngram_max_across:
            # 排除已被更长 N-gram 包含的短 N-gram（避免重复报告）
            already_reported = any(
                ngram in longer and longer != ngram
                for longer, lw in ngram_map.items()
                if len(longer) > len(ngram) and len(lw) >= 2 and ngram in longer
            )
            if not already_reported:
                add("recurring_phrase", "minor",
                    "/".join(sorted(where)), ngram,
                    f"跨章重复短语'{ngram}'在{len(where)}章中出现{total}次 > 上限{ngram_max_across}")
    # v2.5 新增：角色签名台词频率检测（需 --characters 参数）
    if characters_dir and os.path.isdir(characters_dir):
        for char_file in glob.glob(os.path.join(characters_dir, "*.json")):
            try:
                char_data = json.load(open(char_file, encoding="utf-8"))
            except Exception:
                continue
            sig_lines = char_data.get("language_fingerprint", {}).get("signature_lines", [])
            for sig in sig_lines:
                sig_text = re.sub(r"[「」""\"\"']", "", sig).strip()
                if han_len(sig_text) < 4:
                    continue
                # v2.5b 修复：自适应窗口——章节数<5时用实际章节数
                window_size = min(5, len(chapters))
                if window_size < 2:
                    continue
                for i in range(len(chapters) - window_size + 1):
                    window = chapters[i:i+window_size]
                    count = sum(1 for c in window if sig_text in c.text)
                    if count > cfg["signature_line_max_per_5ch"]:
                        add("signature_line_freq", "minor",
                            window[0].name, sig_text,
                            f"签名台词'{sig_text}'{window_size}章窗口内出现{count}次 > 上限{cfg['signature_line_max_per_5ch']}")
                        break
    return issues

def main():
    ap = argparse.ArgumentParser(description="网文文风 lint（write-assistant 流水线前置校验）")
    ap.add_argument("path", help="章节文件或目录")
    ap.add_argument("--json", help="输出交接卡 JSON 路径")
    ap.add_argument("--config", help="阈值配置 JSON 路径")
    ap.add_argument("--style", help="风格包名（加载 lint_overlay.json）")
    ap.add_argument("--styles-root", default=".trae/skills/writer-styles", help="风格包根目录")
    ap.add_argument("--characters", help="角色卡目录（启用签名台词频率检测）")
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
                       if (f.endswith(".txt") or f.endswith(".md")) and re.search(r"\d+", f))
    else:
        files = [args.path]
    chapters = [Chapter(f, open(f, encoding="utf-8-sig", errors="ignore").read()) for f in files]
    if not chapters:
        print("未找到章节文件"); sys.exit(2)

    all_issues, time_report = [], {}
    all_overrides = []  # v2.2: 收集所有章节的覆写记录
    for ch in chapters:
        iss, th = lint_chapter(ch, cfg, disabled, custom_bans, rule_levels)
        all_issues += iss
        if th: time_report[ch.name] = th
        if ch.overrides:
            for ov in ch.overrides:
                all_overrides.append({"chapter": ch.name, "rule": ov["rule"], "reason": ov["reason"], "line": ov["line"], "text": ov.get("text", "")[:50]})
    if len(chapters) > 1:
        all_issues += cross_chapter(chapters, cfg, disabled, cross_rule_levels, args.characters)

    # v2.3（框架升级 F1）：退出码只看 L0 critical；L1 critical 降级为顾问项，报告但不阻断
    blocking = [i for i in all_issues if i.get("level") == "L0" and i["severity"] == "critical"]
    advisory = [i for i in all_issues if i.get("level") == "L1" and i["severity"] == "critical"]
    non_blocking = [i for i in all_issues if i not in blocking and i not in advisory]
    status = "fail" if blocking else "pass"

    # 按 level 分组统计
    by_level = {}
    for i in all_issues:
        lv = i.get("level", "L3")
        by_level.setdefault(lv, []).append(i)

    print(f"\n{'='*56}\n文风 lint 结果：{status.upper()}{style_note}")
    print(f"  阻断项（L0 critical）：{len(blocking)}  |  顾问项（L1 critical，需审核员逐条回应）：{len(advisory)}  |  非阻断项：{len(non_blocking)}\n{'='*56}")
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
                "blocking_count": len(blocking), "advisory_count": len(advisory), "non_blocking_count": len(non_blocking),
                "issues": all_issues, "timeline_clues": time_report, "config": cfg,
                "advisory": advisory, "overrides": all_overrides}
        json.dump(card, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n交接卡已写入：{args.json}")
    if all_overrides:
        print(f"\n{'-'*56}\n合理覆写记录（供审核员复核）：")
        for ov in all_overrides:
            print(f"  {ov['chapter']}:L{ov['line']}  规则={ov['rule']}  理由={ov['reason']}")
            if ov['text']:
                print(f"    段落：{ov['text']}")
    sys.exit(1 if blocking else 0)

if __name__ == "__main__":
    main()
