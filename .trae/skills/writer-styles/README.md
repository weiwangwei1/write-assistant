# writer-styles · 作者文风包注册表

把 writeStyle 仓库的蒸馏成果接入 write-assistant 流水线。**此后 writeStyle 的修正统一在本目录维护**（原仓库归档）。

## 每个风格包的三件套

| 文件 | 作用 | 谁用 |
|------|------|------|
| `style_card.md` | 风格决策卡（≤10条，~1.5k tokens） | 总编每章注入写手 |
| `fingerprint.json` | 文体指纹基线（从原作统计） | style_fingerprint.py 验收 |
| `lint_overlay.json` | lint 阈值覆盖层（签名手法豁免+专属阈值） | style_lint.py `--style` |
| `reference/SKILL-full.md` | 完整版风格规则（蒸馏报告） | 蒸馏修订、人工查阅 |

## 已有风格包

- `chendong/` 辰东——宏大、热血、悲壮，东方玄幻史诗（fingerprint 为 provisional，语录样本，建议用全本重建）
- `yanyujiangnan/` 烟雨江南——黑暗、苍凉、克制，黑暗奇幻（fingerprint high，三本全本1015万字）
- `jiangnan/` 江南——青春史诗、热血苍凉、少年视角，长短句大开大合（fingerprint high，三本273万字。句长26.08/对话53.4%/破折号0.251）
- `jinhezai/` 今何在——诗意碎片、哲思独白、剧本式对话，破折号/省略号为签名手法（fingerprint high，《悟空传》6.1万字。句长15.4/对话65.6%/破折号4.8/省略号8.4）

## 挂载方式

`config/novel_config.json` 增加：

```json
"style_pack": "yanyujiangnan"
```

总编派单时：①将该包 `style_card.md` 注入写手上下文（本章剧情节点之后）；②交接卡 `style_pack` 字段标注；③lint 与指纹校验按 style_card 末尾的命令执行。**一本书只挂一个风格包。**

## 蒸馏新作者（对应《自主蒸馏方法论v2》四阶段，文档见 docs/style-distillation/）

```bash
# ① 指纹基线（需原作≥3万字，禁用蒸馏产物充当原作）
python style_fingerprint.py build 原作1.txt 原作2.txt --author 作者名 \
    --out .trae/skills/writer-styles/作者名/fingerprint.json
# ② 结构化三层提取（画像层/语言层/决策层，每条规则附原文证据）→ 初版 style_card
# ③ 写测试章 → LLM评审（6维rubric，对照原作打分）→ 双轨迭代（改文本+补规则）
# ④ 指纹校验收敛 → 定稿三件套，登记到本目录
```

## 优先级仲裁（重要）

lint 硬约束 > 风格覆盖层 > 决策卡倾向。
覆盖层只能调阈值与豁免签名手法，**不能关闭通用反AI红线**。
区分"作家签名"与"AI指纹"的唯一标准：原作指纹基线里有没有这个特征。
