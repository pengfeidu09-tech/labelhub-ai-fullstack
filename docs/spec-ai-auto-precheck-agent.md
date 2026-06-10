## LabelHub AI 自动预审 Agent 正式改造 Spec

版本: v1.0 | 日期: 2026-06-09 | 状态: 待确认 | 前置文档: labelhub-code-review-report.md

---

## 1. 当前问题总结

代码审查报告确认了 8 个核心问题，按严重度排列:

| # | 问题 | 严重度 | 根因 |
|---|------|--------|------|
| 1 | 标注提交后不自动触发 AI 预审 | P0 | `submit_submission()` (submission_service.py:74) 完成后直接返回，无任何预审调用 |
| 2 | 提交后 DatasetItem 被重置为 unclaimed | P0 | submission_service.py:170-172 执行 `item.status=unclaimed, claimed_by=None` |
| 3 | AI 预审失败会吞掉错误 | P0 | 当前无自动触发，不存在失败处理路径 |
| 4 | 标注质检 / 人工审核 Tab 永远为空 | P1 | `DatasetItem.annotation_phase` 从未在业务流程中被设置 (仅 seed_demo 写入) |
| 5 | HumanReview 摘要为空 | P1 | approve/reject 只写 annotations.json 的 review_info，不创建 HumanReview 数据库记录 |
| 6 | ID 展示混乱 (Item #99 显示为 Submission #36) | P1 | annotation_id 与 DatasetItem.id 属于不同 ID 空间，前端标签 "Submission #" 具有误导性 |
| 7 | [object Object] 展示问题 | P1 | 前端多处直接渲染可能为对象的字段，无类型检查 |
| 8 | 数据排序不稳定 | P2 | 部分 API 无显式排序，依赖数据库默认行为 |

---

## 2. 目标状态机

不引入新枚举值，复用项目现有枚举 (`core/enums.py`)。以下为改造后的完整状态流转:

```
                    ┌─────────────────────────────────────────────┐
                    │             DatasetItem.status              │
                    ├─────────────────────────────────────────────┤
                    │                                             │
  导入 ──→ imported/unclaimed                                     │
                    │                                             │
  认领 ──→ claimed (claimed_by=labeler_id)                        │
                    │                                             │
  草稿 ──→ drafting                                               │
                    │                                             │
  提交 ──→ submitted ← 不再重置为 unclaimed                       │
                    │                                             │
  AI预审 ──→ ai_reviewing (annotation_phase=annotation_qc)        │
                    │                                             │
         ┌────────┼────────┐                                      │
         ↓        ↓        ↓                                      │
    AI pass   AI manual  AI reject                                │
         │     _review    │                                       │
         │        │       │                                       │
  人工审核─→ human_reviewing (annotation_phase=human_review)       │
                    │                                             │
         ┌────────┼────────┐                                      │
         ↓        ↓        ↓                                      │
     approved  rejected   revise                                  │
              _to_modify                                          │
                    │                                             │
  返工提交 ──→ revised_submitted → 重新进入 AI预审/人工审核        │
                    │                                             │
  导出 ──→ export_ready                                           │
```

**annotation_phase 更新规则 (对应任务详情三个 Tab)**:

| 业务阶段 | annotation_phase 值 | Tab 归属 |
|---------|--------------------|---------| 
| 提交后 (待 AI 预审) | `submitted` | 标注 Tab |
| AI 预审中 | `annotation_qc` | 标注质检 Tab |
| AI 预审完成 (pass/manual_review/reject) | `annotation_qc` | 标注质检 Tab |
| 人工审核中 / 完成 | `human_review` | 人工审核 Tab |
| 审核通过 | `approved` | 人工审核 Tab |
| 审核打回 (返工中) | `rework` | 标注 Tab |

**tasks.py:267-274 的 phase 过滤逻辑需要同步调整**: 当 `phase=qc` 时，查询 `annotation_phase IN ('annotation_qc', 'submitted', 'qc')`; 当 `phase=review` 时，查询 `annotation_phase IN ('human_review', 'approved', 'rework', 'review')`。

---

## 3. 新的 AI Agent 数据流

```
Labeler 提交标注
  │
  ▼
POST /api/labeler/submit
  │ submit_submission_endpoint() [labeler.py:785]
  │
  ├─ [1] 必填项验证 (现有逻辑，不变)
  │
  ├─ [2] create_or_update_annotation() → annotations.json
  │      status="submitted"
  │      不再传 ai_review_data (预审由后端自动触发)
  │
  ├─ [3] 更新 DatasetItem [新增]
  │      status = "submitted" (不再是 unclaimed)
  │      claimed_by = 保留当前 labeler (不再清空)
  │      annotation_phase = "submitted"
  │
  ├─ [4] 入队 AIReviewRun [新增]
  │      调用 agent_service.enqueue_ai_review_run()
  │      → 创建 AIReviewRun(task_id, item_id, annotation_id, labeler_id,
  │          input_snapshot={item_data, result_data, schema_json},
  │          status="pending")
  │      → 审计日志: agent_enqueue
  │
  ├─ [5] 立即执行 Agent [新增, 使用 BackgroundTasks]
  │      background_tasks.add_task(_auto_execute_agent, run_id, task_id, item_id)
  │      → agent_service.execute_agent_run()
  │        → _run_real_agent() 或 _run_mock_agent()
  │        → 写入 score/risk_level/suggestion_action/output_json
  │      → 回写 annotations.json 的 ai_review 字段
  │      → 更新 DatasetItem.annotation_phase = "annotation_qc"
  │      → 审计日志: agent_run_start → agent_run_success / agent_run_failed
  │
  └─ [6] 返回 {success, item_id, annotation_id, ai_review_run_id, status}

AI 失败时的处理:
  → submission 仍然成功 (已写入 annotations.json)
  → AIReviewRun.status = "failed" (或 "fallback_required")
  → DatasetItem.annotation_phase = "annotation_qc" (仍标记为质检阶段)
  → annotations.json 的 ai_review = {status: "failed", error: "..."}
  → 审核队列显示 "AI 预审失败 / 需人工复核"
  → 审计日志记录失败原因
  → 如果 mock_fallback=True，则 fallback 写入 mock 结果，标记 used_fallback=True
```

**为什么用 BackgroundTasks 而不是 Celery/Redis**: 项目当前无外部依赖，FastAPI BackgroundTasks 在提交响应返回后异步执行，不会阻塞前端，且 AI 失败不影响提交结果。对于当前 demo 规模完全足够。

**BackgroundTasks 实现要点**: 需要在 `submit_submission_endpoint` 中注入 `background_tasks: BackgroundTasks` 参数，并将 db session 的创建放在 background task 内部 (不能复用请求级 session)。

---

## 4. Labeler LLM 辅助与 AI 自动预审 Agent 的边界

| 维度 | LLM 辅助 (标注台) | AI 自动预审 Agent (提交后) |
|------|-------------------|--------------------------|
| 课题归属 | 4.3 题目级 LLM 辅助 | 4.4 AI 自动预审 |
| 触发时机 | 标注员作答中手动点击 | 提交后自动触发 |
| 目的 | 难题提示、参考建议、字段辅助 | 正式质量评分、通过/打回/人工复核结论 |
| 结果用途 | 仅供标注员参考 | 进入审核队列，辅助 Reviewer 决策 |
| 是否写入 AIReviewRun | 否 (或 trigger_type=labeler_assist 标记排除) | 是 (trigger_type=auto_on_submit) |
| 是否进入审核队列 | 否 | 是 |
| 按钮文案 | "LLM 辅助" / "难题提示" / "作答参考" | 无按钮，自动执行 |

**标注台按钮改造方案 (选 B, 风险更低)**:

仍复用 `/api/ai-precheck/run` 接口和 `ai_precheck_pipeline`，仍写入 AIReviewRun，但:
- AIReviewRun 新增字段 `trigger_type` (VARCHAR(32), nullable=True, default=NULL)
- 标注台手动触发时: `trigger_type = "labeler_assist"`
- 提交后自动触发时: `trigger_type = "auto_on_submit"`
- 审核队列 (`annotation_service.get_pending_annotations`) 只展示 `trigger_type != "labeler_assist"` 的 AI 结果
- 前端按钮文案改为 "LLM 辅助 / 难题提示"，下方增加提示文案

**AIReviewRun 新增字段**:
```sql
ALTER TABLE ai_review_runs ADD COLUMN trigger_type VARCHAR(32) DEFAULT NULL;
```
可选值: `auto_on_submit` / `labeler_assist` / `manual_retry` / `manual_run`

需要在 `main.py` 的 startup migration 中添加此字段。

---

## 5. 修改文件清单

### 后端 (10 个文件)

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `backend/app/services/submission_service.py` | 核心修改 | 提交后入队 + BackgroundTasks 触发 Agent; 修改 DatasetItem 状态; 更新 annotation_phase |
| `backend/app/api/labeler.py` | 核心修改 | 注入 BackgroundTasks 参数; 调用新提交逻辑 |
| `backend/app/services/agent_service.py` | 增强 | enqueue 时写入 trigger_type; 执行完成后回写 annotations.json + annotation_phase |
| `backend/app/models/ai_review_run.py` | 新增字段 | trigger_type VARCHAR(32) |
| `backend/app/main.py` | migration | 新增 trigger_type 字段迁移 |
| `backend/app/api/reviews.py` | 修改 | approve/reject 时更新 annotation_phase + 创建 HumanReview 记录 |
| `backend/app/api/tasks.py` | 修改 | phase 过滤逻辑扩展 (L267-274) |
| `backend/app/api/datasets.py` | 修改 | 添加默认排序 order_by(DatasetItem.id.asc()) |
| `backend/app/core/enums.py` | 新增枚举 | AuditAction 新增: AI_REVIEW_AUTO_TRIGGERED; trigger_type 常量 |
| `backend/app/services/audit_service.py` | 微调 | 确保 create_audit_log 对新增 action 的支持 |

### 前端 (7 个文件)

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `frontend/src/pages/labeler/LabelWorkbenchPage.tsx` | 修改 | 按钮文案改为 "LLM 辅助"; 添加提示文案; 提交后不再传 ai_review |
| `frontend/src/pages/owner/TaskDetailPage.tsx` | 修改 | 修复 Drawer ID 标签; 修复 [object Object]; phase 过滤 |
| `frontend/src/pages/owner/AgentPage.tsx` | 重构 | 增强为 Agent 运行中心 (见第 9 节) |
| `frontend/src/pages/owner/AuditLogPage.tsx` | 修改 | 展示 Item ID + Annotation ID + AIReviewRun ID |
| `frontend/src/pages/reviewer/ReviewQueuePage.tsx` | 修改 | 修复 [object Object]; ID 展示规范化 |
| `frontend/src/pages/reviewer/ReviewDetailPage.tsx` | 修改 | 页面顶部显示完整 ID 上下文; 修复 [object Object] |
| `frontend/src/api/labeler.ts` | 微调 | 提交请求不再传 ai_review 字段 |

---

## 6. 每个文件具体改什么

### 6.1 `backend/app/services/submission_service.py`

**当前代码 (L74-208)**: `submit_submission()` 在写入 annotation 后将 DatasetItem 重置为 unclaimed (L167-173)，无 AI 触发。

**改造内容**:

(a) 删除 L167-173 的 "释放" 逻辑，替换为:
```python
# 提交后保持 claimed 状态，进入 AI 预审流程
item = db.query(DatasetItem).filter(DatasetItem.id == request.dataset_item_id).first()
if item:
    item.status = ItemStatus.SUBMITTED.value  # "submitted"
    item.annotation_phase = "submitted"
    db.commit()
```

(b) 函数末尾 (return 前) 添加 AI 预审入队逻辑:
```python
# 入队 AI 自动预审
from app.services.agent_service import enqueue_ai_review_run
# 构建 input_snapshot
item_data = {}
if item and item.raw_data_json:
    item_data = item.raw_data_json if isinstance(item.raw_data_json, dict) else {}
input_snapshot = {
    "item_data": item_data,
    "result_data": result_data,
    "schema_json": None,
    "task_id": request.task_id,
    "dataset_item_id": request.dataset_item_id,
}
run = enqueue_ai_review_run(
    db=db,
    task_id=request.task_id,
    item_id=request.dataset_item_id,
    annotation_id=annotation.get("id"),
    labeler_id=request.labeler_id,
    work_key=f"{request.task_id}:{request.dataset_item_id}:{request.labeler_id}",
    input_snapshot=input_snapshot,
)
# 在 AIReviewRun 上标记 trigger_type
run.trigger_type = "auto_on_submit"
db.commit()
```

(c) 返回值新增 `ai_review_run_id`:
```python
return {
    "success": True,
    "item_id": request.dataset_item_id,
    "submission_id": annotation['id'],  # 保留兼容
    "annotation_id": annotation['id'],
    "ai_review_run_id": run.id if run else None,
    "status": "submitted",
    "message": "提交成功，AI 预审已自动触发"
}
```

### 6.2 `backend/app/api/labeler.py`

**当前代码 (L785-904)**: `submit_submission_endpoint()` 注入 `db: Session`。

**改造内容**:

(a) 注入 BackgroundTasks:
```python
from fastapi import BackgroundTasks

def submit_submission_endpoint(
    request: SubmissionSubmitRequest,
    background_tasks: BackgroundTasks,  # 新增
    db: Session = Depends(get_db)
):
```

(b) 在 `result = submit_submission(db, request)` 之后，添加后台任务:
```python
# 后台执行 AI 预审 (不阻塞前端)
ai_run_id = result.get("ai_review_run_id")
if ai_run_id:
    background_tasks.add_task(
        _execute_agent_after_submit,
        ai_run_id,
        request.task_id,
        request.dataset_item_id,
        result.get("annotation_id") or result.get("submission_id"),
    )
```

(c) 新增后台任务函数:
```python
def _execute_agent_after_submit(run_id: int, task_id: int, item_id: int, annotation_id: int):
    """提交后异步执行 AI 预审 Agent"""
    from app.core.database import SessionLocal
    from app.services.agent_service import execute_agent_run, _update_annotation_after_agent
    db = SessionLocal()
    try:
        run = db.query(AIReviewRun).filter(AIReviewRun.id == run_id).first()
        if run:
            execute_agent_run(db, run)
            # Agent 执行完成后回写 annotations.json 和 annotation_phase
            _update_annotation_after_agent(db, run, annotation_id, item_id, task_id)
    except Exception as e:
        logger.error(f"[background_agent] run #{run_id} failed: {e}")
    finally:
        db.close()
```

### 6.3 `backend/app/services/agent_service.py`

**改造内容**:

(a) `enqueue_ai_review_run()` (L105-182): 增加 `trigger_type` 参数:
```python
def enqueue_ai_review_run(
    db, task_id, item_id, submission_id=None, annotation_id=None,
    labeler_id=None, work_key=None, input_snapshot=None,
    trigger_type="auto_on_submit"  # 新增参数
) -> AIReviewRun:
    ...
    run = AIReviewRun(
        ...
        trigger_type=trigger_type,  # 新增字段
    )
```

(b) 新增函数 `_update_annotation_after_agent()`:
```python
def _update_annotation_after_agent(db, run, annotation_id, item_id, task_id):
    """Agent 执行完成后回写 annotations.json 和 DatasetItem"""
    # 1. 更新 annotations.json 的 ai_review 字段
    from app.services.annotation_service import _load_annotations, _save_annotations
    annotations = _load_annotations()
    for idx, ann in enumerate(annotations):
        if ann.get("id") == annotation_id:
            ai_review = {
                "run_id": run.id,
                "status": run.status,
                "score": run.score,
                "risk_level": run.risk_level,
                "suggestion": run.suggestion_action,
                "trigger_type": run.trigger_type,
                "output": run.output_json,
            }
            if run.status == "failed":
                ai_review["error"] = run.error_message
                ai_review["error_type"] = run.error_type
            annotations[idx]["ai_review"] = ai_review
            break
    _save_annotations(annotations)

    # 2. 更新 DatasetItem.annotation_phase
    item = db.query(DatasetItem).filter(DatasetItem.id == item_id).first()
    if item:
        item.annotation_phase = "annotation_qc"
        db.commit()
```

### 6.4 `backend/app/models/ai_review_run.py`

新增字段 (L38 之后):
```python
trigger_type = Column(String(32), nullable=True)
```

### 6.5 `backend/app/main.py`

在 startup migration (L146 区域) 新增:
```python
# AIReviewRun 新增 trigger_type
trigger_cols = {c["name"] for c in insp.get_columns("ai_review_runs")} if "ai_review_runs" in (insp.get_table_names() or []) else set()
if "trigger_type" not in trigger_cols:
    try:
        conn.execute(text("ALTER TABLE ai_review_runs ADD COLUMN trigger_type VARCHAR(32)"))
        conn.commit()
    except Exception as e:
        logger.debug(f"[migration] ai_review_runs add trigger_type skipped: {e}")
```

### 6.6 `backend/app/api/reviews.py`

**approve_review (L178-230)**:

(a) 更新 annotation_phase:
```python
# approve 后更新 DatasetItem.annotation_phase
item = db.query(DatasetItem).filter(
    DatasetItem.id == result.get("dataset_item_id")
).first()
if item:
    item.annotation_phase = "approved"
    db.commit()
```

(b) 创建 HumanReview 记录:
```python
from app.models.human_review import HumanReview
hr = HumanReview(
    submission_id=annotation_id,  # 沿用现有语义: submission_id 存储 annotation_id
    reviewer_id=reviewer_id,
    action="approve",
    comments=comment,
    created_at=datetime.now(timezone.utc),
)
db.add(hr)
db.commit()
```

(c) 在审计日志中增加 item_id 和 annotation_id 的完整上下文 (已有，确认不丢失)。

**reject_review (L233+)**: 同样处理，annotation_phase 设为 `"rework"`，HumanReview action 为 `"reject"`。

### 6.7 `backend/app/api/tasks.py`

**L267-274 phase 过滤逻辑改造**:
```python
phase_aliases = {
    'annotation': None,  # 不过滤，显示全部
    'qc': ['submitted', 'annotation_qc', 'qc', 'ai_pending', 'ai_reviewing', 'ai_reviewed'],
    'review': ['human_review', 'human_reviewing', 'approved', 'rework', 'rejected_to_modify', 'review'],
}
if phase and phase != 'annotation':
    aliases = phase_aliases.get(phase, [phase])
    query = query.filter(or_(*[DatasetItem.annotation_phase == alias for alias in aliases]))
```

### 6.8 `backend/app/api/datasets.py`

在所有返回 DatasetItem 列表的查询中添加:
```python
query = query.order_by(DatasetItem.id.asc())
```

### 6.9 `backend/app/core/enums.py`

新增审计动作 (L143 区域):
```python
AI_REVIEW_AUTO_TRIGGERED = "ai_review_auto_triggered"
```

### 6.10 前端改动摘要

**LabelWorkbenchPage.tsx**:
- 搜索 "AI 预审" / "AI 标注质检" 等文案，替换为 "LLM 辅助" / "难题提示"
- 按钮下方添加 `<Alert message="该结果仅供作答参考，不作为正式审核依据" type="info" />`
- 提交时不再把 ai_review 数据传给 submit API (或传但不作为正式审核数据)
- `/api/ai-precheck/run` 仍可使用，但后端会标记 trigger_type=labeler_assist

**TaskDetailPage.tsx**:
- L746: `"Submission #"` 改为 `"标注 #"` 或 `"Annotation #"`
- Drawer 中所有 ID 展示添加上下文: `Annotation #36 (Item #99)`
- 添加 `typeof` 检查防止 [object Object]

**ReviewQueuePage.tsx / ReviewDetailPage.tsx**:
- 规范化 ID 展示 (见第 7 节 ID 规范)
- 添加安全检查: `typeof value === 'object' ? JSON.stringify(value) : String(value)`

**AuditLogPage.tsx**:
- 使用 `log.item_id`、`log.annotation_id`、`log.work_key` 构建可读上下文
- 展示格式: `审核通过 Annotation #36（Item #99, Task #5, work_key=5:99:2）`

---

## 7. 数据字段与 ID 规范

### 7.1 ID 命名统一规范

| ID 名称 | 数据源 | 前端标签 | 说明 |
|---------|--------|---------|------|
| DatasetItem.id | 数据库 dataset_items 表 | `Item #X` | 原始数据项，全局唯一主标识 |
| Annotation.id | annotations.json | `标注 #X` | 标注记录 ID (不再叫 "Submission") |
| AIReviewRun.id | 数据库 ai_review_runs 表 | `AI预审 #X` | AI 预审运行记录 |
| HumanReview.id | 数据库 human_reviews 表 | `人工审核 #X` | 人工审核记录 |
| Task.id | 数据库 tasks 表 | `任务 #X` | 任务 ID |
| work_key | 计算字段 `task_id:item_id:labeler_id` | `work_key` | 标注工作单元唯一键 |

### 7.2 前端展示规范

所有 ID 展示必须遵守:
1. 主标识永远是 `Item #X`
2. 辅助标识同时展示必要的上下文 ID
3. 禁止出现 "Submission #" (改为 "标注 #")
4. 字段缺失显示 `-`，不显示 null / undefined / NaN
5. 对象类型字段必须检查: `typeof v === 'object' ? JSON.stringify(v).slice(0, 80) : String(v ?? '-')`

### 7.3 各页面 ID 展示要求

**审核队列页**: 每行显示 Annotation ID + Item ID + Task ID + work_key + AI 评分摘要

**审核详情页**: 页面顶部 `Annotation #36 / Item #99 / Task #5 / work_key=5:99:2`

**审计日志页**: `审核通过 Annotation #36（Item #99, Task #5, work_key=5:99:2）`

**工作单详情 Drawer**: Item ID + Annotation ID + AIReviewRun ID + HumanReview ID + work_key

---

## 8. annotation_phase 更新规则

| 触发点 | 文件 | 函数 | 设置值 |
|--------|------|------|--------|
| Labeler 提交 | submission_service.py | submit_submission() | `"submitted"` |
| AI 预审完成 | agent_service.py | _update_annotation_after_agent() | `"annotation_qc"` |
| 审核开始 (打开审核详情) | reviews.py | get_review_detail() | `"human_review"` (如当前为 annotation_qc) |
| 审核通过 | reviews.py | approve_review() | `"approved"` |
| 审核打回 | reviews.py | reject_review() | `"rework"` |
| 返工提交 | submission_service.py | submit_submission() (状态为 revised) | `"submitted"` |

**tasks.py phase 过滤映射表**:

```python
phase_to_annotation_phases = {
    'annotation': None,  # 不过滤
    'qc': ['submitted', 'annotation_qc', 'qc'],
    'review': ['human_review', 'approved', 'rework', 'rejected_to_modify', 'review'],
}
```

---

## 9. AIReviewRun 触发与写入规则

### 9.1 触发类型 (trigger_type)

| trigger_type | 触发方式 | 写入 AIReviewRun | 进入审核队列 | 审核详情可见 |
|-------------|---------|-----------------|-------------|------------|
| `auto_on_submit` | 提交后自动 | 是 | 是 | 是 |
| `labeler_assist` | 标注台手动 LLM 辅助 | 是 | 否 | 否 (标注台可查看) |
| `manual_retry` | Agent 页面手动重试 | 是 (更新已有记录) | 是 | 是 |
| `manual_run` | Agent 页面手动执行 | 是 | 是 | 是 |

### 9.2 AIReviewRun 写入字段

每次创建/更新 AIReviewRun 时，必须写入:

| 字段 | 说明 |
|------|------|
| task_id | 任务 ID |
| item_id | DatasetItem.id |
| annotation_id | annotations.json 中的 annotation id |
| labeler_id | 标注员 ID |
| trigger_type | 触发类型 (见上表) |
| input_snapshot_json | {item_data, result_data, schema_json} |
| model_provider / model_name / base_url | 实际使用的 provider 信息 |
| status | pending → running → success / failed / fallback_required |
| score | overall_score (0-100) |
| risk_level | low / medium / high |
| suggestion_action | submit / manual_review / rework / reject |
| output_json | 完整结构化输出 (dimension_scores, reason, summary, issue_tags, suggested_fix) |
| latency_ms | 执行耗时 |
| used_fallback | 是否使用了 mock 兜底 |
| error_type / error_message | 失败时的错误分类和详情 |
| prompt_version | prompt 版本号 |
| retry_count | 重试次数 |

### 9.3 失败处理规则

1. AI 调用超时/异常 → 尝试 mock 兜底 (如果 mock_fallback=True)
2. Mock 兜底成功 → status="success", used_fallback=True
3. Mock 兜底失败 → status="failed", 记录 error_type 和 error_message
4. 重试超过 3 次 → status="fallback_required"
5. **任何情况下 submission 都不受影响** — AI 失败只影响 AIReviewRun，不影响 annotations.json 的提交状态

---

## 10. HumanReview / review_info 摘要规则

### 10.1 创建 HumanReview 记录

在 `reviews.py` 的 `approve_review()` 和 `reject_review()` 中，创建 HumanReview 数据库记录:

```python
from app.models.human_review import HumanReview

hr = HumanReview(
    submission_id=annotation_id,  # 沿用现有字段语义
    reviewer_id=reviewer_id,
    action="approve" | "reject" | "revise",
    comments=comment,
    created_at=datetime.now(timezone.utc),
)
db.add(hr)
db.commit()
```

**注意**: HumanReview 模型的 `submission_id` 字段实际存储 annotation_id (annotations.json 的 id)。这与现有代码的语义一致 (reviews.py 的路径参数就是 `annotation_id`)。不在本次改造中修改模型字段名，避免破坏现有逻辑。

### 10.2 Drawer 中 HumanReview 摘要

后端 `tasks.py` 构建 result_items 时，从 HumanReview 表查询最新记录:

```python
from app.models.human_review import HumanReview
latest_hr = db.query(HumanReview).filter(
    HumanReview.submission_id == annotation_id
).order_by(HumanReview.id.desc()).first()
```

前端 Drawer 展示:
```
人工审核 #12 / 通过 / 审核人 #1 / 2026-06-08 17:19:02
```

如果 HumanReview 不存在但 review_info 存在，降级展示:
```
审核: 通过 / 审核人 #1 / 备注: 审核通过 / 2026-06-08 17:19:02
```

---

## 11. 审计日志增强规则

### 11.1 新增审计动作

| 动作 | action 值 | target_type | target_id | 触发点 |
|------|----------|-------------|-----------|--------|
| 提交后自动入队 | `agent_enqueue` | `ai_review` | AIReviewRun.id | agent_service.enqueue_ai_review_run() |
| Agent 开始执行 | `agent_run_start` | `ai_review` | AIReviewRun.id | agent_service.execute_agent_run() |
| Agent 执行成功 | `agent_run_success` | `ai_review` | AIReviewRun.id | agent_service.execute_agent_run() |
| Agent 执行失败 | `agent_run_failed` | `ai_review` | AIReviewRun.id | agent_service.execute_agent_run() |
| Agent mock 兜底 | `agent_fallback_required` | `ai_review` | AIReviewRun.id | agent_service.execute_agent_run() |
| 标注提交 | `submission_submit` | `annotation` | annotation_id | labeler.py submit 接口 |
| 审核通过 | `review_approve` | `submission` | annotation_id | reviews.py approve_review() |
| 审核打回 | `review_reject` | `submission` | annotation_id | reviews.py reject_review() |

### 11.2 审计日志上下文字段

每条审计日志必须包含:
```python
{
    "task_id": task_id,
    "item_id": dataset_item_id,
    "annotation_id": annotation_id,
    "work_key": f"{task_id}:{item_id}:{labeler_id}",
    "message": "可读的中文描述",
    "payload_json": { ... 结构化数据 ... }
}
```

`create_audit_log()` 已经支持所有这些字段 (`audit_service.py:15-55`)，只需确保调用方正确传入。

### 11.3 前端审计日志展示

`AuditLogPage.tsx` 中修改 `formatAuditContext()`:

```typescript
// 对于所有审核类 action，展示完整上下文
function formatAuditContext(log: AuditLog): string {
    const parts: string[] = [];
    if (log.annotation_id) parts.push(`Annotation #${log.annotation_id}`);
    if (log.item_id) parts.push(`Item #${log.item_id}`);
    if (log.task_id) parts.push(`Task #${log.task_id}`);
    if (log.work_key) parts.push(`work_key=${log.work_key}`);
    // 对于 AI Agent 相关，追加 score/risk
    if (log.action.startsWith('agent_') && log.payload_json) {
        if (log.payload_json.score != null) parts.push(`score=${log.payload_json.score}`);
        if (log.payload_json.risk_level) parts.push(`risk=${log.payload_json.risk_level}`);
    }
    return parts.join(', ');
}
```

---

## 12. 排序规则

| 页面/API | 排序规则 | 文件/行号 |
|---------|---------|----------|
| 任务详情标注 Tab | DatasetItem.id ASC | tasks.py L370+ |
| 任务详情质检 Tab | DatasetItem.id ASC | tasks.py L370+ |
| 任务详情审核 Tab | DatasetItem.id ASC | tasks.py L370+ |
| 数据集列表 | DatasetItem.id ASC | datasets.py (需添加) |
| 审核队列 | annotation_id DESC (最新提交在前) | annotation_service.py (已有) |
| 审计日志 | AuditLog.created_at DESC | audit_logs.py (已有) |
| Agent 运行记录 | AIReviewRun.id DESC | agent_service.py L456 (已有) |
| 我的提交 (Labeler) | annotation_id DESC | annotation_service.py (已有) |

---

## 13. 风险点

| 风险 | 严重度 | 缓解措施 |
|------|--------|---------|
| BackgroundTasks 使用独立 db session，可能与请求 session 冲突 | 高 | 在 background task 内部创建新的 SessionLocal，不复用请求级 session |
| annotations.json 并发读写竞争 | 高 | 使用现有的文件锁机制 (annotation_service.py 中的 _load/_save); Background task 是单线程串行的 |
| 提交后不再释放 DatasetItem 为 unclaimed，可能影响认领流程 | 中 | 验证 TaskMarketPage 的认领逻辑：只展示 status=unclaimed 或 imported 的 item；打回后重新允许认领 |
| AIReviewRun.trigger_type 新字段可能与现有 mock 数据不兼容 | 低 | 字段设为 nullable=True，默认 NULL; 现有数据不受影响 |
| HumanReview 记录的 submission_id 实际存储 annotation_id | 低 | 这是沿用现有语义，不在本次修改; 但前端展示标签改为 "人工审核 #" 而非 "Submission #" |
| AgentPage 重构工作量较大 | 中 | 分两步: 先实现核心自动触发 (P0)，再增强 AgentPage UI (P1) |
| 修改 reviews.py 的 approve/reject 可能影响现有审核流程 | 中 | 只在末尾追加 annotation_phase 更新和 HumanReview 创建，不修改主流程 |
| tasks.py phase 过滤逻辑变更可能影响种子数据展示 | 低 | 新的过滤条件是超集 (包含更多别名)，不会排除种子数据 |

---

## 14. 回滚方案

### 14.1 代码级回滚

所有改动都是增量式的 (在现有函数末尾追加逻辑，不删除核心逻辑)。回滚时:

1. `submission_service.py`: 恢复 DatasetItem.status=unclaimed 的释放逻辑; 删除 AI 入队代码
2. `labeler.py`: 移除 BackgroundTasks 注入
3. `agent_service.py`: 移除 trigger_type 参数 (函数签名兼容，新参数有默认值)
4. `reviews.py`: 移除 HumanReview 创建和 annotation_phase 更新
5. `tasks.py`: 恢复原始 phase_aliases 映射
6. `main.py`: 移除 trigger_type migration (字段保留不影响运行)

### 14.2 数据级回滚

- AIReviewRun.trigger_type 字段为 nullable，回滚代码后现有记录不受影响
- DatasetItem.annotation_phase 如果被设置了错误值，可以批量重置为 NULL
- annotations.json 中新增的 ai_review 字段不影响旧代码读取

### 14.3 回滚判断条件

出现以下情况时应考虑回滚:
- 提交后 DatasetItem 状态异常导致认领流程断裂
- BackgroundTasks 导致数据不一致 (annotation 写入但 Agent 未完成)
- 审核流程出现 500 错误

---

## 15. 人工验收步骤

### 前置准备

1. 启动后端: `cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
2. 启动前端: `cd frontend && npm run dev`
3. 打开浏览器: http://localhost:3000

### 验收流程

**Step 1: 标注台 LLM 辅助 (验收标准 1)**

1. 以 Labeler 身份进入标注工作台
2. 确认按钮文案已改为 "LLM 辅助" / "难题提示" (不再是 "AI 预审")
3. 确认页面有提示文案: "该结果仅供标注员作答参考，不作为正式审核依据"
4. 点击 LLM 辅助按钮，确认结果正常展示
5. 确认此操作不会在审核队列中产生正式 AI 预审记录

**Step 2: 提交后自动预审 (验收标准 2-3)**

1. 在工作台填写标注，点击 "提交"
2. 确认提交成功，页面显示 "提交成功，AI 预审已自动触发"
3. 进入 Owner → Agent 页面，确认能看到刚触发的 AIReviewRun
4. 确认该 Run 的 trigger_type 显示为 `auto_on_submit`
5. 确认 Run 有 score / risk_level / suggestion_action

**Step 3: 审核队列看到 AI 结果 (验收标准 4-5)**

1. 以 Reviewer 身份进入审核队列
2. 确认刚提交的标注出现在审核队列中
3. 确认行内展示: Annotation ID + Item ID + AI score + AI risk + AI suggestion
4. 点击审核详情，确认能看到:
   - 页面顶部: `Annotation #X / Item #Y / Task #Z`
   - AI 评语和多维度评分
   - 原始 Prompt

**Step 4: 人工审核 + HumanReview 摘要 (验收标准 6)**

1. 在审核详情页点击 "通过"
2. 回到 Owner → 任务详情 → 打开该工作单 Drawer
3. 确认 "最近 HumanReview" 显示: `人工审核 #X / 通过 / 审核人 #Y / 时间`
4. 确认不再显示 `最近 HumanReview: -`

**Step 5: 标注质检 / 人工审核 Tab (验收标准 7-8)**

1. 进入 Owner → 任务详情
2. 切换到 "标注质检" Tab，确认有 AI 预审记录 (不再为空)
3. 切换到 "人工审核" Tab，确认有审核通过记录 (不再为空)
4. 确认各 Tab 数据按 Item ID ASC 排序

**Step 6: 审计日志串联 (验收标准 9-10)**

1. 进入 Owner → 审计日志
2. 搜索该 Item 相关的日志
3. 确认能看到完整链路:
   - `submission_submit` (Annotation #X, Item #Y, Task #Z)
   - `agent_enqueue` (AI预审 #W, Item #Y)
   - `agent_run_start` (AI预审 #W)
   - `agent_run_success` (AI预审 #W, score=85, risk=low)
   - `review_approve` (Annotation #X, Item #Y, Task #Z)
4. 确认所有日志同时展示 Item ID 和 Annotation ID

**Step 7: 提交后数据不可再领取 (验收标准 12)**

1. 以 Labeler 身份进入任务市场
2. 确认刚提交的数据不再出现在可领取列表中
3. 以 Reviewer 身份打回该数据
4. 确认打回后该数据重新出现在 Labeler 的任务列表 (返修状态)

**Step 8: 导出主流程 (验收标准 14)**

1. 进入 Owner → 导出
2. 选择已通过审核的数据
3. 确认 JSON / CSV / XLSX 导出正常

**Step 9: [object Object] 检查 (验收标准 11)**

1. 遍历所有页面: 审核队列、审核详情、任务详情 Drawer、审计日志
2. 确认不出现 `[object Object]`、`undefined`、`null`
3. 确认字段缺失时显示 `-`

---

## 附录 A: 改造实施顺序

| 阶段 | 内容 | 文件数 | 预估耗时 |
|------|------|--------|---------|
| Phase 1 (P0) | 提交后自动触发 Agent + 不释放 DatasetItem | 4 (submission_service, labeler, agent_service, main) | 2h |
| Phase 2 (P1) | annotation_phase 同步 + Tab 修复 | 3 (reviews, tasks, agent_service) | 1.5h |
| Phase 3 (P1) | HumanReview 记录创建 + Drawer 摘要 | 2 (reviews, tasks) | 1h |
| Phase 4 (P1) | ID 展示规范化 + [object Object] 修复 | 5 (TaskDetailPage, ReviewQueuePage, ReviewDetailPage, AuditLogPage, labeler) | 2h |
| Phase 5 (P1) | 标注台 LLM 辅助语义修正 | 2 (LabelWorkbenchPage, ai_precheck) | 0.5h |
| Phase 6 (P1) | Agent 页面增强 | 1 (AgentPage) | 2h |
| Phase 7 (P2) | 排序修复 | 2 (datasets, tasks) | 0.5h |

**总预估: 9.5 小时 (约 1.5 个工作日)**

## 附录 B: 新增枚举/常量

```python
# core/enums.py 新增
class AuditAction(str, Enum):
    ...  # 现有枚举不变
    AI_REVIEW_AUTO_TRIGGERED = "ai_review_auto_triggered"

# 新增 trigger_type 常量 (可放在 agent_service.py 或单独的 constants.py)
TRIGGER_AUTO_ON_SUBMIT = "auto_on_submit"
TRIGGER_LABELER_ASSIST = "labeler_assist"
TRIGGER_MANUAL_RETRY = "manual_retry"
TRIGGER_MANUAL_RUN = "manual_run"
```

## 附录 C: 禁止事项确认

| 禁止事项 | 确认 |
|---------|------|
| 不重置数据库 | ✅ 只添加 ALTER TABLE migration |
| 不删除 demo 数据 | ✅ |
| 不修改 backend/.env | ✅ |
| 不迁移 annotations.json 到数据库 | ✅ |
| 不重新启用数据库 Submission 表作为主路径 | ✅ |
| 不启用旧 ai_precheck_service.py | ✅ |
| 不引入 Redis / Celery / 新依赖 | ✅ 使用 FastAPI BackgroundTasks |
| 不大改模板 Designer | ✅ |
| 不大改导出功能 | ✅ |
| 不重做登录权限 | ✅ |
| 不大改 state_machine_service.py | ✅ 不引入 |
