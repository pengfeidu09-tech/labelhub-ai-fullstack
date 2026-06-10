import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Space, Modal, message, Tag } from 'antd';
import { DndContext, DragOverlay, PointerSensor, KeyboardSensor, useSensor, useSensors, closestCenter, useDroppable } from '@dnd-kit/core';
import type { DragStartEvent, DragEndEvent } from '@dnd-kit/core';
import { SortableContext, useSortable, arrayMove, verticalListSortingStrategy, sortableKeyboardCoordinates } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import ComponentPalette, { COMPONENTS } from '../../components/designer/ComponentPalette';
import { SchemaPreview } from '../../components/designer/SchemaPreview';
import FormRenderer from '../../components/renderer/FormRenderer';
import { getTemplateById, updateTemplate, updateTaskTemplate } from '../../api/templates';
import { Template, TemplateSchema, TemplateField } from '../../types/template';

type FieldType = string;

function normalizeFields(fields: TemplateField[]): TemplateField[] {
  const usedKeys = new Set<string>();
  const usedIds = new Set<string>();

  return (fields || []).map((field, index) => {
    let id = field.id || `field_${Date.now()}_${index}`;
    let key = field.key || field.id || '';
    
    key = String(key).trim();
    if (!key) {
      if (field.label) {
        const labelKey = field.label
          .replace(/[\u4e00-\u9fa5]/g, (char) => {
            const pinyinMap: Record<string, string> = {
              '展': 'zhan', '示': 'shi', '项': 'xiang',
              '单': 'dan', '行': 'hang', '文': 'wen', '本': 'ben',
              '多': 'duo', '选': 'xuan', '标': 'biao', '签': 'qian',
              'J': 'json', '编': 'bian', '辑': 'ji',
              'L': 'llm', '辅': 'fu', '助': 'zhu', '分': 'fen', '组': 'zu',
              '评': 'ping', '字': 'zi', '段': 'duan',
              '维': 'wei', '度': 'du'
            };
            return pinyinMap[char] || 'field';
          })
          .replace(/[^a-zA-Z0-9_]/g, '_');
        key = labelKey || `field_${index + 1}`;
      } else {
        key = `field_${index + 1}`;
      }
    }

    // Deduplicate key
    let finalKey = key;
    let count = 1;
    while (usedKeys.has(finalKey)) {
      finalKey = `${key}_${count}`;
      count += 1;
    }
    usedKeys.add(finalKey);

    // Deduplicate id — same logic
    let finalId = String(id);
    let idCount = 1;
    while (usedIds.has(finalId)) {
      finalId = `${id}_${idCount}`;
      idCount += 1;
    }
    usedIds.add(finalId);

    return {
      ...field,
      id: finalId,
      key: finalKey
    };
  });
}

function validateSchema(schema: TemplateSchema): { isValid: boolean; errors: string[] } {
  const errors: string[] = [];
  
  if (!schema.fields || schema.fields.length === 0) {
    errors.push('至少需要一个字段');
    return { isValid: false, errors };
  }

  const keyCount: Record<string, number> = {};
  
  schema.fields.forEach((field, index) => {
    if (!field.id) {
      errors.push(`第 ${index + 1} 个字段缺少 id`);
    }
    
    if (!field.key || !String(field.key).trim()) {
      errors.push(`字段 "${field.label || field.id || '未知'}" 的 key 为空`);
    } else {
      const key = String(field.key).trim();
      keyCount[key] = (keyCount[key] || 0) + 1;
      
      if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(key)) {
        errors.push(`字段 "${field.label || field.id || '未知'}" 的 key 格式不合法，只能包含英文、数字和下划线，且不能以数字开头`);
      }
    }
    
    if (!field.type) {
      errors.push(`字段 "${field.label || field.id || '未知'}" 缺少 type`);
    }
    
    if (field.required && !field.label) {
      errors.push(`必填字段 "${field.key || field.id || '未知'}" 缺少 label`);
    }
    
    if (['radio', 'Radio', 'checkbox', 'Checkbox', 'select', 'Select', 'tag_select', 'TagSelect'].includes(field.type || '')) {
      if (!field.options || field.options.length === 0) {
        errors.push(`选项字段 "${field.label || field.key || '未知'}" 至少需要一个选项`);
      }
    }
  });

  Object.entries(keyCount).forEach(([key, count]) => {
    if (count > 1) {
      errors.push(`key "${key}" 重复出现 ${count} 次`);
    }
  });

  return { isValid: errors.length === 0, errors };
}

function createDefaultField(type: FieldType): TemplateField {
  const id = `field_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

  const getDefaultLabel = (t: string): string => {
    const labelMap: Record<string, string> = {
      ShowItem: '展示项',
      show_item: '展示项',
      TextInput: '单行文本',
      text_input: '单行文本',
      Textarea: '多行文本',
      textarea: '多行文本',
      Radio: '单选',
      radio: '单选',
      Checkbox: '多选',
      checkbox: '多选',
      TagSelect: '标签选择',
      tag_select: '标签选择',
      Select: '下拉选择',
      select: '下拉选择',
      JsonEditor: 'JSON编辑器',
      json_editor: 'JSON编辑器',
      LLMAssist: 'LLM辅助',
      llm_trigger: 'LLM辅助',
      LLMTrigger: 'LLM辅助',
      Group: '分组',
      group: '分组',
      Tabs: '标签页',
      tabs: '标签页',
      Rating: '评分',
      rating: '评分'
    };
    return labelMap[t] || '字段';
  };

  const base = {
    id,
    key: id,
    label: getDefaultLabel(type),
    type: type as TemplateField['type'],
    required: false,
    placeholder: '',
    helpText: '',
    props: {}
  };

  if (['radio', 'Radio', 'checkbox', 'Checkbox', 'select', 'Select', 'tag_select', 'TagSelect'].includes(type)) {
    return {
      ...base,
      options: [
        { label: '选项 A', value: 'A' },
        { label: '选项 B', value: 'B' }
      ]
    } as TemplateField;
  }

  if (['show_item', 'ShowItem'].includes(type)) {
    return {
      ...base,
      value: '{{item.prompt}}',
      format: 'markdown' as const,
      binding: '{{item.prompt}}'
    } as TemplateField;
  }

  if (['rating', 'Rating'].includes(type)) {
    return {
      ...base,
      min: 1,
      max: 5,
      step: 1
    } as TemplateField;
  }

  if (['llm_trigger', 'LLMTrigger', 'LLMAssist'].includes(type)) {
    return {
      ...base,
      buttonText: '生成建议',
      promptTemplate: '',
      targetField: ''
    } as TemplateField;
  }

  if (['json_editor', 'JsonEditor'].includes(type)) {
    return {
      ...base,
      defaultValue: '{}'
    } as TemplateField;
  }

  return base as TemplateField;
}

/** 画布空状态落区 */
function EmptyCanvasDropZone() {
  const { setNodeRef, isOver } = useDroppable({ id: 'canvas-empty-zone' });
  return (
    <div ref={setNodeRef} style={{
      color: '#999', padding: 24, textAlign: 'center', minHeight: 200,
      border: isOver ? '2px dashed #1677ff' : '1px dashed #ddd',
      borderRadius: 8, background: isOver ? '#e6f4ff' : '#fafafa',
      transition: 'all 0.2s'
    }}>
      将左侧物料拖拽到这里，或点击物料快速添加
    </div>
  );
}

/** 画布容器落区（有组件时也可拖拽到底部追加） */
function CanvasDropZoneWrapper({ children, isPaletteDragging }: { children: React.ReactNode; isPaletteDragging: boolean }) {
  const { setNodeRef, isOver } = useDroppable({ id: 'canvas-drop-zone' });
  return (
    <div ref={setNodeRef} style={{
      flex: 1, minWidth: 0, background: '#fff',
      border: isPaletteDragging || isOver ? '2px solid #1677ff' : '1px solid #e5e7eb',
      borderRadius: 10, padding: 16,
      minHeight: 600, maxHeight: 'calc(100vh - 180px)',
      overflowY: 'auto', boxSizing: 'border-box',
      transition: 'border-color 0.2s'
    }}>
      {children}
    </div>
  );
}

/** 画布可排序字段卡片 */
function SortableFieldCard({ field, index, selectedFieldId, totalFields,
  onSelectField, onMoveField, onDuplicateField, onDeleteField }: {
  field: TemplateField; index: number; selectedFieldId: string | null; totalFields: number;
  onSelectField: (id: string) => void;
  onMoveField: (id: string, direction: 'up' | 'down') => void;
  onDuplicateField: (id: string) => void;
  onDeleteField: (id: string) => void;
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: field.id,
    data: { origin: 'canvas' }
  });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
    border: selectedFieldId === field.id ? '2px solid #1677ff' : '1px solid #e5e7eb',
    borderRadius: 10,
    padding: 16,
    marginBottom: 12,
    cursor: 'default',
    background: selectedFieldId === field.id ? '#e6f4ff' : '#fff',
    position: 'relative'
  };

  return (
    <div ref={setNodeRef} style={style}
      onClick={() => onSelectField(field.id)}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, flex: 1, minWidth: 0 }}>
          {/* 拖拽手柄 — listeners + attributes 只绑在这里 */}
          <span
            ref={setActivatorNodeRef}
            {...attributes}
            {...listeners}
            style={{
              cursor: 'grab',
              color: '#999',
              fontSize: 14,
              userSelect: 'none',
              touchAction: 'none',
              lineHeight: '20px',
              flexShrink: 0
            }}
          >
            ⠿
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: 14 }}>
              {field.label || field.key || field.id}
            </div>
            <div style={{ color: '#666', fontSize: 12, marginTop: 4 }}>
              Type: {field.type}
            </div>
            <div style={{ color: '#999', fontSize: 12, marginTop: 2 }}>
              Key: {field.key}
            </div>
          </div>
        </div>
        {field.required && (
          <span style={{ padding: '2px 8px', background: '#fff2f0', color: '#ff4d4f', fontSize: 12, borderRadius: 4 }}>必填</span>
        )}
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); if (index > 0) onMoveField(field.id, 'up'); }}
          disabled={index === 0}
          style={{ padding: '4px 12px', fontSize: 12, border: '1px solid #ddd', borderRadius: 4, cursor: index === 0 ? 'not-allowed' : 'pointer', backgroundColor: index === 0 ? '#f5f5f5' : '#fff' }}
        >上移</button>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); if (index < totalFields - 1) onMoveField(field.id, 'down'); }}
          disabled={index === totalFields - 1}
          style={{ padding: '4px 12px', fontSize: 12, border: '1px solid #ddd', borderRadius: 4, cursor: index === totalFields - 1 ? 'not-allowed' : 'pointer', backgroundColor: index === totalFields - 1 ? '#f5f5f5' : '#fff' }}
        >下移</button>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onDuplicateField(field.id); }}
          style={{ padding: '4px 12px', fontSize: 12, border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer', backgroundColor: '#fff' }}
        >复制</button>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onDeleteField(field.id); }}
          style={{ padding: '4px 12px', fontSize: 12, border: '1px solid #ff4d4f', borderRadius: 4, cursor: 'pointer', backgroundColor: '#fff', color: '#ff4d4f' }}
        >删除</button>
      </div>
    </div>
  );
}

/** 物料拖拽预览浮层 */
function PaletteDragOverlay({ type }: { type: string }) {
  const comp = COMPONENTS.find(c => c.type === type);
  return (
    <div style={{
      padding: 12, background: '#fff', border: '2px solid #1677ff',
      borderRadius: 8, opacity: 0.9, boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
      minWidth: 120
    }}>
      <div style={{ fontWeight: 600, fontSize: 14 }}>{comp?.name || type}</div>
      <div style={{ color: '#666', fontSize: 12, marginTop: 4 }}>{comp?.description || ''}</div>
    </div>
  );
}

/** 画布字段拖拽预览浮层 */
function CanvasFieldDragOverlay({ fieldId, fields }: { fieldId: string; fields: TemplateField[] }) {
  const field = fields.find(f => f.id === fieldId);
  if (!field) return null;
  return (
    <div style={{
      padding: 16, background: '#fff', border: '2px solid #1677ff',
      borderRadius: 10, opacity: 0.9, boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
      minWidth: 200
    }}>
      <div style={{ fontWeight: 600, fontSize: 14 }}>{field.label || field.key}</div>
      <div style={{ color: '#666', fontSize: 12, marginTop: 4 }}>Type: {field.type}</div>
    </div>
  );
}

const TemplateDesignerPage: React.FC = () => {
  const { templateId } = useParams<{ templateId: string }>();
  const [searchParams] = useSearchParams();
  const taskId = searchParams.get('task_id') ? Number(searchParams.get('task_id')) : null;
  const navigate = useNavigate();
  const [template, setTemplate] = useState<Template | null>(null);
  const [schema, setSchema] = useState<TemplateSchema | null>(null);
  const [selectedFieldId, setSelectedFieldId] = useState<string | null>(null);
  const [schemaPreviewVisible, setSchemaPreviewVisible] = useState(false);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewFormData, setPreviewFormData] = useState<Record<string, any>>({});
  const [saving, setSaving] = useState(false);

  const MOCK_ITEM_DATA = {
    prompt: '请判断下面这个模型回答是否准确、完整、安全，并给出详细理由。',
    question: '什么是人工智能？',
    model_answer: '人工智能是让机器模拟人类智能的技术，包括学习、推理、感知和自然语言处理等能力。',
    reference: '人工智能是研究如何让机器具备感知、学习、推理、决策和生成等智能行为的技术领域。',
    media_type: 'text',
    media_url: 'https://example.com/demo',
    url: 'https://example.com/demo',
    content: '这是一条用于模板预览的模拟数据内容。',
    category: 'AI基础知识',
    difficulty: '中等',
    expected_dimensions: '相关性、准确性、完整性、安全性',
    answer_a: '回答 A：人工智能是一种模拟人类智能的技术。',
    answer_b: '回答 B：人工智能主要指机器学习和深度学习。'
  };

  const pageStyle: React.CSSProperties = {
    height: 'calc(100vh - 56px)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    background: '#f5f5f5'
  };

  useEffect(() => {
    if (templateId) {
      fetchTemplate(parseInt(templateId));
    }
  }, [templateId]);

  const generateDefaultFields = (datasetType: string): TemplateField[] => {
    if (datasetType === 'qa_quality') {
      return [
        createDefaultField('ShowItem'),
        createDefaultField('Radio'),
        createDefaultField('Textarea')
      ];
    }
    return [createDefaultField('ShowItem')];
  };

  const fetchTemplate = async (id: number) => {
    try {
      const res = await getTemplateById(id);
      setTemplate(res);
      
      let currentSchema = res.schema as TemplateSchema;
      if (!currentSchema.fields || currentSchema.fields.length === 0) {
        currentSchema = {
          ...currentSchema,
          fields: generateDefaultFields(res.dataset_type)
        };
      } else {
        currentSchema = {
          ...currentSchema,
          fields: normalizeFields(currentSchema.fields)
        };
      }

      // Legacy migration: if schema contains LLMAssist / llm_trigger fields,
      // auto-enable ai_assist and mark fields with _legacy flag
      const legacyLlmTypes = new Set(['llmassist', 'llmtrigger', 'llm_trigger', 'LLMAssist', 'LLMTrigger']);
      const hasLegacyLlm = currentSchema.fields?.some(f => legacyLlmTypes.has(String(f.type)));
      if (hasLegacyLlm) {
        const aiAssist = (currentSchema as any).ai_assist || {};
        if (!aiAssist.enabled) {
          console.warn('[Designer] Legacy LLMAssist field detected — auto-enabling ai_assist.enabled');
          currentSchema = {
            ...currentSchema,
            ai_assist: { ...aiAssist, enabled: true, _migrated_from_field: true }
          } as TemplateSchema;
        }
      }

      setSchema(currentSchema);
    } catch (error) {
      message.error('获取模板失败');
      console.error(error);
    }
  };

  const handleSave = async () => {
    if (!template || !schema) {
      message.warning('模板或 Schema 为空');
      return;
    }
    
    const validation = validateSchema(schema);
    if (!validation.isValid) {
      validation.errors.forEach(err => {
        console.error('[Designer] Validation Error:', err);
      });
      message.error(`校验失败：${validation.errors.join('；')}`);
      return;
    }
    
    setSaving(true);
    try {
      const normalizedSchema = {
        ...schema,
        fields: normalizeFields(schema.fields || [])
      };
      
      const payload = {
        name: template.name,
        description: template.description,
        dataset_type: template.dataset_type,
        schema_version: template.schema_version,
        schema: normalizedSchema
      };

      if (taskId) {
        // 有 task_id 时使用任务模板更新接口
        await updateTaskTemplate(taskId, payload);
      } else {
        // 否则使用通用模板更新接口
        await updateTemplate(template.id, payload);
      }
      message.success('模板保存成功');
    } catch (error) {
      message.error('模板保存失败');
      console.error(error);
    } finally {
      setSaving(false);
    }
  };

  const handleAddField = (type: FieldType) => {

    const newField = createDefaultField(type);

    setSchema(prev => {
      if (!prev) return prev;
      const prevFields = Array.isArray(prev.fields) ? prev.fields : [];
      const nextSchema = {
        ...prev,
        fields: [...prevFields, newField]
      };
      return nextSchema;
    });

    setSelectedFieldId(newField.id);
  };

  const handleDeleteField = (id: string) => {
    setSchema(prev => {
      if (!prev || !prev.fields) return prev;
      const index = prev.fields.findIndex(f => f.id === id);
      const newFields = prev.fields.filter(f => f.id !== id);
      
      if (selectedFieldId === id) {
        if (newFields.length > 0) {
          const newIndex = Math.min(index, newFields.length - 1);
          setTimeout(() => setSelectedFieldId(newFields[newIndex].id), 0);
        } else {
          setTimeout(() => setSelectedFieldId(null), 0);
        }
      }
      
      return {
        ...prev,
        fields: newFields
      };
    });
  };

  const handleDuplicateField = (id: string) => {
    setSchema(prev => {
      if (!prev || !prev.fields) return prev;
      const field = prev.fields.find(f => f.id === id);
      if (!field) return prev;
      
      const baseKey = field.key || 'field';
      let newKey = `${baseKey}_copy`;
      let count = 1;
      while (prev.fields.some(f => f.key === newKey)) {
        newKey = `${baseKey}_copy_${count}`;
        count++;
      }
      
      const newField = {
        ...field,
        id: `field_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        key: newKey,
        label: `${field.label || ''} 副本`
      };
      
      setTimeout(() => setSelectedFieldId(newField.id), 0);
      
      return {
        ...prev,
        fields: [...prev.fields, newField]
      };
    });
  };

  const handleMoveField = (id: string, direction: 'up' | 'down') => {
    setSchema(prev => {
      if (!prev || !prev.fields) return prev;
      const index = prev.fields.findIndex(f => f.id === id);
      if (direction === 'up' && index > 0) {
        const newFields = [...prev.fields];
        [newFields[index - 1], newFields[index]] = [newFields[index], newFields[index - 1]];
        return { ...prev, fields: newFields };
      }
      if (direction === 'down' && index < prev.fields.length - 1) {
        const newFields = [...prev.fields];
        [newFields[index], newFields[index + 1]] = [newFields[index + 1], newFields[index]];
        return { ...prev, fields: newFields };
      }
      return prev;
    });
  };

  const handleUpdateField = (id: string, updates: Partial<TemplateField>) => {
    setSchema(prev => {
      if (!prev || !prev.fields) return prev;
      return {
        ...prev,
        fields: prev.fields.map(f => f.id === id ? { ...f, ...updates } : f)
      };
    });
  };

  const selectedField = schema?.fields?.find(f => f.id === selectedFieldId) || null;

  // --- @dnd-kit 拖拽支持 ---
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );
  const [activeDragItem, setActiveDragItem] = useState<{ id: string; data: any } | null>(null);

  const handleDragStart = (event: DragStartEvent) => {
    setActiveDragItem({ id: String(event.active.id), data: event.active.data.current });
  };

  const handleDragCancel = () => {
    setActiveDragItem(null);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveDragItem(null);
    if (!over) return;

    const activeData = active.data.current;

    // CASE 1: 物料 → 画布（新增组件）
    if (activeData?.origin === 'palette') {
      const fieldType = activeData.type;
      const newField = createDefaultField(fieldType);

      const overId = String(over.id);
      if (overId === 'canvas-empty-zone' || overId === 'canvas-drop-zone') {
        // 画布落区 → 追加到末尾
        setSchema(prev => {
          if (!prev) return prev;
          const fields = [...(prev.fields || []), newField];
          return { ...prev, fields };
        });
      } else {
        // over.id 是字段 id → 插到该字段后面
        const overIndex = schema?.fields?.findIndex(f => f.id === overId) ?? -1;
        const insertIndex = overIndex >= 0 ? overIndex + 1 : (schema?.fields?.length ?? 0);
        setSchema(prev => {
          if (!prev) return prev;
          const fields = [...(prev.fields || [])];
          fields.splice(insertIndex, 0, newField);
          return { ...prev, fields };
        });
      }
      setSelectedFieldId(newField.id);
      return;
    }

    // CASE 2: 画布内排序
    if (active.id !== over.id) {
      const oldIndex = schema?.fields?.findIndex(f => f.id === String(active.id)) ?? -1;
      const newIndex = schema?.fields?.findIndex(f => f.id === String(over.id)) ?? -1;
      if (oldIndex >= 0 && newIndex >= 0) {
        setSchema(prev => {
          if (!prev || !prev.fields) return prev;
          return { ...prev, fields: arrayMove(prev.fields, oldIndex, newIndex) };
        });
      }
    }
  };

  return (
    <div style={pageStyle}>
      {/* Toolbar */}
      <div className="designer-toolbar" style={{ 
        padding: '12px 24px', 
        borderBottom: '1px solid #e8e8e8', 
        backgroundColor: '#fff', 
        flexShrink: 0 
      }}>
        <Space>
          <Button onClick={() => navigate(taskId ? `/owner/tasks/${taskId}` : '/owner/templates')} htmlType="button">← {taskId ? '返回任务' : '返回列表'}</Button>
          <Button type="primary" onClick={handleSave} loading={saving} htmlType="button">保存模板</Button>
          <Button onClick={() => setPreviewVisible(true)} htmlType="button">预览渲染</Button>
          <Button onClick={() => setSchemaPreviewVisible(true)} htmlType="button">查看 Schema</Button>
          <Button onClick={() => navigate(`/owner/templates/clone/${templateId}`)} htmlType="button">复制为新版本</Button>
        </Space>
        {template && (
          <div style={{ marginTop: 8, fontSize: 14, color: '#666' }}>
            正在编辑：<strong>{template.name}</strong>  (版本: {template.schema_version})
            {taskId && (
              <Tag color="blue" style={{ marginLeft: 12 }}>绑定任务 #{taskId}</Tag>
            )}
          </div>
        )}
      </div>

      {/* Main Layout - Flex (DndContext wraps all three panels) */}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onDragCancel={handleDragCancel}
      >
      <div
        style={{
          display: 'flex',
          width: '100%',
          gap: 16,
          padding: 16,
          boxSizing: 'border-box'
        }}
      >
        {/* Left Panel - Material Palette */}
        <div
          style={{
            width: 280,
            flexShrink: 0,
            background: '#fff',
            border: '1px solid #e5e7eb',
            borderRadius: 10,
            padding: 16,
            minHeight: 600,
            maxHeight: 'calc(100vh - 180px)',
            overflowY: 'auto',
            boxSizing: 'border-box'
          }}
        >
          <h3 style={{ marginBottom: 16, fontSize: 14, fontWeight: 600, color: '#1f1f1f' }}>物料区</h3>
          <ComponentPalette
            onAddField={handleAddField}
            aiAssistEnabled={!!(schema as any)?.ai_assist?.enabled}
            onAiAssistToggle={(enabled) => {
              setSchema(prev => {
                if (!prev) return prev;
                return {
                  ...prev,
                  ai_assist: { ...(prev as any).ai_assist, enabled }
                } as TemplateSchema;
              });
            }}
          />
        </div>

        {/* Center Panel - Canvas (Droppable + Sortable) */}
        <CanvasDropZoneWrapper isPaletteDragging={activeDragItem?.data?.origin === 'palette'}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, color: '#1f1f1f' }}>画布区</h3>
            <span style={{ fontSize: 12, color: '#666' }}>当前字段数：{schema?.fields?.length || 0}</span>
          </div>

          {(!schema?.fields || schema.fields.length === 0) ? (
            <EmptyCanvasDropZone />
          ) : (
            <SortableContext items={schema.fields.map(f => f.id)} strategy={verticalListSortingStrategy}>
              {schema.fields.map((field, index) => (
                <SortableFieldCard
                  key={field.id}
                  field={field}
                  index={index}
                  selectedFieldId={selectedFieldId}
                  totalFields={schema.fields.length}
                  onSelectField={setSelectedFieldId}
                  onMoveField={handleMoveField}
                  onDuplicateField={handleDuplicateField}
                  onDeleteField={handleDeleteField}
                />
              ))}
            </SortableContext>
          )}
        </CanvasDropZoneWrapper>

        {/* Right Panel - Properties */}
        <div
          style={{
            width: 340,
            flexShrink: 0,
            minWidth: 0,
            height: 'calc(100vh - 180px)',
            overflowY: 'auto',
            overflowX: 'hidden',
            background: '#fff',
            border: '1px solid #e5e7eb',
            borderRadius: 10,
            padding: 16,
            boxSizing: 'border-box'
          }}
        >
          <h3 style={{ marginBottom: 16, fontSize: 14, fontWeight: 600, color: '#1f1f1f' }}>属性配置</h3>

          {selectedField ? (
            <div>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>Label</label>
                <input
                  value={selectedField.label || ''}
                  onChange={(e) => handleUpdateField(selectedField.id, { label: e.target.value })}
                  style={{ width: '100%', padding: '8px 12px', boxSizing: 'border-box', border: '1px solid #d9d9d9', borderRadius: 6, fontSize: 13 }}
                />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>Key</label>
                <input
                  value={selectedField.key || ''}
                  onChange={(e) => handleUpdateField(selectedField.id, { key: e.target.value })}
                  style={{ 
                    width: '100%', 
                    padding: '8px 12px', 
                    boxSizing: 'border-box', 
                    border: '1px solid #d9d9d9', 
                    borderRadius: 6, 
                    fontSize: 13 
                  }}
                />
                {selectedField.key && (() => {
                  const key = String(selectedField.key).trim();
                  const isValid = /^[a-zA-Z_][a-zA-Z0-9_]*$/.test(key);
                  const isDuplicate = schema?.fields?.filter(f => f.id !== selectedField.id).some(f => String(f.key).trim() === key);
                  if (!key) {
                    return <div style={{ color: '#ff4d4f', fontSize: 12, marginTop: 4 }}>Key 不能为空</div>;
                  }
                  if (!isValid) {
                    return <div style={{ color: '#ff4d4f', fontSize: 12, marginTop: 4 }}>Key 只能包含英文、数字和下划线，且不能以数字开头</div>;
                  }
                  if (isDuplicate) {
                    return <div style={{ color: '#ff4d4f', fontSize: 12, marginTop: 4 }}>Key 重复</div>;
                  }
                  return null;
                })()}
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>Type</label>
                <input
                  value={selectedField.type || ''}
                  disabled
                  style={{ width: '100%', padding: '8px 12px', boxSizing: 'border-box', border: '1px solid #d9d9d9', borderRadius: 6, fontSize: 13, backgroundColor: '#f5f5f5' }}
                />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>Required</label>
                <input
                  type="checkbox"
                  checked={selectedField.required || false}
                  onChange={(e) => handleUpdateField(selectedField.id, { required: e.target.checked })}
                  style={{ transform: 'scale(1.2)' }}
                />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>Placeholder</label>
                <input
                  value={(selectedField.props?.placeholder as string) || ''}
                  onChange={(e) => {
                    const props = { ...(selectedField.props || {}), placeholder: e.target.value };
                    handleUpdateField(selectedField.id, { props });
                  }}
                  style={{ width: '100%', padding: '8px 12px', boxSizing: 'border-box', border: '1px solid #d9d9d9', borderRadius: 6, fontSize: 13 }}
                />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>HelpText</label>
                <textarea
                  value={(selectedField.props?.helpText as string) || ''}
                  onChange={(e) => {
                    const props = { ...(selectedField.props || {}), helpText: e.target.value };
                    handleUpdateField(selectedField.id, { props });
                  }}
                  style={{ width: '100%', padding: '8px 12px', boxSizing: 'border-box', border: '1px solid #d9d9d9', borderRadius: 6, fontSize: 13, minHeight: 60 }}
                />
              </div>

              {['radio', 'Radio', 'checkbox', 'Checkbox', 'select', 'Select', 'tag_select', 'TagSelect'].includes(selectedField.type || '') && (
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', marginBottom: 8, fontSize: 13, fontWeight: 500, color: '#333' }}>Options</label>
                  <div style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>选项名称 / 选项值</div>
                  <div style={{ border: '1px solid #d9d9d9', borderRadius: 6, padding: 8 }}>
                    {(selectedField.options || []).map((opt, index) => (
                      <div
                        key={index}
                        style={{
                          border: '1px solid #f0f0f0',
                          borderRadius: 8,
                          padding: 8,
                          marginBottom: 8,
                          background: '#fafafa',
                          boxSizing: 'border-box',
                          width: '100%'
                        }}
                      >
                        <input
                          value={opt.label}
                          onChange={(e) => {
                            const options = [...(selectedField.options || [])];
                            options[index] = { ...options[index], label: e.target.value };
                            handleUpdateField(selectedField.id, { options });
                          }}
                          placeholder="选项名称"
                          style={{
                            width: '100%',
                            padding: '6px 10px',
                            boxSizing: 'border-box',
                            border: '1px solid #d9d9d9',
                            borderRadius: 4,
                            fontSize: 12,
                            minWidth: 0
                          }}
                        />
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: 'minmax(0, 1fr) 56px',
                            gap: 8,
                            marginTop: 8,
                            alignItems: 'center'
                          }}
                        >
                          <input
                            value={opt.value}
                            onChange={(e) => {
                              const options = [...(selectedField.options || [])];
                              options[index] = { ...options[index], value: e.target.value };
                              handleUpdateField(selectedField.id, { options });
                            }}
                            placeholder="选项值"
                            style={{
                              width: '100%',
                              padding: '6px 10px',
                              boxSizing: 'border-box',
                              border: '1px solid #d9d9d9',
                              borderRadius: 4,
                              fontSize: 12,
                              minWidth: 0
                            }}
                          />
                          <button
                            type="button"
                            onClick={() => {
                              if ((selectedField.options?.length || 0) <= 1) {
                                message.warning('至少保留一个选项');
                                return;
                              }
                              const options = selectedField.options?.filter((_, i) => i !== index) || [];
                              handleUpdateField(selectedField.id, { options });
                            }}
                            style={{
                              width: 56,
                              padding: '6px',
                              fontSize: 12,
                              border: '1px solid #ff4d4f',
                              borderRadius: 4,
                              cursor: 'pointer',
                              backgroundColor: '#fff',
                              color: '#ff4d4f',
                              boxSizing: 'border-box'
                            }}
                          >删除</button>
                        </div>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() => {
                        const options = [...(selectedField.options || []), { label: `选项 ${(selectedField.options?.length || 0) + 1}`, value: `opt_${Date.now()}` }];
                        handleUpdateField(selectedField.id, { options });
                      }}
                      style={{
                        width: '100%',
                        padding: '8px',
                        fontSize: 12,
                        border: '1px dashed #d9d9d9',
                        borderRadius: 4,
                        cursor: 'pointer',
                        backgroundColor: '#fafafa',
                        boxSizing: 'border-box'
                      }}
                    >+ 添加选项</button>
                  </div>
                </div>
              )}

              {['show_item', 'ShowItem'].includes(selectedField.type || '') && (
                <>
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>Value</label>
                    <input
                      value={selectedField.binding || ''}
                      onChange={(e) => handleUpdateField(selectedField.id, { binding: e.target.value })}
                      style={{ width: '100%', padding: '8px 12px', boxSizing: 'border-box', border: '1px solid #d9d9d9', borderRadius: 6, fontSize: 13 }}
                    />
                  </div>
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>Format</label>
                    <select
                      value={selectedField.format || 'text'}
                      onChange={(e) => handleUpdateField(selectedField.id, { format: e.target.value as any })}
                      style={{ width: '100%', padding: '8px 12px', boxSizing: 'border-box', border: '1px solid #d9d9d9', borderRadius: 6, fontSize: 13 }}
                    >
                      <option value="text">text</option>
                      <option value="markdown">markdown</option>
                      <option value="code">code</option>
                    </select>
                  </div>
                </>
              )}

              {['rating', 'Rating'].includes(selectedField.type || '') && (
                <>
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>Min</label>
                    <input
                      type="number"
                      value={(selectedField as any).min || 1}
                      onChange={(e) => handleUpdateField(selectedField.id, { min: parseInt(e.target.value) || 1 } as any)}
                      style={{ width: '100%', padding: '8px 12px', boxSizing: 'border-box', border: '1px solid #d9d9d9', borderRadius: 6, fontSize: 13 }}
                    />
                  </div>
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>Max</label>
                    <input
                      type="number"
                      value={(selectedField as any).max || 5}
                      onChange={(e) => handleUpdateField(selectedField.id, { max: parseInt(e.target.value) || 5 } as any)}
                      style={{ width: '100%', padding: '8px 12px', boxSizing: 'border-box', border: '1px solid #d9d9d9', borderRadius: 6, fontSize: 13 }}
                    />
                  </div>
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>Step</label>
                    <input
                      type="number"
                      value={(selectedField as any).step || 1}
                      onChange={(e) => handleUpdateField(selectedField.id, { step: parseInt(e.target.value) || 1 } as any)}
                      style={{ width: '100%', padding: '8px 12px', boxSizing: 'border-box', border: '1px solid #d9d9d9', borderRadius: 6, fontSize: 13 }}
                    />
                  </div>
                </>
              )}

              {['llm_trigger', 'LLMTrigger', 'LLMAssist'].includes(selectedField.type || '') && (
                <div style={{ padding: 12, backgroundColor: '#fffbe6', border: '1px solid #ffe58f', borderRadius: 8 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: '#ad8b00', marginBottom: 6 }}>⚠ 已迁移为系统能力</div>
                  <div style={{ fontSize: 12, color: '#8c6e00', lineHeight: 1.8 }}>
                    LLM 辅助字段已升级为模板级系统能力配置。请在左侧「系统能力配置」区域开启 AI 辅助审核。
                    该字段在标注工作台中将显示为迁移提示，不再渲染旧的模拟生成面板。
                    建议在下次模板版本迭代时移除此字段。
                  </div>
                </div>
              )}

              {['group', 'Group'].includes(selectedField.type || '') && (
                <>
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>Title</label>
                    <input
                      value={(selectedField as any).title || selectedField.label || '分组'}
                      onChange={(e) => handleUpdateField(selectedField.id, { title: e.target.value } as any)}
                      style={{ width: '100%', padding: '8px 12px', boxSizing: 'border-box', border: '1px solid #d9d9d9', borderRadius: 6, fontSize: 13 }}
                    />
                  </div>
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>Description</label>
                    <textarea
                      value={(selectedField as any).description || ''}
                      onChange={(e) => handleUpdateField(selectedField.id, { description: e.target.value } as any)}
                      style={{ width: '100%', padding: '8px 12px', boxSizing: 'border-box', border: '1px solid #d9d9d9', borderRadius: 6, fontSize: 13, minHeight: 60 }}
                      placeholder="分组描述（可选）"
                    />
                  </div>
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#333' }}>
                      <input
                        type="checkbox"
                        checked={(selectedField as any).collapsible || false}
                        onChange={(e) => handleUpdateField(selectedField.id, { collapsible: e.target.checked } as any)}
                        style={{ transform: 'scale(1.2)' }}
                      />
                      Collapsible（可折叠）
                    </label>
                  </div>
                </>
              )}

              {['tabs', 'Tabs'].includes(selectedField.type || '') && (
                <>
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>Tabs</label>
                    <textarea
                      value={((selectedField as any).tabs || ['标签页 1', '标签页 2']).join(',')}
                      onChange={(e) => {
                        const tabsText = e.target.value;
                        const tabs = tabsText.split(',').map(t => t.trim()).filter(t => t);
                        if (tabs.length === 0) tabs.push('标签页 1');
                        handleUpdateField(selectedField.id, { tabs } as any);
                      }}
                      style={{ width: '100%', padding: '8px 12px', boxSizing: 'border-box', border: '1px solid #d9d9d9', borderRadius: 6, fontSize: 13, minHeight: 60 }}
                      placeholder="使用逗号分隔，例如：基础信息,审核信息,修订记录"
                    />
                    <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>使用逗号分隔，例如：基础信息,审核信息,修订记录</div>
                  </div>
                </>
              )}

              {['json_editor', 'JsonEditor'].includes(selectedField.type || '') && (
                <>
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500, color: '#333' }}>Default Value</label>
                    <textarea
                      value={typeof (selectedField as any).defaultValue === 'object' 
                        ? JSON.stringify((selectedField as any).defaultValue, null, 2)
                        : String((selectedField as any).defaultValue || '{}')}
                      onChange={(e) => {
                        try {
                          const defaultValue = JSON.parse(e.target.value);
                          handleUpdateField(selectedField.id, { defaultValue } as any);
                        } catch {
                          handleUpdateField(selectedField.id, { defaultValue: e.target.value } as any);
                        }
                      }}
                      style={{ width: '100%', padding: '8px 12px', boxSizing: 'border-box', border: '1px solid #d9d9d9', borderRadius: 6, fontSize: 13, minHeight: 80 }}
                      placeholder="JSON 格式，例如：{} 或 {'key': 'value'}"
                    />
                  </div>
                </>
              )}
            </div>
          ) : (
            <div style={{ color: '#999', textAlign: 'center', padding: '40px 20px' }}>
              请从画布中选择一个字段
            </div>
          )}
        </div>
      </div>

      <DragOverlay dropAnimation={null}>
        {activeDragItem ? (
          activeDragItem.data?.origin === 'palette' ? (
            <PaletteDragOverlay type={activeDragItem.data.type} />
          ) : (
            <CanvasFieldDragOverlay fieldId={activeDragItem.id} fields={schema?.fields || []} />
          )
        ) : null}
      </DragOverlay>
      </DndContext>

      {/* Schema Preview Modal */}
      {schema && (
        <SchemaPreview
          visible={schemaPreviewVisible}
          schema={schema}
          onCancel={() => setSchemaPreviewVisible(false)}
        />
      )}

      {/* Preview Modal */}
      {schema && (
        <Modal
          title={`模板预览：${template?.name || '未命名模板'}`}
          open={previewVisible}
          onCancel={() => setPreviewVisible(false)}
          footer={[
            <Button key="close" onClick={() => setPreviewVisible(false)} htmlType="button">关闭</Button>
          ]}
          width={900}
        >
          <div style={{
            backgroundColor: '#eff6ff',
            padding: 12,
            borderRadius: 8,
            marginBottom: 16,
            fontSize: 13,
            color: '#1e40af'
          }}>
            当前为模板预览模式，展示数据为 Mock 数据，不会提交真实标注结果。
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16 }}>
            <div style={{ 
              border: '1px solid #e8e8e8', 
              borderRadius: 8, 
              padding: 16, 
              maxHeight: 'calc(80vh - 140px)', 
              overflowY: 'auto' 
            }}>
              <FormRenderer
                key={schema ? JSON.stringify(schema.fields) : 'empty'}
                schema={schema}
                itemData={MOCK_ITEM_DATA}
                onChange={(formData) => {
                  setPreviewFormData(formData);
                }}
              />
            </div>
            <div style={{ 
              border: '1px solid #e8e8e8', 
              borderRadius: 8, 
              padding: 16, 
              maxHeight: 'calc(80vh - 140px)', 
              overflowY: 'auto' 
            }}>
              <h4 style={{ margin: '0 0 12px 0', fontSize: 14, fontWeight: 600 }}>表单数据 FormData</h4>
              {Object.keys(previewFormData).length === 0 ? (
                <div style={{ 
                  color: '#9ca3af', 
                  fontStyle: 'italic', 
                  padding: 12 
                }}>
                  暂无填写数据
                </div>
              ) : (
                <pre style={{ 
                  fontSize: 12, 
                  backgroundColor: '#f9fafb', 
                  padding: 12, 
                  borderRadius: 8,
                  overflowX: 'hidden',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  maxHeight: 'calc(80vh - 190px)',
                  margin: 0,
                  lineHeight: 1.6
                }}>
                  {JSON.stringify(previewFormData, null, 2)}
                </pre>
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

export default TemplateDesignerPage;
