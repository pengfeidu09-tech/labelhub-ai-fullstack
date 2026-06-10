# 提交前清理清单

最终提交前应删除以下文件/目录：

## 前端

- `frontend/node_modules/`
- `frontend/dist/`
- `frontend/.vite/`

## 后端

- `backend/__pycache__/`
- `backend/**/__pycache__/`
- `backend/*.pyc`
- `backend/**/**/*.pyc`
- `backend/.pytest_cache/`

## 数据与导出

- `backend/exports/` — 历史导出文件
- `backend/*.db.bak` — 数据库备份
- `backend/*.sqlite.bak`
- `backend/*.db-journal` — SQLite 临时文件

## 环境与配置

- `.env` — 本地环境变量
- `.env.local`
- `*.log` — 临时日志

## Git

- `.git/` — 如需提交代码而非历史，可删除

## 迁移与备份

- `migration_backup*/` — 数据库迁移备份
- `backup/` — 通用备份目录

## 大型缓存文件

- `frontend/node_modules/.cache/`
- `backend/.pytest_cache/`

## 注意

- `backend/labelhub.db` 保留（包含 demo 数据）
- `backend/data/annotations.json` 保留（demo 数据源）
- `backend/data/` 目录保留
- `docs/` 目录保留
- `README.md` 保留
- 所有源码保留
