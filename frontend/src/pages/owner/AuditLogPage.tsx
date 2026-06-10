import React, { useState, useEffect } from 'react';
import { PageHeader } from '../../components/common/PageHeader';
import { Table, Button, Space, message, Tag, Modal, Collapse } from 'antd';
import { getAuditLogs } from '../../api/auditLogs';
import { AuditLog } from '../../types/auditLog';
import { formatDateTime } from '../../utils/time';
import { getAuditActionText, getAuditActionColor, formatUserRole, formatTargetType } from '../../utils/status';

interface AuditLogDisplay extends AuditLog {
  actionText?: string;
}

// ── 审计日志关联上下文格式化 ──
const formatAuditContext = (log: AuditLogDisplay): string => {
  const parts: string[] = [];
  if (log.target_id) {
    const typeLabel = formatTargetType(log.target_type || '');
    parts.push(`${typeLabel} #${log.target_id}`);
  }
  if (log.task_id) parts.push(`Task #${log.task_id}`);
  if (log.item_id) parts.push(`Item #${log.item_id}`);
  if (log.submission_id) parts.push(`标注 #${log.submission_id}`);
  if (log.annotation_id) parts.push(`标注 #${log.annotation_id}`);
  if (log.work_key) parts.push(`work_key=${log.work_key}`);
  return parts.length > 0 ? parts.join(', ') : '-';
};

// ── 目标ID带类型标签 ──
const formatTargetIdWithType = (targetType: string, targetId: number): string => {
  if (!targetId) return '-';
  const typeLabel = formatTargetType(targetType || '');
  return `${typeLabel} #${targetId}`;
};

const AuditLogPage: React.FC = () => {
  const [auditLogs, setAuditLogs] = useState<AuditLogDisplay[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedLog, setSelectedLog] = useState<AuditLogDisplay | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);

  const fetchAuditLogs = async () => {
    setLoading(true);
    try {
      const res = await getAuditLogs();
      const logs = res.items || [];
      const logsWithText = logs.map((log: AuditLog) => ({
        ...log,
        actionText: getAuditActionText(log.action)
      }));
      setAuditLogs(logsWithText);
    } catch (error) {
      message.error('获取审计日志失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditLogs();
  }, []);

  const showDetail = (log: AuditLogDisplay) => {
    setSelectedLog(log);
    setDetailVisible(true);
  };





  const columns = [
    { 
      title: 'ID', 
      dataIndex: 'id', 
      key: 'id', 
      width: 80 
    },
    { 
      title: '用户', 
      dataIndex: 'user_id', 
      key: 'user_id', 
      width: 100,
      render: (userId: number) => (
        <span>{formatUserRole(userId)}</span>
      )
    },
    { 
      title: '操作', 
      dataIndex: 'action', 
      key: 'action', 
      width: 200,
      render: (action: string) => (
        <div>
          <Tag color={getAuditActionColor(action)}>
            {getAuditActionText(action)}
          </Tag>
          <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
            {action}
          </div>
        </div>
      )
    },
    { 
      title: '目标类型', 
      dataIndex: 'target_type', 
      key: 'target_type', 
      width: 120,
      render: (type: string) => (
        <span>{formatTargetType(type)}</span>
      )
    },
    { 
      title: '目标ID', 
      dataIndex: 'target_id', 
      key: 'target_id', 
      width: 120,
      render: (id: number, record: AuditLogDisplay) => formatTargetIdWithType(record.target_type || '', id)
    },
    { 
      title: '关联上下文', 
      key: 'context', 
      width: 220,
      render: (_: any, record: AuditLogDisplay) => (
        <span style={{ fontSize: 12, color: '#666' }}>{formatAuditContext(record)}</span>
      )
    },
    { 
      title: '时间', 
      dataIndex: 'created_at', 
      key: 'created_at', 
      width: 180,
      render: (date: string) => date ? formatDateTime(date) : '-'
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: AuditLogDisplay) => (
        <Button type="link" size="small" onClick={() => showDetail(record)}>
          查看详情
        </Button>
      )
    }
  ];

  return (
    <div>
      <PageHeader 
        title="审计日志" 
        subtitle="查看系统操作日志 - 全链路追踪" 
      />
      <div style={{ marginBottom: 16 }}>
        <Space>
          <Button onClick={fetchAuditLogs} loading={loading}>刷新</Button>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={auditLogs}
        rowKey="id"
        loading={loading}
        pagination={{
          pageSize: 15,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total) => `共 ${total} 条记录`
        }}
        scroll={{ x: 1300 }}
      />

      <Modal
        title="审计日志详情"
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={[
          <Button key="close" type="primary" onClick={() => setDetailVisible(false)}>
            关闭
          </Button>
        ]}
        width={700}
      >
        {selectedLog && (
          <div>
            <div style={{ marginBottom: 16 }}>
              <h4>基本信息</h4>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div><strong>日志ID：</strong>#{selectedLog.id}</div>
                <div><strong>用户：</strong>{formatUserRole(selectedLog.user_id)}</div>
                <div><strong>操作：</strong>
                  <Tag color={getAuditActionColor(selectedLog.action)}>
                    {getAuditActionText(selectedLog.action)}
                  </Tag>
                </div>
                <div><strong>操作说明：</strong>{getAuditActionText(selectedLog.action)}</div>
                <div><strong>目标类型：</strong>{formatTargetType(selectedLog.target_type || '')}</div>
                <div><strong>目标ID：</strong>{selectedLog.target_id ? `#${selectedLog.target_id}` : '-'}</div>
                <div><strong>任务ID：</strong>{selectedLog.task_id ? `#${selectedLog.task_id}` : '-'}</div>
                <div><strong>数据项ID：</strong>{selectedLog.item_id ? `#${selectedLog.item_id}` : '-'}</div>
                <div><strong>标注ID：</strong>{selectedLog.submission_id ? `#${selectedLog.submission_id}` : '-'}</div>
                <div><strong>标注ID：</strong>{selectedLog.annotation_id ? `#${selectedLog.annotation_id}` : '-'}</div>
                {selectedLog.work_key && <div style={{ gridColumn: '1 / -1' }}><strong>Work Key：</strong><span style={{ fontSize: 12, wordBreak: 'break-all' }}>{selectedLog.work_key}</span></div>}
                {selectedLog.message && <div style={{ gridColumn: '1 / -1' }}><strong>消息：</strong>{selectedLog.message}</div>}
                <div style={{ gridColumn: '1 / -1' }}><strong>时间：</strong>{selectedLog.created_at ? formatDateTime(selectedLog.created_at) : '-'}</div>
              </div>
            </div>

            {(selectedLog.after_data || selectedLog.extra_info) && (
              <Collapse defaultActiveKey={['afterData', 'extraInfo']} items={[
                ...(selectedLog.after_data ? [{
                  key: 'afterData',
                  label: '变更后数据 (after_data)',
                  children: (
                    <pre style={{
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: 300,
                      overflow: 'auto',
                      backgroundColor: '#f5f5f5',
                      padding: 12,
                      borderRadius: 4
                    }}>
                      {JSON.stringify(selectedLog.after_data, null, 2)}
                    </pre>
                  ),
                }] : []),
                ...(selectedLog.extra_info ? [{
                  key: 'extraInfo',
                  label: '附加信息 (extra_info)',
                  children: (
                    <pre style={{
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: 300,
                      overflow: 'auto',
                      backgroundColor: '#f5f5f5',
                      padding: 12,
                      borderRadius: 4
                    }}>
                      {JSON.stringify(selectedLog.extra_info, null, 2)}
                    </pre>
                  ),
                }] : []),
              ]} />
            )}

            {!selectedLog.after_data && !selectedLog.extra_info && (
              <div style={{ color: '#999', textAlign: 'center', padding: 20 }}>
                暂无详细信息
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default AuditLogPage;