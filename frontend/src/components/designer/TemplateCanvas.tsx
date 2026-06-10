import React from 'react';
import { Button, List, Tag, Empty } from 'antd';
import { TemplateField } from '../../types/template';

interface TemplateCanvasProps {
  fields: TemplateField[];
  selectedFieldId: string | null;
  onSelectField: (id: string) => void;
  onDeleteField: (id: string) => void;
  onDuplicateField: (id: string) => void;
  onMoveField: (id: string, direction: 'up' | 'down') => void;
}

const TemplateCanvas: React.FC<TemplateCanvasProps> = ({
  fields,
  selectedFieldId,
  onSelectField,
  onDeleteField,
  onDuplicateField,
  onMoveField
}) => {
  const isFirst = (index: number) => index === 0;
  const isLast = (index: number) => index === fields.length - 1;

  if (!fields || fields.length === 0) {
    return (
      <div style={{ padding: 16, minHeight: '100%' }}>
        <h3 style={{ marginBottom: 16, fontSize: 14, fontWeight: 600, color: '#1f1f1f' }}>
          画布区 - 当前字段数：0
        </h3>
        <Empty
          description="暂无字段，请从左侧物料区添加组件"
          style={{ margin: '40px 0' }}
        />
      </div>
    );
  }

  return (
    <div style={{ padding: 16, minHeight: '100%' }}>
      <h3 style={{ marginBottom: 16, fontSize: 14, fontWeight: 600, color: '#1f1f1f' }}>
        画布区 - 当前字段数：{fields.length}
      </h3>
      <List
        dataSource={fields}
        renderItem={(field, index) => (
          <List.Item
            key={field.id}
            style={{
              cursor: 'pointer',
              padding: 16,
              marginBottom: 12,
              border: selectedFieldId === field.id
                ? '2px solid #1890ff'
                : '1px solid #e8e8e8',
              borderRadius: 8,
              backgroundColor: selectedFieldId === field.id
                ? '#e6f7ff'
                : '#fff',
              transition: 'all 0.2s'
            }}
            onClick={() => onSelectField(field.id)}
            actions={[
              <Button
                size="small"
                disabled={isFirst(index)}
                onClick={(e) => {
                  e.stopPropagation();
                  onMoveField(field.id, 'up');
                }}
                htmlType="button"
              >
                上移
              </Button>,
              <Button
                size="small"
                disabled={isLast(index)}
                onClick={(e) => {
                  e.stopPropagation();
                  onMoveField(field.id, 'down');
                }}
                htmlType="button"
              >
                下移
              </Button>,
              <Button
                size="small"
                onClick={(e) => {
                  e.stopPropagation();
                  onDuplicateField(field.id);
                }}
                htmlType="button"
              >
                复制
              </Button>,
              <Button
                size="small"
                danger
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteField(field.id);
                }}
                htmlType="button"
              >
                删除
              </Button>
            ]}
          >
            <List.Item.Meta
              title={
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 500 }}>{field.label}</span>
                  {field.required && (
                    <Tag color="red" style={{ fontSize: 12, padding: '1px 6px' }}>
                      必填
                    </Tag>
                  )}
                </div>
              }
              description={
                <div style={{ fontSize: 12, color: '#666' }}>
                  <div>ID: {field.id}</div>
                  <div>Type: {field.type}</div>
                  {field.binding && <div>Binding: {field.binding}</div>}
                  {field.options && field.options.length > 0 && (
                    <div>Options: {field.options.length} 个选项</div>
                  )}
                </div>
              }
            />
          </List.Item>
        )}
      />
    </div>
  );
};

export default TemplateCanvas;
