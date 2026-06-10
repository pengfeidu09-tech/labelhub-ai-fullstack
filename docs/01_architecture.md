# LabelHub 架构设计

## 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端层 (React)                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐     │
│  │ Owner    │  │ Labeler  │  │ Reviewer │  │ 公共组件     │     │
│  │ Dashboard│  │ Workbench│  │ Dashboard│  │ (Form Render)│     │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────────────┘     │
└───────┼─────────────┼─────────────┼─────────────────────────────┘
        │             │             │
        ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        API 网关层                                │
│              FastAPI Router /api/tasks, /api/templates...       │
└─────────────────────────┬───────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐   ┌────────────────┐   ┌──────────────┐
│   业务逻辑层  │   │   AI Agent层   │   │   数据访问层  │
│   Services   │   │  AI Reviewer   │   │  SQLAlchemy  │
└──────────────┘   └────────────────┘   └──────────────┘
                                          │
                                          ▼
                               ┌──────────────────┐
                               │    数据库层      │
                               │  SQLite/MySQL    │
                               └──────────────────┘
```

---

## 核心模块

### 1. 前端模块

| 模块 | 功能 | 文件路径 |
|------|------|----------|
| **OwnerDashboard** | 任务管理、模板配置、数据导入、结果查看、导出 | `frontend/src/pages/Owner` |
| **LabelerWorkbench** | 任务广场、任务领取、在线标注、草稿自动保存 | `frontend/src/pages/Labeler` |
| **ReviewerDashboard** | AI预审查看、人工审核、批量操作 | `frontend/src/pages/Reviewer` |
| **FormRenderer** | 动态表单渲染器 | `frontend/src/components/FormRenderer` |
| **TemplateBuilder** | 模板搭建器 | `frontend/src/components/TemplateBuilder` |

### 2. 后端模块

| 模块 | 功能 | 文件路径 |
|------|------|----------|
| **TaskService** | 任务 CRUD、状态管理 | `backend/app/services/task_service.py` |
| **TemplateService** | 模板 CRUD、Schema 验证 | `backend/app/services/template_service.py` |
| **DatasetService** | 数据集导入、管理 | `backend/app/services/dataset_service.py` |
| **SubmissionService** | 提交管理、草稿保存 | `backend/app/services/submission_service.py` |
| **AIReviewService** | AI 预审逻辑 | `backend/app/services/ai_review_service.py` |
| **HumanReviewService** | 人工审核逻辑 | `backend/app/services/human_review_service.py` |
| **ExportService** | 多格式导出 | `backend/app/services/export_service.py` |
| **AuditService** | 审计日志记录 | `backend/app/services/audit_service.py` |

---

## 数据库核心表设计

### 1. users - 用户表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 用户ID |
| username | VARCHAR(64) | UNIQUE NOT NULL | 用户名 |
| email | VARCHAR(128) | UNIQUE | 邮箱 |
| role | VARCHAR(32) | NOT NULL | 角色：owner/labeler/reviewer |
| password_hash | VARCHAR(256) | NOT NULL | 密码哈希 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 更新时间 |

### 2. tasks - 任务表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 任务ID |
| name | VARCHAR(128) | NOT NULL | 任务名称 |
| description | TEXT | | 任务描述 |
| template_id | INTEGER | FOREIGN KEY REFERENCES template_schemas(id) | 关联模板ID |
| status | VARCHAR(32) | NOT NULL DEFAULT 'draft' | 任务状态：draft/published/paused/ended |
| ai_review_enabled | BOOLEAN | DEFAULT FALSE | 是否启用AI审核 |
| ai_config | JSON | | AI配置（评分维度、阈值等） |
| deadline | DATETIME | | 截止日期 |
| created_by | INTEGER | FOREIGN KEY REFERENCES users(id) | 创建者ID |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 更新时间 |

### 3. template_schemas - 模板Schema表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 模板ID |
| name | VARCHAR(128) | NOT NULL | 模板名称 |
| description | TEXT | | 模板描述 |
| schema | JSON | NOT NULL | 模板JSON Schema |
| schema_version | VARCHAR(16) | NOT NULL DEFAULT '1.0' | Schema版本号 |
| dataset_type | VARCHAR(32) | NOT NULL | 数据集类型：qa_quality/preference_compare/custom |
| frozen_after_publish | BOOLEAN | DEFAULT FALSE | 发布后是否冻结 |
| created_by | INTEGER | FOREIGN KEY REFERENCES users(id) | 创建者ID |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 更新时间 |

### 4. dataset_items - 数据项表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 数据项ID |
| task_id | INTEGER | FOREIGN KEY REFERENCES tasks(id) | 关联任务ID |
| data | JSON | NOT NULL | 原始数据 |
| status | VARCHAR(32) | NOT NULL DEFAULT 'imported' | 数据项状态：imported/unclaimed/claimed/drafting/submitted/ai_reviewing/ai_reviewed/human_reviewing/approved/rejected/export_ready |
| claimed_by | INTEGER | FOREIGN KEY REFERENCES users(id) | 领取者ID |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 更新时间 |

### 5. drafts - 草稿表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 草稿ID |
| task_id | INTEGER | FOREIGN KEY REFERENCES tasks(id) | 关联任务ID |
| dataset_item_id | INTEGER | FOREIGN KEY REFERENCES dataset_items(id) | 关联数据项ID |
| labeler_id | INTEGER | FOREIGN KEY REFERENCES users(id) | 标注员ID |
| data | JSON | NOT NULL | 草稿数据 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 更新时间 |

### 6. submissions - 提交表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 提交ID |
| task_id | INTEGER | FOREIGN KEY REFERENCES tasks(id) | 关联任务ID |
| dataset_item_id | INTEGER | FOREIGN KEY REFERENCES dataset_items(id) | 关联数据项ID |
| labeler_id | INTEGER | FOREIGN KEY REFERENCES users(id) | 标注员ID |
| data | JSON | NOT NULL | 标注数据 |
| status | VARCHAR(32) | NOT NULL DEFAULT 'draft' | 提交状态：draft/submitted/ai_reviewing/ai_passed/ai_rejected/ai_need_human/human_reviewing/approved/rejected_to_modify/revised_submitted |
| rejected_reason | TEXT | | 打回原因 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 更新时间 |

### 7. ai_review_jobs - AI审核任务表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 任务ID |
| submission_id | INTEGER | FOREIGN KEY REFERENCES submissions(id) | 关联提交ID |
| status | VARCHAR(32) | NOT NULL DEFAULT 'pending' | 任务状态：pending/running/success/failed |
| prompt_template | TEXT | | 使用的提示词模板 |
| error_message | TEXT | | 错误信息 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 更新时间 |

### 8. ai_review_results - AI审核结果表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 结果ID |
| job_id | INTEGER | FOREIGN KEY REFERENCES ai_review_jobs(id) | 关联任务ID |
| submission_id | INTEGER | FOREIGN KEY REFERENCES submissions(id) | 关联提交ID |
| overall_score | FLOAT | | 综合评分 (0-100) |
| conclusion | VARCHAR(32) | NOT NULL | 结论：pass/reject/human_review |
| dimension_scores | JSON | | 各维度评分详情 |
| suggestions | TEXT | | 质检建议 |
| mock_mode | BOOLEAN | DEFAULT TRUE | 是否Mock模式 |
| raw_response | TEXT | | AI原始响应 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

### 9. human_reviews - 人工审核表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 审核ID |
| submission_id | INTEGER | FOREIGN KEY REFERENCES submissions(id) | 关联提交ID |
| reviewer_id | INTEGER | FOREIGN KEY REFERENCES users(id) | 审核员ID |
| result | VARCHAR(32) | NOT NULL | 审核结果：approved/rejected/revised |
| comments | TEXT | | 审核意见 |
| revised_data | JSON | | 修订数据 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

### 10. audit_logs - 审计日志表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 日志ID |
| user_id | INTEGER | FOREIGN KEY REFERENCES users(id) | 操作用户ID |
| action | VARCHAR(64) | NOT NULL | 操作类型（如 task_publish, item_claim, submission_submit） |
| target_type | VARCHAR(32) | NOT NULL | 目标类型：task/template/dataset_item/submission/ai_review/human_review/export |
| target_id | INTEGER | NOT NULL | 目标ID |
| before_data | JSON | | 操作前数据 |
| after_data | JSON | | 操作后数据 |
| extra_info | JSON | | 额外信息 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

### 11. export_jobs - 导出任务表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 导出ID |
| task_id | INTEGER | FOREIGN KEY REFERENCES tasks(id) | 关联任务ID |
| user_id | INTEGER | FOREIGN KEY REFERENCES users(id) | 操作用户ID |
| format | VARCHAR(16) | NOT NULL | 导出格式：json/jsonl/csv/excel |
| status | VARCHAR(32) | NOT NULL DEFAULT 'pending' | 导出状态：pending/running/success/failed |
| file_path | VARCHAR(512) | | 导出文件路径 |
| row_count | INTEGER | | 导出行数 |
| error_message | TEXT | | 错误信息 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 更新时间 |

---

## 实体关系图

```
users ───────────────────────────────────────────────────────────────┐
  │                                                                 │
  │ 1:N                                                             │ 1:N
  ▼                                                                 ▼
tasks ◄─────────── template_schemas                         audit_logs
  │                     │                                           │
  │ 1:N                 │ 1:N                                       │
  ▼                     ▼                                           │
dataset_items ─────── submissions ◄──────────────────────────────────┘
     │                    │
     │ 1:N                │ 1:N
     ▼                    ▼
  drafts           ai_review_jobs
                      │
                      │ 1:1
                      ▼
               ai_review_results
                      │
submissions ──────────┴─────────── human_reviews
  │
  │ 1:N
  ▼
export_jobs
```

---

## 数据流

### 数据标注流程

```
Owner创建任务 ──► 配置模板 ──► 导入数据 ──► 发布任务
                                                │
                        Labeler领取 ──► 标注作答 ──► 自动保存草稿 ──► 提交
                                                                        │
                                                                  AI预审 ──► pass/reject/human_review
                                                                        │
                                                         Reviewer审核 ──► 通过/打回/修订
                                                                        │
                                                                  导出数据
```

---

## 核心设计原则

1. **状态机驱动**: 所有业务实体都有明确的状态定义和状态迁移规则
2. **审计追踪**: 所有关键操作都记录审计日志，支持追溯
3. **异步处理**: AI审核和导出任务采用异步模式，避免阻塞
4. **Schema 驱动**: 模板和表单通过 JSON Schema 解耦，支持动态扩展
5. **Mock 优先**: AI 审核默认使用 Mock 模式，保证无 API Key 也能完整演示