import React, { useState, useEffect } from 'react';
import { PageHeader } from '../../components/common/PageHeader';
import { Table, Button, Space, message, Modal, Form, Select, Tag, Tooltip } from 'antd';
import { getExportJobs, exportTask } from '../../api/exports';
import { getTasks } from '../../api/tasks';
import { ExportJob } from '../../types/export';
import { Task } from '../../types/task';
import { normalizeList, formatTaskName, dedupMessage } from '../../utils/format';
import { DownloadOutlined, CopyOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { formatDateTime } from '../../utils/time';

const { Option } = Select;

const getStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    'draft': '草稿',
    'published': '已发布',
    'paused': '已暂停',
    'completed': '已完成'
  };
  return statusMap[status] || status;
};

const ExportPage: React.FC = () => {
  const [exportJobs, setExportJobs] = useState<ExportJob[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportModalVisible, setExportModalVisible] = useState(false);
  const [summaryModalOpen, setSummaryModalOpen] = useState(false);
  const [summaryContent, setSummaryContent] = useState<string>('');
  const [form] = Form.useForm();

  const fetchExportJobs = async () => {
    setLoading(true);
    try {
      const res = await getExportJobs();
      setExportJobs(normalizeList<ExportJob>(res));
    } catch (error) {
      dedupMessage.error('获取导出任务失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const fetchTasks = async () => {
    try {
      const res = await getTasks();
      const taskList = normalizeList<Task>(res);
      setTasks(taskList);
    } catch (error) {
      dedupMessage.error('获取任务列表失败');
      console.error(error);
    }
  };

  const handleExport = async () => {
    try {
      const values = await form.validateFields();
      const { task_id, format } = values;

      if (!task_id) {
        message.warning('请选择任务');
        return;
      }
      if (!format) {
        message.warning('请选择导出格式');
        return;
      }

      setExporting(true);
      await exportTask(task_id, format);
      message.success('导出成功');
      setExportModalVisible(false);
      form.resetFields();
      fetchExportJobs();
    } catch (error: any) {
      if (error?.errorFields) {
        return;
      }
      message.error('导出失败');
      console.error(error);
    } finally {
      setExporting(false);
    }
  };

  useEffect(() => {
    fetchExportJobs();
    fetchTasks();
  }, []);

  const getStatusTag = (status: string) => {
    const statusMap: Record<string, { color: string; text: string }> = {
      'pending': { color: 'default', text: '待处理' },
      'running': { color: 'blue', text: '处理中' },
      'success': { color: 'green', text: '成功' },
      'failed': { color: 'red', text: '失败' }
    };
    const info = statusMap[status] || { color: 'default', text: status };
    return <Tag color={info.color}>{info.text}</Tag>;
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 80 },
    { title: '任务ID', dataIndex: 'task_id', key: 'task_id', width: 100 },
    { title: '格式', dataIndex: 'format', key: 'format', width: 80, render: (v: string) => (v || '-').toUpperCase() },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80, render: getStatusTag },
    { title: '行数', dataIndex: 'row_count', key: 'row_count', width: 100,
      render: (count: number) => {
        if (!count || count === 0) {
          return <span style={{ color: 'orange' }}>0 行</span>;
        }
        return count;
      }
    },
    { title: '文件路径', dataIndex: 'file_path', key: 'file_path', width: 200,
      render: (path: string) => {
        if (!path) return '-';
        if (path.length <= 40) return <span style={{ fontSize: 12 }}>{path}</span>;
        const start = path.substring(0, 15);
        const end = path.substring(path.length - 20);
        return <Tooltip title={path}><span style={{ fontSize: 12 }}>{start}...{end}</span></Tooltip>;
      }
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (date: string) => date ? formatDateTime(date) : '-'
    },
    { title: '操作', key: 'action', width: 200, render: (_: any, record: ExportJob) => (
      <Space size="small">
        {record.status === 'success' && record.file_path && (
          <Button type="link" size="small" icon={<DownloadOutlined />}
            onClick={() => { window.open(`/api/exports/${record.id}/download`, '_blank'); }}>
            下载
          </Button>
        )}
        {record.file_path && (
          <Tooltip title={record.file_path}>
            <Button type="link" size="small" icon={<CopyOutlined />}
              onClick={() => { navigator.clipboard.writeText(record.file_path || '').then(() => message.success('已复制路径')).catch(() => message.error('复制失败')); }}>
            复制
            </Button>
          </Tooltip>
        )}
        {record.status === 'success' && (
          <Button type="link" size="small" icon={<InfoCircleOutlined />}
            onClick={() => {
              setSummaryContent(`导出 #${record.id}\n格式: ${(record.format || '').toUpperCase()}\n行数: ${record.row_count ?? 0}\n文件: ${record.file_path || '-'}\n时间: ${record.created_at ? formatDateTime(record.created_at) : '-'}`);
              setSummaryModalOpen(true);
            }}>
            摘要
          </Button>
        )}
        {record.status === 'failed' && (record as any).error_message && (
          <Tooltip title={(record as any).error_message}>
            <Tag color="red" style={{ fontSize: 11 }}>错误</Tag>
          </Tooltip>
        )}
      </Space>
    )}
  ];

  return (
    <div>
      <PageHeader title="导出管理" subtitle="管理数据导出" />
      <div style={{ marginBottom: 16 }}>
        <Space>
          <Button type="primary" onClick={() => setExportModalVisible(true)}>新建导出</Button>
          <Button onClick={fetchExportJobs} loading={loading}>刷新</Button>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={exportJobs}
        rowKey="id"
        loading={loading}
        pagination={{
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
        }}
      />

      <Modal
        title="新建导出"
        open={exportModalVisible}
        onCancel={() => {
          setExportModalVisible(false);
          form.resetFields();
        }}
        footer={[
          <Button key="cancel" onClick={() => {
            setExportModalVisible(false);
            form.resetFields();
          }}>取消</Button>,
          <Button key="submit" type="primary" loading={exporting} onClick={handleExport}>开始导出</Button>
        ]}
      >
        <Form
          form={form}
          layout="vertical"
        >
          <Form.Item label="选择任务" name="task_id" rules={[{ required: true, message: '请选择任务' }]}>
            <Select placeholder="请选择任务">
              {tasks.map(task => (
                <Option key={task.id} value={task.id}>
                  #{task.id} - {formatTaskName(task)} - {getStatusText(task.status)}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item label="导出格式" name="format" rules={[{ required: true, message: '请选择格式' }]}>
            <Select placeholder="请选择格式">
              <Option value="json">JSON</Option>
              <Option value="jsonl">JSONL</Option>
              <Option value="csv">CSV</Option>
              <Option value="xlsx">XLSX</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="导出摘要"
        open={summaryModalOpen}
        onCancel={() => setSummaryModalOpen(false)}
        footer={[
          <Button key="copy" icon={<CopyOutlined />} onClick={() => {
            navigator.clipboard.writeText(summaryContent).then(() => message.success('已复制')).catch(() => message.error('复制失败'));
          }}>复制</Button>,
          <Button key="close" onClick={() => setSummaryModalOpen(false)}>关闭</Button>
        ]}
      >
        <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, backgroundColor: '#f5f5f5', padding: 12, borderRadius: 6 }}>{summaryContent}</pre>
      </Modal>
    </div>
  );
};

export default ExportPage;
