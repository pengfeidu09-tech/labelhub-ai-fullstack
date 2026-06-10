from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, Any, List, Union


class TemplateFieldOption(BaseModel):
    label: str
    value: str


class TemplateFieldValidation(BaseModel):
    required: Optional[bool] = None
    min: Optional[int] = None
    max: Optional[int] = None
    pattern: Optional[str] = None
    custom: Optional[List[str]] = None


class TemplateField(BaseModel):
    id: str
    type: str = Field(..., pattern="^(ShowItem|TextInput|Textarea|Radio|Checkbox|TagSelect|JsonEditor|LLMAssist|Group|Tabs)$")
    label: str
    binding: Optional[str] = None
    format: Optional[str] = Field(None, pattern="^(text|markdown|json|image)$")
    required: Optional[bool] = False
    options: Optional[List[TemplateFieldOption]] = None
    validation: Optional[TemplateFieldValidation] = None
    props: Optional[dict] = {}
    hidden: Optional[bool] = False
    placeholder: Optional[str] = None
    rows: Optional[int] = None
    height: Optional[int] = None
    inline: Optional[bool] = False


class TemplateLayoutSection(BaseModel):
    id: str
    title: Optional[str] = None
    fields: List[str]
    collapsible: Optional[bool] = False
    defaultExpanded: Optional[bool] = True


class TemplateLayout(BaseModel):
    type: str = Field("single_column", pattern="^(single_column|two_column|tabs|accordion)$")
    sections: Optional[List[TemplateLayoutSection]] = None


class TemplateRuleCondition(BaseModel):
    field: str
    operator: str = Field(..., pattern="^(eq|neq|in|not_in|contains|gt|lt)$")
    value: Any


class TemplateRule(BaseModel):
    id: str
    type: str = Field(..., pattern="^(visibility|required|disabled)$")
    when: Optional[TemplateRuleCondition] = None
    target: str
    effect: str = Field(..., pattern="^(show|hide|enable|disable|require|skip)$")


class TemplateLLMAssist(BaseModel):
    id: str
    name: str
    prompt_template: str
    input_bindings: List[str]
    output_target: str


class TemplateExportMapping(BaseModel):
    source: str
    target: str
    include: Optional[bool] = True
    transform: Optional[str] = None


class TemplateSchemaDefinition(BaseModel):
    schema_version: str = "1.0.0"
    dataset_type: str
    name: str
    description: Optional[str] = None
    layout: Optional[Union[TemplateLayout, str]] = None
    fields: List[TemplateField]
    rules: Optional[List[TemplateRule]] = None
    llm_assist: Optional[List[TemplateLLMAssist]] = None
    export_mapping: Optional[List[TemplateExportMapping]] = None
    ai_review_config: Optional[dict] = None


class TemplateSchemaCreate(BaseModel):
    name: str
    description: Optional[str] = None
    form_schema: dict = Field(alias="schema")
    schema_version: Optional[str] = "1.0.0"
    dataset_type: str = Field(..., pattern="^(qa_quality|preference_compare|custom)$")
    frozen_after_publish: Optional[bool] = False
    parent_template_id: Optional[int] = None
    is_active: Optional[bool] = True
    changelog: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class TemplateSchemaUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    form_schema: Optional[dict] = Field(None, alias="schema")
    schema_version: Optional[str] = None
    frozen_after_publish: Optional[bool] = None
    is_active: Optional[bool] = None
    changelog: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class TemplateCloneRequest(BaseModel):
    schema_version: Optional[str] = None
    changelog: Optional[str] = None


class TemplateSchemaResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    form_schema: dict = Field(alias="schema")
    schema_version: str
    dataset_type: str
    frozen_after_publish: Optional[bool] = False
    parent_template_id: Optional[int] = None
    is_active: Optional[bool] = True
    changelog: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # ── 模板-任务绑定字段 ──
    task_id: Optional[int] = None
    template_scope: Optional[str] = None
    is_task_bound: Optional[bool] = False
    is_official_base: Optional[bool] = False
    is_archived: Optional[bool] = False
    visible_in_template_page: Optional[bool] = True
    legacy_reason: Optional[str] = None
    # ── 扩展字段（API 层填充） ──
    task_name: Optional[str] = None
    linked_task_count: Optional[int] = 0
    llm_assist_enabled: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TemplateListResponse(BaseModel):
    items: list[TemplateSchemaResponse]
    total: int
    page: int
    limit: int
