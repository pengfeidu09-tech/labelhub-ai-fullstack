# LabelHub Video Recording Checklist

## 环境准备

- [ ] 1. 后端已启动（`cd backend && python -m uvicorn app.main:app --reload --port 8000`）
- [ ] 2. 前端已启动（`cd frontend && npm run dev`）
- [ ] 3. Demo 数据存在（数据库中有预置的 Task、DatasetItem、Annotation 数据）
- [ ] 4. 系统健康检查正常（Owner 仪表盘 → 系统健康检查卡片全部显示正常）

## 功能检查

- [ ] 5. 演示模式开启（Owner 仪表盘 → Demo Mode 开关打开）
- [ ] 6. Owner 仪表盘正常（项目总览、AI 质量闭环、最近动态、推荐演示任务、评审路径）
- [ ] 7. Labeler 工作台正常（三栏布局、原始数据、标注表单、Rubric 维度、计时器）
- [ ] 8. AI 预审正常（点击 AI 预审按钮后显示 overall_score、risk_level、dimension_scores、suggested_action、reason）
- [ ] 9. 审核队列正常（Reviewer 页面显示待审核列表）
- [ ] 10. 审核详情正常（原始数据、人工标注、AI 预审结果、AI/人工差异对比）
- [ ] 11. 返修链路正常（打回后 Labeler 可看到原因，修改后可重新提交）
- [ ] 12. 结果中心正常（统计卡片、质量洞察、Rubric 命中分析、重点复核样本、AI 质量报告）
- [ ] 13. 导出 JSON / CSV 正常（点击导出后文件可下载，内容正确）
- [ ] 14. 审计日志正常（按动作类型筛选，显示操作记录）
- [ ] 15. 工时报表正常（按标注员、任务统计工时数据）

## 录屏准备

- [ ] 16. 浏览器缩放 100%（确保画面清晰不模糊）
- [ ] 17. 页面不要出现 undefined / null / NaN（检查所有页面显示正常）
- [ ] 18. 桌面不要暴露隐私信息（关闭无关窗口、隐藏敏感信息）
- [ ] 19. 录屏时按 demo_walkthrough.md 顺序进行
