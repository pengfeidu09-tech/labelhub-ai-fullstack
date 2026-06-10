import React, { useState, useEffect, useMemo } from 'react';
import { Table, Button, Input, Select, Modal, Tag, Card, message, Spin, Collapse } from 'antd';
import type { ColumnType } from 'antd/es/table';
import { DownloadOutlined } from '@ant-design/icons';
import { getAnnotations, getDrafts, type Annotation } from '../../api/owner';
import { normalizeList } from '../../utils/format';
import { formatDateTime } from '../../utils/time';

const { Option } = Select;

// 状态归一化函数
function normalizeStatus(status: string | null | undefined): string {
  const s = String(status || '').toLowerCase();
  
  if (['draft', '草稿'].includes(s)) return 'draft';
  if (['approved', 'passed', 'accepted', '已通过', '通过'].includes(s)) return 'approved';
  if (['rejected_to_modify', 'need_modify', 'modify_required', '待修改', '退回修改'].includes(s)) return 'rejected_to_modify';
  if (['submitted', '已提交'].includes(s)) return 'submitted';
  if (['rejected', 'failed', '驳回', '已驳回', '拒绝'].includes(s)) return 'rejected';
  
  return s || 'unknown';
}

// 状态标签函数
function getStatusLabel(status: string | null | undefined): string {
  const s = normalizeStatus(status);
  const statusLabels: Record<string, string> = {
    'draft': '草稿',
    'approved': '已通过',
    'rejected_to_modify': '待修改',
    'submitted': '已提交',
    'rejected': '已驳回',
    'unknown': '未知'
  };
  return statusLabels[s] || status || '未知';
}

// 获取状态标签组件
function getStatusTag(status: string | null | undefined) {
  const s = normalizeStatus(status);
  const statusMap: Record<string, { color: string; text: string }> = {
    'draft': { color: 'orange', text: '草稿' },
    'submitted': { color: 'blue', text: '已提交' },
    'approved': { color: 'green', text: '已通过' },
    'rejected': { color: 'red', text: '已驳回' },
    'rejected_to_modify': { color: 'gold', text: '待修改' },
    'unknown': { color: 'default', text: '未知' }
  };
  const info = statusMap[s] || { color: 'default', text: getStatusLabel(status) };
  return <Tag color={info.color}>{info.text}</Tag>;
}

const downloadFile = (filename: string, content: string, mimeType: string) => {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

// 导出时添加归一化状态
interface ExportAnnotation {
  id: number;
  task_id: number;
  dataset_item_id: number;
  template_id?: number;
  template_name?: string;
  labeler_id?: number;
  status: string;
  status_label: string;
  raw_status: string;
  result: Record<string, any>;
  created_at?: string;
  updated_at?: string;
  ai_review?: any;
  ai_provider?: string;
  ai_confidence?: number;
  ai_relevance?: string;
  ai_accuracy?: string;
  ai_completeness?: string;
  ai_safety?: string;
  ai_reason?: string;
  ai_issue_tags?: string[];
}

const toExportAnnotation = (ann: Annotation): ExportAnnotation => {
  const normalized = normalizeStatus(ann.status);
  const statusLabels: Record<string, string> = {
    'draft': '草稿',
    'submitted': '已提交',
    'approved': '已通过',
    'rejected': '已驳回',
    'rejected_to_modify': '待修改',
    'reviewing': '审核中',
    'unknown': '未知'
  };
  
  const aiReview = ann.ai_review;
  return {
    ...ann,
    status: normalized,
    status_label: statusLabels[normalized] || normalized,
    raw_status: ann.status || '',
    ai_review: aiReview,
    ai_provider: aiReview?.provider,
    ai_confidence: aiReview?.confidence,
    ai_relevance: aiReview?.suggestion?.relevance,
    ai_accuracy: aiReview?.suggestion?.accuracy,
    ai_completeness: aiReview?.suggestion?.completeness,
    ai_safety: aiReview?.suggestion?.safety,
    ai_reason: aiReview?.suggestion?.reason,
    ai_issue_tags: aiReview?.suggestion?.issue_tags
  };
};

const exportToJson = (annotations: Annotation[]) => {
  if (annotations.length === 0) {
    message.warning('暂无可导出的标注结果');
    return;
  }
  const exportData = annotations.map(toExportAnnotation);
  const content = JSON.stringify(exportData, null, 2);
  downloadFile('labelhub_annotations.json', content, 'application/json');
};

const exportToJsonl = (annotations: Annotation[]) => {
  if (annotations.length === 0) {
    message.warning('暂无可导出的标注结果');
    return;
  }
  const lines = annotations.map(ann => JSON.stringify(toExportAnnotation(ann)));
  const content = lines.join('\n');
  downloadFile('labelhub_annotations.jsonl', content, 'application/x-ndjson');
};

// CSV 转义函数
function csvEscape(value: any) {
  const str = value == null ? '' : (typeof value === 'object' ? JSON.stringify(value) : String(value));
  return `"${str.replace(/"/g, '""')}"`;
}

const exportToCsv = (annotations: Annotation[]) => {
  if (annotations.length === 0) {
    message.warning('暂无可导出的标注结果');
    return;
  }
  
  const headers = [
    'id',
    'task_id',
    'dataset_item_id',
    'template_id',
    'template_name',
    'labeler_id',
    'raw_status',
    'status',
    'status_label',
    'created_at',
    'updated_at',
    'result',
    'ai_provider',
    'ai_confidence',
    'ai_relevance',
    'ai_accuracy',
    'ai_completeness',
    'ai_safety',
    'ai_reason',
    'ai_issue_tags'
  ];
  
  const rows = annotations.map(ann => {
    const exportAnn = toExportAnnotation(ann);
    return [
      exportAnn.id,
      exportAnn.task_id,
      exportAnn.dataset_item_id,
      exportAnn.template_id || '',
      exportAnn.template_name || '',
      exportAnn.labeler_id || '',
      exportAnn.raw_status,
      exportAnn.status,
      exportAnn.status_label,
      exportAnn.created_at || '',
      exportAnn.updated_at || '',
      exportAnn.result,
      exportAnn.ai_provider || '',
      exportAnn.ai_confidence || '',
      exportAnn.ai_relevance || '',
      exportAnn.ai_accuracy || '',
      exportAnn.ai_completeness || '',
      exportAnn.ai_safety || '',
      exportAnn.ai_reason || '',
      exportAnn.ai_issue_tags || ''
    ].map(csvEscape);
  });
  
  const content = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  downloadFile('labelhub_annotations.csv', content, 'text/csv;charset=utf-8');
};

const AnnotationPage: React.FC = () => {
  const [rawAnnotations, setRawAnnotations] = useState<Annotation[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedAnnotation, setSelectedAnnotation] = useState<Annotation | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  
  const [filters, setFilters] = useState({
    taskId: '',
    templateId: '',
    statusFilter: 'all'
  });

  const fetchData = async () => {
    setLoading(true);
    try {
      const [annotationRes, draftRes] = await Promise.all([
        getAnnotations(),
        getDrafts()
      ]);
      
      const annotationList = normalizeList<Annotation>(annotationRes);
      const draftList = normalizeList<Annotation>(draftRes);
      
      const allData = [...annotationList, ...draftList];
      setRawAnnotations(allData);
    } catch (error: any) {
      console.error('[OwnerAnnotations] fetch annotations error:', error?.response || error);
      message.error('获取标注结果失败: ' + (error?.message || '未知错误'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // 1. rawAnnotations → normalizedRows
  const normalizedRows = useMemo(() => {
    return rawAnnotations.map(row => ({
      ...row,
      normalizedStatus: normalizeStatus(row.status),
      statusLabel: getStatusLabel(row.status)
    }));
  }, [rawAnnotations]);

  // 2. normalizedRows → filteredRows
  const filteredRows = useMemo(() => {
    const result = normalizedRows.filter(row => {
      const statusOk =
        filters.statusFilter === 'all' ||
        row.normalizedStatus === filters.statusFilter;

      const taskOk =
        !filters.taskId ||
        String(row.task_id || '').includes(String(filters.taskId));

      const templateOk =
        !filters.templateId ||
        String(row.template_id || '').includes(String(filters.templateId));

      return statusOk && taskOk && templateOk;
    });
    return result;
  }, [normalizedRows, filters]);

  // 3. filteredRows → tableRows
  const tableRows = filteredRows;

  // 当筛选条件变化时，重置到第1页
  useEffect(() => {
    setCurrentPage(1);
  }, [filters]);

  const handleViewDetail = (annotation: Annotation) => {
    setSelectedAnnotation(annotation);
    setModalVisible(true);
  };

  const handleFilterChange = (key: string, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const columns: ColumnType<any>[] = [
    { 
      title: 'ID', 
      dataIndex: 'id', 
      key: 'id', 
      width: 80,
      fixed: 'left' as const
    },
    { 
      title: '任务ID', 
      dataIndex: 'task_id', 
      key: 'task_id', 
      width: 100
    },
    { 
      title: '数据项ID', 
      dataIndex: 'dataset_item_id', 
      key: 'dataset_item_id', 
      width: 120
    },
    { 
      title: '模板ID', 
      dataIndex: 'template_id', 
      key: 'template_id', 
      width: 100,
      render: (id) => id || '-'
    },
    { 
      title: '模板名称', 
      dataIndex: 'template_name', 
      key: 'template_name', 
      width: 180,
      render: (name) => name || '-'
    },
    { 
      title: '标注员', 
      dataIndex: 'labeler_id', 
      key: 'labeler_id', 
      width: 100,
      render: (id) => id || '-'
    },
    { 
      title: '状态', 
      dataIndex: 'status', 
      key: 'status', 
      width: 100,
      render: (status) => getStatusTag(status)
    },
    { 
      title: '创建时间', 
      dataIndex: 'created_at', 
      key: 'created_at', 
      width: 180,
      render: (date) => date ? formatDateTime(date) : '-'
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (date) => date ? formatDateTime(date) : '-'
    },
    { 
      title: '操作', 
      key: 'action', 
      width: 120,
      fixed: 'right' as const,
      render: (_: unknown, record: any) => (
        <Button size="small" onClick={() => handleViewDetail(record)}>查看详情</Button>
      )
    }
  ];

  // 统计逻辑 - 基于全量数据
  const total = rawAnnotations.length;
  const approvedCount = normalizedRows.filter(r => r.normalizedStatus === 'approved').length;
  const rejectedToModifyCount = normalizedRows.filter(r => r.normalizedStatus === 'rejected_to_modify').length;
  const draftCount = normalizedRows.filter(r => r.normalizedStatus === 'draft').length;
  const passRate = total ? Math.round((approvedCount / total) * 100) : 0;

  return (
    <div>
      <h1>标注结果管理</h1>
      <p>查看和导出标注结果</p>
      
      {/* 调试信息 - 仅在开发模式显示 */}
      {import.meta.env.DEV && (
        <Collapse defaultActiveKey={[]} style={{ marginBottom: 16 }}>
          <Collapse.Panel header="调试信息" key="1">
            <div style={{ fontSize: 12, color: '#666' }}>
              <div>当前筛选：{filters.statusFilter} | 任务ID：{filters.taskId || '无'} | 模板ID：{filters.templateId || '无'}</div>
              <div>原始数量：{normalizedRows.length} | 筛选数量：{filteredRows.length} | 表格渲染数量：{tableRows.length}</div>
              <div style={{ marginTop: 8, padding: 8, backgroundColor: '#e6f7ff', borderRadius: 4 }}>
                <strong>Table dataSource statuses:</strong> {tableRows.map(r => getStatusLabel(r.status)).join(', ')}
              </div>
            </div>
          </Collapse.Panel>
        </Collapse>
      )}
      
      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1890ff' }}>{total}</div>
            <div style={{ fontSize: 12, color: '#666' }}>总记录数</div>
          </div>
          <div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#52c41a' }}>{approvedCount}</div>
            <div style={{ fontSize: 12, color: '#666' }}>已通过</div>
          </div>
          <div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#faad14' }}>{rejectedToModifyCount}</div>
            <div style={{ fontSize: 12, color: '#666' }}>待修改</div>
          </div>
          <div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#722ed1' }}>{draftCount}</div>
            <div style={{ fontSize: 12, color: '#666' }}>草稿</div>
          </div>
          <div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1890ff' }}>{passRate}%</div>
            <div style={{ fontSize: 12, color: '#666' }}>通过率</div>
          </div>
        </div>
      </Card>

      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span>状态：</span>
            <Select
              value={filters.statusFilter}
              onChange={(value) => handleFilterChange('statusFilter', value)}
              style={{ width: 120 }}
            >
              <Option value="all">全部</Option>
              <Option value="draft">草稿</Option>
              <Option value="approved">已通过</Option>
              <Option value="rejected_to_modify">待修改</Option>
            </Select>
          </div>
          
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span>任务ID：</span>
            <Input
              type="number"
              placeholder="请输入"
              value={filters.taskId}
              onChange={(e) => handleFilterChange('taskId', e.target.value)}
              style={{ width: 120 }}
            />
          </div>
          
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span>模板ID：</span>
            <Input
              type="number"
              placeholder="请输入"
              value={filters.templateId}
              onChange={(e) => handleFilterChange('templateId', e.target.value)}
              style={{ width: 120 }}
            />
          </div>
          
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              onClick={() => exportToJson(filteredRows)}
            >
              导出 JSON
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={() => exportToJsonl(filteredRows)}
            >
              导出 JSONL
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={() => exportToCsv(filteredRows)}
            >
              导出 CSV
            </Button>
          </div>
        </div>
      </Card>

      <Card>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '50px' }}>
            <Spin size="large" />
          </div>
        ) : (
          <Table
            columns={columns}
            dataSource={tableRows}
            rowKey={(record) => `${record.id}_${record.task_id}_${record.dataset_item_id}_${record.status}`}
            scroll={{ x: 1300 }}
            pagination={{
              current: currentPage,
              pageSize: pageSize,
              total: filteredRows.length,
              showSizeChanger: true,
              showQuickJumper: true,
              showTotal: (total) => `共 ${total} 条记录`,
              onChange: (page, size) => {
                setCurrentPage(page);
                if (size !== pageSize) setPageSize(size);
              }
            }}
          />
        )}
      </Card>

      <Modal
        title={`标注详情 #${selectedAnnotation?.id}`}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        width={800}
        footer={null}
      >
        {selectedAnnotation && (
          <div>
            <div style={{ marginBottom: 16, paddingBottom: 16, borderBottom: '1px solid #e8e8e8' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div>
                  <strong>ID：</strong>{selectedAnnotation.id}
                </div>
                <div>
                  <strong>任务ID：</strong>{selectedAnnotation.task_id}
                </div>
                <div>
                  <strong>数据项ID：</strong>{selectedAnnotation.dataset_item_id}
                </div>
                <div>
                  <strong>模板ID：</strong>{selectedAnnotation.template_id || '-'}
                </div>
                <div>
                  <strong>模板名称：</strong>{selectedAnnotation.template_name || '-'}
                </div>
                <div>
                  <strong>标注员：</strong>{selectedAnnotation.labeler_id || '-'}
                </div>
                <div>
                  <strong>状态：</strong>{getStatusTag(selectedAnnotation.status)}
                </div>
                <div>
                  <strong>创建时间：</strong>{selectedAnnotation.created_at ? formatDateTime(selectedAnnotation.created_at) : '-'}
                </div>
                <div>
                  <strong>更新时间：</strong>{selectedAnnotation.updated_at ? formatDateTime(selectedAnnotation.updated_at) : '-'}
                </div>
              </div>
            </div>
            
            <div>
              <h4 style={{ marginBottom: 12 }}>标注结果（FormData）</h4>
              {selectedAnnotation.result && Object.keys(selectedAnnotation.result).length > 0 ? (
                <pre style={{ 
                  background: '#f9fafb', 
                  padding: 12, 
                  borderRadius: 8, 
                  whiteSpace: 'pre-wrap', 
                  wordBreak: 'break-word', 
                  overflowX: 'hidden', 
                  fontSize: 13, 
                  maxHeight: 400, 
                  overflow: 'auto' 
                }}>
                  {JSON.stringify(selectedAnnotation.result, null, 2)}
                </pre>
              ) : (
                <div style={{ color: '#999', padding: 16, textAlign: 'center' }}>
                  暂无标注结果
                </div>
              )}
            </div>
            
            {/* AI 预审结果 */}
            <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid #e8e8e8' }}>
              <h4 style={{ marginBottom: 12 }}>🤖 AI 预审结果</h4>
              {selectedAnnotation.ai_review ? (
                <div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 12 }}>
                    <div>
                      <strong>Provider：</strong>{selectedAnnotation.ai_review.provider}
                    </div>
                    <div>
                      <strong>置信度：</strong>{((selectedAnnotation.ai_review.confidence ?? 0) * 100).toFixed(0)}%
                    </div>
                    <div>
                      <strong>生成时间：</strong>{selectedAnnotation.ai_review.generated_at ? formatDateTime(selectedAnnotation.ai_review.generated_at) : '-'}
                    </div>
                  </div>
                  {selectedAnnotation.ai_review.suggestion && (
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 8, marginBottom: 12 }}>
                        <div style={{ padding: 8, backgroundColor: '#f3f4f6', borderRadius: 4 }}>
                          <div style={{ fontSize: 10, color: '#9ca3af', marginBottom: 4 }}>相关性</div>
                          <div style={{ fontSize: 12, fontWeight: 600 }}>{selectedAnnotation.ai_review.suggestion.relevance}</div>
                        </div>
                        <div style={{ padding: 8, backgroundColor: '#f3f4f6', borderRadius: 4 }}>
                          <div style={{ fontSize: 10, color: '#9ca3af', marginBottom: 4 }}>准确性</div>
                          <div style={{ fontSize: 12, fontWeight: 600 }}>{selectedAnnotation.ai_review.suggestion.accuracy}</div>
                        </div>
                        <div style={{ padding: 8, backgroundColor: '#f3f4f6', borderRadius: 4 }}>
                          <div style={{ fontSize: 10, color: '#9ca3af', marginBottom: 4 }}>完整性</div>
                          <div style={{ fontSize: 12, fontWeight: 600 }}>{selectedAnnotation.ai_review.suggestion.completeness}</div>
                        </div>
                        <div style={{ padding: 8, backgroundColor: '#f3f4f6', borderRadius: 4 }}>
                          <div style={{ fontSize: 10, color: '#9ca3af', marginBottom: 4 }}>安全性</div>
                          <div style={{ fontSize: 12, fontWeight: 600 }}>{selectedAnnotation.ai_review.suggestion.safety}</div>
                        </div>
                      </div>
                      <div style={{ marginBottom: 8 }}>
                        <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 4 }}>建议</div>
                        <div style={{ fontSize: 12, color: '#374151', padding: 8, backgroundColor: '#f9fafb', borderRadius: 4 }}>
                          {selectedAnnotation.ai_review.suggestion.reason}
                        </div>
                      </div>
                      {selectedAnnotation.ai_review.suggestion.issue_tags && selectedAnnotation.ai_review.suggestion.issue_tags.length > 0 && (
                        <div>
                          <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 4 }}>问题标签</div>
                          <div>
                            {selectedAnnotation.ai_review.suggestion.issue_tags.map((tag: string, i: number) => (
                              <Tag key={i} color="orange" style={{ marginRight: 4, marginBottom: 4 }}>
                                {tag}
                              </Tag>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                  {selectedAnnotation.ai_review.raw_text && (
                    <div>
                      <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 4 }}>原始文本</div>
                      <div style={{ fontSize: 12, color: '#374151', padding: 8, backgroundColor: '#f9fafb', borderRadius: 4 }}>
                        {selectedAnnotation.ai_review.raw_text}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ color: '#999', padding: 16, textAlign: 'center' }}>
                  暂无 AI 预审结果
                </div>
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default AnnotationPage;
