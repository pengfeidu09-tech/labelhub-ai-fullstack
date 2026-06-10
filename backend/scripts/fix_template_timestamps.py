#!/usr/bin/env python3
"""
fix_template_timestamps.py
==========================
修复 template_schemas 表中 created_at / updated_at 为 NULL 的脏数据。

用法:
  # 先 dry-run 查看受影响行
  python scripts/fix_template_timestamps.py --dry-run

  # 执行修复
  python scripts/fix_template_timestamps.py

必须在 backend/ 目录下运行（与 labelhub.db 同级）。
"""
import argparse
import sqlite3
import os
from datetime import datetime, timezone

FALLBACK_TS = "2024-01-01 00:00:00"
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "labelhub.db")


def main():
    parser = argparse.ArgumentParser(description="修复模板时间戳脏数据")
    parser.add_argument("--dry-run", action="store_true", help="只查看不修改")
    args = parser.parse_args()

    db_path = os.path.abspath(DB_PATH)
    if not os.path.exists(db_path):
        print(f"[ERROR] 数据库不存在: {db_path}")
        print("请确保在 backend/ 目录下运行本脚本。")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 检查表是否存在
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='template_schemas'")
    if not cur.fetchone():
        print("[WARN] template_schemas 表不存在，无需修复。")
        conn.close()
        return

    # 查询时间戳为 NULL 的行
    cur.execute("""
        SELECT id, name, dataset_type, created_at, updated_at
        FROM template_schemas
        WHERE created_at IS NULL OR updated_at IS NULL
        ORDER BY id
    """)
    dirty_rows = cur.fetchall()

    if not dirty_rows:
        print("[OK] 没有发现时间戳为 NULL 的模板记录，无需修复。")
        conn.close()
        return

    print(f"[INFO] 发现 {len(dirty_rows)} 条时间戳为 NULL 的记录：")
    print(f"{'ID':<6} {'Name':<30} {'Type':<22} {'created_at':<24} {'updated_at':<24}")
    print("-" * 110)
    for row in dirty_rows:
        print(f"{row['id']:<6} {(row['name'] or ''):<30} {(row['dataset_type'] or ''):<22} "
              f"{(row['created_at'] or 'NULL'):<24} {(row['updated_at'] or 'NULL'):<24}")

    if args.dry_run:
        print(f"\n[DRY-RUN] 共 {len(dirty_rows)} 条记录将被修复（created_at / updated_at → {FALLBACK_TS}）")
        conn.close()
        return

    # 执行修复
    now_str = FALLBACK_TS
    updated = 0
    for row in dirty_rows:
        new_created = row["created_at"] or now_str
        new_updated = row["updated_at"] or new_created
        cur.execute(
            "UPDATE template_schemas SET created_at = ?, updated_at = ? WHERE id = ?",
            (new_created, new_updated, row["id"]),
        )
        updated += 1

    conn.commit()
    print(f"\n[DONE] 已修复 {updated} 条记录。")

    # 验证
    cur.execute("""
        SELECT id, name, created_at, updated_at
        FROM template_schemas
        WHERE created_at IS NULL OR updated_at IS NULL
    """)
    remaining = cur.fetchall()
    if remaining:
        print(f"[WARN] 仍有 {len(remaining)} 条记录时间戳为 NULL！")
    else:
        print("[OK] 验证通过：所有模板记录时间戳均非 NULL。")

    conn.close()


if __name__ == "__main__":
    main()
