import React, { useState, useEffect, useCallback } from 'react';
import { Card, Row, Col, Statistic, Table, DatePicker, Select, Button, Spin, Alert } from 'antd';
import { PageHeader } from '../../components/common/PageHeader';
import { getMyWorkStats, getDailyWorkReport, getAvailableTasks, formatDuration } from '../../api/labeler';
import { dedupMessage } from '../../utils/format';
import {
  EditOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  ThunderboltOutlined,
  PercentageOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

const { RangePicker } = DatePicker;

interface WorkStats {
  today_labeled_count: number;
  today_submitted_count: number;
  today_valid_count: number;
  today_invalid_count: number;
  today_approved_count: number;
  today_rejected_count: number;
  today_total_seconds: number;
  avg_seconds_per_item: number;
  review_pass_rate: number;
  ai_human_agreement_rate: number;
}

interface DailyReport {
  date: string;
  task_id: number;
  task_name: string;
  labeled_count: number;
  submitted_count: number;
  approved_count: number;
  rejected_count: number;
  invalid_count: number;
  total_seconds: number;
  avg_seconds: number;
  pass_rate: number;
}

interface TaskOption {
  id: number;
  name: string;
}

const formatAvgDuration = (seconds: number): string => {
  return formatDuration(seconds);
};

const getApprovalRateColor = (rate: number): string => {
  if (rate >= 80) return '#52c41a';
  if (rate >= 60) return '#faad14';
  return '#ff4d4f';
};

const WorkReportPage: React.FC = () => {
  const [stats, setStats] = useState<WorkStats | null>(null);
  const [dailyData, setDailyData] = useState<DailyReport[]>([]);
  const [tasks, setTasks] = useState<TaskOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);
  const [dailyError, setDailyError] = useState<string | null>(null);
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<number | undefined>(undefined);

  const fetchStats = useCallback(async () => {
    try {
      const data = await getMyWorkStats();
      setStats(data);
    } catch (error) {
      dedupMessage.error('获取个人统计失败');
      console.error(error);
    }
  }, []);

  const fetchDailyReport = useCallback(async (startDate?: string, endDate?: string, taskId?: number) => {
    try {
      setTableLoading(true);
      setDailyError(null);
      const params: { start_date?: string; end_date?: string; task_id?: number } = {};
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;
      if (taskId) params.task_id = taskId;
      const data = await getDailyWorkReport(params);
      const items = Array.isArray(data) ? data : data?.reports || data?.items || data?.data || [];
      setDailyData(items);
    } catch (error) {
      setDailyError('日报明细加载失败，请稍后重试');
      dedupMessage.error('获取日报数据失败');
      console.error(error);
    } finally {
      setTableLoading(false);
    }
  }, []);

  const fetchTasks = useCallback(async () => {
    try {
      const data: any = await getAvailableTasks();
      const items = Array.isArray(data) ? data : data?.items || data?.data || [];
      setTasks(items.map((t: any) => ({ id: t.id, name: t.name || t.title || `任务#${t.id}` })));
    } catch (error) {
      console.error(error);
    }
  }, []);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([fetchStats(), fetchTasks(), fetchDailyReport()]);
      setLoading(false);
    };
    init();
  }, [fetchStats, fetchTasks, fetchDailyReport]);

  const handleQuery = () => {
    const startDate = dateRange?.[0]?.format('YYYY-MM-DD');
    const endDate = dateRange?.[1]?.format('YYYY-MM-DD');
    fetchDailyReport(startDate, endDate, selectedTaskId);
  };

  const cardBodyStyle = { padding: '16px 20px' };

  const columns = [
    {
      title: '日期',
      dataIndex: 'date',
      key: 'date',
      width: 120,
    },
    {
      title: '任务名称',
      dataIndex: 'task_name',
      key: 'task_name',
      width: 160,
      ellipsis: true,
    },
    {
      title: '标注数量',
      dataIndex: 'labeled_count',
      key: 'labeled_count',
      width: 90,
      align: 'right' as const,
    },
    {
      title: '提交数量',
      dataIndex: 'submitted_count',
      key: 'submitted_count',
      width: 90,
      align: 'right' as const,
    },
    {
      title: '通过数量',
      dataIndex: 'approved_count',
      key: 'approved_count',
      width: 90,
      align: 'right' as const,
    },
    {
      title: '打回数量',
      dataIndex: 'rejected_count',
      key: 'rejected_count',
      width: 90,
      align: 'right' as const,
      render: (val: number) => val > 0 ? <span style={{ color: '#ff4d4f' }}>{val}</span> : val,
    },
    {
      title: '无效数量',
      dataIndex: 'invalid_count',
      key: 'invalid_count',
      width: 90,
      align: 'right' as const,
      render: (val: number) => val > 0 ? <span style={{ color: '#999' }}>{val}</span> : val,
    },
    {
      title: '总用时',
      dataIndex: 'total_seconds',
      key: 'total_seconds',
      width: 100,
      align: 'right' as const,
      render: (val: number) => formatDuration(val),
    },
    {
      title: '平均用时',
      dataIndex: 'avg_seconds',
      key: 'avg_seconds',
      width: 100,
      align: 'right' as const,
      render: (val: number) => formatAvgDuration(val),
    },
    {
      title: '通过率',
      dataIndex: 'pass_rate',
      key: 'pass_rate',
      width: 100,
      align: 'right' as const,
      render: (val: number) => {
        if (val == null) return '-';
        const display = typeof val === 'number' && val <= 1 ? (val * 100).toFixed(1) : Number(val).toFixed(1);
        return <span style={{ color: getApprovalRateColor(Number(display)), fontWeight: 600 }}>{display}%</span>;
      },
    },
  ];

  return (
    <div>
      <PageHeader title="工时报表" subtitle="个人标注工作量统计与日报" />

      <Spin spinning={loading}>
        <Row gutter={[12, 12]} style={{ marginBottom: 24 }}>
          <Col span={4}>
            <Card size="small" styles={{ body: cardBodyStyle }}>
              <Statistic
                title="今日标注题数"
                value={stats?.today_labeled_count ?? '-'}
                prefix={<EditOutlined />}
                valueStyle={{ fontSize: 22 }}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" styles={{ body: cardBodyStyle }}>
              <Statistic
                title="今日提交题数"
                value={stats?.today_submitted_count ?? '-'}
                prefix={<FileTextOutlined />}
                valueStyle={{ fontSize: 22, color: '#1890ff' }}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" styles={{ body: cardBodyStyle }}>
              <Statistic
                title="今日有效题数"
                value={stats?.today_valid_count ?? '-'}
                valueStyle={{ fontSize: 22, color: '#52c41a' }}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" styles={{ body: cardBodyStyle }}>
              <Statistic
                title="今日无效题数"
                value={stats?.today_invalid_count ?? '-'}
                valueStyle={{ fontSize: 22, color: '#999' }}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" styles={{ body: cardBodyStyle }}>
              <Statistic
                title="今日通过数"
                value={stats?.today_approved_count ?? '-'}
                prefix={<CheckCircleOutlined />}
                valueStyle={{ fontSize: 22, color: '#52c41a' }}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" styles={{ body: cardBodyStyle }}>
              <Statistic
                title="今日打回数"
                value={stats?.today_rejected_count ?? '-'}
                prefix={<CloseCircleOutlined />}
                valueStyle={{ fontSize: 22, color: '#ff4d4f' }}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" styles={{ body: cardBodyStyle }}>
              <Statistic
                title="今日总用时"
                value={stats?.today_total_seconds != null ? formatDuration(stats.today_total_seconds) : '-'}
                prefix={<ClockCircleOutlined />}
                valueStyle={{ fontSize: 22 }}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" styles={{ body: cardBodyStyle }}>
              <Statistic
                title="平均每题用时"
                value={stats?.avg_seconds_per_item != null ? formatAvgDuration(stats.avg_seconds_per_item) : '-'}
                prefix={<ThunderboltOutlined />}
                valueStyle={{ fontSize: 22 }}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" styles={{ body: cardBodyStyle }}>
              <Statistic
                title="审核通过率"
                value={stats?.review_pass_rate != null ? (stats.review_pass_rate <= 1 ? (stats.review_pass_rate * 100).toFixed(1) : Number(stats.review_pass_rate).toFixed(1)) : '-'}
                suffix={stats?.review_pass_rate != null ? '%' : ''}
                prefix={<PercentageOutlined />}
                valueStyle={{ fontSize: 22, color: stats?.review_pass_rate != null ? getApprovalRateColor(stats.review_pass_rate <= 1 ? stats.review_pass_rate * 100 : stats.review_pass_rate) : undefined }}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" styles={{ body: cardBodyStyle }}>
              <Statistic
                title="AI/人工一致率"
                value={stats?.ai_human_agreement_rate != null ? (stats.ai_human_agreement_rate <= 1 ? (stats.ai_human_agreement_rate * 100).toFixed(1) : Number(stats.ai_human_agreement_rate).toFixed(1)) : '-'}
                suffix={stats?.ai_human_agreement_rate != null ? '%' : ''}
                prefix={<RobotOutlined />}
                valueStyle={{ fontSize: 22, color: '#722ed1' }}
              />
            </Card>
          </Col>
        </Row>
      </Spin>

      <Card title="日报明细" style={{ marginBottom: 24 }}>
        {dailyError && <Alert message={dailyError} type="error" showIcon closable onClose={() => setDailyError(null)} style={{ marginBottom: 16 }} />}
        <Row gutter={16} align="middle" style={{ marginBottom: 16 }}>
          <Col>
            <span style={{ marginRight: 8 }}>日期范围：</span>
            <RangePicker
              value={dateRange}
              onChange={(dates) => setDateRange(dates as [dayjs.Dayjs | null, dayjs.Dayjs | null] | null)}
              format="YYYY-MM-DD"
              placeholder={['开始日期', '结束日期']}
              allowClear
            />
          </Col>
          <Col>
            <span style={{ marginRight: 8 }}>任务：</span>
            <Select
              value={selectedTaskId}
              onChange={setSelectedTaskId}
              placeholder="全部任务"
              allowClear
              style={{ width: 200 }}
              options={tasks.map((t) => ({ label: t.name, value: t.id }))}
            />
          </Col>
          <Col>
            <Button type="primary" onClick={handleQuery}>
              查询
            </Button>
          </Col>
        </Row>

        <Table
          rowKey={(record) => `${record.date}_${record.task_id}`}
          columns={columns}
          dataSource={dailyData}
          loading={tableLoading}
          pagination={{
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
            defaultPageSize: 20,
          }}
          size="middle"
          bordered
        />
      </Card>
    </div>
  );
};

export default WorkReportPage;
