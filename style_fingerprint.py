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
from collections import Counter

FUNC_WORDS = ["的", "了", "在", "是", "不", "他", "她", "我", "你", "也",
              "都", "就", "又", "还", "与", "和", "或", "着", "过", "把",
              "被", "向", "从", "但", "而", "却", "只", "已", "曾", "将"]

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

def cmd_check(args):
    base = json.load(open(args.baseline, encoding="utf-8"))
    if base.get("status") == "pending":
        print(f"基线 {args.baseline} 状态为 pending（原作指纹未构建），跳过校验"); sys.exit(2)
    text = "".join(open(f, encoding="utf-8-sig", errors="ignore").read() + "\n" for f in args.files)
    cur = extract_features(text)
    bm, tol = base["metrics"], {**DEFAULT_TOLERANCE, **base.get("tolerance", {})}

    dims, fails = [], []
    def dim(name, cur_v, base_v, rel=True):
        dev = abs(cur_v - base_v) / (abs(base_v) or 1e-9) if rel else abs(cur_v - base_v)
        ok = dev <= tol.get(name, 0.35)
        dims.append({"dim": name, "current": cur_v, "baseline": base_v,
                     "deviation": round(dev, 4), "tolerance": tol.get(name), "pass": ok})
        if not ok: fails.append(name)

    dim("func_words_cosine", round(cosine_dist(cur["func_words_per_1000"], bm["func_words_per_1000"]), 4), 0.0, rel=False)
    for k in ["sent_len_mean", "sent_len_stdev", "short_sent_ratio", "long_sent_ratio",
              "para_len_mean", "short_para_ratio", "dialogue_ratio",
              "comma_period_ratio", "dash_per_1000", "ellipsis_per_1000"]:
        dim(k, cur[k], bm[k])

    status = "fail" if fails else "pass"
    print(f"\n风格指纹校验：{status.upper()}（基线：{base['metrics'].get('author','?')}，置信度 {base.get('confidence','?')}）")
    for d in dims:
        mark = "✓" if d["pass"] else "✗"
        print(f"  {mark} {d['dim']:22s} 当前 {d['current']:<10} 基线 {d['baseline']:<10} 偏差 {d['deviation']:.3f}（容差 {d['tolerance']}）")
    if base.get("confidence") == "provisional":
        print("  ⚠ 基线为 provisional（样本不足），此结果仅供趋势参考")

    if args.json:
        card = {"card_type": "style_fingerprint_check", "from_agent": "style_fingerprint(script)",
                "to_agent": "chapter-writer", "status": status, "baseline_ref": args.baseline,
                "baseline_confidence": base.get("confidence"), "failed_dims": fails, "dims": dims}
        json.dump(card, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"交接卡已写入：{args.json}")
    sys.exit(1 if fails else 0)

def main():
    ap = argparse.ArgumentParser(description="文体指纹提取与校验")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="从原作构建基线")
    b.add_argument("files", nargs="+"); b.add_argument("--author", required=True); b.add_argument("--out", required=True)
    c = sub.add_parser("check", help="校验文本与基线偏差")
    c.add_argument("files", nargs="+"); c.add_argument("--baseline", required=True); c.add_argument("--json")
    args = ap.parse_args()
    {"build": cmd_build, "check": cmd_check}[args.cmd](args)

if __name__ == "__main__":
    main()
