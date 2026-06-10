import React, { useEffect, useState } from 'react';
import { Layout, Menu, Alert, Switch } from 'antd';
import type { MenuProps } from 'antd';
import { Link, useLocation, useNavigate, Outlet } from 'react-router-dom';
import { useAppStore } from '../stores/appStore';
import { ConnectionStatus } from '../components/common/ConnectionStatus';
import { ExperimentOutlined } from '@ant-design/icons';

const { Header, Sider, Content } = Layout;

const DEMO_MODE_KEY = 'labelhub_demo_mode';

const OwnerMenuItems: MenuProps['items'] = [
  { key: '/owner', label: <Link to="/owner">仪表盘</Link> },
  { key: '/owner/tasks', label: <Link to="/owner/tasks">项目/任务总览</Link> },
  { key: '/owner/templates', label: <Link to="/owner/templates">模板管理</Link> },
  { key: '/owner/agent', label: <Link to="/owner/agent">AI 审核 Agent</Link> },
  { key: '/owner/rubrics', label: <Link to="/owner/rubrics">Rubric 标准库</Link> },
  { key: '/owner/annotations', label: <Link to="/owner/annotations">标注结果</Link> },
  { key: '/owner/exports', label: <Link to="/owner/exports">导出管理</Link> },
  { key: '/owner/audit-logs', label: <Link to="/owner/audit-logs">审计日志</Link> },
  { key: '/owner/datasets', label: <Link to="/owner/datasets">数据集</Link> },
];

const LabelerMenuItems: MenuProps['items'] = [
  { key: '/labeler/tasks', label: <Link to="/labeler/tasks">任务市场</Link> },
  { key: '/labeler/workbench', label: <Link to="/labeler/workbench">标注工作台</Link> },
  { key: '/labeler/submissions', label: <Link to="/labeler/submissions">我的提交</Link> },
  { key: '/labeler/reports', label: <Link to="/labeler/reports">工时报表</Link> },
];

const ReviewerMenuItems: MenuProps['items'] = [
  { key: '/reviewer/queue', label: <Link to="/reviewer/queue">审核队列</Link> },
];

const demoTips: Record<string, string> = {
  '/owner/tasks': '任务负责人入口：创建标注任务、配置数据范围、查看任务状态。',
  '/owner/templates': '任务负责人入口：搭建任务专属标注模板，拖拽字段、配置属性、Schema 校验。',
  '/owner/agent': 'AI 审核 Agent：配置预审模型、查看预审记录、风险分布和维度评分。',
  '/owner/audit-logs': '审计追踪：全链路操作可追溯，从创建任务到标注、AI 预审、审核、导出均有记录。',
  '/labeler/tasks': '标注员入口：浏览任务市场，筛选/查看任务详情，领取任务后进入标注工作台。',
  '/labeler/workbench': '标注工作台：查看原始数据、只读 Rubric 标准参考，填写正式表单，使用 LLM 辅助获取 Rubric 对齐建议，保存草稿并提交。',
  '/labeler/submissions': '标注员提交记录：查看已提交答案的状态、AI 分数、审核结果。',
  '/reviewer': '人工审核员：根据 AI 预审结果和标注答案进行复核，通过或打回。',
};

const MainLayout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const currentRole = useAppStore((state) => state.currentRole);
  const setCurrentRole = useAppStore((state) => state.setCurrentRole);
  const [demoMode, setDemoMode] = useState(() => localStorage.getItem(DEMO_MODE_KEY) === 'true');

  useEffect(() => {
    const path = location.pathname;
    if (path.startsWith('/owner')) {
      setCurrentRole('owner');
    } else if (path.startsWith('/labeler')) {
      setCurrentRole('labeler');
    } else if (path.startsWith('/reviewer')) {
      setCurrentRole('reviewer');
    }
  }, [location.pathname, setCurrentRole]);

  useEffect(() => {
    localStorage.setItem(DEMO_MODE_KEY, String(demoMode));
  }, [demoMode]);

  let menuItems: MenuProps['items'] = [];
  if (currentRole === 'owner') menuItems = OwnerMenuItems;
  if (currentRole === 'labeler') menuItems = LabelerMenuItems;
  if (currentRole === 'reviewer') menuItems = ReviewerMenuItems;

  const handleBack = () => {
    setCurrentRole(null);
    navigate('/');
  };

  const getDemoTip = () => {
    if (!demoMode) return null;
    const path = location.pathname;
    // Results center
    if (path.includes('/results')) return '数据落地：通过审核的数据进入结果中心，可按 JSON、CSV、XLSX、JSONL 等格式导出。';
    // Task detail (but not list)
    if (/\/owner\/tasks\/\d+/.test(path)) return '任务详情：查看任务信息、模板绑定、审核规则配置、标注进度和工作单明细。';
    // Export page
    if (path.includes('/exports')) return '导出管理：创建导出任务，选择 JSON / CSV / XLSX / JSONL 格式，下载已通过的高质量数据。';
    for (const [prefix, tip] of Object.entries(demoTips)) {
      if (path.startsWith(prefix)) return tip;
    }
    return null;
  };

  const demoTip = getDemoTip();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="light" width={200}>
        <div style={{ padding: 16, textAlign: 'center', fontWeight: 'bold' }}>
          LabelHub
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div onClick={handleBack} style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
            返回首页
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 12, color: '#999' }}>演示模式</span>
            <Switch
              size="small"
              checked={demoMode}
              onChange={setDemoMode}
              checkedChildren="开"
              unCheckedChildren="关"
            />
            <ConnectionStatus />
          </div>
        </Header>
        <Content style={{ padding: 24, background: '#f5f5f5' }}>
          {demoTip && (
            <Alert
              type="info"
              showIcon
              icon={<ExperimentOutlined />}
              message={demoTip}
              style={{ marginBottom: 16 }}
              closable
            />
          )}
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
