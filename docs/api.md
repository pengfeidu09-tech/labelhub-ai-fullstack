# LabelHub API 文档

> 启动后端后访问 http://localhost:8000/docs 查看完整 Swagger API 文档

---

## 1. Health 健康检查

| Method | Path | 说明 | 请求参数 | 响应字段 |
|--------|------|------|----------|----------|
| GET | /api/health | 健康检查 | 无 | `status`, `timestamp` |

---

## 2. Dashboard 仪表盘

| Method | Path | 说明 | 请求参数 | 响应字段 |
|--------|------|------|----------|----------|
| GET | /api/dashboard/stats | 项目统计数据 | 无 | `total_tasks`, `completed_tasks`, `in_progress_tasks`, `total_datasets`, `total_annotations` |
| GET | /api/dashboard/quality | 质量概览 | 无 | `overall_quality_score`, `pass_rate`, `reject_rate`, `quality_trend` |
| GET | /api/dashboard/activities | 最近活动 | 无 | `activities[]` (每项含 `id`, `action`, `user`, `target`, `timestamp`) |
| GET | /api/dashboard/health-check | 系统健康状态 | 无 | `status`, `database`, `disk_usage`, `uptime` |

---

## 3. Tasks 任务管理

| Method | Path | 说明 | 请求参数 | 响应字段 |
|--------|------|------|----------|----------|
| GET | /api/tasks | 获取任务列表 | `status`, `page`, `page_size` (query) | `tasks[]`, `total`, `page`, `page_size` |
| POST | /api/tasks | 创建任务 | `name`, `description`, `template_id`, `dataset_id`, `assignees[]` (body) | `id`, `name`, `status`, `created_at` |
| GET | /api/tasks/{id} | 获取任务详情 | `id` (path) | `id`, `name`, `description`, `status`, `template`, `dataset`, `assignees[]`, `created_at`, `updated_at` |
| PUT | /api/tasks/{id} | 更新任务 | `id` (path), `name`, `description`, `status`, `assignees[]` (body) | `id`, `name`, `status`, `updated_at` |
| GET | /api/tasks/{id}/result-summary | 获取任务结果统计 | `id` (path) | `total_annotations`, `approved_count`, `rejected_count`, `pending_count`, `quality_score` |

---

## 4. Templates 标注模板

| Method | Path | 说明 | 请求参数 | 响应字段 |
|--------|------|------|----------|----------|
| GET | /api/templates | 获取模板列表 | `page`, `page_size` (query) | `templates[]`, `total`, `page`, `page_size` |
| POST | /api/templates | 创建模板 | `name`, `description`, `labels[]`, `settings` (body) | `id`, `name`, `created_at` |
| GET | /api/templates/{id} | 获取模板详情 | `id` (path) | `id`, `name`, `description`, `labels[]`, `settings`, `created_at` |
| PUT | /api/templates/{id} | 更新模板 | `id` (path), `name`, `description`, `labels[]`, `settings` (body) | `id`, `name`, `updated_at` |

---

## 5. Datasets 数据集

| Method | Path | 说明 | 请求参数 | 响应字段 |
|--------|------|------|----------|----------|
| GET | /api/datasets | 获取数据集列表 | `page`, `page_size` (query) | `datasets[]`, `total`, `page`, `page_size` |
| POST | /api/datasets | 导入数据集 | `name`, `description`, `file` (multipart/form-data) | `id`, `name`, `file_count`, `created_at` |
| GET | /api/datasets/{id} | 获取数据集详情 | `id` (path) | `id`, `name`, `description`, `file_count`, `files[]`, `created_at` |

---

## 6. Labeler / Workbench 标注员工作台

| Method | Path | 说明 | 请求参数 | 响应字段 |
|--------|------|------|----------|----------|
| GET | /api/labeler/available-tasks | 获取可领取任务列表 | 无 | `tasks[]` (每项含 `id`, `name`, `priority`, `remaining_count`) |
| POST | /api/labeler/claim | 领取任务 | `task_id` (body) | `claim_id`, `task_id`, `status`, `claimed_at` |
| GET | /api/labeler/workbench | 获取工作台数据 | `task_id` (query) | `task`, `current_item`, `annotations[]`, `progress` |
| POST | /api/labeler/submit | 提交标注结果 | `task_id`, `item_id`, `annotations[]` (body) | `submission_id`, `status`, `submitted_at` |

---

## 7. AI Precheck AI 预检

| Method | Path | 说明 | 请求参数 | 响应字段 |
|--------|------|------|----------|----------|
| POST | /api/ai-precheck/run | 执行 AI 预检 | `task_id`, `check_type` (body) | `job_id`, `status`, `started_at` |
| GET | /api/ai-precheck/status | 查询预检状态 | `job_id` (query) | `job_id`, `status`, `progress`, `result`, `completed_at` |

---

## 8. Reviews 审核管理

| Method | Path | 说明 | 请求参数 | 响应字段 |
|--------|------|------|----------|----------|
| GET | /api/reviews/queue | 获取审核队列 | `status`, `page`, `page_size` (query) | `reviews[]`, `total`, `page`, `page_size` |
| GET | /api/reviews/{id} | 获取审核详情 | `id` (path) | `id`, `task_id`, `annotation_id`, `status`, `reviewer`, `comments`, `created_at` |
| POST | /api/reviews/{id}/approve | 审核通过 | `id` (path), `comment` (body, 可选) | `id`, `status`, `approved_at` |
| POST | /api/reviews/{id}/reject | 审核驳回 | `id` (path), `reason`, `comment` (body) | `id`, `status`, `rejected_at` |

---

## 9. Quality 质量管理

| Method | Path | 说明 | 请求参数 | 响应字段 |
|--------|------|------|----------|----------|
| GET | /api/quality/tasks/{id}/insights | 获取任务质量洞察 | `id` (path) | `quality_score`, `common_errors[]`, `suggestions[]`, `trend` |
| GET | /api/quality/tasks/{id}/rubric-analysis | 获取评分标准分析 | `id` (path) | `rubric_scores[]`, `overall_score`, `weak_areas[]` |
| GET | /api/quality/tasks/{id}/priority-reviews | 获取优先审核项 | `id` (path) | `priority_items[]` (每项含 `annotation_id`, `reason`, `score`) |
| POST | /api/quality/tasks/{id}/report | 生成质量报告 | `id` (path), `report_type` (body) | `report_id`, `status`, `generated_at` |

---

## 10. Export 数据导出

| Method | Path | 说明 | 请求参数 | 响应字段 |
|--------|------|------|----------|----------|
| POST | /api/exports/task/{id} | 创建导出任务 | `id` (path), `format`, `filters` (body) | `export_id`, `status`, `created_at` |
| GET | /api/exports | 获取导出列表 | `page`, `page_size` (query) | `exports[]`, `total`, `page`, `page_size` |
| GET | /api/exports/{id}/download | 下载导出文件 | `id` (path) | 文件流 (binary) |
| GET | /api/export/annotations | 导出标注数据 | `task_id`, `format` (query) | 标注数据 (JSON/CSV) |

---

## 11. Audit Logs 审计日志

| Method | Path | 说明 | 请求参数 | 响应字段 |
|--------|------|------|----------|----------|
| GET | /api/audit-logs | 获取审计日志列表 | `action`, `user_id`, `target_type`, `task_id`, `start_time`, `end_time`, `page`, `page_size` (query) | `logs[]` (每项含 `id`, `action`, `user_id`, `target_type`, `target_id`, `detail`, `timestamp`), `total`, `page`, `page_size` |

---

## 12. Worktime 工时管理

| Method | Path | 说明 | 请求参数 | 响应字段 |
|--------|------|------|----------|----------|
| GET | /api/work-report | 获取工时报告 | `user_id`, `start_date`, `end_date` (query) | `reports[]`, `total_hours`, `summary` |
| GET | /api/workbench-session | 获取工作台会话列表 | `user_id`, `status` (query) | `sessions[]` (每项含 `id`, `user_id`, `task_id`, `start_time`, `end_time`, `duration`) |

---

## 13. Rubrics 评分标准

| Method | Path | 说明 | 请求参数 | 响应字段 |
|--------|------|------|----------|----------|
| GET | /api/rubrics | 获取评分标准列表 | `page`, `page_size` (query) | `rubrics[]` (每项含 `id`, `name`, `criteria[]`, `created_at`), `total`, `page`, `page_size` |
