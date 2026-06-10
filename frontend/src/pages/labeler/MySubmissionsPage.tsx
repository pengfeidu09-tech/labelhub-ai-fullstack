import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Empty, Spin, message, Button, Modal, Descriptions, Input, Row, Col, Statistic, Tooltip } from 'antd';
import { Submission } from '../../types/submission';
import { getLabelerSubmissions, LABELER_ID, exportAnnotationsJson, exportAnnotationsCsv } from '../../api/labeler';
import { normalizeList } from '../../utils/format';
import { formatDateTime } from '../../utils/time';
import { FileTextOutlined, EditOutlined, EyeOutlined, WarningOutlined, DownloadOutlined } from '@ant-design/icons';

const MySubmissionsPage: React.FC = () => {
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSubmission, setSelectedSubmission] = useState<Submission | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [serverStats, setServerStats] = useState<{total: number; draft: number; submitted: number; rejected: number; approved: number; invalid_submitted: number} | null>(null);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  
  // 筛选状态
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [taskIdFilter, setTaskIdFilter] = useState<string>('');
  const [itemIdFilter, setItemIdFilter] = useState<string>('');

  useEffect(() => {
    fetchSubmissions();
  }, [statusFilter, currentPage, pageSize]);

  const fetchSubmissions = async (page?: number, limit?: number) => {
    try {
      setLoading(true);
      const p = page || currentPage;
      const l = limit || pageSize;
      const data = await getLabelerSubmissions({ 
        status: statusFilter !== 'all' ? statusFilter : undefined,
        page: p,
        limit: l
      } as any);
      const items = normalizeList<Submission>(data);
      setSubmissions(items);
      // 使用后端返回的全量统计和分页
      const responseData = data as any;
      if (responseData?.stats) {
        setServerStats(responseData.stats);
      }
      if (responseData?.total !== undefined) {
        setTotal(responseData.total);
      }
    } catch (error) {
      message.error('获取提交记录失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  // 统计数据：优先使用后端全量统计，fallback 到前端分页统计
  const stats = serverStats ? {
    total: serverStats.total,
    draft: serverStats.draft,
    submitted: serverStats.submitted,
    rejected: serverStats.rejected,
    approved: serverStats.approved,
    invalid_submitted: serverStats.invalid_submitted,
  } : {
    total: submissions.length,
    draft: submissions.filter(s => s.status === 'draft' || s.status === 'claimed').length,
    submitted: submissions.filter(s => s.status === 'submitted').length,
    rejected: submissions.filter(s => s.status === 'rejected_to_modify' || s.status === 'returned_to_modify' || s.status === 'needs_revision').length,
    approved: submissions.filter(s => s.status === 'approved' || s.status === 'export_ready').length,
    invalid_submitted: submissions.filter(s => s.status === 'invalid_submitted').length,
  };

  // 筛选数据（仅做 task_id / item_id 的前端筛选，状态筛选由后端处理）
  const filteredSubmissions = submissions.filter(item => {
    // 任务ID筛选
    if (taskIdFilter && String(item.task_id) !== taskIdFilter) {
      return false;
    }
    // 数据项ID筛选
    if (itemIdFilter && String(item.dataset_item_id) !== itemIdFilter) {
      return false;
    }
    return true;
  });

  const getStatusTag = (status: string) => {
    switch (status) {
      case 'draft':
      case 'saved_draft':
        return <Tag color="gray">草稿</Tag>;
      case 'claimed':
      case 'in_progress':
        return <Tag color="blue">已领取</Tag>;
      case 'submitted':
        return <Tag color="blue">已提交 / 待审核</Tag>;
      case 'approved':
      case 'export_ready':
        return <Tag color="green">已通过</Tag>;
      case 'rejected_to_modify':
        return <Tag color="red">已打回</Tag>;
      case 'returned_to_modify':
      case 'needs_revision':
        return <Tag color="orange">待返修</Tag>;
      case 'rework':
      case 'rework_submitted':
      case 'revised_submitted':
        return <Tag color="blue">返修已提交</Tag>;
      case 'invalid_submitted':
        return <Tag color="orange">无效待审</Tag>;
      case 'invalid_approved':
        return <Tag color="red">无效已确认</Tag>;
      default:
        return <Tag>{status}</Tag>;
    }
  };

  const handleViewDetail = (record: Submission) => {
    setSelectedSubmission(record);
    setModalOpen(true);
  };

  const handleContinueEdit = (record: Submission) => {
    const status = record.status;
    
    // 已提交/已通过：不跳 workbench，只打开详情弹窗
    if (status === 'submitted' || status === 'approved' || status === 'export_ready' || status === 'invalid_submitted' || status === 'invalid_approved' || status === 'rework_submitted' || status === 'revised_submitted') {
      handleViewDetail(record);
      return;
    }
    
    let mode = 'edit';
    if (status === 'rejected_to_modify' || status === 'rework' || status === 'returned_to_modify' || status === 'needs_revision') {
      mode = 'rework';
    } else if (status === 'draft' || status === 'saved_draft') {
      mode = 'draft';
    } else if (status === 'claimed' || status === 'in_progress' || status === 'new') {
      mode = 'new';
    }
    
    // 使用这条记录自己的 work_key 和 annotation_id
    const labelerId = 2;
    const workKey = (record as any).work_key || `${record.task_id}:${record.dataset_item_id}:${labelerId}`;
    const annotationId = record.id;
    const url = `/labeler/workbench?submission_id=${annotationId}&item_id=${record.dataset_item_id}&task_id=${record.task_id}&work_key=${workKey}&mode=${mode}`;
    window.location.href = url;
  };

  const handleExport = async (format: 'json' | 'csv') => {
    try {
      const blob = format === 'json' ? await exportAnnotationsJson() : await exportAnnotationsCsv();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `annotations_export.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      message.success(`已导出 ${format.toUpperCase()} 文件`);
    } catch (error) {
      message.error('导出失败');
      console.error(error);
    }
  };

  const columns = [
    {
      title: '提交ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
      render: (value: number) => `#${value}`
    },
    {
      title: '任务ID',
      dataIndex: 'task_id',
      key: 'task_id',
      width: 80,
      render: (value: number) => `#${value}`
    },
    {
      title: '数据项ID',
      dataIndex: 'dataset_item_id',
      key: 'dataset_item_id',
      width: 80,
      render: (value: number) => `#${value}`
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => getStatusTag(status)
    },
    {
      title: 'AI分数',
      key: 'ai_score',
      width: 80,
      render: (_: any, record: any) => {
        const score = record.ai_review?.overall_score ?? record.ai_review?.score ?? record.ai_score ?? record.ai_review_score;
        if (score == null) return '-';
        return <span style={{ color: score >= 80 ? '#52c41a' : score >= 60 ? '#faad14' : '#ff4d4f', fontWeight: 600 }}>{score}</span>;
      }
    },
    {
      title: 'AI风险',
      key: 'ai_risk',
      width: 80,
      render: (_: any, record: any) => {
        const risk = record.ai_review?.risk_level ?? record.ai_risk_level ?? record.ai_review_risk_level;
        if (!risk) return '-';
        const color = risk === 'high' ? 'red' : risk === 'medium' ? 'orange' : 'green';
        const text = risk === 'high' ? '高' : risk === 'medium' ? '中' : '低';
        return <Tag color={color} style={{ fontSize: 11 }}>{text}</Tag>;
      }
    },
    {
      title: '审核结果',
      key: 'review_result',
      width: 90,
      render: (_: any, record: any) => {
        const status = record.status;
        if (status === 'approved' || status === 'export_ready') return <Tag color="green">已通过</Tag>;
        if (status === 'rejected_to_modify') return <Tag color="red">已打回</Tag>;
        if (status === 'returned_to_modify' || status === 'needs_revision') return <Tag color="orange">待返修</Tag>;
        if (status === 'rework_submitted' || status === 'revised_submitted') return <Tag color="blue">返修已提交</Tag>;
        if (status === 'human_reviewing') return <Tag color="orange">审核中</Tag>;
        if (status === 'submitted') return <Tag color="blue">待审核</Tag>;
        if (status === 'invalid_submitted') return <Tag color="orange">无效待审</Tag>;
        if (status === 'invalid_approved') return <Tag color="red">无效已确认</Tag>;
        return '-';
      }
    },
    {
      title: '退回原因',
      dataIndex: 'rejected_reason',
      key: 'rejected_reason',
      width: 140,
      render: (value: any) => {
        if (!value) return '-';
        const displayText = value.length > 20 ? value.substring(0, 20) + '...' : value;
        return (
          <Tooltip title={value}>
            <span style={{ color: '#fa8c16', cursor: 'help', fontSize: 12 }}>
              {displayText}
            </span>
          </Tooltip>
        );
      }
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 140,
      render: (value: string) => value ? formatDateTime(value) : '-'
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: any, record: Submission) => {
        const status = record.status;
        if (status === 'approved' || status === 'export_ready' || status === 'submitted' || status === 'invalid_submitted' || status === 'invalid_approved' || status === 'rework_submitted' || status === 'revised_submitted') {
          return (
            <Button icon={<EyeOutlined />} size="small" onClick={() => handleViewDetail(record)}>
              查看
            </Button>
          );
        }
        if (status === 'rejected_to_modify' || status === 'rework' || status === 'returned_to_modify' || status === 'needs_revision') {
          return (
            <Button type="primary" danger icon={<EditOutlined />} size="small" onClick={() => handleContinueEdit(record)}>
              继续返修
            </Button>
          );
        }
        return (
          <Button type="primary" icon={<EditOutlined />} size="small" onClick={() => handleContinueEdit(record)}>
            {status === 'draft' || status === 'saved_draft' ? '继续编辑' : '继续标注'}
          </Button>
        );
      }
    }
  ];

  return (
    <div className="p-6">
      <h1>我的提交</h1>
      <p>查看我的标注提交记录</p>
      <p>标注员ID: {LABELER_ID}</p>
      
      {/* 顶部统计卡片 */}
      <Row gutter={16} className="mb-6">
        <Col span={4}>
          <Card>
            <Statistic
              title="全部"
              value={stats.total}
              prefix={<FileTextOutlined />}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
              title="草稿"
              value={stats.draft}
              prefix={<EditOutlined />}
              valueStyle={{ color: '#d9d9d9' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
              title="已提交"
              value={stats.submitted}
              prefix={<EyeOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
                title="待修改"
                value={stats.rejected}
                prefix={<WarningOutlined />}
                valueStyle={{ color: '#fa8c16' }}
              />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
              title="已通过"
              value={stats.approved}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
              title="无效待审"
              value={serverStats?.invalid_submitted ?? 0}
              valueStyle={{ color: '#fa8c16' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 筛选区 */}
      <Card className="mb-6">
        <Row gutter={16} align="middle">
          <Col span={6}>
            <label className="mr-3">状态：</label>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setCurrentPage(1); // 切换筛选时重置页码
              }}
              className="px-3 py-2 border rounded"
            >
              <option value="all">全部</option>
              <option value="draft">草稿/已领取</option>
              <option value="submitted">已提交</option>
              <option value="rejected">待修改</option>
              <option value="approved">已通过</option>
              <option value="invalid_submitted">无效待审</option>
            </select>
          </Col>
          <Col span={6}>
            <label className="mr-3">任务ID：</label>
            <Input
              placeholder="输入任务ID"
              value={taskIdFilter}
              onChange={(e) => setTaskIdFilter(e.target.value)}
              style={{ width: 150 }}
            />
          </Col>
          <Col span={6}>
            <label className="mr-3">数据项ID：</label>
            <Input
              placeholder="输入数据项ID"
              value={itemIdFilter}
              onChange={(e) => setItemIdFilter(e.target.value)}
              style={{ width: 150 }}
            />
          </Col>
          <Col span={6}>
            <Button
              onClick={() => {
                setStatusFilter('all');
                setTaskIdFilter('');
                setItemIdFilter('');
              }}
            >
              重置筛选
            </Button>
            <Button onClick={() => handleExport('json')} icon={<DownloadOutlined />} style={{ marginLeft: 8 }}>导出 JSON</Button>
            <Button onClick={() => handleExport('csv')} icon={<DownloadOutlined />} style={{ marginLeft: 8 }}>导出 CSV</Button>
          </Col>
        </Row>
      </Card>

      {/* 提交列表 */}
      <Card>
        {loading ? (
          <Spin spinning={loading} tip="加载中..."><div /></Spin>
        ) : filteredSubmissions.length === 0 ? (
          <Empty description="暂无提交记录" />
        ) : (
          <Table
            rowKey="id"
            columns={columns}
            dataSource={filteredSubmissions}
            pagination={{ 
              current: currentPage,
              pageSize: pageSize,
              total: total,
              showSizeChanger: true,
              showTotal: (t) => `共 ${t} 条`,
              onChange: (page, size) => {
                setCurrentPage(page);
                setPageSize(size);
              }
            }}
          />
        )}
      </Card>

      {/* 详情弹窗 */}
      <Modal
        title="提交详情"
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setSelectedSubmission(null);
        }}
        footer={null}
        width={800}
      >
        {selectedSubmission && (
          <div>
            <Descriptions bordered column={2}>
              <Descriptions.Item label="提交ID">#{selectedSubmission.id}</Descriptions.Item>
              <Descriptions.Item label="任务ID">#{selectedSubmission.task_id}</Descriptions.Item>
              <Descriptions.Item label="数据项ID">#{selectedSubmission.dataset_item_id}</Descriptions.Item>
              <Descriptions.Item label="状态">{getStatusTag(selectedSubmission.status)}</Descriptions.Item>
              <Descriptions.Item label="版本">v{(selectedSubmission as any).version || selectedSubmission.revision_no || 1}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDateTime(selectedSubmission.created_at || '')}</Descriptions.Item>
              <Descriptions.Item label="更新时间" span={2}>{formatDateTime((selectedSubmission as any).updated_at || '')}</Descriptions.Item>
              {(selectedSubmission as any).reviewer_id && (
                <Descriptions.Item label="审核员ID">#{(selectedSubmission as any).reviewer_id}</Descriptions.Item>
              )}
              {(selectedSubmission as any).reviewed_at && (
                <Descriptions.Item label="审核时间">{formatDateTime((selectedSubmission as any).reviewed_at)}</Descriptions.Item>
              )}
            </Descriptions>
            
            {/* 退回原因 */}
            {(selectedSubmission as any).rejected_reason && (
              <div style={{ marginTop: 16, padding: 12, backgroundColor: '#fff7e6', borderRadius: 8 }}>
                <h4 style={{ color: '#fa8c16', marginBottom: 8 }}>⚠️ 审核退回原因</h4>
                <p>{(selectedSubmission as any).rejected_reason}</p>
              </div>
            )}
            
            {/* 提交结果 */}
            <div style={{ marginTop: 16 }}>
              <h4>标注结果：</h4>
              <pre style={{ 
                whiteSpace: 'pre-wrap', 
                wordBreak: 'break-word', 
                maxHeight: 400, 
                overflow: 'auto', 
                backgroundColor: '#f5f5f5', 
                padding: 16, 
                borderRadius: 8 
              }}>
                {JSON.stringify((selectedSubmission as any).result || selectedSubmission.data || selectedSubmission.submission_data || selectedSubmission.label_data || {}, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default MySubmissionsPage;