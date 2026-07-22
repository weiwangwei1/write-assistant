# 交接卡格式规范

## 概述

交接卡（Handoff Card）是 Agent 间通信的核心机制。上游 Agent 完成工作后，将产出写入对应的交接卡 JSON 文件；下游 Agent 读取交接卡获取输入，完成工作后写入下一张交接卡。

## 交接卡文件清单

| 文件名 | 从 → 到 | 用途 |
|--------|---------|------|
| `task_plan.json` | 总编 → 各Agent | 全局任务计划与进度 |
| `outline.json` | 大纲师 → 角色师 | 小说大纲与情节线 |
| `characters.json` | 角色师 → 写手 | 角色卡与人物关系 |
| `chapter_draft.json` | 写手 → 审稿员 | 章节初稿 |
| `review_feedback.json` | 审稿员 → 写手/适配师 | 评审反馈或通过通知 |
| `final_chapter.json` | 适配师 → 发布 | 终稿与发布信息 |

## 通用格式

```json
{
  "card_type": "outline|characters|draft|review|final",
  "from": "agent-name",
  "to": "agent-name",
  "timestamp": "ISO-8601",
  "status": "pending|in_progress|completed|rejected",
  "novel_id": "novel_001",
  "chapter_num": null,
  "content": {},
  "instructions": ""
}
```

## 状态流转

```
pending → in_progress → completed
                     ↘ rejected (需重写)
```

## 使用规则

1. 上游 Agent 写卡时设置 `status: "pending"`
2. 下游 Agent 读卡后将 `status` 改为 `"in_progress"`
3. 完成后改为 `"completed"` 并写入下一张交接卡
4. 审稿不通过时设为 `"rejected"`，附带修改建议
5. 每张卡处理完毕后保留存档，不删除
