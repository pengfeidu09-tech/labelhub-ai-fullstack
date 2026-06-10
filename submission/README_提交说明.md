# LabelHub 数据标注平台 — 提交说明

## 项目名称
LabelHub 数据标注平台

## 项目定位
面向大模型数据生产的 AI 标注与审核平台。

## 核心流程
1. 任务负责人创建任务
2. 任务负责人配置任务专属模板
3. 任务负责人配置审核规则
4. 标注员在任务市场领取任务
5. 标注员进入高性能标注工作台
6. 查看只读 Rubric 标准参考
7. 点击 LLM 辅助获得 Rubric 对齐建议
8. 提交答案
9. AI Agent 自动预审
10. Reviewer 人工审核
11. Owner 查看结果中心
12. 多格式导出和审计追踪

## 主演示任务
任务 #10 官方原题·问答质量标注

## 扩展演示任务
任务 #11 官方原题·偏好对比标注

## 技术栈
- 前端：React 18 + TypeScript + Vite + Ant Design
- 后端：FastAPI + SQLAlchemy + Pydantic + SQLite
- AI：DashScope / qwen3.7-plus / Demo fallback

## 启动方式
参见 `submission/部署说明.md` 或项目根目录 `README.md`
