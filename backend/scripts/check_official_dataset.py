#!/usr/bin/env python3
"""
官方数据集健康检查脚本 — check_official_dataset.py

用法:
  python backend/scripts/check_official_dataset.py --namespace official_raw_v1
"""
import argparse
import io
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def main():
    parser = argparse.ArgumentParser(description="LabelHub 官方数据集健康检查")
    parser.add_argument("--namespace", default="official_raw_v1", help="数据来源标识")
    args = parser.parse_args()
    ns = args.namespace

    from app.core.database import SessionLocal
    from app.models.task import Task
    from app.models.dataset_item import DatasetItem

    db = SessionLocal()
    errors = []
    warnings = []

    print()
    print("=" * 60)
    print("Official Dataset Health Check")
    print("=" * 60)

    # 1. Namespace 是否存在
    tasks = db.query(Task).filter(Task.source_namespace == ns).all()
    if not tasks:
        errors.append("namespace '%s' 不存在任何 Task" % ns)
    print("- namespace: %s" % ns)
    print("- tasks found: %d" % len(tasks))

    # 2 & 3. qa_quality_raw / preference_compare_raw
    qa_task = db.query(Task).filter(
        Task.source_namespace == ns,
        Task.name.like("%qa_quality%"),
    ).first()
    pc_task = db.query(Task).filter(
        Task.source_namespace == ns,
        Task.name.like("%preference_compare%"),
    ).first()

    qa_exists = qa_task is not None
    pc_exists = pc_task is not None
    print("- qa_quality_raw task: %s (#%s)" % ("YES" if qa_exists else "NO", qa_task.id if qa_task else "-"))
    print("- preference_compare_raw task: %s (#%s)" % ("YES" if pc_exists else "NO", pc_task.id if pc_task else "-"))

    if not qa_exists:
        errors.append("qa_quality_raw 任务不存在")
    if not pc_exists:
        errors.append("preference_compare_raw 任务不存在")

    # 4 & 5. Item 数量
    qa_items = db.query(DatasetItem).filter(
        DatasetItem.source_namespace == ns,
        DatasetItem.dataset_type == "qa_quality",
    ).all() if qa_exists else []

    pc_items = db.query(DatasetItem).filter(
        DatasetItem.source_namespace == ns,
        DatasetItem.dataset_type == "preference_compare",
    ).all() if pc_exists else []

    qa_count = len(qa_items)
    pc_count = len(pc_items)
    qa_ok = qa_count == 30
    pc_ok = pc_count == 12

    print("- qa_quality count: %d / expected 30 %s" % (qa_count, "OK" if qa_ok else "MISMATCH"))
    print("- preference_compare count: %d / expected 12 %s" % (pc_count, "OK" if pc_ok else "MISMATCH"))

    if not qa_ok:
        errors.append("qa_quality 数量 %d != 30" % qa_count)
    if not pc_ok:
        errors.append("preference_compare 数量 %d != 12" % pc_count)

    # 6. 逐条字段完整性检查
    all_items = qa_items + pc_items
    required_common = ["official_id", "dataset_type", "source_namespace", "raw_payload",
                       "raw_payload_sha256", "source_file", "is_official_raw"]
    missing_fields = []
    empty_prompts = []
    gold_leak = []

    for item in all_items:
        oid = item.official_id or item.id
        # 必填字段
        for field in required_common:
            val = getattr(item, field, None)
            if val is None or val == "" or val is False:
                if field == "is_official_raw" and val is False:
                    missing_fields.append((oid, field, "False (expected True)"))
                elif val is None or val == "":
                    missing_fields.append((oid, field, "NULL/empty"))

        # source_file check
        if item.source_file != "datasets.zip":
            missing_fields.append((oid, "source_file", "got '%s' expected 'datasets.zip'" % item.source_file))

        # is_official_raw check
        if item.is_official_raw is not True:
            missing_fields.append((oid, "is_official_raw", "not True"))

        # prompt 非空检查
        payload = item.raw_payload or {}
        if item.dataset_type == "qa_quality":
            for key in ["prompt", "model_answer", "reference"]:
                if not payload.get(key):
                    empty_prompts.append((oid, item.dataset_type, key))
        elif item.dataset_type == "preference_compare":
            for key in ["prompt", "response_a", "response_b"]:
                if not payload.get(key):
                    empty_prompts.append((oid, item.dataset_type, key))
            # gold leak 检查: gold 字段不应出现在 raw_data_json (展示给标注员的)
            display = item.raw_data_json or {}
            gold_keys = ["preferred", "margin", "safety_flag", "annotator_note"]
            for gk in gold_keys:
                if gk in display:
                    gold_leak.append((oid, gk))

    raw_payload_ok = len(missing_fields) == 0
    gold_hidden = len(gold_leak) == 0

    print("- raw_payload complete: %s" % ("YES" if raw_payload_ok else "NO (%d issues)" % len(missing_fields)))
    print("- gold hidden from labeler: %s" % ("YES" if gold_hidden else "LEAK DETECTED (%d)" % len(gold_leak)))
    print("- empty prompts: %d" % len(empty_prompts))

    if missing_fields:
        print("\n  Missing fields detail:")
        for oid, field, reason in missing_fields[:10]:
            print("    official_id=%s field=%s reason=%s" % (oid, field, reason))
        if len(missing_fields) > 10:
            print("    ... and %d more" % (len(missing_fields) - 10))

    if empty_prompts:
        print("\n  Empty prompt fields:")
        for oid, dtype, key in empty_prompts[:10]:
            print("    official_id=%s type=%s field=%s" % (oid, dtype, key))

    if gold_leak:
        print("\n  Gold leak detected:")
        for oid, key in gold_leak[:10]:
            print("    official_id=%s leaked_key=%s" % (oid, key))

    # 7. 旧目录混入检查
    legacy_items = db.query(DatasetItem).filter(
        DatasetItem.source_namespace == ns,
        DatasetItem.source_file != "datasets.zip",
    ).count()
    print("- legacy items mixed in: %d %s" % (legacy_items, "(OK)" if legacy_items == 0 else "PROBLEM"))
    if legacy_items > 0:
        errors.append("发现 %d 条非 datasets.zip 来源的 official_raw_v1 数据" % legacy_items)

    # 8. Default demo tasks switched
    demo_tasks = db.query(Task).filter(
        Task.source_namespace == ns,
        Task.is_default_demo == True,
    ).count()
    old_demo = db.query(Task).filter(
        Task.source_namespace == "demo_seed",
        Task.is_default_demo == True,
    ).count()
    demo_switched = demo_tasks > 0 and old_demo == 0
    print("- default demo tasks switched: %s (official=%d, old_demo=%d)" % (
        "YES" if demo_switched else "NO", demo_tasks, old_demo))

    # 9. Legacy tasks marked
    legacy_unmarked = db.query(Task).filter(
        Task.source_namespace.is_(None),
    ).count()
    legacy_marked = db.query(Task).filter(
        Task.source_namespace == "demo_seed",
    ).count()
    legacy_ok = legacy_unmarked == 0 and legacy_marked > 0
    print("- legacy tasks hidden or marked: %s (unmarked=%d, demo_seed=%d)" % (
        "YES" if legacy_ok else "NO", legacy_unmarked, legacy_marked))

    # Summary
    print()
    if errors:
        print("RESULT: FAIL (%d errors)" % len(errors))
        for e in errors:
            print("  [ERROR] %s" % e)
    elif warnings:
        print("RESULT: WARN (%d warnings)" % len(warnings))
        for w in warnings:
            print("  [WARN] %s" % w)
    else:
        print("RESULT: ALL CHECKS PASSED")

    print("=" * 60)
    print()

    db.close()
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
