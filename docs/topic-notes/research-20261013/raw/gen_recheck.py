# -*- coding: utf-8 -*-
"""生成浏览器端 canvas 像素比对脚本：用页面真实字体渲染 PUA，重新匹配候选字符"""
import json
BASE = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw'
m = json.load(open(BASE + r'\fontmap.json', encoding='utf-8'))
pairs = [[int(k, 16), v['char']] for k, v in m.items() if v and v.get('char')]

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

js = 'window.__FMP=' + json.dumps(pairs, ensure_ascii=False) + ';window.__CANDS=' + json.dumps(cands, ensure_ascii=False) + ';'
js += r'''
window.__recheck = function(fam){
  var S=64, B=32, STEP=2;
  var cv=document.createElement('canvas'); cv.width=S; cv.height=S;
  var ctx=cv.getContext('2d',{willReadFrequently:true});
  function feat(ch, fam2){
    ctx.clearRect(0,0,S,S);
    ctx.font='56px '+fam2;
    ctx.textBaseline='middle'; ctx.textAlign='center'; ctx.fillStyle='#000';
    ctx.fillText(ch,S/2,S/2);
    var d=ctx.getImageData(0,0,S,S).data;
    var minx=S,maxx=-1,miny=S,maxy=-1,i,x,y;
    for(y=0;y<S;y++)for(x=0;x<S;x++){i=(y*S+x)*4; if(d[i+3]>30){if(x<minx)minx=x;if(x>maxx)maxx=x;if(y<miny)miny=y;if(y>maxy)maxy=y;}}
    if(maxx<0)return null;
    var w=maxx-minx+1,h=maxy-miny+1;
    var f=new Float32Array(B*B);
    var sc=Math.min((B-4)/w,(B-4)/h);
    var nw=Math.max(1,Math.round(w*sc)),nh=Math.max(1,Math.round(h*sc));
    var ox=(B-nw)/2,oy=(B-nh)/2;
    for(y=0;y<nh;y++)for(x=0;x<nw;x++){
      var sx=minx+Math.min(w-1,Math.floor(x/sc)),sy=miny+Math.min(h-1,Math.floor(y/sc));
      var tx=Math.round(ox)+x,ty=Math.round(oy)+y;
      f[ty*B+tx]=d[(sy*S+sx)*4+3]/255;
    }
    return f;
  }
  function norm(f){var v=0;for(var i=0;i<f.length;i++)v+=f[i]*f[i];return Math.sqrt(v)||1;}
  // 渲染全部候选（页面上下文里用 simhei 渲染）
  var cmap={},cnorm={};
  for(var k=0;k<window.__CANDS.length;k++){
    var c=window.__CANDS[k];
    var f=feat(c,'SimHei,"Microsoft YaHei",sans-serif');
    if(f){cmap[c]=f;cnorm[c]=norm(f);}
  }
  var out=[];
  for(var j=0;j<window.__FMP.length;j++){
    var cp=window.__FMP[j][0], orig=window.__FMP[j][1];
    var fp=feat(String.fromCharCode(cp), fam);
    if(!fp){out.push([cp,orig,orig,0]);continue;}
    var np=norm(fp);
    var best=orig, bs=-1, second=0, secondCh='';
    for(var c in cmap){
      var fc=cmap[c];
      var dot=0;
      for(var i=0;i<fp.length;i++)dot+=fp[i]*fc[i];
      var s=dot/(np*cnorm[c]);
      if(s>bs){second=bs;secondCh=best;bs=s;best=c;}
      else if(s>second){second=s;secondCh=c;}
    }
    out.push([cp,orig,best,Math.round(bs*1000)/1000,Math.round(second*1000)/1000,secondCh]);
  }
  return out;
};
"READY"'''
open(BASE + r'\recheck_inject.js', 'w', encoding='utf-8').write(js)
print('js len', len(js))