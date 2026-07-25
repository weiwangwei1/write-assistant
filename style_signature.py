#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
style_signature.py — 作者签名手法自动提取（P1-1）

通过 N-gram 频率交叉对比，自动发现：
1. 签名短语：该作者显著偏好的 2-4字实词短语（频率比 > 阈值）
2. 回避词：其他作者常用但该作者几乎不用的短语（建议加入 custom_ban_words）
3. 意象偏好：Top-30 高频实词 N-gram
4. 感官通道分布：视/听/嗅/触/味五通道频率

基线策略：交叉对比——用其他作者原作合并作为"通用基线"。
需要至少 2 位作者的原作才能运行。

用法：
  python style_signature.py extract --author yanyujiangnan
  python style_signature.py extract --all
  python style_signature.py extract --author jinhezai --json signature_jinhezai.json
  python style_signature.py compare yanyujiangnan jiangnan  # 对比两位作者差异

退出码：0=成功  2=错误（原作不足等）
"""
import re, os, sys, json, argparse, math
from collections import Counter

# 功能词（单字），N-gram 中包含这些字的跳过，只保留纯实词
STOP_CHARS = set("的了是在他她我你也都就又还与和或着过把被向从但而却只已曾将一这那其之于以所对给让使到地得不什么怎么这个那个些每各某此彼")

# 感官词表
SENSORY_WORDS = {
    "视觉": ["光", "亮", "影", "色", "红", "黑", "金", "灰", "白", "暗", "闪烁", "光芒", "视线", "目光", "瞳", "焰", "辉", "芒", "晃", "耀", "斑", "明"],
    "听觉": ["声", "响", "音", "砰", "咔", "嗒", "吱", "嗡", "轰", "鸣", "嘶", "吼", "叫", "喊", "低语", "回响", "叹息", "寂静", "喧嚣", "嘈杂", "哗"],
    "嗅觉": ["味", "腥", "香", "臭", "气息", "烟味", "焦", "腐", "霉", "铁锈", "血腥", "刺鼻", "芬芳", "恶臭"],
    "触觉": ["凉", "热", "烫", "冷", "寒", "温", "冰", "暖", "刺", "麻", "痛", "痒", "滑", "粗糙", "颤", "抖", "酥", "僵", "黏"],
    "味觉": ["甜", "苦", "酸", "咸", "涩", "辣", "鲜"],
}

def han_count(s):
    return sum(1 for c in s if '\u4e00' <= c <= '\u9fff')

def load_author_texts(styles_root):
    """扫描所有作者的原作，返回 {author_name: combined_text}
    优先读取 原作_utf8/（UTF-8编码），回退到 原作/（可能GB18030）"""
    authors = {}
    if not os.path.isdir(styles_root):
        print(f"风格包根目录不存在：{styles_root}")
        return authors
    for name in sorted(os.listdir(styles_root)):
        # 优先使用 原作_utf8/，回退到 原作/
        ref_dir = os.path.join(styles_root, name, "reference", "原作_utf8")
        if not os.path.isdir(ref_dir):
            ref_dir = os.path.join(styles_root, name, "reference", "原作")
        if not os.path.isdir(ref_dir):
            continue
        texts = []
        for fname in sorted(os.listdir(ref_dir)):
            if not fname.endswith(".txt"):
                continue
            if "_sample" in fname:
                continue  # 跳过样本文件
            fpath = os.path.join(ref_dir, fname)
            try:
                text = open(fpath, encoding="utf-8-sig", errors="ignore").read()
                texts.append(text)
            except Exception as e:
                print(f"  警告：读取 {fpath} 失败：{e}")
        if texts:
            authors[name] = "\n".join(texts)
            chars = han_count(authors[name])
            print(f"  {name}: {len(texts)}篇, {chars}字")
    return authors

def extract_ngrams(text, n_range=(2, 3, 4)):
    """提取纯实词 N-gram 频率表"""
    chunks = re.findall(r"[\u4e00-\u9fff]+", text)
    freq = Counter()
    for chunk in chunks:
        for n in range(n_range[0], n_range[1] + 1):
            for i in range(len(chunk) - n + 1):
                gram = chunk[i:i + n]
                if any(c in STOP_CHARS for c in gram):
                    continue
                freq[gram] += 1
    return freq

def extract_sensory(text):
    """提取感官通道分布（每千字）"""
    total = max(1, han_count(text))
    result = {}
    for ch_name, words in SENSORY_WORDS.items():
        cnt = sum(text.count(w) for w in words)
        result[ch_name] = round(cnt / total * 1000, 3)
    return result

def cmd_extract(args):
    styles_root = args.styles_root
    authors = load_author_texts(styles_root)
    if len(authors) < 2:
        print("需要至少2位作者的原作才能进行交叉对比（当前不足）")
        sys.exit(2)

    target_authors = [args.author] if args.author and not args.all else sorted(authors.keys())
    if args.author and args.author not in authors:
        print(f"作者 {args.author} 无原作或不存在")
        sys.exit(2)

    all_results = {}
    for target in target_authors:
        if target not in authors:
            print(f"  跳过 {target}（无原作）")
            continue

        target_text = authors[target]
        target_total = max(1, han_count(target_text))
        target_freq = extract_ngrams(target_text)

        # 构建"其他作者合并"基线
        others_text = "\n".join(text for name, text in authors.items() if name != target)
        others_total = max(1, han_count(others_text))
        others_freq = extract_ngrams(others_text)

        # 签名短语：频率比 > 3 且出现 > 5次
        signatures = []
        for gram, count in target_freq.most_common(500):
            if count < 5:
                continue
            target_per_1k = count / target_total * 1000
            others_count = others_freq.get(gram, 0)
            others_per_1k = others_count / others_total * 1000
            if others_per_1k < 0.01:  # 其他作者几乎不用
                ratio = float('inf') if target_per_1k > 0.01 else 0
            else:
                ratio = target_per_1k / others_per_1k
            if ratio > 3.0:
                signatures.append({
                    "phrase": gram,
                    "count": count,
                    "per_1000": round(target_per_1k, 3),
                    "others_per_1000": round(others_per_1k, 3),
                    "ratio": round(ratio, 1) if ratio != float('inf') else 999.9,
                })

        # 回避词：其他作者高频(>10次)但当前作者几乎不用(<=1次)
        avoided = []
        for gram, count in others_freq.most_common(500):
            if count < 10:
                continue
            target_count = target_freq.get(gram, 0)
            if target_count <= 1:
                others_per_1k = count / others_total * 1000
                avoided.append({
                    "phrase": gram,
                    "others_count": count,
                    "others_per_1000": round(others_per_1k, 3),
                    "target_count": target_count,
                })

        # 意象 Top-30
        imagery = []
        for gram, count in target_freq.most_common(30):
            imagery.append({
                "word": gram,
                "count": count,
                "per_1000": round(count / target_total * 1000, 3),
            })

        # 感官通道
        sensory = extract_sensory(target_text)

        result = {
            "author": target,
            "sample_chars": target_total,
            "signature_phrases": signatures[:30],
            "avoided_phrases": avoided[:20],
            "imagery_top30": imagery,
            "sensory_distribution": sensory,
        }
        all_results[target] = result

        # 打印摘要
        print(f"\n{'='*56}")
        print(f"作者签名报告：{target}（{target_total}字）")
        print(f"{'='*56}")
        print(f"\n签名短语（Top 15）：")
        for s in signatures[:15]:
            print(f"  {s['phrase']:8s}  {s['count']:4d}次  {s['per_1000']:.2f}/千字  "
                  f"比值{s['ratio']:.1f}x  (其他作者{s['others_per_1000']:.3f}/千字)")
        print(f"\n回避词（Top 10，建议加入 custom_ban_words）：")
        for a in avoided[:10]:
            print(f"  {a['phrase']:8s}  其他作者{a['others_count']:4d}次  "
                  f"本作者{a['target_count']}次")
        print(f"\n意象 Top 15：")
        for im in imagery[:15]:
            print(f"  {im['word']:8s}  {im['count']:4d}次  {im['per_1000']:.2f}/千字")
        print(f"\n感官通道分布（/千字）：")
        for ch, val in sorted(sensory.items(), key=lambda x: -x[1]):
            bar = "#" * int(val * 2)
            print(f"  {ch:4s}  {val:6.2f}  {bar}")

    if args.json:
        output = all_results if args.all else all_results.get(args.author, all_results)
        json.dump(output, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n签名报告已写入：{args.json}")


def cmd_compare(args):
    """对比两位作者的签名差异"""
    styles_root = args.styles_root
    authors = load_author_texts(styles_root)
    if args.author1 not in authors or args.author2 not in authors:
        print(f"需要两位作者的原作（{args.author1} 和 {args.author2}）")
        sys.exit(2)

    freq1 = extract_ngrams(authors[args.author1])
    freq2 = extract_ngrams(authors[args.author2])
    total1 = max(1, han_count(authors[args.author1]))
    total2 = max(1, han_count(authors[args.author2]))

    # 合并词表
    all_grams = set(freq1.keys()) | set(freq2.keys())
    diffs = []
    for gram in all_grams:
        c1 = freq1.get(gram, 0)
        c2 = freq2.get(gram, 0)
        if c1 + c2 < 5:
            continue
        p1 = c1 / total1 * 1000
        p2 = c2 / total2 * 1000
        if p1 < 0.01 and p2 < 0.01:
            continue
        # 差异度 = |p1-p2| / max(p1,p2)
        diff = abs(p1 - p2) / max(p1, p2, 0.01)
        diffs.append((gram, c1, c2, p1, p2, diff))

    diffs.sort(key=lambda x: -x[5])

    print(f"\n{'='*56}")
    print(f"作者对比：{args.author1} vs {args.author2}")
    print(f"{'='*56}")
    print(f"\n{args.author1} 独有高频（对方几乎不用）：")
    count = 0
    for gram, c1, c2, p1, p2, diff in diffs:
        if c2 <= 1 and p1 > 0.5:
            print(f"  {gram:8s}  {args.author1}:{c1:4d}次({p1:.2f}/千字)  {args.author2}:{c2}次")
            count += 1
            if count >= 15:
                break
    print(f"\n{args.author2} 独有高频（对方几乎不用）：")
    count = 0
    for gram, c1, c2, p1, p2, diff in diffs:
        if c1 <= 1 and p2 > 0.5:
            print(f"  {gram:8s}  {args.author1}:{c1}次  {args.author2}:{c2:4d}次({p2:.2f}/千字)")
            count += 1
            if count >= 15:
                break


def cmd_vocabulary(args):
    """P2-3: 生成签名短语词库，供 style_card 注入"""
    styles_root = args.styles_root
    authors = load_author_texts(styles_root)
    if args.author not in authors:
        print(f"作者 {args.author} 无原作或不存在"); sys.exit(2)

    target_text = authors[args.author]
    target_total = max(1, han_count(target_text))
    target_freq = extract_ngrams(target_text)

    others_text = "\n".join(text for name, text in authors.items() if name != args.author)
    others_total = max(1, han_count(others_text))
    others_freq = extract_ngrams(others_text)

    # 签名短语（排除角色名——通过长度>=2且不是常见名字模式来过滤）
    signatures = []
    for gram, count in target_freq.most_common(500):
        if count < 5: continue
        target_per_1k = count / target_total * 1000
        others_count = others_freq.get(gram, 0)
        others_per_1k = others_count / others_total * 1000
        if others_per_1k < 0.01:
            ratio = 999.9
        else:
            ratio = target_per_1k / others_per_1k
        if ratio > 3.0:
            signatures.append({"phrase": gram, "per_1000": round(target_per_1k, 3),
                               "ratio": ratio if ratio != 999.9 else 999.9})

    # 回避词
    avoided = []
    for gram, count in others_freq.most_common(500):
        if count < 10: continue
        target_count = target_freq.get(gram, 0)
        if target_count <= 1:
            avoided.append({"phrase": gram, "others_per_1000": round(count / others_total * 1000, 3)})

    # 感官通道
    sensory = extract_sensory(target_text)

    # 生成词汇表 JSON
    vocab = {
        "card_type": "style_vocabulary",
        "author": args.author,
        "generated_from_chars": target_total,
        "signature_phrases_top20": signatures[:20],
        "avoided_phrases_top10": avoided[:10],
        "imagery_top20": [{"word": w, "per_1000": round(c / target_total * 1000, 3)}
                          for w, c in target_freq.most_common(20)],
        "sensory_reference": sensory,
        "usage_note": "本词库由 style_signature.py 自动生成，可注入 style_card.md 作为写手词汇参考。"
                       "签名短语=该作者显著偏好的表达；回避词=其他作者常用但本作者几乎不用的表达；"
                       "意象Top20=高频实词，反映作者关注的核心概念。",
    }

    # 输出路径：风格包目录下 vocabulary.json
    out_path = args.out or os.path.join(styles_root, args.author, "vocabulary.json")
    json.dump(vocab, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"\n词库已生成：{out_path}（{args.author}，基于{target_total}字原作）")
    print(f"\n签名短语 Top 10：")
    for s in signatures[:10]:
        print(f"  {s['phrase']:8s}  {s['per_1000']:.2f}/千字  比值{s['ratio']:.1f}x")
    print(f"\n回避词 Top 5：")
    for a in avoided[:5]:
        print(f"  {a['phrase']:8s}  其他作者{a['others_per_1000']:.2f}/千字")
    print(f"\n感官参考：{', '.join(f'{k}:{v:.2f}' for k, v in sorted(sensory.items(), key=lambda x: -x[1]))}")


def main():
    ap = argparse.ArgumentParser(description="作者签名手法自动提取（P1-1）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="提取作者签名")
    e.add_argument("--author", help="指定作者名（不指定则提取所有）")
    e.add_argument("--all", action="store_true", help="提取所有作者")
    e.add_argument("--json", help="输出 JSON 报告路径")
    e.add_argument("--styles-root", default=".trae/skills/writer-styles", help="风格包根目录")

    c = sub.add_parser("compare", help="对比两位作者差异")
    c.add_argument("author1", help="作者1")
    c.add_argument("author2", help="作者2")
    c.add_argument("--styles-root", default=".trae/skills/writer-styles", help="风格包根目录")

    v = sub.add_parser("vocabulary", help="P2-3: 生成签名短语词库（供 style_card 注入）")
    v.add_argument("--author", required=True, help="作者名")
    v.add_argument("--out", help="输出路径（默认：风格包/vocabulary.json）")
    v.add_argument("--styles-root", default=".trae/skills/writer-styles", help="风格包根目录")

    args = ap.parse_args()
    if args.cmd == "extract":
        if not args.author and not args.all:
            args.all = True
        cmd_extract(args)
    elif args.cmd == "compare":
        cmd_compare(args)
    elif args.cmd == "vocabulary":
        cmd_vocabulary(args)


if __name__ == "__main__":
    main()
