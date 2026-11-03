# -*- coding: utf-8 -*-
"""番茄字体映射还原：渲染 PUA 字形，与系统中文字体做像素比对"""
import json
import freetype
import numpy as np

FONT = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw\font_ttf.ttf'
REF = r'C:\Windows\Fonts\simhei.ttf'
SIZE = 64

def render(face, codepoint):
    """把单个字形渲染成 SIZE x SIZE 的归一化灰度图（裁剪包围盒后缩放）"""
    face.load_char(codepoint, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_NORMAL)
    bmp = face.glyph.bitmap
    w, h = bmp.width, bmp.rows
    if w == 0 or h == 0:
        return None
    arr = np.array(bmp.buffer, dtype=np.uint8).reshape(h, bmp.pitch)[:, :w].astype(np.float32)
    # 裁剪到实际墨迹
    ys, xs = np.nonzero(arr > 20)
    if len(ys) == 0:
        return None
    arr = arr[ys.min():ys.max()+1, xs.min():xs.max()+1]
    # 归一化到 SIZE 方框（保持非等比会导致走样，这里等比缩放 + 居中）
    h2, w2 = arr.shape
    scale = (SIZE - 8) / max(h2, w2)
    nh, nw = max(1, int(h2 * scale)), max(1, int(w2 * scale))
    # 用 PIL 缩放
    from PIL import Image
    img = Image.fromarray(arr.astype(np.uint8)).resize((nw, nh), Image.BILINEAR)
    canvas = np.zeros((SIZE, SIZE), dtype=np.float32)
    oy, ox = (SIZE - nh) // 2, (SIZE - nw) // 2
    canvas[oy:oy+nh, ox:ox+nw] = np.asarray(img, dtype=np.float32)
    canvas = canvas / 255.0
    return canvas

def main():
    pua_chars = json.load(open(r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw\pua_chars.json', encoding='utf-8'))
    # 候选字符集：GB2312 全部汉字 + 常用标点数字字母
    cands = []
    for b1 in range(0xB0, 0xF8):
        for b2 in range(0xA1, 0xFF):
            try:
                c = bytes([b1, b2]).decode('gb2312')
                cands.append(c)
            except Exception:
                pass
    for c in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ，。！？、：；""''《》【】…—·（）「」':
        cands.append(c)
    cands = list(dict.fromkeys(cands))
    print('candidates:', len(cands))

    fright = freetype.Face(FONT)
    fref = freetype.Face(REF)
    fright.set_pixel_sizes(0, SIZE * 2)
    fref.set_pixel_sizes(0, SIZE * 2)

    # 渲染候选集
    cand_mats = {}
    for c in cands:
        m = render(fref, ord(c))
        if m is not None:
            cand_mats[c] = m
    print('rendered candidates:', len(cand_mats))

    result = {}
    for hexcode in pua_chars:
        cp = int(hexcode, 16)
        m = render(fright, cp)
        if m is None:
            result[hexcode] = None
            continue
        best, bestscore = None, -1
        for c, cm in cand_mats.items():
            # 归一化互相关
            a, b = m.ravel(), cm.ravel()
            denom = (np.linalg.norm(a) * np.linalg.norm(b))
            score = float(np.dot(a, b) / denom) if denom > 0 else 0
            if score > bestscore:
                bestscore, best = score, c
        result[hexcode] = {'char': best, 'score': round(bestscore, 3)}
    json.dump(result, open(r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw\fontmap.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    # 输出样例
    for k in list(result.keys())[:30]:
        print(k, result[k])

if __name__ == '__main__':
    main()