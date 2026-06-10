import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from app.core.database import SessionLocal
from app.models.task import Task
from app.models.dataset_item import DatasetItem

db = SessionLocal()

# Official tasks
tasks = db.query(Task).filter(Task.source_namespace == "official_raw_v1").all()
for t in tasks:
    cnt = db.query(DatasetItem).filter(DatasetItem.task_id == t.id).count()
    md_len = len(t.annotation_guide_md) if t.annotation_guide_md else 0
    print("Task#%d name=%s items=%d is_default_demo=%s md_chars=%d" % (t.id, t.name, cnt, t.is_default_demo, md_len))

# First qa_quality item
item = db.query(DatasetItem).filter(
    DatasetItem.source_namespace == "official_raw_v1",
    DatasetItem.dataset_type == "qa_quality",
).first()
if item:
    payload = item.raw_payload or {}
    display = item.raw_data_json or {}
    pkeys = sorted(payload.keys())
    dkeys = sorted(display.keys())
    prompt = payload.get("prompt", "")
    print("\nqa_quality first item:")
    print("  official_id=%s" % item.official_id)
    print("  payload_keys=%s" % pkeys)
    print("  display_keys=%s" % dkeys)
    print("  raw_payload_sha256=%s" % (item.raw_payload_sha256 or "")[:16])
    print("  prompt=%s" % str(prompt)[:80])

# First preference item
item2 = db.query(DatasetItem).filter(
    DatasetItem.source_namespace == "official_raw_v1",
    DatasetItem.dataset_type == "preference_compare",
).first()
if item2:
    gold = item2.gold_payload or {}
    pkeys2 = sorted((item2.raw_payload or {}).keys())
    gkeys = sorted(gold.keys())
    print("\npreference_compare first item:")
    print("  official_id=%s" % item2.official_id)
    print("  payload_keys=%s" % pkeys2)
    print("  gold_keys=%s" % gkeys)
    print("  preferred=%s margin=%s safety_flag=%s" % (gold.get("preferred"), gold.get("margin"), gold.get("safety_flag")))

# Counts
old_tasks = db.query(Task).filter(Task.source_namespace == "demo_seed").count()
old_items = db.query(DatasetItem).filter(DatasetItem.source_namespace == "demo_seed").count()
off_tasks = db.query(Task).filter(Task.source_namespace == "official_raw_v1").count()
off_items = db.query(DatasetItem).filter(DatasetItem.source_namespace == "official_raw_v1").count()
total = db.query(DatasetItem).count()
print("\n--- Summary ---")
print("demo_seed: tasks=%d items=%d" % (old_tasks, old_items))
print("official_raw_v1: tasks=%d items=%d" % (off_tasks, off_items))
print("Total items in DB: %d" % total)
db.close()
