import React from 'react';
import { Button, Switch, Tooltip } from 'antd';
import { useDraggable } from '@dnd-kit/core';

export interface ComponentItem {
  type: string;
  name: string;
  description: string;
}

interface ComponentPaletteProps {
  onAddField: (type: string) => void;
  aiAssistEnabled?: boolean;
  onAiAssistToggle?: (enabled: boolean) => void;
}

/** 表单字段物料 — 可拖入画布 */
export const FIELD_COMPONENTS: ComponentItem[] = [
  { type: 'ShowItem', name: '展示项', description: '展示只读内容，支持多种格式' },
  { type: 'TextInput', name: '单行文本', description: '单行文本输入框' },
  { type: 'Textarea', name: '多行文本', description: '多行文本输入框' },
  { type: 'Radio', name: '单选', description: '单选按钮组' },
  { type: 'Checkbox', name: '多选', description: '多选框组' },
  { type: 'TagSelect', name: '标签选择', description: '标签式选择器' },
  { type: 'JsonEditor', name: 'JSON编辑器', description: 'JSON数据编辑器' },
  { type: 'Group', name: '分组', description: '字段分组容器' },
  { type: 'Tabs', name: '标签页', description: '多标签页容器' },
  { type: 'Rating', name: '评分', description: '评分组件' }
];

/** 兼容旧名: 导出全部物料（不含 LLMAssist） */
export const COMPONENTS: ComponentItem[] = FIELD_COMPONENTS;

/** 单个可拖拽物料卡片 */
function DraggablePaletteItem({ item, onAddField }: { item: ComponentItem; onAddField: (type: string) => void }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `palette_${item.type}`,
    data: { origin: 'palette', type: item.type }
  });

  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        padding: 12,
        border: '1px solid #f0f0f0',
        borderRadius: 8,
        background: '#fafafa',
        marginBottom: 10,
        cursor: 'grab',
        opacity: isDragging ? 0.4 : 1,
        transition: 'opacity 0.2s'
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontWeight: 600,
          fontSize: 14,
          color: '#111827',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis'
        }}>
          {item.name}
        </div>
        <div style={{
          marginTop: 4,
          fontSize: 12,
          color: '#6b7280',
          lineHeight: 1.5,
          wordBreak: 'normal' as const
        }}>
          {item.description}
        </div>
      </div>
      <Button
        type="primary"
        size="small"
        htmlType="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onAddField(item.type);
        }}
        style={{ flexShrink: 0, minWidth: 60 }}
      >
        添加
      </Button>
    </div>
  );
}

const ComponentPalette: React.FC<ComponentPaletteProps> = ({ onAddField, aiAssistEnabled = false, onAiAssistToggle }) => {
  return (
    <div>
      {/* ── 表单字段物料 ── */}
      <div style={{ marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid #f0f0f0' }}>
        <div style={{ fontSize: 11, color: '#999', marginBottom: 8, fontWeight: 600, letterSpacing: 1 }}>表单字段</div>
        {FIELD_COMPONENTS.map((item) => (
          <DraggablePaletteItem key={item.type} item={item} onAddField={onAddField} />
        ))}
      </div>

      {/* ── 系统能力配置 ── */}
      <div>
        <div style={{ fontSize: 11, color: '#999', marginBottom: 10, fontWeight: 600, letterSpacing: 1 }}>系统能力配置</div>
        <div style={{
          padding: 12,
          border: '1px solid #d6e4ff',
          borderRadius: 8,
          background: '#f0f5ff',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontWeight: 600, fontSize: 13 }}>AI 辅助审核</span>
            <Switch
              size="small"
              checked={aiAssistEnabled}
              onChange={(checked) => onAiAssistToggle?.(checked)}
            />
          </div>
          <div style={{ fontSize: 11, color: '#6b7280', lineHeight: 1.6 }}>
            开启后，标注工作台右侧将展示 AI 预审结果面板，标注员可参考 AI 建议进行标注。审核详情页将展示 AI/人工差异对比。
          </div>
          <Tooltip title="此配置控制模板是否启用 AI 预审能力，对应 schema.ai_assist.enabled 字段">
            <div style={{ fontSize: 10, color: '#9ca3af', marginTop: 6, cursor: 'help' }}>
              schema 字段: ai_assist.enabled
            </div>
          </Tooltip>
        </div>
      </div>
    </div>
  );
};

export default ComponentPalette;