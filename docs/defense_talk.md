# LabelHub Defense Talk

## 1. 项目背景

大模型数据生产中，人工标注、AI 质检、审核返修、质量分析和数据导出通常是割裂的。团队往往需要在多个工具之间切换：标注用一个系统、质检用另一个、导出还要手动处理。LabelHub 解决的是从标注生产到质量治理再到数据交付的闭环问题。我们把任务配置、动态标注、AI 预审、人工审核、返修流转、结果中心、质量分析和多格式导出整合在一个平台中，让数据生产的每一步都可追溯、可治理、可交付。

## 2. 解决方案

LabelHub 通过五个核心设计实现质量闭环：

第一，Schema-driven 动态模板。标注表单由 JSON Schema 驱动，支持可视化设计器编辑，运行时动态渲染，一套模板适配多种标注场景。

第二，三层嵌套数据模型。Project/Task 承载任务配置，DatasetItem 承载数据样本，Annotation/Submission/AIReviewRun/HumanReview 承载标注结果和审核记录。三层解耦，支持同一数据多次返修和复审。

第三，AI Review Agent。在人工提交前给出结构化质量建议，包括总分、风险等级、维度分、建议动作和原因说明。当前使用 mock 模式保证演示稳定，接口结构支持替换真实模型。

第四，人工审核状态机。从提交到审核到通过或打回，每个状态转换都有审计记录。打回后 Labeler 可以看到原因、修改后重新提交，形成返修闭环。

第五，结果中心与审计日志。Owner 可以从任务级别查看数据质量，不只是看完成数量，还能看到风险分布、一致率、高争议 Rubric 和重点复核样本。审计日志记录全链路操作，支持复盘和质量追责。

## 3. 核心架构

LabelHub 采用三层嵌套数据结构：

第一层：Project / Task
承载任务配置、模板关联、AI 开关、状态管理和统计口径。一个 Task 对应一个标注任务，包含模板、数据集和审核配置。

第二层：DatasetItem / TaskItem / WorkUnit
承载具体样本、题目、分配状态和工作单。每个 DatasetItem 包含原始数据（prompt、model_answer、reference 等），以及当前标注状态。

第三层：Annotation / Submission / AIReviewRun / HumanReview / WorkSession / ExportRecord / AuditLog
承载标注结果、提交记录、AI 预审结果、人工审核记录、工作会话、导出记录和审计日志。

为什么这样设计：
- 任务、样本、提交结果解耦，避免数据冗余
- 支持同一数据多次返修和复审，每次提交独立追踪
- AI 结果与人工结果独立存储，便于差异对比和持续优化
- 支持全链路审计和导出复盘，每一步操作可追溯

## 4. AI Agent 设计

AI Review Agent 接收四个输入：
1. 原始数据（prompt、model_answer、reference）
2. 人工标注结果（relevance、accuracy、completeness、safety、reason）
3. Rubric 维度定义
4. 模板 schema

输出结构化质量建议：
- overall_score：0-100 综合评分
- risk_level：low / medium / high 风险等级
- dimension_scores：四个维度的分项评分和值
- suggested_action：submit / manual_review / reject 建议动作
- confidence：0-1 置信度
- reason：质量原因说明
- summary：质量摘要
- issue_tags：问题标签列表

当前工程状态：支持 mock AI Review Agent，保证演示稳定；输出结构已标准化，后续可替换真实大模型 API。接口设计遵循 Provider 模式，只需实现 ai_provider.py 即可接入 OpenAI / Claude 等模型。

## 5. 工作流闭环

完整工作流：

Owner 发布任务 → Labeler 领取数据并填写标注 → AI 预审 Agent 给出质量建议 → Labeler 提交标注 → Reviewer 查看审核详情 → 对比 AI 与人工结果 → 通过或打回 → Labeler 查看打回原因 → 修改后重新提交 → Reviewer 再次审核 → 通过 → Owner 查看结果中心 → 查看质量洞察、Rubric 分析、重点复核 → 生成 AI 质量报告 → 导出通过数据 → 审计日志追踪全流程

每个状态转换都有审计记录，支持复盘和质量追责。

## 6. 项目亮点

1. Schema-driven 动态标注模板：JSON Schema 驱动，可视化设计器 + 动态渲染器解耦
2. 三层嵌套数据结构：Task → DatasetItem → Annotation/Submission/AIReviewRun，解耦任务、数据和结果
3. AI 预审 Agent：结构化评分、风险等级、维度分、建议动作，辅助人工决策
4. AI / 人工差异对比：审核详情中对比 AI 和人工结果，支持差异分析
5. 返修闭环状态机：打回→查看原因→修改→重新提交→再次审核，完整闭环
6. 结果中心质量洞察：AI 平均分、风险分布、一致率、重点复核数
7. Rubric 命中分析：4 维度统计、高争议标记、标签分类
8. 重点复核样本：6 条触发规则筛选，跳转审核详情
9. AI 质量报告：7 节结构化报告，可复制，标注生成来源
10. 多格式导出：JSON / CSV / XLSX，含 AI 预审统计
11. 审计日志：30+ 关键动作追踪，全链路可追溯
12. 工时统计：按标注员、任务、日期统计工时
13. 演示模式和评审路径：评委可快速理解系统价值

## 7. 项目价值

LabelHub 面向真实大模型数据生产场景。相比普通标注平台，它更关注质量治理、风险识别、返修闭环、可追溯和可交付。

具体价值：
- AI 参与预审、风险识别、质量分析和报告生成，不是简单打分
- 标注、审核、返修、导出、审计形成闭环，不是割裂的工具
- 全链路审计日志支持复盘和质量追责
- 多格式导出支持训练数据交付
- 可作为企业级标注平台雏形，支持后续扩展真实模型、多模态标注和权限系统
