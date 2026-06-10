# LabelHub 更新日志

## v1.5.0 (2026-05-30) - Phase 14: 评审展示与产品化收口

### 新增
- Owner 仪表盘首页：项目总览、AI 质量闭环概览、最近业务动态、角色快速入口、推荐演示任务
- 评审演示路径模块（8 步 Demo Walkthrough）
- 系统健康检查模块（API/数据库/Demo数据/AI预审/导出服务状态）
- Demo 数据说明模块（场景/字段/维度/角色/AI Agent 说明）
- 演示模式开关（localStorage 保存，关键页面显示功能提示）
- 6 个新审计动作：dashboard_view, demo_walkthrough_view, demo_mode_enable, demo_mode_disable, system_health_check, demo_data_doc_view

## v1.4.0 (2026-05-30) - Phase 13: AI 质量治理升级

### 新增
- 质量洞察模块：AI 平均分、风险分布、人工通过率、AI/人工一致率、低分样本、重点复核
- Rubric 命中分析：4 维度统计、高争议标记、标签分类
- 重点复核样本：6 条触发规则筛选、跳转审核详情
- AI 质量报告：7 节结构化报告、可复制、标注生成来源
- 4 个新审计动作：quality_insight_view, rubric_analysis_view, quality_report_generate, priority_review_list_view

## v1.3.0 (2026-05-29) - Phase 12: 返修闭环与工时统计

### 新增
- 返修闭环流程：打回→查看原因→修改→重新提交→再次审核
- 工时统计报表：按标注员、任务、日期统计工时
- 工作会话管理：开始/暂停/结束计时
- 审核详情增强：AI/人工对比、审核时间线

## v1.2.0 (2026-05-27) - Phase 10-11: AI 预审与审核

### 新增
- AI 预审 Agent：结构化评分、风险等级、维度分、建议动作
- 人工审核队列：审核通过/打回/修订
- 审核详情页：原始数据+标注+AI预审对比
- 审计日志：全链路操作追踪

## v1.1.0 (2026-05-23) - Phase 7-9: 标注工作台与提交

### 新增
- Labeler 标注工作台：三栏布局、动态表单渲染
- 草稿自动保存
- 标注提交与状态流转
- 任务市场与数据领取

## v1.0.0 (2026-05-21) - Phase 1-6: 基础架构

### 新增
- 项目基础架构：FastAPI + React + SQLite
- 任务管理：创建、发布、暂停、结束
- 模板设计器：JSON Schema 驱动的可视化模板编辑
- 数据集导入：JSON/JSONL/XLSX 格式支持
- 多格式导出：JSON/CSV/XLSX
- Demo 数据：问答质量评估场景
