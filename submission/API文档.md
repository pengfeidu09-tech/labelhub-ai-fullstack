# API 文档

Base URL: `http://127.0.0.1:8000/api`

## Health

| Method | Path | 说明 |
|--------|------|------|
| GET | /health | 健康检查 |

## Dashboard

| Method | Path | 说明 |
|--------|------|------|
| GET | /dashboard/stats | 仪表盘统计数据 |
| GET | /dashboard/quality | 质量指标 |
| GET | /dashboard/activities | 最近业务动态 |
| GET | /dashboard/health-check | 系统健康检查 |

## Tasks

| Method | Path | 说明 |
|--------|------|------|
| GET | /tasks | 任务列表 |
| POST | /tasks | 创建任务 |
| GET | /tasks/{task_id} | 任务详情 |
| PUT | /tasks/{task_id} | 更新任务 |
| POST | /tasks/{task_id}/publish | 发布任务 |
| POST | /tasks/{task_id}/pause | 暂停任务 |
| POST | /tasks/{task_id}/end | 结束任务 |
| GET | /tasks/{task_id}/template | 获取任务模板 |
| PUT | /tasks/{task_id}/template | 绑定任务模板 |
| GET | /tasks/{task_id}/items | 任务数据项列表 |
| GET | /tasks/{task_id}/results/summary | 任务结果汇总 |

## Templates

| Method | Path | 说明 |
|--------|------|------|
| GET | /templates | 模板列表 |
| POST | /templates | 创建模板 |
| GET | /templates/{template_id} | 模板详情 |
| PUT | /templates/{template_id} | 更新模板 |
| POST | /templates/{template_id}/clone | 克隆模板版本 |

## Datasets

| Method | Path | 说明 |
|--------|------|------|
| GET | /datasets | 数据集列表 |
| GET | /datasets/{dataset_id}/items | 数据项列表 |

## Labeler

| Method | Path | 说明 |
|--------|------|------|
| GET | /labeler/items | 标注员工作项列表 |
| GET | /labeler/workbench/current | 当前工作台状态 |
| GET | /labeler/form/{item_id} | 获取表单元数据 |
| POST | /labeler/save-draft | 保存草稿 |
| POST | /labeler/submit | 提交标注 |
| POST | /labeler/claim-next | 领取下一条 |
| POST | /labeler/session/open | 开启会话 |
| POST | /labeler/session/heartbeat | 心跳上报 |
| POST | /labeler/session/close | 关闭会话 |
| GET | /labeler/submissions | 我的提交列表 |
| GET | /labeler/reports | 工时报表 |

## AI Agent

| Method | Path | 说明 |
|--------|------|------|
| GET | /agent/provider-config | 获取 Provider 配置 |
| PUT | /agent/provider-config | 更新 Provider 配置 |
| GET | /agent/provider-test | 测试 Provider 连通性 |
| GET | /agent/runs | Agent 运行记录列表 |
| GET | /agent/runs/{run_id} | 运行记录详情 |
| GET | /agent/runs/stats | 运行统计 |
| POST | /agent/runs/{run_id}/retry | 重试失败运行 |
| POST | /agent/run-pending | 执行待处理队列 |
| POST | /agent/rerun/{submission_id} | 重新运行 AI 预审 |
| GET | /agent/config/{task_id} | 获取任务 Agent 配置 |
| PUT | /agent/config/{task_id} | 更新任务 Agent 配置 |

## AI Precheck

| Method | Path | 说明 |
|--------|------|------|
| POST | /ai/precheck | AI 预审（按 dataset_type 路由） |
| GET | /ai/latest-assist | 获取最新辅助结果 |

## Review

| Method | Path | 说明 |
|--------|------|------|
| GET | /reviews/queue | 审核队列 |
| GET | /reviews/{submission_id} | 审核详情 |
| POST | /reviews/{submission_id}/approve | 审核通过 |
| POST | /reviews/{submission_id}/reject | 审核打回 |
| GET | /reviews/{annotation_id}/timeline | 审计时间线 |

## Results / Export

| Method | Path | 说明 |
|--------|------|------|
| GET | /tasks/{task_id}/results | 结果中心 |
| POST | /exports | 创建导出任务 |
| GET | /exports | 导出记录列表 |
| GET | /exports/{export_id}/download | 下载导出文件 |

## Audit

| Method | Path | 说明 |
|--------|------|------|
| GET | /audit-logs | 审计日志列表 |
| POST | /audit-logs | 写入审计日志 |
| GET | /audit-logs/{log_id} | 审计日志详情 |

## Rubrics

| Method | Path | 说明 |
|--------|------|------|
| GET | /rubrics | Rubric 标准库列表 |
| GET | /rubrics/health | Rubric 健康检查 |
