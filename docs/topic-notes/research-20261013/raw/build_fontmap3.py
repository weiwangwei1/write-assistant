# -*- coding: utf-8 -*-
"""精修映射：freetype 渲染 PUA 字形 → 与系统字体候选做特征匹配 → 贪心唯一分配"""
import json
import freetype
import numpy as np
from PIL import Image

BASE = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw'
FONT = BASE + r'\font_ttf.ttf'
REF = r'C:\Windows\Fonts\simhei.ttf'
SIZE = 48

def render_norm(face, codepoint, size=SIZE):
    face.load_char(codepoint, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_NORMAL)
    bmp = face.glyph.bitmap
    w, h = bmp.width, bmp.rows
    if w == 0 or h == 0:
        return None
    arr = np.array(bmp.buffer, dtype=np.uint8).reshape(h, bmp.pitch)[:, :w].astype(np.float32)
    ys, xs = np.nonzero(arr > 25)
    if len(ys) == 0:
        return None
    arr = arr[ys.min():ys.max()+1, xs.min():xs.max()+1]
    h2, w2 = arr.shape
    scale = (size - 8) / max(h2, w2)
    nh, nw = max(1, int(round(h2 * scale))), max(1, int(round(w2 * scale)))
    img = Image.fromarray(arr.astype(np.uint8)).resize((nw, nh), Image.LANCZOS)
    canvas = np.zeros((size, size), dtype=np.float32)
    oy, ox = (size - nh) // 2, (size - nw) // 2
    canvas[oy:oy+nh, ox:ox+nw] = np.asarray(img, dtype=np.float32)
    return canvas / 255.0

def best_iou(a, b, max_shift=4):
    ab = a > 0.55
    bb = b > 0.55
    best = 0.0
    for dy in range(-max_shift, max_shift+1):
        for dx in range(-max_shift, max_shift+1):
            b2 = np.roll(np.roll(bb, dy, axis=0), dx, axis=1)
            inter = np.logical_and(ab, b2).sum()
            union = np.logical_or(ab, b2).sum()
            if union > 0:
                v = inter / union
                if v > best:
                    best = v
    return best

def main():
    pua = json.load(open(BASE + r'\pua_chars.json', encoding='utf-8'))
    print('pua:', len(pua))
    fmain = freetype.Face(FONT)
    fref = freetype.Face(REF)
    fmain.set_pixel_sizes(0, 128)
    fref.set_pixel_sizes(0, 128)

    # 1) 渲染 PUA
    pua_mats = {}
    for h in pua:
        m = render_norm(fmain, int(h, 16))
        if m is not None:
            pua_mats[h] = m
    print('rendered pua:', len(pua_mats))

    # 2) 渲染候选：常用字表（GB2312 一级+二级）裁剪为常用 3500 字 + 常用符号
    cands = []
    for b1 in range(0xB0, 0xD8):  # GB2312 一级汉字 3755
        for b2 in range(0xA1, 0xFF):
            try:
                cands.append(bytes([b1, b2]).decode('gb2312'))
            except Exception:
                pass
    for b1 in range(0xD8, 0xF8):  # 二级汉字
        for b2 in range(0xA1, 0xFF):
            try:
                cands.append(bytes([b1, b2]).decode('gb2312'))
            except Exception:
                pass
    for c in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ，。！？、：；”“《》【】…—·（）~':
        cands.append(c)
    cands = list(dict.fromkeys(cands))
    print('candidates:', len(cands))
    cand_mats = {}
    for c in cands:
        m = render_norm(fref, ord(c))
        if m is not None:
            cand_mats[c] = m
    print('rendered cands:', len(cand_mats))

    # 3) 预筛（灰度余弦）→ 精算（IoU）
    def flat(m):
        return m.ravel().astype(np.float32)
    def nrm(v):
        n = np.linalg.norm(v)
        return v / n if n > 0 else v
    cm_flat = {c: nrm(flat(m)) for c, m in cand_mats.items()}
    all_pairs = []
    for h, pm in pua_mats.items():
        pf = nrm(flat(pm))
        sims = []
        for c, cf in cm_flat.items():
            sims.append((float(np.dot(pf, cf)), c))
        sims.sort(reverse=True)
        top = sims[:25]
        for _, c in top:
            s = best_iou(pm, cand_mats[c])
            all_pairs.append((s, h, c))
    all_pairs.sort(reverse=True, key=lambda x: x[0])
    print('scored pairs:', len(all_pairs))

    # 4) 贪心唯一分配
    used_h, used_c = set(), set()
    assign = {}
    for s, h, c in all_pairs:
        if h in used_h or c in used_c:
            continue
        if s < 0.35:
            break
        assign[h] = {'char': c, 'iou': round(s, 3)}
        used_h.add(h)
        used_c.add(c)
    print('assigned:', len(assign), '/', len(pua_mats))
    json.dump(assign, open(BASE + r'\fontmap3.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    # 打印分配结果按码位顺序
    for h in pua:
        if h in assign:
            a = assign[h]
            if a['iou'] < 0.7:
                print('LOW', h, a)
    print('--- sample ---')
    for h in pua[:50]:
        print(h, assign.get(h))

if __name__ == '__main__':
    main()