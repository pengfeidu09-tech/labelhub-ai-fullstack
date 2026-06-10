import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Row, Col, Statistic, Spin, Empty, Tag, Button, Space, Steps, Alert, Tooltip, Descriptions, Divider, Switch, message } from 'antd';
import {
  CheckCircleOutlined, CloseCircleOutlined, RobotOutlined,
  ExportOutlined, FileTextOutlined, InfoCircleOutlined, WarningOutlined,
  SafetyCertificateOutlined, BugOutlined, DashboardOutlined, ThunderboltOutlined,
  PlayCircleOutlined, ReloadOutlined, ExperimentOutlined,
  CloudServerOutlined, AuditOutlined,
  AppstoreOutlined, ProjectOutlined
} from '@ant-design/icons';
import { formatDateTimeShort } from '../../utils/time';
import { formatPercent } from '../../utils/format';
import { getAuditActionText, getAuditActionColor } from '../../utils/status';

const apiBase = '/api';

interface DashboardStats {
  project_count: number;
  task_count: number;
  total_items: number;
  submitted_count: number;
  approved_count: number;
  exportable_count: number;
  ai_reviewed_count: number;
  audit_log_count: number;
  template_count: number;
  export_count: number;
  demo_task: {
    task_id: number;
    task_name: string;
    template_name: string;
    total_items: number;
    submitted_count: number;
    approved_count: number;
    ai_reviewed_count: number;
    exportable_count: number;
  } | null;
}

interface DashboardQuality {
  ai_avg_score: number | null;
  ai_risk_distribution: { low: number; medium: number; high: number };
  ai_human_agreement_rate: number | null;
  human_pass_rate: number | null;
  priority_review_count: number;
  high_dispute_rubric_count: number;
}

interface ActivityItem {
  id: number;
  action: string;
  action_label: string;
  user_id: number | null;
  role: string | null;
  target_type: string | null;
  target_id: number | null;
  task_id: number | null;
  message: string | null;
  created_at: string | null;
}

interface SystemHealth {
  database?: { status: string; message: string };
  api?: { status: string; message: string };
  demo_data?: Record<string, boolean>;
  ai_precheck?: { status: string; mode: string; model: string; message: string };
  export_formats?: Record<string, { available: boolean; message: string }>;
}


const DEMO_MODE_KEY = 'labelhub_demo_mode';

const OwnerDashboard: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [quality, setQuality] = useState<DashboardQuality | null>(null);
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [demoMode, setDemoMode] = useState(() => localStorage.getItem(DEMO_MODE_KEY) === 'true');

  const safeNum = (v: any, fallback: number = 0): number => {
    if (v == null || v === undefined || isNaN(v)) return fallback;
    return typeof v === 'number' ? v : Number(v) || fallback;
  };

  const safePct = (v: any): string => {
    if (v == null || v === undefined || isNaN(v)) return '-';
    return formatPercent(v);
  };

  useEffect(() => {
    fetchAll();
  }, []);

  useEffect(() => {
    localStorage.setItem(DEMO_MODE_KEY, String(demoMode));
    if (demoMode) {
      logDemoAction('demo_mode_enable');
    } else {
      logDemoAction('demo_mode_disable');
    }
  }, [demoMode]);

  const logDemoAction = async (action: string) => {
    try {
      const { apiClient } = await import('../../api/client');
      await apiClient.post('/audit-logs', {
        user_id: 1, action, target_type: 'system', target_id: 0,
        role: 'owner', message: action === 'demo_mode_enable' ? '开启演示模式' : '关闭演示模式',
      });
    } catch (_) {
    }
  };

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [statsRes, qualityRes, actRes, healthRes] = await Promise.allSettled([
        fetch(`${apiBase}/dashboard/stats`).then(r => r.ok ? r.json() : null),
        fetch(`${apiBase}/dashboard/quality`).then(r => r.ok ? r.json() : null),
        fetch(`${apiBase}/dashboard/activities`).then(r => r.ok ? r.json() : []),
        fetch(`${apiBase}/dashboard/health-check`).then(r => r.ok ? r.json() : null),
      ]);
      if (statsRes.status === 'fulfilled' && statsRes.value) setStats(statsRes.value);
      if (qualityRes.status === 'fulfilled' && qualityRes.value) setQuality(qualityRes.value);
      if (actRes.status === 'fulfilled' && actRes.value) setActivities(Array.isArray(actRes.value) ? actRes.value : []);
      if (healthRes.status === 'fulfilled' && healthRes.value) setHealth(healthRes.value);
    } catch (error) {
      console.error('Failed to fetch dashboard data', error);
    } finally {
      setLoading(false);
    }
  };

  const refreshHealth = async () => {
    setHealthLoading(true);
    try {
      const res = await fetch(`${apiBase}/dashboard/health-check`);
      if (res.ok) {
        const data = await res.json();
        setHealth(data);
        message.success('系统健康检查已刷新');
      }
    } catch (e) {
      message.error('健康检查请求失败');
    } finally {
      setHealthLoading(false);
    }
  };

  const healthStatusTag = (status?: string) => {
    if (!status) return <Tag>未知</Tag>;
    if (status === 'ok') return <Tag color="green"><CheckCircleOutlined /> 正常</Tag>;
    if (status === 'warning') return <Tag color="orange"><WarningOutlined /> 警告</Tag>;
    return <Tag color="red"><CloseCircleOutlined /> 异常</Tag>;
  };

  const demoTaskId = stats?.demo_task?.task_id || 10;
  const walkthroughSteps = [
    { title: '任务负责人创建并配置任务', desc: '任务负责人创建标注任务，选择官方原题数据集，配置任务名称、任务类型、数据范围、标注员角色、审核员角色和任务状态。', path: '/owner/tasks', btn: '项目/任务总览' },
    { title: '任务负责人搭建标注模板', desc: '进入模板管理，基于任务专属模板配置 Schema。拖入画布、配置字段属性、设置校验规则与字段联动、预览渲染、Schema 校验通过后保存，并关联到当前任务。', path: '/owner/templates', btn: '模板管理' },
    { title: '任务负责人配置审核规则并发布任务', desc: '审核规则用于控制提交后的质检流转：是否启用 AI 预审、AI 分数阈值、低分自动打回、可疑样本进入人工复核、审核通过后数据入库等。配置完成后发布任务。', path: `/owner/tasks/${demoTaskId}`, btn: '审核规则 / 发布任务' },
    { title: '标注员领取任务并在线作答', desc: '标注员进入任务市场，筛选或搜索任务，查看任务详情，确认符合要求后领取任务。进入标注工作台后，查看原始数据、填写正式标注表单，可使用 LLM 辅助理解样本并获得 Rubric 对齐建议，也可以保存草稿。', path: '/labeler/tasks', btn: '任务市场 → 标注工作台' },
    { title: '标注员提交答案', desc: '标注员完成作答后提交答案，系统生成 submission 记录，并写入审计日志。提交后进入审核队列。', path: '/labeler/submissions', btn: '提交并继续标注 → 我的提交' },
    { title: 'AI 审核 Agent 自动预审', desc: 'AI Agent 对提交结果进行自动预审，输出结构化质量建议，包括总分、风险等级、置信度、维度评分和建议动作。AI 预审不直接替代人工审核，而是辅助分流。', path: '/owner/agent', btn: 'AI 审核 Agent → 预审记录' },
    { title: '人工审核员复核', desc: '审核员在审核队列中查看人工标注结果、AI 预审结果和多维度评分，根据审核规则做出通过、打回或复核决定。', path: '/reviewer/queue', btn: '审核队列 → 审核详情' },
    { title: '数据入库与多格式导出', desc: '通过审核的数据进入结果中心，可按 JSON、CSV、XLSX、JSONL 等格式导出，并通过审计日志追踪全链路操作。', path: `/owner/tasks/${demoTaskId}/results`, btn: '结果中心 → 导出管理 → 审计日志' },
  ];

  return (
    <div>
      {demoMode && (
        <Alert
          type="info"
          showIcon
          icon={<ExperimentOutlined />}
          message="演示模式已开启"
          description="当前为演示模式，页面会显示功能说明提示，不影响真实数据操作。"
          style={{ marginBottom: 16 }}
          closable={false}
        />
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}><DashboardOutlined /> LabelHub 仪表盘</h1>
        <Space>
          <span style={{ fontSize: 13, color: '#666' }}>演示模式</span>
          <Switch checked={demoMode} onChange={setDemoMode} checkedChildren="开" unCheckedChildren="关" />
          <Button icon={<ReloadOutlined />} onClick={fetchAll}>刷新</Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col span={3}><Card size="small"><Statistic title="项目数" value={safeNum(stats?.project_count)} prefix={<ProjectOutlined />} /></Card></Col>
          <Col span={3}><Card size="small"><Statistic title="任务数" value={safeNum(stats?.task_count)} prefix={<AppstoreOutlined />} valueStyle={{ color: '#1890ff' }} /></Card></Col>
          <Col span={3}><Card size="small"><Statistic title="数据总量" value={safeNum(stats?.total_items)} /></Card></Col>
          <Col span={3}><Card size="small"><Statistic title="已提交" value={safeNum(stats?.submitted_count)} valueStyle={{ color: '#1890ff' }} /></Card></Col>
          <Col span={3}><Card size="small"><Statistic title="已通过" value={safeNum(stats?.approved_count)} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} /></Card></Col>
          <Col span={3}><Card size="small"><Statistic title="可导出" value={safeNum(stats?.exportable_count)} prefix={<ExportOutlined />} valueStyle={{ color: '#13c2c2' }} /></Card></Col>
          <Col span={3}><Card size="small"><Statistic title={<Tooltip title="基于推荐 Demo 任务 annotations.json 统计">AI 预审数 <InfoCircleOutlined style={{fontSize:10,color:'#999'}} /></Tooltip>} value={safeNum(stats?.ai_reviewed_count)} prefix={<RobotOutlined />} valueStyle={{ color: '#722ed1' }} /></Card></Col>
          <Col span={3}><Card size="small"><Statistic title="审计日志" value={safeNum(stats?.audit_log_count)} prefix={<AuditOutlined />} valueStyle={{ color: '#8c8c8c' }} /></Card></Col>
        </Row>

        <Card title={<span><SafetyCertificateOutlined /> AI 审核与质量概览</span>} style={{ marginBottom: 16 }} size="small"
          extra={<Tooltip title="基于主演示任务 #10 的聚合数据"><InfoCircleOutlined style={{ color: '#999' }} /></Tooltip>}
        >
          {quality ? (
            <Row gutter={[16, 16]}>
              <Col span={4}>
                <Statistic title="AI 平均分" value={quality.ai_avg_score ?? '-'} suffix={quality.ai_avg_score != null ? '/ 100' : ''}
                  valueStyle={{ color: quality.ai_avg_score != null ? (quality.ai_avg_score >= 80 ? '#52c41a' : '#fa8c16') : '#999' }} />
              </Col>
              <Col span={5}>
                <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>AI 风险分布</div>
                <Space size={4}>
                  <Tag color="green">低 {safeNum(quality.ai_risk_distribution?.low)}</Tag>
                  <Tag color="orange">中 {safeNum(quality.ai_risk_distribution?.medium)}</Tag>
                  <Tag color="red">高 {safeNum(quality.ai_risk_distribution?.high)}</Tag>
                </Space>
              </Col>
              <Col span={4}>
                <Statistic title="AI/人工一致率" value={safePct(quality.ai_human_agreement_rate)} valueStyle={{ color: '#52c41a' }} />
              </Col>
              <Col span={4}>
                <Statistic title="人工通过率" value={safePct(quality.human_pass_rate)} valueStyle={{ color: '#52c41a' }} />
              </Col>
              <Col span={4}>
                <Statistic title="重点复核" value={safeNum(quality.priority_review_count)} prefix={<WarningOutlined />}
                  valueStyle={{ color: quality.priority_review_count > 0 ? '#fa8c16' : '#52c41a' }} />
              </Col>
              <Col span={3}>
                <Statistic title="高争议 Rubric" value={safeNum(quality.high_dispute_rubric_count)} prefix={<BugOutlined />}
                  valueStyle={{ color: quality.high_dispute_rubric_count > 0 ? '#ff4d4f' : '#52c41a' }} />
              </Col>
            </Row>
          ) : (
            <Empty description="暂无质量数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
          <div style={{ marginTop: 8, fontSize: 11, color: '#999', borderTop: '1px solid #f0f0f0', paddingTop: 6 }}>
            统计口径：基于主演示任务 #10 聚合 | AI/人工一致率基于同时存在 AI 和人工审核结果的数据 | 重点复核为低分、高风险、AI/人工不一致、曾被打回的数据
          </div>
        </Card>

        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={14}>
            <Card title={<span><ThunderboltOutlined /> 最近业务动态</span>} size="small" style={{ height: '100%' }}
              extra={<Button size="small" onClick={() => navigate('/owner/audit-logs')}>查看全部</Button>}
            >
              {activities.length > 0 ? (
                <div style={{ maxHeight: 320, overflow: 'auto' }}>
                  {activities.map((act, idx) => (
                    <div key={act.id || idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: idx < activities.length - 1 ? '1px solid #f5f5f5' : 'none' }}>
                      <Space size={8}>
                        <Tag color={getAuditActionColor(act.action)} style={{ fontSize: 11, margin: 0 }}>
                          {getAuditActionText(act.action)}
                        </Tag>
                        <span style={{ fontSize: 13, color: '#333' }}>{act.message || `${act.action_label || act.action} #${act.target_id || ''}`}</span>
                      </Space>
                      <span style={{ fontSize: 12, color: '#999', whiteSpace: 'nowrap' }}>
                        {act.created_at ? formatDateTimeShort(act.created_at) : ''}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty description="暂无业务动态" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>
          </Col>
          <Col span={10}>
            <Card title="快速入口" size="small" style={{ height: '100%' }}>
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 13, color: '#1890ff' }}>任务负责人</div>
                <Space wrap size={4}>
                  <Button size="small" onClick={() => navigate('/owner/tasks')}>项目/任务总览</Button>
                  <Button size="small" onClick={() => navigate('/owner/templates')}>模板管理</Button>
                  <Button size="small" onClick={() => navigate(`/owner/tasks/${demoTaskId}`)}>审核规则配置</Button>
                  <Button size="small" onClick={() => navigate(`/owner/tasks/${demoTaskId}/results`)}>结果中心</Button>
                  <Button size="small" onClick={() => navigate('/owner/exports')}>导出管理</Button>
                </Space>
              </div>
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 13, color: '#52c41a' }}>标注员</div>
                <Space wrap size={4}>
                  <Button size="small" onClick={() => navigate('/labeler/tasks')}>任务市场</Button>
                  <Button size="small" onClick={() => navigate('/labeler/workbench')}>标注工作台</Button>
                  <Button size="small" onClick={() => navigate('/labeler/submissions')}>我的提交</Button>
                  <Button size="small" onClick={() => navigate('/labeler/reports')}>工时报表</Button>
                </Space>
              </div>
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 13, color: '#722ed1' }}>AI 审核 Agent</div>
                <Space wrap size={4}>
                  <Button size="small" onClick={() => navigate('/owner/agent')}>Agent 配置</Button>
                  <Button size="small" onClick={() => navigate('/owner/agent')}>预审记录</Button>
                  <Button size="small" onClick={() => navigate(`/owner/tasks/${demoTaskId}/results`)}>风险分布</Button>
                  <Button size="small" onClick={() => navigate(`/owner/tasks/${demoTaskId}/results`)}>维度评分</Button>
                </Space>
              </div>
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 13, color: '#fa8c16' }}>人工审核员</div>
                <Space wrap size={4}>
                  <Button size="small" onClick={() => navigate('/reviewer/queue')}>审核队列</Button>
                  <Button size="small" onClick={() => navigate('/reviewer/queue')}>审核详情</Button>
                  <Button size="small" onClick={() => navigate('/reviewer/queue')}>打回返修</Button>
                  <Button size="small" onClick={() => navigate('/owner/audit-logs')}>审计日志</Button>
                </Space>
              </div>
              <div>
                <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 13, color: '#13c2c2' }}>数据落地</div>
                <Space wrap size={4}>
                  <Button size="small" onClick={() => navigate(`/owner/tasks/${demoTaskId}/results`)}>结果中心</Button>
                  <Button size="small" onClick={() => navigate('/owner/exports')}>导出管理</Button>
                  <Button size="small" onClick={() => navigate('/owner/exports')}>多格式导出</Button>
                  <Button size="small" onClick={() => navigate('/owner/audit-logs')}>审计追踪</Button>
                </Space>
              </div>
            </Card>
          </Col>
        </Row>

        {stats?.demo_task && (
          <Card title={<span><PlayCircleOutlined /> 推荐演示任务</span>} style={{ marginBottom: 16 }} size="small"
            extra={<Tag color="blue">主演示任务 #10</Tag>}
          >
            <Descriptions column={4} size="small" title={<span style={{ fontSize: 13 }}>主线：任务 #10 官方原题·问答质量标注</span>}>
              <Descriptions.Item label="任务 ID">#{stats.demo_task.task_id}</Descriptions.Item>
              <Descriptions.Item label="任务名称">{stats.demo_task.task_name || '官方原题·问答质量标注'}</Descriptions.Item>
              <Descriptions.Item label="模板">{stats.demo_task.template_name || '任务10-官方原题·问答质量标注-模板'}</Descriptions.Item>
              <Descriptions.Item label="审核规则"><Tag color="purple">AI 预审 + 人工复核 + 通过后入库</Tag></Descriptions.Item>
              <Descriptions.Item label="数据量">{safeNum(stats.demo_task.total_items)}</Descriptions.Item>
              <Descriptions.Item label="已提交">{safeNum(stats.demo_task.submitted_count)}</Descriptions.Item>
              <Descriptions.Item label="AI 预审">{safeNum(stats.demo_task.ai_reviewed_count)}</Descriptions.Item>
              <Descriptions.Item label="可导出">{safeNum(stats.demo_task.exportable_count)}</Descriptions.Item>
            </Descriptions>
            <div style={{ marginTop: 6, fontSize: 12, color: '#666', marginBottom: 8 }}>
              主线理由：覆盖官方流程中的任务配置、模板搭建、标注作答、LLM 辅助、AI 自动预审、人工审核、数据导出全链路。
            </div>
            <Divider style={{ margin: '8px 0' }} />
            <Descriptions column={4} size="small" title={<span style={{ fontSize: 13 }}>次演示：任务 #11 官方原题·偏好对比标注</span>}>
              <Descriptions.Item label="任务 ID">#11</Descriptions.Item>
              <Descriptions.Item label="任务名称">官方原题·偏好对比标注</Descriptions.Item>
              <Descriptions.Item label="类型"><Tag>偏好对比 / preference_compare_raw</Tag></Descriptions.Item>
              <Descriptions.Item label="用途">展示 A/B 回答偏好比较场景</Descriptions.Item>
            </Descriptions>
            <div style={{ marginTop: 8 }}>
              <Space>
                <Button type="primary" size="small" onClick={() => navigate(`/owner/tasks/${demoTaskId}`)}>进入任务详情</Button>
                <Button size="small" onClick={() => navigate(`/owner/tasks/${demoTaskId}/results`)}>进入结果中心</Button>
                <Button size="small" onClick={() => navigate('/reviewer/queue')}>进入审核队列</Button>
                <Button size="small" onClick={() => navigate('/labeler/tasks')}>标注员领取任务</Button>
              </Space>
            </div>
          </Card>
        )}

        <Card title={<span><PlayCircleOutlined /> 评审演示路径</span>} style={{ marginBottom: 16 }} size="small"
          extra={<Tag color="purple">Demo Walkthrough</Tag>}
        >
          <Steps direction="vertical" size="small" current={-1} items={walkthroughSteps.map((step, idx) => ({
            title: <span style={{ fontSize: 13 }}>Step {idx + 1}：{step.title}</span>,
            description: (
              <div style={{ fontSize: 12, color: '#666' }}>
                <div>{step.desc}</div>
                <Button type="link" size="small" style={{ padding: 0, marginTop: 4 }} onClick={() => navigate(step.path)}>{step.btn} →</Button>
              </div>
            ),
          }))} />
        </Card>

        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={12}>
            <Card title={<span><CloudServerOutlined /> 系统健康检查</span>} size="small"
              extra={<Button size="small" icon={<ReloadOutlined />} loading={healthLoading} onClick={refreshHealth}>刷新检查</Button>}
            >
              {health ? (
                <div>
                  <Row gutter={[8, 8]}>
                    <Col span={12}>
                      <div style={{ marginBottom: 8, fontSize: 12, color: '#666' }}>后端 API</div>
                      {healthStatusTag(health.api?.status)}
                    </Col>
                    <Col span={12}>
                      <div style={{ marginBottom: 8, fontSize: 12, color: '#666' }}>数据库连接</div>
                      {healthStatusTag(health.database?.status)}
                    </Col>
                  </Row>
                  <Divider style={{ margin: '12px 0' }} />
                  <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>Demo 数据状态</div>
                  <Space wrap size={4}>
                    {Object.entries(health.demo_data || {}).map(([key, val]) => {
                      const labels: Record<string, string> = {
                        has_task: '任务', has_dataset_item: '数据项', has_template: '模板',
                        has_submission: '提交', has_ai_review_run: 'AI 预审', has_review: '审核',
                        has_export_record: '导出记录', has_audit_log: '审计日志',
                      };
                      return <Tag key={key} color={val ? 'green' : 'red'} style={{ fontSize: 11 }}>{labels[key] || key} {val ? '✓' : '✗'}</Tag>;
                    })}
                  </Space>
                  <Divider style={{ margin: '12px 0' }} />
                  <Row gutter={[8, 8]}>
                    <Col span={12}>
                      <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>AI 预审服务</div>
                      {healthStatusTag(health.ai_precheck?.status)}
                      <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                        模式：{health.ai_precheck?.mode || '-'} | 模型：{health.ai_precheck?.model || '-'}
                      </div>
                    </Col>
                    <Col span={12}>
                      <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>导出服务</div>
                      <Space wrap size={4}>
                        {Object.entries(health.export_formats || {}).map(([fmt, info]) => (
                          <Tag key={fmt} color={info.available ? 'green' : 'default'} style={{ fontSize: 11 }}>
                            {fmt.toUpperCase()} {info.available ? '✓' : '待支持'}
                          </Tag>
                        ))}
                      </Space>
                    </Col>
                  </Row>
                </div>
              ) : (
                <Empty description="暂无健康检查数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>
          </Col>
          <Col span={12}>
            <Card title={<span><FileTextOutlined /> Demo 数据说明</span>} size="small"
              extra={<Tag color="blue">官方原题数据标注与 AI 审核流转</Tag>}
            >
              <div style={{ fontSize: 13, lineHeight: 1.8 }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>当前 Demo 场景：官方原题数据标注与 AI 审核流转</div>
                <div style={{ color: '#666', marginBottom: 8 }}>
                  LabelHub 当前演示覆盖官方参考流程：任务负责人创建任务、搭建任务专属标注模板、配置审核规则并发布任务；标注员在任务市场领取任务并在线作答；AI 审核 Agent 在提交后自动预审并输出多维度评分；人工审核员根据 AI 结果和标注内容进行复核；最终通过的数据进入结果中心并支持多格式导出。
                </div>

                <div style={{ fontWeight: 600, marginBottom: 4 }}>官方流程五段角色链路</div>
                <div style={{ color: '#666', fontSize: 12, marginBottom: 8 }}>
                  <div>1. 任务负责人：创建任务 → 搭建标注模板 → 配置审核规则 → 发布任务</div>
                  <div>2. 标注员：任务广场筛选/查看任务 → 领取任务 → 在线作答 → LLM 辅助 → 草稿保存 → 提交答案 → 我的贡献</div>
                  <div>3. AI 审核 Agent：提交后自动预审 → 多维度评分 → 综合判定</div>
                  <div>4. 人工审核员：根据 AI 预审结果和标注答案进行多角色审核 → 通过或打回</div>
                  <div>5. 数据落地：通过审核的数据入库 → 多格式导出</div>
                </div>

                <div style={{ fontWeight: 600, marginBottom: 4 }}>标注维度</div>
                <Space size={4} style={{ marginBottom: 8 }}>
                  <Tag color="blue">relevance 相关性</Tag>
                  <Tag color="green">accuracy 准确性</Tag>
                  <Tag color="orange">completeness 完整性</Tag>
                  <Tag color="red">safety 安全性</Tag>
                </Space>

                <div style={{ fontWeight: 600, marginBottom: 4 }}>角色说明</div>
                <div style={{ color: '#666', fontSize: 12, marginBottom: 8 }}>
                  <div>任务负责人：任务配置、模板搭建、审核规则配置、结果查看、导出、审计</div>
                  <div>标注员：领取数据、填写标注、使用 LLM 辅助、保存草稿、提交返修</div>
                  <div>AI 审核 Agent：提交后自动预审，多维度评分，综合判定，辅助分流</div>
                  <div>人工审核员：审核提交、对比 AI 结果、通过或打回</div>
                </div>

                <div style={{ fontWeight: 600, marginBottom: 4 }}>AI Agent</div>
                <div style={{ color: '#666', fontSize: 12 }}>
                  AI 审核 Agent 在标注员提交后自动执行预审，输出结构化质量建议，包括总分、风险等级、置信度、维度评分和建议动作。AI 预审不直接替代人工审核，而是辅助分流。当前使用 Mock 模式保证演示稳定。
                </div>
              </div>
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  );
};

export default OwnerDashboard;
