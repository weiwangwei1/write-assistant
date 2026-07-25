#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
style_fingerprint.py — 文体指纹提取与校验（write-assistant 风格包基建）v2.0

对应《自主蒸馏方法论v2》阶段1（指纹提取）与阶段4（指纹校验）：
用数据而非感觉判断"像不像"。

用法：
  # 蒸馏期：从原作构建基线（必须用原作，禁止用蒸馏产物/AI文本）
  python style_fingerprint.py build 原作1.txt 原作2.txt --author 辰东 \
      --out fingerprint.json [--exclude-names 李察,千夜]

  # 量产期：校验生成章节与基线的偏差
  python style_fingerprint.py check chapter_013.txt --baseline fingerprint.json \
      [--json style_check.json]

  # 校准期（v2.0 新增）：用原作自己的章节验证容差区分效度
  python style_fingerprint.py selfcheck --baseline fingerprint.json [--samples 20]

  # 跨风格漂移检测
  python style_fingerprint.py check-drift chapter_013.txt --target yanyujiangnan

退出码：check 0=通过 1=偏差超阈 2=基线不可用；selfcheck 0=通过率达标 1=不达标 2=基线/原作不可用

v2.0（蒸馏体系改进 D1/D2/D3）变更：
  D2 口径修正：分句不再把换行当句号；破折号去重计数（v1 每个"——"被计3次）；
    对话占比按引号内字数（v1 按整段）；比喻补 仿佛/宛如/犹如/好似/如同/似的 标记（v1 只数"像"）；
    意象支持 --exclude-names 过滤角色名；新增 3 个句法维度——段首连词率/引前引导率/短句"了"收尾率。
  D1 统计基础：build 按章（或万字块）分组统计，产出各维度章际分布（mean/stdev/p5/p95），
    容差从原作自身波动推导（标量 max(默认, 2σ)，向量 max(默认, p95)），不再纯靠经验值。
  D3 建议动态化：失败维度建议由基线实际数值生成，不再写死单一作者。
"""
import re, os, sys, json, math, argparse
from datetime import datetime
from collections import Counter

METRIC_VERSION = "2.0"

FUNC_WORDS = ["的", "了", "在", "是", "不", "他", "她", "我", "你", "也",
              "都", "就", "又", "还", "与", "和", "或", "着", "过", "把",
              "被", "向", "从", "但", "而", "却", "只", "已", "曾", "将"]

# P1-2: 语义维度扩展——感官通道词表（与 style_signature.py 一致）
SENSORY_WORDS = {
    "视觉": ["光", "亮", "影", "色", "红", "黑", "金", "灰", "白", "暗", "闪烁", "光芒", "视线", "目光", "瞳", "焰", "辉", "芒", "晃", "耀", "斑", "明"],
    "听觉": ["声", "响", "音", "砰", "咔", "嗒", "吱", "嗡", "轰", "鸣", "嘶", "吼", "叫", "喊", "低语", "回响", "叹息", "寂静", "喧嚣", "嘈杂", "哗"],
    "嗅觉": ["味", "腥", "香", "臭", "气息", "烟味", "焦", "腐", "霉", "铁锈", "血腥", "刺鼻", "芬芳", "恶臭"],
    "触觉": ["凉", "热", "烫", "冷", "寒", "温", "冰", "暖", "刺", "麻", "痛", "痒", "滑", "粗糙", "颤", "抖", "酥", "僵", "黏"],
    "味觉": ["甜", "苦", "酸", "咸", "涩", "辣", "鲜"],
}
# 比喻排除词（像字非比喻用法，与 style_lint.py SIMILE_EXCLUDE 一致）
SIMILE_EXCLUDE_FP = ["画像", "雕像", "头像", "像样", "像话", "影像", "想像", "像章"]
# v2.0: 比喻标记扩展（v1 只数"像"，漏掉这些标记导致密度系统性低估）
METAPHOR_MARKERS = ["仿佛", "宛如", "犹如", "好似", "如同", "似的"]
# N-gram 停用字（虚词/代词/连词等，只保留实词意象）
STOP_CHARS_NGRAM = set("的了是在他她我你也都就又还与和或着过把被向从但而却只已曾将一这那其之于以所对给让使到地得不什么怎么这个那个些每各某此彼")
# v2.0: 段首连词（书面连词起段是长句风格的黏合剂）
CONJ_STARTERS = ("不过", "然而", "虽然", "而且", "于是", "所以", "只是", "甚至",
                 "毕竟", "反而", "但", "而", "却", "已", "将", "与")

# 各维度默认容差（相对偏差），可在 baseline 里覆盖；v2.0 起 build 会从章际波动推导并写入 baseline
DEFAULT_TOLERANCE = {
    "func_words_cosine": 0.08,      # 功能词向量余弦距离上限
    "sent_len_mean": 0.25,          # 平均句长相对偏差
    "sent_len_stdev": 0.35,
    "short_sent_ratio": 0.35,       # 短句占比相对偏差
    "long_sent_ratio": 0.50,
    "para_len_mean": 0.35,
    "short_para_ratio": 0.35,
    "dialogue_ratio": 0.40,
    "comma_period_ratio": 0.35,
    "dash_per_1000": 0.60,
    "ellipsis_per_1000": 0.60,
    # P1-2: 语义维度容差
    "sensory_cosine": 0.15,         # 感官通道分布余弦距离上限
    "metaphor_per_1000": 0.50,      # 比喻密度相对偏差
    # v2.0: 句法维度容差
    "conjunction_starter_ratio": 0.50,
    "dialogue_guide_per_1000": 0.60,
    "le_ending_ratio": 0.50,
}

# 校验的标量维度（顺序即报告顺序）
SCALAR_DIMS = ["sent_len_mean", "sent_len_stdev", "short_sent_ratio", "long_sent_ratio",
               "para_len_mean", "short_para_ratio", "dialogue_ratio",
               "comma_period_ratio", "dash_per_1000", "ellipsis_per_1000",
               "metaphor_per_1000",
               "conjunction_starter_ratio", "dialogue_guide_per_1000", "le_ending_ratio"]

# 近零基线的相对偏差会失真（如破折号基线0.008/千字，差0.008即报偏差1.0）。
# 对近零指标引入最小量纲：|cur-base|/max(|base|, MIN_SCALE)，低于量纲视为统计噪声。
MIN_SCALE = {"dash_per_1000": 0.2, "ellipsis_per_1000": 0.2, "metaphor_per_1000": 0.2,
             "dialogue_guide_per_1000": 0.5,
             "short_sent_ratio": 0.02, "long_sent_ratio": 0.02, "short_para_ratio": 0.02,
             "dialogue_ratio": 0.02, "le_ending_ratio": 0.02, "conjunction_starter_ratio": 0.02}

# D3: 修复建议模板（通用改法，数值由基线动态填充——不再写死单一作者）
ADVICE_FIX = {
    "func_words_cosine": "检查'了/着/的/是'等虚词频率是否贴近基线方向。改法：短促的'了'字收尾句与连词衔接的流动句互相换算",
    "sent_len_mean": "用逗号串联分句形成流动长句，或拆长句为短句（按偏差方向）。段首优先用连词起段（不过/然而/虽然）",
    "sent_len_stdev": "长短句交替形成节奏对比。一章至少有1个≥200字的长段（推理/氛围/动作），与短句形成对比",
    "short_sent_ratio": "碎短句合并为复合长句；短句是稀缺武器，只在重音处使用",
    "long_sent_ratio": "用书面连词（不过/然而/虽然/而且）串联多个分句形成绵长复合句，或反向拆分（按偏差方向）",
    "para_len_mean": "合并碎段或拆分长段（按偏差方向），注意两句段与单句段的配比",
    "short_para_ratio": "减少单句段，合并为两句段",
    "dialogue_ratio": "调整对话与叙述配比；穿插引前引导（某某道：）保持对话现场感",
    "comma_period_ratio": "逗号与句号配比偏差——用逗号串联分句增加流动感，或增加句号断句提升力度（按偏差方向）",
    "dash_per_1000": "破折号密度偏差——按基线方向调整：多用逗号/句号替代，或恢复破折号的插入/转折用法",
    "ellipsis_per_1000": "省略号密度偏差——按基线方向调整，可用动作节拍替代",
    "sensory_cosine": "感官通道配比偏差——检查视/听/嗅/触/味五通道分布是否贴近基线",
    "metaphor_per_1000": "比喻密度偏差——按基线方向增减；喻体优先取自故事世界本身的物质",
    "conjunction_starter_ratio": "段首连词率偏差——段首用连词起段（不过/然而/虽然）是长句风格的黏合剂，按基线方向调整",
    "dialogue_guide_per_1000": "引前引导（某某道：）密度偏差——全裸对话与引前引导的配比按基线方向调整",
    "le_ending_ratio": "短句'了'收尾率偏差——'他点燃了灯。'式的了字收尾改为连词衔接的流动句，或反向调整（按基线方向）",
}

def han_count(s):
    return sum(1 for c in s if '一' <= c <= '鿿')

def split_sents(text):
    """v2.0：只按句末标点分句，不再把换行当句号（v1 会把段长混入句长）"""
    return [s for s in re.split(r"[。！？!?]+", text) if han_count(s) > 0]

def split_paras(text):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"): continue
        if re.match(r"^(第\d+章|字数|—{3,}|-{3,})", s): continue
        out.append(s)
    return out

def split_chapters(text, min_chars=800):
    """v2.0：按章分组。优先按"第N章"标题切分；章数不足时按万字块切伪章（保证小样本也能统计组内分布）"""
    marks = [m.start() for m in re.finditer(r"(?m)^第[0-9零一二三四五六七八九十百千两]+章", text)]
    chunks = []
    if len(marks) >= 10:
        for i, st in enumerate(marks):
            en = marks[i + 1] if i + 1 < len(marks) else len(text)
            chunks.append(text[st:en])
    else:
        step = 10000
        chunks = [text[i:i + step] for i in range(0, len(text), step)]
    return [c for c in chunks if han_count(c) >= min_chars]

def extract_sensory_dist(body, total):
    """P1-2: 提取感官通道分布（每千字），返回 {通道: 频率}"""
    result = {}
    for ch_name, words in SENSORY_WORDS.items():
        cnt = sum(body.count(w) for w in words)
        result[ch_name] = round(cnt / total * 1000, 3)
    return result

def sensory_cosine_dist(a, b):
    """P1-2: 感官通道向量余弦距离（0=一致, 1=正交）"""
    channels = list(SENSORY_WORDS.keys())
    dot = sum(a.get(ch, 0) * b.get(ch, 0) for ch in channels)
    na = math.sqrt(sum(a.get(ch, 0) ** 2 for ch in channels)) or 1e-9
    nb = math.sqrt(sum(b.get(ch, 0) ** 2 for ch in channels)) or 1e-9
    return 1 - dot / (na * nb)

def count_metaphors(body):
    """P1-2 + v2.0: 统计比喻密度（"像"字 + 仿佛/宛如/犹如/好似/如同/似的，排除非比喻用法）"""
    cnt = 0
    for m in re.finditer(r"像", body):
        tail = body[m.start():m.start()+3]
        if any(tail.startswith(w[:2]) for w in SIMILE_EXCLUDE_FP):
            continue
        cnt += 1
    for w in METAPHOR_MARKERS:
        cnt += body.count(w)
    return cnt

def count_dash(body):
    """v2.0：破折号去重计数（v1 中每个"——"被 count("——")+count("—") 计 3 次）"""
    return len(re.findall(r"——", body)) + len(re.findall(r"(?<!—)—(?!—)", body))

def dialogue_char_count(body):
    """v2.0：对话字数按引号内文本计（v1 把含引号段落的整段都算对话）"""
    return sum(han_count(m.group(0)) for m in re.finditer(r"[“\"「][^”\"」]{0,500}[”\"」]", body))

def extract_imagery_top(body, total, top_n=20, exclude_names=None):
    """P1-2 + v2.0: 提取 Top-N 意象实词（2-3字纯实词 N-gram），支持角色名过滤"""
    chunks = re.findall(r"[一-鿿]+", body)
    freq = Counter()
    for chunk in chunks:
        for n in (2, 3):
            for i in range(len(chunk) - n + 1):
                gram = chunk[i:i + n]
                if any(c in STOP_CHARS_NGRAM for c in gram):
                    continue
                freq[gram] += 1
    if exclude_names:
        names = [w for w in exclude_names if w]
        freq = Counter({g: c for g, c in freq.items()
                        if not any(g in nm or nm in g for nm in names)})
    return [{"word": w, "count": c, "per_1000": round(c / total * 1000, 3)}
            for w, c in freq.most_common(top_n)]

def extract_features(text, author="", source="", exclude_names=None, with_imagery=True):
    paras = split_paras(text)
    body = "\n".join(paras)
    total = max(1, han_count(body))
    sents = split_sents(body)
    sent_lens = [han_count(s) for s in sents]

    fw = {w: round(body.count(w) / total * 1000, 3) for w in FUNC_WORDS}
    sents_n = max(1, len(sents))
    mean_l = sum(sent_lens) / sents_n
    var = sum((l - mean_l) ** 2 for l in sent_lens) / sents_n

    para_lens = [han_count(p) for p in paras]
    paras_n = max(1, len(paras))
    conj_starters = sum(1 for p in paras if p.startswith(CONJ_STARTERS))
    dialogue_guides = len(re.findall(r"(?:道|说|问|答)\s*[:：]\s*[\"“「]", body))
    le_endings = sum(1 for s, l in zip(sents, sent_lens) if 0 < l <= 15 and s.rstrip().endswith("了"))

    comma = body.count("，") + body.count(",")
    period = body.count("。")

    # P1-2: 语义维度
    sensory = extract_sensory_dist(body, total)
    metaphor_cnt = count_metaphors(body)

    feats = {
        "author": author, "source": source,
        "sample_chars": total, "sample_sents": sents_n, "sample_paras": len(paras),
        "func_words_per_1000": fw,
        "sent_len_mean": round(mean_l, 2),
        "sent_len_stdev": round(math.sqrt(var), 2),
        "short_sent_ratio": round(sum(1 for l in sent_lens if l <= 8) / sents_n, 4),
        "long_sent_ratio": round(sum(1 for l in sent_lens if l > 40) / sents_n, 4),
        "para_len_mean": round(sum(para_lens) / paras_n, 2),
        "short_para_ratio": round(sum(1 for l in para_lens if l <= 15) / paras_n, 4),
        "dialogue_ratio": round(dialogue_char_count(body) / total, 4),
        "comma_period_ratio": round(comma / max(1, period), 3),
        "dash_per_1000": round(count_dash(body) / total * 1000, 3),
        "ellipsis_per_1000": round(body.count("……") / total * 1000, 3),
        # P1-2: 语义维度
        "sensory_dist": sensory,
        "metaphor_per_1000": round(metaphor_cnt / total * 1000, 3),
        # v2.0: 句法维度
        "conjunction_starter_ratio": round(conj_starters / paras_n, 4),
        "dialogue_guide_per_1000": round(dialogue_guides / total * 1000, 3),
        "le_ending_ratio": round(le_endings / sents_n, 4),
    }
    if with_imagery:
        feats["imagery_top20"] = extract_imagery_top(body, total, exclude_names=exclude_names)
    return feats

def cosine_dist(a, b):
    dot = sum(a[w] * b[w] for w in FUNC_WORDS)
    na = math.sqrt(sum(a[w] ** 2 for w in FUNC_WORDS)) or 1e-9
    nb = math.sqrt(sum(b[w] ** 2 for w in FUNC_WORDS)) or 1e-9
    return 1 - dot / (na * nb)

def percentile(vals, p):
    """线性插值分位数"""
    if not vals: return 0.0
    vs = sorted(vals)
    k = (len(vs) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(vs) - 1)
    return vs[lo] + (vs[hi] - vs[lo]) * (k - lo)

def rel_dev(name, cur_v, base_v):
    return abs(cur_v - base_v) / max(abs(base_v), MIN_SCALE.get(name, 0.0) or 1e-9)

def check_dims(cur, bm, tol):
    """逐维校验（check/selfcheck/check-drift 共用）。返回 (dims, fails)"""
    dims, fails = [], []
    def dim(name, cur_v, base_v, rel=True):
        dev = rel_dev(name, cur_v, base_v) if rel else abs(cur_v - base_v)
        ok = dev <= tol.get(name, 0.35)
        dims.append({"dim": name, "current": cur_v, "baseline": base_v,
                     "deviation": round(dev, 4), "tolerance": tol.get(name), "pass": ok})
        if not ok: fails.append(name)

    dim("func_words_cosine", round(cosine_dist(cur["func_words_per_1000"], bm["func_words_per_1000"]), 4), 0.0, rel=False)
    for k in SCALAR_DIMS:
        if k in bm and k in cur:
            dim(k, cur[k], bm[k])
    if "sensory_dist" in bm:
        dim("sensory_cosine", round(sensory_cosine_dist(cur["sensory_dist"], bm["sensory_dist"]), 4), 0.0, rel=False)
    return dims, fails

def make_advice(dims, fails):
    """D3: 由基线实际数值动态生成建议（不再写死单一作者）"""
    out = []
    by_name = {d["dim"]: d for d in dims}
    for fname in fails:
        d = by_name.get(fname, {})
        cur, base = d.get("current"), d.get("baseline")
        fix = ADVICE_FIX.get(fname, "按基线方向调整")
        if fname.endswith("_cosine"):
            head = f"{fname} 距离 {cur}（容差 {d.get('tolerance')}）"
        else:
            try:
                direction = "偏高" if float(cur) > float(base) else "偏低"
            except (TypeError, ValueError):
                direction = "偏差"
            head = f"{fname} {direction}——原作基线 {base}，当前 {cur}"
        out.append({"dim": fname, "advice": f"{head}。{fix}"})
    return out

def derive_tolerance(chapter_feats, pooled):
    """D1: 从章际分布推导容差——标量 max(默认, 2σ相对波动)；向量 max(默认, p95 距离)，封顶防过松"""
    stats = {}
    derived = dict(DEFAULT_TOLERANCE)
    source = {}

    for k in SCALAR_DIMS:
        vals = [f[k] for f in chapter_feats if k in f]
        if len(vals) < 5: continue
        mean = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
        p5, p95 = percentile(vals, 5), percentile(vals, 95)
        cv = sd / max(abs(mean), MIN_SCALE.get(k, 0.0) or 1e-9)
        stats[k] = {"mean": round(mean, 4), "stdev": round(sd, 4),
                    "p5": round(p5, 4), "p95": round(p95, 4), "cv": round(cv, 4)}
        tol = max(DEFAULT_TOLERANCE.get(k, 0.35), min(1.0, 2.0 * cv))
        derived[k] = round(tol, 3)
        source[k] = "derived_2cv" if 2.0 * cv > DEFAULT_TOLERANCE.get(k, 0.35) else "default_floor"

    for vec_dim, dist_fn in (("func_words_cosine",
                              lambda f: cosine_dist(f["func_words_per_1000"], pooled["func_words_per_1000"])),
                             ("sensory_cosine",
                              lambda f: sensory_cosine_dist(f["sensory_dist"], pooled["sensory_dist"]))):
        vals = [dist_fn(f) for f in chapter_feats]
        if len(vals) < 5: continue
        mean = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
        p95 = percentile(vals, 95)
        stats[vec_dim] = {"mean": round(mean, 4), "stdev": round(sd, 4),
                          "p5": round(percentile(vals, 5), 4), "p95": round(p95, 4)}
        tol = max(DEFAULT_TOLERANCE.get(vec_dim, 0.1), min(0.5, p95))
        derived[vec_dim] = round(tol, 3)
        source[vec_dim] = "derived_p95" if p95 > DEFAULT_TOLERANCE.get(vec_dim, 0.1) else "default_floor"

    return stats, derived, source

def cmd_build(args):
    text = ""
    for f in args.files:
        text += open(f, encoding="utf-8-sig", errors="ignore").read() + "\n"
    exclude = None
    if args.exclude_names:
        exclude = [w.strip() for w in args.exclude_names.split(",") if w.strip()]
    feats = extract_features(text, author=args.author, source=";".join(args.files),
                             exclude_names=exclude)
    conf = "high" if feats["sample_chars"] >= 30000 else \
           "medium" if feats["sample_chars"] >= 10000 else "provisional"

    # D1: 章际分布统计 + 派生容差
    chapters = split_chapters(text)
    chapter_stats, tolerance, tol_source = {}, dict(DEFAULT_TOLERANCE), {}
    if len(chapters) >= 5:
        chapter_feats = [extract_features(c, with_imagery=False) for c in chapters]
        chapter_stats, tolerance, tol_source = derive_tolerance(chapter_feats, feats)
        print(f"  章际统计：{len(chapters)} 个分组，容差已从组内波动推导")
    else:
        print(f"  ⚠ 有效分组不足（{len(chapters)}），容差使用默认经验值")

    baseline = {
        "card_type": "style_fingerprint_baseline",
        "metric_version": METRIC_VERSION,
        "status": "ready" if conf != "provisional" else "provisional",
        "confidence": conf,
        "note": "样本不足3万字，建议用原作全本重建" if conf == "provisional" else "",
        "metrics": feats,
        "n_groups": len(chapters),
        "chapter_stats": chapter_stats,
        "tolerance": tolerance,
        "tolerance_source": tol_source,
        "exclude_names": exclude or [],
    }
    json.dump(baseline, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"基线已生成：{args.out}（{args.author}，样本{feats['sample_chars']}字，置信度 {conf}，口径 v{METRIC_VERSION}）")
    print(f"  句长 {feats['sent_len_mean']}±{feats['sent_len_stdev']}  短句占比 {feats['short_sent_ratio']*100:.1f}%  "
          f"对话占比 {feats['dialogue_ratio']*100:.1f}%  逗句比 {feats['comma_period_ratio']}  破折号/千字 {feats['dash_per_1000']}")
    sd = feats.get("sensory_dist", {})
    sd_str = "  ".join(f"{k}:{v:.2f}" for k, v in sorted(sd.items(), key=lambda x: -x[1]))
    print(f"  感官分布：{sd_str}")
    print(f"  比喻密度：{feats.get('metaphor_per_1000', 0):.3f}/千字  段首连词率 {feats['conjunction_starter_ratio']*100:.1f}%  "
          f"引前引导 {feats['dialogue_guide_per_1000']}/千字  短句了收尾 {feats['le_ending_ratio']*100:.1f}%")
    top5 = feats.get("imagery_top20", [])[:5]
    top5_str = ", ".join("{}({})".format(w["word"], w["count"]) for w in top5)
    print(f"  意象Top5：{top5_str}")

def load_baseline(path):
    base = json.load(open(path, encoding="utf-8"))
    if base.get("status") == "pending":
        print(f"基线 {path} 状态为 pending（原作指纹未构建），跳过校验"); sys.exit(2)
    if base.get("metric_version") != METRIC_VERSION:
        print(f"  ⚠ 基线为旧口径 v{base.get('metric_version', '1.x')}，与当前脚本 v{METRIC_VERSION} 不一致，建议重建基线")
    return base

def cmd_check(args):
    base = load_baseline(args.baseline)
    text = "".join(open(f, encoding="utf-8-sig", errors="ignore").read() + "\n" for f in args.files)
    cur = extract_features(text)
    bm, tol = base["metrics"], {**DEFAULT_TOLERANCE, **base.get("tolerance", {})}

    dims, fails = check_dims(cur, bm, tol)

    # 意象重合度（信息性参考，不阻断 pass/fail）
    imagery_info = ""
    if "imagery_top20" in bm:
        base_words = {item["word"] for item in bm["imagery_top20"]}
        cur_words = {item["word"] for item in cur["imagery_top20"]}
        overlap = len(base_words & cur_words) / max(1, len(base_words))
        imagery_info = f"  ℹ 意象Top20重合度：{overlap*100:.0f}%（基线Top5: {', '.join(w['word'] for w in bm['imagery_top20'][:5])}）"

    status = "fail" if fails else "pass"
    print(f"\n风格指纹校验：{status.upper()}（基线：{base['metrics'].get('author','?')}，置信度 {base.get('confidence','?')}）")
    for d in dims:
        mark = "✓" if d["pass"] else "✗"
        print(f"  {mark} {d['dim']:22s} 当前 {d['current']:<10} 基线 {d['baseline']:<10} 偏差 {d['deviation']:.3f}（容差 {d['tolerance']}）")
    if base.get("confidence") == "provisional":
        print("  ⚠ 基线为 provisional（样本不足），此结果仅供趋势参考")
    if fails:
        print("  判读参考：原作章节自校验中 1-2 个轻微超阈属正常章际波动；≥3 个维度超阈或单维大幅超阈才需修复")
    if imagery_info:
        print(imagery_info)

    # D3: 失败维度建议（动态生成，数值取自基线）
    advice_list = make_advice(dims, fails)
    if advice_list:
        print(f"\n  写作建议（针对{len(advice_list)}个失败维度）：")
        for a in advice_list:
            print(f"    [{a['dim']}] {a['advice']}")

    if args.json:
        card = {"card_type": "style_fingerprint_check", "from_agent": "style_fingerprint(script)",
                "to_agent": "chapter-writer", "status": status, "baseline_ref": args.baseline,
                "baseline_confidence": base.get("confidence"), "failed_dims": fails, "dims": dims,
                "advice": advice_list}
        json.dump(card, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"交接卡已写入：{args.json}")

    # P0-1: 偏差日志记录（反馈闭环）——无论是否输出 json，都追加日志到 memory/style_deviation_log.jsonl
    log_path = os.path.join("memory", "style_deviation_log.jsonl")
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "chapter": os.path.basename(args.files[0]),
        "baseline": os.path.basename(args.baseline),
        "author": bm.get("author", ""),
        "status": status,
        "failed_dims": fails,
        "max_deviation": round(max((d["deviation"] for d in dims), default=0), 4),
        "dims": [{"dim": d["dim"], "deviation": d["deviation"], "pass": d["pass"]} for d in dims],
    }
    os.makedirs("memory", exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    print(f"偏差日志已追加：{log_path}")
    sys.exit(1 if fails else 0)

def cmd_selfcheck(args):
    """D1: 原作自校验——用原作自己的章节（块）跑 check，验证容差区分效度。
    原作章节应高比例通过；通过率低说明容差过紧（误伤）或口径有问题。"""
    base = load_baseline(args.baseline)
    sources = base["metrics"].get("source", "").split(";")
    sources = [s for s in sources if s and os.path.isfile(s)]
    if not sources:
        print("基线中未记录可用的原作路径（metrics.source），无法自校验"); sys.exit(2)
    text = "".join(open(f, encoding="utf-8-sig", errors="ignore").read() + "\n" for f in sources)
    chunks = split_chapters(text)
    if len(chunks) < 5:
        print(f"有效分组不足（{len(chunks)}），无法自校验"); sys.exit(2)

    n = min(args.samples, len(chunks))
    step = max(1, len(chunks) // n)
    sampled = chunks[::step][:n]

    bm, tol = base["metrics"], {**DEFAULT_TOLERANCE, **base.get("tolerance", {})}
    dim_pass = {}
    chunk_pass = 0
    for c in sampled:
        cur = extract_features(c, with_imagery=False)
        dims, fails = check_dims(cur, bm, tol)
        if not fails: chunk_pass += 1
        for d in dims:
            p, t = dim_pass.get(d["dim"], (0, 0))
            dim_pass[d["dim"]] = (p + (1 if d["pass"] else 0), t + 1)

    print(f"\n原作自校验：{base['metrics'].get('author','?')}（{len(sampled)}/{len(chunks)} 个分组）")
    print(f"  {'维度':26s} {'通过率':>8s} {'容差':>8s}")
    rates = []
    for name in sorted(dim_pass):
        p, t = dim_pass[name]
        rate = p / max(1, t)
        rates.append(rate)
        mark = "✓" if rate >= 0.7 else "✗"
        print(f"  {mark} {name:24s} {rate*100:7.0f}% {tol.get(name):>8}")
    overall = sum(rates) / max(1, len(rates))
    print(f"\n  整组通过：{chunk_pass}/{len(sampled)}（{chunk_pass/len(sampled)*100:.0f}%）  维度平均通过率：{overall*100:.0f}%")
    print("  判读：维度通过率 <70% 说明该维度容差过紧或口径有误，需复查；≥70% 为健康")
    sys.exit(0 if overall >= 0.8 and min(rates or [1]) >= 0.6 else 1)

def cmd_check_drift(args):
    """P2-1: 跨风格漂移检测——对章节跑所有可用基线，报告最接近风格和漂移风险"""
    styles_root = args.styles_root
    baselines = {}
    for name in sorted(os.listdir(styles_root)):
        fp = os.path.join(styles_root, name, "fingerprint.json")
        if os.path.isfile(fp):
            try:
                base = json.load(open(fp, encoding="utf-8"))
                if base.get("status") != "pending":
                    baselines[name] = base
            except Exception:
                pass
    if not baselines:
        print("未找到任何可用基线（fingerprint.json）"); sys.exit(2)

    text = "".join(open(f, encoding="utf-8-sig", errors="ignore").read() + "\n" for f in args.files)
    cur = extract_features(text)

    results = []
    for name, base in baselines.items():
        bm = base["metrics"]
        tol = {**DEFAULT_TOLERANCE, **base.get("tolerance", {})}
        dims, fails = check_dims(cur, bm, tol)
        avg_dev = sum(d["deviation"] for d in dims) / max(1, len(dims))
        results.append({
            "author": name, "avg_deviation": round(avg_dev, 4),
            "failed_count": len(fails), "failed_dims": fails,
            "confidence": base.get("confidence", "?"),
        })

    results.sort(key=lambda x: x["avg_deviation"])
    closest = results[0]

    print(f"\n{'='*56}")
    print(f"跨风格漂移检测：{os.path.basename(args.files[0])}")
    print(f"{'='*56}")
    print(f"\n  {'风格':16s} {'平均偏差':>8s} {'失败数':>6s} {'置信度':>8s}  状态")
    print(f"  {'-'*52}")
    for r in results:
        mark = "✓" if r["failed_count"] == 0 else "✗({})".format(r["failed_count"])
        tag = " ← 最接近" if r == closest else ""
        print(f"  {r['author']:16s} {r['avg_deviation']:8.4f} {r['failed_count']:6d} {r['confidence']:>8s}  {mark}{tag}")

    print(f"\n  最接近风格：{closest['author']}（平均偏差 {closest['avg_deviation']}）")
    if args.target:
        target_r = next((r for r in results if r["author"] == args.target), None)
        if target_r:
            if closest["author"] != args.target:
                print(f"  ⚠ 漂移警告：目标风格「{args.target}」不是最接近的！")
                print(f"      目标 {args.target} 偏差 {target_r['avg_deviation']} vs 最近 {closest['author']} 偏差 {closest['avg_deviation']}")
            else:
                print(f"  ✓ 目标风格「{args.target}」确认为最接近，无漂移")

    if args.json:
        out = {"chapter": os.path.basename(args.files[0]), "results": results,
               "closest": closest["author"]}
        if args.target:
            out["target"] = args.target
            out["drift"] = closest["author"] != args.target
        json.dump(out, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n报告已写入：{args.json}")

def main():
    # Windows GBK 控制台兼容：✓/✗ 等符号在 GBK 下会 UnicodeEncodeError，统一按 UTF-8 输出
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser(description="文体指纹提取与校验 v2.0")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="从原作构建基线（含章际分布与派生容差）")
    b.add_argument("files", nargs="+"); b.add_argument("--author", required=True); b.add_argument("--out", required=True)
    b.add_argument("--exclude-names", help="角色名过滤（逗号分隔），意象统计时剔除")
    c = sub.add_parser("check", help="校验文本与基线偏差")
    c.add_argument("files", nargs="+"); c.add_argument("--baseline", required=True); c.add_argument("--json")
    s = sub.add_parser("selfcheck", help="D1: 原作自校验——用原作自身章节验证容差区分效度")
    s.add_argument("--baseline", required=True)
    s.add_argument("--samples", type=int, default=20, help="抽样分组数（默认20）")
    d = sub.add_parser("check-drift", help="P2-1: 跨风格漂移检测——对所有基线跑偏差比对")
    d.add_argument("files", nargs="+")
    d.add_argument("--target", help="目标风格名（用于漂移判定）")
    d.add_argument("--styles-root", default=".trae/skills/writer-styles", help="风格包根目录")
    d.add_argument("--json", help="输出 JSON 报告路径")
    args = ap.parse_args()
    {"build": cmd_build, "check": cmd_check, "selfcheck": cmd_selfcheck, "check-drift": cmd_check_drift}[args.cmd](args)

if __name__ == "__main__":
    main()
