import React from 'react';
import { Card, Row, Col, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '../stores/appStore';

const { Title, Paragraph } = Typography;

const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const setCurrentRole = useAppStore((state) => state.setCurrentRole);

  const handleEnter = (role: 'owner' | 'labeler' | 'reviewer', path: string) => {
    setCurrentRole(role);
    navigate(path);
  };

  return (
    <div style={{ padding: 48, maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: 48 }}>
        <Title>LabelHub</Title>
        <Paragraph>AI 数据标注平台</Paragraph>
      </div>
      <Row gutter={[24, 24]}>
        <Col span={8}>
          <Card
            hoverable
            style={{ height: 200, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}
            onClick={() => handleEnter('owner', '/owner')}
          >
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 48, color: '#1890ff', marginBottom: 16 }}>📋</div>
              <Title level={3}>项目所有者</Title>
              <Paragraph>管理任务、模板、数据集和导出</Paragraph>
            </div>
          </Card>
        </Col>
        <Col span={8}>
          <Card
            hoverable
            style={{ height: 200, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}
            onClick={() => handleEnter('labeler', '/labeler')}
          >
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 48, color: '#52c41a', marginBottom: 16 }}>✏️</div>
              <Title level={3}>标注员</Title>
              <Paragraph>浏览任务、进行标注和查看提交</Paragraph>
            </div>
          </Card>
        </Col>
        <Col span={8}>
          <Card
            hoverable
            style={{ height: 200, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}
            onClick={() => handleEnter('reviewer', '/reviewer')}
          >
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 48, color: '#faad14', marginBottom: 16 }}>✅</div>
              <Title level={3}>审核员</Title>
              <Paragraph>审核标注提交</Paragraph>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default HomePage;
