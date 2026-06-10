# LabelHub 系统架构文档

## 1. 系统整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Frontend (React / TypeScript)                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ── Demo Mode │
│  │  Owner   │ │  Labeler │ │ Reviewer │ │  Common  │    Switch     │
│  │  Pages   │ │  Pages   │ │  Pages   │ │  Pages   │              │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘              │
│       └─────────────┴─────────────┴────────────┘                    │
│                          │ REST API                                 │
└──────────────────────────┼──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      API Gateway (FastAPI)                          │
│   ┌─────────────────────────────────────────────────────────┐       │
│   │  20 Routers: tasks, templates, datasets, labeler,       │       │
│   │  ai_reviews, reviews, exports, audit_logs, owner, ...   │       │
│   └────────────────────────┬────────────────────────────────┘       │
│                            │                                        │
│       ┌────────────────────┼────────────────────┐                   │
│       ▼                    ▼                    ▼                   │
│ ┌───────────┐    ┌─────────────────┐    ┌───────────────┐          │
│ │ Business  │    │  AI Agent Layer │    │  Data Access  │          │
│ │ Logic     │    │                 │    │  (SQLAlchemy) │          │
│ │ Services  │    │ ┌─────────────┐ │    │               │          │
│ │           │    │ │ AI Precheck │ │    │  ORM Models   │          │
│ │ task_svc  │    │ │ Pipeline    │ │    │  Repositories │          │
│ │ template  │    │ └─────────────┘ │    │               │          │
│ │ annot_svc │    │ ┌─────────────┐ │    │               │          │
│ │ review_svc│    │ │ AI Provider │ │    │               │          │
│ │ export_svc│    │ │ (Mock/LLM)  │ │    │               │          │
│ │ audit_svc │    │ └─────────────┘ │    │               │          │
│ │ quality   │    │ ┌─────────────┐ │    │               │          │
│ │ dashboard │    │ │ Rule Engine │ │    │               │          │
│ │ ...       │    │ └─────────────┘ │    │               │          │
│ └─────┬─────┘    └─────────────────┘    └───────┬───────┘          │
│       │                                         │                  │
└───────┼─────────────────────────────────────────┼──────────────────┘
        │                                         │
        ▼                                         ▼
┌───────────────────┐                  ┌─────────────────────┐
│  annotations.json │                  │  Database (SQLite)  │
│  (File Storage)   │                  │                     │
│                   │                  │  ┌───────────────┐  │
│  标注结果文件      │                  │  │ tasks         │  │
│  导出文件          │                  │  │ dataset_items │  │
│  (exports/)       │                  │  │ submissions   │  │
│                   │                  │  │ ai_review_runs│  │
│                   │                  │  │ human_reviews │  │
│                   │                  │  │ audit_logs    │  │
│                   │                  │  │ ...           │  │
│                   │                  │  └───────────────┘  │
└───────────────────┘                  └─────────────────────┘
```

**架构要点：**

- **Frontend** 采用 React + TypeScript，按角色（Owner / Labeler / Reviewer）划分页面模块，内置 Demo Mode 开关
- **API Gateway** 基于 FastAPI，包含 20 个 Router，统一处理请求路由、参数校验与响应格式
- **Business Logic Layer** 由 17 个 Service 模块组成，封装核心业务逻辑
- **AI Agent Layer** 独立部署，包含 AI Precheck Pipeline、AI Provider 与 Rule Engine，当前为 Mock 模式
- **Data Access Layer** 使用 SQLAlchemy ORM，统一管理数据库读写
- **Database** 使用 SQLite，轻量级单文件部署
- **File Storage** 使用 `annotations.json` 存储标注结果，`exports/` 目录存储导出文件，与数据库并行存储

---

## 2. 前端模块划分

### 2.1 按角色划分的页面

#### Owner 页面（11 个）

| 页面 | 路径 | 说明 |
|------|------|------|
| OwnerDashboard | `/owner/dashboard` | 项目主控台，展示任务统计、质量指标、AI 审核概览 |
| TaskListPage | `/owner/tasks` | 任务列表，支持筛选、排序、批量操作 |
| TaskDetailPage | `/owner/tasks/:id` | 任务详情，含配置、进度、数据项预览 |
| TaskResultsPage | `/owner/tasks/:id/results` | 任务结果中心，查看所有标注与审核结果 |
| TemplatePage | `/owner/templates` | 模板管理，列表与 CRUD 操作 |
| TemplateDesignerPage | `/owner/templates/designer` | 可视化模板设计器，拖拽式构建 Schema |
| DatasetPage | `/owner/datasets` | 数据集管理，导入、预览、分类 |
| ExportPage | `/owner/export` | 数据导出，选择格式与范围 |
| AnnotationPage | `/owner/annotation` | 标注管理，查看所有标注数据 |
| AuditLogPage | `/owner/audit` | 审计日志，全量操作追踪 |
| RubricLibraryPage | `/owner/rubrics` | 评分标准库，管理 AI 预审维度与规则 |

#### Labeler 页面（4 个）

| 页面 | 路径 | 说明 |
|------|------|------|
| TaskMarketPage | `/labeler/market` | 任务市场，浏览可领取的标注任务 |
| LabelWorkbenchPage | `/labeler/workbench` | 标注工作台，核心标注操作界面 |
| MySubmissionsPage | `/labeler/submissions` | 我的提交，查看提交历史与审核状态 |
| WorkReportPage | `/labeler/report` | 工作报告，个人工作量与质量统计 |

#### Reviewer 页面（2 个）

| 页面 | 路径 | 说明 |
|------|------|------|
| ReviewQueuePage | `/reviewer/queue` | 审核队列，待审核任务列表 |
| ReviewDetailPage | `/reviewer/review/:id` | 审核详情，查看标注结果并做出审核决定 |

#### Common 页面

| 页面 | 说明 |
|------|------|
| HomePage | 首页，角色入口与系统介绍 |
| MainLayout | 主布局，含导航栏、Demo Mode 开关、系统提示 |

### 2.2 关键组件

| 组件 | 说明 |
|------|------|
| FormRenderer | 根据 TemplateSchema 动态渲染标注表单，支持多种字段类型 |
| SchemaPreview | Schema 实时预览，展示模板结构 |
| TemplateCanvas | 模板设计画布，拖拽式编辑器核心组件 |
| ConnectionStatus | 连接状态指示器，实时显示后端与 AI 服务连通性 |

---

## 3. 后端模块划分

### 3.1 API 层（20 个 Router）

| Router | 路径前缀 | 说明 |
|--------|----------|------|
| health | `/api/health` | 健康检查，系统状态探针 |
| tasks | `/api/tasks` | 任务 CRUD 与状态管理 |
| templates | `/api/templates` | 模板 CRUD 与 Schema 管理 |
| datasets | `/api/datasets` | 数据集导入与管理 |
| labeler | `/api/labeler` | 标注员相关接口（领取、提交） |
| ai_reviews | `/api/ai-reviews` | AI 审核结果查询 |
| reviews | `/api/reviews` | 人工审核操作接口 |
| exports | `/api/exports` | 导出任务管理（列表） |
| export | `/api/export` | 导出执行接口（触发下载） |
| audit_logs | `/api/audit-logs` | 审计日志查询 |
| owner | `/api/owner` | Owner 专属聚合接口 |
| dev | `/api/dev` | 开发调试接口 |
| ai_precheck | `/api/ai-precheck` | AI 预审触发与结果查询 |
| seed_demo | `/api/seed-demo` | 演示数据种子接口 |
| workbench_session | `/api/workbench-sessions` | 标注工作台会话管理 |
| work_report | `/api/work-report` | 工作报告统计接口 |
| item_actions | `/api/item-actions` | 数据项操作（跳过、标记等） |
| rubrics | `/api/rubrics` | 评分标准 CRUD |
| quality | `/api/quality` | 质量指标查询 |
| dashboard | `/api/dashboard` | 仪表盘聚合数据 |

### 3.2 Service 层（17 个 Service）

| Service | 说明 |
|---------|------|
| task_service | 任务生命周期管理：创建、配置、发布、状态流转 |
| template_service | 模板管理：Schema 定义、版本控制、校验 |
| annotation_service | 标注数据管理：保存、查询、更新 |
| ai_precheck_service | AI 预审调度：触发预审、结果存储 |
| ai_precheck_pipeline | AI 预审流水线：规则引擎执行、评分计算、风险判定 |
| ai_provider | AI 提供者抽象：统一接口，当前 Mock 实现，可扩展接入 LLM |
| ai_review_service | AI 审核服务：审核结果聚合与分析 |
| human_review_service | 人工审核服务：审核操作、通过/驳回处理 |
| submission_service | 提交管理：标注提交、状态更新、关联审核 |
| export_service | 导出服务：格式转换、文件生成、任务管理 |
| audit_service | 审计服务：操作记录、日志查询、链路追踪 |
| task_stats_service | 任务统计：进度计算、完成率、质量指标 |
| quality_service | 质量服务：标注质量评估、一致性检查 |
| dashboard_service | 仪表盘服务：聚合统计数据、趋势分析 |
| dataset_import_service | 数据集导入：文件解析、数据项创建、批量入库 |
| state_machine_service | 状态机服务：任务/数据项状态流转控制、合法性校验 |

### 3.3 Models（12 个核心模型）

| Model | 说明 |
|-------|------|
| Task | 任务主表，包含模板、AI 配置、状态等 |
| DatasetItem | 数据项，包含 raw_data、状态、分类 |
| TemplateSchema | 模板 Schema，定义标注表单结构 |
| Submission | 标注提交，关联标注员与数据项 |
| AIReviewRun | AI 审核运行记录，含评分与建议 |
| HumanReview | 人工审核记录，含审核决定与意见 |
| AnnotationWorkSession | 标注工作会话，追踪标注过程 |
| ExportJob | 导出任务，记录导出状态与文件路径 |
| AuditLog | 审计日志，全量操作追踪 |
| Draft | 标注草稿，支持暂存 |
| DraftVersion | 草稿版本，支持版本回溯 |
| WorkReport | 工作报告，标注员工作量统计 |

---

## 4. 数据模型关系

系统采用三层嵌套的数据模型架构：

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Project / Task                                │
│                                                         │
│  Task                                                   │
│  ├── id, name, description                              │
│  ├── status (draft → published → in_progress → ...)     │
│  ├── template_schema_id ──────► TemplateSchema          │
│  ├── ai_config (预审开关、模型选择、阈值)                  │
│  ├── rubric_id ──────────────► Rubric                   │
│  └── created_by, created_at, ...                        │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Layer 2: DatasetItem                             │  │
│  │                                                   │  │
│  │  DatasetItem                                      │  │
│  │  ├── id, task_id ──► Task                         │  │
│  │  ├── raw_data (原始数据内容)                        │  │
│  │  ├── status (pending → claimed → annotated → ...) │  │
│  │  ├── category (数据分类)                           │  │
│  │  └── metadata                                     │  │
│  │                                                   │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │  Layer 3: Annotation / Review / Audit       │  │  │
│  │  │                                             │  │  │
│  │  │  Submission                                 │  │  │
│  │  │  ├── item_id ──► DatasetItem                │  │  │
│  │  │  ├── labeler_id                             │  │  │
│  │  │  ├── annotation_data (标注结果)              │  │  │
│  │  │  └── status                                 │  │  │
│  │  │                                             │  │  │
│  │  │  AIReviewRun                                │  │  │
│  │  │  ├── submission_id ──► Submission           │  │  │
│  │  │  ├── overall_score, risk_level              │  │  │
│  │  │  └── dimension_scores, reason               │  │  │
│  │  │                                             │  │  │
│  │  │  HumanReview                                │  │  │
│  │  │  ├── submission_id ──► Submission           │  │  │
│  │  │  ├── reviewer_id                            │  │  │
│  │  │  └── decision, comment                      │  │  │
│  │  │                                             │  │  │
│  │  │  AnnotationWorkSession                      │  │  │
│  │  │  ├── item_id, labeler_id                    │  │  │
│  │  │  └── start_time, end_time, duration         │  │  │
│  │  │                                             │  │  │
│  │  │  ExportJob                                  │  │  │
│  │  │  ├── task_id ──► Task                       │  │  │
│  │  │  ├── format (json/csv/xlsx)                 │  │  │
│  │  │  └── file_path, status                      │  │  │
│  │  │                                             │  │  │
│  │  │  AuditLog                                   │  │  │
│  │  │  ├── user_id, action, target_type           │  │  │
│  │  │  └── target_id, detail, timestamp           │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**层级关系说明：**

- **Layer 1 — Task**：顶层任务容器，绑定 TemplateSchema 与 AI 配置，控制整体状态流转
- **Layer 2 — DatasetItem**：任务下的数据项，每条包含原始数据与自身状态，是标注的基本单元
- **Layer 3 — Annotation/Submission/Review/Audit**：围绕数据项产生的标注、审核、会话、导出与审计记录，构成完整的数据生命周期

---

## 5. 业务流程

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  任务创建  │───►│  数据导入  │───►│  任务发布  │───►│ 标注员领取 │
│  (Owner)  │    │  (Owner)  │    │  (Owner)  │    │ (Labeler) │
└──────────┘    └──────────┘    └──────────┘    └─────┬────┘
                                                      │
                                                      ▼
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  返工修改  │◄───│  驳回     │◄───│ 人工审核  │◄───│ AI 预审   │
│ (Labeler) │    │(Reviewer)│    │(Reviewer) │    │  (Agent)  │
└─────┬────┘    └──────────┘    └─────┬────┘    └──────────┘
      │                               │
      │         ┌──────────┐          │
      └────────►│  重新标注  │          │
                │ (Labeler) │          │
                └──────────┘          │
                                      ▼
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  审计追踪  │◄───│  数据导出  │◄───│  结果中心  │◄───│  审核通过  │
│  (System) │    │  (Owner)  │    │  (Owner)  │    │(Reviewer) │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

**流程详细说明：**

1. **任务创建**：Owner 创建任务，配置 TemplateSchema、AI 预审参数、评分标准
2. **数据导入**：Owner 通过 DatasetImportService 导入数据集，系统自动创建 DatasetItem 记录
3. **任务发布**：Owner 发布任务，状态从 `draft` 变为 `published`，任务进入市场
4. **标注员领取**：Labeler 在 TaskMarketPage 浏览并领取任务，DatasetItem 状态变为 `claimed`
5. **标注**：Labeler 在 LabelWorkbenchPage 进行标注，FormRenderer 根据 Schema 动态渲染表单
6. **AI 预审**：标注提交后，AI Precheck Pipeline 自动执行规则评分，生成 AIReviewRun
7. **提交**：标注员提交标注结果，创建 Submission 记录
8. **人工审核**：Reviewer 在 ReviewQueuePage 查看待审核项，在 ReviewDetailPage 做出审核决定
9. **通过/驳回**：Reviewer 决定通过或驳回，创建 HumanReview 记录
10. **返工**：若驳回，标注员需重新标注并重新提交
11. **结果中心**：Owner 在 TaskResultsPage 查看所有已通过标注的汇总
12. **导出**：Owner 选择格式与范围，触发 ExportJob，生成文件至 `exports/` 目录
13. **审计追踪**：全流程所有状态变更均记录至 AuditLog

---

## 6. AI 预审 Agent 流程

```
┌─────────────────────────────────────────────────────────┐
│                    AI Precheck Pipeline                  │
│                                                         │
│  ┌───────────┐                                          │
│  │  Input     │                                         │
│  │           │                                         │
│  │ • raw_data│                                         │
│  │ • 标注结果 │                                         │
│  │ • rubric  │                                         │
│  │   维度    │                                         │
│  │ • template│                                         │
│  │   schema  │                                         │
│  └─────┬─────┘                                         │
│        │                                               │
│        ▼                                               │
│  ┌───────────────────────────────────────────┐         │
│  │          Rule Engine Scoring               │         │
│  │                                           │         │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐    │         │
│  │  │Relevance│ │Accuracy │ │Complete-│    │         │
│  │  │ 相关性  │ │ 准确性  │ │ness     │    │         │
│  │  │ 评分    │ │ 评分    │ │完整性   │    │         │
│  │  └────┬────┘ └────┬────┘ │评分     │    │         │
│  │       │           │      └────┬────┘    │         │
│  │       │           │           │          │         │
│  │  ┌────┴───────────┴───────────┴────┐    │         │
│  │  │          Safety 安全性评分        │    │         │
│  │  └───────────────┬─────────────────┘    │         │
│  │                  │                      │         │
│  └──────────────────┼──────────────────────┘         │
│                     │                                │
│                     ▼                                │
│  ┌───────────────────────────────────────────┐       │
│  │              AI Provider                   │       │
│  │                                           │       │
│  │   当前模式: Mock                           │       │
│  │   未来扩展: OpenAI / Claude / 自定义 LLM   │       │
│  └───────────────────┬───────────────────────┘       │
│                      │                               │
│                      ▼                               │
│  ┌───────────────────────────────────────────┐       │
│  │              Output                        │       │
│  │                                           │       │
│  │  • overall_score    (综合评分 0-100)       │       │
│  │  • risk_level       (low/medium/high)     │       │
│  │  • suggested_action (approve/flag/reject) │       │
│  │  • confidence       (置信度 0-1)          │       │
│  │  • dimension_scores (各维度评分)           │       │
│  │  • reason           (评分理由)             │       │
│  │  • summary          (审核摘要)             │       │
│  │  • issue_tags       (问题标签列表)         │       │
│  └───────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

**流程说明：**

1. **输入组装**：将原始数据、标注结果、Rubric 维度定义、Template Schema 组装为预审输入
2. **规则引擎评分**：沿四个核心维度进行评分：
   - **Relevance（相关性）**：标注内容与原始数据的相关程度
   - **Accuracy（准确性）**：标注结果的准确程度
   - **Completeness（完整性）**：标注覆盖的完整程度
   - **Safety（安全性）**：内容安全性检查
3. **AI Provider 调用**：将规则引擎结果提交至 AI Provider 进行综合判断，当前使用 Mock 模式返回模拟结果
4. **输出生成**：生成包含评分、风险等级、建议动作、置信度、维度评分、理由、摘要、问题标签的完整审核结果

**Mock 模式说明：** 当前系统使用 Mock AI Provider，返回基于规则的模拟评分。未来可无缝切换至真实 LLM 服务，仅需实现 AI Provider 接口即可。

---

## 7. 审计日志链路

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│  用户操作  │  │ 系统事件  │  │ 状态变更  │  │ AI 事件   │
└─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘
      │             │             │             │
      └─────────────┴─────────────┴─────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │     AuditLog 记录      │
              │                       │
              │  • user_id            │
              │  • action             │
              │  • target_type        │
              │  • target_id          │
              │  • detail (JSON)      │
              │  • timestamp          │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │     查询与追踪         │
              │                       │
              │  • 按 user 筛选       │
              │  • 按 action 筛选     │
              │  • 按 target 筛选     │
              │  • 按时间范围筛选      │
              │  • 支持分页与排序      │
              └───────────────────────┘
```

**关键追踪动作：**

| Action | 说明 |
|--------|------|
| `task.create` | 任务创建 |
| `task.publish` | 任务发布 |
| `task.update` | 任务配置更新 |
| `dataset.import` | 数据集导入 |
| `item.claim` | 数据项领取 |
| `annotation.save` | 标注保存 |
| `annotation.submit` | 标注提交 |
| `ai_precheck.run` | AI 预审执行 |
| `review.approve` | 审核通过 |
| `review.reject` | 审核驳回 |
| `export.create` | 导出任务创建 |
| `export.complete` | 导出完成 |

**审计特性：**

- **全量记录**：所有状态流转均自动记录，不可篡改
- **链路追踪**：通过 `target_type` + `target_id` 可追踪任意实体的完整操作历史
- **多维查询**：支持按用户、动作、目标、时间范围组合查询
- **审计不可删除**：AuditLog 记录仅支持追加，不支持删除或修改

---

## 8. 导出链路

```
┌───────────┐     ┌──────────────┐     ┌──────────────┐
│ Owner 触发 │────►│ ExportJob    │────►│ 查询已通过    │
│ 导出请求   │     │ 创建 (pending)│     │ 标注数据      │
└───────────┘     └──────────────┘     └──────┬───────┘
                                               │
                                               ▼
┌───────────┐     ┌──────────────┐     ┌──────────────┐
│ 审计日志   │◄────│ 写入 exports/ │◄────│ 关联 AI 审核  │
│ 记录      │     │ 目录          │     │ 数据 JOIN     │
└───────────┘     └──────────────┘     └──────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ 格式转换      │
                  │              │
                  │ • JSON       │
                  │ • CSV        │
                  │ • XLSX       │
                  └──────────────┘
```

**导出流程详细步骤：**

1. **触发导出**：Owner 在 ExportPage 选择导出格式（JSON / CSV / XLSX）与数据范围，触发导出请求
2. **创建 ExportJob**：系统创建 ExportJob 记录，状态为 `pending`
3. **查询标注数据**：查询指定任务下所有已通过审核的 Submission 记录
4. **关联 AI 审核**：将 Submission 与 AIReviewRun 进行 LEFT JOIN，附加 AI 评分与风险等级
5. **格式转换**：
   - **JSON**：结构化输出，包含完整字段与嵌套关系
   - **CSV**：扁平化输出，适合 Excel 打开与数据分析
   - **XLSX**：Excel 格式，支持多 Sheet（标注数据 + AI 审核数据）
6. **写入文件**：将格式化后的数据写入 `exports/` 目录，文件名含任务 ID 与时间戳
7. **更新 ExportJob**：状态更新为 `completed`，记录 `file_path`
8. **审计记录**：在 AuditLog 中记录导出操作，包含导出范围、格式、记录数等详情

**导出数据结构（JSON 示例）：**

```json
{
  "task_id": "xxx",
  "export_time": "2026-05-30T10:00:00Z",
  "total_records": 100,
  "items": [
    {
      "item_id": "xxx",
      "raw_data": { ... },
      "annotation": { ... },
      "ai_review": {
        "overall_score": 85,
        "risk_level": "low",
        "dimension_scores": { ... }
      },
      "human_review": {
        "decision": "approved",
        "reviewer": "xxx"
      }
    }
  ]
}
```
