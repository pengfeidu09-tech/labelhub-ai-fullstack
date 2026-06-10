import React from 'react';

interface ShowItemRendererProps {
  itemData?: any;
  field?: any;
}

const ShowItemRenderer: React.FC<ShowItemRendererProps> = ({ itemData, field }) => {
  const format = field?.format || 'text';
  const fieldName = field?.fieldName;
  const value = itemData?.[fieldName] || itemData;
  
  if (!value) {
    return null;
  }

  switch (format) {
    case 'markdown':
      return (
        <div style={{ padding: '16px', backgroundColor: '#f5f5f5', borderRadius: '8px' }}>
          <p style={{ margin: 0 }}>{value}</p>
        </div>
      );

    case 'json':
      return (
        <div style={{ padding: '16px', backgroundColor: '#f5f5f5', borderRadius: '8px' }}>
          <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0 }}>
            {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
          </pre>
        </div>
      );

    case 'code':
      return (
        <div style={{ padding: '16px', backgroundColor: '#1f1f1f', borderRadius: '8px' }}>
          <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, color: '#e0e0e0', fontFamily: 'monospace' }}>
            {value}
          </pre>
        </div>
      );

    case 'image':
      return (
        <div style={{ padding: '16px', backgroundColor: '#f5f5f5', borderRadius: '8px' }}>
          <img 
            src={value} 
            alt="展示图片" 
            style={{ maxWidth: '100%', maxHeight: '300px', objectFit: 'contain' }}
          />
        </div>
      );

    case 'video':
      return (
        <div style={{ padding: '16px', backgroundColor: '#f5f5f5', borderRadius: '8px' }}>
          <video 
            src={value} 
            controls 
            style={{ maxWidth: '100%', maxHeight: '300px' }}
          />
        </div>
      );

    case 'text':
    default:
      return (
        <div style={{ padding: '16px', backgroundColor: '#f5f5f5', borderRadius: '8px' }}>
          <p style={{ margin: 0 }}>{String(value)}</p>
        </div>
      );
  }
};

export default ShowItemRenderer;
