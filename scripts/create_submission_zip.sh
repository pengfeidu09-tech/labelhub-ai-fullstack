#!/bin/bash
# LabelHub 提交包清理脚本 (Linux/Mac)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEMP_DIR=$(mktemp -d)/labelhub-submission
ZIP_NAME="labelhub-ai-fullstack-submission.zip"
ZIP_PATH="$PROJECT_ROOT/$ZIP_NAME"

echo "=== LabelHub 提交包清理 ==="
echo "项目根目录: $PROJECT_ROOT"
echo "临时目录: $TEMP_DIR"

mkdir -p "$TEMP_DIR"

# Copy with rsync, excluding sensitive/unnecessary files
rsync -a \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='dist' \
  --exclude='.vite' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='migration_backup*' \
  --exclude='backup' \
  --exclude='exports' \
  --exclude='.env' \
  --exclude='.env.local' \
  --exclude='*.log' \
  --exclude='*.db-journal' \
  --exclude='*.db.bak' \
  --exclude='labelhub_backup_*.db' \
  --exclude='.qoder' \
  --exclude='*.zip' \
  "$PROJECT_ROOT/" "$TEMP_DIR/"

# Create zip
echo "打包中..."
cd "$TEMP_DIR"
rm -f "$ZIP_PATH"
zip -r "$ZIP_PATH" . -q

# Clean up
rm -rf "$(dirname "$TEMP_DIR")"

# Print result
ZIP_SIZE=$(du -h "$ZIP_PATH" | cut -f1)
echo ""
echo "=== 打包完成 ==="
echo "文件: $ZIP_PATH"
echo "大小: $ZIP_SIZE"

# Validation
echo ""
echo "=== 安全检查 ==="
ISSUES=0
for pattern in '.env' 'node_modules' '.git/' 'dist/'; do
  if unzip -l "$ZIP_PATH" 2>/dev/null | grep -q "$pattern"; then
    echo "  发现: $pattern"
    ISSUES=$((ISSUES + 1))
  fi
done

if [ $ISSUES -gt 0 ]; then
  echo "发现 $ISSUES 个问题！"
  exit 1
else
  echo "所有安全检查通过！"
fi
