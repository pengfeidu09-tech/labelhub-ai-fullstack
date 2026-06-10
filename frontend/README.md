# LabelHub 前端

LabelHub 数据标注平台的前端界面，使用 React 18 + TypeScript + Vite 构建。

## 技术栈

- React 18
- TypeScript
- Vite
- Ant Design
- React Router
- Zustand
- Axios
- Day.js

## 快速开始

### 环境要求

- Node.js 18+
- npm 8+

### 安装依赖

```bash
cd frontend
npm install
```

### 配置环境变量

创建 `.env` 文件（可以从 `.env.example` 复制）：

```bash
cp .env.example .env
```

默认配置：
```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

### 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:5173

### 构建生产版本

```bash
npm run build
```

## 项目结构

```
frontend/
├── src/
│   ├── api/                # API 客户端
│   ├── components/         # 组件
│   ├── layouts/            # 布局
│   ├── pages/              # 页面
│   │   ├── owner/          # 项目所有者页面
│   │   ├── labeler/        # 标注员页面
│   │   └── reviewer/       # 审核员页面
│   ├── stores/             # Zustand 状态管理
│   ├── types/              # TypeScript 类型定义
│   ├── utils/              # 工具函数
│   ├── App.tsx             # 主应用
│   └── main.tsx            # 入口文件
├── index.html
├── package.json
├── vite.config.ts
└── tsconfig.json
```

## 功能模块

### 项目所有者 (Owner)
- 任务管理
- 模板管理
- 数据导入
- 导出历史
- 审计日志

### 标注员 (Labeler)
- 任务广场
- 标注工作台
- 我的提交

### 审核员 (Reviewer)
- 审核队列
- 审核详情

## 后端连接

确保后端服务已启动在 http://127.0.0.1:8000

启动后端：
```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
