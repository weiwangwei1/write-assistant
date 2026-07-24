# 文件I/O优化指南

## 概述
基于对写作系统文件流转的全面分析，识别出3类文件冗余和4类读写低效问题。本指南定义优化方案、实施步骤和验证方法。

## 优化前问题分析

### 问题1: 正文三重存储
- chapter_draft.json 内嵌正文全文（约8-16KB）
- output/chapter_NNN.txt 存储正文正本
- memory/recent_chapters/ 存储正文副本（约7KB/章）
- 同一份正文存3个地方，读写3次

### 问题2: 审核源文件不归档
- detail_review_chN.json 和 deai_analysis_chN.json 被 merged_review_chN.json 吸收后仍留在 handoff/
- 每章累积约39KB无用文件
- 300章规模下 handoff/ 将堆积约11700KB无用文件

### 问题3: 角色库双重存储
- memory/characters.json (226KB) 全量包含8个独立角色卡内容
- memory/characters/ 目录下8个独立卡 (共158KB) 
- 完全重复存储，修改时需双写

### 问题4: 全文文件全量重建
- 每章入库时全量重建 output/{novel_title}_全文.txt
- 330章规模下每次重建约1MB文本写入
- 入库写入复杂度O(N)而非O(1)

### 问题5: quality+final 评分重叠
- quality_review_chN.json 和 final_review_chN.json 评分维度高度重叠
- 两个文件都基于修订终稿评分，维度重复率约60%
- 每章产生约44KB冗余评分数据

## 优化方案

### 优化1: 正文单源存储
| 项目 | 优化前 | 优化后 |
|------|--------|--------|
| 草稿正文 | chapter_draft.json 内嵌 | 仅引用 output/ 路径 |
| 滑动窗口 | memory/recent_chapters/ 副本 | 按需从 output/ 读取 |
| 正文存储位置 | 3处 | 1处 (output/) |

实施Skill: chapter-writer v2.5, memory-manager v1.5

### 优化2: 审核源文件归档
| 项目 | 优化前 | 优化后 |
|------|--------|--------|
| detail+deai源文件 | 长期留在handoff/ | 合并后移入 handoff/archive_ch{N}/ |
| handoff/文件数 | 每章+7个 | 每章+4个(draft元数据/merged/final/评估) |

### 优化3: 角色库索引化
| 项目 | 优化前 | 优化后 |
|------|--------|--------|
| characters.json | 226KB全量角色卡 | ~5KB索引+关系网络 |
| 独立卡 | 158KB(被视为副本) | 158KB(唯一源) |
| 修改角色 | 需双写 | 只改独立卡 |

实施Skill: memory-manager v1.5

### 优化4: 全文文件追加模式
| 项目 | 优化前 | 优化后 |
|------|--------|--------|
| 写入模式 | 全量重建(330章=1MB) | 追加本章(3KB) |
| 复杂度 | O(N) | O(1) |
| 330章总写入量 | ~165MB(累计) | ~1MB |

实施Skill: memory-manager v1.5

### 优化5: 审核步骤合并 ✅ 已实施
| 项目 | 优化前 | 优化后 |
|------|--------|--------|
| 审核步骤 | quality(8维) → final(8维) | unified_review(12维) |
| 中间文件 | 2个(quality+final) | 1个(unified_review) |
| 每章节省 | ~20KB + 1次读写 | - |

实施方式: 创建 `auto-runner/unified_review_spec.md` 规范文件，定义12维统一评分（8技术维+4补充维），权重等价转换（技术维×0.6，补充维×0.4），评分公式 `unified_score = technical_score×0.6 + supplementary_score×0.4` 与传统 `final_score` 完全等价。Ch12等价性验证通过：unified_score(9.51) == final_score(9.51)。样例文件：`handoff/chapters/unified_review_ch012.json`。task_config模板已更新支持unified模式配置。

## 目录结构优化

### 优化前
```
handoff/
├── topic_screening.json     (立项期)
├── title_review.json        (立项期)
├── outline.json             (立项期)
├── outline_review.json      (立项期)
├── characters.json          (立项期)
├── setting_review.json      (立项期)
├── chapter_draft.json       (单章期, 无章节后缀)
├── detail_review_ch11.json  (单章期)
├── deai_analysis_ch11.json  (单章期)
├── merged_review_ch11.json  (单章期)
├── quality_review_ch11.json (单章期)
├── final_review_ch11.json   (单章期)
└── ... (300章时将堆积1800+文件)
```

### 优化后
```
handoff/
├── setup/                   (立项期文件, 一次性)
│   ├── topic_screening.json
│   ├── title_review.json
│   ├── outline.json
│   ├── outline_review.json
│   ├── characters.json
│   └── setting_review.json
├── chapters/                (单章期文件, 按章号命名)
│   ├── draft_ch001.json     (元数据, 无正文)
│   ├── merged_review_ch001.json
│   ├── unified_review_ch001.json
│   └── parallel_assessment.json
├── archive/                 (归档的审核源文件)
│   ├── ch001/
│   │   ├── detail_review.json
│   │   └── deai_analysis.json
│   └── ...
└── task_plan.json           (运行时文件)
```

## 命名规范

| 文件类型 | 命名格式 | 示例 |
|---------|---------|------|
| 草稿元数据 | draft_ch{NNN:03d}.json | draft_ch001.json |
| 合并审核 | merged_review_ch{NNN:03d}.json | merged_review_ch011.json |
| 统一审稿 | unified_review_ch{NNN:03d}.json | unified_review_ch011.json |
| 终稿 | chapter_{NNN:03d}.txt | chapter_001.txt |
| 角色卡 | {角色名}.json | 许愿.json |

## 收益汇总

| 优化项 | 每章节省 | 300章节省 | 实施复杂度 |
|--------|---------|----------|-----------|
| 正文单源 | 8-16KB + 2次读写 | 2.4-4.8MB | 低 |
| 审核源归档 | 39KB留档 | 11.7MB | 低 |
| 角色库索引 | 158KB全局 | 158KB | 中 |
| 全文追加 | 1MB→3KB写入 | 165MB→1MB | 低 |
| 审核合并 | 20KB + 1步骤 | 6MB + 300步 | 中 |
| 目录分区 | 定位效率 | - | 低 |
| **合计** | **~70KB/章 + 3次读写 + 1步骤** | **~24MB + 900次读写 + 300步骤** | - |
