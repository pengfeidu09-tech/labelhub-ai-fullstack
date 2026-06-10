import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Table, Button, Space, Tag, Input, Select, Card, Row, Col, Form, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { getTasks, getTaskStats } from '../../api/tasks';
import { claimNext } from '../../api/labeler';
import { normalizeList } from '../../utils/format';
import { formatDateTime } from '../../utils/time';
import { PageHeader } from '../../components/common/PageHeader';

const { Option } = Select;

interface FilterForm {
  task_no: string;
  task_name: string;
  status: string;
  supplier_type: string;
}

const STATUS_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'published', label: '进行中' },
  { value: 'paused', label: '已暂停' },
  { value: 'ended', label: '已结束' },
  { value: 'completed', label: '已结束' },
  { value: 'draft', label: '草稿' },
];

const SUPPLIER_TYPE_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'single', label: '单供应商' },
  { value: 'multi', label: '多供应商' },
];

const getStatusTag = (status: string) => {
  const s = String(status || '').toLowerCase();
  switch (s) {
    case 'published':
    case 'active':
      return <Tag color="green">进行中</Tag>;
    case 'paused':
      return <Tag color="orange">已暂停</Tag>;
    case 'ended':
    case 'completed':
      return <Tag color="default">已结束</Tag>;
    case 'draft':
      return <Tag>草稿</Tag>;
    default:
      return <Tag>{status}</Tag>;
  }
};

const getSupplierTypeLabel = (task: any) => {
  const mode = task.supplier_type || task.supplier_mode || task.assignment_mode || '';
  const m = String(mode).toLowerCase();
  if (m === 'single' || m === '单供应商') return '单供应商';
  if (m === 'multi' || m === '多供应商') return '多供应商';
  return task.multi_supplier ? '多供应商' : '单供应商';
};

const getPhaseLabel = (task: any) => {
  const phase = task.phase || task.current_phase || '';
  const p = String(phase).toLowerCase();
  if (p === 'labeling' || p === '标注') return '标注';
  if (p === 'label_qc' || p === '标注质检') return '标注质检';
  if (p === 'human_review' || p === '人工审核') return '人工审核';
  if (p === 'exportable' || p === '可导出') return '可导出';
  if (task.ai_review_enabled) return '标注';
  return '标注';
};

const TaskMarketPage: React.FC = () => {
  const navigate = useNavigate();
  const [form] = Form.useForm<FilterForm>();

  const [allTasks, setAllTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [claimingTaskId, setClaimingTaskId] = useState<number | null>(null);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10 });

  const [filters, setFilters] = useState<FilterForm>({
    task_no: '',
    task_name: '',
    status: 'all',
    supplier_type: 'all',
  });

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      let normalized: any[] = [];
      try {
        const statsRes = await getTaskStats();
        normalized = normalizeList(statsRes);
      } catch {
        const res = await getTasks();
        normalized = normalizeList(res);
      }
      setAllTasks(normalized);
    } catch (error) {
      message.error('加载任务列表失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  const filteredTasks = useMemo(() => {
    let result = [...allTasks];

    if (filters.task_no.trim()) {
      const kw = filters.task_no.trim().toLowerCase();
      result = result.filter(
        (t) =>
          String(t.task_no || t.id || '')
            .toLowerCase()
            .includes(kw)
      );
    }

    if (filters.task_name.trim()) {
      const kw = filters.task_name.trim().toLowerCase();
      result = result.filter(
        (t) =>
          String(t.name || t.title || '')
            .toLowerCase()
            .includes(kw)
      );
    }

    if (filters.status !== 'all') {
      result = result.filter((t) => {
        const s = String(t.status || '').toLowerCase();
        if (filters.status === 'published') return s === 'published' || s === 'active';
        if (filters.status === 'paused') return s === 'paused';
        if (filters.status === 'ended') return s === 'ended' || s === 'completed';
        if (filters.status === 'draft') return s === 'draft';
        return s === filters.status.toLowerCase();
      });
    }

    if (filters.supplier_type !== 'all') {
      result = result.filter((t) => {
        const label = getSupplierTypeLabel(t);
        if (filters.supplier_type === 'single') return label === '单供应商';
        if (filters.supplier_type === 'multi') return label === '多供应商';
        return true;
      });
    }

    return result.sort((a, b) => {
      // 官方原题排在最前
      const aOff = a.is_default_demo ? 1 : 0;
      const bOff = b.is_default_demo ? 1 : 0;
      return bOff - aOff;
    });
  }, [allTasks, filters]);

  const handleQuery = () => {
    const values = form.getFieldsValue();
    setFilters(values);
    setPagination((prev) => ({ ...prev, current: 1 }));
  };

  const handleReset = () => {
    form.resetFields();
    setFilters({ task_no: '', task_name: '', status: 'all', supplier_type: 'all' });
    setPagination((prev) => ({ ...prev, current: 1 }));
  };

  const handleClaimTask = async (taskId: number) => {
    try {
      setClaimingTaskId(taskId);
      const responseData = await claimNext(taskId);

      if (responseData.has_active && responseData.item) {
        const item = responseData.item;
        const workKey = item.work_key || `${item.task_id}:${item.item_id || item.dataset_item_id}:2`;
        if (responseData.success) {
          message.success(responseData.message || '领取成功');
        } else {
          message.info(responseData.message || '已为你打开当前进行中任务');
        }
        window.location.href = `/labeler/workbench?item_id=${item.item_id || item.dataset_item_id}&task_id=${item.task_id}&work_key=${workKey}&mode=edit`;
      } else {
        if (responseData.code === 'NO_AVAILABLE_ITEM') {
          message.warning(responseData.message || '当前任务下暂无可领取数据');
        } else {
          message.error(responseData.message || '暂无可领取数据');
        }
      }
    } catch (error: any) {
      const errData = error.response?.data;
      if (errData?.code === 'NO_AVAILABLE_ITEM') {
        message.warning(errData.message || '当前任务下暂无可领取数据');
      } else {
        message.error(errData?.detail || '领取任务失败');
      }
    } finally {
      setClaimingTaskId(null);
    }
  };

  const columns = [
    {
      title: '任务编号',
      dataIndex: 'task_no',
      key: 'task_no',
      width: 110,
      render: (text: string, record: any) => text || record.id || '-',
    },
    {
      title: '任务名称',
      dataIndex: 'name',
      key: 'name',
      width: 220,
      ellipsis: true,
      render: (text: string, record: any) => (
        <span>
          {text || record.title || '未命名任务'}
          {record.is_official_raw && (
            <Tag color="blue" style={{ marginLeft: 4, fontSize: 10 }}>官方原题</Tag>
          )}
          {record.source_namespace === 'demo_seed' && (
            <Tag color="default" style={{ marginLeft: 4, fontSize: 10 }}>demo</Tag>
          )}
        </span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => getStatusTag(status),
    },
    {
      title: '作业模式',
      key: 'supplier_type',
      width: 100,
      render: (_: any, record: any) => getSupplierTypeLabel(record),
    },
    {
      title: '阶段',
      key: 'phase',
      width: 100,
      render: (_: any, record: any) => getPhaseLabel(record),
    },
    {
      title: '来源',
      key: 'source',
      width: 90,
      render: (_: any, record: any) => {
        if (record.is_official_raw) return <Tag color="blue" style={{ fontSize: 10 }}>official_raw</Tag>;
        if (record.source_namespace === 'demo_seed') return <Tag color="default" style={{ fontSize: 10 }}>demo_seed</Tag>;
        return <Tag>{record.source_namespace || '-'}</Tag>;
      },
    },
    {
      title: '待处理',
      dataIndex: 'pending_count',
      key: 'pending_count',
      width: 80,
      align: 'right' as const,
      render: (v: number) => (v != null ? v : '-'),
    },
    {
      title: '处理中',
      dataIndex: 'in_progress_count',
      key: 'in_progress_count',
      width: 80,
      align: 'right' as const,
      render: (v: number) => (v != null ? <span style={{ color: '#1890ff' }}>{v}</span> : '-'),
    },
    {
      title: '待流转',
      dataIndex: 'to_flow_count',
      key: 'to_flow_count',
      width: 80,
      align: 'right' as const,
      render: (v: number) => (v != null ? v : '-'),
    },
    {
      title: '待修改',
      dataIndex: 'to_rework_count',
      key: 'to_rework_count',
      width: 80,
      align: 'right' as const,
      render: (v: number) => (v != null ? <span style={{ color: '#fa8c16' }}>{v}</span> : '-'),
    },
    {
      title: '总数',
      dataIndex: 'total_count',
      key: 'total_count',
      width: 60,
      align: 'right' as const,
      render: (v: number) => (v != null ? <strong>{v}</strong> : '-'),
    },
    {
      title: '承接小组',
      dataIndex: 'team',
      key: 'team',
      width: 110,
      ellipsis: true,
      render: (text: string) => text || '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      render: (date: string) => (date ? formatDateTime(date) : '-'),
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      fixed: 'right' as const,
      render: (_: any, record: any) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            onClick={() => navigate(`/owner/tasks/${record.id}`)}
          >
            详情
          </Button>
          <Button
            type="primary"
            size="small"
            loading={claimingTaskId === record.id}
            disabled={claimingTaskId !== null}
            onClick={() => handleClaimTask(record.id)}
          >
            开始标注
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="任务市场" subtitle="浏览可承接的标注任务，点击开始标注领取数据。" />

      <Card size="small" style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline" initialValues={filters}>
          <Row gutter={16} align="middle" style={{ width: '100%' }}>
            <Col span={4}>
              <Form.Item name="task_no" style={{ marginBottom: 0 }}>
                <Input placeholder="任务编号" allowClear size="small" />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item name="task_name" style={{ marginBottom: 0 }}>
                <Input placeholder="任务名称" allowClear size="small" />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item name="status" style={{ marginBottom: 0 }}>
                <Select style={{ width: '100%' }} size="small">
                  {STATUS_OPTIONS.map((opt) => (
                    <Option key={opt.value} value={opt.value}>
                      {opt.label}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item name="supplier_type" style={{ marginBottom: 0 }}>
                <Select style={{ width: '100%' }} size="small">
                  {SUPPLIER_TYPE_OPTIONS.map((opt) => (
                    <Option key={opt.value} value={opt.value}>
                      {opt.label}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Space size="small">
                <Button type="primary" size="small" onClick={handleQuery}>
                  查询
                </Button>
                <Button size="small" onClick={handleReset}>
                  重置
                </Button>
              </Space>
            </Col>
          </Row>
        </Form>
      </Card>

      <Table
        columns={columns}
        dataSource={filteredTasks}
        rowKey="id"
        loading={loading}
        scroll={{ x: 1400 }}
        size="small"
        pagination={{
          current: pagination.current,
          pageSize: pagination.pageSize,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total) => `共 ${total} 个任务`,
          onChange: (page, pageSize) =>
            setPagination({ current: page, pageSize }),
        }}
        locale={{ emptyText: '暂无可用任务' }}
      />
    </div>
  );
};

export default TaskMarketPage;
