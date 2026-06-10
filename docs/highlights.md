# Project Highlights

## 一句话定位

LabelHub 是一个面向大模型数据生产的 AI-powered 数据标注质量治理平台。

## 技术亮点

- **Schema-driven Template**：JSON Schema 驱动标注模板，可视化设计器编辑 + 运行时动态渲染，一套模板适配多种标注场景
- **State-machine Workflow**：Draft → Submitted → AI Precheck → Human Review → Approved / Rejected → Rework → Resubmit，每个状态转换有审计记录
- **AI Review Agent**：结构化评分（0-100）、风险等级（low/medium/high）、维度分、建议动作、原因说明，当前 mock 模式保证演示稳定
- **AI-human Comparison**：审核详情中对比 AI 预审与人工标注结果，差异可视化，支持差异分析
- **Quality Insight**：AI 平均分、风险分布、一致率、重点复核数，从任务级别查看数据质量
- **Audit Trail**：30+ 关键动作追踪，全链路可追溯，支持复盘和质量追责
- **Multi-format Export**：JSON / CSV / XLSX 导出，含 AI 预审统计，支持训练数据交付

## 产品亮点

- **三角色协作**：Owner 管理任务和质量、Labeler 标注和 AI 预审、Reviewer 审核和返修
- **三栏式标注工作台**：左侧原始数据、中间动态标注表单、右侧 AI 预审，一个页面完成全部操作
- **返修闭环**：打回→查看原因→修改→重新提交→再次审核，完整闭环
- **结果中心**：统计卡片、质量洞察、Rubric 命中分析、重点复核样本、AI 质量报告
- **演示模式**：一键开启演示提示，评审路径引导，系统健康检查
- **系统健康检查**：API / 数据库 / Demo 数据 / AI 预审 / 导出服务状态实时监控

## 工程亮点

- **前后端分离**：FastAPI + React + TypeScript，REST API 通信
- **REST API**：13 个模块、35+ 接口，结构化响应，错误码统一
- **结构化数据模型**：三层嵌套（Task → DatasetItem → Annotation/Submission/AIReviewRun/HumanReview），解耦任务、数据和结果
- **审计日志**：30+ 关键动作，全链路操作追踪
- **导出服务**：JSON / CSV / XLSX 三种格式，异步导出，记录可追溯
- **文档完整**：架构文档、数据模型文档、API 文档、部署文档、演示脚本、质量 Agent 文档

## 简历表达

- 设计并实现 LabelHub 数据标注与质量治理平台，覆盖任务配置、动态标注、AI 预审、人工审核、返修流转、结果导出和审计追踪。
- 基于 Project/Task → DatasetItem/WorkUnit → Submission/AIReviewRun/HumanReview 的三层嵌套模型，支持多状态流转和全链路追溯。
- 实现 AI Review Agent 结构化预审能力，输出质量分、风险等级、维度分和建议动作，并支持 AI/人工结果差异对比。
- 构建结果中心、质量洞察、Rubric 命中分析、重点复核样本和多格式导出能力，提升标注数据的可治理性和可交付性。
