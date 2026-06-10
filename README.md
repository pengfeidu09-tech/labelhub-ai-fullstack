# LabelHub — LLM 数据生产 AI 质量治理平台

## 项目简介

LabelHub 是一个面向 LLM 数据生产的 AI 质量治理平台，覆盖从任务配置、模板设计、标注工作台、AI 预检 Agent、人工审核、返工流程、结果中心、多格式导出、审计日志、工时统计、质量洞察到 Rubric 分析、优先审核样本、AI 质量报告的完整链路。

**核心定位**：LabelHub 不是一个简单的 CRUD 标注系统，而是一条从数据生产 → AI 预检 → 人工审核 → 返工闭环 → 质量分析 → 训练数据导出的**完整数据质量治理链**。

---

## 核心亮点

1. **Schema-driven 动态标注模板** — 通过 JSON Schema 驱动模板定义，支持拖拽式模板设计器（ComponentPalette + TemplateCanvas + PropertyPanel），运行时自动渲染标注表单，无需硬编码字段。

2. **三层嵌套数据结构** — `Project/Task → DatasetItem → Annotation/Submission/AIReviewRun/HumanReview/WorkSession/ExportRecord/AuditLog`，清晰的数据血缘关系，支撑全链路可追溯。

3. **AI Precheck Agent** — 标注提交前自动触发 AI 预检，输出结构化评分（overall_score）、风险等级（risk_level: low/medium/high）、维度评分（dimension_scores）、建议动作（suggested_action）及原因（reason），辅助标注员自检。

4. **AI/Human 差异对比** — 审核页面支持 AI 预检结果与人工标注结果的逐维度对比，帮助审核员快速定位争议点，提升审核效率。

5. **返工闭环与状态机** — 完整的状态机驱动（draft → submitted → in_review → approved / rejected → rework → resubmitted），拒绝后自动进入返工流程，标注员可查看拒绝原因并重新提交，形成质量闭环。

6. **结果中心与多格式导出** — 结果中心提供质量仪表盘（通过率、分布统计、趋势图），支持 JSON / CSV / XLSX 多格式导出已审核通过的数据，满足不同训练框架的输入需求。

7. **全链路审计追踪** — 从 dashboard 访问到数据导出，关键操作均记录 AuditLog，包含操作人、时间、动作类型、目标对象，确保全流程可追溯、可审计。

8. **工时统计与操作记录** — 通过 WorkSession 记录标注员每次操作的起止时间，自动汇总工时报告，支撑项目管理和绩效评估。

9. **AI 质量洞察与 Rubric 命中分析** — 质量洞察页面展示 AI 评分分布、风险分布、维度雷达图；Rubric 分析页面展示各评分标准的命中率和分布，辅助 Owner 优化评分标准。

10. **Demo 演示与 Demo 模式** — 内置 Demo 数据和演示脚本，支持一键体验完整流程；Demo 模式下 AI Agent 使用 mock 服务，确保演示稳定可靠。

---

## 系统角色

| 角色 | 职责 |
|------|------|
| **Owner** | 任务管理（创建/发布/归档）、模板设计、结果中心查看、数据导出、审计日志查看、质量报告生成、Rubric 管理 |
| **Labeler** | 认领数据、填写标注、触发 AI 预检、保存草稿、提交标注、查看拒绝原因、返工重新提交、查看个人工时报告 |
| **Reviewer** | 审核队列浏览、审核详情查看、AI/Human 对比、通过/拒绝操作、审核时间线查看 |

---

## 核心流程

```
Owner 发布任务
  → Labeler 认领数据
  → Labeler 填写标注
  → AI Precheck Agent 输出质量建议
  → Labeler 提交标注
  → Reviewer 审核标注
  → Reviewer 通过 / 拒绝
  → (拒绝) Labeler 返工并重新提交
  → Owner 查看结果中心
  → Owner 导出已审核数据
  → AuditLog 追踪全链路
```

---

## 技术架构

### Frontend

- **框架**：React 18 / Vite / TypeScript
- **UI 组件库**：Ant Design
- **状态管理**：Zustand
- **核心页面**：
  - 角色化页面路由（Owner / Labeler / Reviewer）
  - 标注工作台三栏布局（数据展示 / 标注表单 / AI 预检结果）
  - 结果中心质量仪表盘
  - 模板设计器（拖拽式）
  - Demo 模式支持

### Backend

- **框架**：Python FastAPI
- **ORM**：SQLAlchemy
- **数据校验**：Pydantic
- **数据库**：SQLite（开发环境）
- **核心模块**：
  - Task 管理
  - DatasetItem / 数据导入
  - Annotation / Draft / Submission
  - AI Precheck Pipeline
  - Human Review
  - Export 多格式导出
  - AuditLog 审计日志
  - WorkSession / WorkReport 工时统计
  - Quality Insight / Rubric Analysis
- **AI Precheck**：当前使用 **mock 模式**，模拟结构化评分输出，确保 Demo 稳定运行

### Database

SQLite（开发环境），核心数据表：

| 表名 | 说明 |
|------|------|
| Task | 标注任务 |
| DatasetItem | 数据条目 |
| Submission | 标注提交 |
| AIReviewRun | AI 预检运行记录 |
| HumanReview | 人工审核记录 |
| WorkSession | 工时记录 |
| ExportRecord | 导出记录 |
| AuditLog | 审计日志 |

### AI Agent

AI 审核 Agent 支持完整的队列化审核流程：

- **队列状态**：pending → running → success / failed / fallback_required
- **失败重试**：自动重试失败任务，超过最大重试次数后标记为 fallback_required
- **人工兜底**：fallback_required 状态的任务自动进入人工审核流程
- **审计追踪**：所有 Agent 动作（入队、运行成功、失败、兜底）均记录审计日志
- **当前模式**：使用 **mock 模式**，返回预设的结构化评分结果，确保 Demo 环境稳定运行
- **接口结构**：支持替换真实大模型，只需实现 AIProvider 接口即可切换

AI Precheck Agent 输出结构：

```json
{
  "overall_score": 85,
  "risk_level": "low",
  "dimension_scores": {
    "accuracy": 90,
    "completeness": 80,
    "clarity": 85
  },
  "suggested_action": "approve",
  "reason": "标注质量良好，各维度评分均达标"
}
```

> ⚠️ **重要说明**：当前 AI Agent 默认使用 **mock 模式**，返回预设的结构化评分结果，用于演示完整流程和 UI 交互。mock 模式不依赖真实 LLM API，确保 Demo 环境稳定运行。可通过配置切换为阿里云 DashScope 等真实模型。

---

## 真实模型接入

### 配置阿里云 DashScope / Qwen

1. 复制配置文件：
   ```bash
   cp backend/.env.example backend/.env
   ```

2. 在 `backend/.env` 中设置：
   ```
   AI_PROVIDER=dashscope
   DASHSCOPE_API_KEY=sk-your-api-key-here
   DASHSCOPE_MODEL=qwen-turbo
   ```

3. 可选模型：`qwen-turbo`（快速）、`qwen3.7-plus`（均衡）、`qwen-max`（高质量）

4. 重启后端即可生效，Agent 页面会自动显示当前 provider 模式

### Fallback 机制

- 真实模型调用失败（超时、返回非 JSON、API 错误）时，自动使用 mock 兜底
- 兜底结果标记 `fallback: true`，审计日志记录 `agent_fallback_required`
- 超过最大重试次数（3次）的任务标记为 `fallback_required`，需人工审核

### 注意事项

- **不要提交 `.env` 文件**，API Key 仅保留在本地
- 切换回 mock 模式只需设置 `AI_PROVIDER=mock`
- 支持任何 OpenAI 兼容 API，修改 `LLM_API_BASE_URL` 即可

---

## 启动方式

### Backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### 默认地址

| 服务 | 地址 |
|------|------|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

---

## Demo 数据

Demo 场景为 **QA 质量评估任务**，数据字段如下：

| 字段 | 说明 |
|------|------|
| `prompt` / `question` | 问题文本 |
| `model_answer` | 模型回答 |
| `reference` | 参考答案 |
| `category` | 问题分类 |
| `difficulty` | 难度等级 |
| `expected_dimensions` | 期望评估维度 |
| `tags` | 标签 |

---

## 导出格式

| 格式 | 状态 | 说明 |
|------|------|------|
| JSON | ✅ 已支持 | 完整结构化数据导出 |
| CSV | ✅ 已支持 | 表格化数据导出 |
| XLSX | ✅ 已支持 | Excel 格式导出 |
| JSONL | 📋 计划中 | 逐行 JSON 格式，适配训练框架输入，尚未实现 |

---

## 审计与可追溯性

系统记录以下关键审计动作：

| 审计动作 | 说明 |
|----------|------|
| `dashboard_view` | 访问仪表盘 |
| `open_item` | 打开数据条目 |
| `claim_item` | 认领数据 |
| `draft_save` | 保存草稿 |
| `ai_precheck_run` | 触发 AI 预检 |
| `submission_submit` | 提交标注 |
| `review_open` | 打开审核 |
| `review_approve` | 审核通过 |
| `review_reject` | 审核拒绝 |
| `rework_submit` | 返工提交 |
| `export_create` | 创建导出 |
| `export_complete` | 导出完成 |
| `agent_enqueue` | AI Agent 入队 |
| `agent_run_success` | AI Agent 运行成功 |
| `agent_run_failed` | AI Agent 运行失败 |
| `agent_fallback_required` | AI Agent 需人工兜底 |
| `quality_report_generate` | 生成质量报告 |
| `system_health_check` | 系统健康检查 |

---

## 项目价值

- **真实 LLM 数据生产链**：覆盖标注 → 审核 → 返工 → 导出 → 审计的完整闭环，而非简单的数据录入系统。
- **AI 参与质量治理**：AI 参与预检、风险识别、质量分析、报告生成，形成人机协同的质量保障机制。
- **闭环可追溯**：标注-审核-返工-导出-审计形成完整闭环，每一步操作均有审计记录。
- **企业级原型**：可作为企业级标注平台的原型，支持角色权限、模板驱动、多格式导出、质量分析等核心能力。

---

## 项目文档

| 文档 | 说明 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 系统架构设计 |
| [docs/api.md](docs/api.md) | API 接口文档 |
| [docs/deployment.md](docs/deployment.md) | 部署指南 |
| [docs/demo_walkthrough.md](docs/06_demo_walkthrough.md) | Demo 演示流程 |
| [docs/data_model.md](docs/01_architecture.md) | 数据模型设计 |
| [docs/quality_agent.md](docs/00_requirement_breakdown.md) | AI 质量治理设计 |
| [SUBMISSION.md](SUBMISSION.md) | 提交说明 |
| [CHANGELOG.md](CHANGELOG.md) | 变更日志 |

---

## 提交说明

- 不提交 `node_modules/`、`dist/`、`__pycache__/`
- 不提交本地 `.env` 文件
- Demo 数据保留（`labelhub.db`、`annotations.json`）
- 详细清理清单见 [docs/submission_cleanup.md](docs/submission_cleanup.md)
- Smoke Test 清单见 [docs/smoke_test.md](docs/smoke_test.md)
