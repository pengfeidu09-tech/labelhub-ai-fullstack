# LabelHub 截图证据包

本目录包含 LabelHub 平台各核心页面的截图，按演示链路排列。

## 截图清单

| 序号 | 文件名 | 页面说明 | 核心验证点 |
|------|--------|----------|------------|
| 01 | 01_owner_task_overview.png | Owner 任务总览 | 任务列表、状态标签、数据量统计 |
| 02 | 02_owner_task_detail.png | Owner 任务详情 | 任务配置、模板、数据集、进度统计 |
| 03 | 03_template_designer.png | 模板设计器 | 模板字段、维度配置、预览 |
| 04 | 04_labeler_workbench.png | Labeler 工作台 | 原始数据、标注表单、计时状态、AI辅助 |
| 05 | 05_ai_precheck_result.png | AI 预审结果 | 分数、风险等级、建议动作、原因、维度详情 |
| 06 | 06_labeler_my_submissions.png | Labeler 我的提交 | 统计卡片、状态标签(待审核/已通过/已打回/待返修/返修已提交)、退回原因 |
| 07 | 07_reviewer_queue.png | 审核队列 | 待审核列表、状态标签统一中文化、筛选 |
| 08 | 08_reviewer_detail.png | 审核详情 | 原始数据+人工标注+AI预审+差异对比 |
| 09 | 09_review_approve_or_reject.png | 审核通过/打回 | 通过/打回操作、原因填写、状态流转 |
| 10 | 10_result_center_dashboard.png | 结果中心 | 统计卡片、AI/人工概览、质量指标、导出 |
| 11 | 11_export_records.png | 导出记录 | ID/格式/状态/行数/路径/下载/复制/摘要 |
| 12 | 12_audit_logs.png | 审计日志 | 操作列表、用户角色、目标类型/ID、详情弹窗 |
| 13 | 13_worktime_report.png | 工时报表 | 今日统计、日报明细、时间格式(00:01:24) |

## 截图要求

- 每张图只截一个核心页面
- 页面上不要出现明显错误、空字段、乱码、长小数、路径撑爆、状态矛盾
- 不要放低清长图
- 不要出现空白页
- 格式：PNG，分辨率 ≥ 1280x720

## 状态流转验证链路

```
Owner 创建任务 → Labeler 领取标注 → 保存草稿 → AI预审 → 提交
→ Reviewer 审核队列 → 审核详情 → 通过/打回
→ 通过 → 结果中心可导出 → 导出记录
→ 打回 → Labeler 返修 → 重新提交 → 再次审核
→ 审计日志全链路追踪
→ 工时报表聚合
```
