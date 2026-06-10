# LabelHub 状态机设计

## 概述

LabelHub 包含 4 个核心状态机，覆盖标注数据从创建到导出的全生命周期：

| 状态机 | 关联实体 | 说明 |
|--------|----------|------|
| **任务状态机** | Task | 管理任务的生命周期 |
| **标注/提交状态机** | Submission / Annotation | 管理标注提交的流转 |
| **审核状态机** | HumanReview | 管理人工审核的决策 |
| **导出状态机** | ExportJob | 管理数据导出的执行 |

---

## 1. 任务状态机

### 状态定义

| 状态 | 值 | 说明 |
|------|----|------|
| 草稿 | `draft` | 任务未完成配置，不可被标注员领取 |
| 已发布 | `published` | 任务已发布，标注员可领取数据项 |
| 已暂停 | `paused` | 任务暂停，标注员不可领取新数据项 |
| 已结束 | `ended` | 任务已结束，所有操作终止 |

### 状态流转图

```
          create
            │
            ▼
    ┌──────────────┐
    │    draft     │
    └──────┬───────┘
           │ publish
           ▼
    ┌──────────────┐    pause     ┌──────────────┐
    │  published   │ ───────────► │    paused    │
    └──────┬───────┘              └──────┬───────┘
           │                             │ resume (= publish)
           │                             ▼
           │              ┌──────────────────────┐
           │              │     published        │
           │              └──────────┬───────────┘
           │                         │
           │    end                  │ end
           └─────────────────────────┤
                                     ▼
                            ┌──────────────┐
                            │    ended     │
                            └──────────────┘
```

### 状态迁移规则

| 当前状态 | 触发事件 | 目标状态 | 操作者 | API |
|----------|----------|----------|--------|-----|
| draft | publish | published | Owner | `POST /api/tasks/{id}/publish` |
| published | pause | paused | Owner | `POST /api/tasks/{id}/pause` |
| paused | resume | published | Owner | `POST /api/tasks/{id}/publish` |
| published | end | ended | Owner | `POST /api/tasks/{id}/end` |
| paused | end | ended | Owner | `POST /api/tasks/{id}/end` |
| ended | — | — | — | 终态，不可迁移 |

---

## 2. 标注/提交状态机

### 状态定义

| 状态 | 值 | 说明 |
|------|----|------|
| 未领取 | `unclaimed` | 数据项未被任何标注员领取 |
| 已领取 | `claimed` | 标注员已领取，尚未开始标注 |
| 草稿 | `draft` | 标注员正在标注，已保存草稿 |
| 已提交 | `submitted` | 标注员已提交，等待审核 |
| 人工审核中 | `human_reviewing` | 审核员正在审核 |
| 已通过 | `approved` | 审核通过，可导出 |
| 待修改 | `rejected_to_modify` | 审核打回，标注员需修改 |
| 可导出 | `export_ready` | 已标记为可导出 |

### 状态流转图

```
           数据导入
              │
              ▼
       ┌──────────────┐    claim     ┌──────────────┐
       │  unclaimed   │ ───────────► │   claimed    │
       └──────────────┘              └──────┬───────┘
                                           │ save_draft
                                           ▼
                                    ┌──────────────┐
                                    │    draft     │◄──────────────┐
                                    └──────┬───────┘               │
                                           │ submit                │ 修改后重新提交
                                           ▼                       │
                                    ┌──────────────┐               │
                                    │  submitted   │               │
                                    └──────┬───────┘               │
                                           │                       │
                                           ▼                       │
                                    ┌──────────────┐               │
                                    │human_reviewing│              │
                                    └──────┬───────┘               │
                                    ┌──────┼──────┐                │
                                    ▼             ▼                │
                             ┌──────────┐  ┌────────────────┐      │
                             │ approved │  │rejected_to_modify│─────┘
                             └────┬─────┘  └────────────────┘
                                  │
                                  ▼
                             ┌──────────────┐
                             │export_ready  │
                             └──────────────┘
```

### 状态迁移规则

| 当前状态 | 触发事件 | 目标状态 | 操作者 | 说明 |
|----------|----------|----------|--------|------|
| unclaimed | claim | claimed | Labeler | 标注员领取数据项 |
| claimed | save_draft | draft | Labeler | 保存草稿 |
| draft | save_draft | draft | Labeler | 更新草稿 |
| draft | submit | submitted | Labeler | 提交标注 |
| submitted | start_review | human_reviewing | Reviewer | 开始审核 |
| human_reviewing | approve | approved | Reviewer | 审核通过 |
| human_reviewing | reject | rejected_to_modify | Reviewer | 打回修改 |
| rejected_to_modify | resubmit | draft | Labeler | 修改后重新提交（回到草稿状态） |
| approved | mark_export | export_ready | System | 标记为可导出 |

### 关键约束

- **禁止状态回退**：已提交（submitted）的标注不能回退到草稿（draft）状态
- **终端状态**：approved / export_ready 为终端状态，不可再迁移
- **work_key 唯一性**：同一 `task_id:dataset_item_id:labeler_id` 组合在同一时刻只能有一条活跃记录

---

## 3. 审核状态机

### 状态定义

审核状态嵌入在标注/提交状态中，通过 `human_reviewing` → `approved` / `rejected_to_modify` 体现。

### 状态流转图

```
           标注提交
              │
              ▼
       ┌──────────────┐
       │  submitted   │
       └──────┬───────┘
              │ start_review
              ▼
       ┌──────────────┐
       │human_reviewing│
       └──────┬───────┘
         ┌────┴────┐
         ▼         ▼
  ┌──────────┐  ┌────────────────┐
  │ approved │  │rejected_to_modify│
  └──────────┘  └────────────────┘
```

### 审核决策

| 决策 | 目标状态 | 说明 | API |
|------|----------|------|-----|
| approve | approved | 审核通过，数据可导出 | `POST /api/reviews/{id}/approve` |
| reject | rejected_to_modify | 打回修改，标注员需修改后重新提交 | `POST /api/reviews/{id}/reject` |
| revise | approved | 审核员直接修订后通过 | `POST /api/reviews/{id}/revise` |

### 审核信息记录

每次审核操作记录以下信息：

| 字段 | 说明 |
|------|------|
| reviewer_id | 审核员 ID |
| action | 审核动作（approve/reject/revise） |
| comment | 审核意见 |
| reviewed_at | 审核时间 |

---

## 4. 导出状态机

### 状态定义

| 状态 | 值 | 说明 |
|------|----|------|
| 待处理 | `pending` | 导出任务已创建，等待执行 |
| 执行中 | `running` | 正在生成导出文件 |
| 成功 | `success` | 导出完成，可下载 |
| 失败 | `failed` | 导出失败，可查看错误信息 |

### 状态流转图

```
           创建导出任务
              │
              ▼
       ┌──────────────┐    start     ┌──────────────┐
       │   pending    │ ───────────► │   running    │
       └──────────────┘              └──────┬───────┘
                                           │
                                    ┌──────┴──────┐
                                    ▼             ▼
                             ┌──────────┐  ┌──────────┐
                             │ success  │  │  failed  │
                             └──────────┘  └──────────┘
```

### 状态迁移规则

| 当前状态 | 触发事件 | 目标状态 | 说明 |
|----------|----------|----------|------|
| pending | start | running | 开始执行导出 |
| running | complete | success | 导出完成，file_path 已生成 |
| running | error | failed | 导出失败，error_message 已记录 |

### 导出格式

| 格式 | 值 | 说明 |
|------|----|------|
| JSON | `json` | 格式化 JSON 数组 |
| JSONL | `jsonl` | 每行一条 JSON 记录 |
| CSV | `csv` | CSV 表格（UTF-8 BOM） |
| XLSX | `xlsx` | Excel 表格 |

---

## 完整状态流转总览

```
任务创建 ──► draft ──► published
                           │
                           ▼
                    数据导入 ──► unclaimed
                                      │
                                      ▼ claim
                               claimed ──► draft ──► submitted
                                                          │
                                                          ▼
                                                   human_reviewing
                                                     ┌────┴────┐
                                                     ▼         ▼
                                                 approved   rejected_to_modify
                                                     │              │
                                                     ▼              │ 修改重提
                                              export_ready    draft ──► submitted
                                                     │
                                                     ▼
                                                  导出数据
```

---

## 状态迁移审计

所有状态迁移必须记录审计日志，确保操作可追溯：

| 审计动作 | 值 | 说明 |
|----------|----|------|
| 任务创建 | `task_create` | Owner 创建任务 |
| 任务发布 | `task_publish` | Owner 发布任务 |
| 任务暂停 | `task_pause` | Owner 暂停任务 |
| 任务恢复 | `task_resume` | Owner 恢复任务 |
| 任务结束 | `task_end` | Owner 结束任务 |
| 数据项领取 | `item_claim` | Labeler 领取数据项 |
| 数据项释放 | `item_unclaim` | Labeler 释放数据项 |
| 草稿保存 | `draft_save` | Labeler 保存草稿 |
| 标注提交 | `submission_submit` | Labeler 提交标注 |
| 标注修订 | `submission_revise` | Labeler 修订后重新提交 |
| AI 审核开始 | `ai_review_start` | 系统触发 AI 审核 |
| AI 审核完成 | `ai_review_complete` | AI 审核完成 |
| AI 预审执行 | `ai_precheck_run` | Labeler 触发 AI 预审 |
| 人工审核通过 | `review_approve` | Reviewer 通过审核 |
| 人工审核打回 | `review_reject` | Reviewer 打回审核 |
| 人工审核修订 | `review_revise` | Reviewer 修订后通过 |
| 导出创建 | `export_create` | Owner 创建导出任务 |
| 导出完成 | `export_complete` | 导出成功 |
| 导出失败 | `export_failed` | 导出失败 |
