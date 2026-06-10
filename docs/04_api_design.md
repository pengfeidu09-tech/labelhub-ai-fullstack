# LabelHub API 设计

## API 基础信息

| 属性 | 值 |
|------|------|
| 基础路径 | `/api` |
| 版本 | v1 |
| 认证方式 | JWT Token |
| 数据格式 | JSON |

## 认证头部

```
Authorization: Bearer <token>
```

---

## 1. Tasks API - 任务管理

### 1.1 创建任务

- **路径**: `POST /api/tasks`
- **权限**: Owner
- **请求体**:
```json
{
  "name": "string",
  "description": "string",
  "template_id": "integer",
  "ai_review_enabled": "boolean",
  "ai_config": "object",
  "deadline": "datetime"
}
```
- **响应**:
```json
{
  "id": "integer",
  "name": "string",
  "status": "string",
  "created_at": "datetime"
}
```

### 1.2 获取任务列表

- **路径**: `GET /api/tasks`
- **权限**: Owner/Labeler/Reviewer
- **查询参数**:
  - `status`: 任务状态筛选
  - `page`: 页码
  - `limit`: 每页数量
- **响应**:
```json
{
  "items": [
    {
      "id": "integer",
      "name": "string",
      "description": "string",
      "status": "string",
      "created_at": "datetime"
    }
  ],
  "total": "integer"
}
```

### 1.3 获取任务详情

- **路径**: `GET /api/tasks/{task_id}`
- **权限**: Owner/Labeler/Reviewer
- **响应**:
```json
{
  "id": "integer",
  "name": "string",
  "description": "string",
  "template": "object",
  "status": "string",
  "ai_review_enabled": "boolean",
  "ai_config": "object",
  "deadline": "datetime",
  "created_by": "integer",
  "created_at": "datetime"
}
```

### 1.4 更新任务

- **路径**: `PUT /api/tasks/{task_id}`
- **权限**: Owner
- **请求体**: 同创建任务

### 1.5 删除任务

- **路径**: `DELETE /api/tasks/{task_id}`
- **权限**: Owner

### 1.6 发布任务

- **路径**: `POST /api/tasks/{task_id}/publish`
- **权限**: Owner

### 1.7 暂停任务

- **路径**: `POST /api/tasks/{task_id}/pause`
- **权限**: Owner

### 1.8 结束任务

- **路径**: `POST /api/tasks/{task_id}/end`
- **权限**: Owner

---

## 2. Templates API - 模板管理

### 2.1 创建模板

- **路径**: `POST /api/templates`
- **权限**: Owner
- **请求体**:
```json
{
  "name": "string",
  "description": "string",
  "schema": "object"
}
```
- **响应**:
```json
{
  "id": "integer",
  "name": "string",
  "version": "integer",
  "created_at": "datetime"
}
```

### 2.2 获取模板列表

- **路径**: `GET /api/templates`
- **权限**: Owner/Labeler/Reviewer

### 2.3 获取模板详情

- **路径**: `GET /api/templates/{template_id}`
- **权限**: Owner/Labeler/Reviewer

### 2.4 更新模板

- **路径**: `PUT /api/templates/{template_id}`
- **权限**: Owner

### 2.5 删除模板

- **路径**: `DELETE /api/templates/{template_id}`
- **权限**: Owner

---

## 3. Datasets API - 数据集管理

### 3.1 导入数据集

- **路径**: `POST /api/datasets/import`
- **权限**: Owner
- **请求体**:
```json
{
  "task_id": "integer",
  "format": "csv | json | jsonl",
  "data": "array"
}
```

### 3.2 导入官方演示数据

- **路径**: `POST /api/datasets/import-demo`
- **权限**: Owner
- **请求体**:
```json
{
  "task_id": "integer",
  "dataset_type": "qa_quality | preference_compare"
}
```

### 3.3 获取数据集列表

- **路径**: `GET /api/datasets`
- **权限**: Owner/Labeler/Reviewer
- **查询参数**:
  - `task_id`: 任务ID
  - `status`: 数据状态

### 3.4 获取数据项详情

- **路径**: `GET /api/datasets/{dataset_item_id}`
- **权限**: Owner/Labeler/Reviewer

### 3.5 删除数据项

- **路径**: `DELETE /api/datasets/{dataset_item_id}`
- **权限**: Owner

---

## 4. Labeler API - 标注员操作

### 4.1 领取任务

- **路径**: `POST /api/labeler/tasks/{task_id}/claim`
- **权限**: Labeler

### 4.2 获取已领取任务

- **路径**: `GET /api/labeler/tasks`
- **权限**: Labeler

### 4.3 获取待标注数据

- **路径**: `GET /api/labeler/items`
- **权限**: Labeler
- **查询参数**:
  - `task_id`: 任务ID

### 4.4 获取标注表单

- **路径**: `GET /api/labeler/form/{dataset_item_id}`
- **权限**: Labeler
- **响应**:
```json
{
  "template": "object",
  "item_data": "object",
  "submission": "object"
}
```

### 4.5 保存草稿

- **路径**: `POST /api/labeler/draft`
- **权限**: Labeler
- **请求体**:
```json
{
  "task_id": "integer",
  "dataset_item_id": "integer",
  "data": "object"
}
```

### 4.6 提交标注

- **路径**: `POST /api/labeler/submit`
- **权限**: Labeler
- **请求体**:
```json
{
  "task_id": "integer",
  "dataset_item_id": "integer",
  "data": "object"
}
```

### 4.7 获取提交历史

- **路径**: `GET /api/labeler/submissions`
- **权限**: Labeler

---

## 5. AI Reviews API - AI 审核

### 5.1 触发 AI 审核

- **路径**: `POST /api/ai-reviews/{submission_id}`
- **权限**: System
- **响应**:
```json
{
  "id": "integer",
  "submission_id": "integer",
  "status": "string",
  "overall_score": "number",
  "conclusion": "string",
  "dimension_scores": "object",
  "suggestions": "string",
  "mock_mode": "boolean",
  "prompt_template": "string",
  "raw_response": "string",
  "parsed_result": "object",
  "created_at": "datetime"
}
```

### 5.2 获取 AI 审核结果

- **路径**: `GET /api/ai-reviews/{submission_id}`
- **权限**: Owner/Reviewer

### 5.3 批量触发 AI 审核

- **路径**: `POST /api/ai-reviews/batch`
- **权限**: Owner
- **请求体**:
```json
{
  "submission_ids": "array"
}
```

---

## 6. Reviews API - 人工审核

### 6.1 获取待审核列表

- **路径**: `GET /api/reviews/pending`
- **权限**: Reviewer
- **查询参数**:
  - `task_id`: 任务ID
  - `page`: 页码

### 6.2 获取审核详情

- **路径**: `GET /api/reviews/{submission_id}`
- **权限**: Reviewer
- **响应**:
```json
{
  "submission": "object",
  "ai_review": "object",
  "human_review": "object"
}
```

### 6.3 通过审核

- **路径**: `POST /api/reviews/{submission_id}/approve`
- **权限**: Reviewer
- **请求体**:
```json
{
  "comments": "string"
}
```

### 6.4 打回审核

- **路径**: `POST /api/reviews/{submission_id}/reject`
- **权限**: Reviewer
- **请求体**:
```json
{
  "comments": "string"
}
```

### 6.5 修订审核

- **路径**: `POST /api/reviews/{submission_id}/revise`
- **权限**: Reviewer
- **请求体**:
```json
{
  "revised_data": "object",
  "comments": "string"
}
```

### 6.6 批量审核

- **路径**: `POST /api/reviews/batch`
- **权限**: Reviewer
- **请求体**:
```json
{
  "submission_ids": "array",
  "action": "approve | reject",
  "comments": "string"
}
```

---

## 7. Exports API - 数据导出

### 7.1 导出任务结果

- **路径**: `POST /api/exports/task/{task_id}`
- **权限**: Owner
- **请求体**:
```json
{
  "format": "json | jsonl | csv | xlsx",
  "filter": {
    "status": "string",
    "date_range": ["datetime", "datetime"]
  }
}
```
- **响应**: 文件下载

### 7.2 获取导出历史

- **路径**: `GET /api/exports`
- **权限**: Owner
- **查询参数**:
  - `task_id`: 任务ID
  - `page`: 页码
- **响应**:
```json
{
  "items": [
    {
      "id": "integer",
      "task_id": "integer",
      "format": "string",
      "status": "string",
      "file_path": "string",
      "created_at": "datetime"
    }
  ],
  "total": "integer"
}
```

### 7.3 导出单个提交

- **路径**: `GET /api/exports/submission/{submission_id}`
- **权限**: Owner/Reviewer
- **查询参数**:
  - `format`: json | jsonl

---

## 8. Audit Logs API - 审计日志

### 8.1 获取审计日志

- **路径**: `GET /api/audit-logs`
- **权限**: Owner
- **查询参数**:
  - `user_id`: 用户ID
  - `action`: 操作类型
  - `target_type`: 目标类型
  - `start_time`: 开始时间
  - `end_time`: 结束时间
  - `page`: 页码
- **响应**:
```json
{
  "items": [
    {
      "id": "integer",
      "user_id": "integer",
      "action": "string",
      "target_type": "string",
      "target_id": "integer",
      "before_data": "object",
      "after_data": "object",
      "created_at": "datetime"
    }
  ],
  "total": "integer"
}
```

---

## 9. Auth API - 用户认证

### 9.1 登录

- **路径**: `POST /api/auth/login`
- **请求体**:
```json
{
  "username": "string",
  "password": "string"
}
```
- **响应**:
```json
{
  "access_token": "string",
  "token_type": "bearer",
  "user": {
    "id": "integer",
    "username": "string",
    "role": "string"
  }
}
```

### 9.2 登出

- **路径**: `POST /api/auth/logout`
- **权限**: Authenticated

---

## 错误响应格式

```json
{
  "error": "string",
  "message": "string",
  "code": "integer"
}
```

---

## API 权限矩阵

| API 路径 | Owner | Labeler | Reviewer |
|----------|-------|---------|----------|
| /api/tasks | ✅ | ✅ | ✅ |
| /api/tasks/{id} | ✅ | ✅ | ✅ |
| /api/tasks POST | ✅ | ❌ | ❌ |
| /api/tasks/{id} PUT | ✅ | ❌ | ❌ |
| /api/tasks/{id} DELETE | ✅ | ❌ | ❌ |
| /api/templates | ✅ | ✅ | ✅ |
| /api/templates POST | ✅ | ❌ | ❌ |
| /api/datasets | ✅ | ✅ | ✅ |
| /api/datasets/import | ✅ | ❌ | ❌ |
| /api/datasets/import-demo | ✅ | ❌ | ❌ |
| /api/labeler/* | ❌ | ✅ | ❌ |
| /api/ai-reviews/* | ✅ | ❌ | ✅ |
| /api/reviews/* | ✅ | ❌ | ✅ |
| /api/exports/* | ✅ | ❌ | ❌ |
| /api/audit-logs | ✅ | ❌ | ❌ |