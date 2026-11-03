import json
m = json.load(open(r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw\fontmap.json', encoding='utf-8'))

# 常用字候选集：把页面可能出现的字符全部覆盖——用 fontmap 中已映射字符 + 高频字
# 这里用「以字形重比对」的方式：对每个 PUA，把映射字符及全部候选一起比较
cands = []
for b1 in range(0xB0, 0xF8):
    for b2 in range(0xA1, 0xFF):
        try:
            cands.append(bytes([b1, b2]).decode('gb2312'))
        except Exception:
            pass
for c in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ，。！？、：；“”‘’《》【】…—·（）':
    cands.append(c)
cands = list(dict.fromkeys(cands))
pairs = [[int(k, 16), v['char']] for k, v in m.items() if v and v.get('char')]

js = 'window.__FMP=' + json.dumps(pairs, ensure_ascii=False) + ';\n'
js += 'window.__CANDS=' + json.dumps(cands, ensure_ascii=False) + ';\n'
js += r'''
window.__verify = function(cb){
  var S = 64;
  var map = {}; window.__FMP.forEach(function(p){ map[p[0]] = p[1]; });
  var cv = document.createElement('canvas'); cv.width = S; cv.height = S;
  var ctx = cv.getContext('2d', {willReadFrequently: true});
  var fams = [];
  for (var i = 0; i < document.fonts.size; i++) {
    var f = Array.from(document.fonts)[i];
    if (f.status === 'loaded' || f.status === 'unloaded') fams.push(f.family.replace(/"/g, ''));
  }
  function renderGlyph(ch, fam, useFam) {
    ctx.clearRect(0, 0, S, S);
    ctx.font = S * 0.8 + 'px ' + (useFam && fam ? '"' + fam + '"' : 'sans-serif');
    ctx.textBaseline = 'middle'; ctx.textAlign = 'center'; ctx.fillStyle = '#000';
    ctx.fillText(ch, S / 2, S / 2);
    var img = ctx.getImageData(0, 0, S, S).data;
    var arr = [];
    for (var i = 0; i < img.length; i += 4) arr.push(img[i + 3]);
    return arr;
  }
  function norm(arr) {
    var v = 0; for (var i = 0; i < arr.length; i++) v += arr[i] * arr[i];
    return Math.sqrt(v) || 1;
  }
  function cos(a, b, na, nb) {
    var d = 0; for (var i = 0; i < a.length; i++) d += a[i] * b[i];
    return d / (na * nb);
  }
  function crop(arr) {
    // 裁剪包围盒并重排为 32x32 便于更稳的比较
    var minx = S, maxx = -1, miny = S, maxy = -1;
    for (var y = 0; y < S; y++) for (var x = 0; x < S; x++) {
      if (arr[y * S + x] > 30) { if (x < minx) minx = x; if (x > maxx) maxx = x; if (y < miny) miny = y; if (y > maxy) maxy = y; }
    }
    if (maxx < 0) return null;
    var w = maxx - minx + 1, h = maxy - miny + 1;
    var cv2 = document.createElement('canvas'); cv2.width = S; cv2.height = S;
    var c2 = cv2.getContext('2d');
    // 用 drawImage 需源 canvas，这里直接手工采样（双线性太麻烦，用最近邻）
    var data = c2.createImageData(S, S);
    var scale = Math.min(S / w, S / h) * 0.9;
    var nw = Math.max(1, Math.round(w * scale)), nh = Math.max(1, Math.round(h * scale));
    var ox = (S - nw) / 2, oy = (S - nh) / 2;
    for (var yy = 0; yy < nh; yy++) for (var xx = 0; xx < nw; xx++) {
      var sx = minx + Math.min(w - 1, Math.floor(xx / scale));
      var sy = miny + Math.min(h - 1, Math.floor(yy / scale));
      var di = ((Math.round(oy) + yy) * S + Math.round(ox) + xx) * 4;
      data.data[di] = 0; data.data[di + 1] = 0; data.data[di + 2] = 0; data.data[di + 3] = arr[sy * S + sx];
    }
    c2.putImageData(data, 0, 0);
    var img2 = c2.getImageData(0, 0, S, S).data;
    var out = [];
    // 降采样到 32x32
    var B = 32, step = S / B;
    for (var by = 0; by < B; by++) for (var bx = 0; bx < B; bx++) {
      var sum = 0, cnt = 0;
      for (var y2 = Math.floor(by * step); y2 < Math.floor((by + 1) * step); y2++)
        for (var x2 = Math.floor(bx * step); x2 < Math.floor((bx + 1) * step); x2++) {
          sum += img2[(y2 * S + x2) * 4 + 3]; cnt++;
        }
      out.push(sum / cnt);
    }
    return out;
  }
  var results = [];
  var candPrepared = null;
  window.__FMP.forEach(function(pair) {
    var cp = pair[0], orig = pair[1];
    var pa = renderGlyph(String.fromCharCode(cp), null, true); // 用页面字体渲染（字体族已由页面 CSS 指定？不，canvas 默认不走 @font-face）
    pa = crop(pa);
    if (!pa) { results.push([cp, orig, null, 0]); return; }
    var na = norm(pa);
    // 候选只在「原映射」+ 全部候选里找；候选渲染用无衬线（近似目标字体度量）
    var best = null, bestScore = -1;
    // 先与全部候选比（第一次运行时缓存）
    if (!candPrepared) {
      candPrepared = {};
      window.__CANDS.forEach(function(ch) {
        var m = crop(renderGlyph(ch, null, false));
        if (m) candPrepared[ch] = m;
      });
    }
    for (var ch in candPrepared) {
      var pb = candPrepared[ch]; var nb = norm(pb);
      var sc = cos(pa, pb, na, nb);
      if (sc > bestScore) { bestScore = sc; best = ch; }
    }
    results.push([cp, orig, best, Math.round(bestScore * 1000) / 1000]);
  });
  cb(results);
};
"DONE"'''
open(r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw\verify_inject.js', 'w', encoding='utf-8').write(js)
print('js bytes:', len(js))