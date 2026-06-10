# LabelHub 模板 Schema 协议

## 一、Schema 顶层结构

```json
{
  "schema_version": "1.0.0",
  "dataset_type": "qa_quality",
  "name": "问答质量评估模板",
  "description": "用于评估大模型回答质量",
  "layout": {
    "type": "single_column",
    "sections": []
  },
  "fields": [...],
  "rules": [...],
  "llm_assist": [...],
  "export_mapping": [...],
  "ai_review_config": {...}
}
```

### 顶层字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| schema_version | string | 是 | Schema 版本号，格式：x.y.z，例如 "1.0.0" |
| dataset_type | string | 是 | 数据集类型：qa_quality、preference_compare、custom |
| name | string | 是 | 模板名称 |
| description | string | 否 | 模板描述 |
| layout | object | 否 | 布局配置 |
| fields | array | 是 | 字段定义数组 |
| rules | array | 否 | 字段联动规则 |
| llm_assist | array | 否 | AI 辅助配置 |
| export_mapping | array | 否 | 导出字段映射 |
| ai_review_config | object | 否 | AI 审核配置 |

## 二、字段类型协议

### 支持的字段类型

| 类型 | 说明 | 渲染组件 |
|------|------|----------|
| ShowItem | 数据展示项 | div（只读） |
| TextInput | 单行文本输入 | Input |
| Textarea | 多行文本输入 | TextArea |
| Radio | 单选 | Radio.Group |
| Checkbox | 多选 | Checkbox.Group |
| TagSelect | 标签选择 | Select (tags mode) |
| JsonEditor | JSON 编辑器 | TextArea (monospace) |
| LLMAssist | AI 辅助组件 | Alert with Button |
| Group | 分组容器 | div with border |
| Tabs | 标签页容器 | 占位组件 |

### 字段定义结构

```typescript
interface TemplateField {
  id: string;              // 字段唯一标识
  type: string;            // 字段类型
  label: string;            // 显示标签
  binding?: string;         // 数据绑定，如 "{{item.prompt}}"
  format?: string;         // 格式：text | markdown | json | image
  required?: boolean;       // 是否必填
  options?: Array<{         // 选项配置
    label: string;         // 显示文本
    value: string;          // 值
  }>;
  validation?: {            // 验证规则
    required?: boolean;
    min?: number;
    max?: number;
    pattern?: string;
    custom?: string[];
  };
  props?: object;           // 传递给组件的其他属性
  hidden?: boolean;         // 是否隐藏
  placeholder?: string;     // 占位文本
  rows?: number;            // 行数（Textarea）
  height?: number;          // 高度（JsonEditor）
  inline?: boolean;         // 是否内联显示
}
```

## 三、ShowItem Binding 规则

### 绑定语法

使用 `{{item.字段名}}` 语法绑定数据项字段：

```
{{item.prompt}}         - 绑定 prompt 字段
{{item.model_answer}}   - 绑定 model_answer 字段
{{item.reference}}      - 绑定 reference 字段
{{item.tags}}           - 绑定 tags 字段
```

### 绑定解析示例

```json
{
  "id": "prompt_show",
  "type": "ShowItem",
  "label": "问题",
  "binding": "{{item.prompt}}",
  "format": "text"
}
```

假设 item 数据为：
```json
{
  "prompt": "什么是机器学习？",
  "model_answer": "机器学习是...",
  "reference": "机器学习是人工智能的一个分支..."
}
```

渲染结果：
- 标签："问题"
- 内容：`<div>什么是机器学习？</div>`

### 特殊格式处理

| format | 处理方式 |
|--------|----------|
| text | 普通文本，直接显示 |
| markdown | Markdown 格式（目前以纯文本显示） |
| json | JSON 字符串化显示 |
| image | 图片 URL（未来支持图片预览） |

## 四、Validation 规则

### 验证配置结构

```typescript
interface TemplateFieldValidation {
  required?: boolean;     // 是否必填
  min?: number;          // 最小值/长度
  max?: number;          // 最大值/长度
  pattern?: string;      // 正则表达式
  custom?: string[];     // 自定义验证规则
}
```

### 验证示例

```json
{
  "id": "relevance",
  "type": "Radio",
  "label": "相关性",
  "required": true,
  "validation": {
    "required": true
  }
}
```

## 五、Visibility Rules 规则

### 规则结构

```typescript
interface TemplateRule {
  id: string;                          // 规则唯一标识
  type: 'visibility' | 'required' | 'disabled';
  when?: {                             // 触发条件
    field: string;                    // 依赖字段
    operator: string;                 // 操作符
    value: any;                       // 目标值
  };
  target: string;                      // 目标字段
  effect: 'show' | 'hide' | 'enable' | 'disable' | 'require' | 'skip';
}
```

### 支持的操作符

| 操作符 | 说明 | 示例 |
|--------|------|------|
| eq | 等于 | `operator: "eq", value: "correct"` |
| neq | 不等于 | `operator: "neq", value: "safe"` |
| in | 包含于 | `operator: "in", value: ["incorrect", "partially_correct"]` |
| not_in | 不包含于 | `operator: "not_in", value: ["safe"]` |
| contains | 包含 | `operator: "contains", value: "error"` |
| gt | 大于 | `operator: "gt", value: 60` |
| lt | 小于 | `operator: "lt", value: 80` |

### 规则示例

```json
{
  "id": "show_correction_when_low_accuracy",
  "type": "visibility",
  "when": {
    "field": "accuracy",
    "operator": "in",
    "value": ["incorrect", "partially_correct"]
  },
  "target": "correction_json",
  "effect": "show"
}
```

当 accuracy 字段值为 "incorrect" 或 "partially_correct" 时，显示 correction_json 字段。

## 六、LLM Assist 协议

### LLM Assist 配置结构

```typescript
interface TemplateLLMAssist {
  id: string;                    // 唯一标识
  name: string;                  // 显示名称
  prompt_template: string;       // 提示词模板
  input_bindings: string[];      // 输入绑定字段
  output_target: string;         // 输出目标字段
}
```

### LLM Assist 示例

```json
{
  "id": "quality_assist",
  "name": "AI 质量建议",
  "prompt_template": "请根据问题、模型回答和参考答案，给出质量评估建议。",
  "input_bindings": ["prompt", "model_answer", "reference"],
  "output_target": "overall_comment"
}
```

### 当前实现状态

- 当前为 Mock 模式，不调用真实 LLM
- 组件显示为 Alert，包含提示词模板
- "生成建议"按钮处于禁用状态

## 七、Export Mapping 协议

### 导出映射结构

```typescript
interface TemplateExportMapping {
  source: string;     // 源字段 ID
  target: string;     // 目标字段名
  include?: boolean;  // 是否包含（默认 true）
  transform?: string; // 转换函数（未来支持）
}
```

### 导出映射示例

```json
{
  "export_mapping": [
    {"source": "relevance", "target": "relevance", "include": true},
    {"source": "accuracy", "target": "accuracy", "include": true},
    {"source": "reason", "target": "reason", "include": true}
  ]
}
```

## 八、Schema Version 兼容策略

### 版本格式

采用语义化版本 (SemVer)：`主版本.次版本.修订版本`

- 主版本：不兼容的 API 变更
- 次版本：向后兼容的功能新增
- 修订版本：向后兼容的问题修复

### 兼容性处理

1. **前向兼容**：新版 Schema 应能处理旧版数据
2. **字段缺失**：使用默认值填充缺失字段
3. **字段多余**：忽略无法识别的字段
4. **版本检测**：通过 `schema_version` 字段检测版本

### 默认值策略

| 字段 | 默认值 |
|------|--------|
| required | false |
| hidden | false |
| format | "text" |
| options | [] |
| validation | {} |
| props | {} |

### 版本迁移示例

旧版字段：
```json
{
  "type": "Radio",
  "label": "相关性"
}
```

新版兼容处理：
```json
{
  "type": "Radio",
  "label": "相关性",
  "required": false,
  "options": [],
  "format": "text",
  "validation": {},
  "props": {}
}
```

## 九、Layout 配置

### Layout 结构

```typescript
interface TemplateLayout {
  type: 'single_column' | 'two_column' | 'tabs' | 'accordion';
  sections?: Array<{
    id: string;
    title?: string;
    fields: string[];
    collapsible?: boolean;
    defaultExpanded?: boolean;
  }>;
}
```

### Layout 类型说明

| 类型 | 说明 |
|------|------|
| single_column | 单列布局（默认） |
| two_column | 两列布局 |
| tabs | 标签页布局 |
| accordion | 手风琴布局 |

## 十、附录

### 内置数据集类型

| 类型 | 说明 | 典型字段 |
|------|------|----------|
| qa_quality | 问答质量评估 | relevance, accuracy, completeness, safety |
| preference_compare | 偏好对比 | preferred, margin, dimensions |

### 完整字段类型列表

```
ShowItem       - 数据展示
TextInput      - 单行文本
Textarea       - 多行文本
Radio          - 单选按钮
Checkbox       - 多选框
TagSelect      - 标签选择
JsonEditor     - JSON 编辑器
LLMAssist      - AI 辅助
Group          - 分组容器
Tabs           - 标签页
```

## 十一、模板 Designer 页面使用说明

### 1. 页面访问

在模板列表页面，点击任意模板的"打开 Designer"按钮，即可进入模板 Designer 页面。页面 URL 格式：`/owner/templates/designer/{templateId}`

### 2. 页面布局

Designer 页面采用三栏布局：

- **左侧：物料区 (Material Panel)**：列出所有可用的字段组件，点击"添加"按钮将组件添加到画布中
- **中间：画布区 (Designer Canvas)**：显示当前模板的所有字段，可以选择、移动、复制、删除字段
- **右侧：属性面板 (Property Panel)**：选中字段后显示该字段的详细配置，可以修改属性

### 3. 顶部工具栏

顶部提供以下操作按钮：

- **返回列表**：回到模板管理页面
- **保存模板**：保存当前修改到服务器
- **预览渲染**：在弹窗中预览模板在标注工作台中的实际显示效果
- **查看 Schema**：在弹窗中查看当前模板的完整 JSON Schema
- **复制为新版本**：快速复制当前模板创建新版本

### 4. 物料区使用

物料区提供 10 种可拖拽的组件：

1. **ShowItem**：用于展示数据项内容（问题、答案等）
2. **TextInput**：单行文本输入框
3. **Textarea**：多行文本输入框
4. **Radio**：单选按钮组
5. **Checkbox**：多选框组
6. **TagSelect**：标签选择器
7. **JsonEditor**：JSON 编辑器
8. **LLMAssist**：AI 辅助生成组件
9. **Group**：字段分组容器
10. **Tabs**：标签页容器

点击物料卡片上的"添加"按钮，该组件就会被添加到画布底部。

### 5. 画布区操作

在画布区可以对字段进行以下操作：

- **选择**：点击字段卡片选中该字段
- **上移**：将字段在列表中向上移动一个位置
- **下移**：将字段在列表中向下移动一个位置
- **复制**：创建该字段的副本并添加到列表末尾
- **删除**：从列表中移除该字段

选中的字段会高亮显示蓝色边框和背景。

### 6. 属性面板配置

选中字段后，属性面板会显示该字段的配置项：

#### 通用属性（所有字段）

- **id**：字段唯一标识（只读）
- **type**：字段类型（只读）
- **label**：字段显示标签
- **required**：是否必填（开关）
- **占位符**：输入框的占位文本
- **帮助文本**：字段下方的提示文本

#### ShowItem 特殊属性

- **binding**：数据绑定表达式，如 `{{item.prompt}}`
- **format**：数据格式，可选：text、markdown、json、image、video、code

#### 选项类字段（Radio/Checkbox/TagSelect）

- **选项**：选项列表，可以添加、删除、修改 label 和 value

#### Textarea 特殊属性

- **行数**：输入框的默认行数
- **最大长度**：输入框的最大字符数

#### JsonEditor 特殊属性

- **默认值 JSON**：编辑器的默认 JSON 数据

#### LLMAssist 特殊属性

- **字段名**：字段的名称标识
- **提示模板**：AI 生成建议时使用的提示词模板
- **输入绑定**：输入绑定字段数组（JSON 格式）
- **输出目标**：输出到哪个字段

#### Group/Tabs 属性

- **子字段/标签页内容**：使用 JSON 编辑器处理（简化版本）

### 7. Schema 预览

点击"查看 Schema"按钮可以查看当前完整的模板 JSON Schema，这对于调试和检查配置非常有用。

### 8. 渲染预览

点击"预览渲染"按钮，可以在弹窗中看到模板在标注工作台中的真实样子，使用模拟数据进行展示，方便快速验证模板效果。

### 9. 保存模板

修改完成后，点击"保存模板"按钮将修改保存到服务器。保存成功后会显示成功提示。

### 10. 兼容性处理

- 打开旧模板时，如果 `schema.fields` 不存在，会根据 `dataset_type` 自动生成默认字段
- 所有字段操作都有安全检查，防止白屏或报错
- 向后兼容旧版的 Schema 格式
