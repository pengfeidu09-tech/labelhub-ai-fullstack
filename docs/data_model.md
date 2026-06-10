# LabelHub 数据模型文档

## 概述

LabelHub 的数据模型围绕**标注任务管理**这一核心场景设计，采用三层嵌套结构（Task → DatasetItem → Annotation/Submission），并辅以模板定义、AI 预审、人工审核、工时追踪、数据导出和审计日志等支撑实体。

---

## 实体定义

### 1. Task — 任务容器

**用途**：Task 是最顶层的组织单元，代表一个完整的标注项目。它定义了标注的目标、使用的模板、是否启用 AI 预审等全局配置，并管理整个任务的生命周期。

**关键字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String/UUID | 主键 |
| `name` | String | 任务名称 |
| `template_id` | String/UUID | 关联的标注模板 ID |
| `ai_review_enabled` | Boolean | 是否启用 AI 预审 |
| `status` | Enum | 任务状态：`draft` / `published` / `paused` / `ended` |
| `created_at` | Timestamp | 创建时间 |

**关系**：

- **has many** `DatasetItem` — 一个任务包含多条数据项
- **has one** `TemplateSchema` — 一个任务使用一套标注模板（通过 `template_id` 关联）

---

### 2. DatasetItem — 数据项

**用途**：DatasetItem 是待标注的最小数据单元，承载原始数据和标注后的结果数据。它是 Task 和 Annotation 之间的桥梁，同时记录数据项自身的状态流转和分类信息。

**关键字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String/UUID | 主键 |
| `task_id` | String/UUID | 所属任务 ID |
| `raw_data` | JSON | 原始数据（如文本、图片 URL、音频等） |
| `item_data` | JSON | 标注后的结构化数据 |
| `status` | Enum | 数据项状态：`unclaimed` / `claimed` / `drafting` / `submitted` / `ai_reviewing` / `approved` / `rejected` / `export_ready` / `invalid` |
| `category` | String | 数据分类标签 |
| `difficulty` | String/Enum | 难度等级 |

**关系**：

- **belongs to** `Task` — 数据项属于某个任务
- **has many** `Annotation` — 一条数据项可有多条标注记录
- **has many** `Submission` — 一条数据项可有多条提交记录

**状态流转说明**：

```
unclaimed → claimed → drafting → submitted → ai_reviewing → approved → export_ready
                                              ↓                ↓
                                           approved         rejected → drafting
                                                              ↓
                                                           invalid
```

---

### 3. TemplateSchema — 标注模板

**用途**：TemplateSchema 定义标注的结构化规范，使用 JSON Schema 描述标注字段的类型、约束和默认值，确保同一任务下所有标注结果遵循统一格式。

**关键字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String/UUID | 主键 |
| `name` | String | 模板名称 |
| `schema` | JSON Schema | 标注字段的 JSON Schema 定义 |
| `schema_json` | JSON | 模板的完整 JSON 表示（含 UI 渲染配置等） |

**关系**：

- **has many** `Task` — 一套模板可被多个任务复用

---

### 4. Annotation — 标注记录

**用途**：Annotation 是标注工作的核心产出物，存储在 `annotations.json` 文件中。它记录标注员对某条数据项的标注结果、AI 预审反馈、人工审核意见以及标注耗时等信息。

**关键字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String/UUID | 主键 |
| `task_id` | String/UUID | 所属任务 ID |
| `dataset_item_id` | String/UUID | 关联的数据项 ID |
| `labeler_id` | String/UUID | 标注员 ID |
| `result` | JSON | 标注结果（遵循 TemplateSchema 定义的结构） |
| `status` | Enum | 标注状态 |
| `ai_review` | JSON | AI 预审结果摘要（内嵌） |
| `review_info` | JSON | 人工审核信息摘要（内嵌） |
| `duration_seconds` | Number | 标注耗时（秒） |

**关系**：

- **belongs to** `DatasetItem` — 标注记录关联某条数据项
- **has one** `AIReviewRun` — 一条标注记录对应一次 AI 预审运行
- **has one** `HumanReview` — 一条标注记录对应一次人工审核

---

### 5. Submission — 提交记录

**用途**：Submission 追踪标注结果的提交与流转状态，是工作流管理的核心实体。它与 Annotation 分离，专注于记录"提交"这一动作的状态变化，而非标注内容本身。

**关键字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String/UUID | 主键 |
| `annotation_id` | String/UUID | 关联的标注记录 ID |
| `dataset_item_id` | String/UUID | 关联的数据项 ID |
| `labeler_id` | String/UUID | 提交者（标注员）ID |
| `status` | Enum | 提交状态：`draft` / `submitted` / `ai_reviewing` / `approved` / `rejected_to_modify` |

**关系**：

- **belongs to** `Annotation` — 提交记录关联某条标注记录

**状态流转说明**：

```
draft → submitted → ai_reviewing → approved
                         ↓
                  rejected_to_modify → draft
```

---

### 6. AIReviewRun — AI 预审运行

**用途**：AIReviewRun 记录一次 AI 预审的完整输出，包括各维度的评分、风险等级、建议动作和置信度等。它与 Annotation 分离存储，确保 AI 评估结果可独立查询和分析。

**关键字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String/UUID | 主键 |
| `annotation_id` | String/UUID | 关联的标注记录 ID |
| `overall_score` | Number | 综合评分 |
| `risk_level` | Enum/String | 风险等级（如 low / medium / high） |
| `suggested_action` | Enum/String | 建议动作（如 approve / reject / review） |
| `confidence` | Number | AI 预审置信度（0~1） |
| `passed` | Boolean | 是否通过预审 |
| `summary` | String | AI 预审摘要说明 |
| `dimension_scores` | JSON | 各维度评分详情（如 `{"accuracy": 0.9, "completeness": 0.8}`） |

**关系**：

- **belongs to** `Annotation` — AI 预审运行关联某条标注记录

---

### 7. HumanReview — 人工审核

**用途**：HumanReview 记录审核员对标注结果的人工审核意见，包括通过、驳回或修订等动作及审核评论。

**关键字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String/UUID | 主键 |
| `annotation_id` | String/UUID | 关联的标注记录 ID |
| `reviewer_id` | String/UUID | 审核员 ID |
| `action` | Enum | 审核动作：`approve` / `reject` / `revise` |
| `comment` | String | 审核评论 |

**关系**：

- **belongs to** `Annotation` — 人工审核关联某条标注记录

---

### 8. AnnotationWorkSession — 工时会话

**用途**：AnnotationWorkSession 追踪标注员在单条数据项上的工作时长，支持会话的启动、暂停和累计，用于工时统计和效率分析。

**关键字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String/UUID | 主键 |
| `labeler_id` | String/UUID | 标注员 ID |
| `item_id` | String/UUID | 数据项 ID |
| `status` | Enum | 会话状态：`active` / `stopped` |
| `started_at` | Timestamp | 会话开始时间 |
| `accumulated_seconds` | Number | 累计工作时长（秒） |

**关系**：

- **belongs to** Labeler（标注员） — 工时会话属于某位标注员
- **belongs to** `DatasetItem` — 工时会话关联某条数据项

---

### 9. ExportJob — 导出任务

**用途**：ExportJob 管理标注数据的异步导出，支持多种导出格式，记录导出的进度、状态和产出文件信息。

**关键字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String/UUID | 主键 |
| `task_id` | String/UUID | 关联的任务 ID |
| `format` | String | 导出格式（如 JSON、CSV、COCO 等） |
| `status` | Enum | 导出状态：`pending` / `running` / `success` / `failed` |
| `file_path` | String | 导出文件路径 |
| `row_count` | Number | 导出数据行数 |

**关系**：

- **belongs to** `Task` — 导出任务属于某个任务

---

### 10. AuditLog — 审计日志

**用途**：AuditLog 记录系统中所有关键操作的审计轨迹，采用通用引用设计（`target_type` + `target_id`），可关联任意实体，满足合规和追溯需求。

**关键字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String/UUID | 主键 |
| `user_id` | String/UUID | 操作用户 ID |
| `action` | String | 操作类型（如 create、update、delete、approve 等） |
| `target_type` | String | 目标实体类型（如 Task、Annotation、DatasetItem 等） |
| `target_id` | String/UUID | 目标实体 ID |
| `task_id` | String/UUID | 关联任务 ID（便于按任务筛选日志） |
| `message` | String | 操作描述信息 |
| `created_at` | Timestamp | 操作时间 |

**关系**：

- 独立实体，通过 `target_type` + `target_id` 多态引用任意业务实体

---

## 实体关系总览

```
TemplateSchema
      │
      │ 1:N
      ▼
    Task ◄────────────── ExportJob
      │                      (belongs to Task)
      │ 1:N
      ▼
  DatasetItem ◄──── AnnotationWorkSession
      │                      (belongs to DatasetItem)
      │ 1:N
      ▼
  Annotation ──────┬──── AIReviewRun
      │            │           (belongs to Annotation)
      │            │
      │            └──── HumanReview
      │                        (belongs to Annotation)
      │ 1:N
      ▼
  Submission
  (belongs to Annotation)

  AuditLog (独立，通过 target_type + target_id 多态引用)
```

---

## 架构设计决策

### 为什么使用三层嵌套结构（Task → DatasetItem → Annotation/Submission）

三层嵌套结构遵循**数据、工作、结果分离**的原则：

- **Task（任务层）**：组织工作。定义"做什么"——使用什么模板、是否启用 AI 预审、任务的生命周期状态。Task 是管理视角的入口，负责全局配置和进度管控。
- **DatasetItem（数据层）**：承载数据。定义"对什么做"——原始数据和标注后数据的载体。DatasetItem 持有数据本身及其状态流转，与标注行为解耦。
- **Annotation/Submission（结果层）**：承载结果。定义"做出了什么"——标注内容、提交状态、审核反馈。结果与数据分离，使得同一条数据可以被多次标注、多轮审核，而不会污染原始数据。

这种分离带来的好处：
1. **关注点分离**：每一层只关心自己的职责，修改标注逻辑不影响数据管理，调整任务配置不影响标注结果。
2. **灵活复用**：同一套数据（DatasetItem）可以分配给不同任务或不同标注员，标注结果独立存储。
3. **状态隔离**：Task 的 `published/paused/ended` 状态、DatasetItem 的 `claimed/submitted` 状态、Submission 的 `draft/approved` 状态各自独立流转，互不干扰。

---

### 为什么 Submission 和 AIReviewRun 独立

Submission 和 AIReviewRun 虽然都围绕 Annotation 展开，但它们服务于不同的目的，拥有不同的生命周期：

- **Submission 追踪工作流状态**：它关注的是"标注结果在流程中的位置"——是草稿、已提交、AI 审核中、已通过还是被驳回修改。Submission 的状态变化驱动业务流程的推进，是工作流引擎的核心数据。当标注被驳回需要修改时，Submission 回到 `draft` 状态，触发重新标注的流程。

- **AIReviewRun 捕获 AI 评估输出**：它关注的是"AI 对标注质量的判断"——评分、风险等级、建议动作、各维度得分。AIReviewRun 是一次性的计算结果，不会随工作流状态变化而改变。它服务于质量分析和模型迭代，而非流程驱动。

独立存储的好处：
1. **生命周期不同**：Submission 随工作流反复变更状态，AIReviewRun 一旦生成就基本不变。混合存储会导致频繁更新影响只读数据的查询性能。
2. **查询模式不同**：Submission 主要被工作流引擎按状态查询，AIReviewRun 主要被质量分析模块按评分和风险等级聚合。分离后可独立优化索引。
3. **扩展性**：未来可能一条 Annotation 经历多次 AI 预审（如修改后重新预审），独立表天然支持一对多关系。

---

### 为什么 AuditLog 独立

AuditLog 是典型的**横切关注点（Cross-cutting Concern）**，它需要记录系统中所有关键实体的操作轨迹，而非仅限于某个特定业务实体：

- **多态引用设计**：通过 `target_type` + `target_id` 的组合，AuditLog 可以关联 Task、DatasetItem、Annotation、Submission 等任意实体，无需为每种实体建立独立的日志表。
- **性能隔离**：审计日志的写入频率极高，且查询模式（按时间范围、操作类型、用户等）与业务查询完全不同。独立表确保日志写入不会影响业务表的查询性能，也便于对日志表进行分区、归档等运维操作。
- **合规需求**：审计日志通常有独立的保留策略和访问权限要求，独立存储便于统一管理。

---

### 为什么 AnnotationWorkSession 独立聚合工时

工时追踪与标注内容是两个完全不同的关注维度：

- **会话跨越多次操作**：一个 WorkSession 从标注员打开数据项开始，到主动停止或切换为止，期间可能经历多次保存、暂存等操作。工时是连续的时间段概念，而非离散的操作记录。
- **需要独立计算累计时长**：WorkSession 通过 `started_at` 和 `accumulated_seconds` 追踪实际工作时间，支持暂停/恢复场景。如果将工时嵌入 Annotation，每次暂停都需要更新 Annotation 记录，既不自然也增加并发冲突风险。
- **服务于不同分析场景**：工时数据主要用于效率分析（人均标注速度、任务耗时预估、标注员绩效评估），与标注内容的质量评估是独立的维度。独立存储便于按标注员、按任务、按时间段聚合工时统计。
- **一对多关系**：同一条数据项可能被同一标注员多次打开（如驳回后重新标注），每次打开对应一个独立的 WorkSession，天然是一对多关系。
