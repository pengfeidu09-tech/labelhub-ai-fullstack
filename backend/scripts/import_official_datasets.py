#!/usr/bin/env python3
"""
官方数据集导入脚本 — import_official_datasets.py

用法:
  # 从项目根目录执行
  python backend/scripts/import_official_datasets.py --zip ./datasets.zip --mode create-new-official --source-namespace official_raw_v1

  # 从 backend 目录执行
  cd backend
  python scripts/import_official_datasets.py --zip ../datasets.zip --mode create-new-official --source-namespace official_raw_v1
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 路径 & sys.path 设置
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)

# 确保 backend 在 sys.path 中
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
IGNORE_PREFIXES = ("__MACOSX/", "__MACOSX\\", "MACOSX/", "MACOSX\\")
IGNORE_NAMES = {".DS_Store", ".~qa_quality.xlsx"}
IGNORE_PATTERNS = [re.compile(r"/\._"), re.compile(r"^_\._"), re.compile(r"/\.\~")]

EXPECTED_QA_COUNT = 30
EXPECTED_PC_COUNT = 12

# JSON 路径优先级
QA_JSON_PATHS = [
    "datasets/qa_quality/json/qa_quality.json",
    "datasets/qa_quality/jsonl/qa_quality.jsonl",
]
PC_JSON_PATHS = [
    "datasets/preference_compare/json/preference_compare.json",
    "datasets/preference_compare/jsonl/preference_compare.jsonl",
]

# MD 文件按目录识别（文件名可能乱码）
QA_MD_DIR = "datasets/qa_quality/"
PC_MD_DIR = "datasets/preference_compare/"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def should_ignore(name: str) -> bool:
    basename = os.path.basename(name)
    if basename in IGNORE_NAMES:
        return True
    if basename.startswith("._"):
        return True
    for prefix in IGNORE_PREFIXES:
        if name.startswith(prefix):
            return True
    return False


def resolve_zip_path(user_path: Optional[str]) -> str:
    """解析 ZIP 文件路径，优先用户指定路径，然后自动探测。"""
    if user_path:
        p = os.path.abspath(user_path)
        if not os.path.isfile(p):
            print(f"[ERROR] 指定的 ZIP 文件不存在: {p}")
            sys.exit(1)
        return p

    candidates = [
        os.path.join(PROJECT_ROOT, "datasets.zip"),
        os.path.join(BACKEND_DIR, "datasets.zip"),
        os.path.join(BACKEND_DIR, "..", "datasets.zip"),
        os.path.join(os.getcwd(), "datasets.zip"),
    ]
    for c in candidates:
        c = os.path.normpath(os.path.abspath(c))
        if os.path.isfile(c):
            return c

    print("[ERROR] 找不到 datasets.zip，请通过 --zip 参数指定路径。")
    print("  尝试过的路径:")
    for c in candidates:
        print(f"    - {c}")
    sys.exit(1)


def read_json_from_zip(zf: zipfile.ZipFile, paths: List[str]) -> Tuple[Optional[List], str]:
    """按优先级尝试从 ZIP 读取 JSON 数据，返回 (items_list, used_path)。"""
    for p in paths:
        try:
            data = zf.read(p)
            text = data.decode("utf-8")
            if p.endswith(".jsonl"):
                items = [json.loads(line) for line in text.strip().splitlines() if line.strip()]
            else:
                items = json.loads(text)
            if isinstance(items, list):
                return items, p
        except KeyError:
            continue
    return None, ""


def read_md_from_zip(zf: zipfile.ZipFile, dir_prefix: str) -> Optional[str]:
    """从 ZIP 中按目录前缀读取 .md 文件。"""
    for name in zf.namelist():
        if name.startswith(dir_prefix) and name.endswith(".md") and not should_ignore(name):
            try:
                data = zf.read(name)
                return data.decode("utf-8")
            except Exception:
                continue
    return None


# ---------------------------------------------------------------------------
# 数据库操作
# ---------------------------------------------------------------------------
def ensure_columns(engine):
    """通过 ALTER TABLE 确保新列存在（幂等）。"""
    from sqlalchemy import text, inspect

    inspector = inspect(engine)

    # DatasetItem 新列
    di_existing = {col["name"] for col in inspector.get_columns("dataset_items")}
    di_new_cols = {
        "source_namespace": "VARCHAR(64)",
        "source_file": "VARCHAR(256)",
        "source_zip_sha256": "VARCHAR(64)",
        "raw_payload": "JSON",
        "raw_payload_sha256": "VARCHAR(64)",
        "is_official_raw": "BOOLEAN DEFAULT 0",
        "gold_payload": "JSON",
        "official_id": "VARCHAR(64)",
    }
    with engine.connect() as conn:
        for col_name, col_type in di_new_cols.items():
            if col_name not in di_existing:
                sql = f"ALTER TABLE dataset_items ADD COLUMN {col_name} {col_type}"
                conn.execute(text(sql))
                print(f"  [DDL] dataset_items.{col_name} added")
        conn.commit()

    # Task 新列
    task_existing = {col["name"] for col in inspector.get_columns("tasks")}
    task_new_cols = {
        "source_namespace": "VARCHAR(64)",
        "is_official_raw": "BOOLEAN DEFAULT 0",
        "is_default_demo": "BOOLEAN DEFAULT 0",
        "annotation_guide_md": "TEXT",
    }
    with engine.connect() as conn:
        for col_name, col_type in task_new_cols.items():
            if col_name not in task_existing:
                sql = f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type}"
                conn.execute(text(sql))
                print(f"  [DDL] tasks.{col_name} added")
        conn.commit()


def mark_old_data(db, source_ns: str):
    """标记旧任务和 items 为 demo_seed。"""
    from app.models.task import Task
    from app.models.dataset_item import DatasetItem

    # 标记旧 tasks
    old_tasks = db.query(Task).filter(Task.source_namespace.is_(None)).all()
    for t in old_tasks:
        t.source_namespace = "demo_seed"
        t.is_official_raw = False
        t.is_default_demo = False
    if old_tasks:
        print(f"  [标记] {len(old_tasks)} 个旧任务 → demo_seed")

    # 标记旧 items
    old_items_count = db.query(DatasetItem).filter(DatasetItem.source_namespace.is_(None)).update(
        {"source_namespace": "demo_seed", "is_official_raw": False},
        synchronize_session="fetch"
    )
    if old_items_count:
        print(f"  [标记] {old_items_count} 个旧 items → demo_seed")

    db.commit()


def upsert_task(db, name: str, dataset_type: str, description: str,
                source_namespace: str, annotation_guide_md: Optional[str],
                template_id: Optional[int]) -> Any:
    """创建或更新官方原题任务（不覆盖已有同 source_namespace 任务）。"""
    from app.models.task import Task

    existing = db.query(Task).filter(
        Task.source_namespace == source_namespace,
        Task.name == name,
    ).first()

    if existing:
        existing.description = description
        existing.annotation_guide_md = annotation_guide_md
        existing.is_official_raw = True
        existing.is_default_demo = True
        if template_id:
            existing.template_id = template_id
        db.commit()
        db.refresh(existing)
        print(f"  [更新] Task#{existing.id} {name}")
        return existing

    task = Task(
        name=name,
        description=description,
        template_id=template_id,
        status="published",
        ai_review_enabled=True,
        source_namespace=source_namespace,
        is_official_raw=True,
        is_default_demo=True,
        annotation_guide_md=annotation_guide_md,
        created_by=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    print(f"  [创建] Task#{task.id} {name}")
    return task


def upsert_item(db, task_id: int, item_data: Dict, dataset_type: str,
                source_namespace: str, source_file: str, zip_sha256: str,
                gold_payload: Optional[Dict] = None) -> Tuple[str, bool]:
    """Upsert 单条 DatasetItem，返回 (action, is_new)。action = 'created' | 'updated'。"""
    from app.models.dataset_item import DatasetItem

    official_id = item_data.get("id", "")
    raw_payload_sha = sha256_json(item_data)

    existing = db.query(DatasetItem).filter(
        DatasetItem.source_namespace == source_namespace,
        DatasetItem.dataset_type == dataset_type,
        DatasetItem.official_id == official_id,
    ).first()

    # 构建展示字段
    if dataset_type == "qa_quality":
        raw_display = {
            "prompt": item_data.get("prompt", ""),
            "model_answer": item_data.get("model_answer", ""),
            "reference": item_data.get("reference", ""),
            "category": item_data.get("category", ""),
            "difficulty": item_data.get("difficulty", ""),
            "media_type": item_data.get("media_type", ""),
            "media_url": item_data.get("media_url", ""),
            "content_markdown": item_data.get("content_markdown", ""),
            "tags": item_data.get("tags", []),
            "lang": item_data.get("lang", "zh"),
            "source": item_data.get("source", ""),
            "expected_dimensions": item_data.get("expected_dimensions", []),
            "official_id": item_data.get("id", ""),
        }
        hidden_ref = {
            "reference": item_data.get("reference", ""),
            "expected_dimensions": item_data.get("expected_dimensions", []),
            "tags": item_data.get("tags", []),
            "source": item_data.get("source", ""),
        }
    elif dataset_type == "preference_compare":
        raw_display = {
            "prompt": item_data.get("prompt", ""),
            "response_a": item_data.get("response_a", ""),
            "model_a": item_data.get("model_a", ""),
            "response_b": item_data.get("response_b", ""),
            "model_b": item_data.get("model_b", ""),
            "task_type": item_data.get("task_type", ""),
            "lang": item_data.get("lang", "zh"),
            "dimensions": item_data.get("dimensions", []),
            "official_id": item_data.get("id", ""),
        }
        hidden_ref = gold_payload or {}
    else:
        raw_display = item_data
        hidden_ref = {}

    if existing:
        # 更新展示字段和 raw_payload，不碰 status / annotation_phase / submission 等
        existing.raw_data_json = raw_display
        existing.raw_payload = item_data
        existing.raw_payload_sha256 = raw_payload_sha
        existing.hidden_reference_json = hidden_ref
        existing.gold_payload = gold_payload
        existing.source_file = source_file
        existing.source_zip_sha256 = zip_sha256
        existing.external_id = official_id
        existing.item_key = f"{source_namespace}:{dataset_type}:{official_id}"
        if dataset_type == "qa_quality":
            existing.category = item_data.get("category")
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        return "updated", False

    item = DatasetItem(
        task_id=task_id,
        external_id=official_id,
        dataset_type=dataset_type,
        raw_data_json=raw_display,
        hidden_reference_json=hidden_ref,
        status="unclaimed",
        source_namespace=source_namespace,
        source_file=source_file,
        source_zip_sha256=zip_sha256,
        raw_payload=item_data,
        raw_payload_sha256=raw_payload_sha,
        is_official_raw=True,
        gold_payload=gold_payload,
        official_id=official_id,
        item_key=f"{source_namespace}:{dataset_type}:{official_id}",
        category=item_data.get("category") if dataset_type == "qa_quality" else None,
        annotation_phase=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(item)
    db.commit()
    return "created", True


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    # Force UTF-8 output on Windows
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="LabelHub 官方数据集导入脚本")
    parser.add_argument("--zip", dest="zip_path", default=None, help="datasets.zip 路径")
    parser.add_argument("--mode", required=True, choices=["create-new-official"], help="导入模式")
    parser.add_argument("--source-namespace", required=True, help="数据来源标识")
    parser.add_argument("--allow-extracted", action="store_true", help="允许读取解压目录（本次不使用）")
    parser.add_argument("--reset-official-results", action="store_true", help="重置人工/AI 结果（本次不使用）")
    args = parser.parse_args()

    source_ns = args.source_namespace

    # 1. 解析 ZIP 路径
    zip_path = resolve_zip_path(args.zip_path)
    zip_sha256 = sha256_file(zip_path)
    print(f"\n{'='*60}")
    print(f"LabelHub 官方数据集导入")
    print(f"{'='*60}")
    print(f"  zip_path:          {zip_path}")
    print(f"  zip_sha256:        {zip_sha256}")
    print(f"  source_namespace:  {source_ns}")
    print(f"  mode:              {args.mode}")
    print()

    # 2. 打开 ZIP 并解析
    zf = zipfile.ZipFile(zip_path, "r")
    all_names = zf.namelist()
    ignored = [n for n in all_names if should_ignore(n)]
    valid = [n for n in all_names if not should_ignore(n)]
    print(f"  忽略文件数:        {len(ignored)}")

    # 3. 读取 JSON 数据
    qa_items, qa_path = read_json_from_zip(zf, QA_JSON_PATHS)
    pc_items, pc_path = read_json_from_zip(zf, PC_JSON_PATHS)

    if qa_items is None:
        print("[ERROR] 找不到 qa_quality JSON 数据")
        sys.exit(1)
    if pc_items is None:
        print("[ERROR] 找不到 preference_compare JSON 数据")
        sys.exit(1)

    print(f"  qa_quality_json:   {qa_path}")
    print(f"  qa_quality_count:  {len(qa_items)}")
    print(f"  preference_json:   {pc_path}")
    print(f"  preference_count:  {len(pc_items)}")

    # 4. 读取标注要求 MD
    qa_md = read_md_from_zip(zf, QA_MD_DIR)
    pc_md = read_md_from_zip(zf, PC_MD_DIR)
    print(f"  qa_quality_md:     {'OK' if qa_md else 'MISSING'} ({len(qa_md or '')} chars)")
    print(f"  preference_md:     {'OK' if pc_md else 'MISSING'} ({len(pc_md or '')} chars)")

    # 5. 数量校验
    count_ok = True
    if len(qa_items) != EXPECTED_QA_COUNT:
        print(f"\n  ⚠ WARNING: qa_quality 数量 {len(qa_items)} ≠ 预期 {EXPECTED_QA_COUNT}")
        count_ok = False
    if len(pc_items) != EXPECTED_PC_COUNT:
        print(f"\n  ⚠ WARNING: preference_compare 数量 {len(pc_items)} ≠ 预期 {EXPECTED_PC_COUNT}")
        count_ok = False

    if not count_ok:
        print("\n  数量不匹配，等待 3 秒后继续... (Ctrl+C 取消)")
        try:
            time.sleep(3)
        except KeyboardInterrupt:
            print("\n  [取消] 用户中断")
            sys.exit(0)

    print(f"\n{'─'*60}")
    print("开始导入...")

    # 6. 初始化数据库
    from app.core.database import engine, SessionLocal
    from app.core.database import Base

    # 确保表存在
    Base.metadata.create_all(bind=engine)

    # 确保新列存在
    print("\n[DDL] 检查并添加新列...")
    ensure_columns(engine)

    db = SessionLocal()

    try:
        # 7. 标记旧数据
        print("\n[标记] 标记旧数据为 demo_seed...")
        mark_old_data(db, source_ns)

        # 8. 查找或创建模板
        from app.models.template_schema import TemplateSchema
        qa_template = db.query(TemplateSchema).filter(
            TemplateSchema.dataset_type == "qa_quality",
            TemplateSchema.is_active == True,
        ).order_by(TemplateSchema.id.desc()).first()

        pc_template = db.query(TemplateSchema).filter(
            TemplateSchema.dataset_type == "preference_compare",
            TemplateSchema.is_active == True,
        ).order_by(TemplateSchema.id.desc()).first()

        # 9. 创建 / 更新任务
        print("\n[任务] 创建或更新官方原题任务...")

        qa_desc = f"官方原题 · 问答质量标注 (qa_quality)\n来源: datasets.zip ({source_ns})\n共 {len(qa_items)} 条"
        if qa_md:
            qa_desc += f"\n\n{qa_md[:500]}"

        pc_desc = f"官方原题 · 偏好对比标注 (preference_compare)\n来源: datasets.zip ({source_ns})\n共 {len(pc_items)} 条"
        if pc_md:
            pc_desc += f"\n\n{pc_md[:500]}"

        qa_task = upsert_task(
            db,
            name=f"官方原题·问答质量标注 (qa_quality_raw)",
            dataset_type="qa_quality",
            description=qa_desc,
            source_namespace=source_ns,
            annotation_guide_md=qa_md,
            template_id=qa_template.id if qa_template else None,
        )

        pc_task = upsert_task(
            db,
            name=f"官方原题·偏好对比标注 (preference_compare_raw)",
            dataset_type="preference_compare",
            description=pc_desc,
            source_namespace=source_ns,
            annotation_guide_md=pc_md,
            template_id=pc_template.id if pc_template else None,
        )

        # 10. 导入 items
        print(f"\n[导入] qa_quality → Task#{qa_task.id} ...")
        qa_created = 0
        qa_updated = 0
        for item_data in qa_items:
            action, is_new = upsert_item(
                db, qa_task.id, item_data, "qa_quality",
                source_ns, "datasets.zip", zip_sha256,
            )
            if is_new:
                qa_created += 1
            else:
                qa_updated += 1

        print(f"  qa_quality: {qa_created} 新建, {qa_updated} 更新")

        print(f"\n[导入] preference_compare → Task#{pc_task.id} ...")
        pc_created = 0
        pc_updated = 0
        for item_data in pc_items:
            # 提取 gold_payload
            gold = {
                "preferred": item_data.get("preferred"),
                "margin": item_data.get("margin"),
                "dimensions": item_data.get("dimensions"),
                "safety_flag": item_data.get("safety_flag"),
                "annotator_note": item_data.get("annotator_note"),
            }
            action, is_new = upsert_item(
                db, pc_task.id, item_data, "preference_compare",
                source_ns, "datasets.zip", zip_sha256,
                gold_payload=gold,
            )
            if is_new:
                pc_created += 1
            else:
                pc_updated += 1

        print(f"  preference_compare: {pc_created} 新建, {pc_updated} 更新")

        # 11. 旧任务 is_default_demo = False
        from app.models.task import Task
        db.query(Task).filter(
            Task.source_namespace != source_ns,
            Task.source_namespace.isnot(None),
        ).update({"is_default_demo": False}, synchronize_session="fetch")
        db.commit()

        zf.close()

        # 12. 输出结果
        total_new = qa_created + pc_created
        total_updated = qa_updated + pc_updated
        print(f"\n{'='*60}")
        print(f"导入完成!")
        print(f"{'='*60}")
        print(f"  导入命令:           python backend/scripts/import_official_datasets.py --zip {zip_path} --mode create-new-official --source-namespace {source_ns}")
        print(f"  ZIP 路径:           {zip_path}")
        print(f"  ZIP SHA-256:        {zip_sha256}")
        print(f"  qa_quality:         {len(qa_items)} 条 (预期 {EXPECTED_QA_COUNT}) {'✓' if len(qa_items)==EXPECTED_QA_COUNT else '⚠'}")
        print(f"  preference_compare: {len(pc_items)} 条 (预期 {EXPECTED_PC_COUNT}) {'✓' if len(pc_items)==EXPECTED_PC_COUNT else '⚠'}")
        print(f"  qa_quality Task:    #{qa_task.id}")
        print(f"  preference Task:    #{pc_task.id}")
        print(f"  新建 items:         {total_new}")
        print(f"  更新 items:         {total_updated}")
        print(f"  忽略文件数:         {len(ignored)}")
        print(f"  旧任务标记:         demo_seed (Task#1~#9)")
        print(f"  默认演示入口:       已切换到 {source_ns}")
        print()

    except Exception as e:
        db.rollback()
        print(f"\n[ERROR] 导入失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
