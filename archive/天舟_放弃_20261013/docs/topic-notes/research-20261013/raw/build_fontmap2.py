# -*- coding: utf-8 -*-
"""精修版字体映射：freetype 渲染 + 多参照字体 + IoU 匹配"""
import json
import freetype
import numpy as np
from PIL import Image

BASE = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw'
FONT = BASE + r'\font_ttf.ttf'
REFS = [r'C:\Windows\Fonts\simhei.ttf', r'C:\Windows\Fonts\STXIHEI.TTF']
SIZE = 96

def render_norm(face, codepoint, size=SIZE):
    """渲染字形 → 裁剪包围盒 → 等比缩放到 (size-16) 内 → 居中到 size 方框，返回 0-1 浮点矩阵"""
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
    scale = (size - 16) / max(h2, w2)
    nh, nw = max(1, int(round(h2 * scale))), max(1, int(round(w2 * scale)))
    img = Image.fromarray(arr.astype(np.uint8)).resize((nw, nh), Image.LANCZOS)
    canvas = np.zeros((size, size), dtype=np.float32)
    oy, ox = (size - nh) // 2, (size - nw) // 2
    canvas[oy:oy+nh, ox:ox+nw] = np.asarray(img, dtype=np.float32)
    return canvas / 255.0

def best_shift_iou(a, b, max_shift=6):
    """在 ±max_shift 平移中找最大 IoU（二值）」"""
    ab = a > 0.5
    bb = b > 0.5
    best = 0.0
    for dy in range(-max_shift, max_shift+1, 2):
        for dx in range(-max_shift, max_shift+1, 2):
            b2 = np.roll(np.roll(bb, dy, axis=0), dx, axis=1)
            inter = np.logical_and(ab, b2).sum()
            union = np.logical_or(ab, b2).sum()
            if union > 0:
                iou = inter / union
                if iou > best:
                    best = iou
    return best

def main():
    pua = json.load(open(BASE + r'\pua_chars.json', encoding='utf-8'))
    cands = []
    for b1 in range(0xB0, 0xF8):
        for b2 in range(0xA1, 0xFF):
            try:
                cands.append(bytes([b1, b2]).decode('gb2312'))
            except Exception:
                pass
    for c in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ，。！？、：；”“《》【】…—·（）':
        cands.append(c)
    cands = list(dict.fromkeys(cands))
    print('candidates:', len(cands))

    fmain = freetype.Face(FONT)
    frefs = [freetype.Face(p) for p in REFS]
    fmain.set_pixel_sizes(0, 128)
    for f in frefs:
        f.set_pixel_sizes(0, 128)

    # 预渲染参照候选（两个字体分别渲染后叠加取平均以稳定形状差异）
    cand_mats = {}
    for c in cands:
        ms = [render_norm(f, ord(c)) for f in frefs]
        ms = [m for m in ms if m is not None]
        if ms:
            cand_mats[c] = ms  # 存列表，比对时取每个参照的最大 IoU
    print('rendered cands:', len(cand_mats))

    result = {}
    low = []
    for hexcode in pua:
        cp = int(hexcode, 16)
        cit = render_norm(fmain, cp)
        if cit is None:
            result[hexcode] = None
            continue
        scores = []
        for c, ms in cand_mats.items():
            sc = max(best_shift_iou(cit, m) for m in ms)
            scores.append((sc, c))
        scores.sort(reverse=True)
        top = scores[:5]
        result[hexcode] = {'char': top[0][1], 'iou': round(top[0][0], 3), 'top': [(round(s,3), c) for s, c in top]}
        if top[0][0] < 0.75:
            low.append((hexcode, top))
    json.dump(result, open(BASE + r'\fontmap2.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('done. low-confidence:', len(low))
    for h, t in low[:60]:
        print(h, [(round(s,3), c) for s, c in t])

if __name__ == '__main__':
    main()