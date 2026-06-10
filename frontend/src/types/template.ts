export interface TemplateFieldOption {
  label: string;
  value: string;
}

export interface TemplateFieldValidation {
  required?: boolean;
  min?: number;
  max?: number;
  pattern?: string;
  custom?: string[];
}

export interface TemplateField {
  id: string;
  key?: string;
  type: 'ShowItem' | 'TextInput' | 'Textarea' | 'Radio' | 'Checkbox' | 'TagSelect' | 'JsonEditor' | 'LLMAssist' | 'Group' | 'Tabs' | 'Rating' | 'TextInput' | 'Select';
  label?: string;
  name?: string;
  binding?: string;
  format?: 'text' | 'markdown' | 'json' | 'image' | 'code';
  required?: boolean;
  options?: TemplateFieldOption[];
  validation?: TemplateFieldValidation;
  props?: Record<string, any>;
  hidden?: boolean;
  placeholder?: string;
  rows?: number;
  height?: number;
  inline?: boolean;
  prompt_template?: string;
  input_bindings?: string[];
  output_target?: string;
  children?: TemplateField[];
  tabs?: Array<{ title: string; fields: TemplateField[] }>;
  defaultValue?: any;
  min?: number;
  max?: number;
  step?: number;
  buttonText?: string;
  promptTemplate?: string;
  targetField?: string;
  title?: string;
  description?: string;
  collapsible?: boolean;
  rules?: TemplateRule[] | Record<string, any>;
}

export interface TemplateLayoutSection {
  id: string;
  title?: string;
  fields: string[];
  collapsible?: boolean;
  defaultExpanded?: boolean;
}

export interface TemplateLayout {
  type: 'single_column' | 'two_column' | 'tabs' | 'accordion';
  sections?: TemplateLayoutSection[];
}

export interface TemplateRuleCondition {
  field: string;
  operator: 'eq' | 'neq' | 'in' | 'not_in' | 'contains' | 'gt' | 'lt';
  value: any;
}

export interface TemplateRule {
  id: string;
  type: 'visibility' | 'required' | 'disabled';
  when?: TemplateRuleCondition;
  target: string;
  effect: 'show' | 'hide' | 'enable' | 'disable' | 'require' | 'skip';
}

export interface TemplateLLMAssist {
  id: string;
  name: string;
  prompt_template: string;
  input_bindings: string[];
  output_target: string;
}

export interface TemplateExportMapping {
  source: string;
  target: string;
  include?: boolean;
  transform?: string;
}

export interface TemplateSchema {
  schema_version: string;
  dataset_type: string;
  name: string;
  description?: string;
  layout?: TemplateLayout | string;
  fields: TemplateField[];
  required?: string[];
  rules?: TemplateRule[];
  llm_assist?: TemplateLLMAssist[];
  export_mapping?: TemplateExportMapping[];
  ai_review_config?: {
    enabled: boolean;
    scoreDimensions?: Array<{ name: string; weight: number }>;
    passThreshold?: number;
    rejectThreshold?: number;
  };
}

export interface Template {
  id: number;
  name: string;
  description?: string;
  schema: TemplateSchema | Record<string, any>;
  schema_version: string;
  dataset_type: string;
  frozen_after_publish: boolean;
  parent_template_id?: number;
  is_active: boolean;
  changelog?: string;
  created_by: number;
  created_at?: string;
  updated_at?: string;
  // ── 模板-任务绑定字段 ──
  task_id?: number;
  template_scope?: string;
  is_task_bound?: boolean;
  is_official_base?: boolean;
  is_archived?: boolean;
  visible_in_template_page?: boolean;
  legacy_reason?: string;
  // ── 扩展字段 ──
  task_name?: string;
  linked_task_count?: number;
  llm_assist_enabled?: boolean;
}

export interface TemplateListResponse {
  items: Template[];
  total: number;
  page: number;
  limit: number;
}

export interface TemplateCloneRequest {
  schema_version?: string;
  changelog?: string;
}
