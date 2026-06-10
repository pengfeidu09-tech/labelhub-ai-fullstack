import React, { useState, useEffect, useMemo } from 'react';
import { PageHeader } from '../../components/common/PageHeader';
import { Table, Button, Space, message, Tag, Modal, Form, Input, Select, Switch, Tooltip, Alert, Row, Col, Card, Statistic } from 'antd';
import { useNavigate } from 'react-router-dom';
import { getTasks, createTask, publishTask, pauseTask, endTask } from '../../api/tasks';
import { getTemplates } from '../../api/templates';
import { Task } from '../../types/task';
import { Template } from '../../types/template';
import { formatTaskName, normalizeList, dedupMessage } from '../../utils/format';
import { formatDateMinute } from '../../utils/time';
import { StatusTag } from '../../utils/status';
import { FileTextOutlined, RobotOutlined } from '@ant-design/icons';

const { Option } = Select;

const TaskListPage: React.FC = () => {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [form] = Form.useForm();

  const [keywordFilter, setKeywordFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [aiFilter, setAiFilter] = useState<string>('all');
  const [sortOrder, setSortOrder] = useState<string>('newest');

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const res = await getTasks();
      setTasks(normalizeList<Task>(res));
    } catch (error) {
      dedupMessage.error('获取任务列表失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const fetchTemplates = async () => {
    try {
      const res = await getTemplates();
      setTemplates(normalizeList<Template>(res));
    } catch (error) {
      dedupMessage.error('获取模板列表失败');
      console.error(error);
    }
  };

  useEffect(() => {
    fetchTasks();
    fetchTemplates();
  }, []);

  const handleCreateTask = async (values: any) => {
    try {
      await createTask(values);
      message.success('创建任务成功');
      setCreateModalVisible(false);
      form.resetFields();
      fetchTasks();
    } catch (error) {
      message.error('创建任务失败');
      console.error(error);
    }
  };

  const handlePublish = async (id: number) => {
    try {
      await publishTask(id);
      message.success('发布任务成功');
      fetchTasks();
    } catch (error) {
      message.error('发布任务失败');
      console.error(error);
    }
  };

  const handlePause = async (id: number) => {
    try {
      await pauseTask(id);
      message.success('暂停任务成功');
      fetchTasks();
    } catch (error) {
      message.error('暂停任务失败');
      console.error(error);
    }
  };

  const handleEnd = async (id: number) => {
    try {
      await endTask(id);
      message.success('结束任务成功');
      fetchTasks();
    } catch (error) {
      message.error('结束任务失败');
      console.error(error);
    }
  };

  const filteredTasks = useMemo(() => {
    let result = [...tasks];

    if (keywordFilter.trim()) {
      const kw = keywordFilter.trim().toLowerCase();
      result = result.filter(t => formatTaskName(t).toLowerCase().includes(kw) || String(t.id).includes(kw));
    }

    if (statusFilter !== 'all') {
      result = result.filter(t => t.status === statusFilter);
    }

    if (aiFilter === 'enabled') {
      result = result.filter(t => t.ai_review_enabled === true);
    } else if (aiFilter === 'disabled') {
      result = result.filter(t => !t.ai_review_enabled);
    }

    result.sort((a, b) => {
      // official_raw 任务排在最前
      const aOff = a.is_default_demo ? 1 : 0;
      const bOff = b.is_default_demo ? 1 : 0;
      if (aOff !== bOff) return bOff - aOff;
      const ta = new Date(a.created_at || 0).getTime();
      const tb = new Date(b.created_at || 0).getTime();
      return sortOrder === 'newest' ? tb - ta : ta - tb;
    });

    return result;
  }, [tasks, keywordFilter, statusFilter, aiFilter, sortOrder]);

  const totalStats = useMemo(() => ({
    total: tasks.length,
    published: tasks.filter(t => t.status === 'published').length,
    aiEnabled: tasks.filter(t => t.ai_review_enabled).length,
  }), [tasks]);

  const columns = [
    { 
      title: 'ID', 
      dataIndex: 'id', 
      key: 'id', 
      width: 60,
      fixed: 'left' as const
    },
    { 
      title: '任务名称', 
      dataIndex: 'name', 
      key: 'name', 
      width: 180,
      render: (_name: string, record: Task) => (
        <Tooltip title={formatTaskName(record)}>
          <span style={{ 
            display: 'inline-block',
            maxWidth: 160,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap'
          }}>
            {formatTaskName(record)}
          </span>
          {record.is_official_raw && (
            <Tag color="blue" style={{ marginLeft: 4, fontSize: 10 }}>官方原题</Tag>
          )}
          {record.source_namespace === 'demo_seed' && (
            <Tag color="default" style={{ marginLeft: 4, fontSize: 10 }}>demo</Tag>
          )}
        </Tooltip>
      )
    },
    { 
      title: '状态', 
      dataIndex: 'status', 
      key: 'status', 
      width: 90,
      render: (status: string) => <StatusTag status={status} type="task" />
    },
    { 
      title: 'AI审核', 
      dataIndex: 'ai_review_enabled', 
      key: 'ai_review_enabled', 
      width: 80,
      render: (enabled: boolean) => enabled ? <Tag color="green" style={{ fontSize: 11 }}>开启</Tag> : <Tag style={{ fontSize: 11 }}>关闭</Tag>
    },
    { 
      title: '总数据', 
      key: 'total_items', 
      width: 80,
      render: (_: any, record: any) => (record as any).total_items ?? (record as any).item_count ?? '-'
    },
    { 
      title: '已提交', 
      key: 'submitted_count', 
      width: 80,
      render: (_: any, record: any) => (record as any).submitted_count ?? '-'
    },
    { 
      title: 'AI已预审', 
      key: 'ai_reviewed_count', 
      width: 90,
      render: (_: any, record: any) => {
        const v = (record as any).ai_reviewed_count;
        return v != null ? <span style={{ color: '#722ed1' }}>{v}</span> : '-';
      }
    },
    { 
      title: '已通过', 
      key: 'approved_count', 
      width: 80,
      render: (_: any, record: any) => {
        const v = (record as any).approved_count;
        return v != null ? <span style={{ color: '#52c41a' }}>{v}</span> : '-';
      }
    },
    { 
      title: '可导出', 
      key: 'export_ready_count', 
      width: 80,
      render: (_: any, record: any) => {
        const v = (record as any).export_ready_count;
        return v != null ? <span style={{ color: '#13c2c2' }}>{v}</span> : '-';
      }
    },
    { 
      title: '创建时间', 
      dataIndex: 'created_at', 
      key: 'created_at', 
      width: 140,
      render: (date: string) => date ? formatDateMinute(date) : '-'
    },
    { 
      title: '操作', 
      key: 'action', 
      width: 260,
      fixed: 'right' as const,
      render: (_: any, record: Task) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => navigate(`/owner/tasks/${record.id}`)}>
            任务详情
          </Button>
          <Button type="link" size="small" onClick={() => navigate(`/owner/tasks/${record.id}/results`)}>
            结果中心
          </Button>
          {record.status === 'draft' && (
            <Button type="link" size="small" style={{ color: '#52c41a' }} onClick={() => handlePublish(record.id)}>
              发布
            </Button>
          )}
          {record.status === 'published' && (
            <Button type="link" size="small" style={{ color: '#fa8c16' }} onClick={() => handlePause(record.id)}>
              暂停
            </Button>
          )}
          {(record.status === 'published' || record.status === 'paused') && (
            <Button type="link" danger size="small" onClick={() => handleEnd(record.id)}>
              结束
            </Button>
          )}
        </Space>
      )
    }
  ];

  return (
    <div>
      <PageHeader title="项目/任务总览" subtitle="管理数据标注项目、模板、进度与质量状态。" />
      <Alert 
        type="info" 
        showIcon 
        style={{ marginBottom: 16 }}
        message="官方演示流程"
        description={
          <ol style={{ margin: 0, paddingLeft: 20, fontSize: 12, lineHeight: '20px' }}>
            <li>任务负责人：创建并配置任务，搭建标注模板，配置审核规则，发布任务</li>
            <li>标注员：进入任务市场领取任务，进入标注工作台在线作答</li>
            <li>标注员：使用 LLM 辅助获取 Rubric 对齐建议，保存草稿，提交答案</li>
            <li>AI 审核 Agent：提交后自动预审，输出多维度评分和风险等级</li>
            <li>人工审核员：进入审核队列，对比 AI 预审与标注结果，通过或打回</li>
            <li>数据落地：通过审核的数据进入结果中心，多格式导出</li>
            <li>审计追踪：全链路操作可追溯</li>
          </ol>
        }
      />

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small"><Statistic title="任务总数" value={totalStats.total} prefix={<FileTextOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="已发布" value={totalStats.published} valueStyle={{ color: '#1890ff' }} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="AI审核开启" value={totalStats.aiEnabled} prefix={<RobotOutlined />} valueStyle={{ color: '#722ed1' }} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="筛选结果" value={filteredTasks.length} valueStyle={{ color: filteredTasks.length < tasks.length ? '#fa8c16' : '#52c41a' }} /></Card>
        </Col>
      </Row>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col span={5}>
            <Input
              placeholder="搜索任务名称/ID"
              value={keywordFilter}
              onChange={e => setKeywordFilter(e.target.value)}
              allowClear
              size="small"
            />
          </Col>
          <Col span={4}>
            <Select value={statusFilter} onChange={setStatusFilter} style={{ width: '100%' }} size="small">
              <Option value="all">全部状态</Option>
              <Option value="draft">草稿</Option>
              <Option value="published">已发布</Option>
              <Option value="paused">暂停</Option>
              <Option value="completed">已结束</Option>
            </Select>
          </Col>
          <Col span={4}>
            <Select value={aiFilter} onChange={setAiFilter} style={{ width: '100%' }} size="small">
              <Option value="all">全部AI审核</Option>
              <Option value="enabled">开启</Option>
              <Option value="disabled">关闭</Option>
            </Select>
          </Col>
          <Col span={4}>
            <Select value={sortOrder} onChange={setSortOrder} style={{ width: '100%' }} size="small">
              <Option value="newest">最新创建</Option>
              <Option value="oldest">最早创建</Option>
            </Select>
          </Col>
          <Col span={7}>
            <Space size="small">
              <Button size="small" onClick={() => { setKeywordFilter(''); setStatusFilter('all'); setAiFilter('all'); setSortOrder('newest'); }}>重置</Button>
              <Button type="primary" size="small" onClick={() => setCreateModalVisible(true)}>创建任务</Button>
              <Button size="small" onClick={fetchTasks} loading={loading}>刷新</Button>
            </Space>
          </Col>
        </Row>
      </Card>

      <Table
        columns={columns}
        dataSource={filteredTasks}
        rowKey="id"
        loading={loading}
        scroll={{ x: 1100 }}
        pagination={{
          pageSize: 10,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total) => `共 ${total} 个任务`
        }}
        locale={{ emptyText: '没有匹配的任务' }}
      />

      <Modal
        title="创建任务"
        open={createModalVisible}
        onCancel={() => {
          setCreateModalVisible(false);
          form.resetFields();
        }}
        footer={[
          <Button key="cancel" onClick={() => setCreateModalVisible(false)}>取消</Button>,
          <Button key="submit" type="primary" onClick={() => form.submit()}>创建</Button>
        ]}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreateTask}
        >
          <Form.Item label="任务名称" name="name" rules={[{ required: true, message: '请输入任务名称' }]}>
            <Input placeholder="请输入任务名称" />
          </Form.Item>
          <Form.Item label="任务描述" name="description">
            <Input.TextArea placeholder="请输入任务描述" rows={3} />
          </Form.Item>
          <Form.Item label="选择模板" name="template_id" rules={[{ required: true, message: '请选择模板' }]}>
            <Select placeholder="请选择模板">
              {templates.map(template => (
                <Option key={template.id} value={template.id}>{template.name}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item label="启用AI审核" name="ai_review_enabled" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default TaskListPage;
