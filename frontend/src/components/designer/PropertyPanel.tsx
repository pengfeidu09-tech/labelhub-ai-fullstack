import React from 'react';
import { Form, Input, Select, Switch, InputNumber, Button, List, Empty } from 'antd';
import { TemplateField } from '../../types/template';

interface PropertyPanelProps {
  field: TemplateField | null;
  onChange: (updates: Partial<TemplateField>) => void;
}

const { Option } = Select;
const { TextArea } = Input;

const PropertyPanel: React.FC<PropertyPanelProps> = ({ field, onChange }) => {
  if (!field) {
    return (
      <div style={{ padding: 16, minHeight: '100%' }}>
        <h3 style={{ marginBottom: 16, fontSize: 14, fontWeight: 600, color: '#1f1f1f' }}>
          属性面板
        </h3>
        <Empty
          description="请从画布中选择一个字段"
          style={{ margin: '40px 0' }}
        />
      </div>
    );
  }

  const updateProp = (key: string, value: any) => {
    onChange({ [key]: value });
  };

  const updateNestedProp = (parent: string, key: string, value: any) => {
    const current = (field as any)[parent] || {};
    onChange({ [parent]: { ...current, [key]: value } });
  };

  const updateOption = (index: number, key: 'label' | 'value', value: string) => {
    if (!field.options) return;
    const newOptions = [...field.options];
    newOptions[index] = { ...newOptions[index], [key]: value };
    onChange({ options: newOptions });
  };

  const addOption = () => {
    const newOptions = [...(field.options || [])];
    newOptions.push({ label: `选项 ${newOptions.length + 1}`, value: `opt_${Date.now()}` });
    onChange({ options: newOptions });
  };

  const removeOption = (index: number) => {
    const newOptions = field.options?.filter((_, i) => i !== index) || [];
    onChange({ options: newOptions });
  };

  return (
    <div style={{ padding: 16, minHeight: '100%', overflowY: 'auto' }}>
      <h3 style={{ marginBottom: 16, fontSize: 14, fontWeight: 600, color: '#1f1f1f' }}>
        属性面板
      </h3>
      <Form layout="vertical" size="small">
        <Form.Item label="ID">
          <Input value={field.id} disabled />
        </Form.Item>
        <Form.Item label="类型">
          <Input value={field.type} disabled />
        </Form.Item>
        <Form.Item label="标签">
          <Input
            value={field.label || ''}
            onChange={(e) => updateProp('label', e.target.value)}
          />
        </Form.Item>
        <Form.Item label="必填">
          <Switch
            checked={field.required || false}
            onChange={(checked) => updateProp('required', checked)}
          />
        </Form.Item>
        <Form.Item label="占位符">
          <Input
            value={(field.props?.placeholder as string) || ''}
            onChange={(e) => updateNestedProp('props', 'placeholder', e.target.value)}
          />
        </Form.Item>
        <Form.Item label="帮助文本">
          <Input
            value={(field.props?.helpText as string) || ''}
            onChange={(e) => updateNestedProp('props', 'helpText', e.target.value)}
          />
        </Form.Item>

        {(field.type === 'ShowItem') && (
          <>
            <Form.Item label="绑定">
              <Input
                value={field.binding || ''}
                onChange={(e) => updateProp('binding', e.target.value)}
              />
            </Form.Item>
            <Form.Item label="格式">
              <Select
                value={field.format || 'text'}
                onChange={(value) => updateProp('format', value)}
              >
                <Option value="text">Text</Option>
                <Option value="markdown">Markdown</Option>
                <Option value="json">JSON</Option>
                <Option value="image">Image</Option>
                <Option value="video">Video</Option>
                <Option value="code">Code</Option>
              </Select>
            </Form.Item>
          </>
        )}

        {(field.type === 'Radio' || field.type === 'Checkbox' || field.type === 'TagSelect') && (
          <Form.Item label="选项">
            <div style={{ marginBottom: 8 }}>
              <Button type="dashed" size="small" onClick={addOption} block htmlType="button">
                + 添加选项
              </Button>
            </div>
            <List
              dataSource={field.options || []}
              renderItem={(option, index) => (
                <List.Item
                  key={index}
                  style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}
                  actions={[
                    <Button
                      size="small"
                      danger
                      type="text"
                      onClick={() => removeOption(index)}
                      htmlType="button"
                    >
                      删除
                    </Button>
                  ]}
                >
                  <div style={{ display: 'flex', gap: 8, width: '100%' }}>
                    <Input
                      size="small"
                      placeholder="Label"
                      value={option.label}
                      onChange={(e) => updateOption(index, 'label', e.target.value)}
                      style={{ flex: 1 }}
                    />
                    <Input
                      size="small"
                      placeholder="Value"
                      value={option.value}
                      onChange={(e) => updateOption(index, 'value', e.target.value)}
                      style={{ flex: 1 }}
                    />
                  </div>
                </List.Item>
              )}
            />
          </Form.Item>
        )}

        {field.type === 'Textarea' && (
          <>
            <Form.Item label="行数">
              <InputNumber
                value={(field.props?.rows as number) || 4}
                onChange={(value) => updateNestedProp('props', 'rows', value)}
                min={1}
                max={20}
                style={{ width: '100%' }}
              />
            </Form.Item>
            <Form.Item label="最大长度">
              <InputNumber
                value={(field.props?.maxLength as number) || undefined}
                onChange={(value) => updateNestedProp('props', 'maxLength', value)}
                min={0}
                style={{ width: '100%' }}
              />
            </Form.Item>
          </>
        )}

        {field.type === 'JsonEditor' && (
          <Form.Item label="默认值 JSON">
            <TextArea
              value={JSON.stringify((field.props?.defaultValue as any) || {}, null, 2)}
              onChange={(e) => {
                try {
                  updateNestedProp('props', 'defaultValue', JSON.parse(e.target.value));
                } catch {}
              }}
              rows={4}
            />
          </Form.Item>
        )}

        {field.type === 'LLMAssist' && (
          <>
            <Form.Item label="字段名">
              <Input
                value={field.name || ''}
                onChange={(e) => updateProp('name', e.target.value)}
              />
            </Form.Item>
            <Form.Item label="提示模板">
              <TextArea
                value={field.prompt_template || ''}
                onChange={(e) => updateProp('prompt_template', e.target.value)}
                rows={3}
              />
            </Form.Item>
            <Form.Item label="输入绑定 (数组 JSON)">
              <TextArea
                value={JSON.stringify(field.input_bindings || [], null, 2)}
                onChange={(e) => {
                  try {
                    updateProp('input_bindings', JSON.parse(e.target.value));
                  } catch {}
                }}
                rows={3}
              />
            </Form.Item>
            <Form.Item label="输出目标">
              <Input
                value={field.output_target || ''}
                onChange={(e) => updateProp('output_target', e.target.value)}
              />
            </Form.Item>
          </>
        )}

        {field.type === 'Group' && (
          <Form.Item label="子字段 (JSON)">
            <TextArea
              value={JSON.stringify(field.children || [], null, 2)}
              onChange={(e) => {
                try {
                  updateProp('children', JSON.parse(e.target.value));
                } catch {}
              }}
              rows={6}
            />
          </Form.Item>
        )}

        {field.type === 'Tabs' && (
          <Form.Item label="标签页">
            <List
              dataSource={field.tabs || []}
              renderItem={(tab, index) => (
                <List.Item key={index} style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                  <Input
                    placeholder="标签标题"
                    value={tab.title}
                    onChange={(e) => {
                      const newTabs = [...(field.tabs || [])];
                      newTabs[index] = { ...newTabs[index], title: e.target.value };
                      onChange({ tabs: newTabs });
                    }}
                  />
                </List.Item>
              )}
            />
          </Form.Item>
        )}
      </Form>
    </div>
  );
};

export default PropertyPanel;
