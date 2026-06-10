import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '../../components/common/PageHeader';
import { Card, Table, Button, Space, Tag, Modal, message, Collapse, Descriptions, Switch, Input } from 'antd';
import { getTemplates, createQaQualityTemplate, createPreferenceCompareTemplate, cloneTemplateVersion } from '../../api/templates';
import { formatDateMinute, formatDateTime } from '../../utils/time';
import type { Template } from '../../types/template';

const TemplatePage: React.FC = () => {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(false);
  const [includeLegacy, setIncludeLegacy] = useState(false);

  // Detail modal state
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);

  // Clone modal state
  const [cloneModalVisible, setCloneModalVisible] = useState(false);
  const [cloneVersion, setCloneVersion] = useState('');
  const [cloneReason, setCloneReason] = useState('');
  const [cloning, setCloning] = useState(false);

  // Creating state for maintenance buttons
  const [creating, setCreating] = useState(false);

  const fetchTemplates = useCallback(async (legacy?: boolean) => {
    setLoading(true);
    try {
      const useLegacy = legacy ?? includeLegacy;
      const res = await getTemplates(undefined, 1, 50, useLegacy);
      setTemplates(res.items || []);
    } catch (error) {
      message.error('获取模板列表失败，保留上次数据');
      console.error(error);
    } finally {
      setLoading(false);
    }
  }, [includeLegacy]);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  // ── Handlers ──

  const handleViewDetail = (template: Template) => {
    setSelectedTemplate(template);
    setDetailModalVisible(true);
  };

  const handleEditTemplate = (template: Template) => {
    if (!template.id) {
      message.warning('该模板 ID 为空，无法编辑');
      return;
    }
    const taskIdParam = template.task_id ? `?task_id=${template.task_id}` : '';
    navigate(`/owner/templates/designer/${template.id}${taskIdParam}`);
  };

  const handleOpenTask = (template: Template) => {
    if (template.task_id) {
      navigate(`/owner/tasks/${template.task_id}`);
    } else {
      message.warning('该模板未绑定任务');
    }
  };

  const handleCloneConfirm = async () => {
    if (!selectedTemplate) {
      message.warning('请先选择模板');
      return;
    }
    if (!cloneVersion.trim()) {
      message.warning('请输入版本号');
      return;
    }
    try {
      setCloning(true);
      await cloneTemplateVersion(selectedTemplate.id, {
        schema_version: cloneVersion.trim(),
        changelog: cloneReason.trim() || undefined,
      });
      message.success('复制新版本成功');
      setCloneModalVisible(false);
      setCloneVersion('');
      setCloneReason('');
      fetchTemplates();
    } catch (error) {
      message.error('复制新版本失败');
      console.error(error);
    } finally {
      setCloning(false);
    }
  };

  const handleCreateQaTemplate = async () => {
    try {
      setCreating(true);
      await createQaQualityTemplate();
      message.success('问答质量模板创建成功');
      fetchTemplates();
    } catch (error) {
      message.error('创建失败');
      console.error(error);
    } finally {
      setCreating(false);
    }
  };

  const handleCreatePreferenceTemplate = async () => {
    try {
      setCreating(true);
      await createPreferenceCompareTemplate();
      message.success('偏好对比模板创建成功');
      fetchTemplates();
    } catch (error) {
      message.error('创建失败');
      console.error(error);
    } finally {
      setCreating(false);
    }
  };

  const handleRepairBinding = async () => {
    setLoading(true);
    try {
      // Re-fetch to refresh; backend handles repair logic on its side
      await fetchTemplates();
      message.success('任务模板绑定已刷新');
    } catch (error) {
      message.error('修复任务模板绑定失败');
      console.error(error);
    }
  };

  const handleToggleLegacy = (checked: boolean) => {
    setIncludeLegacy(checked);
    fetchTemplates(checked);
  };

  // ── Render helpers ──

  const getDatasetTypeTag = (type: string) => {
    switch (type) {
      case 'qa_quality':
        return <Tag color="blue">问答质量</Tag>;
      case 'preference_compare':
        return <Tag color="purple">偏好对比</Tag>;
      default:
        return <Tag>{type}</Tag>;
    }
  };

  // ── Table columns ──

  const columns = [
    {
      title: '任务编号',
      dataIndex: 'task_id',
      key: 'task_id',
      width: 100,
      render: (taskId: number | undefined) => (taskId ? `#${taskId}` : '-'),
    },
    {
      title: '任务名称',
      dataIndex: 'task_name',
      key: 'task_name',
      width: 160,
      render: (name: string | undefined) => name || '-',
    },
    {
      title: '数据集类型',
      dataIndex: 'dataset_type',
      key: 'dataset_type',
      width: 120,
      render: (type: string) => getDatasetTypeTag(type),
    },
    {
      title: '当前模板',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (name: string, record: Template) => (
        <span>
          {name}
          {includeLegacy && record.is_archived && (
            <Tag color="default" style={{ marginLeft: 6 }}>遗留</Tag>
          )}
        </span>
      ),
    },
    {
      title: '模板ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: '模板版本',
      dataIndex: 'schema_version',
      key: 'schema_version',
      width: 100,
    },
    {
      title: 'LLM辅助',
      dataIndex: 'llm_assist_enabled',
      key: 'llm_assist_enabled',
      width: 100,
      render: (enabled: boolean | undefined) =>
        enabled
          ? <Tag color="green">已开启</Tag>
          : <Tag>未开启</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      render: (active: boolean) =>
        active
          ? <Tag color="green">活跃</Tag>
          : <Tag color="default">未激活</Tag>,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 170,
      render: (date: string | undefined) => (date ? formatDateMinute(date) : '-'),
    },
    {
      title: '操作',
      key: 'action',
      width: 300,
      render: (_: unknown, record: Template) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleEditTemplate(record)}>
            编辑模板
          </Button>
          <Button type="link" size="small" onClick={() => handleViewDetail(record)}>
            查看Schema
          </Button>
          <Button
            type="link"
            size="small"
            disabled={!record.task_id}
            onClick={() => handleOpenTask(record)}
          >
            打开对应任务
          </Button>
        </Space>
      ),
    },
  ];

  // ── Maintenance section items ──

  const maintenanceItems = [
    {
      key: 'maintenance',
      label: '高级维护',
      children: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Space wrap>
            <span style={{ fontWeight: 500 }}>初始化官方基础模板：</span>
            <Button
              type="primary"
              size="small"
              onClick={handleCreateQaTemplate}
              loading={creating}
            >
              创建问答质量模板
            </Button>
            <Button
              size="small"
              onClick={handleCreatePreferenceTemplate}
              loading={creating}
            >
              创建偏好对比模板
            </Button>
          </Space>

          <Space wrap>
            <span style={{ fontWeight: 500 }}>修复任务模板绑定：</span>
            <Button size="small" onClick={handleRepairBinding}>
              修复任务模板绑定
            </Button>
          </Space>

          <Space align="center">
            <span style={{ fontWeight: 500 }}>显示历史模板：</span>
            <Switch
              checked={includeLegacy}
              onChange={handleToggleLegacy}
              checkedChildren="显示"
              unCheckedChildren="隐藏"
            />
            {includeLegacy && (
              <Tag color="orange">当前包含历史/遗留模板</Tag>
            )}
          </Space>
        </div>
      ),
    },
  ];

  // ── Render ──

  return (
    <div>
      <PageHeader title="任务模板管理" subtitle="查看和管理各任务的绑定模板" />

      <Card>
        <Space style={{ marginBottom: 16 }}>
          <Button onClick={() => fetchTemplates()}>刷新</Button>
        </Space>

        <Table
          columns={columns}
          dataSource={templates}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 20 }}
          scroll={{ x: 1400 }}
        />
      </Card>

      {/* Advanced maintenance section */}
      <Card style={{ marginTop: 16 }}>
        <Collapse items={maintenanceItems} />
      </Card>

      {/* Detail modal with Schema viewer */}
      <Modal
        title="模板详情"
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={[
          <Button key="close" type="primary" onClick={() => setDetailModalVisible(false)}>
            关闭
          </Button>,
        ]}
        width={800}
      >
        {selectedTemplate && (
          <div>
            <Descriptions bordered column={2} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="ID">{selectedTemplate.id}</Descriptions.Item>
              <Descriptions.Item label="名称">{selectedTemplate.name}</Descriptions.Item>
              <Descriptions.Item label="类型">{getDatasetTypeTag(selectedTemplate.dataset_type)}</Descriptions.Item>
              <Descriptions.Item label="版本">{selectedTemplate.schema_version}</Descriptions.Item>
              <Descriptions.Item label="任务绑定">
                {selectedTemplate.task_id ? `#${selectedTemplate.task_id}` : '无'}
              </Descriptions.Item>
              <Descriptions.Item label="父模板">
                {selectedTemplate.parent_template_id ? `#${selectedTemplate.parent_template_id}` : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="活跃状态">{selectedTemplate.is_active ? '是' : '否'}</Descriptions.Item>
              <Descriptions.Item label="冻结">{selectedTemplate.frozen_after_publish ? '是' : '否'}</Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {selectedTemplate.created_at ? formatDateTime(selectedTemplate.created_at) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="更新时间">
                {selectedTemplate.updated_at ? formatDateTime(selectedTemplate.updated_at) : '-'}
              </Descriptions.Item>
              {selectedTemplate.changelog && (
                <Descriptions.Item label="变更日志" span={2}>{selectedTemplate.changelog}</Descriptions.Item>
              )}
            </Descriptions>

            <Collapse defaultActiveKey={['schema']} items={[{
              key: 'schema',
              label: 'Schema 定义',
              children: (
                <pre style={{
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  maxHeight: 500,
                  overflow: 'auto',
                  backgroundColor: '#f5f5f5',
                  padding: 12,
                  borderRadius: 4,
                }}>
                  {JSON.stringify(selectedTemplate.schema, null, 2)}
                </pre>
              ),
            }]} />
          </div>
        )}
      </Modal>

      {/* Clone version modal */}
      <Modal
        title="复制为新版本"
        open={cloneModalVisible}
        onCancel={() => {
          setCloneModalVisible(false);
          setCloneVersion('');
          setCloneReason('');
        }}
        onOk={handleCloneConfirm}
        okText="确认克隆"
        cancelText="取消"
        confirmLoading={cloning}
      >
        {selectedTemplate && (
          <div>
            <p>将克隆模板：<strong>{selectedTemplate.name}</strong></p>
            <p>当前版本：{selectedTemplate.schema_version}</p>
            <p>新版本将基于父模板 <strong>#{selectedTemplate.id}</strong> 创建</p>

            <div style={{ marginTop: 16 }}>
              <label>新版本号：</label>
              <Input
                value={cloneVersion}
                onChange={(e) => setCloneVersion(e.target.value)}
                placeholder="例如：1.1.0"
                style={{ width: '100%', marginTop: 8 }}
              />
            </div>

            <div style={{ marginTop: 16 }}>
              <label>变更说明：</label>
              <textarea
                value={cloneReason}
                onChange={(e) => setCloneReason(e.target.value)}
                placeholder="请描述本次变更内容..."
                rows={3}
                style={{ width: '100%', marginTop: 8, padding: 8 }}
              />
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default TemplatePage;
