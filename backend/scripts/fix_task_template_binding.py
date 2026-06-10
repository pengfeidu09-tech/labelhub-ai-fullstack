#!/usr/bin/env python3
"""
fix_task_template_binding.py
----------------------------
Repair script: bind every task to exactly one template_schema and govern legacy templates.

Usage (run from backend/ where labelhub.db lives):
    python scripts/fix_task_template_binding.py
    python scripts/fix_task_template_binding.py --dry-run

Idempotent: running multiple times will NOT create duplicate templates.
"""

import argparse
import io
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

# Ensure stdout can handle Chinese characters on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Hardcoded base schemas (mirrored from template_service.py)
# ---------------------------------------------------------------------------

QA_QUALITY_SCHEMA = {
    "schema_version": "1.0.0",
    "dataset_type": "qa_quality",
    "name": "问答质量评估模板",
    "description": "用于评估大模型回答质量的标注模板",
    "layout": {
        "type": "single_column",
        "sections": []
    },
    "fields": [
        {
            "id": "prompt_show",
            "type": "ShowItem",
            "label": "问题",
            "binding": "{{item.prompt}}",
            "format": "text",
            "required": False,
            "props": {}
        },
        {
            "id": "model_answer_show",
            "type": "ShowItem",
            "label": "模型回答",
            "binding": "{{item.model_answer}}",
            "format": "markdown",
            "required": False,
            "props": {}
        },
        {
            "id": "reference_show",
            "type": "ShowItem",
            "label": "参考答案",
            "binding": "{{item.reference}}",
            "format": "text",
            "required": False,
            "props": {}
        },
        {
            "id": "category_show",
            "type": "ShowItem",
            "label": "类别",
            "binding": "{{item.category}}",
            "format": "text",
            "required": False,
            "props": {}
        },
        {
            "id": "difficulty_show",
            "type": "ShowItem",
            "label": "难度",
            "binding": "{{item.difficulty}}",
            "format": "text",
            "required": False,
            "props": {}
        },
        {
            "id": "tags_show",
            "type": "ShowItem",
            "label": "标签",
            "binding": "{{item.tags}}",
            "format": "text",
            "required": False,
            "props": {}
        },
        {
            "id": "relevance",
            "type": "Radio",
            "label": "相关性",
            "required": True,
            "options": [
                {"label": "高", "value": "high"},
                {"label": "中", "value": "medium"},
                {"label": "低", "value": "low"}
            ],
            "validation": {
                "required": True
            },
            "props": {}
        },
        {
            "id": "accuracy",
            "type": "Radio",
            "label": "准确性",
            "required": True,
            "options": [
                {"label": "正确", "value": "correct"},
                {"label": "部分正确", "value": "partially_correct"},
                {"label": "错误", "value": "incorrect"}
            ],
            "validation": {
                "required": True
            },
            "props": {}
        },
        {
            "id": "completeness",
            "type": "Radio",
            "label": "完整性",
            "required": True,
            "options": [
                {"label": "完整", "value": "complete"},
                {"label": "部分", "value": "partial"},
                {"label": "不完整", "value": "incomplete"}
            ],
            "validation": {
                "required": True
            },
            "props": {}
        },
        {
            "id": "safety",
            "type": "Radio",
            "label": "安全性",
            "required": True,
            "options": [
                {"label": "安全", "value": "safe"},
                {"label": "风险", "value": "risky"},
                {"label": "不安全", "value": "unsafe"}
            ],
            "validation": {
                "required": True
            },
            "props": {}
        },
        {
            "id": "overall_comment",
            "type": "Textarea",
            "label": "总体评价",
            "required": False,
            "placeholder": "请输入总体评价...",
            "rows": 3,
            "props": {}
        },
        {
            "id": "reason",
            "type": "Textarea",
            "label": "详细理由",
            "required": True,
            "placeholder": "请详细说明评分理由...",
            "rows": 4,
            "validation": {
                "required": True
            },
            "props": {}
        },
        {
            "id": "issue_tags",
            "type": "TagSelect",
            "label": "问题标签",
            "required": False,
            "options": [
                {"label": "事实错误", "value": "fact_error"},
                {"label": "信息不全", "value": "incomplete"},
                {"label": "偏离主题", "value": "off_topic"},
                {"label": "安全风险", "value": "unsafe"},
                {"label": "表述模糊", "value": "ambiguous"}
            ],
            "props": {}
        },
        {
            "id": "correction_json",
            "type": "JsonEditor",
            "label": "修正内容",
            "required": False,
            "height": 150,
            "props": {}
        }
    ],
    "rules": [
        {
            "id": "show_correction_when_low_accuracy",
            "type": "visibility",
            "when": {
                "field": "accuracy",
                "operator": "in",
                "value": ["incorrect", "partially_correct"]
            },
            "target": "correction_json",
            "effect": "show"
        }
    ],
    "llm_assist": [
        {
            "id": "quality_assist",
            "name": "AI 质量建议",
            "prompt_template": "请根据问题、模型回答和参考答案，给出质量评估建议。",
            "input_bindings": ["prompt", "model_answer", "reference"],
            "output_target": "overall_comment"
        }
    ],
    "export_mapping": [
        {"source": "relevance", "target": "relevance", "include": True},
        {"source": "accuracy", "target": "accuracy", "include": True},
        {"source": "completeness", "target": "completeness", "include": True},
        {"source": "safety", "target": "safety", "include": True},
        {"source": "reason", "target": "reason", "include": True}
    ],
    "ai_review_config": {
        "enabled": True,
        "scoreDimensions": [
            {"name": "相关性", "weight": 0.2},
            {"name": "准确性", "weight": 0.3},
            {"name": "完整性", "weight": 0.2},
            {"name": "安全性", "weight": 0.2},
            {"name": "总评", "weight": 0.1}
        ],
        "passThreshold": 80,
        "rejectThreshold": 60
    }
}

PREFERENCE_COMPARE_SCHEMA = {
    "schema_version": "1.0.0",
    "dataset_type": "preference_compare",
    "name": "A/B 偏好对比模板",
    "description": "用于对比两个回答的偏好选择",
    "layout": {
        "type": "two_column",
        "sections": []
    },
    "fields": [
        {
            "id": "prompt_show",
            "type": "ShowItem",
            "label": "问题",
            "binding": "{{item.prompt}}",
            "format": "text",
            "required": False,
            "props": {}
        },
        {
            "id": "response_a_show",
            "type": "ShowItem",
            "label": "回答 A",
            "binding": "{{item.response_a}}",
            "format": "markdown",
            "required": False,
            "props": {}
        },
        {
            "id": "response_b_show",
            "type": "ShowItem",
            "label": "回答 B",
            "binding": "{{item.response_b}}",
            "format": "markdown",
            "required": False,
            "props": {}
        },
        {
            "id": "model_a_show",
            "type": "ShowItem",
            "label": "模型 A",
            "binding": "{{item.model_a}}",
            "format": "text",
            "required": False,
            "props": {}
        },
        {
            "id": "model_b_show",
            "type": "ShowItem",
            "label": "模型 B",
            "binding": "{{item.model_b}}",
            "format": "text",
            "required": False,
            "props": {}
        },
        {
            "id": "preferred",
            "type": "Radio",
            "label": "更优回答",
            "required": True,
            "options": [
                {"label": "回答 A", "value": "a"},
                {"label": "回答 B", "value": "b"},
                {"label": "两者相当", "value": "tie"}
            ],
            "validation": {
                "required": True
            },
            "props": {}
        },
        {
            "id": "margin",
            "type": "Radio",
            "label": "差异程度",
            "required": True,
            "options": [
                {"label": "明显差异", "value": "large"},
                {"label": "轻微差异", "value": "small"},
                {"label": "无差异", "value": "none"}
            ],
            "validation": {
                "required": True
            },
            "props": {}
        },
        {
            "id": "safety_flag",
            "type": "Radio",
            "label": "安全标记",
            "required": True,
            "options": [
                {"label": "安全", "value": "safe"},
                {"label": "风险", "value": "risky"},
                {"label": "不安全", "value": "unsafe"}
            ],
            "validation": {
                "required": True
            },
            "props": {}
        },
        {
            "id": "dimensions",
            "type": "Checkbox",
            "label": "评估维度",
            "required": False,
            "options": [
                {"label": "正确性", "value": "correctness"},
                {"label": "完整性", "value": "completeness"},
                {"label": "逻辑性", "value": "logic"},
                {"label": "流畅性", "value": "fluency"}
            ],
            "props": {}
        },
        {
            "id": "reason",
            "type": "Textarea",
            "label": "判断理由",
            "required": True,
            "placeholder": "请说明选择理由...",
            "rows": 4,
            "validation": {
                "required": True
            },
            "props": {}
        }
    ],
    "rules": [],
    "llm_assist": [
        {
            "id": "preference_assist",
            "name": "AI 偏好建议",
            "prompt_template": "请根据问题、回答A和回答B，给出偏好选择建议。",
            "input_bindings": ["prompt", "response_a", "response_b"],
            "output_target": "reason"
        }
    ],
    "export_mapping": [
        {"source": "preferred", "target": "preferred", "include": True},
        {"source": "margin", "target": "margin", "include": True},
        {"source": "safety_flag", "target": "safety_flag", "include": True},
        {"source": "reason", "target": "reason", "include": True}
    ],
    "ai_review_config": {
        "enabled": True,
        "scoreDimensions": [
            {"name": "正确性", "weight": 0.4},
            {"name": "完整性", "weight": 0.3},
            {"name": "逻辑性", "weight": 0.3}
        ],
        "passThreshold": 85,
        "rejectThreshold": 70
    }
}

BASE_SCHEMAS = {
    "qa_quality": QA_QUALITY_SCHEMA,
    "preference_compare": PREFERENCE_COMPARE_SCHEMA,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DB_PATH = "labelhub.db"


def get_existing_columns(cursor: sqlite3.Cursor, table_name: str) -> set:
    """Return set of column names for a table using PRAGMA."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def add_column_if_missing(cursor: sqlite3.Cursor, table: str, col: str, col_def: str):
    """ALTER TABLE ADD COLUMN only if the column does not already exist."""
    existing = get_existing_columns(cursor, table)
    if col not in existing:
        sql = f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"
        print(f"  [ALTER] {sql}")
        cursor.execute(sql)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Step 0: Add missing columns
# ---------------------------------------------------------------------------

def step0_add_columns(cursor: sqlite3.Cursor, dry_run: bool):
    """Add missing columns. This always runs (even in dry-run) because later
    steps depend on these columns existing. ALTER TABLE ADD COLUMN is safe
    and idempotent -- it only adds if the column is truly missing."""
    print("\n=== Step 0: Add missing columns ===")

    # template_schemas new columns
    ts_columns = [
        ("task_id", "INTEGER"),
        ("template_scope", "TEXT"),
        ("is_task_bound", "INTEGER DEFAULT 0"),
        ("is_official_base", "INTEGER DEFAULT 0"),
        ("is_archived", "INTEGER DEFAULT 0"),
        ("visible_in_template_page", "INTEGER DEFAULT 1"),
        ("legacy_reason", "TEXT"),
    ]
    for col, col_def in ts_columns:
        add_column_if_missing(cursor, "template_schemas", col, col_def)

    # tasks new columns
    task_columns = [
        ("llm_assist_enabled", "INTEGER DEFAULT 1"),
    ]
    for col, col_def in task_columns:
        add_column_if_missing(cursor, "tasks", col, col_def)

    print("  Step 0 complete.")


# ---------------------------------------------------------------------------
# Step 1 & 2: Scan tasks and bind existing templates (handle shared refs)
# ---------------------------------------------------------------------------

def step1_2_bind_existing_tasks(cursor: sqlite3.Cursor, dry_run: bool) -> tuple:
    """For tasks that already have a template_id pointing to an existing template,
    mark that template as task_bound and rename it.

    Handles shared templates: if multiple tasks reference the same template_id,
    or the template is already bound to a different task (from a prior run or
    force_fix), the current task gets a clone instead of stealing the binding.

    Returns (fixed_count, created_count).
    """
    print("\n=== Step 1-2: Bind existing task-template pairs ===")
    fixed = 0
    created = 0

    cursor.execute("SELECT id, name, template_id FROM tasks")
    tasks = cursor.fetchall()

    # Build a map: template_id -> list of task_ids that reference it (in DB)
    tpl_to_tasks: dict = {}
    for task_id, task_name, template_id in tasks:
        if template_id is not None:
            tpl_to_tasks.setdefault(template_id, []).append(task_id)

    # Track which templates have been claimed in THIS run
    claimed_templates: dict = {}  # template_id -> task_id that claimed it

    for task_id, task_name, template_id in tasks:
        if template_id is None:
            continue

        # Check if template actually exists and get its current binding state
        cursor.execute(
            "SELECT id, schema, dataset_type, task_id, is_task_bound FROM template_schemas WHERE id = ?",
            (template_id,),
        )
        tpl_row = cursor.fetchone()
        if tpl_row is None:
            print(f"  [WARN] Task {task_id} references template_id={template_id} which does not exist; skipping.")
            continue

        tpl_schema_json = tpl_row[1]
        tpl_dataset_type = tpl_row[2]
        tpl_current_task_id = tpl_row[3]
        tpl_is_task_bound = tpl_row[4]
        new_template_name = f"任务{task_id}-{task_name}-模板"

        # If the template is already correctly bound to THIS task (e.g. from
        # force_fix or a prior run), just make sure the name is right and skip.
        if (tpl_is_task_bound == 1
                and tpl_current_task_id == task_id):
            if not dry_run:
                cursor.execute(
                    """UPDATE template_schemas
                       SET name = ?, visible_in_template_page = 1, updated_at = ?
                       WHERE id = ?""",
                    (new_template_name, now_iso(), template_id),
                )
                print(f"  [SKIP] Task {task_id} -> template {template_id} already correctly bound; name ensured.")
            else:
                print(f"  [DRY-RUN] Task {task_id} -> template {template_id} already bound; would ensure name.")
            fixed += 1
            continue

        # Determine if we can claim this template exclusively
        already_bound_to_other = (
            tpl_is_task_bound == 1
            and tpl_current_task_id is not None
            and tpl_current_task_id != task_id
        )
        is_shared_among_tasks = len(tpl_to_tasks.get(template_id, [])) > 1
        claimed_by_other_in_run = (
            template_id in claimed_templates and claimed_templates[template_id] != task_id
        )

        can_claim = not already_bound_to_other and not is_shared_among_tasks and not claimed_by_other_in_run

        if can_claim:
            # Exclusive: update in place
            if not dry_run:
                cursor.execute(
                    """UPDATE template_schemas
                       SET template_scope = 'task_bound',
                           is_task_bound = 1,
                           visible_in_template_page = 1,
                           task_id = ?,
                           name = ?,
                           updated_at = ?
                       WHERE id = ?""",
                    (task_id, new_template_name, now_iso(), template_id),
                )
                print(f"  [BOUND] Task {task_id} -> template {template_id} renamed to '{new_template_name}'")
                fixed += 1
            else:
                print(f"  [DRY-RUN] Would bind task {task_id} -> template {template_id} as '{new_template_name}'")
                fixed += 1
            claimed_templates[template_id] = task_id
        else:
            # Need a clone: template is shared or already bound to another task
            if not dry_run:
                ts = now_iso()
                cursor.execute(
                    """INSERT INTO template_schemas
                       (name, description, schema, schema_version, dataset_type,
                        frozen_after_publish, created_by, created_at, updated_at,
                        is_active, parent_template_id,
                        template_scope, is_task_bound, task_id,
                        is_archived, visible_in_template_page)
                       VALUES (?, ?, ?, '1.0.0', ?, 0, 1, ?, ?, 1, ?,
                               'task_bound', 1, ?, 0, 1)""",
                    (new_template_name, f"任务{task_id}的绑定模板(克隆自模板{template_id})",
                     tpl_schema_json, tpl_dataset_type, ts, ts,
                     template_id, task_id),
                )
                new_tpl_id = cursor.lastrowid
                cursor.execute(
                    "UPDATE tasks SET template_id = ?, updated_at = ? WHERE id = ?",
                    (new_tpl_id, ts, task_id),
                )
                print(f"  [CLONED] Task {task_id} -> new template {new_tpl_id} (cloned from shared template {template_id}) as '{new_template_name}'")
                created += 1
            else:
                print(f"  [DRY-RUN] Would clone template {template_id} for task {task_id} as '{new_template_name}'")
                created += 1

    print(f"  Step 1-2 complete. fixed_task_bindings = {fixed}, cloned_for_shared = {created}")
    return fixed, created


# ---------------------------------------------------------------------------
# Step 3: Create templates for tasks without one
# ---------------------------------------------------------------------------

def determine_dataset_type(task_name: str) -> str:
    if "preference_compare" in task_name or "偏好" in task_name:
        return "preference_compare"
    return "qa_quality"


def find_or_create_official_base(cursor: sqlite3.Cursor, dataset_type: str, dry_run: bool) -> int:
    """Find an existing official_base template for the given dataset_type,
    or create one from the hardcoded base schema. Returns template id."""
    cursor.execute(
        "SELECT id FROM template_schemas WHERE is_official_base = 1 AND dataset_type = ? LIMIT 1",
        (dataset_type,),
    )
    row = cursor.fetchone()
    if row:
        return row[0]

    # Create from scratch
    ts = now_iso()
    schema_json = json.dumps(BASE_SCHEMAS[dataset_type], ensure_ascii=False)
    base_name = f"官方基础-{dataset_type}-模板"
    desc = f"自动创建的官方基础模板 ({dataset_type})"

    if dry_run:
        print(f"  [DRY-RUN] Would create official_base template for {dataset_type}")
        return -1  # sentinel

    cursor.execute(
        """INSERT INTO template_schemas
           (name, description, schema, schema_version, dataset_type,
            frozen_after_publish, created_by, created_at, updated_at,
            is_active, template_scope, is_official_base, is_task_bound,
            is_archived, visible_in_template_page)
           VALUES (?, ?, ?, '1.0.0', ?, 0, 1, ?, ?, 1, 'official_base', 1, 0, 0, 0)""",
        (base_name, desc, schema_json, dataset_type, ts, ts),
    )
    new_id = cursor.lastrowid
    print(f"  [CREATED] official_base template id={new_id} for {dataset_type}")
    return new_id


def step3_create_missing_templates(cursor: sqlite3.Cursor, dry_run: bool) -> int:
    """For tasks with no template_id (or dangling reference), create and bind a new template."""
    print("\n=== Step 3: Create templates for tasks without one ===")
    created = 0

    cursor.execute("SELECT id, name, template_id FROM tasks")
    tasks = cursor.fetchall()

    for task_id, task_name, template_id in tasks:
        # Skip if template_id exists and template is present
        if template_id is not None:
            cursor.execute("SELECT id FROM template_schemas WHERE id = ?", (template_id,))
            if cursor.fetchone() is not None:
                continue

        # Skip tasks 10 and 11 -- they are handled in step 4/5
        if task_id in (10, 11):
            continue

        dataset_type = determine_dataset_type(task_name)

        # Find or create official base to clone from
        base_id = find_or_create_official_base(cursor, dataset_type, dry_run)

        # Fetch schema JSON from the base template
        if not dry_run and base_id > 0:
            cursor.execute("SELECT schema FROM template_schemas WHERE id = ?", (base_id,))
            row = cursor.fetchone()
            schema_json = row[0] if row else json.dumps(BASE_SCHEMAS[dataset_type], ensure_ascii=False)
        else:
            schema_json = json.dumps(BASE_SCHEMAS[dataset_type], ensure_ascii=False)

        new_template_name = f"任务{task_id}-{task_name}-模板"
        ts = now_iso()

        if dry_run:
            print(f"  [DRY-RUN] Would create task_bound template for task {task_id} ({dataset_type})")
            created += 1
            continue

        cursor.execute(
            """INSERT INTO template_schemas
               (name, description, schema, schema_version, dataset_type,
                frozen_after_publish, created_by, created_at, updated_at,
                is_active, parent_template_id,
                template_scope, is_task_bound, task_id,
                is_archived, visible_in_template_page)
               VALUES (?, ?, ?, '1.0.0', ?, 0, 1, ?, ?, 1, ?,
                       'task_bound', 1, ?, 0, 1)""",
            (new_template_name, f"任务{task_id}的绑定模板", schema_json,
             dataset_type, ts, ts, base_id, task_id),
        )
        new_tpl_id = cursor.lastrowid

        # Update task's template_id
        cursor.execute(
            "UPDATE tasks SET template_id = ?, updated_at = ? WHERE id = ?",
            (new_tpl_id, ts, task_id),
        )
        print(f"  [CREATED] task_bound template id={new_tpl_id} for task {task_id} ({dataset_type})")
        created += 1

    print(f"  Step 3 complete. created_task_templates = {created}")
    return created


# ---------------------------------------------------------------------------
# Step 4 & 5: Force fix tasks 10 and 11
# ---------------------------------------------------------------------------

def force_fix_task(cursor: sqlite3.Cursor, task_id: int, task_name: str,
                   dataset_type: str, dry_run: bool) -> int:
    """Ensure task has exactly one task_bound template of the right type.
    Returns the template id (or -1 in dry-run)."""
    print(f"\n=== Step 4/5: Force fix task {task_id} ({task_name}) ===")

    expected_name = f"任务{task_id}-{task_name}-模板"
    ts = now_iso()

    # Check if there's already a task_bound template for this task
    cursor.execute(
        """SELECT id FROM template_schemas
           WHERE task_id = ? AND is_task_bound = 1
           LIMIT 1""",
        (task_id,),
    )
    row = cursor.fetchone()

    if row:
        tpl_id = row[0]
        print(f"  Task {task_id} already has task_bound template id={tpl_id}; updating in place.")
        if not dry_run:
            cursor.execute(
                """UPDATE template_schemas
                   SET name = ?,
                       dataset_type = ?,
                       template_scope = 'task_bound',
                       is_task_bound = 1,
                       task_id = ?,
                       visible_in_template_page = 1,
                       is_archived = 0,
                       updated_at = ?
                   WHERE id = ?""",
                (expected_name, dataset_type, task_id, ts, tpl_id),
            )
            # Make sure tasks.template_id points to this template
            cursor.execute(
                "UPDATE tasks SET template_id = ?, updated_at = ? WHERE id = ?",
                (tpl_id, ts, task_id),
            )
        else:
            print(f"  [DRY-RUN] Would update template {tpl_id} for task {task_id}")
        return tpl_id

    # No existing task_bound template -- check if task has a template_id pointing somewhere
    cursor.execute("SELECT template_id FROM tasks WHERE id = ?", (task_id,))
    task_row = cursor.fetchone()
    existing_tid = task_row[0] if task_row else None

    if existing_tid is not None:
        cursor.execute("SELECT id FROM template_schemas WHERE id = ?", (existing_tid,))
        if cursor.fetchone() is not None:
            # Re-use the existing template, mark it task_bound
            print(f"  Re-using existing template_id={existing_tid} for task {task_id}.")
            if not dry_run:
                cursor.execute(
                    """UPDATE template_schemas
                       SET name = ?,
                           dataset_type = ?,
                           template_scope = 'task_bound',
                           is_task_bound = 1,
                           task_id = ?,
                           visible_in_template_page = 1,
                           is_archived = 0,
                           updated_at = ?
                       WHERE id = ?""",
                    (expected_name, dataset_type, task_id, ts, existing_tid),
                )
                cursor.execute(
                    "UPDATE tasks SET template_id = ?, updated_at = ? WHERE id = ?",
                    (existing_tid, ts, task_id),
                )
            else:
                print(f"  [DRY-RUN] Would update template {existing_tid}")
            return existing_tid

    # Need to create a brand-new template
    schema_json = json.dumps(BASE_SCHEMAS[dataset_type], ensure_ascii=False)

    if dry_run:
        print(f"  [DRY-RUN] Would create new task_bound template for task {task_id}")
        return -1

    cursor.execute(
        """INSERT INTO template_schemas
           (name, description, schema, schema_version, dataset_type,
            frozen_after_publish, created_by, created_at, updated_at,
            is_active, template_scope, is_task_bound, task_id,
            is_archived, visible_in_template_page)
           VALUES (?, ?, ?, '1.0.0', ?, 0, 1, ?, ?, 1,
                   'task_bound', 1, ?, 0, 1)""",
        (expected_name, f"任务{task_id}的绑定模板", schema_json,
         dataset_type, ts, ts, task_id),
    )
    new_tpl_id = cursor.lastrowid

    cursor.execute(
        "UPDATE tasks SET template_id = ?, updated_at = ? WHERE id = ?",
        (new_tpl_id, ts, task_id),
    )
    print(f"  [CREATED] task_bound template id={new_tpl_id} for task {task_id}")
    return new_tpl_id


# ---------------------------------------------------------------------------
# Step 6: Archive legacy templates
# ---------------------------------------------------------------------------

def step6_archive_legacy(cursor: sqlite3.Cursor, dry_run: bool) -> int:
    """Archive templates with no task_id, not official_base, not task_bound."""
    print("\n=== Step 6: Archive legacy templates ===")
    ts = now_iso()

    cursor.execute(
        """SELECT id, name FROM template_schemas
           WHERE (task_id IS NULL OR task_id = 0)
             AND (is_official_base IS NULL OR is_official_base = 0)
             AND (is_task_bound IS NULL OR is_task_bound = 0)
             AND (template_scope IS NULL OR template_scope NOT IN ('task_bound', 'official_base'))
        """
    )
    legacy_rows = cursor.fetchall()
    archived = 0

    for tpl_id, tpl_name in legacy_rows:
        if not dry_run:
            cursor.execute(
                """UPDATE template_schemas
                   SET template_scope = 'legacy',
                       is_archived = 1,
                       visible_in_template_page = 0,
                       legacy_reason = 'unbound_legacy_template',
                       updated_at = ?
                   WHERE id = ?""",
                (ts, tpl_id),
            )
            print(f"  [ARCHIVED] template id={tpl_id} name='{tpl_name}'")
            archived += 1
        else:
            print(f"  [DRY-RUN] Would archive template id={tpl_id} name='{tpl_name}'")
            archived += 1

    print(f"  Step 6 complete. archived_legacy_templates = {archived}")
    return archived


# ---------------------------------------------------------------------------
# Step 7: Enable LLM assist for tasks 10 and 11
# ---------------------------------------------------------------------------

def step7_enable_llm_assist(cursor: sqlite3.Cursor, dry_run: bool):
    print("\n=== Step 7: Enable LLM assist for tasks 10 and 11 ===")
    ts = now_iso()

    for tid in (10, 11):
        if not dry_run:
            cursor.execute(
                "UPDATE tasks SET llm_assist_enabled = 1, updated_at = ? WHERE id = ?",
                (ts, tid),
            )
            print(f"  [OK] Task {tid}: llm_assist_enabled = 1")
        else:
            print(f"  [DRY-RUN] Would set llm_assist_enabled=1 for task {tid}")

    print("  Step 7 complete.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fix task-template bindings in labelhub.db")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()
    dry_run = args.dry_run

    if not os.path.exists(DB_PATH):
        print(f"ERROR: Cannot find {DB_PATH} in current directory.")
        print("Please run this script from the backend/ directory where labelhub.db lives.")
        sys.exit(1)

    print(f"Database: {os.path.abspath(DB_PATH)}")
    print(f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    try:
        # Step 0: Add missing columns (always safe, idempotent)
        step0_add_columns(cursor, dry_run)

        # Step 4/5 FIRST: Force fix tasks 10 and 11 so their templates are
        # claimed before the general binding pass. This prevents other tasks
        # that share the same template_id from stealing the binding.
        task10_tid = force_fix_task(
            cursor, task_id=10,
            task_name="官方原题·问答质量标注",
            dataset_type="qa_quality",
            dry_run=dry_run,
        )

        task11_tid = force_fix_task(
            cursor, task_id=11,
            task_name="官方原题·偏好对比标注",
            dataset_type="preference_compare",
            dry_run=dry_run,
        )

        # Step 1-2: Bind existing task-template pairs (handles shared templates
        # by cloning; respects bindings already established by force_fix above)
        fixed_bindings, cloned_in_step12 = step1_2_bind_existing_tasks(cursor, dry_run)

        # Step 3: Create templates for tasks that lack one
        created_templates = step3_create_missing_templates(cursor, dry_run)
        created_templates += cloned_in_step12  # include clones from step 1-2

        # Step 6: Archive legacy templates
        archived = step6_archive_legacy(cursor, dry_run)

        # Step 7: Enable LLM assist
        step7_enable_llm_assist(cursor, dry_run)

        if not dry_run:
            conn.commit()
            print("\n>>> All changes COMMITTED successfully.")
        else:
            conn.rollback()
            print("\n>>> DRY-RUN complete. No changes were committed.")

    except Exception as e:
        conn.rollback()
        print(f"\n!!! ERROR: {e}")
        raise
    finally:
        conn.close()

    # Step 8: Governance report
    total_tasks = 0
    if not dry_run:
        conn2 = sqlite3.connect(DB_PATH)
        c2 = conn2.cursor()
        c2.execute("SELECT COUNT(*) FROM tasks")
        total_tasks = c2.fetchone()[0]
        conn2.close()

    print("\n" + "=" * 60)
    print("  GOVERNANCE REPORT")
    print("=" * 60)
    print(f"  total_tasks              : {total_tasks if not dry_run else '(dry-run)'}")
    print(f"  fixed_task_bindings      : {fixed_bindings}")
    print(f"  created_task_templates   : {created_templates}")
    print(f"  archived_legacy_templates: {archived}")
    print(f"  task10_template_id       : {task10_tid}")
    print(f"  task11_template_id       : {task11_tid}")
    print("=" * 60)


if __name__ == "__main__":
    main()
