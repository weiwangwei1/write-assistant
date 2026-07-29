# 感知织体诊断器 v4.0 设计文档

> 替代 v3.0 设计（perception_tracker_v3_design.md）及三个独立工具（framework_experiment.py / scene_perception_lint.py）
> 定位：写手提交前的自检工具，一次运行输出四维报告
> 核心问题："这段话是角色在感知，还是作者在交代？"

---

## 一、v3.0 终评估

### 1.1 做对的部分（保留）

| 原则 | 来源 | v4.0 如何保留 |
|------|------|-------------|
| 范式从词频→感知通道 | v3.0 A1 | T3 核心算法 |
| 自发现替代硬编码 | v3.0 A3 | T3 输入管道 |
| "换感知不换词" | v3.0 A2 | T3 诊断逻辑 |
| P3 动作预算有效 | v2.0 P3 | T4 搬迁 |
| P5 指代密度有效 | v2.0 P5 | T4 搬迁 |
| D3 双层锚点+回溯 | scene_lint D3 | T1 空间锚定 |
| D2 动作后解释检测 | scene_lint D2 | T2 核心检测 |
| D5 焦距起点 | scene_lint D5 | T1 开篇检测 |
| D7 专名锚定 | scene_lint D7 | T1 专名检测 |

### 1.2 五个致命缺陷（必须解决）

#### 缺陷1：工具碎片化

```
v3.0 架构：
  perception_tracker.py     (A1-A5)  5 维
  framework_experiment.py    (P2/P3/P5) 3 维
  scene_perception_lint.py   (D1-D7)  7 维
  ────────────────────────────────────
  合计：3 脚本 × 15 维度

问题：写手提交前要跑 3 个工具、解读 15 个维度报告。
     维度间大量重叠，同一问题从不同角度报多次。
```

#### 缺陷2：维度冗余

| 重叠组 | 涉及维度 | 本质同一问题 |
|--------|---------|------------|
| 感知具身 | A1 + A4 + D1 + D3 + D5 + D7 | "这段话有没有场景锚定" |
| 作者介入 | D2 + D6 + P2 | "作者解释/翻译/收尾了多少次" |
| 意象通道 | A1 + A2 + D4 | "高频词的感知维度是否单一" |
| 频率控制 | P3 + P5 | "情绪动作/指代是否超限" |

#### 缺陷3：A3 定位错误

A3（高频名词自发现）是 A1/A2/A4 的**输入管道**，不是文本质量维度。
把它做成评分维度 = 评估自己的 NLP 管道质量，不是评估文本质量。

#### 缺陷4：A2 = delta(A1)

A2（替代词通道转移）= 变体非视觉占比 - 原词非视觉占比。
这是 A1 的差值，不是独立维度。合并后逻辑更清晰。

#### 缺陷5：A5 为时过早

单章诊断都还没稳定，跨章演化追踪增加复杂度但收益不明确。
v4.0 暂时移除，待单章诊断稳定后作为扩展功能加入。

---

## 二、v4.0 核心设计

### 2.1 设计原则

1. **一个工具，一次运行**：合并为 `perception_texture.py`，输出一份四维报告
2. **按粒度分层**：段落级（T1/T2）→ 名词级（T3）→ 模式级（T4），从粗到细
3. **管道与维度分离**：自发现是输入处理步骤，不评分
4. **诊断而非约束**：检测问题并报告，不告诉写手怎么写
5. **可复用**：现有代码大量搬迁，不从头重写

### 2.2 四维架构

```
perception_texture.py
│
├── T1 具身感知度      [段落级]  角色是否通过身体在感知
│   ├── 感官动词 + 身体部位 + 空间锚点 检测
│   ├── 信息交付段检测（原 D1）
│   ├── 空间失锚检测（原 D3 双层锚点）
│   ├── 开篇焦距检测（原 D5）
│   └── 专名锚定检测（原 D7）
│
├── T2 叙述者退场度    [段落级]  作者是否在解释/翻译/收尾
│   ├── 动作后解释检测（原 D2）
│   ├── 世界自转检测（原 D6，正向指标）
│   └── 金句密度检测（原 P2，修复误判）
│
├── T3 意象感知多样性   [名词级]  高频词的感知通道是否丰富
│   ├── [管道] 高频名词自发现（原 A3，不评分）
│   ├── 通道覆盖检测（原 A1）
│   ├── 替代词转移检测（原 A2，合并进 A1）
│   └── 感官萦绕检测（原 D4）
│
└── T4 节律控制        [模式级]  情绪动作/指代频率
    ├── 重复动作预算（原 P3，改为自发现）
    └── 指代密度（原 P5，改为自发现）
```

### 2.3 与 v3.0 的维度映射

| v3.0 维度 | 去向 | 说明 |
|-----------|------|------|
| A1 感知维度覆盖 | → T3 | 核心逻辑保留 |
| A2 替代词通道转移 | → T3 | 合并为 T3 子检测（delta 不单独评分） |
| A3 高频名词自发现 | → T3 管道 | 降为输入处理，不评分 |
| A4 感知-身体关联 | → T1 | 身体反应检测合入具身感知 |
| A5 跨章意象演化 | 移除 | 暂不实现，待单章稳定后扩展 |
| P2 金句密度 | → T2 | 修复误判逻辑后合入 |
| P3 重复动作预算 | → T4 | 搬迁，改为自发现模式 |
| P5 指代密度 | → T4 | 搬迁，改为自发现模式 |
| D1 信息交付段 | → T1 | 核心信号合入具身感知 |
| D2 叙述者翻译 | → T2 | 核心检测 |
| D3 空间失锚 | → T1 | 双层锚点系统搬迁 |
| D4 感官一次性 | → T3 | 萦绕检测合入意象分析 |
| D5 焦距起点 | → T1 | 开篇检测作为 T1 子项 |
| D6 世界自转 | → T2 | 正向指标合入叙述者退场 |
| D7 专名锚定 | → T1 | 首次锚定检测作为 T1 子项 |

---

## 三、T1 具身感知度

### 3.1 检测目标

回答：**每段话是角色在感知，还是作者在交代？**

"具身"= 段落中存在角色通过身体感知世界的证据。
"脱体"= 段落中没有角色的身体参与，信息从叙述者直接交付。

### 3.2 信号体系

#### 正向信号（具身证据）

```python
# 1. 感官动词——角色通过身体感知
SENSORY_VERBS = [
    "看", "望", "盯", "瞧", "瞥", "凝视", "注视",
    "听", "闻", "嗅", "尝", "舔",
    "摸", "碰", "握", "攥", "捏", "按", "蹭",
    "感觉", "感到", "察觉", "觉察",
    "烫", "凉", "冷", "热", "疼", "痒", "麻", "酸",
    "听见", "看到", "闻到", "摸到",
]

# 2. 身体部位——角色的身体在场
BODY_PARTS = [
    "手", "指", "掌", "拳", "腕", "臂",
    "眼", "脸", "眉", "唇", "牙", "额", "喉",
    "肩", "背", "腰", "脚", "膝", "腿",
    "心跳", "呼吸", "脉搏",
]

# 3. 空间锚点——角色在空间中有位置（v2.0 双层锚点）
STRONG_ANCHORS = [
    "左", "右", "前", "后", "上", "下", "旁", "对面",
    "身后", "面前", "头顶", "脚",
    "城墙", "地面", "空中", "裂缝", "雉堞", "城", "墙", "门",
    "通道", "角落", "石地", "门框", "膝上", "掌心",
    "半步", "两步", "三步", "一步",
]
WEAK_ANCHORS = [
    "手边", "身旁", "身边", "附近", "近处", "不远处",
    "一旁", "一侧", "边上", "旁边", "身侧",
]
SPATIAL_PATTERNS = [
    re.compile(r"[\u4e00-\u9fff](?:边|侧|旁)"),
    re.compile(r"(?:离|距)[^。！？]{1,6}步"),
    re.compile(r"(?:左|右|前|后)(?:侧|方|面)"),
]
```

#### 负向信号（脱体证据）

```python
# 1. 信息标记词——暗示叙述者在"交代"
INFO_MARKERS = [
    "据说", "原来", "就是", "也就是说", "换句话说",
    "因为", "所以", "因此", "原因是",
    "规定", "制度", "编制", "条例",
    "叫了", "称为", "管这叫",
]

# 2. 事实陈述句模式
FACT_STATEMENT_PATTERN = re.compile(
    r"[^。！？]*?(?:是|有|管|叫|规定|编制|征调|征诏)[^。！？]*?[。！？]"
)

# 3. 数字密度信号
# 年份/编制/人数等数字 → 交代信息
```

### 3.3 检测算法

```python
def classify_paragraph_embodiment(para: str, idx: int, all_paragraphs: List[str]) -> ParagraphClass:
    """
    对单个段落进行具身分类

    返回分类 + 诊断信息
    """
    char_count = count_chars(para)
    if char_count < 20:
        return ParagraphClass(type="short", score=1.0)  # 短段不参与评分

    # 正向信号计数
    sensory_count = sum(para.count(v) for v in SENSORY_VERBS)
    body_count = sum(para.count(b) for b in BODY_PARTS)
    anchor_weighted = count_anchors(para)  # 复用 D3 的双层锚点计数

    # 负向信号计数
    marker_count = sum(para.count(m) for m in INFO_MARKERS)
    number_count = len(re.findall(r"\d+", para))
    fact_count = len(FACT_STATEMENT_PATTERN.findall(para))
    info_density = marker_count + number_count + fact_count * 0.5

    # 分类逻辑
    has_sensory = sensory_count >= 2
    has_body = body_count >= 1
    has_anchor = anchor_weighted >= 1.0
    has_info = info_density >= 4 and sensory_count <= 1

    if has_sensory and has_body and has_anchor:
        return ParagraphClass(type="embodied", score=1.0,
                              signals={"sensory": sensory_count, "body": body_count, "anchor": anchor_weighted})
    elif has_info:
        return ParagraphClass(type="info_dump", score=0.0,
                              signals={"info_density": info_density, "sensory": sensory_count},
                              diagnosis="信息密度高但感官锚定低——在交代信息而非感知场景")
    elif has_sensory and has_body:
        return ParagraphClass(type="partial", score=0.7,
                              signals={"sensory": sensory_count, "body": body_count, "anchor": anchor_weighted},
                              diagnosis="有感官和身体但缺空间锚——角色在感知但位置模糊")
    elif has_sensory or has_body:
        return ParagraphClass(type="weak", score=0.4,
                              signals={"sensory": sensory_count, "body": body_count, "anchor": anchor_weighted})
    else:
        return ParagraphClass(type="plain", score=0.5)  # 对话/过渡段，中性
```

### 3.4 空间失锚检测（搬迁 D3 v2.0）

在具身分类基础上，对动作密集段额外检测空间锚定：

```python
def check_spatial_drift(para: str, paragraphs: List[str], idx: int) -> Optional[Issue]:
    """
    对动作密集段（动作动词≥3）检测空间锚定
    逻辑搬迁自 scene_perception_lint.py D3 v2.0
    保留：双层锚点 + 前段回溯2段 + 锚点-动作比
    """
    action_count = sum(para.count(v) for v in ACTION_VERBS)
    if action_count < 3:
        return None

    anchor_weighted, strong, weak, pattern = _count_anchors(para)
    prev_context, _ = _get_prev_context(paragraphs, idx)
    anchor_action_ratio = anchor_weighted / max(action_count, 1)

    if anchor_weighted < 0.5 and prev_context < 0.5:
        return Issue(severity="warning",
                    diagnosis=f"动作段无空间锚（锚点={anchor_weighted:.1f}，前段上下文={prev_context:.2f}）",
                    suggestion="在动作前补充空间基线：谁在哪、距离多远、什么方向")
    elif anchor_action_ratio < 0.15 and prev_context < 0.3:
        return Issue(severity="info",
                    diagnosis=f"动作密集但空间稀疏（锚点-动作比={anchor_action_ratio:.2f}）")
    return None
```

### 3.5 开篇焦距检测（搬迁 D5 v2.0）

```python
def check_focal_entry(paragraphs: List[str]) -> Optional[Issue]:
    """
    检测第一段的焦距层级
    逻辑搬迁自 scene_perception_lint.py D5 v2.0
    保留：世界级/建筑级/人物级三级判定 + 画面检测
    """
    # 检查前3句的焦距层级
    # 画面级广角(95) > 概念级广角(75) > 建筑级中景(60) > 人物级近景(30)
    # ...
```

### 3.6 专名锚定检测（搬迁 D7）

```python
def check_proper_noun_anchoring(paragraphs: List[str]) -> List[Issue]:
    """
    检测新造专名首次出现时是否有锚定信息
    逻辑搬迁自 scene_perception_lint.py D7
    保留：专名表 + 锚定模式 + 前后20字窗口检测
    """
    # ...
```

### 3.7 评分公式

```python
# T1 评分
embodied_count = sum(1 for p in para_classes if p.type == "embodied")
info_dump_count = sum(1 for p in para_classes if p.type == "info_dump")
total_checked = sum(1 for p in para_classes if p.type not in ("short",))

embodied_ratio = embodied_count / max(total_checked, 1)

# 基础分
t1_score = embodied_ratio * 100

# 信息交付段额外扣分
t1_score -= info_dump_count * 5

# 开篇焦距扣分
if focal_level == "人物级近景":
    t1_score -= 10
elif focal_level == "建筑级中景":
    t1_score -= 5

# 专名未锚定扣分
t1_score -= unanchored_count * 5

t1_score = max(0, min(100, t1_score))
```

### 3.8 报告输出

```json
{
  "dim": "T1",
  "dim_name": "具身感知度",
  "score": 72.5,
  "stats": {
    "total_paragraphs": 45,
    "embodied": 28,
    "info_dump": 5,
    "partial": 8,
    "weak": 4,
    "embodied_ratio": "62.2%",
    "focal_level": "画面级广角",
    "unanchored_nouns": 1
  },
  "issues": [
    {
      "severity": "warning",
      "location": "第5段",
      "excerpt": "征诏令管着裂缝，派征调者进去，能拿的都拿...",
      "diagnosis": "信息密度=6.5（标记词2+数字3+事实句3），感官动词=0——信息交付段",
      "suggestion": "让角色用身体感知这些信息：把'征诏令规定十二人'变成角色数人时手指划过名字"
    },
    {
      "severity": "warning",
      "location": "第27段",
      "diagnosis": "动作段无空间锚（锚点=0.3，前段上下文=0.2）",
      "suggestion": "在动作前补充空间基线：谁在哪、距离多远、什么方向"
    }
  ]
}
```

---

## 四、T2 叙述者退场度

### 4.1 检测目标

回答：**作者介入了多少次？**

"介入"= 叙述者在角色动作后解释含义、直接交代世界规则、用哲理句收尾。
"退场"= 叙述者隐身，让行为和场景自己说话。

### 4.2 检测算法

#### 4.2.1 动作后解释检测（搬迁 D2）

```python
# 解释标记词
EXPLANATION_MARKERS = [
    "这是", "那叫", "这比", "这说明", "这就叫",
    "不是A是B", "不是因为", "与其说是",
    "换句话说", "也就是说",
    "脸可以骗人", "手不行", "比任何", "更沉", "更重",
]

def detect_narrator_translation(paragraphs: List[str]) -> List[Issue]:
    """
    检测角色动作后紧跟的叙述者解释
    逻辑搬迁自 scene_perception_lint.py D2
    """
    issues = []
    for idx, para in enumerate(paragraphs):
        sentences = split_sentences(para)
        for si, sent in enumerate(sentences):
            if si == 0:
                continue
            is_explanation = any(m in sent for m in EXPLANATION_MARKERS)
            if is_explanation:
                prev_sent = sentences[si - 1]
                action_words = ["手", "脸", "眼", "脚", "刀", "铜钱", "站", "蹲",
                                "走", "转", "握", "攥", "停", "抖", "翻", "磨"]
                has_action = any(w in prev_sent for w in action_words)
                if has_action:
                    issues.append(Issue(
                        severity="warning",
                        location=f"第{idx+1}段, 第{si+1}句",
                        excerpt=(prev_sent + " → " + sent)[:80],
                        diagnosis="角色动作后紧跟叙述者解释，行为不自足",
                        suggestion="删掉解释句，看动作自己能否传达含义"
                    ))
    return issues
```

#### 4.2.2 金句密度检测（修复 P2）

```python
def detect_punchline_fixed(para: str) -> Tuple[bool, str]:
    """
    P2 修复版：短句需同时满足≥2个条件才判为金句

    v2.0 问题：
      "安静。"（2字）→ 判为金句（匹配"安静"）
      "程铖没动。"（5字）→ 判为金句（匹配"没动"）
      → 大量误判

    v4.0 修复：
      条件A：包含对比结构（不是A是B / 没有X只有Y）
      条件B：包含超验判断（比X更Y / 算得出X算不出Y）
      条件C：包含哲理性名词（规则/代价/选择/意义/重量）
      条件D：独立成段且≤15字
      需要≥2个条件同时满足
    """
    char_count = count_chars(para)

    # 长句走原逻辑
    if char_count > 50:
        for pattern in PUNCHLINE_PATTERNS:
            if pattern.search(para):
                return True, para.strip()[:60]
        return False, ""

    # 短句：多条件判定
    conditions = 0

    # 条件A：对比结构
    if re.search(r"(?:不是.*?是|没有.*?只有|不.*?倒是)", para):
        conditions += 1

    # 条件B：超验判断
    if re.search(r"(?:比.*?更|算得出.*?算不出|能.*?不能)", para):
        conditions += 1

    # 条件C：哲理性名词
    if any(w in para for w in ["规则", "代价", "选择", "意义", "重量", "重要"]):
        conditions += 1

    # 条件D：独立成段且≤15字
    if char_count <= 15:
        conditions += 1

    # 需要≥2个条件
    if conditions >= 2:
        return True, para.strip()[:60]

    # 单独的 "安静。" "程铖没动。" 不判为金句
    return False, ""
```

#### 4.2.3 世界自转检测（搬迁 D6，正向指标）

```python
def detect_world_rotation(paragraphs: List[str]) -> Tuple[int, List[Issue]]:
    """
    检测世界独立于角色存在的痕迹（正向指标）
    逻辑搬迁自 scene_perception_lint.py D6
    有世界自转 = 叙述者退场 = 加分
    """
    rotation_count = 0
    issues = []

    rotation_signals = [
        ("生物活动", ["虫", "苔", "鸟", "鼠", "蚁", "爬", "啃", "飞", "蠕动"]),
        ("天气变化", ["风", "雨", "雪", "光", "暗", "亮", "灭", "云"]),
        ("物件自主变化", ["被吹", "滑落", "碰到", "发亮", "发暗", "变了"]),
    ]

    for idx, para in enumerate(paragraphs):
        for signal_name, keywords in rotation_signals:
            hits = [kw for kw in keywords if kw in para]
            if hits:
                char_refs = sum(1 for c in ["程铖", "他", "老周", "沈缺"] if c in para)
                if char_refs <= 2:
                    rotation_count += 1
                    break

    return rotation_count, issues
```

### 4.3 评分公式

```python
# T2 评分
translation_count = len(translation_issues)
punchline_count = count_punchlines(paragraphs)
punchline_density = punchline_count / max(total_chars / 1000, 1)
rotation_count = len(world_rotation_paras)

# 基础分
t2_score = 100

# 动作后解释扣分
t2_score -= translation_count * 10

# 金句密度扣分
if punchline_density > 4:
    t2_score -= (punchline_density - 4) * 15
elif punchline_density > 3:
    t2_score -= (punchline_density - 3) * 10

# 世界自转加分（叙述者退场的正面证据）
if rotation_count >= 3:
    t2_score += 10
elif rotation_count >= 1:
    t2_score += 5

t2_score = max(0, min(100, t2_score))
```

---

## 五、T3 意象感知多样性

### 5.1 检测目标

回答：**高频名词的感知通道是否丰富？**

核心洞察（保留自 v3.0）：意象重复的真正问题不是词频，是感知维度单一。
18 次出现全是视觉 = 重复；18 次出现走 5 种通道 = 丰富。

### 5.2 管道：高频名词自发现（原 A3，不评分）

```python
def discover_noun_groups(text: str, min_freq: int = 5) -> Dict[str, NounGroup]:
    """
    自动发现高频名词 + 变体分组

    输入：章节文本
    输出：{组名: {core, variants, total}}

    步骤：
    1. 提取2-4字中文连续词组
    2. 过滤停用词 + 动词后缀
    3. 词频统计，筛选≥min_freq
    4. 变体分组：共享核心字 + 上下文共现
    5. 可选：人工配置覆盖
    """
    # 分词（简化版）
    word_pattern = re.compile(r"[\u4e00-\u9fff]{2,4}")
    candidates = word_pattern.findall(text)

    # 过滤
    filtered = [w for w in candidates
                if w not in STOP_WORDS
                and not any(w.endswith(suf) for suf in VERB_SUFFIXES)
                and len(w) >= 2]

    # 词频统计
    freq = Counter(filtered)
    high_freq = {w: c for w, c in freq.items() if c >= min_freq}

    # 变体分组
    groups = {}
    used = set()
    for word in sorted(high_freq, key=lambda w: -high_freq[w]):
        if word in used:
            continue
        # 找共享核心字的变体
        core_char = word[0]  # 简化：首字作为核心字
        variants = []
        for other in high_freq:
            if other != word and other not in used:
                if core_char in other or _co_occurs(text, word, other):
                    variants.append(other)
                    used.add(other)
        used.add(word)
        if variants or high_freq[word] >= 8:
            groups[word] = NounGroup(
                core=word,
                variants=variants,
                total=high_freq[word] + sum(high_freq[v] for v in variants)
            )

    return groups
```

### 5.3 感知通道定义（保留 v3.0，优化关键词）

```python
PERCEPTION_CHANNELS = {
    "视觉": {
        "keywords": ["光", "亮", "暗", "紫", "色", "看", "望", "盯", "瞧",
                      "影", "闪", "亮起", "发紫", "暗色", "纹路", "一收一放"],
    },
    "听觉": {
        "keywords": ["声", "响", "磨", "碎", "哑", "咯吱", "听", "嗡",
                      "嘶", "劈", "碰", "刮", "嗡嗡", "磕"],
    },
    "嗅觉": {
        "keywords": ["味", "碱", "焦", "臭", "腥", "香", "闻", "气",
                      "烟", "炊烟", "泔水", "铁锈", "干涩"],
    },
    "触觉": {
        "keywords": ["烫", "凉", "冷", "热", "暖", "寒", "摸", "碰",
                      "握", "攥", "捏", "糙", "滑", "涩", "硬", "软",
                      "硌", "疼", "干热"],
    },
    "效应": {
        "keywords": ["风", "灌", "吹", "渗", "爬", "蠕动", "收", "放",
                      "变", "裂", "合", "关", "开"],
    },
}
```

### 5.4 通道检测算法（优化版：句子级上下文）

```python
def detect_channel_for_occurrence(word: str, paragraph: str) -> str:
    """
    检测名词在某段落中出现的感知通道

    优化（来自 v3.0 设计文档）：
    1. 找到名词所在的完整句子（句号分隔）
    2. 在句子内匹配通道关键词
    3. 返回命中最多的通道
    """
    # 1. 找到包含该词的完整句子
    sentences = re.split(r"[。！？]", paragraph)
    target_sentence = ""
    for sent in sentences:
        if word in sent:
            target_sentence = sent
            break

    if not target_sentence:
        target_sentence = paragraph  # 回退到整段

    # 2. 在句子内匹配通道
    channel_hits = defaultdict(int)
    for channel, config in PERCEPTION_CHANNELS.items():
        for kw in config["keywords"]:
            if kw in target_sentence:
                channel_hits[channel] += 1

    # 3. 返回命中最多的通道
    if not channel_hits:
        return "未检测"
    return max(channel_hits, key=channel_hits.get)
```

### 5.5 替代词转移检测（原 A2，合入 T3）

```python
def check_substitution_transfer(group: NounGroup, paragraphs: List[str]) -> TransferResult:
    """
    检测替代词是否带来了新感知通道

    v3.0 A2 核心逻辑，合入 T3 作为子检测：
    - 原词通道分布 vs 变体通道分布
    - 转移率 = 变体非视觉占比 - 原词非视觉占比
    """
    # 原词的通道分布
    core_channels = []
    for idx, para in enumerate(paragraphs):
        if group.core in para:
            ch = detect_channel_for_occurrence(group.core, para)
            core_channels.append(ch)

    # 变体的通道分布
    variant_channels = []
    for variant in group.variants:
        for idx, para in enumerate(paragraphs):
            if variant in para:
                ch = detect_channel_for_occurrence(variant, para)
                variant_channels.append(ch)

    core_non_visual = sum(1 for c in core_channels if c not in ("视觉", "未检测")) / max(len(core_channels), 1)
    variant_non_visual = sum(1 for c in variant_channels if c not in ("视觉", "未检测")) / max(len(variant_channels), 1)

    transfer_rate = variant_non_visual - core_non_visual

    if transfer_rate > 0.1:
        status = "有效转移"
    elif transfer_rate < -0.1:
        status = "退步"
    else:
        status = "同通道平移"

    return TransferResult(
        noun=group.core,
        core_non_visual_ratio=core_non_visual,
        variant_non_visual_ratio=variant_non_visual,
        transfer_rate=transfer_rate,
        status=status
    )
```

### 5.6 感官萦绕检测（搬迁 D4）

```python
def check_sensory_lingering(paragraphs: List[str]) -> List[Issue]:
    """
    检测感官细节引入后是否在后续段落再现
    逻辑搬迁自 scene_perception_lint.py D4 v1.1
    保留：5段窗口 + ≥3次视为萦绕
    """
    # ...
```

### 5.7 评分公式

```python
# T3 评分
group_scores = []

for group in discovered_groups:
    if group.total < 5:
        continue  # 样本不足

    # 通道覆盖率
    occurrences = find_all_occurrences(group, paragraphs)
    channels = [detect_channel_for_occurrence(o.word, paragraphs[o.para_idx]) for o in occurrences]
    non_visual_count = sum(1 for c in channels if c not in ("视觉", "未检测"))
    coverage = non_visual_count / len(channels)

    # 评分
    if coverage >= 0.4:
        s = 100
    elif coverage >= 0.25:
        s = 80
    elif coverage >= 0.1:
        s = 50
    else:
        s = 20
        if group.total > 15:  # 高频+单一=最严重
            s -= 20

    # 替代词转移扣分
    transfer = check_substitution_transfer(group, paragraphs)
    if transfer.status == "同通道平移":
        s -= 10
    elif transfer.status == "退步":
        s -= 15

    group_scores.append(s)

# 感官萦绕扣分
oneoff_count = count_sensory_oneoffs(paragraphs)
lingering_penalty = oneoff_count * 5

t3_score = max(0, min(100, sum(group_scores) / max(len(group_scores), 1) - lingering_penalty))
```

### 5.8 报告输出

```json
{
  "dim": "T3",
  "dim_name": "意象感知多样性",
  "score": 45.0,
  "stats": {
    "discovered_groups": 5,
    "groups_detail": [
      {
        "noun": "口子",
        "total": 18,
        "channel_distribution": {"视觉": 15, "听觉": 1, "触觉": 1, "嗅觉": 1, "效应": 0},
        "coverage_ratio": 0.17,
        "score": 50,
        "transfer": "同通道平移",
        "diagnosis": "18次出现中15次走视觉，非视觉覆盖率17%。替代词'口子'与原词'裂缝'走同一通道",
        "suggestion": "不换词，换感知方式：第5次写风声（听觉），第9次写温度（触觉），第13次写气味（嗅觉）"
      },
      {
        "noun": "铜钱",
        "total": 42,
        "channel_distribution": {"视觉": 10, "听觉": 5, "触觉": 3, "未检测": 4},
        "coverage_ratio": 0.38,
        "score": 80,
        "diagnosis": "42次出现，非视觉覆盖率38%，感知维度较丰富"
      }
    ],
    "sensory_oneoff_count": 2
  }
}
```

---

## 六、T4 节律控制

### 6.1 检测目标

回答：**情绪指标动作和指代是否失控？**

### 6.2 重复动作预算（搬迁 P3，改为自发现）

```python
def discover_recurring_actions(paragraphs: List[str]) -> List[ActionPattern]:
    """
    自动发现重复的情绪指标动作

    v2.0 P3 是硬编码（磨刀速度变化/铜钱翻转/手抖脸平静）
    v4.0 改为自发现：

    1. 扫描所有动作描述
    2. 找出跨段落重复出现的动作模式
    3. 按语义分组（共享核心动词）
    4. 检查每次出现的情绪上下文是否不同
    """
    # 动作动词集合
    ACTION_VERBS_SET = {"磨", "转", "翻", "抖", "握", "攥", "捏", "碰", "咬",
                        "站", "蹲", "走", "转", "停", "顿", "看", "盯"}

    # 扫描所有包含动作动词的段落
    action_occurrences = defaultdict(list)
    for idx, para in enumerate(paragraphs):
        for verb in ACTION_VERBS_SET:
            if verb in para:
                # 提取动作上下文（前后15字）
                pos = para.find(verb)
                context = para[max(0, pos-10):pos+10]
                action_occurrences[verb].append({
                    "para": idx + 1,
                    "verb": verb,
                    "context": context
                })

    # 找出重复≥4次的动作
    patterns = []
    for verb, occs in action_occurrences.items():
        if len(occs) >= 4:
            patterns.append(ActionPattern(
                verb=verb,
                count=len(occs),
                occurrences=occs,
                budget=4,  # 默认预算：4次/章
                over_limit=len(occs) > 4
            ))

    return patterns
```

### 6.3 指代密度（搬迁 P5，改为自发现）

```python
def discover_referential_patterns(paragraphs: List[str]) -> List[RefPattern]:
    """
    自动发现高频指代模式

    v2.0 P5 是硬编码（那几枚/那枚/它/掌中之物）
    v4.0 改为自发现：

    1. 扫描所有"那X""这X""它"模式
    2. 统计频率
    3. 超限的报告
    """
    full_text = "\n".join(paragraphs)

    # 指代模式正则
    ref_patterns = [
        (r"那[\u4e00-\u9fff]{1,2}", "那X", 6),    # 那几枚/那枚/那个
        (r"这[\u4e00-\u9fff]{1,2}", "这X", 6),    # 这枚/这个/这里
        (r"它[^\u4e00-\u9fff]", "它", 8),          # 它（代词）
        (r"掌中之物", "掌中之物", 3),               # 高情感浓度表达
    ]

    results = []
    for pattern, name, threshold in ref_patterns:
        matches = re.findall(pattern, full_text)
        count = len(matches)
        results.append(RefPattern(
            name=name,
            count=count,
            threshold=threshold,
            over_limit=count > threshold
        ))

    return results
```

### 6.4 评分公式

```python
# T4 评分
t4_score = 100

# 重复动作扣分
for pattern in action_patterns:
    if pattern.over_limit:
        excess = pattern.count - pattern.budget
        t4_score -= min(excess * 8, 20)

# 指代密度扣分
for ref in ref_patterns:
    if ref.over_limit:
        excess = ref.count - ref.threshold
        t4_score -= min(excess * 5, 15)

t4_score = max(0, t4_score)
```

---

## 七、综合评分

```python
# 综合评分
overall_score = T1 * 0.30 + T2 * 0.25 + T3 * 0.25 + T4 * 0.20

# 权重逻辑：
# T1 (30%): 最核心——场景是否被角色身体感知
# T2 (25%): 叙述者是否退场——作者介入次数
# T3 (25%): 意象感知是否多样——高频词的通道覆盖
# T4 (20%): 节律是否受控——动作/指代频率
```

### 评分等级

| 等级 | 分数 | 含义 |
|------|------|------|
| A | ≥85 | 感知织体良好，场景被角色身体充分感知 |
| B | 70-84 | 基本良好，有少量作者介入或感知单一 |
| C | 55-69 | 中等，信息交付模式残留，需优化 |
| D | <55 | 不足，叙述者主导，需重构写作思维 |

---

## 八、数据结构

```python
@dataclass
class ParagraphClass:
    """段落分类结果"""
    type: str           # embodied / info_dump / partial / weak / plain / short
    score: float        # 0-1
    signals: Dict       # 检测到的信号
    diagnosis: str = "" # 诊断说明（仅非 embodied 时）

@dataclass
class NounGroup:
    """高频名词组"""
    core: str                   # 核心词
    variants: List[str]         # 变体列表
    total: int                  # 总出现次数

@dataclass
class NounOccurrence:
    """单次出现记录"""
    para_idx: int               # 段落号
    word: str                   # 具体使用的词
    channel: str                # 感知通道
    context: str                # 上下文（所在句子）

@dataclass
class TransferResult:
    """替代词转移结果"""
    noun: str
    core_non_visual_ratio: float
    variant_non_visual_ratio: float
    transfer_rate: float
    status: str                 # 有效转移 / 同通道平移 / 退步

@dataclass
class ActionPattern:
    """重复动作模式"""
    verb: str
    count: int
    occurrences: List[Dict]
    budget: int
    over_limit: bool

@dataclass
class RefPattern:
    """指代模式"""
    name: str
    count: int
    threshold: int
    over_limit: bool

@dataclass
class TextureReport:
    """完整报告"""
    file: str
    total_chars: int
    total_paragraphs: int

    # T1
    t1_score: float
    para_classes: List[ParagraphClass]
    t1_issues: List[Issue]

    # T2
    t2_score: float
    translation_count: int
    punchline_count: int
    punchline_density: float
    world_rotation_count: int
    t2_issues: List[Issue]

    # T3
    t3_score: float
    discovered_groups: List[NounGroup]
    noun_coverage: List[Dict]    # 每个名词组的通道分布
    transfer_results: List[TransferResult]
    sensory_oneoff_count: int
    t3_issues: List[Issue]

    # T4
    t4_score: float
    action_patterns: List[ActionPattern]
    ref_patterns: List[RefPattern]
    t4_issues: List[Issue]

    # 综合
    overall_score: float
    summary: str
```

---

## 九、实现路线图

### 阶段1：核心引擎（T1 + T2）

**目标**：段落级诊断能跑通

- 实现 T1 具身感知度
  - 搬迁 D3 双层锚点系统（`_count_anchors` / `_get_prev_context`）
  - 搬迁 D5 焦距检测（`detect_focal_entry`）
  - 搬迁 D7 专名锚定（`_has_anchoring`）
  - 新写：段落分类器 `classify_paragraph_embodiment`
- 实现 T2 叙述者退场度
  - 搬迁 D2 动作后解释检测（`detect_narrator_translation`）
  - 搬迁 D6 世界自转（`detect_world_rotation`）
  - 新写：P2 修复版金句检测（`detect_punchline_fixed`）
- 用 Ch1 v7 验证

### 阶段2：意象分析（T3）

**目标**：名词级诊断能跑通

- 实现 A3 自发现管道（`discover_noun_groups`）
- 实现 A1 通道检测（`detect_channel_for_occurrence`，句子级上下文）
- 实现 A2 转移检测（`check_substitution_transfer`）
- 搬迁 D4 萦绕检测（`check_sensory_lingering`）
- 用三章 v7 验证，对比 v2.0 硬编码结果

### 阶段3：节律控制（T4）

**目标**：模式级诊断能跑通

- 搬迁 P3 重复动作检测，改为自发现模式
- 搬迁 P5 指代密度检测，改为自发现模式
- 用三章 v7 验证

### 阶段4：整合与验证

**目标**：统一报告 + 全量验证

- 整合四维为统一入口
- 用三章 v7 全量验证
- 对比 v2.0 + v3.0 的检测结果
- 更新 scene_perception_guide.md

### 验证标准

| 标准 | 预期结果 |
|------|---------|
| T1 对 Ch1 v7 第5段 | 判为 info_dump（信息密度高、感官低） |
| T2 对 Ch1 v7 "名字不能让伤口不疼" | 判为叙述者翻译（动作后解释） |
| T3 对 Ch1 v7 "口子" | 18次出现，非视觉覆盖率<20%，诊断感知单一 |
| T3 对 Ch1 v7 "口子"vs"裂缝" | 判为同通道平移（非"恢复原词"） |
| T3 自发现 | 自动找到与 v2.0 硬编码相同的 5 个意象组 |
| T4 对 Ch1 v7 磨刀 | 检测到6次，超4次预算 |
| T4 对 Ch2 v7 "那几枚" | 检测到16次，超6次预算 |
| T2 P2修复 | "安静。"不判为金句 |

---

## 十、文件结构

```
test/
├── perception_texture.py              ← v4.0 新建（T1-T4 统一入口）
├── perception_texture_v4_design.md    ← 本文档
├── framework_experiment.py            ← 保留作历史参照（不再使用）
├── scene_perception_lint.py           ← 保留作历史参照（代码搬迁后不再使用）
├── scene_perception_guide.md          ← 后续更新（整合 v4.0 术语）
├── perception_tracker_v3_design.md    ← 保留作历史参照
└── practice/
    ├── chapter_001_v7.txt
    ├── chapter_002_v7.txt
    ├── chapter_003_v7.txt
    ├── framework_ch1_v8.json           ← v2.0 报告（历史参照）
    ├── framework_ch2_v8.json
    └── framework_ch3_v8.json
```

---

## 十一、与现有工具的关系

### 11.1 代码复用清单

| 源文件 | 函数 | 去向 | 复用方式 |
|--------|------|------|---------|
| scene_perception_lint.py | `_count_anchors` | T1 | 直接搬迁 |
| scene_perception_lint.py | `_get_prev_context` | T1 | 直接搬迁 |
| scene_perception_lint.py | `detect_info_dump` | T1 | 信号合入分类器 |
| scene_perception_lint.py | `detect_spatial_drift` | T1 | 逻辑搬迁为子检测 |
| scene_perception_lint.py | `detect_focal_entry` | T1 | 直接搬迁 |
| scene_perception_lint.py | `detect_proper_noun_anchoring` | T1 | 直接搬迁 |
| scene_perception_lint.py | `detect_narrator_translation` | T2 | 直接搬迁 |
| scene_perception_lint.py | `detect_world_rotation` | T2 | 直接搬迁 |
| scene_perception_lint.py | `detect_sensory_oneoff` | T3 | 搬迁为子检测 |
| framework_experiment.py | `detect_punchline` | T2 | 修复后搬迁 |
| framework_experiment.py | `analyze_recurring_actions` | T4 | 改为自发现 |
| framework_experiment.py | `analyze_referential_density` | T4 | 改为自发现 |
| framework_experiment.py | `detect_sensory_channel` | T3 | 优化为句子级 |

### 11.2 不复用的部分

| 源 | 原因 |
|----|------|
| framework_experiment.py `IMAGERY_GROUPS` | 硬编码，由 T3 自发现替代 |
| framework_experiment.py `RECURRING_ACTION_PATTERNS` | 硬编码，由 T4 自发现替代 |
| framework_experiment.py `REFERENTIAL_PATTERNS` | 硬编码，由 T4 自发现替代 |
| framework_experiment.py `analyze_imagery` | P1 评分崩塌，由 T3 替代 |
| framework_experiment.py `analyze_substitution_quality` | P4 建议矛盾，由 T3 转移检测替代 |
| scene_perception_lint.py `diagnose` | 主流程重写 |

---

## 十二、CLI 接口

```bash
# 基本用法
python perception_texture.py chapter_001.txt

# JSON 输出
python perception_texture.py chapter_001.txt --json report.json

# 版本对比
python perception_texture.py chapter_001.txt --compare chapter_001_v7.txt

# 仅运行指定维度
python perception_texture.py chapter_001.txt --dims T1,T2
```

### 输出格式

```
============================================================
  感知织体诊断报告 v4.0
  文件: chapter_001_v7.txt
  字数: 2580 | 段落: 45
============================================================

  综合评分: 68.3 / 100  [C-中等]
  信息交付模式残留，意象感知单一，需优化感知维度覆盖

------------------------------------------------------------
  T1 具身感知度    ████████████░░░░░░░░  62.2
       具身段: 28/45 (62.2%) | 信息交付段: 5 | 焦距: 画面级广角
       问题 (3条):
         [warning] 第5段: 信息密度=6.5，感官=0——信息交付段
         [warning] 第27段: 动作段无空间锚
         [warning] 第3段: "大徵"首次出现无锚定

  T2 叙述者退场度  ██████████████░░░░░░  70.0
       动作后解释: 3处 | 金句: 2个(1.2/千字) | 世界自转: 4段
       问题 (3条):
         [warning] 第5段: "名字不能让伤口不疼"——动作后解释
         [warning] 第13段: "铜钱算规则，命另算"——哲理收尾

  T3 意象感知多样性 ████████░░░░░░░░░░░░  45.0
       发现名词组: 5 | 感官一次性: 2
       问题 (3条):
         [critical] '口子': 18次出现，非视觉覆盖率17%——感知单一
         [warning] '口子'vs'裂缝': 同通道平移——换词不换感知
         [info] '气味'类感官: 引入后5段内未再现——一次性

  T4 节律控制      ██████████████████░  85.0
       重复动作: 磨(6/4 超限) | 指代: 那X(8/6 超限)
       问题 (2条):
         [warning] '磨'动作: 6次/4次预算——超限
         [warning] '那X'指代: 8次/6次预算——超限

============================================================
```
