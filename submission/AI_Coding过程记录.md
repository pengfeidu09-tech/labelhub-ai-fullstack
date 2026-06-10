# AI Coding 过程记录

## 阶段 1：项目初始化
- **目标**：搭建前后端基础框架
- **问题**：无
- **AI Coding 参与点**：生成项目骨架、路由配置、基础组件
- **人工验收结果**：前后端可启动，页面可访问

## 阶段 2：任务、数据集、模板基础模块
- **目标**：实现任务管理、数据集管理、模板管理的 CRUD
- **问题**：数据模型设计需兼顾灵活性和查询效率
- **AI Coding 参与点**：生成 SQLAlchemy 模型、FastAPI 路由、React 页面组件
- **人工验收结果**：三个模块 CRUD 功能正常

## 阶段 3：标注工作台
- **目标**：标注员可在线填写标注表单并提交
- **问题**：大型组件性能问题、状态管理复杂度
- **AI Coding 参与点**：FormRenderer 动态表单、提交/草稿逻辑、Session 管理
- **人工验收结果**：标注流程可用

## 阶段 4：AI 预审 Agent
- **目标**：提交后自动运行 AI 审核，输出结构化质量建议
- **问题**：Prompt 工程、JSON 解析稳定性、Mock fallback
- **AI Coding 参与点**：Agent Service、Prompt 模板、执行引擎、Mock Provider
- **人工验收结果**：AI 预审可运行，结果可展示

## 阶段 5：审核队列与审核详情
- **目标**：审核员可查看提交、对比 AI 结果、通过或打回
- **问题**：三栏布局信息密度、AI/人工差异对比
- **AI Coding 参与点**：ReviewDetailPage 三栏组件、差异对比表格、Rubric 命中分析
- **人工验收结果**：审核流程完整

## 阶段 6：结果中心、导出、审计日志
- **目标**：通过审核的数据可导出，全链路操作可追踪
- **问题**：多格式导出兼容性
- **AI Coding 参与点**：ExportPage、AuditLogPage、导出服务
- **人工验收结果**：JSON/CSV/XLSX/JSONL 导出可用

## 阶段 7：任务专属模板治理
- **目标**：每个任务绑定唯一专属模板，支持拖拽搭建
- **问题**：模板设计器交互复杂度、Schema 校验
- **AI Coding 参与点**：TemplateDesignerPage 拖拽画布、ComponentPalette、PropertyPanel
- **人工验收结果**：模板搭建 → 保存 → 绑定任务流程通畅

## 阶段 8：qwen3.7-plus Provider 接入
- **目标**：默认 AI 模型切换为 DashScope qwen3.7-plus
- **问题**：Provider 配置链路、API Key 安全、fallback 机制
- **AI Coding 参与点**：OpenAICompatibleProvider、配置优先级链、运行时配置管理
- **人工验收结果**：qwen3.7-plus 可调通，Mock fallback 可用

## 阶段 9：标注工作台性能优化
- **目标**：解决 CPU 持续 128%~136%、页面无响应问题
- **问题**：RAF 60fps 循环、每次击键触发全组件重渲染、StrictMode 双重执行
- **AI Coding 参与点**：WorkbenchTimerDisplay 隔离组件、formData ref + debounce、移除 StrictMode
- **人工验收结果**：CPU 恢复正常，输入流畅

## 阶段 10：只读 Rubric 标准参考与 LLM Rubric 对齐建议
- **目标**：Rubric 面板作为只读参考，LLM 辅助提供维度对齐建议
- **问题**：避免 Rubric 面板与审核规则混淆、避免交互式控件影响性能
- **AI Coding 参与点**：OptimizedRubricPanel React.memo、SimpleLLMResultPanel Rubric 对齐建议
- **人工验收结果**：Rubric 面板只读展示正常，LLM 对齐建议可见

## 阶段 11：官方验收流程收口
- **目标**：按官方 5 段角色链路重写仪表盘演示路径，审核规则配置独立
- **问题**：旧流程偏质量洞察闭环、审核规则与 Rubric 面板混淆
- **AI Coding 参与点**：OwnerDashboard 8 步演示路径、TaskDetailPage 审核规则卡片、快捷入口 5 角色分区
- **人工验收结果**：演示路径清晰，审核规则独立展示

## 阶段 12：提交包清理
- **目标**：生成干净的提交压缩包，脱敏、补齐文档
- **问题**：敏感文件清理、旧文档更新、submission 材料编写
- **AI Coding 参与点**：清理脚本、文档生成、旧说法替换
- **人工验收结果**：zip 干净，文档完整
