# writer-styles · 作者文风包注册表

把 writeStyle 仓库的蒸馏成果接入 write-assistant 流水线。**此后 writeStyle 的修正统一在本目录维护**（原仓库归档）。

## 每个风格包的三件套

| 文件 | 作用 | 谁用 |
|------|------|------|
| `style_card.md` | 风格决策卡（≤10条，~1.5k tokens） | 总编每章注入写手 |
| `fingerprint.json` | 文体指纹基线（从原作统计，v2.0 含章际分布+派生容差） | style_fingerprint.py 验收 |
| `lint_overlay.json` | lint 阈值覆盖层（签名手法豁免+专属阈值） | style_lint.py `--style` |
| `vocabulary.json` | 签名词库（签名短语/回避词/意象/感官配比） | 写作用词参考 |
| `reference/SKILL-full.md` | 完整版风格规则（蒸馏报告） | 蒸馏修订、人工查阅 |

## 已有风格包

- `yanyujiangnan/` 烟雨江南——黑暗、苍凉、克制，黑暗奇幻（fingerprint v2.0 high，三本全本1015万字）
- `chendong/` 辰东——宏大、热血、悲壮，东方玄幻史诗（fingerprint v2.0 high，两本全本1109万字）
- `jiangnan/` 江南——青春史诗、热血苍凉、少年视角（fingerprint v2.0 high，三本273万字）
- `jinhezai/` 今何在——诗意碎片、哲思独白、剧本式对话，破折号/省略号为签名手法（fingerprint v2.0 high，《悟空传》6.1万字）
- `maibao/` 卖报小郎君——轻快爽文、段子手叙事（fingerprint v2.0 high，两本657万字）
- `wuzei/` 爱潜水的乌贼——克制悬疑、设定流、长短句大开大合（fingerprint v2.0 high，三本1016万字）
- `wochixihongshi/` 我吃西红柿——明快直给、短句口语、对话驱动，省略号为签名手法（fingerprint v2.0 high，两本全本791万字）
- `tiancantudou/` 天蚕土豆——绵密铺陈、长句流转、叙述驱动，破折号近乎为零+着字高频为签名手法（fingerprint v2.0 high，两本全本779万字）

## 挂载方式

`config/novel_config.json` 增加：

```json
"style_pack": "yanyujiangnan"
```

总编派单时：①将该包 `style_card.md` 注入写手上下文（本章剧情节点之后）；②交接卡 `style_pack` 字段标注；③lint 与指纹校验按 style_card 末尾的命令执行。**一本书只挂一个风格包。**

## 蒸馏新作者（四阶段流程，方法论见 docs/style-distillation/）

> **原作语料位置**：原作 txt 已从仓库移出，存放在 `d:\personFile\corpus\writer-styles\<作者名>\原作[_utf8]\`。蒸馏时用绝对路径引用。

```bash
# ① 指纹基线（需原作≥3万字，禁用蒸馏产物充当原作；--exclude-names 过滤主角名防意象污染）
python style_fingerprint.py build "d:\personFile\corpus\writer-styles\作者名\原作_utf8\原作1.txt" "d:\personFile\corpus\writer-styles\作者名\原作_utf8\原作2.txt" --author 作者名 \
    --exclude-names 主角名1,主角名2 \
    --out .trae/skills/writer-styles/作者名/fingerprint.json
# ② 结构化三层提取（画像层/语言层/决策层）→ 初版 style_card（模板见下）
# ③ 写测试章 → LLM评审（6维rubric）→ 双轨迭代（改文本+补规则）→ 记录 rubric_review.md
# ④ 指纹自校验 + 校验收敛 → 定稿 → 入库验收
python style_fingerprint.py selfcheck --baseline .../fingerprint.json   # 容差健康度（原作章节应高比例通过）
python style_pack_check.py --style 作者名                               # 入库验收清单（FAIL 禁止入库）
```

## style_card.md 模板（D4，入库强制）

决策卡是"为什么这样写"的可执行决策，不是风格形容词堆砌。每张卡必须满足：

1. **≤10 条核心决策**，每条结构为：
   - **量化决策**：可机器/人工核验的阈值或计数（如"了≤25/千字""引前引导≥4处/章"），并注明推导链（"原作 15.3 vs 我们 36.4"）
   - **原文例句**：≥1 处原作引文（佐证该决策来自原作而非臆想）
   - **错误/正确对照**：❌ 反例 + ✅ 正例（让写手知道边界在哪）
2. 全卡量化指标 ≥5 处、原文例句 ≥3 处、至少 1 组错误/正确对照（`style_pack_check.py` P5 项机器核验）
3. 纯倾向性描述（如"克制是灵魂"）允许存在，但不能替代量化决策，且必须附改法示例
4. 卡尾附本包的 lint/指纹校验命令

## 迭代闭环产物（D5，阶段③的记录规范）

蒸馏迭代的评审过程必须留痕，否则"自主迭代"无法复盘也无法复用：

- `rubric_review.md`：每轮迭代的 6 维 rubric 评分记录（语言质感/节奏控制/氛围营造/人物质感/克制程度/规则遵守，各 1-5 分）+ 本轮改动摘要；收敛标准：连续两轮分数变化 <5%
- `reverse_validation.md`：反向验证记录（图灵测试式——把生成段与原作段混排，让评审判断哪段是原作；判断错误率应随迭代下降）
- 两文件随三件套一同入库，`style_pack_check.py` 暂不强制（P 级 WARN 项预留）

## 优先级仲裁（重要）

lint 硬约束 > 风格覆盖层 > 决策卡倾向。
覆盖层只能调阈值与豁免签名手法，**不能关闭通用反AI红线**。
区分"作家签名"与"AI指纹"的唯一标准：原作指纹基线里有没有这个特征。

## 指纹口径 v2.0 说明（2026-07-26 重建）

- 分句只按句末标点（v1 把换行当句号，句长混入段长）；破折号去重计数（v1 每个"——"计3次，故 v2.0 破折号密度约为 v1 的 1/3）；对话占比按引号内字数（v1 按整段，故 v2.0 普遍低于 v1 口径）；比喻密度含 仿佛/宛如/犹如/好似/如同/似的
- 新增句法维度：段首连词率 / 引前引导率 / 短句"了"收尾率
- 容差由章际波动推导（标量 max(默认, 2σ)，向量 max(默认, p95)），高方差维度会触顶 1.0——这意味着该维度在单章尺度上区分度有限，校验时作参考而非硬判
- v1 口径基线已被 v2.0 取代（git 历史可查旧值）；lint_overlay 的阈值若引用 v1 口径数值，复查时注意口径差（破折号/对话占比）
