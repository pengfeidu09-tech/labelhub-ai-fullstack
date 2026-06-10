# Smoke Test

## 1. Runtime

- 后端启动成功
- 前端启动成功
- /api/health 返回 200
- 右上角显示后端 API 正常

## 2. Owner

- 仪表盘正常
- AI 质量闭环概览正常
- 推荐演示任务正常
- 系统健康检查正常
- Rubric 标准库正常
- AI 审核 Agent 页面正常
- 导出管理正常
- 审计日志正常

## 3. Labeler

- 任务市场正常
- 标注工作台正常
- 计时器正常
- 快速切换页面不清零
- 保存草稿正常
- AI 预审正常
- 提交标注正常
- 我的提交正常
- 工时报表正常

## 4. Reviewer

- 审核队列正常
- 审核详情正常
- AI / 人工差异对比正常
- 审核通过正常
- 打回返修正常

## 5. AI Agent

- 提交后自动入队
- pending / running / success / failed / fallback_required 状态正常
- 运行待处理队列正常
- 重试失败任务正常
- 详情抽屉正常
- Prompt、输入快照、结构化输出、原始 JSON 正常
- 审计日志有 agent 动作

## 6. Export

- JSON 导出成功
- CSV 导出成功
- XLSX 导出成功
- 导出行数不为 0
- 导出文件包含人工标注结果
- 导出文件包含 AIReviewRun / ai_review_result
- 导出记录可下载 / 复制 / 查看摘要

## 7. Console

- 无红色 error
- 无 405 / 500
- 无 duplicate key
- 无 uncaught exception
- React Router future warning 可接受
