#!/usr/bin/env python3
"""
AI Review Run 修复脚本 — repair_ai_review_runs.py

功能:
  1. 标记旧错误 Run 为 invalid:
     - preference_compare 数据但输出为 qa_quality 字段的 Run
     - trigger_type = legacy_unknown 的 Run
     - trigger_type = labeler_assist_* 但被误用于审核详情的 Run
  2. 可选：重跑 P0002/P0003 的正式审核

用法:
  # 仅查看需要修复的 Run（dry-run）
  python backend/scripts/repair_ai_review_runs.py --dry-run

  # 执行修复：标记旧 Run 为 invalid
  python backend/scripts/repair_ai_review_runs.py --mark-invalid

  # 执行修复 + 重跑 P0002/P0003
  python backend/scripts/repair_ai_review_runs.py --mark-invalid --rerun-p0002-p0003
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


def is_qa_quality_output(output_json):
    """检查 output 是否包含 qa_quality 特征字段"""
    if not output_json or not isinstance(output_json, dict):
        return False
    dims = output_json.get("dimension_scores") or output_json.get("dimensions") or {}
    if isinstance(dims, dict):
        qa_keys = {"relevance", "accuracy", "completeness", "safety"}
        if qa_keys & set(dims.keys()):
            return True
    # 检查是否有 overall_score 且没有 preferred
    if "overall_score" in output_json and "preferred" not in output_json:
        return True
    return False


def is_preference_compare_output(output_json):
    """检查 output 是否包含 preference_compare 特征字段"""
    if not output_json or not isinstance(output_json, dict):
        return False
    return "preferred" in output_json or "margin" in output_json


def main():
    parser = argparse.ArgumentParser(description="AI Review Run 修复脚本")
    parser.add_argument("--dry-run", action="store_true", help="仅查看需要修复的 Run")
    parser.add_argument("--mark-invalid", action="store_true", help="标记旧错误 Run 为 invalid")
    parser.add_argument("--rerun-p0002-p0003", action="store_true", help="重跑 P0002/P0003 正式审核")
    args = parser.parse_args()

    dry_run = args.dry_run
    mark_invalid = args.mark_invalid
    rerun = args.rerun_p0002_p0003

    if not dry_run and not mark_invalid and not rerun:
        print("请指定操作: --dry-run (查看) / --mark-invalid (标记) / --rerun-p0002-p0003 (重跑)")
        print("示例: python backend/scripts/repair_ai_review_runs.py --dry-run")
        sys.exit(0)

    from app.core.database import SessionLocal
    from app.models.task import Task
    from app.models.dataset_item import DatasetItem
    from app.models.ai_review_run import AIReviewRun

    db = SessionLocal()

    print("\n" + "=" * 60)
    print("AI Review Run Repair Tool")
    print("=" * 60)

    # ─── Phase 1: 扫描所有 Run，分类需要失效的 ─────────────────────
    all_runs = db.query(AIReviewRun).filter(
        AIReviewRun.status.in_(["success", "pending", "running", "failed"]),
    ).all()

    print("\nTotal active runs: %d" % len(all_runs))

    to_invalidate = []

    for run in all_runs:
        reasons = []
        snap = run.input_snapshot_json or {}
        output = run.output_json or {}
        trigger = run.trigger_type or ""
        dataset_type = snap.get("dataset_type") or (snap.get("item_data") or {}).get("dataset_type")

        # 检查 1: legacy_unknown trigger
        if trigger in ("legacy_unknown", ""):
            reasons.append("legacy/empty trigger_type='%s'" % trigger)

        # 检查 2: preference_compare 数据但输出为 qa_quality
        if dataset_type == "preference_compare" and is_qa_quality_output(output):
            reasons.append("preference_compare item but qa_quality output")

        # 检查 3: labeler_assist trigger 不应出现在正式审核
        if trigger.startswith("labeler_assist"):
            reasons.append("labeler_assist trigger in review queue")

        # 检查 4: auto_on_submit 但没有 dataset_type 在 snapshot 中（旧数据）
        if trigger == "auto_on_submit" and not snap.get("dataset_type") and not snap.get("prompt_profile"):
            # 看看 item 的实际 dataset_type
            item = db.query(DatasetItem).filter(DatasetItem.id == run.item_id).first()
            if item and item.dataset_type == "preference_compare":
                if is_qa_quality_output(output):
                    reasons.append("auto_on_submit for pref_compare without dataset_type in snapshot, output is qa_quality")

        if reasons:
            to_invalidate.append((run, reasons))

    # 打印扫描结果
    print("\nRuns to invalidate: %d" % len(to_invalidate))
    for run, reasons in to_invalidate:
        snap = run.input_snapshot_json or {}
        print("  Run#%d | task=%d item=%d | trigger=%s | status=%s | reasons: %s" % (
            run.id, run.task_id, run.item_id,
            run.trigger_type or "(empty)",
            run.status,
            "; ".join(reasons),
        ))

    # ─── Phase 2: 执行标记 ─────────────────────────────────────────
    if mark_invalid and not dry_run:
        print("\nMarking %d runs as invalid..." % len(to_invalidate))
        for run, reasons in to_invalidate:
            run.status = "invalid"
            run.error_message = "repaired: %s" % "; ".join(reasons)
            run.updated_at = datetime.now(timezone.utc)
        db.commit()
        print("Done. %d runs marked as invalid." % len(to_invalidate))
    elif dry_run:
        print("\n[DRY RUN] Would mark %d runs as invalid." % len(to_invalidate))

    # ─── Phase 3: 重跑 P0002/P0003 ─────────────────────────────────
    if rerun and not dry_run:
        from app.services.agent_service import enqueue_ai_review_run, execute_agent_run

        # 找到 preference_compare 任务
        task = db.query(Task).filter(
            Task.name.like("%preference_compare%"),
        ).first()

        if not task:
            print("[ERROR] 找不到 preference_compare 任务")
        else:
            print("\nRe-running P0002/P0003 for task #%d (%s)..." % (task.id, task.name))

            target_ids = ["P0002", "P0003"]
            items = db.query(DatasetItem).filter(
                DatasetItem.task_id == task.id,
                DatasetItem.official_id.in_(target_ids),
            ).all()

            if not items:
                print("[WARN] 找不到 P0002/P0003 items")
            else:
                for item in items:
                    official_id = item.official_id
                    payload = item.raw_payload or {}
                    raw_data = item.raw_data_json or {}

                    item_data = {
                        "official_id": official_id,
                        "dataset_type": "preference_compare",
                        "prompt": payload.get("prompt") or raw_data.get("prompt", ""),
                        "response_a": payload.get("response_a") or raw_data.get("response_a", ""),
                        "response_b": payload.get("response_b") or raw_data.get("response_b", ""),
                        "model_a": payload.get("model_a") or raw_data.get("model_a", ""),
                        "model_b": payload.get("model_b") or raw_data.get("model_b", ""),
                        "task_type": payload.get("task_type") or raw_data.get("task_type", ""),
                        "lang": payload.get("lang") or raw_data.get("lang", "zh"),
                    }

                    input_snapshot = {
                        "item_data": item_data,
                        "result_data": {},
                        "human_result": {},
                        "official_id": official_id,
                        "dataset_type": "preference_compare",
                        "prompt_profile": "ai_review_preference_compare_v1",
                    }

                    # 先 supersede 旧的 manual_run
                    old_runs = db.query(AIReviewRun).filter(
                        AIReviewRun.task_id == task.id,
                        AIReviewRun.item_id == item.id,
                        AIReviewRun.trigger_type == "manual_run",
                        AIReviewRun.status.in_(["success", "pending", "running"]),
                    ).all()
                    for old_run in old_runs:
                        old_run.status = "superseded"
                        old_run.error_message = "superseded by repair script re-run"
                        old_run.updated_at = datetime.now(timezone.utc)
                    db.commit()

                    run = enqueue_ai_review_run(
                        db=db,
                        task_id=task.id,
                        item_id=item.id,
                        annotation_id=None,
                        input_snapshot=input_snapshot,
                        trigger_type="manual_review_run",
                    )

                    if run.status == "success":
                        print("  [SKIP] %s already completed (Run#%d)" % (official_id, run.id))
                        continue

                    print("  [RUN]  %s -> Run#%d ..." % (official_id, run.id), end=" ")
                    result = execute_agent_run(db, run)

                    if result.status == "success":
                        out = result.output_json or {}
                        print("OK (score=%s, preferred=%s, margin=%s)" % (
                            result.score,
                            out.get("preferred", "?"),
                            out.get("margin", "?"),
                        ))
                    else:
                        print("FAIL (status=%s, error=%s)" % (result.status, result.error_type))

    elif rerun and dry_run:
        print("\n[DRY RUN] Would re-run P0002/P0003 with ai_review_preference_compare_v1 profile.")

    print("\n" + "=" * 60)
    print("Repair complete.")
    print("=" * 60 + "\n")

    db.close()


if __name__ == "__main__":
    main()
