import React from 'react';
import { Modal } from 'antd';
import { TemplateSchema } from '../../types/template';

interface SchemaPreviewProps {
  visible: boolean;
  schema: TemplateSchema;
  onCancel: () => void;
}

export const SchemaPreview: React.FC<SchemaPreviewProps> = ({
  visible,
  schema,
  onCancel
}) => {
  return (
    <Modal
      title="Schema JSON Preview"
      open={visible}
      onCancel={onCancel}
      footer={[
        <button key="close" onClick={onCancel}>关闭</button>
      ]}
      width={800}
      style={{ top: 20 }}
    >
      <div style={{ maxHeight: '70vh', overflow: 'auto', backgroundColor: '#f5f5f5', padding: 16, borderRadius: 4 }}>
        <pre style={{ fontSize: 12, lineHeight: 1.5, margin: 0 }}>
          {JSON.stringify(schema, null, 2)}
        </pre>
      </div>
    </Modal>
  );
};
