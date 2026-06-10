# LabelHub 部署指南

---

## 1. 环境要求

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| Node.js | >= 16 | 前端运行环境 |
| Python | >= 3.10 | 后端运行环境 |
| npm / pnpm | - | 前端包管理器 |
| SQLite | - | 随 Python 内置，无需额外安装 |
| Git | - | 版本控制 |

---

## 2. 后端启动

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- 后端运行地址：http://localhost:8000
- `--reload` 参数启用热重载，开发时修改代码自动生效
- Swagger 文档地址：http://localhost:8000/docs

---

## 3. 前端启动

```bash
cd frontend
npm install
npm run dev
```

- 前端默认运行地址：http://localhost:3000
- 若 3000 端口被占用，Vite 会自动尝试 3001、3002 等端口
- 前端通过 Vite proxy 将 `/api` 请求转发至后端 http://127.0.0.1:8000

---

## 4. 数据初始化

- 后端首次启动时会自动创建 SQLite 数据库文件
- 可通过调用 `/api/seed-demo` 接口注入 Demo 数据
- 标注数据存储在 `annotations.json` 文件中，与数据库配合使用

---

## 5. 常见问题

### 端口被占用

- 后端：使用 `uvicorn` 的 `--port` 参数指定其他端口，如 `--port 8001`
- 前端：在 `vite.config.ts` 中修改 `server.port` 配置，或直接使用 Vite 自动分配的端口

### npm install 失败

- 确认 Node.js 版本 >= 16：`node -v`
- 清除缓存后重试：`npm cache clean --force`
- 使用国内镜像源：`npm install --registry=https://registry.npmmirror.com`

### Python 依赖缺失

- 确认 Python 版本 >= 3.10：`python --version`
- 重新安装依赖：`pip install -r requirements.txt`
- 如有网络问题，可使用镜像源：`pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

### 后端 API 不通

- 确认后端服务已启动：访问 http://localhost:8000/api/health
- 检查前端代理配置：确认 `vite.config.ts` 中 `proxy` 将 `/api` 转发至 `http://127.0.0.1:8000`
- 确认后端监听地址与前端代理目标一致

### 前端页面空白

- 打开浏览器开发者工具 (F12) 查看控制台错误信息
- 确认后端服务正在运行，前端 API 请求能正常响应
- 检查前端构建是否有报错：`npm run build`

### Demo 数据不存在

- 调用 `/api/seed-demo` 接口注入 Demo 数据
- 确认后端服务运行正常后再调用该接口
- 如重复调用，注意可能产生重复数据

### 导出文件找不到

- 检查 `backend/exports/` 目录是否存在导出文件
- 确认导出任务已成功完成（通过 `GET /api/exports` 查看状态）
- 如目录不存在，手动创建 `backend/exports/` 目录后重试
