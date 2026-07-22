// 各章字数与质量评分分布
(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var fontFamily = '"Noto Sans CJK SC", "WenQuanYi Micro Hei", "Microsoft YaHei", sans-serif';

  var chapters = ['第1章', '第2章', '第3章', '第4章', '第5章', '第6章', '第7章'];
  var words = [3500, 3500, 4080, 3900, 4200, 2980, 2920];
  var scores = [null, null, 8.14, 8.14, null, 8.14, 8.57];

  var chart = echarts.init(document.getElementById('chart-chapters'), null, { renderer: 'svg' });
  chart.setOption({
    animation: false,
    textStyle: { fontFamily: fontFamily },
    color: [accent, accent2],
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      backgroundColor: bg2,
      borderColor: rule,
      textStyle: { color: ink, fontFamily: fontFamily },
      formatter: function(params) {
        var lines = [params[0].axisValue];
        params.forEach(function(p) {
          var v = p.value == null ? '—（补录无留存）' : (p.seriesName === '质量评分' ? p.value + ' 分' : p.value.toLocaleString() + ' 字');
          lines.push(p.marker + ' ' + p.seriesName + '：' + v);
        });
        return lines.join('<br>');
      }
    },
    legend: {
      data: ['章节字数', '质量评分'],
      textStyle: { color: muted, fontFamily: fontFamily },
      top: 0
    },
    grid: { left: 60, right: 56, top: 42, bottom: 36 },
    xAxis: {
      type: 'category',
      data: chapters,
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontFamily: fontFamily },
      axisTick: { show: false }
    },
    yAxis: [
      {
        type: 'value',
        name: '字数',
        nameTextStyle: { color: muted, fontFamily: fontFamily },
        min: 0,
        max: 4500,
        axisLabel: { color: muted, fontFamily: fontFamily, formatter: function(v) { return v.toLocaleString(); } },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } }
      },
      {
        type: 'value',
        name: '评分',
        nameTextStyle: { color: muted, fontFamily: fontFamily },
        min: 7.5,
        max: 9,
        axisLabel: { color: muted, fontFamily: fontFamily },
        splitLine: { show: false }
      }
    ],
    series: [
      {
        name: '章节字数',
        type: 'bar',
        data: words,
        barWidth: '42%',
        itemStyle: { color: accent, borderRadius: [4, 4, 0, 0], opacity: 0.85 },
        label: { show: true, position: 'top', color: muted, fontSize: 11, fontFamily: fontFamily, formatter: function(p) { return p.value.toLocaleString(); } }
      },
      {
        name: '质量评分',
        type: 'line',
        yAxisIndex: 1,
        data: scores,
        connectNulls: false,
        symbol: 'circle',
        symbolSize: 9,
        lineStyle: { color: accent2, width: 2.5 },
        itemStyle: { color: accent2, borderColor: bg2, borderWidth: 2 },
        label: { show: true, position: 'top', color: accent2, fontSize: 11, fontFamily: fontFamily, formatter: function(p) { return p.value == null ? '' : p.value.toFixed(2); } }
      }
    ]
  });
  window.addEventListener('resize', function() { chart.resize(); });
})();
