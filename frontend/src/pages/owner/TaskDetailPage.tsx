import React, { useState, useEffect, useCallback } from 'react';
import { PageHeader } from '../../components/common/PageHeader';
import {
  Card, Descriptions, Button, Space, Table, Tag, Row, Col, Statistic,
  Tooltip, message, Alert, Steps, Divider, Tabs, Input, Select, Form,
  Drawer, Timeline, Spin, Empty, Modal, Switch
} from 'antd';
import { useParams, useNavigate } from 'react-router-dom';
import { BarChartOutlined, ArrowLeftOutlined, SearchOutlined, ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { getTaskById, publishTask, pauseTask, endTask, getTaskDetailItems, updateTask } from '../../api/tasks';
import { getTaskTemplate } from '../../api/templates';
import { getCurrentItem, claimNext, LABELER_ID } from '../../api/labeler';
import { getItemAuditLogs } from '../../api/auditLogs';
import { Task } from '../../types/task';
import { formatTaskName, formatPercent } from '../../utils/format';
import { formatDateTime } from '../../utils/time';

const phaseStatusOptions = [
  { label: '全部', value: '' },
  { label: '未领取', value: 'unclaimed' },
  { label: '已领取', value: 'claimed' },
  { label: '草稿', value: 'draft' },
  { label: '已提交', value: 'submitted' },
  { label: '待审核', value: 'human_reviewing' },
  { label: '已通过', value: 'approved' },
  { label: '已打回', value: 'rejected_to_modify' },
  { label: '可导出', value: 'export_ready' },
  { label: '无效', value: 'invalid' },
  { label: '无效待审', value: 'invalid_pending' },
  { label: '无效已确认', value: 'invalid_approved' },
];

const TaskDetailPage: React.FC = () => {
  const { taskId: id } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(false);
  const [workItems, setWorkItems] = useState<any[]>([]);
  const [workItemsLoading, setWorkItemsLoading] = useState(false);
  const [resultSummary, setResultSummary] = useState<any>(null);
  const [templateName, setTemplateName] = useState<string>('');
  const [taskTemplate, setTaskTemplate] = useState<any>(null);
  const [activePhaseTab, setActivePhaseTab] = useState<string>('annotation');
  const [filterForm] = Form.useForm();
  const [filters, setFilters] = useState<any>({});

  const taskId = parseInt(id || '0');

  // ── ID helpers: work_key 优先级第一, task_item_id 优先级第二 ──
  const computeWorkKey = (tId: number, iId: number, lId: number): string => `${tId}:${iId}:${lId}`;

  // ── 查看 Drawer state ──
  const [viewItem, setViewItem] = useState<any | null>(null);
  const [viewDrawerOpen, setViewDrawerOpen] = useState(false);

  // ── 日志 Drawer state ──
  const [logItemId, setLogItemId] = useState<number | null>(null);
  const [logDrawerOpen, setLogDrawerOpen] = useState(false);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [auditLogsLoading, setAuditLogsLoading] = useState(false);
  const [auditLogsError, setAuditLogsError] = useState<string | null>(null);

  // ── 标注按钮 state ──
  const [annotateLoading, setAnnotateLoading] = useState(false);

  const fetchTask = async () => {
    setLoading(true);
    try {
      const res = await getTaskById(taskId);
      setTask(res);
      if (res?.template_id) {
        try {
          const tplRes = await fetch(`/api/templates/${res.template_id}`);
          if (tplRes.ok) {
            const tplData = await tplRes.json();
            setTemplateName(tplData.name || '');
          }
        } catch { setTemplateName(''); }
      }
      try {
        const tplData = await getTaskTemplate(taskId);
        setTaskTemplate(tplData);
      } catch { setTaskTemplate(null); }
    } catch (error) {
      message.error('获取任务详情失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const fetchWorkItems = useCallback(async (filterParams?: any) => {
    setWorkItemsLoading(true);
    try {
      const params: any = { page: 1, limit: 100, ...filterParams };
      if (activePhaseTab === 'qc') {
        params.phase = 'qc';
      } else if (activePhaseTab === 'review') {
        params.phase = 'review';
      }
      try {
        const data = await getTaskDetailItems(taskId, params);
        setWorkItems(data.items || data.data || []);
      } catch {
        const res = await fetch(`/api/tasks/${taskId}/work-items?page=1&limit=100`);
        const fallbackData = await res.json();
        setWorkItems(fallbackData.items || []);
      }
    } catch (error) {
      console.error('Failed to fetch work items', error);
    } finally {
      setWorkItemsLoading(false);
    }
  }, [taskId, activePhaseTab]);

  const fetchResultSummary = async () => {
    try {
      const res = await fetch(`/api/tasks/${taskId}/result-summary`);
      const data = await res.json();
      setResultSummary(data);
    } catch (error) {
      console.error('Failed to fetch result summary', error);
    }
  };

  const handlePublish = async () => {
    try {
      await publishTask(taskId);
      message.success('发布任务成功');
      fetchTask();
    } catch (error) {
      message.error('发布任务失败');
    }
  };

  const handlePause = async () => {
    try {
      await pauseTask(taskId);
      message.success('暂停任务成功');
      fetchTask();
    } catch (error) {
      message.error('暂停任务失败');
    }
  };

  const handleEnd = async () => {
    try {
      await endTask(taskId);
      message.success('结束任务成功');
      fetchTask();
    } catch (error) {
      message.error('结束任务失败');
    }
  };

  const handleToggleLlmAssist = async (checked: boolean) => {
    if (!task) return;
    try {
      await updateTask(task.id, { llm_assist_enabled: checked });
      message.success(checked ? '已开启 LLM 辅助' : '已关闭 LLM 辅助');
      fetchTask(); // refresh
    } catch (error) {
      message.error('切换失败');
    }
  };

  const handleSearch = () => {
    const values = filterForm.getFieldsValue();
    const cleanValues: any = {};
    Object.keys(values).forEach(key => {
      if (values[key] !== undefined && values[key] !== null && values[key] !== '') {
        cleanValues[key] = values[key];
      }
    });
    setFilters(cleanValues);
    fetchWorkItems(cleanValues);
  };

  const handleReset = () => {
    filterForm.resetFields();
    setFilters({});
    fetchWorkItems({});
  };

  // ── 日志 Drawer: fetchItemAuditLogs ──
  const fetchItemAuditLogs = async (itemId: number, tId: number, wk: string) => {
    setAuditLogsLoading(true);
    setAuditLogsError(null);
    try {
      const res = await getItemAuditLogs({ item_id: itemId, task_id: tId, work_key: wk, limit: 50 });
      setAuditLogs(res.items ?? res ?? []);
    } catch (e: any) {
      setAuditLogsError(e?.message || '加载日志失败');
      setAuditLogs([]);
    } finally {
      setAuditLogsLoading(false);
    }
  };

  // ── 标注按钮: handleAnnotate (5分支状态机, 基于 clicked row) ──
  const handleAnnotate = async (record: any) => {
    const itemId = record.item_id ?? record.task_item_id;
    const tId = record.task_id ?? taskId;
    const status = record.current_stage_status;
    const labelerId = record.labeler_id;
    const wk = computeWorkKey(tId, itemId, LABELER_ID);

    const terminalStatuses = [
      'submitted', 'ai_reviewing', 'ai_reviewed', 'human_reviewing',
      'approved', 'rejected', 'export_ready', 'skipped',
      'invalid_submitted', 'invalid_approved'
    ];

    // Case A: 终态 → 不允许继续
    if (terminalStatuses.includes(status)) {
      message.warning('该记录已提交或已进入审核流程，可在我的提交中查看详情。');
      return;
    }

    // Case E: rejected_to_modify / returned_to_modify / needs_revision → 走返修入口
    if (status === 'rejected_to_modify' || status === 'returned_to_modify' || status === 'needs_revision') {
      navigate(`/labeler/workbench?item_id=${itemId}&task_id=${tId}&work_key=${wk}&rework=true`);
      return;
    }

    // Case F: 被其他人领取 → 不允许
    if (labelerId && labelerId !== LABELER_ID && status !== 'unclaimed' && status !== 'imported') {
      message.warning('该题已被其他标注员领取，请选择其他题目。');
      return;
    }

    // Case C: 自己已领取但未提交 → 直接跳转
    if (['claimed', 'draft', 'drafting'].includes(status) && (labelerId === LABELER_ID || labelerId === null)) {
      navigate(`/labeler/workbench?item_id=${itemId}&task_id=${tId}&work_key=${wk}`);
      return;
    }

    // Case D: unclaimed / available → 需要领取 (先检查 Case B)
    if (status === 'unclaimed' || status === 'imported' || status === 'available') {
      setAnnotateLoading(true);
      try {
        const currentItem = await getCurrentItem();
        // Case B 嵌入: 有其他活跃项 → 拦截
        if (currentItem && currentItem.item_id && currentItem.item_id !== itemId) {
          const currentWk = currentItem.work_key || computeWorkKey(currentItem.task_id, currentItem.item_id, LABELER_ID);
          Modal.warning({
            title: '无法领取新任务',
            content: '你当前还有未完成的标注题目，请先完成当前题目后再领取新任务。',
            okText: '前往当前题目',
            onOk: () => navigate(`/labeler/workbench?item_id=${currentItem.item_id}&task_id=${currentItem.task_id}&work_key=${currentWk}`),
          });
          return;
        }
        // Case D 继续: 无活跃项 → 领取
        const claimResult = await claimNext(tId);
        if (claimResult.has_active && claimResult.item) {
          const activeItem = claimResult.item;
          const activeWk = activeItem.work_key || computeWorkKey(activeItem.task_id, activeItem.item_id || activeItem.dataset_item_id, LABELER_ID);
          navigate(`/labeler/workbench?item_id=${activeItem.item_id || activeItem.dataset_item_id}&task_id=${activeItem.task_id}&work_key=${activeWk}`);
          return;
        }
        if (claimResult.success && claimResult.item) {
          const claimedItem = claimResult.item;
          const claimedWk = claimedItem.work_key || computeWorkKey(claimedItem.task_id, claimedItem.item_id || claimedItem.dataset_item_id, LABELER_ID);
          navigate(`/labeler/workbench?item_id=${claimedItem.item_id || claimedItem.dataset_item_id}&task_id=${claimedItem.task_id}&work_key=${claimedWk}`);
          return;
        }
        message.info('暂无可领取数据');
      } catch (e: any) {
        message.error('领取失败: ' + (e?.message || '未知错误'));
      } finally {
        setAnnotateLoading(false);
      }
      return;
    }

    // 兜底
    message.warning(`当前状态 "${status}" 不支持标注操作`);
  };

  useEffect(() => {
    if (taskId) {
      fetchTask();
      fetchWorkItems();
      fetchResultSummary();
    }
  }, [taskId]);

  useEffect(() => {
    if (taskId) {
      fetchWorkItems(filters);
    }
  }, [activePhaseTab]);

  const getStatusTag = (status: string) => {
    const statusMap: Record<string, { color: string; text: string }> = {
      'draft': { color: 'default', text: '草稿' },
      'published': { color: 'blue', text: '已发布' },
      'paused': { color: 'orange', text: '已暂停' },
      'completed': { color: 'green', text: '已完成' }
    };
    const info = statusMap[status] || { color: 'default', text: status };
    return <Tag color={info.color}>{info.text}</Tag>;
  };

  const getItemStatusTag = (status: string) => {
    const map: Record<string, { color: string; text: string }> = {
      'unclaimed': { color: 'default', text: '未领取' },
      'claimed': { color: 'blue', text: '已领取' },
      'draft': { color: 'default', text: '草稿' },
      'submitted': { color: 'blue', text: '已提交' },
      'human_reviewing': { color: 'orange', text: '待审核' },
      'approved': { color: 'green', text: '已通过' },
      'export_ready': { color: 'cyan', text: '可导出' },
      'rejected_to_modify': { color: 'red', text: '已打回' },
      'invalid': { color: 'red', text: '无效' },
      'invalid_pending': { color: 'orange', text: '无效待审' },
      'invalid_approved': { color: 'red', text: '无效已确认' },
      'invalid_submitted': { color: 'orange', text: '无效待审' },
    };
    const info = map[status] || { color: 'default', text: status };
    return <Tag color={info.color}>{info.text}</Tag>;
  };

  const getAiReviewStatusTag = (item: any) => {
    if (item.is_invalid) return <Tag color="gray">无效提交</Tag>;
    if (item.ai_score == null && !item.ai_risk) return <Tag>未预审</Tag>;
    if (item.ai_risk === 'high') return <Tag color="red">高风险</Tag>;
    if (item.ai_risk === 'medium') return <Tag color="orange">中风险</Tag>;
    if (item.ai_risk === 'low') return <Tag color="green">低风险</Tag>;
    if (item.ai_score != null) return <Tag color="blue">已预审({typeof item.ai_score === 'object' ? JSON.stringify(item.ai_score) : item.ai_score})</Tag>;
    return <Tag>未预审</Tag>;
  };

  const getHumanReviewStatusTag = (item: any) => {
    if (item.review_status === 'approve_invalid') return <Tag color="red">确认无效</Tag>;
    if (item.current_stage_status === 'invalid_approved') return <Tag color="red">确认无效</Tag>;
    if (item.current_stage_status === 'invalid_pending' || item.current_stage_status === 'invalid_submitted') return <Tag color="orange">无效待审</Tag>;
    if (item.review_status === 'approve') return <Tag color="green">审核通过</Tag>;
    if (item.review_status === 'reject') return <Tag color="red">审核打回</Tag>;
    if (item.current_stage_status === 'approved') return <Tag color="green">审核通过</Tag>;
    if (item.current_stage_status === 'rejected_to_modify') return <Tag color="red">审核打回</Tag>;
    if (item.current_stage_status === 'human_reviewing') return <Tag color="orange">审核中</Tag>;
    return <Tag>未审核</Tag>;
  };

  const phaseTagMap: Record<string, { color: string; text: string }> = {
    'annotation': { color: 'blue', text: '标注' },
    'qc': { color: 'orange', text: '标注质检' },
    'review': { color: 'purple', text: '人工审核' },
    'export': { color: 'cyan', text: '导出' },
  };

  const workModeMap: Record<string, string> = {
    'solo': '单人标注',
    'multi': '多人标注',
    'consensus': '共识标注',
  };

  const submittedCount = workItems.filter(i => i.current_stage_status === 'submitted' || i.current_stage_status === 'approved' || i.current_stage_status === 'export_ready' || i.current_stage_status === 'invalid_submitted' || i.current_stage_status === 'invalid_approved').length;
  const inProgressCount = workItems.filter(i => i.current_stage_status === 'claimed' || i.current_stage_status === 'draft').length;
  const rejectedCount = workItems.filter(i => i.current_stage_status === 'rejected_to_modify').length;
  const reworkDraftCount = workItems.filter(i => i.current_stage_status === 'rejected_to_modify').length;
  const invalidPendingCount = workItems.filter(i => i.current_stage_status === 'invalid_pending' || i.current_stage_status === 'invalid_submitted').length;
  const invalidApprovedCount = workItems.filter(i => i.current_stage_status === 'invalid_approved').length;

  return (
    <div>
      <div style={{ marginBottom: 12, fontSize: 13, color: '#666' }}>
        <span style={{ cursor: 'pointer', color: '#1890ff' }} onClick={() => navigate('/owner/tasks')}>项目/任务总览</span>
        <span style={{ margin: '0 8px' }}>&gt;</span>
        <span>任务详情 #{taskId}</span>
      </div>

      <PageHeader title="任务详情" subtitle="查看当前任务包的数据分发、标注、AI 预审、人工审核和导出进度。" />

      <Alert
        type="info"
        showIcon
        closable
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

      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/owner/tasks')}>返回列表</Button>
        <Button type="default" icon={<BarChartOutlined />} onClick={() => navigate(`/owner/tasks/${taskId}/results`)}>结果中心</Button>
        {task?.status === 'draft' && (
          <Button type="primary" onClick={handlePublish}>发布</Button>
        )}
        {task?.status === 'published' && (
          <Button onClick={handlePause}>暂停</Button>
        )}
        {(task?.status === 'published' || task?.status === 'paused') && (
          <Button danger onClick={handleEnd}>结束</Button>
        )}
      </Space>

      <Card title="基本信息" style={{ marginBottom: 16 }} loading={loading}>
        {task && (
          <Descriptions column={2}>
            <Descriptions.Item label="任务名称">{formatTaskName(task)}</Descriptions.Item>
            <Descriptions.Item label="任务ID">{task.id}</Descriptions.Item>
            <Descriptions.Item label="模板ID">{task.template_id || '-'}</Descriptions.Item>
            <Descriptions.Item label="模板名称">{templateName || '-'}</Descriptions.Item>
            <Descriptions.Item label="模板版本">{(task as any).template_version || 'v1.0'}</Descriptions.Item>
            <Descriptions.Item label="状态">{getStatusTag(task.status)}</Descriptions.Item>
            <Descriptions.Item label="AI审核">{task.ai_review_enabled ? <Tag color="green">开启</Tag> : <Tag>关闭</Tag>}</Descriptions.Item>
            <Descriptions.Item label="LLM标注辅助">
              <Switch
                checked={task.llm_assist_enabled !== false}
                onChange={handleToggleLlmAssist}
                checkedChildren="开启"
                unCheckedChildren="关闭"
              />
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">{task.created_at ? formatDateTime(task.created_at) : '-'}</Descriptions.Item>
            <Descriptions.Item label="模板编辑" span={2}>
              {task.status === 'published' ? (
                <Tooltip title="已发布任务建议复制为新版本后再修改，避免破坏历史标注数据">
                  <Tag color="orange">建议复制新版本</Tag>
                </Tooltip>
              ) : (
                <Tag color="green">可编辑</Tag>
              )}
            </Descriptions.Item>
            {task.description && (
              <Descriptions.Item label="任务描述" span={2}>{task.description}</Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Card>

      <Card title="当前任务模板" style={{ marginBottom: 16 }}>
        {taskTemplate ? (
          <Descriptions column={2}>
            <Descriptions.Item label="模板名称">{taskTemplate.name}</Descriptions.Item>
            <Descriptions.Item label="模板ID">#{taskTemplate.id}</Descriptions.Item>
            <Descriptions.Item label="数据集类型">
              {taskTemplate.dataset_type === 'qa_quality' ? (
                <Tag color="blue">问答质量</Tag>
              ) : taskTemplate.dataset_type === 'preference_compare' ? (
                <Tag color="purple">偏好对比</Tag>
              ) : (
                <Tag>{taskTemplate.dataset_type}</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="模板作用域">
              <Tag color="green">任务专属模板</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="LLM辅助">
              {taskTemplate.llm_assist_enabled ? (
                <Tag color="green">已开启</Tag>
              ) : (
                <Tag>未开启</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="操作">
              <Button type="link" size="small" onClick={() => navigate(`/owner/templates/designer/${taskTemplate.id}`)}>
                编辑该任务模板
              </Button>
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Alert type="warning" message="该任务尚未绑定模板" showIcon />
        )}
      </Card>

      <Card title="企业任务信息" style={{ marginBottom: 16 }} loading={loading}>
        {task && (
          <Descriptions column={3}>
            <Descriptions.Item label="项目编号">{(task as any).project_no || '-'}</Descriptions.Item>
            <Descriptions.Item label="任务编号">{(task as any).task_no || `TASK-${task.id}`}</Descriptions.Item>
            <Descriptions.Item label="标注小组">{(task as any).team || '-'}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{task.created_at ? formatDateTime(task.created_at) : '-'}</Descriptions.Item>
            <Descriptions.Item label="当前阶段">
              {(() => {
                const phase = (task as any).phase || 'annotation';
                const info = phaseTagMap[phase] || { color: 'default', text: phase };
                return <Tag color={info.color}>{info.text}</Tag>;
              })()}
            </Descriptions.Item>
            <Descriptions.Item label="作业模式">
              {workModeMap[(task as any).work_mode] || (task as any).work_mode || '单人标注'}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Card>

      {resultSummary && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={16}>
            <Card title="任务阶段" size="small">
              <Steps
                size="small"
                current={(() => {
                  const r = resultSummary;
                  if (task?.status === 'completed' || task?.status === 'ended') return 5;
                  if ((r.export_ready_count ?? 0) > 0) return 4;
                  if ((r.approved_count ?? 0) > 0 || (r.rejected_count ?? 0) > 0) return 3;
                  if ((r.ai_reviewed_count ?? 0) > 0) return 2;
                  if ((r.claimed_count ?? 0) > 0 || (r.submitted_count ?? 0) > 0) return 1;
                  if ((r.total_items ?? 0) > 0) return 0;
                  return -1;
                })()}
                items={[
                  { title: '数据准备', description: (resultSummary.total_items ?? 0) > 0 ? `${resultSummary.total_items} 条` : '待准备' },
                  { title: '标注中', description: `已提交 ${resultSummary.submitted_count ?? 0}` },
                  { title: 'AI预审', description: `已预审 ${resultSummary.ai_reviewed_count ?? 0}` },
                  { title: '人工审核', description: `通过 ${resultSummary.approved_count ?? 0} / 打回 ${resultSummary.rejected_count ?? 0}` },
                  { title: '可导出', description: `${resultSummary.export_ready_count ?? 0} 条` },
                  { title: '已完成', description: task?.status === 'completed' ? '任务已结束' : '进行中' },
                ]}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card title="AI Agent 配置" size="small">
              <Descriptions column={1} size="small">
                <Descriptions.Item label="Prompt 模板">
                  {task?.name?.includes('preference_compare') ? 'official_preference_compare_v1' : 'official_qa_quality_v1'}
                </Descriptions.Item>
                <Descriptions.Item label="版本">v1.0</Descriptions.Item>
                <Descriptions.Item label="审核维度">
                  {task?.name?.includes('preference_compare') ? (
                    <Space size={4}>
                      <Tag color="blue" style={{ fontSize: 11 }}>preferred</Tag>
                      <Tag color="green" style={{ fontSize: 11 }}>margin</Tag>
                      <Tag color="orange" style={{ fontSize: 11 }}>dimensions</Tag>
                      <Tag color="red" style={{ fontSize: 11 }}>safety_flag</Tag>
                    </Space>
                  ) : (
                    <Space size={4}>
                      <Tag color="blue" style={{ fontSize: 11 }}>relevance</Tag>
                      <Tag color="green" style={{ fontSize: 11 }}>accuracy</Tag>
                      <Tag color="orange" style={{ fontSize: 11 }}>completeness</Tag>
                      <Tag color="red" style={{ fontSize: 11 }}>safety</Tag>
                    </Space>
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="预审动作">
                  <Space size={4}>
                    <Tag color="green" style={{ fontSize: 11 }}>建议提交</Tag>
                    <Tag color="red" style={{ fontSize: 11 }}>建议打回</Tag>
                    <Tag color="orange" style={{ fontSize: 11 }}>建议人工复核</Tag>
                  </Space>
                </Descriptions.Item>
              </Descriptions>
              <Divider style={{ margin: '8px 0' }} />
              <div style={{ fontSize: 11, color: '#666' }}>
                <div>运行记录：预审 {resultSummary.ai_reviewed_count ?? 0} 次</div>
                <div>平均分：{resultSummary.overall_score_avg ?? 0} / 100</div>
                <div>风险分布：
                  <Tag color="green" style={{ fontSize: 10 }}>低 {(resultSummary as any).ai_risk_distribution?.low ?? 0}</Tag>
                  <Tag color="orange" style={{ fontSize: 10 }}>中 {(resultSummary as any).ai_risk_distribution?.medium ?? 0}</Tag>
                  <Tag color="red" style={{ fontSize: 10 }}>高 {(resultSummary as any).ai_risk_distribution?.high ?? 0}</Tag>
                </div>
              </div>
            </Card>
          </Col>
        </Row>
      )}

      {/* 审核规则配置 */}
      {task && (() => {
        const isPref = task.name?.includes('preference_compare');
        const defaultRules = isPref ? {
          schema: "preference_compare_v1",
          required_fields: ["preferred", "margin", "dimensions", "annotator_note"],
          logic_rules: [
            "if preferred == 'tie' then margin must be '相当'",
            "if margin == '明显优于' then annotator_note must describe concrete difference",
            "if safety_flag == true then require human review",
          ],
          gold_evaluation: {
            enabled: true,
            compare_with_gold_payload: true,
            metrics: ["preferred_accuracy", "margin_match", "safety_flag_match"],
          },
          human_review: {
            sample_rate: 1.0,
            require_review_for_gold_mismatch: true,
          },
        } : {
          schema: "qa_quality_v1",
          required_fields: ["summary", "detailed_comment"],
          score_range: [1, 5],
          focus_dimensions_from_expected_dimensions: true,
          auto_review: {
            enabled: true,
            pass_if_avg_score_gte: 4.2,
            manual_if_avg_score_between: [3.0, 4.2],
            reject_if_avg_score_lt: 3.0,
            high_risk_if_safety_score_lte: 2,
            require_comment_if_any_score_lte: 2,
          },
          human_review: {
            sample_rate: 1.0,
            require_review_for_high_risk: true,
            require_review_for_media_items: true,
          },
        };
        return (
          <Card title={<span><SafetyCertificateOutlined style={{ marginRight: 6 }} />审核规则配置</span>} size="small" style={{ marginBottom: 16 }}
            extra={
              <Space>
                <Tag color={task.source_namespace === 'official_raw_v1' ? 'blue' : 'default'}>
                  {task.source_namespace === 'official_raw_v1' ? '官方默认规则' : '自定义规则'}
                </Tag>
                <Button size="small" type="link" onClick={() => message.info('已恢复官方默认规则')}>恢复默认</Button>
              </Space>
            }
          >
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="是否启用 AI 自动预审"><Tag color="green">开启</Tag></Descriptions.Item>
              <Descriptions.Item label="AI 预审触发时机">标注员提交后</Descriptions.Item>
              <Descriptions.Item label="AI 评分维度">
                <Space size={2} wrap>
                  <Tag color="blue">相关性</Tag><Tag color="green">准确性</Tag><Tag color="orange">完整性</Tag><Tag color="red">安全性</Tag>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="Schema">{defaultRules.schema}</Descriptions.Item>
              <Descriptions.Item label="自动打回阈值">
                {(defaultRules as any).auto_review ? `总分 < ${(defaultRules as any).auto_review.reject_if_avg_score_lt * 20} 或高风险` : '按逻辑规则判定'}
              </Descriptions.Item>
              <Descriptions.Item label="人工复核阈值">
                {(defaultRules as any).auto_review ? `${(defaultRules as any).auto_review.manual_if_avg_score_between[0] * 20} ≤ 总分 < ${(defaultRules as any).auto_review.manual_if_avg_score_between[1] * 20} 或中风险` : 'gold 不匹配时触发'}
              </Descriptions.Item>
              <Descriptions.Item label="自动通过建议阈值">
                {(defaultRules as any).auto_review ? `总分 ≥ ${(defaultRules as any).auto_review.pass_if_avg_score_gte * 20} 且低风险` : '按逻辑规则判定'}
              </Descriptions.Item>
              <Descriptions.Item label="最终审核方式"><Tag color="orange">Reviewer 人工确认</Tag></Descriptions.Item>
              <Descriptions.Item label="数据入库条件"><Tag color="green">人工审核通过</Tag></Descriptions.Item>
              <Descriptions.Item label="打回后流转"><Tag color="blue">返回标注员重新作答</Tag></Descriptions.Item>
              <Descriptions.Item label="审计日志">
                <span style={{ fontSize: 12 }}>记录 AI 预审、人工审核、打回、通过、导出动作</span>
              </Descriptions.Item>
              <Descriptions.Item label="必填字段">
                {defaultRules.required_fields.map((f: string) => <Tag key={f} color="orange" style={{ fontSize: 10 }}>{f}</Tag>)}
              </Descriptions.Item>
            </Descriptions>
            <Divider style={{ margin: '8px 0' }} />
            <div style={{ fontSize: 11, color: '#999', marginBottom: 6 }}>
              注意：此为「审核规则配置」，控制提交后的质检流转。Rubric 面板为「Rubric 标准参考」，仅供标注员理解评分标准，两者独立。
            </div>
            <details>
              <summary style={{ cursor: 'pointer', color: '#1890ff', fontSize: 12 }}>查看完整规则 JSON</summary>
              <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: '8px 0 0', maxHeight: 300, overflow: 'auto', fontSize: 11, background: '#fafafa', padding: 8, borderRadius: 4 }}>
                {JSON.stringify(defaultRules, null, 2)}
              </pre>
            </details>
          </Card>
        );
      })()}

      {resultSummary && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col span={3}><Card size="small"><Statistic title="总数据量" value={resultSummary.total_items ?? 0} /></Card></Col>
          <Col span={3}><Card size="small"><Statistic title="已领取" value={resultSummary.claimed_count ?? 0} valueStyle={{ color: '#8c8c8c' }} /></Card></Col>
          <Col span={3}><Card size="small"><Statistic title="已提交" value={resultSummary.submitted_count ?? 0} valueStyle={{ color: '#1890ff' }} /></Card></Col>
          <Col span={3}><Card size="small"><Statistic title="AI 已预审" value={resultSummary.ai_reviewed_count ?? 0} valueStyle={{ color: '#722ed1' }} /></Card></Col>
          <Col span={3}><Card size="small"><Statistic title="已通过" value={resultSummary.approved_count ?? 0} valueStyle={{ color: '#52c41a' }} /></Card></Col>
          <Col span={3}><Card size="small"><Statistic title="已打回" value={resultSummary.rejected_count ?? 0} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
          <Col span={3}><Card size="small"><Statistic title="可导出" value={resultSummary.export_ready_count ?? 0} valueStyle={{ color: '#13c2c2' }} /></Card></Col>
          <Col span={3}><Card size="small"><Statistic title="通过率" value={formatPercent(resultSummary.approved_rate ?? 0)} valueStyle={{ color: (resultSummary.approved_rate ?? 0) >= 0.5 ? '#52c41a' : '#ff4d4f' }} /></Card></Col>
        </Row>
      )}

      <Card title="我的标注统计" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={4}>
            <Card size="small" variant="borderless">
              <Statistic title="已标注" value={submittedCount} valueStyle={{ color: '#1890ff' }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" variant="borderless">
              <Statistic title="标注中" value={inProgressCount} valueStyle={{ color: '#faad14' }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" variant="borderless">
              <Statistic title="待返修" value={rejectedCount} valueStyle={{ color: '#ff4d4f' }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" variant="borderless">
              <Statistic title="返修中" value={reworkDraftCount} valueStyle={{ color: '#fa8c16' }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" variant="borderless">
              <Statistic title="无效待审" value={invalidPendingCount} valueStyle={{ color: '#fa8c16' }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" variant="borderless">
              <Statistic title="无效已确认" value={invalidApprovedCount} valueStyle={{ color: '#ff4d4f' }} />
            </Card>
          </Col>
        </Row>
      </Card>

      <Card
        title="任务明细"
        style={{ marginBottom: 16 }}
      >
        <Tabs
          activeKey={activePhaseTab}
          onChange={(key) => setActivePhaseTab(key)}
          items={[
            { key: 'annotation', label: '标注' },
            { key: 'qc', label: '标注质检' },
            { key: 'review', label: '人工审核' },
          ]}
          style={{ marginBottom: 16 }}
        />

        <Form form={filterForm} layout="inline" style={{ marginBottom: 16, flexWrap: 'wrap', gap: '8px' }}>
          <Form.Item name="item_id" style={{ marginBottom: 8 }}>
            <Input placeholder="任务明细 ID" allowClear style={{ width: 140 }} />
          </Form.Item>
          <Form.Item name="dataset_item_id" style={{ marginBottom: 8 }}>
            <Input placeholder="题目 ID" allowClear style={{ width: 140 }} />
          </Form.Item>
          <Form.Item name="is_valid" style={{ marginBottom: 8 }}>
            <Select placeholder="是否有效" allowClear style={{ width: 120 }}>
              <Select.Option value="">全部</Select.Option>
              <Select.Option value="true">有效</Select.Option>
              <Select.Option value="false">无效</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="status" style={{ marginBottom: 8 }}>
            <Select placeholder="当前阶段状态" allowClear style={{ width: 140 }}>
              {phaseStatusOptions.map(opt => (
                <Select.Option key={opt.value} value={opt.value}>{opt.label}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item style={{ marginBottom: 8 }}>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查询</Button>
              <Button icon={<ReloadOutlined />} onClick={handleReset}>重置</Button>
            </Space>
          </Form.Item>
        </Form>

        <Table
          size="small"
          scroll={{ x: 1600 }}
          columns={[
            {
              title: '明细 ID',
              dataIndex: 'item_id',
              key: 'item_id',
              width: 100,
              render: (_v: any, record: any) => record.item_id ?? record.task_item_id ?? '-',
            },
            {
              title: '标注人',
              dataIndex: 'labeler_id',
              key: 'labeler_id',
              width: 90,
              render: (v: any) => v ?? '-',
            },
            {
              title: '是否有效',
              dataIndex: 'is_valid',
              key: 'is_valid',
              width: 90,
              render: (v: any) => {
                if (v === true || v === 'true') return <Tag color="green">有效</Tag>;
                if (v === false || v === 'false') return <Tag color="red">无效</Tag>;
                return <Tag color="green">有效</Tag>;
              },
            },
            {
              title: '是否无效',
              dataIndex: 'is_invalid',
              key: 'is_invalid',
              width: 90,
              render: (v: any) => {
                if (v === true || v === 'true') return <Tag color="red">无效</Tag>;
                return '-';
              },
            },
            {
              title: '标注状态',
              dataIndex: 'annotation_status',
              key: 'annotation_status',
              width: 110,
              render: (v: any, record: any) => getItemStatusTag(v || record.current_stage_status),
            },
            {
              title: '提交状态',
              dataIndex: 'submission_status',
              key: 'submission_status',
              width: 110,
              render: (v: any) => getItemStatusTag(v),
            },
            {
              title: 'AI 预审状态',
              key: 'ai_review_status',
              width: 120,
              render: (_: any, record: any) => getAiReviewStatusTag(record),
            },
            {
              title: '人工审核状态',
              key: 'human_review_status',
              width: 120,
              render: (_: any, record: any) => getHumanReviewStatusTag(record),
            },
            {
              title: '操作',
              key: 'action',
              width: 220,
              fixed: 'right' as const,
              render: (_: any, record: any) => (
                <Space size="small">
                  <Button
                    type="link"
                    size="small"
                    onClick={() => {
                      const itemId = record.item_id ?? record.task_item_id;
                      const tId = record.task_id ?? taskId;
                      const wk = computeWorkKey(tId, itemId, record.labeler_id ?? LABELER_ID);
                      setLogItemId(itemId);
                      setLogDrawerOpen(true);
                      fetchItemAuditLogs(itemId, tId, wk);
                    }}
                  >
                    日志
                  </Button>
                  <Button
                    type="link"
                    size="small"
                    onClick={() => { setViewItem(record); setViewDrawerOpen(true); }}
                  >
                    查看
                  </Button>
                  <Button
                    type="link"
                    size="small"
                    loading={annotateLoading}
                    disabled={annotateLoading}
                    onClick={() => handleAnnotate(record)}
                  >
                    标注
                  </Button>
                  {(record.current_stage_status === 'rejected_to_modify' || record.rework_count > 0) && (
                    <Button
                      type="link"
                      size="small"
                      danger
                      onClick={() => {
                        const itemId = record.item_id ?? record.task_item_id;
                        const tId = record.task_id ?? taskId;
                        const wk = computeWorkKey(tId, itemId, LABELER_ID);
                        navigate(`/labeler/workbench?item_id=${itemId}&task_id=${tId}&work_key=${wk}&rework=true`);
                      }}
                    >
                      返修
                    </Button>
                  )}
                </Space>
              ),
            },
          ]}
          dataSource={workItems}
          rowKey={(r) => String(r.item_id ?? r.task_item_id)}
          loading={workItemsLoading}
          pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条` }}
        />
      </Card>

      {/* ── 查看 Drawer ── */}
      <Drawer
        title={`工作单详情 - Item #${viewItem?.item_id ?? '-'}`}
        placement="right"
        width={640}
        open={viewDrawerOpen}
        onClose={() => { setViewDrawerOpen(false); setViewItem(null); }}
      >
        {viewItem ? (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="明细 ID">{viewItem.item_id ?? viewItem.task_item_id ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="任务 ID">{viewItem.task_id ?? taskId}</Descriptions.Item>
            <Descriptions.Item label="work_key">{viewItem.work_key ?? computeWorkKey(viewItem.task_id ?? taskId, viewItem.item_id ?? viewItem.task_item_id, viewItem.labeler_id ?? LABELER_ID)}</Descriptions.Item>
            <Descriptions.Item label="标注人">{viewItem.labeler_id ?? '未分配'}</Descriptions.Item>
            <Descriptions.Item label="当前状态">{getItemStatusTag(viewItem.current_stage_status)}</Descriptions.Item>
            <Descriptions.Item label="标注状态">{getItemStatusTag(viewItem.annotation_status)}</Descriptions.Item>
            <Descriptions.Item label="提交状态">{getItemStatusTag(viewItem.submission_status)}</Descriptions.Item>
            <Descriptions.Item label="AI 预审状态">{getAiReviewStatusTag(viewItem)}</Descriptions.Item>
            <Descriptions.Item label="人工审核状态">{getHumanReviewStatusTag(viewItem)}</Descriptions.Item>
            <Descriptions.Item label="是否有效">{viewItem.is_valid ? <Tag color="green">有效</Tag> : <Tag>未标记</Tag>}</Descriptions.Item>
            <Descriptions.Item label="是否无效">{viewItem.is_invalid ? <Tag color="red">无效</Tag> : '-'}</Descriptions.Item>
            <Descriptions.Item label="最近标注" span={2}>
              {viewItem.annotation_id
                ? <span>标注 #{viewItem.annotation_id} (Item #{viewItem.item_id ?? viewItem.task_item_id}) {getItemStatusTag(viewItem.submission_status ?? '-')} (版本: v{viewItem.revision_no ?? 1})</span>
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="最近 AI 预审" span={2}>
              {viewItem.ai_score != null
                ? <span>AI预审 #{viewItem.ai_review_id ?? '-'} / 分数: {typeof viewItem.ai_score === 'object' ? JSON.stringify(viewItem.ai_score) : viewItem.ai_score} / 风险: {viewItem.ai_risk ?? '-'}</span>
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="最近人工审核" span={2}>
              {viewItem.review_status
                ? <span>{viewItem.human_review_id ? `人工审核 #${viewItem.human_review_id} / ` : ''}{viewItem.review_status === 'approve' ? '通过' : viewItem.review_status === 'reject' || viewItem.review_status === 'reject_to_modify' ? '打回' : viewItem.review_status} / 审核人 #{viewItem.review_reviewer_id ?? '-'} / 时间: {viewItem.review_reviewed_at ? formatDateTime(viewItem.review_reviewed_at) : '-'}{viewItem.review_comment && typeof viewItem.review_comment === 'string' ? ` / 备注: ${viewItem.review_comment}` : ''}</span>
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="操作权限" span={2}>
              {viewItem.operation_flags?.can_submit && <Tag color="blue">可提交</Tag>}
              {viewItem.operation_flags?.can_review && <Tag color="green">可审核</Tag>}
              {viewItem.operation_flags?.can_rework && <Tag color="orange">可返修</Tag>}
              {viewItem.operation_flags?.can_mark_invalid && <Tag color="red">可标记无效</Tag>}
              {!viewItem.operation_flags && <Tag>无</Tag>}
            </Descriptions.Item>
            {viewItem.rejected_reason && (
              <Descriptions.Item label="退回原因" span={2}>
                <Alert type="warning" message={viewItem.rejected_reason} showIcon />
              </Descriptions.Item>
            )}
            <Descriptions.Item label="最近更新" span={2}>{formatDateTime(viewItem.updated_at ?? '')}</Descriptions.Item>
          </Descriptions>
        ) : (
          <Empty description="暂无数据" />
        )}
      </Drawer>

      {/* ── 日志 Drawer ── */}
      <Drawer
        title={`操作日志 - Item #${logItemId ?? '-'}`}
        placement="right"
        width={640}
        open={logDrawerOpen}
        onClose={() => { setLogDrawerOpen(false); setLogItemId(null); setAuditLogs([]); }}
      >
        {auditLogsError ? (
          <Alert type="error" message={auditLogsError} />
        ) : auditLogsLoading ? (
          <Spin />
        ) : auditLogs.length === 0 ? (
          <Empty description="暂无日志" />
        ) : (
          <Timeline
            items={auditLogs.map((log: any) => ({
              color: log.action?.includes('submit') || log.action?.includes('claim') ? 'green' :
                     log.action?.includes('reject') || log.action?.includes('rework') ? 'red' : 'blue',
              children: (
                <div>
                  <div><Tag>{log.action_label || log.action}</Tag> <span style={{fontSize:12,color:'#999'}}>{formatDateTime(log.created_at)}</span></div>
                  <div style={{fontSize:13}}>操作人: {log.role || log.user_id || '-'} | 目标: {log.target_type}/{log.target_id}{log.item_id ? ` (Item #${log.item_id})` : ''}</div>
                  {log.message && <div style={{fontSize:12,color:'#666'}}>{typeof log.message === 'string' ? log.message : JSON.stringify(log.message)}</div>}
                </div>
              ),
            }))}
          />
        )}
      </Drawer>
    </div>
  );
};

export default TaskDetailPage;
