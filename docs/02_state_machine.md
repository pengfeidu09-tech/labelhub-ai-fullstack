# LabelHub 状态机设计

## 状态机总览

LabelHub 包含 4 个核心状态机，覆盖任务全生命周期：

| 状态机 | 描述 | 关联表 |
|--------|------|--------|
| **task_status** | 任务状态流转 | tasks |
| **item_status** | 数据项状态流转 | dataset_items |
| **submission_status** | 提交状态流转 | submissions |
| **ai_review_status** | AI 审核状态流转 | ai_review_jobs |

---

## 1. Task Status - 任务状态机

### 状态定义

| 状态 | 说明 |
|------|------|
| `draft` | 草稿状态，任务未完成配置 |
| `published` | 已发布，标注员可领取 |
| `paused` | 暂停状态，标注员不可领取 |
| `ended` | 任务已结束 |

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
           │                             │ resume
           │                             ▼
           │              ┌──────────────────────┐
           │              │     published        │
           │              └──────────┬───────────┘
           │                         │ end
           │                         ▼
           │              ┌──────────────────────┐
           └─────────────►│      ended          │
                          └──────────────────────┘
```

### 状态迁移规则

| 当前状态 | 触发事件 | 目标状态 | 权限 |
|----------|----------|----------|------|
| draft | publish | published | owner |
| published | pause | paused | owner |
| paused | resume | published | owner |
| published | end | ended | owner |
| paused | end | ended | owner |

---

## 2. Item Status - 数据项状态机

### 状态定义

| 状态 | 说明 |
|------|------|
| `imported` | 已导入，等待处理 |
| `unclaimed` | 未被领取 |
| `claimed` | 已被标注员领取 |
| `drafting` | 标注中（有草稿） |
| `submitted` | 已提交 |
| `ai_reviewing` | AI 审核中 |
| `ai_reviewed` | AI 审核完成 |
| `human_reviewing` | 人工审核中 |
| `approved` | 已通过 |
| `rejected` | 已打回 |
| `export_ready` | 准备导出 |

### 状态流转图

```
           import
             │
             ▼
    ┌──────────────┐    claim     ┌──────────────┐
    │  imported    │ ────────────►│   unclaimed  │
    └──────┬───────┘              └──────┬───────┘
           │                             │ claim
           │                             ▼
           │              ┌──────────────────────────────┐
           │              │         claimed              │
           │              └──────────────────┬───────────┘
           │                                 │ start_draft
           │                                 ▼
           │              ┌──────────────────────────────┐
           │              │         drafting             │
           │              └──────────────────┬───────────┘
           │                                 │ submit
           │                                 ▼
           │              ┌──────────────────────────────┐
           │              │         submitted            │
           │              └──────────────────┬───────────┘
           │                                 │ trigger_ai_review
           │                                 ▼
           │              ┌──────────────────────────────┐
           │              │       ai_reviewing           │
           │              └──────────────────┬───────────┘
           │                      ┌──────────┼──────────┐
           │                      ▼          ▼          ▼
           │              ┌──────────┐ ┌──────────┐ ┌──────────┐
           │              │ai_reviewed│ │ai_reviewed│ │ai_reviewed│
           │              └────┬─────┘ └────┬─────┘ └──────┬────┘
           │                   │            │               │
           │                   │            │               │ trigger_human_review
           │                   │            │               ▼
           │                   │            │    ┌──────────────────┐
           │                   │            │    │  human_reviewing │
           │                   │            │    └────────┬─────────┘
           │                   │            │             │
           │         approve   │    reject  │      approve│reject
           │                   │            │             │
           ▼                   ▼            ▼             ▼
    ┌──────────┐       ┌──────────┐ ┌──────────┐    ┌──────────┐
    │approved  │       │ rejected │ │ unclaimed│    │approved  │
    └────┬─────┘       └────┬─────┘ └──────────┘    └────┬─────┘
         │                  │                            │
         │ export_ready     │ reclaim                    │ export_ready
         ▼                  ▼                            ▼
    ┌──────────┐       ┌──────────┐               ┌──────────┐
    │export_ready│      │ unclaimed│               │export_ready│
    └──────────┘       └──────────┘               └──────────┘
```

### 状态迁移规则

| 当前状态 | 触发事件 | 目标状态 | 权限 |
|----------|----------|----------|------|
| imported | initialize | unclaimed | system |
| unclaimed | claim | claimed | labeler |
| claimed | start_draft | drafting | labeler |
| drafting | save_draft | drafting | labeler |
| drafting | submit | submitted | labeler |
| submitted | trigger_ai_review | ai_reviewing | system |
| ai_reviewing | ai_review_complete | ai_reviewed | system |
| ai_reviewed | trigger_human_review | human_reviewing | system |
| ai_reviewed | auto_approve | approved | system |
| ai_reviewed | auto_reject | rejected | system |
| human_reviewing | approve | approved | reviewer |
| human_reviewing | reject | rejected | reviewer |
| human_reviewing | revise | approved | reviewer |
| approved | mark_export_ready | export_ready | system |
| rejected | reclaim | unclaimed | labeler |

---

## 3. Submission Status - 提交状态机

### 状态定义

| 状态 | 说明 |
|------|------|
| `draft` | 草稿（自动保存） |
| `submitted` | 已提交 |
| `ai_reviewing` | AI 审核中 |
| `ai_passed` | AI 通过 |
| `ai_rejected` | AI 拒绝 |
| `ai_need_human` | 需要人工审核 |
| `human_reviewing` | 人工审核中 |
| `approved` | 已通过 |
| `rejected_to_modify` | 打回修改 |
| `revised_submitted` | 修订后重新提交 |

### 状态流转图

```
           create
             │
             ▼
    ┌──────────────┐
    │    draft     │◄─────────────────────┐
    └──────┬───────┘                      │
           │ submit                       │ auto_save
           ▼                              │
    ┌──────────────┐                      │
    │  submitted   │                      │
    └──────┬───────┘                      │
           │ trigger_ai_review            │
           ▼                              │
    ┌──────────────┐                      │
    │ ai_reviewing │                      │
    └──────┬───────┘                      │
           │                              │
    ┌──────┼──────┐                       │
    ▼      ▼      ▼                       │
┌──────┐ ┌──────┐ ┌──────────┐            │
│ai_passed││ai_rejected││ai_need_human│   │
└───┬───┘ └───┬───┘ └────┬─────┘          │
    │         │          │                │
    │         │          ▼                │
    │         │    ┌──────────────┐       │
    │         │    │human_reviewing│       │
    │         │    └──────┬───────┘       │
    │         │           │               │
    │         │    ┌──────┼──────┐        │
    │         │    ▼      ▼      ▼        │
    │         │ ┌──────┐ ┌──────────┐ ┌──────┐
    │         │ │approved││rejected_to_modify││approved│
    │         │ └──────┘ └────┬─────┘ └──────┘
    │         │               │           │
    │         │               │ revise_submit
    │         │               ▼           │
    │         │    ┌────────────────┐     │
    │         │    │revised_submitted│─────┘
    │         │    └────────────────┘
    │         │
    │         │ reclaim
    │         ▼
    │    ┌──────────────┐
    │    │    draft     │
    │    └──────────────┘
    │
    ▼
┌──────────────┐
│  approved    │
└──────────────┘
```

### 状态迁移规则

| 当前状态 | 触发事件 | 目标状态 | 权限 |
|----------|----------|----------|------|
| draft | auto_save | draft | labeler |
| draft | submit | submitted | labeler |
| submitted | trigger_ai_review | ai_reviewing | system |
| ai_reviewing | ai_pass | ai_passed | system |
| ai_reviewing | ai_reject | ai_rejected | system |
| ai_reviewing | ai_need_human | ai_need_human | system |
| ai_passed | auto_approve | approved | system |
| ai_passed | trigger_human_review | human_reviewing | system |
| ai_rejected | auto_reject | rejected_to_modify | system |
| ai_need_human | trigger_human_review | human_reviewing | system |
| human_reviewing | approve | approved | reviewer |
| human_reviewing | reject | rejected_to_modify | reviewer |
| human_reviewing | revise | approved | reviewer |
| rejected_to_modify | revise_submit | revised_submitted | labeler |
| revised_submitted | trigger_ai_review | ai_reviewing | system |

---

## 4. AI Review Status - AI 审核状态机

### 状态定义

| 状态 | 说明 |
|------|------|
| `pending` | 等待审核 |
| `running` | 审核中 |
| `success` | 审核成功 |
| `failed` | 审核失败 |

### 状态流转图

```
           create
             │
             ▼
    ┌──────────────┐    start     ┌──────────────┐
    │   pending    │ ───────────► │   running    │
    └──────┬───────┘              └──────┬───────┘
           │ cancel                      │
           ▼                            │
    ┌──────────────┐             ┌──────┴──────┐
    │    failed    │◄────────────┼────────────►│   success    │
    └──────────────┘             │             └──────────────┘
                                 │
                                 ▼
                          ┌──────────────┐
                          │    failed    │
                          └──────────────┘
```

### 状态迁移规则

| 当前状态 | 触发事件 | 目标状态 | 权限 |
|----------|----------|----------|------|
| pending | start | running | system |
| pending | cancel | failed | system |
| running | complete | success | system |
| running | error | failed | system |

### AI 审核结论

| 结论 | 说明 | 触发条件 |
|------|------|----------|
| `pass` | 通过 | 评分 >= 通过阈值 |
| `reject` | 拒绝 | 评分 < 拒绝阈值 |
| `human_review` | 需要人工审核 | 拒绝阈值 <= 评分 < 通过阈值 |

---

## 完整状态流转图

```
任务创建 ──► draft ──► published
                           │
                           ▼
                    数据导入 ──► imported ──► unclaimed
                                                  │
                                                  ▼
                    领取任务 ──► claimed ──► drafting
                                                │
                                                ▼
                                           submitted
                                                │
                                                ▼
                                          ai_reviewing
                                                │
                                 ┌─────────────┼─────────────┐
                                 ▼             ▼             ▼
                              ai_passed   ai_rejected   ai_need_human
                                 │             │             │
                                 │             │             ▼
                                 │             │    human_reviewing
                                 │             │         │
                                 │             │    ┌────┴────┐
                                 │             │    ▼         ▼
                                 │             │ approved  rejected_to_modify
                                 │             │              │
                                 │             │              ▼
                                 │             │    revised_submitted
                                 │             │         │
                                 │             └─────────┘
                                 │
                                 ▼
                            approved ──► export_ready
```

---

## 状态迁移审计

所有状态迁移必须记录审计日志，记录内容包括：

| 字段 | 说明 |
|------|------|
| `user_id` | 操作人ID |
| `action` | 操作类型（如 task_publish, item_claim, submission_submit） |
| `target_type` | 目标类型（task/dataset_item/submission/ai_review/human_review/export） |
| `target_id` | 目标ID |
| `before_data` | 状态变更前数据（包含原状态） |
| `after_data` | 状态变更后数据（包含新状态） |
| `created_at` | 操作时间 |

### 审计日志记录时机

| 操作 | 触发记录 |
|------|----------|
| 任务创建 | task_create |
| 任务发布 | task_publish |
| 任务暂停 | task_pause |
| 任务恢复 | task_resume |
| 任务结束 | task_end |
| 数据项导入 | item_import |
| 数据项领取 | item_claim |
| 草稿保存 | draft_save |
| 提交 | submission_submit |
| AI 审核开始 | ai_review_start |
| AI 审核完成 | ai_review_complete |
| 人工审核开始 | human_review_start |
| 人工审核通过 | human_review_approve |
| 人工审核打回 | human_review_reject |
| 人工审核修订 | human_review_revise |
| 修订提交 | submission_revise_submit |
| 导出任务创建 | export_create |
| 导出任务完成 | export_complete |