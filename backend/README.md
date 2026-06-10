# LabelHub AI - 智能标注平台

LabelHub AI 是一个面向 AI 数据标注竞赛的全流程平台，支持动态表单设计、标注工作台、AI 预审质检、人工审核流、结果中心与多格式导出。

## 项目亮点

- **动态表单 Designer / Renderer** — Owner 可视化设计标注模板，Labeler 动态渲染表单
- **Labeler 标注工作台** — 队列管理、计时、草稿保存、操作日志
- **AI 预审 / 质检 Agent** — 规则版 AI 预审，检测必填项缺失、理由过短、评分风险等
- **Reviewer 人工审核流** — 审核队列、AI/人工差异对比、通过/打回/修订
- **结果中心与多格式导出** — 任务维度统计、质量报告、JSON/JSONL/CSV/XLSX 导出
- **质量报告** — AI 预审统计、人工审核统计、常见问题 Top 5、可复制摘要

## 技术栈

- **后端**: FastAPI + SQLAlchemy + SQLite
- **前端**: React + TypeScript + Ant Design + Vite
- **AI 预审**: 规则引擎（无外部 LLM 依赖，Mock 模式可完整演示）

## 本地启动

### 后端

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/api/health

### 前端

```bash
cd frontend
npm install
npm run dev
```

- 前端页面: http://localhost:5173

## 演示流程

1. **Owner 创建任务** → 搭建模板 → 发布任务
2. **Labeler 领取** → 标注 → AI 预审 → 提交
3. **Reviewer 审核** → 通过 / 打回
4. **Labeler 返修** → 重新提交
5. **Reviewer 通过** → Owner 导出结果 → 查看质量报告

### 详细步骤

1. 访问前端首页，选择角色进入
2. Owner → 模板管理 → 创建问答质量评估模板
3. Owner → 任务管理 → 创建任务 → 发布
4. Owner → 数据集 → 导入演示数据
5. Labeler → 任务市场 → 领取任务
6. Labeler → 标注工作台 → 填写表单 → AI 预审 → 提交
7. Reviewer → 审核队列 → 审核详情 → 通过/打回
8. Labeler → 我的提交 → 继续修改（返修）
9. Owner → 任务详情 → 结果中心 → 查看统计/质量报告
10. Owner → 结果中心 → 导出已通过数据（JSON/CSV/XLSX）

## 目录结构

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── core/                # 核心配置（database/config/enums/password）
│   ├── models/              # SQLAlchemy ORM 模型
│   ├── schemas/             # Pydantic 请求/响应模式
│   ├── services/            # 业务服务层
│   │   ├── annotation_service.py   # 标注数据管理（annotations.json）
│   │   ├── ai_precheck_service.py  # AI 规则版预审
│   │   ├── export_service.py       # 导出服务
│   │   └── ...
│   └── api/                 # API 路由
│       ├── tasks.py         # 任务管理 + 结果统计
│       ├── labeler.py       # 标注员接口
│       ├── reviews.py       # 审核接口
│       ├── ai_precheck.py   # AI 预审接口
│       ├── export.py        # 导出接口
│       └── ...
├── data/                    # JSON 数据存储
├── exports/                 # 导出文件目录
└── requirements.txt

frontend/
├── src/
│   ├── pages/
│   │   ├── owner/           # Owner 页面
│   │   │   ├── OwnerDashboard.tsx
│   │   │   ├── TaskListPage.tsx
│   │   │   ├── TaskDetailPage.tsx
│   │   │   ├── TaskResultsPage.tsx    # 结果中心 + 质量报告
│   │   │   ├── ExportPage.tsx
│   │   │   └── ...
│   │   ├── labeler/         # Labeler 页面
│   │   │   ├── LabelWorkbenchPage.tsx  # 标注工作台
│   │   │   ├── MySubmissionsPage.tsx
│   │   │   └── ...
│   │   └── reviewer/        # Reviewer 页面
│   │       ├── ReviewQueuePage.tsx
│   │       ├── ReviewDetailPage.tsx
│   │       └── ...
│   ├── components/renderer/ # 动态表单渲染器
│   └── api/                 # API 客户端
└── package.json
```

## 核心 API

| 接口 | 说明 |
|------|------|
| `GET /api/health` | 健康检查 |
| `GET /api/tasks/{id}/result-summary` | 任务结果统计 |
| `POST /api/ai/precheck` | AI 预审 |
| `POST /api/labeler/submit` | 提交标注（含必填项校验） |
| `GET /api/labeler/submissions` | 我的提交 |
| `POST /api/reviews/{id}/approve` | 审核通过 |
| `POST /api/reviews/{id}/reject` | 审核打回 |
| `POST /api/exports/task/{id}` | 导出任务数据 |
| `GET /api/export/annotations` | 导出全部标注（含 AI 预审字段） |

## 状态流转

```
unclaimed → claimed → draft → submitted → human_reviewing → approved → export_ready
                                              ↓
                                     rejected_to_modify → rework_draft → submitted
```
