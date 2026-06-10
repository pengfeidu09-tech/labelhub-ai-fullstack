import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Row, Col, Statistic, Button, Select, Space, Table, Tag, message, Spin, Empty, Descriptions, Divider, Alert, Tooltip, Modal, Progress, Collapse } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, RobotOutlined, EyeOutlined, ExportOutlined, FileTextOutlined, CopyOutlined, DownloadOutlined, InfoCircleOutlined, WarningOutlined, SafetyCertificateOutlined, BugOutlined, SettingOutlined, SwapOutlined, CameraOutlined } from '@ant-design/icons';
import { formatDateTime, formatDateTimeShort, formatDateMinute } from '../../utils/time';
import dayjs from 'dayjs';
import { formatTaskName, formatPercent } from '../../utils/format';

const { Option } = Select;

interface ResultSummary {
  task_id: number;
  task_name: string;
  total_items: number;
  template_name: string;
  task_status: string;
  created_at: string | null;
  claimed_count: number;
  submitted_count: number;
  ai_reviewed_count: number;
  human_reviewing_count: number;
  reviewing_count: number;
  approved_count: number;
  rejected_count: number;
  invalid_pending_count: number;
  invalid_approved_count: number;
  export_ready_count: number;
  approved_rate: number;
  reject_rate: number;
  ai_decision_stats: { pass: number; reject: number; human_review: number };
  overall_score_avg: number;
  human_review_stats: { approve: number; reject: number; revise: number };
  top_issues: { message: string; count: number }[];
  updated_at: string | null;
  ai_risk_distribution?: { low: number; medium: number; high: number };
  ai_human_agreement_rate?: number | null;
}

interface ExportJob {
  id: number;
  task_id: number;
  format: string;
  status: string;
  row_count: number | null;
  file_path: string | null;
  error_message: string | null;
  created_at: string | null;
}

interface QualityInsights {
  task_id: number;
  ai_avg_score: number | null;
  ai_risk_distribution: { low: number; medium: number; high: number };
  human_pass_rate: number | null;
  ai_human_agreement_rate: number | null;
  rejected_count: number;
  exportable_count: number;
  low_score_count: number;
  priority_review_count: number;
  total_with_ai_review: number;
  total_with_human_review: number;
  stat_notes: Record<string, string>;
}

interface RubricAnalysisItem {
  rubric_id: string;
  rubric_name: string;
  dimension: string;
  type: string;
  priority: string;
  human_met: number;
  human_not_met: number;
  human_uncertain: number;
  ai_suggested: number;
  ai_human_agree: number;
  ai_human_total: number;
  agreement_rate: number | null;
  not_met_rate: number;
  uncertain_rate: number;
  is_high_dispute: boolean;
  dispute_reasons: string[];
  tags: string[];
  rejected_appearances: number;
}

interface PriorityReviewItem {
  submission_id: number;
  task_id: number;
  dataset_item_id: number;
  labeler_id: number;
  ai_score: number | null;
  ai_risk_level: string | null;
  human_status: string;
  triggers: string[];
  updated_at: string | null;
  created_at: string | null;
}

interface QualityReport {
  task_id: number;
  generated_at: string;
  generated_by: string;
  report_text: string;
  sample_note: string;
  structured?: {
    quality_policy_and_delivery?: {
      policy_version: string;
      ai_pass_threshold: number;
      high_risk_rules: string;
      must_review_rules: string[];
      exportable_count: number;
      recommend_immediate_export: boolean;
      pre_export_suggestions: string[];
    };
  };
}

interface QualityPolicy {
  task_id: number;
  version: string;
  scope: string;
  note: string;
  ai_pass_threshold: number;
  high_risk_threshold: { score_below: number; risk_level: string };
  auto_suggestion_rules: { name: string; condition: string; action: string; enabled: boolean }[];
  must_review_rules: { name: string; enabled: boolean }[];
  export_admission_rules: { name: string; enabled: boolean }[];
}

interface SmartReviewStrategy {
  task_id: number;
  policy_version: string;
  summary: {
    auto_pass_candidate: number;
    manual_review_required: number;
    rework_suggested: number;
    must_review: number;
    high_risk: number;
    ai_human_disagree: number;
  };
  items: SmartReviewItem[];
  total: number;
  note: string;
}

interface SmartReviewItem {
  submission_id: number;
  task_id: number;
  dataset_item_id: number;
  ai_score: number | null;
  risk_level: string | null;
  human_status: string;
  review_strategy: string;
  trigger_reasons: string[];
  suggested_action: string;
}

interface SnapshotSummary {
  snapshot_id: string;
  task_id: number;
  total_rows: number;
  approved_rows: number;
  rows_with_ai_review: number;
  rows_without_ai_review: number;
  rows_with_human_review: number;
  format: string;
  quality_policy_version: string;
  data_filter: string;
  includes_ai_review: boolean;
  includes_human_review: boolean;
  generated_at: string;
  job_id: number;
  status: string;
  file_path: string | null;
  created_at: string | null;
}

const apiBase = '/api';

const dimLabel: Record<string, string> = {
  relevance: '相关性',
  accuracy: '准确性',
  completeness: '完整性',
  safety: '安全性',
};

const strategyLabel: Record<string, { text: string; color: string }> = {
  auto_pass_candidate: { text: '自动放行候选', color: 'green' },
  manual_review_required: { text: '需要人工复核', color: 'orange' },
  rework_suggested: { text: '建议返修', color: 'red' },
  reject_suggested: { text: '建议拒绝', color: 'volcano' },
  export_ready: { text: '可导出', color: 'cyan' },
  blocked: { text: '暂不可导出', color: 'default' },
};

const TaskResultsPage: React.FC = () => {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [summary, setSummary] = useState<ResultSummary | null>(null);
  const [exportJobs, setExportJobs] = useState<ExportJob[]>([]);
  const [insights, setInsights] = useState<QualityInsights | null>(null);
  const [rubricData, setRubricData] = useState<RubricAnalysisItem[]>([]);
  const [priorityItems, setPriorityItems] = useState<PriorityReviewItem[]>([]);
  const [qualityReport, setQualityReport] = useState<QualityReport | null>(null);
  const [qualityPolicy, setQualityPolicy] = useState<QualityPolicy | null>(null);
  const [reviewStrategy, setReviewStrategy] = useState<SmartReviewStrategy | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState<string>('json');
  const [reportModalOpen, setReportModalOpen] = useState(false);
  const [reportGenerating, setReportGenerating] = useState(false);
  const [snapshotModalOpen, setSnapshotModalOpen] = useState(false);
  const [snapshotData, setSnapshotData] = useState<SnapshotSummary | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);

  const taskIdNum = parseInt(taskId || '0');

  const fetchSummary = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/tasks/${taskIdNum}/result-summary`);
      if (!res.ok) throw new Error('Failed to fetch');
      const data = await res.json();
      setSummary(data);
    } catch (error) {
      message.error('获取任务结果统计失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const fetchExportJobs = async () => {
    try {
      const res = await fetch(`${apiBase}/exports?task_id=${taskIdNum}`);
      if (!res.ok) throw new Error('Failed to fetch');
      const data = await res.json();
      const items = data.items || data.data || (Array.isArray(data) ? data : []);
      setExportJobs(items);
    } catch (error) {
      console.error('Failed to fetch export jobs', error);
    }
  };

  const fetchInsights = async () => {
    try {
      const res = await fetch(`${apiBase}/quality/tasks/${taskIdNum}/insights`);
      if (!res.ok) return;
      const data = await res.json();
      setInsights(data);
    } catch (error) {
      console.error('Failed to fetch quality insights', error);
    }
  };

  const fetchRubricAnalysis = async () => {
    try {
      const res = await fetch(`${apiBase}/quality/tasks/${taskIdNum}/rubric-analysis`);
      if (!res.ok) return;
      const data = await res.json();
      setRubricData(data.rubrics || []);
    } catch (error) {
      console.error('Failed to fetch rubric analysis', error);
    }
  };

  const fetchPriorityReviews = async () => {
    try {
      const res = await fetch(`${apiBase}/quality/tasks/${taskIdNum}/priority-reviews`);
      if (!res.ok) return;
      const data = await res.json();
      setPriorityItems(data.items || []);
    } catch (error) {
      console.error('Failed to fetch priority reviews', error);
    }
  };

  const fetchQualityPolicy = async () => {
    try {
      const res = await fetch(`${apiBase}/quality/tasks/${taskIdNum}/policy`);
      if (!res.ok) return;
      const data = await res.json();
      setQualityPolicy(data);
    } catch (error) {
      console.error('Failed to fetch quality policy', error);
    }
  };

  const fetchReviewStrategy = async () => {
    try {
      const res = await fetch(`${apiBase}/quality/tasks/${taskIdNum}/review-strategy`);
      if (!res.ok) return;
      const data = await res.json();
      setReviewStrategy(data);
    } catch (error) {
      console.error('Failed to fetch review strategy', error);
    }
  };

  const handleGenerateReport = async () => {
    setReportGenerating(true);
    try {
      const res = await fetch(`${apiBase}/quality/tasks/${taskIdNum}/report`, { method: 'POST' });
      if (!res.ok) throw new Error('Failed to generate report');
      const data = await res.json();
      setQualityReport(data);
      setReportModalOpen(true);
      message.success('AI 质量报告已生成');
    } catch (error) {
      message.error('生成质量报告失败');
      console.error(error);
    } finally {
      setReportGenerating(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await fetch(`${apiBase}/exports/task/${taskIdNum}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format: exportFormat })
      });
      if (!res.ok) throw new Error('Export failed');
      const data = await res.json();
      const rowCount = data.row_count ?? data.rows_count ?? '-';
      message.success(`导出成功，本次导出 ${rowCount} 条数据`);
      fetchExportJobs();
    } catch (error) {
      message.error('导出失败');
      console.error(error);
    } finally {
      setExporting(false);
    }
  };

  const handleViewSnapshot = async (jobId: number) => {
    setSnapshotLoading(true);
    setSnapshotModalOpen(true);
    try {
      const res = await fetch(`${apiBase}/exports/${jobId}/snapshot-summary`);
      if (!res.ok) throw new Error('Failed to fetch');
      const data = await res.json();
      setSnapshotData(data);
    } catch (error) {
      message.error('获取快照摘要失败');
      console.error(error);
    } finally {
      setSnapshotLoading(false);
    }
  };

  useEffect(() => {
    if (taskIdNum) {
      Promise.all([
        fetchSummary(),
        fetchExportJobs(),
        fetchInsights(),
        fetchRubricAnalysis(),
        fetchPriorityReviews(),
        fetchQualityPolicy(),
        fetchReviewStrategy()
      ]);
    }
  }, [taskIdNum]);

  const getStatusTag = (status: string) => {
    const map: Record<string, { color: string; text: string }> = {
      'draft': { color: 'default', text: '草稿' },
      'published': { color: 'blue', text: '已发布' },
      'paused': { color: 'orange', text: '已暂停' },
      'completed': { color: 'green', text: '已完成' }
    };
    const info = map[status] || { color: 'default', text: status };
    return <Tag color={info.color}>{info.text}</Tag>;
  };

  const getExportStatusTag = (status: string) => {
    const map: Record<string, { color: string; text: string }> = {
      'pending': { color: 'default', text: '待处理' },
      'running': { color: 'blue', text: '处理中' },
      'success': { color: 'green', text: '成功' },
      'failed': { color: 'red', text: '失败' }
    };
    const info = map[status] || { color: 'default', text: status };
    return <Tag color={info.color}>{info.text}</Tag>;
  };

  const getRubricTag = (tag: string) => {
    const map: Record<string, string> = {
      '高争议': 'red',
      '稳定': 'green',
      '高频问题': 'orange',
      '低命中': 'default',
    };
    return <Tag color={map[tag] || 'default'} style={{ fontSize: 11 }}>{tag}</Tag>;
  };

  const getTriggerTag = (trigger: string) => {
    if (trigger.includes('高风险')) return <Tag color="red" style={{ fontSize: 11 }}>{trigger}</Tag>;
    if (trigger.includes('低于阈值')) return <Tag color="orange" style={{ fontSize: 11 }}>{trigger}</Tag>;
    if (trigger.includes('不一致')) return <Tag color="volcano" style={{ fontSize: 11 }}>{trigger}</Tag>;
    if (trigger.includes('打回')) return <Tag color="magenta" style={{ fontSize: 11 }}>{trigger}</Tag>;
    if (trigger.includes('缺失')) return <Tag color="gold" style={{ fontSize: 11 }}>{trigger}</Tag>;
    return <Tag style={{ fontSize: 11 }}>{trigger}</Tag>;
  };

  const getSnapshotId = (record: ExportJob): string => {
    try {
      if (record.error_message) {
        const parsed = JSON.parse(record.error_message);
        if (parsed.snapshot_id) return parsed.snapshot_id;
      }
    } catch (e) {}
    const ts = record.created_at ? dayjs(record.created_at).format('YYYYMMDD_HHmmss') : 'unknown';
    return `snapshot_task_${record.task_id || 0}_${ts}`;
  };

  const exportColumns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 50 },
    { title: 'Snapshot ID', key: 'snapshot_id', width: 200, render: (_: any, record: ExportJob) => (
      <Tooltip title={getSnapshotId(record)}>
        <span style={{ fontSize: 12, fontFamily: 'monospace' }}>
          <CameraOutlined style={{ marginRight: 4, color: '#13c2c2' }} />
          {getSnapshotId(record).length > 30 ? getSnapshotId(record).substring(0, 27) + '...' : getSnapshotId(record)}
        </span>
      </Tooltip>
    )},
    { title: '格式', dataIndex: 'format', key: 'format', width: 60, render: (v: string) => (v || '-').toUpperCase() },
    { title: '状态', dataIndex: 'status', key: 'status', width: 70, render: getExportStatusTag },
    { title: '行数', dataIndex: 'row_count', key: 'row_count', width: 50, render: (v: number) => v ?? 0 },
    { title: '策略版本', key: 'policy_version', width: 100, render: (_: any, record: ExportJob) => {
      try {
        if (record.error_message) {
          const parsed = JSON.parse(record.error_message);
          if (parsed.quality_policy_version) return <Tag color="blue" style={{ fontSize: 11 }}>{parsed.quality_policy_version}</Tag>;
        }
      } catch (e) {}
      return <Tag style={{ fontSize: 11 }}>quality_policy_v1</Tag>;
    }},
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 140, render: (v: string) => v ? formatDateTimeShort(v) : '-' },
    { title: '操作', key: 'action', width: 200, render: (_: any, record: ExportJob) => (
      <Space size="small">
        {record.status === 'success' && record.file_path && (
          <Button type="link" size="small" icon={<DownloadOutlined />}
            onClick={() => { window.open(`${apiBase}/exports/${record.id}/download`, '_blank'); }}>
            下载
          </Button>
        )}
        {record.file_path && (
          <Tooltip title={record.file_path}>
            <Button type="link" size="small" icon={<CopyOutlined />}
              onClick={() => { navigator.clipboard.writeText(record.file_path || '').then(() => message.success('已复制路径')).catch(() => message.error('复制失败')); }}>
            </Button>
          </Tooltip>
        )}
        {record.status === 'success' && (
          <Button type="link" size="small" icon={<CameraOutlined />}
            onClick={() => handleViewSnapshot(record.id)}>
            快照
          </Button>
        )}
        {record.status === 'failed' && record.error_message && (
          <Tooltip title={record.error_message}><Tag color="red" style={{ fontSize: 11 }}>错误</Tag></Tooltip>
        )}
      </Space>
    )}
  ];

  const rubricColumns = [
    { title: 'Rubric', dataIndex: 'rubric_name', key: 'rubric_name', width: 100, render: (v: string) => <span style={{ fontWeight: 500 }}>{v}</span> },
    { title: '维度', dataIndex: 'dimension', key: 'dimension', width: 80, render: (v: string) => dimLabel[v] || v },
    { title: '类型', dataIndex: 'type', key: 'type', width: 80, render: (v: string) => v === 'objective' ? '客观' : '主观' },
    { title: '优先级', dataIndex: 'priority', key: 'priority', width: 80, render: (v: string) => v === 'must_have' ? <Tag color="red">必须</Tag> : <Tag>可选</Tag> },
    { title: '人工满足', dataIndex: 'human_met', key: 'human_met', width: 70, render: (v: number) => <span style={{ color: '#52c41a' }}>{v}</span> },
    { title: '人工不满足', dataIndex: 'human_not_met', key: 'human_not_met', width: 80, render: (v: number) => <span style={{ color: v > 0 ? '#ff4d4f' : '#999' }}>{v}</span> },
    { title: '不确定', dataIndex: 'human_uncertain', key: 'human_uncertain', width: 70, render: (v: number) => <span style={{ color: '#fa8c16' }}>{v}</span> },
    { title: 'AI建议', dataIndex: 'ai_suggested', key: 'ai_suggested', width: 70 },
    { title: '一致率', dataIndex: 'agreement_rate', key: 'agreement_rate', width: 80, render: (v: number | null) => {
      if (v == null) return '-';
      const pct = Math.round(v * 100);
      return <Progress percent={pct} size="small" status={pct < 60 ? 'exception' : 'active'} format={() => `${pct}%`} />;
    }},
    { title: '标签', dataIndex: 'tags', key: 'tags', width: 160, render: (tags: string[]) => tags.length > 0 ? <Space size={4}>{tags.map(t => getRubricTag(t))}</Space> : <span style={{ color: '#999' }}>-</span> },
  ];

  const priorityColumns = [
    { title: 'Submission', dataIndex: 'submission_id', key: 'submission_id', width: 90 },
    { title: 'Item', dataIndex: 'dataset_item_id', key: 'dataset_item_id', width: 70 },
    { title: '标注员', dataIndex: 'labeler_id', key: 'labeler_id', width: 70, render: (v: number) => `#${v}` },
    { title: 'AI 分数', dataIndex: 'ai_score', key: 'ai_score', width: 80, render: (v: number | null) => {
      if (v == null) return '-';
      return <span style={{ color: v < 70 ? '#ff4d4f' : v < 80 ? '#fa8c16' : '#52c41a', fontWeight: 600 }}>{v}</span>;
    }},
    { title: '风险', dataIndex: 'ai_risk_level', key: 'ai_risk_level', width: 70, render: (v: string | null) => {
      if (!v) return '-';
      const map: Record<string, { color: string; text: string }> = { high: { color: 'red', text: '高' }, medium: { color: 'orange', text: '中' }, low: { color: 'green', text: '低' } };
      const info = map[v] || { color: 'default', text: v };
      return <Tag color={info.color}>{info.text}</Tag>;
    }},
    { title: '人工状态', dataIndex: 'human_status', key: 'human_status', width: 100, render: (v: string) => {
      const map: Record<string, { color: string; text: string }> = {
        approved: { color: 'green', text: '已通过' },
        rejected_to_modify: { color: 'red', text: '已打回' },
        submitted: { color: 'blue', text: '待审核' },
        invalid_submitted: { color: 'default', text: '无效待审' },
      };
      const info = map[v] || { color: 'default', text: v };
      return <Tag color={info.color}>{info.text}</Tag>;
    }},
    { title: '触发原因', dataIndex: 'triggers', key: 'triggers', width: 250, render: (triggers: string[]) => <Space size={4} wrap>{triggers.map(t => getTriggerTag(t))}</Space> },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 140, render: (v: string | null) => v ? formatDateMinute(v) : '-' },
    { title: '操作', key: 'action', width: 100, render: (_: any, record: PriorityReviewItem) => (
      <Button type="link" size="small" icon={<EyeOutlined />}
        onClick={() => navigate(`/reviewer/reviews/${record.submission_id}`)}>
        查看详情
      </Button>
    )},
  ];

  const smartReviewColumns = [
    { title: 'Submission', dataIndex: 'submission_id', key: 'submission_id', width: 90 },
    { title: 'Item', dataIndex: 'dataset_item_id', key: 'dataset_item_id', width: 70 },
    { title: 'AI 分数', dataIndex: 'ai_score', key: 'ai_score', width: 80, render: (v: number | null) => {
      if (v == null) return '-';
      return <span style={{ color: v < 70 ? '#ff4d4f' : v < 80 ? '#fa8c16' : '#52c41a', fontWeight: 600 }}>{v}</span>;
    }},
    { title: '风险', dataIndex: 'risk_level', key: 'risk_level', width: 70, render: (v: string | null) => {
      if (!v) return '-';
      const map: Record<string, { color: string; text: string }> = { high: { color: 'red', text: '高' }, medium: { color: 'orange', text: '中' }, low: { color: 'green', text: '低' } };
      const info = map[v] || { color: 'default', text: v };
      return <Tag color={info.color}>{info.text}</Tag>;
    }},
    { title: '人工状态', dataIndex: 'human_status', key: 'human_status', width: 100, render: (v: string) => {
      const map: Record<string, { color: string; text: string }> = {
        approved: { color: 'green', text: '已通过' },
        export_ready: { color: 'cyan', text: '可导出' },
        rejected_to_modify: { color: 'red', text: '已打回' },
        submitted: { color: 'blue', text: '待审核' },
      };
      const info = map[v] || { color: 'default', text: v };
      return <Tag color={info.color}>{info.text}</Tag>;
    }},
    { title: '复核策略', dataIndex: 'review_strategy', key: 'review_strategy', width: 120, render: (v: string) => {
      const info = strategyLabel[v] || { text: v, color: 'default' };
      return <Tag color={info.color}>{info.text}</Tag>;
    }},
    { title: '触发原因', dataIndex: 'trigger_reasons', key: 'trigger_reasons', width: 220, render: (reasons: string[]) => reasons.length > 0 ? <Space size={4} wrap>{reasons.map(r => getTriggerTag(r))}</Space> : <span style={{ color: '#999' }}>-</span> },
    { title: '建议动作', dataIndex: 'suggested_action', key: 'suggested_action', width: 100, render: (v: string) => {
      const map: Record<string, { color: string; text: string }> = {
        auto_pass: { color: 'green', text: '自动放行' },
        manual_review: { color: 'orange', text: '人工复核' },
        rework: { color: 'red', text: '返修' },
        export: { color: 'cyan', text: '可导出' },
        review_before_export: { color: 'gold', text: '复核后导出' },
      };
      const info = map[v] || { color: 'default', text: v };
      return <Tag color={info.color}>{info.text}</Tag>;
    }},
    { title: '操作', key: 'action', width: 100, render: (_: any, record: SmartReviewItem) => (
      <Button type="link" size="small" icon={<EyeOutlined />}
        onClick={() => navigate(`/reviewer/reviews/${record.submission_id}`)}>
        查看详情
      </Button>
    )},
  ];

  const reportSummary = summary
    ? `本任务共包含 ${summary.total_items} 条数据，已提交 ${summary.submitted_count} 条，AI 已完成预审 ${summary.ai_reviewed_count} 条，人工审核通过 ${summary.approved_count} 条，当前可导出 ${summary.export_ready_count} 条。其中无效待审 ${summary.invalid_pending_count ?? 0} 条，已确认无效 ${summary.invalid_approved_count ?? 0} 条。AI 预审主要用于提前识别缺失字段、理由过短、质量风险等问题，人工审核负责最终质量把关。`
    : '';

  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', padding: 100 }}><Spin size="large" /></div>;
  }

  if (!summary) {
    return <Empty description="暂无任务结果数据" />;
  }

  return (
    <div>
      <div style={{ marginBottom: 12, fontSize: 13, color: '#666' }}>
        <span style={{ cursor: 'pointer', color: '#1890ff' }} onClick={() => navigate('/owner/tasks')}>项目/任务总览</span>
        <span style={{ margin: '0 8px' }}>&gt;</span>
        <span style={{ cursor: 'pointer', color: '#1890ff' }} onClick={() => navigate(`/owner/tasks/${taskIdNum}`)}>任务详情 #{taskIdNum}</span>
        <span style={{ margin: '0 8px' }}>&gt;</span>
        <span>结果中心</span>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>任务结果中心</h1>
        <Space>
          <Button onClick={() => navigate(`/owner/tasks/${taskIdNum}`)}>返回任务详情</Button>
          <Button onClick={() => navigate('/owner/tasks')}>返回任务列表</Button>
        </Space>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={3} size="small">
          <Descriptions.Item label="任务ID">#{summary.task_id}</Descriptions.Item>
          <Descriptions.Item label="任务名称">{formatTaskName({ name: summary.task_name, id: summary.task_id })}</Descriptions.Item>
          <Descriptions.Item label="状态">{getStatusTag(summary.task_status)}</Descriptions.Item>
          <Descriptions.Item label="模板">{summary.template_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="总数据量">{summary.total_items}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{summary.created_at ? formatDateTime(summary.created_at) : '-'}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={2}><Card size="small"><Statistic title="总数据量" value={summary.total_items ?? 0} /></Card></Col>
        <Col span={2}><Card size="small"><Statistic title="已领取" value={summary.claimed_count ?? 0} valueStyle={{ color: '#8c8c8c' }} /></Card></Col>
        <Col span={2}><Card size="small"><Statistic title="已提交" value={summary.submitted_count ?? 0} valueStyle={{ color: '#1890ff' }} /></Card></Col>
        <Col span={2}><Card size="small"><Statistic title="AI 已预审" value={summary.ai_reviewed_count ?? 0} prefix={<RobotOutlined />} valueStyle={{ color: '#722ed1' }} /></Card></Col>
        <Col span={2}><Card size="small"><Statistic title="待审核" value={summary.reviewing_count ?? summary.human_reviewing_count ?? 0} prefix={<EyeOutlined />} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
        <Col span={2}><Card size="small"><Statistic title="已通过" value={summary.approved_count ?? 0} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={2}><Card size="small"><Statistic title="已打回" value={summary.rejected_count ?? 0} prefix={<CloseCircleOutlined />} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
        <Col span={2}><Card size="small"><Statistic title="无效待审" value={summary.invalid_pending_count ?? 0} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
        <Col span={2}><Card size="small"><Statistic title="无效已确认" value={summary.invalid_approved_count ?? 0} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
        <Col span={2}><Card size="small"><Statistic title="可导出" value={summary.export_ready_count ?? 0} prefix={<ExportOutlined />} valueStyle={{ color: '#13c2c2' }} /></Card></Col>
        <Col span={2}><Card size="small"><Statistic title="通过率" value={formatPercent(summary.approved_rate ?? 0)} valueStyle={{ color: (summary.approved_rate ?? 0) >= 0.5 ? '#52c41a' : '#ff4d4f' }} /></Card></Col>
      </Row>

      <Card title={<span><SettingOutlined /> 质量策略中心</span>} style={{ marginBottom: 16 }} size="small"
        extra={<Tag color="blue">{qualityPolicy?.version || 'quality_policy_v1'}</Tag>}
      >
        {qualityPolicy ? (
          <>
            <Alert type="info" style={{ marginBottom: 12 }} message={qualityPolicy.note || '当前为任务级质量策略，使用默认配置'} showIcon icon={<InfoCircleOutlined />} />
            <Collapse defaultActiveKey={[]} ghost items={[
              {
                key: 'threshold',
                label: <span style={{ fontWeight: 500 }}>AI 通过阈值 & 自动建议规则</span>,
                children: (
                  <>
                    <Row gutter={16}>
                      <Col span={8}>
                        <Statistic title="AI 通过阈值" value={qualityPolicy.ai_pass_threshold} suffix=" 分" valueStyle={{ color: '#52c41a' }} />
                      </Col>
                      <Col span={8}>
                        <Statistic title="高风险分数阈值" value={qualityPolicy.high_risk_threshold.score_below} suffix=" 分" valueStyle={{ color: '#ff4d4f' }} />
                      </Col>
                      <Col span={8}>
                        <Statistic title="高风险等级" value={qualityPolicy.high_risk_threshold.risk_level} valueStyle={{ color: '#ff4d4f' }} />
                      </Col>
                    </Row>
                    <Divider style={{ margin: '12px 0' }} />
                    <Table size="small" pagination={false} dataSource={qualityPolicy.auto_suggestion_rules} rowKey="name"
                      columns={[
                        { title: '规则', dataIndex: 'name', width: 120, render: (v: string) => <span style={{ fontWeight: 500 }}>{v}</span> },
                        { title: '条件', dataIndex: 'condition', width: 250 },
                        { title: '动作', dataIndex: 'action', width: 120, render: (v: string) => {
                          const map: Record<string, { color: string; text: string }> = { submit: { color: 'green', text: '提交' }, manual_review: { color: 'orange', text: '复核' }, rework: { color: 'red', text: '打回' } };
                          const info = map[v] || { color: 'default', text: v };
                          return <Tag color={info.color}>{info.text}</Tag>;
                        }},
                        { title: '启用', dataIndex: 'enabled', width: 80, render: (v: boolean) => v ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag> },
                      ]}
                    />
                  </>
                ),
              },
              {
                key: 'must_review',
                label: <span style={{ fontWeight: 500 }}>必审样本规则</span>,
                children: (
                  <Table size="small" pagination={false} dataSource={qualityPolicy.must_review_rules} rowKey="name"
                    columns={[
                      { title: '规则', dataIndex: 'name', width: 250, render: (v: string) => <span>{v}</span> },
                      { title: '启用', dataIndex: 'enabled', width: 80, render: (v: boolean) => v ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag> },
                    ]}
                  />
                ),
              },
              {
                key: 'export_rules',
                label: <span style={{ fontWeight: 500 }}>导出准入规则</span>,
                children: (
                  <Table size="small" pagination={false} dataSource={qualityPolicy.export_admission_rules} rowKey="name"
                    columns={[
                      { title: '规则', dataIndex: 'name', width: 350, render: (v: string) => <span>{v}</span> },
                      { title: '启用', dataIndex: 'enabled', width: 80, render: (v: boolean) => v ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag> },
                    ]}
                  />
                ),
              },
            ]} />
          </>
        ) : (
          <Empty description="暂无质量策略数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      <Card title={<span><SwapOutlined /> 智能复核策略</span>} style={{ marginBottom: 16 }} size="small"
        extra={reviewStrategy ? <Tag color="blue">{reviewStrategy.policy_version}</Tag> : null}
      >
        {reviewStrategy ? (
          <>
            <Alert type="info" style={{ marginBottom: 12 }} message={reviewStrategy.note} showIcon icon={<InfoCircleOutlined />} />
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col span={4}>
                <Statistic title="自动放行候选" value={reviewStrategy.summary.auto_pass_candidate} valueStyle={{ color: '#52c41a' }} />
              </Col>
              <Col span={4}>
                <Statistic title="人工复核建议" value={reviewStrategy.summary.manual_review_required} valueStyle={{ color: '#fa8c16' }} />
              </Col>
              <Col span={4}>
                <Statistic title="建议打回" value={reviewStrategy.summary.rework_suggested} valueStyle={{ color: '#ff4d4f' }} />
              </Col>
              <Col span={4}>
                <Statistic title="必审样本" value={reviewStrategy.summary.must_review} valueStyle={{ color: '#722ed1' }} />
              </Col>
              <Col span={4}>
                <Statistic title="高风险样本" value={reviewStrategy.summary.high_risk} valueStyle={{ color: '#ff4d4f' }} />
              </Col>
              <Col span={4}>
                <Statistic title="AI/人工不一致" value={reviewStrategy.summary.ai_human_disagree} valueStyle={{ color: '#eb2f96' }} />
              </Col>
            </Row>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>智能复核队列</div>
            {reviewStrategy.items.length > 0 ? (
              <Table
                size="small"
                pagination={{ pageSize: 10 }}
                dataSource={reviewStrategy.items}
                rowKey="submission_id"
                columns={smartReviewColumns}
                scroll={{ x: 1100 }}
              />
            ) : (
              <Empty description="暂无复核队列数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </>
        ) : (
          <Empty description="暂无智能复核策略数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card title={<span><RobotOutlined /> AI 预审概览</span>} size="small">
            <Row gutter={16}>
              <Col span={8}><Statistic title="AI 通过" value={summary.ai_decision_stats.pass} valueStyle={{ color: '#52c41a' }} /></Col>
              <Col span={8}><Statistic title="AI 建议打回" value={summary.ai_decision_stats.reject} valueStyle={{ color: '#ff4d4f' }} /></Col>
              <Col span={8}><Statistic title="AI 建议复核" value={summary.ai_decision_stats.human_review} valueStyle={{ color: '#fa8c16' }} /></Col>
            </Row>
            <Divider style={{ margin: '12px 0' }} />
            <Row gutter={16}>
              <Col span={12}><Statistic title="AI 平均分" value={summary.overall_score_avg} suffix="/ 100" /></Col>
              <Col span={12}>
                <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>AI 风险分布</div>
                <Space size={4}>
                  <Tag color="green">低 {summary.ai_risk_distribution?.low ?? 0}</Tag>
                  <Tag color="orange">中 {summary.ai_risk_distribution?.medium ?? 0}</Tag>
                  <Tag color="red">高 {summary.ai_risk_distribution?.high ?? 0}</Tag>
                </Space>
              </Col>
            </Row>
          </Card>
        </Col>
        <Col span={8}>
          <Card title={<span><EyeOutlined /> 人工审核概览</span>} size="small">
            <Row gutter={16}>
              <Col span={8}><Statistic title="人工通过" value={summary.human_review_stats.approve} valueStyle={{ color: '#52c41a' }} /></Col>
              <Col span={8}><Statistic title="人工打回" value={summary.human_review_stats.reject} valueStyle={{ color: '#ff4d4f' }} /></Col>
              <Col span={8}><Statistic title="人工修订" value={summary.human_review_stats.revise} valueStyle={{ color: '#1890ff' }} /></Col>
            </Row>
            <Divider style={{ margin: '12px 0' }} />
            <Row gutter={16}>
              <Col span={12}><Statistic title="打回率" value={formatPercent(summary.reject_rate)} /></Col>
              <Col span={12}><Statistic title="AI/人工一致率" value={formatPercent(summary.ai_human_agreement_rate)} /></Col>
            </Row>
          </Card>
        </Col>
        <Col span={8}>
          <Card title="质量指标" size="small">
            <Row gutter={16}>
              <Col span={12}><Statistic title="通过率" value={formatPercent(summary.approved_rate ?? 0)} valueStyle={{ color: (summary.approved_rate ?? 0) >= 0.5 ? '#52c41a' : '#ff4d4f' }} /></Col>
              <Col span={12}><Statistic title="可导出" value={summary.export_ready_count ?? 0} prefix={<ExportOutlined />} valueStyle={{ color: '#13c2c2' }} /></Col>
            </Row>
            <Divider style={{ margin: '12px 0' }} />
            <Row gutter={16}>
              <Col span={12}><Statistic title="已提交" value={summary.submitted_count ?? 0} valueStyle={{ color: '#1890ff' }} /></Col>
              <Col span={12}><Statistic title="已打回" value={summary.rejected_count ?? 0} valueStyle={{ color: '#ff4d4f' }} /></Col>
            </Row>
          </Card>
        </Col>
      </Row>

      <Card title={<span><SafetyCertificateOutlined /> 质量洞察</span>} style={{ marginBottom: 16 }} size="small"
        extra={<Tooltip title="统计口径说明"><InfoCircleOutlined style={{ color: '#999' }} /></Tooltip>}
      >
        {insights ? (
          <>
            <Row gutter={[16, 16]}>
              <Col span={3}>
                <Statistic
                  title={<Tooltip title={insights.stat_notes?.ai_avg_score || ''}>AI 平均分 <InfoCircleOutlined style={{ fontSize: 10, color: '#999' }} /></Tooltip>}
                  value={insights.ai_avg_score ?? '-'}
                  suffix={insights.ai_avg_score != null ? '/ 100' : ''}
                  valueStyle={{ color: insights.ai_avg_score != null ? (insights.ai_avg_score >= 80 ? '#52c41a' : insights.ai_avg_score >= 60 ? '#fa8c16' : '#ff4d4f') : '#999' }}
                />
              </Col>
              <Col span={4}>
                <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>AI 风险分布</div>
                <Space direction="vertical" size={4}>
                  <div><Tag color="green">低风险</Tag><span style={{ fontWeight: 600 }}>{insights.ai_risk_distribution.low}</span></div>
                  <div><Tag color="orange">中风险</Tag><span style={{ fontWeight: 600 }}>{insights.ai_risk_distribution.medium}</span></div>
                  <div><Tag color="red">高风险</Tag><span style={{ fontWeight: 600 }}>{insights.ai_risk_distribution.high}</span></div>
                </Space>
              </Col>
              <Col span={3}>
                <Statistic
                  title={<Tooltip title={insights.stat_notes?.ai_human_agreement_rate || ''}>AI/人工一致率 <InfoCircleOutlined style={{ fontSize: 10, color: '#999' }} /></Tooltip>}
                  value={insights.ai_human_agreement_rate != null ? formatPercent(insights.ai_human_agreement_rate) : '-'}
                  valueStyle={{ color: insights.ai_human_agreement_rate != null ? (insights.ai_human_agreement_rate >= 0.8 ? '#52c41a' : '#fa8c16') : '#999' }}
                />
              </Col>
              <Col span={3}>
                <Statistic title="人工通过率" value={insights.human_pass_rate != null ? formatPercent(insights.human_pass_rate) : '-'} valueStyle={{ color: '#52c41a' }} />
              </Col>
              <Col span={3}>
                <Statistic title="已打回" value={insights.rejected_count} valueStyle={{ color: '#ff4d4f' }} />
              </Col>
              <Col span={3}>
                <Statistic title="可导出" value={insights.exportable_count} prefix={<ExportOutlined />} valueStyle={{ color: '#13c2c2' }} />
              </Col>
              <Col span={3}>
                <Statistic title={<Tooltip title={insights.stat_notes?.low_score_count || ''}>低分样本 <InfoCircleOutlined style={{ fontSize: 10, color: '#999' }} /></Tooltip>} value={insights.low_score_count} valueStyle={{ color: insights.low_score_count > 0 ? '#ff4d4f' : '#52c41a' }} />
              </Col>
              <Col span={2}>
                <Statistic title={<Tooltip title={insights.stat_notes?.priority_review_count || ''}>重点复核 <InfoCircleOutlined style={{ fontSize: 10, color: '#999' }} /></Tooltip>} value={insights.priority_review_count} valueStyle={{ color: insights.priority_review_count > 0 ? '#fa8c16' : '#52c41a' }} />
              </Col>
            </Row>
            <div style={{ marginTop: 12, fontSize: 11, color: '#999', borderTop: '1px solid #f0f0f0', paddingTop: 8 }}>
              统计口径：AI 平均分基于已完成 AI 预审的数据计算 | AI/人工一致率基于已同时存在 AI 结果和人工审核结果的数据计算 | 低分样本为 AI 分数 &lt; 70 | 重点复核为低分、高风险、AI/人工不一致、曾被打回的数据
            </div>
          </>
        ) : (
          <Empty description="暂无质量洞察数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      <Card title={<span><BugOutlined /> Rubric 命中分析</span>} style={{ marginBottom: 16 }} size="small">
        {rubricData.length > 0 ? (
          <>
            <Table
              size="small"
              pagination={false}
              dataSource={rubricData}
              rowKey="rubric_id"
              columns={rubricColumns}
              scroll={{ x: 900 }}
            />
            <div style={{ marginTop: 8, fontSize: 11, color: '#999' }}>
              高争议 Rubric：AI/人工一致率低于 60%、不满足比例高于 40%、不确定比例高于 30%、或被打回样本中频繁出现
            </div>
          </>
        ) : (
          <Empty description="暂无 Rubric 命中分析数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      <Card title={<span><WarningOutlined /> 重点复核样本</span>} style={{ marginBottom: 16 }} size="small"
        extra={priorityItems.length > 0 ? <Tag color="orange">{priorityItems.length} 条需关注</Tag> : null}
      >
        {priorityItems.length > 0 ? (
          <Table
            size="small"
            pagination={{ pageSize: 10 }}
            dataSource={priorityItems}
            rowKey="submission_id"
            columns={priorityColumns}
            scroll={{ x: 1000 }}
          />
        ) : (
          <Empty description="暂无重点复核样本，数据质量良好" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      <Card title={<span><FileTextOutlined /> 质量报告</span>} style={{ marginBottom: 16 }} size="small"
        extra={
          <Space>
            <Button size="small" icon={<CopyOutlined />} onClick={() => {
              if (reportSummary) {
                navigator.clipboard.writeText(reportSummary).then(() => message.success('已复制报告摘要到剪贴板')).catch(() => message.error('复制失败'));
              }
            }}>复制摘要</Button>
            <Button type="primary" size="small" icon={<RobotOutlined />} loading={reportGenerating} onClick={handleGenerateReport}>
              生成 AI 质量报告
            </Button>
          </Space>
        }
      >
        <Alert type="info" style={{ marginBottom: 16 }} message={reportSummary} />
        {summary.top_issues.length > 0 && (
          <div>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>常见问题 Top 5</div>
            <Table
              size="small"
              pagination={false}
              dataSource={summary.top_issues}
              rowKey="message"
              columns={[
                { title: '排名', key: 'rank', width: 60, render: (_: any, __: any, i: number) => i + 1 },
                { title: '问题描述', dataIndex: 'message', key: 'message' },
                { title: '出现次数', dataIndex: 'count', key: 'count', width: 100, render: (v: number) => <Tag color="orange">{v}</Tag> }
              ]}
            />
          </div>
        )}
        {summary.top_issues.length === 0 && (
          <div style={{ color: '#52c41a' }}>暂无常见问题，数据质量良好</div>
        )}
      </Card>

      <Card title={<span><CameraOutlined /> 数据集版本快照 - 导出记录</span>} style={{ marginBottom: 16 }} size="small">
        <Space style={{ marginBottom: 16 }}>
          <Select value={exportFormat} onChange={setExportFormat} style={{ width: 120 }}>
            <Option value="json">JSON</Option>
            <Option value="jsonl">JSONL</Option>
            <Option value="csv">CSV</Option>
            <Option value="xlsx">XLSX</Option>
          </Select>
          <Button type="primary" icon={<ExportOutlined />} loading={exporting} onClick={handleExport}>
            导出已通过数据
          </Button>
          <Button onClick={() => { fetchExportJobs(); }}>刷新</Button>
        </Space>
        <Table
          size="small"
          columns={exportColumns}
          dataSource={exportJobs}
          rowKey="id"
          pagination={{ pageSize: 5 }}
          locale={{ emptyText: '暂无导出记录' }}
          scroll={{ x: 1000 }}
        />
      </Card>

      <Modal
        title={<span><CameraOutlined /> 数据集版本快照</span>}
        open={snapshotModalOpen}
        onCancel={() => setSnapshotModalOpen(false)}
        width={680}
        footer={[
          <Button key="copy" icon={<CopyOutlined />} onClick={() => {
            if (snapshotData) {
              navigator.clipboard.writeText(JSON.stringify(snapshotData, null, 2)).then(() => message.success('已复制快照摘要')).catch(() => message.error('复制失败'));
            }
          }}>复制</Button>,
          <Button key="close" onClick={() => setSnapshotModalOpen(false)}>关闭</Button>
        ]}
      >
        {snapshotLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : snapshotData ? (
          <div>
            <div style={{ marginBottom: 12, padding: 12, backgroundColor: '#f0f5ff', borderRadius: 6, border: '1px solid #d6e4ff' }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>
                <CameraOutlined style={{ marginRight: 6, color: '#1890ff' }} />
                {snapshotData.snapshot_id}
              </div>
              <div style={{ fontSize: 12, color: '#666' }}>
                策略版本: {snapshotData.quality_policy_version} | 数据筛选: {snapshotData.data_filter} | 生成时间: {snapshotData.generated_at ? formatDateTime(snapshotData.generated_at) : '-'}
              </div>
            </div>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="总行数">{snapshotData.total_rows}</Descriptions.Item>
              <Descriptions.Item label="已通过行数">{snapshotData.approved_rows}</Descriptions.Item>
              <Descriptions.Item label="含 AI 预审">{snapshotData.rows_with_ai_review}</Descriptions.Item>
              <Descriptions.Item label="缺失 AI 预审">
                <span style={{ color: snapshotData.rows_without_ai_review > 0 ? '#ff4d4f' : '#52c41a' }}>
                  {snapshotData.rows_without_ai_review}
                </span>
              </Descriptions.Item>
              <Descriptions.Item label="含人工审核">{snapshotData.rows_with_human_review}</Descriptions.Item>
              <Descriptions.Item label="导出格式">{(snapshotData.format || '').toUpperCase()}</Descriptions.Item>
              <Descriptions.Item label="包含 AI 预审结果">{snapshotData.includes_ai_review ? <Tag color="green">是</Tag> : <Tag color="red">否</Tag>}</Descriptions.Item>
              <Descriptions.Item label="包含人工审核结果">{snapshotData.includes_human_review ? <Tag color="green">是</Tag> : <Tag color="red">否</Tag>}</Descriptions.Item>
            </Descriptions>
            {snapshotData.rows_without_ai_review > 0 && (
              <Alert type="warning" style={{ marginTop: 12 }} message={`有 ${snapshotData.rows_without_ai_review} 条数据缺失 AI 预审结果，建议在正式交付前补齐`} showIcon />
            )}
          </div>
        ) : (
          <Empty description="无法获取快照数据" />
        )}
      </Modal>

      <Modal
        title="AI 质量报告"
        open={reportModalOpen}
        onCancel={() => setReportModalOpen(false)}
        width={720}
        footer={[
          <Button key="copy" icon={<CopyOutlined />} onClick={() => {
            if (qualityReport?.report_text) {
              navigator.clipboard.writeText(qualityReport.report_text).then(() => message.success('已复制报告到剪贴板')).catch(() => message.error('复制失败'));
            }
          }}>复制报告</Button>,
          <Button key="close" onClick={() => setReportModalOpen(false)}>关闭</Button>
        ]}
      >
        {qualityReport && (
          <div>
            <div style={{ marginBottom: 8, fontSize: 12, color: '#999' }}>
              生成来源: {qualityReport.generated_by} | 生成时间: {formatDateTime(qualityReport.generated_at)}
            </div>
            {qualityReport.sample_note && (
              <Alert type="warning" message={qualityReport.sample_note} style={{ marginBottom: 12 }} showIcon />
            )}
            {qualityReport.structured?.quality_policy_and_delivery && (
              <Alert type="info" style={{ marginBottom: 12 }} message={
                <div>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>质量策略与交付建议</div>
                  <div>当前任务采用 {qualityReport.structured.quality_policy_and_delivery.policy_version}，AI 分数 {qualityReport.structured.quality_policy_and_delivery.ai_pass_threshold} 分以上且低风险样本可作为自动放行候选。</div>
                  <div style={{ marginTop: 4 }}>当前可导出数据: {qualityReport.structured.quality_policy_and_delivery.exportable_count} 条</div>
                  <div style={{ marginTop: 4 }}>
                    {qualityReport.structured.quality_policy_and_delivery.recommend_immediate_export
                      ? <span style={{ color: '#52c41a' }}>建议可立即导出</span>
                      : <span style={{ color: '#fa8c16' }}>建议在正式交付前处理上述问题</span>
                    }
                  </div>
                </div>
              } showIcon icon={<SettingOutlined />} />
            )}
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, backgroundColor: '#f5f5f5', padding: 16, borderRadius: 6, maxHeight: 500, overflow: 'auto' }}>{qualityReport.report_text}</pre>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default TaskResultsPage;
