#!/usr/bin/env python3
"""
官方原题小样本 AI 预审脚本 — run_ai_review_official.py

用法:
  python backend/scripts/run_ai_review_official.py --namespace official_raw_v1 --task qa_quality_raw --limit 4
  python backend/scripts/run_ai_review_official.py --namespace official_raw_v1 --task preference_compare_raw --limit 3
  python backend/scripts/run_ai_review_official.py --namespace official_raw_v1 --task preference_compare_raw --official-ids P0001 --force --profile official_preference_compare_v1
"""
import argparse
import io
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os
import json
import logging
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="官方原题小样本 AI 预审")
    parser.add_argument("--namespace", required=True, help="数据来源标识")
    parser.add_argument("--task", required=True, help="任务名关键词: qa_quality_raw / preference_compare_raw")
    parser.add_argument("--limit", type=int, default=4, help="最大处理条数")
    parser.add_argument("--official-ids", nargs="*", default=None, help="指定 official_id 列表")
    parser.add_argument("--force", action="store_true", help="强制重跑（忽略已有 success 结果）")
    parser.add_argument("--profile", default=None, help="指定 prompt_profile，如 official_preference_compare_v1")
    parser.add_argument("--mark-old-invalid", action="store_true", help="将旧 Run 标记为 invalid（wrong_prompt_profile）")
    args = parser.parse_args()

    ns = args.namespace
    task_kw = args.task.lower()
    limit = args.limit
    target_ids = args.official_ids
    force = args.force
    profile = args.profile
    mark_old_invalid = args.mark_old_invalid

    from app.core.database import SessionLocal
    from app.models.task import Task
    from app.models.dataset_item import DatasetItem
    from app.models.ai_review_run import AIReviewRun
    from app.services.agent_service import enqueue_ai_review_run, execute_agent_run

    db = SessionLocal()

    # 找到对应的 task
    task = db.query(Task).filter(
        Task.source_namespace == ns,
        Task.name.like("%%%s%%" % task_kw),
    ).first()

    if not task:
        print("[ERROR] 找不到任务: namespace=%s, task=%s" % (ns, task_kw))
        db.close()
        sys.exit(1)

    dataset_type = "qa_quality" if "qa_quality" in task_kw else "preference_compare"
    if not profile:
        profile = "official_%s_v1" % dataset_type

    print("\n%s" % ("=" * 60))
    print("Official AI Pre-review (Small Sample)")
    print("%s" % ("=" * 60))
    print("  namespace:    %s" % ns)
    print("  task:         #%d %s" % (task.id, task.name))
    print("  dataset_type: %s" % dataset_type)
    print("  prompt_profile: %s" % profile)
    print("  force:        %s" % force)
    print("  limit:        %d" % limit)

    # 选择 items
    query = db.query(DatasetItem).filter(
        DatasetItem.task_id == task.id,
        DatasetItem.source_namespace == ns,
    )
    if target_ids:
        query = query.filter(DatasetItem.official_id.in_(target_ids))
    items = query.order_by(DatasetItem.id.asc()).limit(limit).all()

    print("  items found:  %d" % len(items))
    for item in items:
        print("    - %s (item_id=%d)" % (item.official_id, item.id))

    # 如果需要标记旧 Run 为 invalid
    if mark_old_invalid:
        print()
        print("Marking old runs with wrong profile as invalid...")
        for item in items:
            old_runs = db.query(AIReviewRun).filter(
                AIReviewRun.task_id == task.id,
                AIReviewRun.item_id == item.id,
                AIReviewRun.status == "success",
            ).all()
            for old_run in old_runs:
                snap = old_run.input_snapshot_json or {}
                old_profile = snap.get("prompt_profile", "")
                if old_profile != profile:
                    old_run.status = "invalid"
                    old_run.error_message = "wrong_prompt_profile: was '%s', expected '%s'" % (old_profile, profile)
                    old_run.updated_at = datetime.now(timezone.utc)
                    print("  [INVALID] Run#%d for %s (old profile=%s)" % (old_run.id, item.official_id, old_profile))
        db.commit()

    print()
    print("Starting AI review runs...")
    print("-" * 60)

    success_count = 0
    fail_count = 0

    for item in items:
        official_id = item.official_id or str(item.id)
        payload = item.raw_payload or {}
        raw_data = item.raw_data_json or {}

        # 构建 input_snapshot —— 按 dataset_type 分流
        if dataset_type == "qa_quality":
            item_data = {
                "official_id": official_id,
                "dataset_type": "qa_quality",
                "prompt": payload.get("prompt", ""),
                "model_answer": payload.get("model_answer", ""),
                "answer": payload.get("model_answer", ""),
                "reference": payload.get("reference", ""),
                "reference_answer": payload.get("reference", ""),
                "category": payload.get("category", ""),
                "difficulty": payload.get("difficulty", ""),
                "lang": payload.get("lang", "zh"),
                "media_type": payload.get("media_type", ""),
                "expected_dimensions": payload.get("expected_dimensions", []),
            }
        else:
            # preference_compare
            item_data = {
                "official_id": official_id,
                "dataset_type": "preference_compare",
                "prompt": payload.get("prompt", ""),
                "response_a": payload.get("response_a", ""),
                "response_b": payload.get("response_b", ""),
                "model_a": payload.get("model_a", ""),
                "model_b": payload.get("model_b", ""),
                "task_type": payload.get("task_type", ""),
                "lang": payload.get("lang", "zh"),
                "dimensions": payload.get("dimensions", []),
            }

        input_snapshot = {
            "item_data": item_data,
            "result_data": {},
            "official_id": official_id,
            "dataset_type": dataset_type,
            "source_namespace": ns,
            "prompt_profile": profile,
        }

        if force:
            # --force: 删除旧的成功 run 记录，重新创建
            old_runs = db.query(AIReviewRun).filter(
                AIReviewRun.task_id == task.id,
                AIReviewRun.item_id == item.id,
                AIReviewRun.status.in_(["success", "pending", "running"]),
            ).all()
            for old_run in old_runs:
                old_run.status = "superseded"
                old_run.error_message = "superseded by --force re-run with profile=%s" % profile
                old_run.updated_at = datetime.now(timezone.utc)
            db.commit()

        # Enqueue
        run = enqueue_ai_review_run(
            db=db,
            task_id=task.id,
            item_id=item.id,
            annotation_id=None,
            input_snapshot=input_snapshot,
            trigger_type="manual_run",
        )

        if run.status == "success" and not force:
            print("  [SKIP] %s already completed (Run#%d, score=%s)" % (official_id, run.id, run.score))
            success_count += 1
            continue

        # Execute
        print("  [RUN]  %s -> Run#%d ..." % (official_id, run.id), end=" ")
        result = execute_agent_run(db, run)

        if result.status == "success":
            out = result.output_json or {}
            extra = ""
            if dataset_type == "preference_compare":
                extra = ", preferred=%s, margin=%s" % (out.get("preferred", "?"), out.get("margin", "?"))
            print("OK (score=%s, risk=%s, action=%s, fallback=%s%s)" % (
                result.score, result.risk_level, result.suggestion_action,
                "yes" if result.used_fallback else "no", extra))
            success_count += 1
        else:
            print("FAIL (status=%s, error=%s)" % (result.status, result.error_type))
            fail_count += 1

    print()
    print("=" * 60)
    print("Done: %d success, %d failed" % (success_count, fail_count))
    print("=" * 60)
    print()

    db.close()


if __name__ == "__main__":
    main()
