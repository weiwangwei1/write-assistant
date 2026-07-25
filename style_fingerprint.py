#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
style_fingerprint.py — 文体指纹提取与校验（write-assistant 风格包基建）

对应《自主蒸馏方法论v2》阶段1（指纹提取）与阶段4（指纹校验）：
用数据而非感觉判断"像不像"。

用法：
  # 蒸馏期：从原作构建基线（必须用原作，禁止用蒸馏产物/AI文本）
  python style_fingerprint.py build 原作1.txt 原作2.txt --author 辰东 \
      --out fingerprint.json

  # 量产期：校验生成章节与基线的偏差
  python style_fingerprint.py check chapter_013.txt --baseline fingerprint.json \
      [--json style_check.json]

退出码：check 模式 0=通过 1=偏差超阈 2=基线不可用
"""
import re, os, sys, json, math, argparse, unicodedata
from datetime import datetime
from collections import Counter

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
# N-gram 停用字（虚词/代词/连词等，只保留实词意象）
STOP_CHARS_NGRAM = set("的了是在他她我你也都就又还与和或着过把被向从但而却只已曾将一这那其之于以所对给让使到地得不什么怎么这个那个些每各某此彼")

# 各维度默认容差（相对偏差），可在 baseline 里覆盖
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
}

# P2-2: 维度失败自动建议——闭合"检测→修复"回路
DIMENSION_ADVICE = {
    "func_words_cosine": "功能词分布偏差——检查'了/着/的/是'等虚词频率。烟雨江南：了≤25/千字、着≤9/千字、书面连词≥5/千字。改法：把'他点燃了灯。'式的了字收尾改为连词衔接的流动句",
    "sent_len_mean": "平均句长偏差——原作以长句为骨（27.78字）。用逗号串联分句形成流动长句，减少句号断句。段首优先用连词起段（不过/然而/虽然）",
    "sent_len_stdev": "句长变化幅度不够——需长短句交替形成节奏对比。一章至少有1个≥200字的长段（推理/氛围/动作），与短句形成节奏对比",
    "short_sent_ratio": "短句（≤8字）占比偏高——原作仅8.2%。将碎短句合并为复合长句，短句是稀缺武器一章最多1-2次用于重锤收束",
    "long_sent_ratio": "长句（>40字）占比偏低——原作占18.3%。用书面连词（不过/然而/虽然/而且）串联多个分句形成绵长复合句",
    "para_len_mean": "段落平均长度偏差——原作段落偏长（57字）。合并碎段，以两句段为主（原作34.6%），单句段≤40%",
    "short_para_ratio": "碎段（≤15字）占比偏高——减少单句段，合并为两句段",
    "dialogue_ratio": "对话占比偏差——烟雨江南风格对话占比25-35%。调整对话与叙述的配比，穿插引前引导（某某道：）",
    "comma_period_ratio": "逗句比偏差——原作逗号多于句号（比值2.157）。减少句号断句，用逗号串联分句形成流动感",
    "dash_per_1000": "破折号过多——烟雨江南几乎不用破折号（0.008/千字）。用逗号/句号替代破折号做插入或转折",
    "ellipsis_per_1000": "省略号过多——原作省略号0.646/千字。减少省略号使用，用动作节拍替代",
    "sensory_cosine": "感官通道分布偏差——检查视觉/听觉/触觉/嗅觉/味觉的配比。烟雨江南：视觉13.29>听觉4.39>触觉2.78>嗅觉0.94>味觉0.70",
    "metaphor_per_1000": "比喻密度过高——原作比喻仅0.294/千字（约2500字章节最多1处）。减少'像'字比喻，改为直接描写或以景写情。喻体优先取自故事世界本身的物质",
}

def han_count(s):
    return sum(1 for c in s if '一' <= c <= '鿿')

def split_sents(text):
    return [s for s in re.split(r"[。！？!?\n]+", text) if han_count(s) > 0]

def split_paras(text):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"): continue
        if re.match(r"^(第\d+章|字数|—{3,}|-{3,})", s): continue
        out.append(s)
    return out

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
    """P1-2: 统计比喻密度（像字比喻，排除非比喻用法）"""
    cnt = 0
    for m in re.finditer(r"像", body):
        tail = body[m.start():m.start()+3]
        if any(tail.startswith(w[:2]) for w in SIMILE_EXCLUDE_FP):
            continue
        cnt += 1
    return cnt

def extract_imagery_top(body, total, top_n=20):
    """P1-2: 提取 Top-N 意象实词（2-3字纯实词 N-gram）"""
    chunks = re.findall(r"[\u4e00-\u9fff]+", body)
    freq = Counter()
    for chunk in chunks:
        for n in (2, 3):
            for i in range(len(chunk) - n + 1):
                gram = chunk[i:i + n]
                if any(c in STOP_CHARS_NGRAM for c in gram):
                    continue
                freq[gram] += 1
    return [{"word": w, "count": c, "per_1000": round(c / total * 1000, 3)}
            for w, c in freq.most_common(top_n)]

def extract_features(text, author="", source=""):
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
    dialogue_chars = sum(han_count(p) for p in paras if re.search(r"[\"“「]", p))

    comma = body.count("，") + body.count(",")
    period = body.count("。")

    # P1-2: 语义维度
    sensory = extract_sensory_dist(body, total)
    metaphor_cnt = count_metaphors(body)
    imagery = extract_imagery_top(body, total)

    return {
        "author": author, "source": source,
        "sample_chars": total, "sample_sents": sents_n, "sample_paras": len(paras),
        "func_words_per_1000": fw,
        "sent_len_mean": round(mean_l, 2),
        "sent_len_stdev": round(math.sqrt(var), 2),
        "short_sent_ratio": round(sum(1 for l in sent_lens if l <= 8) / sents_n, 4),
        "long_sent_ratio": round(sum(1 for l in sent_lens if l > 40) / sents_n, 4),
        "para_len_mean": round(sum(para_lens) / max(1, len(paras)), 2),
        "short_para_ratio": round(sum(1 for l in para_lens if l <= 15) / max(1, len(paras)), 4),
        "dialogue_ratio": round(dialogue_chars / total, 4),
        "comma_period_ratio": round(comma / max(1, period), 3),
        "dash_per_1000": round((body.count("——") + body.count("—")) / total * 1000, 3),
        "ellipsis_per_1000": round(body.count("……") / total * 1000, 3),
        # P1-2: 语义维度
        "sensory_dist": sensory,
        "metaphor_per_1000": round(metaphor_cnt / total * 1000, 3),
        "imagery_top20": imagery,
    }

def cosine_dist(a, b):
    dot = sum(a[w] * b[w] for w in FUNC_WORDS)
    na = math.sqrt(sum(a[w] ** 2 for w in FUNC_WORDS)) or 1e-9
    nb = math.sqrt(sum(b[w] ** 2 for w in FUNC_WORDS)) or 1e-9
    return 1 - dot / (na * nb)

def cmd_build(args):
    text = ""
    for f in args.files:
        text += open(f, encoding="utf-8-sig", errors="ignore").read() + "\n"
    feats = extract_features(text, author=args.author, source=";".join(args.files))
    conf = "high" if feats["sample_chars"] >= 30000 else \
           "medium" if feats["sample_chars"] >= 10000 else "provisional"
    baseline = {
        "card_type": "style_fingerprint_baseline",
        "status": "ready" if conf != "provisional" else "provisional",
        "confidence": conf,
        "note": "样本不足3万字，建议用原作全本重建" if conf == "provisional" else "",
        "metrics": feats,
        "tolerance": dict(DEFAULT_TOLERANCE),
    }
    json.dump(baseline, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"基线已生成：{args.out}（{args.author}，样本{feats['sample_chars']}字，置信度 {conf}）")
    print(f"  句长 {feats['sent_len_mean']}±{feats['sent_len_stdev']}  短句占比 {feats['short_sent_ratio']*100:.1f}%  "
          f"对话占比 {feats['dialogue_ratio']*100:.1f}%  逗句比 {feats['comma_period_ratio']}  破折号/千字 {feats['dash_per_1000']}")
    # P1-2: 语义维度摘要
    sd = feats.get("sensory_dist", {})
    sd_str = "  ".join(f"{k}:{v:.2f}" for k, v in sorted(sd.items(), key=lambda x: -x[1]))
    print(f"  感官分布：{sd_str}")
    print(f"  比喻密度：{feats.get('metaphor_per_1000', 0):.3f}/千字")
    top5 = feats.get("imagery_top20", [])[:5]
    top5_str = ", ".join("{}({})".format(w["word"], w["count"]) for w in top5)
    print(f"  意象Top5：{top5_str}")

def cmd_check(args):
    base = json.load(open(args.baseline, encoding="utf-8"))
    if base.get("status") == "pending":
        print(f"基线 {args.baseline} 状态为 pending（原作指纹未构建），跳过校验"); sys.exit(2)
    text = "".join(open(f, encoding="utf-8-sig", errors="ignore").read() + "\n" for f in args.files)
    cur = extract_features(text)
    bm, tol = base["metrics"], {**DEFAULT_TOLERANCE, **base.get("tolerance", {})}

    dims, fails = [], []
    # 近零基线的相对偏差会失真（如破折号基线0.008/千字，差0.008即报偏差1.0）。
    # 对 *_per_1000 类指标引入最小量纲：|cur-base|/max(|base|, MIN_SCALE)，
    # MIN_SCALE=0.2/千字 ≈ 半次出现（按2500字/章计），低于此视为统计噪声。
    MIN_SCALE = {"dash_per_1000": 0.2, "ellipsis_per_1000": 0.2, "metaphor_per_1000": 0.2}
    def dim(name, cur_v, base_v, rel=True):
        if rel:
            dev = abs(cur_v - base_v) / max(abs(base_v), MIN_SCALE.get(name, 0.0) or 1e-9)
        else:
            dev = abs(cur_v - base_v)
        ok = dev <= tol.get(name, 0.35)
        dims.append({"dim": name, "current": cur_v, "baseline": base_v,
                     "deviation": round(dev, 4), "tolerance": tol.get(name), "pass": ok})
        if not ok: fails.append(name)

    dim("func_words_cosine", round(cosine_dist(cur["func_words_per_1000"], bm["func_words_per_1000"]), 4), 0.0, rel=False)
    for k in ["sent_len_mean", "sent_len_stdev", "short_sent_ratio", "long_sent_ratio",
              "para_len_mean", "short_para_ratio", "dialogue_ratio",
              "comma_period_ratio", "dash_per_1000", "ellipsis_per_1000"]:
        dim(k, cur[k], bm[k])

    # P1-2: 语义维度校验（旧基线无这些字段时自动跳过，向后兼容）
    if "sensory_dist" in bm:
        sc = round(sensory_cosine_dist(cur["sensory_dist"], bm["sensory_dist"]), 4)
        dim("sensory_cosine", sc, 0.0, rel=False)
    if "metaphor_per_1000" in bm:
        dim("metaphor_per_1000", cur["metaphor_per_1000"], bm["metaphor_per_1000"])
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
    if imagery_info:
        print(imagery_info)

    # P2-2: 失败维度自动建议
    advice_list = []
    if fails:
        print(f"\n  写作建议（针对{len(fails)}个失败维度）：")
        for fname in fails:
            advice = DIMENSION_ADVICE.get(fname, "")
            if advice:
                print(f"    [{fname}] {advice}")
                advice_list.append({"dim": fname, "advice": advice})

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
    MIN_SCALE_DRIFT = {"dash_per_1000": 0.2, "ellipsis_per_1000": 0.2, "metaphor_per_1000": 0.2}

    results = []
    for name, base in baselines.items():
        bm = base["metrics"]
        tol = {**DEFAULT_TOLERANCE, **base.get("tolerance", {})}
        fails = []
        total_dev = 0.0
        dim_count = 0

        fw_dev = cosine_dist(cur["func_words_per_1000"], bm["func_words_per_1000"])
        total_dev += fw_dev; dim_count += 1
        if fw_dev > tol.get("func_words_cosine", 0.08): fails.append("func_words_cosine")

        for k in ["sent_len_mean", "sent_len_stdev", "short_sent_ratio", "long_sent_ratio",
                  "para_len_mean", "short_para_ratio", "dialogue_ratio",
                  "comma_period_ratio", "dash_per_1000", "ellipsis_per_1000"]:
            if k not in bm: continue
            ms = MIN_SCALE_DRIFT.get(k, 0)
            dev = abs(cur[k] - bm[k]) / max(abs(bm[k]), ms or 1e-9)
            total_dev += dev; dim_count += 1
            if dev > tol.get(k, 0.35): fails.append(k)

        if "sensory_dist" in bm:
            sc = sensory_cosine_dist(cur["sensory_dist"], bm["sensory_dist"])
            total_dev += sc; dim_count += 1
            if sc > tol.get("sensory_cosine", 0.15): fails.append("sensory_cosine")
        if "metaphor_per_1000" in bm:
            ms = MIN_SCALE_DRIFT.get("metaphor_per_1000", 0)
            dev = abs(cur["metaphor_per_1000"] - bm["metaphor_per_1000"]) / max(abs(bm["metaphor_per_1000"]), ms or 1e-9)
            total_dev += dev; dim_count += 1
            if dev > tol.get("metaphor_per_1000", 0.50): fails.append("metaphor_per_1000")

        avg_dev = total_dev / max(1, dim_count)
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
    ap = argparse.ArgumentParser(description="文体指纹提取与校验")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="从原作构建基线")
    b.add_argument("files", nargs="+"); b.add_argument("--author", required=True); b.add_argument("--out", required=True)
    c = sub.add_parser("check", help="校验文本与基线偏差")
    c.add_argument("files", nargs="+"); c.add_argument("--baseline", required=True); c.add_argument("--json")
    d = sub.add_parser("check-drift", help="P2-1: 跨风格漂移检测——对所有基线跑偏差比对")
    d.add_argument("files", nargs="+")
    d.add_argument("--target", help="目标风格名（用于漂移判定）")
    d.add_argument("--styles-root", default=".trae/skills/writer-styles", help="风格包根目录")
    d.add_argument("--json", help="输出 JSON 报告路径")
    args = ap.parse_args()
    {"build": cmd_build, "check": cmd_check, "check-drift": cmd_check_drift}[args.cmd](args)

if __name__ == "__main__":
    main()
