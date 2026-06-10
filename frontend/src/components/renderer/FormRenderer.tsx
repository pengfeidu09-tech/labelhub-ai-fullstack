import React, { useState, useCallback, useMemo, useEffect } from 'react';
import { Input, Radio, Checkbox, Select, Empty, Alert, Button } from 'antd';
import type { TemplateSchema, TemplateField } from '../../types/template';

const { TextArea } = Input;

interface FormRendererProps {
  schema?: TemplateSchema | null;
  itemData?: any;
  value?: any;
  onChange?: (value: any) => void;
  datasetType?: string;
  readonly?: boolean;
  missingFields?: string[];
  aiAssistText?: string;
}

const renderTemplate = (template: string, item: any): string => {
  if (!template) return '';
  return String(template).replace(/\{\{item\.([^}]+)\}\}/g, (_, rawKey) => {
    const key = String(rawKey).trim();
    return item?.[key] ?? '';
  });
};

const inferShowItemValue = (field: TemplateField, item: any): string => {
  const label = String(field.label || '').toLowerCase();
  const key = String(field.key || field.id || '').toLowerCase();
  const fieldAsAny = field as any;
  const bindingVal = renderTemplate(field.binding || fieldAsAny.value || '', item);
  if (bindingVal) return bindingVal;
  if (label.includes('问题') || key.includes('question') || key.includes('prompt')) return item.question ?? item.prompt ?? '';
  if (label.includes('模型回答') || key.includes('answer') || key.includes('model_answer')) return item.model_answer ?? '';
  if (label.includes('参考') || key.includes('reference')) return item.reference ?? '';
  if (label.includes('媒体类型') || key.includes('media_type')) return item.media_type ?? '';
  if (label.includes('媒体url') || key.includes('url') || key.includes('media_url')) return item.media_url ?? item.url ?? '';
  if (label.includes('内容') || key.includes('content')) return item.content ?? '';
  if (label.includes('分类') || key.includes('category')) return item.category ?? '';
  if (label.includes('难度') || key.includes('difficulty')) return item.difficulty ?? '';
  if (label.includes('预期维度') || key.includes('expected_dimensions')) return item.expected_dimensions ?? '';
  if (label.includes('回答a') || key.includes('answer_a')) return item.answer_a ?? '';
  if (label.includes('回答b') || key.includes('answer_b')) return item.answer_b ?? '';
  return '';
};

const isEmptyShowValue = (value: string): boolean => {
  if (!value) return true;
  if (value.trim() === '') return true;
  if (value === '暂无预览数据') return true;
  if (value === '[]' || value === '{}') return true;
  return false;
};

const shouldHideEmptyShowItem = (field: TemplateField): boolean => {
  const fieldAsAny = field as any;
  if (fieldAsAny.showWhenEmpty === true) return false;
  const key = String(field.key || field.id || '').toLowerCase();
  const hiddenKeys = ['media_type', 'media_url', 'content_detail', 'expected_dimension', 'expected_dimensions', 'preview_dimension', 'preview_dimensions'];
  if (hiddenKeys.some(hk => key.includes(hk))) return true;
  const label = String(field.label || '').toLowerCase();
  const hiddenLabels = ['媒体类型', '媒体url', '内容详情', '预期维度'];
  if (hiddenLabels.some(hl => label.includes(hl))) return true;
  return false;
};

const RATING_FIELDS = new Set(['relevance', 'accuracy', 'completeness', 'safety']);
const RATING_LABELS: Record<string, string> = {
  relevance: '相关性',
  accuracy: '准确性',
  completeness: '完整性',
  safety: '安全性',
};

const CollapsibleField: React.FC<{ title: string; defaultCollapsed?: boolean; children: React.ReactNode }> = ({ title, defaultCollapsed = true, children }) => {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  useEffect(() => {
    setCollapsed(defaultCollapsed);
  }, [defaultCollapsed]);

  return (
    <div style={{ marginBottom: 8 }}>
      <div
        onClick={() => setCollapsed(!collapsed)}
        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, marginBottom: collapsed ? 0 : 8, userSelect: 'none' }}
      >
        <span style={{ fontSize: 10, color: '#999', transition: 'transform 0.2s', transform: collapsed ? 'rotate(0deg)' : 'rotate(90deg)', display: 'inline-block' }}>▶</span>
        <span style={{ fontSize: 13, fontWeight: 500, color: '#555' }}>{title}</span>
        {collapsed && <span style={{ fontSize: 11, color: '#bbb' }}>（点击展开）</span>}
      </div>
      {!collapsed && <div style={{ paddingLeft: 16 }}>{children}</div>}
    </div>
  );
};

const FormRenderer: React.FC<FormRendererProps> = ({
  schema,
  itemData,
  value = {},
  onChange,
  datasetType,
  readonly = false,
  missingFields = [],
  aiAssistText = ''
}) => {
  const [internalValue, setInternalValue] = useState<Record<string, any>>(value);

  // Stable ref for onChange to avoid infinite update loop
  const onChangeRef = React.useRef(onChange);
  useEffect(() => { onChangeRef.current = onChange; }, [onChange]);

  useEffect(() => {
    setInternalValue(prev => {
      // Shallow-equal check: avoid setState if nothing changed
      const prevKeys = Object.keys(prev);
      const nextKeys = Object.keys(value);
      if (prevKeys.length === nextKeys.length && prevKeys.every(k => prev[k] === value[k])) {
        return prev;
      }
      return value;
    });
  }, [value]);

  // Stable updateField: no dependency on internalValue, uses functional setState
  const updateField = useCallback((fieldKey: string, fieldValue: any) => {
    setInternalValue(prev => {
      const newValue = { ...prev, [fieldKey]: fieldValue };
      // Fire onChange in microtask to avoid sync setState-in-render
      Promise.resolve().then(() => {
        onChangeRef.current?.(newValue);
      });
      return newValue;
    });
  }, []); // intentionally empty deps — stable forever

  const getFieldValue = useCallback((fieldKey: string): any => {
    return internalValue[fieldKey] ?? '';
  }, [internalValue]);

  const defaultQASchema: TemplateSchema = {
    schema_version: '1.0.0',
    dataset_type: 'qa_quality',
    name: '问答质量评估模板',
    fields: [
      { id: 'field_1', key: 'prompt', type: 'ShowItem', label: '问题', binding: '{{item.prompt}}', format: 'text' },
      { id: 'field_2', key: 'model_answer', type: 'ShowItem', label: '模型回答', binding: '{{item.model_answer}}', format: 'markdown' },
      { id: 'field_3', key: 'reference', type: 'ShowItem', label: '参考答案', binding: '{{item.reference}}', format: 'text' },
      { id: 'field_4', key: 'relevance', type: 'Radio', label: '相关性', required: true, options: [
        { label: '高', value: 'high' },
        { label: '中', value: 'medium' },
        { label: '低', value: 'low' }
      ]},
      { id: 'field_5', key: 'accuracy', type: 'Radio', label: '准确性', required: true, options: [
        { label: '正确', value: 'correct' },
        { label: '部分正确', value: 'partially_correct' },
        { label: '错误', value: 'incorrect' }
      ]},
      { id: 'field_6', key: 'overall_comment', type: 'Textarea', label: '总体评价', rows: 3 },
      { id: 'field_7', key: 'correction_json', type: 'JsonEditor', label: '修正内容', defaultValue: '{}' }
    ]
  };

  const activeSchema = useMemo(() => {
    if (schema && schema.fields && schema.fields.length > 0) {
      return schema;
    }
    return defaultQASchema;
  }, [schema, datasetType]);

  const isRequired = (field: TemplateField): boolean => {
    return !!(field.required ||
      field.validation?.required ||
      (Array.isArray(field.rules) && field.rules.some((r: any) => r.required)) ||
      (field.rules && !Array.isArray(field.rules) && typeof field.rules === 'object' && (field.rules as any).required));
  };

  const isFieldMissing = (field: TemplateField, fieldKey: string): boolean => {
    const title = field.title || field.label || field.name || fieldKey;
    return missingFields.includes(title) || missingFields.includes(fieldKey);
  };

  const renderRatingMatrix = (ratingFields: TemplateField[]) => {
    return (
      <div style={{ marginBottom: 12, border: '1px solid #f0f0f0', borderRadius: 6, overflow: 'hidden' }}>
        <div style={{ backgroundColor: '#fafafa', padding: '6px 12px', fontWeight: 600, fontSize: 13, borderBottom: '1px solid #f0f0f0' }}>
          评分矩阵
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <tbody>
            {ratingFields.map((field) => {
              const fieldKey = String(field.key || field.id);
              const fieldId = String(field.id || field.key);
              const fieldValue = getFieldValue(fieldKey);
              const missing = isFieldMissing(field, fieldKey);
              return (
                <tr key={fieldId} style={{ borderBottom: '1px solid #f5f5f5' }}>
                  <td style={{ padding: '6px 12px', fontWeight: 500, width: 80, backgroundColor: '#fafafa', whiteSpace: 'nowrap' }}>
                    {RATING_LABELS[fieldKey] || field.label}
                    {isRequired(field) && <span style={{ color: 'red' }}> *</span>}
                  </td>
                  <td style={{ padding: '6px 12px', backgroundColor: missing ? '#fff2f0' : 'transparent' }}>
                    <Radio.Group
                      value={fieldValue}
                      onChange={(e) => updateField(fieldKey, e.target.value)}
                      disabled={readonly}
                      size="small"
                      optionType="button"
                      buttonStyle="solid"
                    >
                      {field.options?.map((opt) => (
                        <Radio.Button key={opt.value} value={opt.value} style={{ fontSize: 12 }}>{opt.label}</Radio.Button>
                      ))}
                    </Radio.Group>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  };

  const renderField = (field: TemplateField) => {
    const fieldKey = String(field.key || field.id);
    const fieldId = String(field.id || field.key);
    const fieldValue = getFieldValue(fieldKey);
    const fieldAsAny = field as any;
    const fieldType = String(field.type || '').toLowerCase();
    const missing = isFieldMissing(field, fieldKey);
    const missingStyle = missing ? { border: '1px solid #ffccc7', borderRadius: 4, padding: 6, backgroundColor: '#fff2f0' } : {};
    const req = isRequired(field);

    const renderLabel = (labelText?: string) => (
      <label style={{ fontWeight: 500, marginBottom: 4, display: 'block', fontSize: 13 }}>
        {labelText || field.label}
        {req && <span style={{ color: 'red' }}> *</span>}
      </label>
    );

    if (fieldType === 'showitem' || fieldType === 'show_item') {
      const displayValue = inferShowItemValue(field, itemData);
      const format = field.format || fieldAsAny.format || 'text';
      
      if (isEmptyShowValue(displayValue) && shouldHideEmptyShowItem(field)) {
        return null;
      }

      return (
        <div key={fieldId} data-field-key={fieldId} style={{ marginBottom: 8, ...missingStyle }}>
          {renderLabel()}
          {displayValue ? (
            format === 'code' ? (
              <pre style={{ padding: '8px 12px', backgroundColor: '#f5f5f5', borderRadius: 4, fontFamily: 'monospace', fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.5, color: '#111827', margin: 0 }}>
                {displayValue}
              </pre>
            ) : (
              <div style={{ padding: '8px 12px', backgroundColor: '#f5f5f5', borderRadius: 4, whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.5, color: '#111827', fontSize: 13 }}>
                {displayValue}
              </div>
            )
          ) : (
            <div style={{ padding: '8px 12px', backgroundColor: '#fafafa', borderRadius: 4, color: '#9ca3af', fontStyle: 'italic', fontSize: 12 }}>
              暂无预览数据
            </div>
          )}
        </div>
      );
    }

    if (RATING_FIELDS.has(fieldKey) && fieldType === 'radio') {
      return null;
    }

    if (fieldType === 'textinput' || fieldType === 'text_input') {
      return (
        <div key={fieldId} data-field-key={fieldId} style={{ marginBottom: 8, ...missingStyle }}>
          {renderLabel()}
          <Input
            value={fieldValue}
            onChange={(e) => updateField(fieldKey, e.target.value)}
            placeholder={field.placeholder || fieldAsAny.placeholder}
            disabled={readonly}
            size="small"
          />
        </div>
      );
    }

    if (fieldType === 'textarea') {
      const isLongField = ['correction', '修正', '详细理由', 'detail_reason', 'additional', '额外'].some(k => 
        (field.label || '').includes(k) || fieldKey.includes(k)
      );
      const isReasonField = ['详细理由', 'detail_reason', 'reason'].some(k =>
        (field.label || '').includes(k) || fieldKey.includes(k)
      );
      const rows = field.rows || fieldAsAny.rows || 3;

      if (isLongField) {
        return (
          <div key={fieldId} data-field-key={fieldId} style={{ marginBottom: 8 }}>
            <CollapsibleField title={`${field.label || fieldKey}${req ? ' *' : ''}`} defaultCollapsed={!isReasonField && !req}>
              <div style={missingStyle}>
                <TextArea
                  value={fieldValue}
                  onChange={(e) => updateField(fieldKey, e.target.value)}
                  placeholder={field.placeholder || fieldAsAny.placeholder}
                  rows={rows}
                  disabled={readonly}
                />
              </div>
            </CollapsibleField>
          </div>
        );
      }

      return (
        <div key={fieldId} data-field-key={fieldId} style={{ marginBottom: 8, ...missingStyle }}>
          {renderLabel()}
          <TextArea
            value={fieldValue}
            onChange={(e) => updateField(fieldKey, e.target.value)}
            placeholder={field.placeholder || fieldAsAny.placeholder}
            rows={rows}
            disabled={readonly}
          />
        </div>
      );
    }

    if (fieldType === 'radio') {
      return (
        <div key={fieldId} data-field-key={fieldId} style={{ marginBottom: 8, ...missingStyle }}>
          {renderLabel()}
          <Radio.Group
            value={fieldValue}
            onChange={(e) => updateField(fieldKey, e.target.value)}
            disabled={readonly}
            size="small"
            optionType="button"
            buttonStyle="solid"
          >
            {field.options?.map((opt) => (
              <Radio.Button key={opt.value} value={opt.value} style={{ fontSize: 12 }}>{opt.label}</Radio.Button>
            ))}
          </Radio.Group>
        </div>
      );
    }

    if (fieldType === 'checkbox') {
      return (
        <div key={fieldId} data-field-key={fieldId} style={{ marginBottom: 8, ...missingStyle }}>
          {renderLabel()}
          <Checkbox.Group
            value={Array.isArray(fieldValue) ? fieldValue : []}
            onChange={(checkedValues) => updateField(fieldKey, checkedValues)}
            disabled={readonly}
          >
            {field.options?.map((opt) => (
              <Checkbox key={opt.value} value={opt.value}>{opt.label}</Checkbox>
            ))}
          </Checkbox.Group>
        </div>
      );
    }

    if (fieldType === 'select' || fieldType === 'tagselect' || fieldType === 'tag_select') {
      const selectOptions = field.options?.map((opt) => ({ label: opt.label, value: opt.value })) || [];

      if (fieldType === 'tagselect' || fieldType === 'tag_select') {
        return (
          <div key={fieldId} data-field-key={fieldId} style={{ marginBottom: 8, ...missingStyle }}>
            {renderLabel()}
            <Select
              mode="tags"
              style={{ width: '100%' }}
              value={Array.isArray(fieldValue) ? fieldValue : []}
              onChange={(values) => updateField(fieldKey, values)}
              placeholder={field.placeholder || '选择或输入'}
              disabled={readonly}
              size="small"
            >
              {selectOptions.map((opt) => (
                <Select.Option key={opt.value} value={opt.value}>{opt.label}</Select.Option>
              ))}
            </Select>
          </div>
        );
      }

      return (
        <div key={fieldId} data-field-key={fieldId} style={{ marginBottom: 8, ...missingStyle }}>
          {renderLabel()}
          <Select
            style={{ width: '100%' }}
            value={fieldValue || undefined}
            onChange={(value) => updateField(fieldKey, value)}
            placeholder={field.placeholder || '选择'}
            disabled={readonly}
            size="small"
          >
            {selectOptions.map((opt) => (
              <Select.Option key={opt.value} value={opt.value}>{opt.label}</Select.Option>
            ))}
          </Select>
        </div>
      );
    }

    if (fieldType === 'rating') {
      const min = fieldAsAny.min || 1;
      const max = fieldAsAny.max || 5;
      return (
        <div key={fieldId} data-field-key={fieldId} style={{ marginBottom: 8, ...missingStyle }}>
          {renderLabel()}
          <Input
            type="number"
            value={fieldValue}
            onChange={(e) => updateField(fieldKey, parseInt(e.target.value) || min)}
            min={min}
            max={max}
            step={fieldAsAny.step || 1}
            disabled={readonly}
            style={{ width: 100 }}
            size="small"
          />
          <span style={{ marginLeft: 6, color: '#999', fontSize: 12 }}>{min}-{max}</span>
        </div>
      );
    }

    if (fieldType === 'jsoneditor' || fieldType === 'json_editor') {
      const jsonValue = typeof fieldValue === 'object' 
        ? JSON.stringify(fieldValue, null, 2)
        : (fieldValue || fieldAsAny.defaultValue || '{}');
      const isEmpty = jsonValue === '{}' || jsonValue === '' || !jsonValue.trim();
      
      return (
        <div key={fieldId} data-field-key={fieldId} style={{ marginBottom: 8 }}>
          <CollapsibleField title={`${field.label || 'JSON 编辑器'}${req ? ' *' : ''}${isEmpty ? '（空）' : ''}`} defaultCollapsed={true}>
            <div style={missingStyle}>
              <TextArea
                value={jsonValue}
                onChange={(e) => {
                  try {
                    const parsed = JSON.parse(e.target.value);
                    updateField(fieldKey, parsed);
                  } catch {
                    updateField(fieldKey, e.target.value);
                  }
                }}
                rows={4}
                style={{ fontFamily: 'monospace', fontSize: 12 }}
                disabled={readonly}
              />
            </div>
          </CollapsibleField>
        </div>
      );
    }

    if (fieldType === 'llmassist' || fieldType === 'llmtrigger' || fieldType === 'llm_trigger') {
      // Legacy LLMAssist field — 已迁移为系统级能力，不再作为表单字段渲染
      return (
        <div key={fieldId} data-field-key={fieldId} style={{ marginBottom: 8 }}>
          <div style={{ padding: '8px 12px', backgroundColor: '#fffbe6', borderRadius: 6, border: '1px solid #ffe58f' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
              <span style={{ fontSize: 13, fontWeight: 500, color: '#ad8b00' }}>⚠ {field.label || 'LLM 辅助'}（已迁移）</span>
            </div>
            <div style={{ fontSize: 12, color: '#8c6e00' }}>
              AI 辅助已升级为模板系统能力配置，请在模板设计器左侧「系统能力配置」中开启。
              标注工作台的 AI 预审面板由后端统一驱动，不再使用表单字段模式。
            </div>
          </div>
        </div>
      );
    }

    if (fieldType === 'group') {
      const title = fieldAsAny.title || field.label || '分组';
      const description = fieldAsAny.description || '';
      const children = fieldAsAny.children || fieldAsAny.fields || [];

      return (
        <div key={fieldId} data-field-key={fieldId} style={{ marginBottom: 8, border: '1px solid #e8e8e8', borderRadius: 6, overflow: 'hidden' }}>
          <div style={{ backgroundColor: '#fafafa', padding: '6px 12px', fontWeight: 600, fontSize: 13, borderBottom: '1px solid #e8e8e8' }}>
            {title}
            {req && <span style={{ color: 'red' }}> *</span>}
          </div>
          {description && <div style={{ padding: '4px 12px', color: '#666', fontSize: 12 }}>{description}</div>}
          <div style={{ padding: 8 }}>
            {Array.isArray(children) && children.map((child: any) => renderField(child))}
          </div>
        </div>
      );
    }

    if (fieldType === 'tabs') {
      const tabs = fieldAsAny.tabs || ['标签页 1', '标签页 2'];
      return (
        <div key={fieldId} data-field-key={fieldId} style={{ marginBottom: 8, ...missingStyle }}>
          {renderLabel()}
          <div style={{ display: 'flex', gap: 6, borderBottom: '1px solid #e8e8e8', paddingBottom: 6 }}>
            {tabs.map((tab: string, index: number) => (
              <Button key={index} type={index === 0 ? 'primary' : 'default'} size="small" disabled={readonly}>
                {tab}
              </Button>
            ))}
          </div>
        </div>
      );
    }

    return (
      <div key={fieldId} data-field-key={fieldId} style={{ marginBottom: 8 }}>
        <Alert message={`不支持的字段类型：${field.type}`} type="warning" showIcon style={{ ...missingStyle }} />
      </div>
    );
  };

  if (!activeSchema || !activeSchema.fields || activeSchema.fields.length === 0) {
    return <Empty description="暂无表单配置" />;
  }

  const ratingFields = activeSchema.fields.filter(f => 
    RATING_FIELDS.has(String(f.key || f.id)) && String(f.type || '').toLowerCase() === 'radio'
  );
  const nonRatingFields = activeSchema.fields.filter(f => 
    !(RATING_FIELDS.has(String(f.key || f.id)) && String(f.type || '').toLowerCase() === 'radio')
  );

  return (
    <div>
      {ratingFields.length > 0 && renderRatingMatrix(ratingFields)}
      {nonRatingFields.map((field) => (
        <React.Fragment key={String(field.id || field.key)}>
          {renderField(field)}
        </React.Fragment>
      ))}
      {aiAssistText && !internalValue['ai_assist_text'] && (
        <div style={{ marginTop: 8, padding: '8px 12px', backgroundColor: '#f0f5ff', borderRadius: 6, border: '1px solid #d6e4ff' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <span style={{ fontSize: 13, fontWeight: 500 }}>🤖 LLM 辅助信息</span>
            <span style={{ fontSize: 11, color: '#999' }}>（仅供参考，不会覆盖人工详细理由）</span>
          </div>
          <div style={{ fontSize: 12, color: '#333', whiteSpace: 'pre-wrap', marginBottom: 8, padding: '6px 8px', backgroundColor: '#fff', borderRadius: 4 }}>
            {aiAssistText}
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {(() => {
              const reasonKeys = ['reason', 'detail_reason', 'overall_comment'];
              const existingReasonKey = reasonKeys.find(k => internalValue[k] !== undefined && internalValue[k] !== '');
              return (
                <Button size="small" type="dashed" onClick={() => {
                  if (existingReasonKey) {
                    const current = String(internalValue[existingReasonKey] || '').trim();
                    const assistText = String(aiAssistText || '').trim();
                    updateField(existingReasonKey, current ? `${current}\n${assistText}` : assistText);
                  } else {
                    updateField('reason', aiAssistText);
                  }
                }} disabled={readonly}>
                  采纳到详细理由
                </Button>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
};

export default FormRenderer;
