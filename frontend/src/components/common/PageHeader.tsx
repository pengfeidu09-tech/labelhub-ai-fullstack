import React from 'react';
import { Typography } from 'antd';

const { Title } = Typography;

interface PageHeaderProps {
  title: string;
  subtitle?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({ title, subtitle }) => {
  return (
    <div style={{ marginBottom: 24 }}>
      <Title level={2} style={{ margin: 0 }}>{title}</Title>
      {subtitle && <div style={{ color: '#666', marginTop: 8 }}>{subtitle}</div>}
    </div>
  );
};
