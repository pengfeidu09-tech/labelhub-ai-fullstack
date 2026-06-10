import React, { useEffect, useState } from 'react';
import {
  Card,
  Form,
  Input,
  Switch,
  Select,
  InputNumber,
  Button,
  message,
  Space,
  Tag,
  Descriptions,
  Alert,
  Divider,
  Spin,
  Row,
  Col,
  Table,
  Statistic,
  Modal,
} from 'antd';
import {
  CheckCircleTwoTone,
  CloseCircleTwoTone,
  ApiOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { formatDateTime } from '../../utils/time';
import { formatProblemLabel } from '../../utils/problemLabels';
import {
  getAIProviderConfig,
  saveAIProviderConfig,
  testAIProvider,
  listAIRuns,
  getAIRun,
  getAIRunStats,
  AIProviderConfig,
  ProviderTestResult,
  AIRunListItem,
  AIRunDetail,
  AIRunStats,
} from '../../api/agent';

const { Option } = Select;

const AI_ERROR_MAP: Record<string, { short: string; detail: string; suggestion: string }> = {
  dependency_missing: { short: '缺少后端依赖', detail: '后端缺少必要依赖库，真实模型请求未发出。', suggestion: '请在后端环境执行 pip install requests 并重启服务。' },
  invalid_api_key: { short: 'API Key 无效', detail: 'API Key 无效或已过期，鉴权失败。', suggestion: '请在 backend/.env 中重新配置 DASHSCOPE_API_KEY。' },
  model_not_found: { short: '模型不可用', detail: '模型名称不可用，请确认模型名是否正确。', suggestion: '请确认模型名是否为 qwen3.7-plus，或更换其他可用模型。' },
  bad_request: { short: '请求参数错误', detail: '请求参数不正确，请检查模型名、Base URL 和请求体。', suggestion: '请检查 AI 模型配置中的 Base URL 和模型名称。' },
  timeout: { short: '请求超时', detail: '模型接口请求超时，未在规定时间内返回结果。', suggestion: '请稍后重试，或在 AI 模型配置中调大超时时间。' },
  network_error: { short: '网络请求失败', detail: '网络请求失败，无法连接到模型接口。', suggestion: '请检查本机网络和 DashScope 接口地址。' },
  json_parse_error: { short: 'JSON 解析失败', detail: '模型返回内容不是合法 JSON，系统已尝试解析但失败。', suggestion: '可尝试开启 AI_FORCE_JSON 或调整 prompt。' },
  missing_api_key: { short: 'API Key 未配置', detail: 'API Key 未配置，真实模型请求无法发出。', suggestion: '请在 backend/.env 中配置 DASHSCOPE_API_KEY。' },
  rate_limited: { short: 'API 限流', detail: '模型接口调用频率超限。', suggestion: '请稍后重试。' },
  server_error: { short: '服务端错误', detail: '模型服务端返回错误。', suggestion: '请稍后重试，或联系模型服务商。' },
  unknown_error: { short: '未知错误', detail: '发生未知错误。', suggestion: '请查看运行详情中的原始错误信息。' },
};

const formatAiError = (errorType?: string | null): string => {
  if (!errorType) return '未知错误';
  return AI_ERROR_MAP[errorType]?.short || errorType;
};

// 问题标签中文映射
// 状态中文映射
// 触发方式中文映射
const TRIGGER_LABELS: Record<string, string> = {
  auto_on_submit: '提交自动',
  labeler_assist: '标注辅助',
  labeler_assist_manual: '标注辅助',
  labeler_assist_on_open: '打开自动',
  manual_retry: '手动重试',
  manual_run: '手动执行',
  manual_review_run: '手动审核',
  legacy_unknown: '旧数据',
};

// 触发方式筛选选项
const TRIGGER_FILTER_OPTIONS = [
  { value: '', label: '全部类型' },
  { value: 'auto_on_submit,manual_review_run', label: '正式审核' },
  { value: 'auto_on_submit', label: '提交自动' },
  { value: 'manual_review_run', label: '手动审核' },
  { value: 'labeler_assist_manual,labeler_assist_on_open', label: '标注辅助' },
  { value: 'legacy_unknown', label: '旧数据' },
];

const STATUS_LABELS: Record<string, string> = {
  success: '已完成', completed: '已完成',
  failed: '失败', fallback: '已兜底',
  pending: '待处理', running: '运行中',
  fallback_required: '需人工兜底',
};

// 风险等级中文映射
const RISK_LABELS: Record<string, string> = {
  low: '低风险', medium: '中风险', high: '高风险',
};

// 建议动作中文映射
const ACTION_LABELS: Record<string, string> = {
  submit: '建议通过', approve: '建议通过',
  reject: '建议返修', rework: '建议返修',
  manual_review: '建议人工审核', fallback_required: '需人工兜底',
};

const PROVIDER_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'mock', label: 'Mock（演示模式）' },
  { value: 'dashscope', label: 'DashScope（Qwen / 通义千问）' },
];

const STATUS_FILTER_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待处理' },
  { value: 'running', label: '运行中' },
  { value: 'success', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'fallback_required', label: '需人工兜底' },
];

const AgentPage: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [providerConfig, setProviderConfig] = useState<AIProviderConfig | null>(null);
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null);

  // 运行队列
  const [runs, setRuns] = useState<AIRunListItem[]>([]);
  const [runsTotal, setRunsTotal] = useState(0);
  const [runsPage, setRunsPage] = useState(1);
  const [runsStatus, setRunsStatus] = useState('');
  const [runsTriggerType, setRunsTriggerType] = useState('auto_on_submit,manual_review_run');
  const [runsLoading, setRunsLoading] = useState(false);
  const [stats, setStats] = useState<AIRunStats | null>(null);
  const [detailModal, setDetailModal] = useState<AIRunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const config = await getAIProviderConfig();
      setProviderConfig(config);
      form.setFieldsValue({
        provider: config.provider,
        model: config.model,
        base_url: config.base_url,
        timeout_seconds: config.timeout_seconds ?? 25,
        mock_fallback: !!config.mock_fallback,
        force_json: !!config.force_json,
      });
    } catch (err: any) {
      const status = err?.response?.status;
      const url = err?.config?.url || '/agent/provider-config';
      const method = (err?.config?.method || 'GET').toUpperCase();
      // 降级提示：不影响运行队列
      setProviderConfig(null);
      message.warning(`配置加载失败: ${method} ${url} ${status || err?.message || '未知错误'}，请刷新`);
    } finally {
      setLoading(false);
    }
  };

  const loadRuns = async (page?: number, status?: string, triggerType?: string) => {
    setRunsLoading(true);
    try {
      const p = page ?? runsPage;
      const s = status !== undefined ? status : runsStatus;
      const tt = triggerType !== undefined ? triggerType : runsTriggerType;
      const res = await listAIRuns({
        status: s || undefined,
        trigger_type: tt || undefined,
        page: p,
        limit: 20,
      });
      setRuns(res.items || []);
      setRunsTotal(res.total);
      setRunsPage(p);
    } catch {
      setRuns([]);
      setRunsTotal(0);
    } finally {
      setRunsLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const s = await getAIRunStats();
      setStats(s);
    } catch {
      setStats(null);
    }
  };

  const loadDetail = async (runId: number) => {
    setDetailLoading(true);
    try {
      const d = await getAIRun(runId);
      setDetailModal(d);
    } catch {
      message.warning('加载详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    loadConfig();
    loadRuns(1, '', 'auto_on_submit,manual_review_run');
    loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSave = async () => {
    const values = await form.validateFields();
    setLoading(true);
    try {
      const saved = await saveAIProviderConfig(values);
      setProviderConfig(saved);
      form.setFieldsValue({
        provider: saved.provider,
        model: saved.model,
        base_url: saved.base_url,
        timeout_seconds: saved.timeout_seconds ?? 25,
        mock_fallback: !!saved.mock_fallback,
        force_json: !!saved.force_json,
      });
      message.success('配置已保存');
      await loadConfig();
    } catch (err: any) {
      message.error(`保存失败: ${err?.response?.data?.detail || err?.message || err}`);
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testAIProvider();
      setTestResult(result);
      if (result.test_status === 'success') {
        message.success('Provider 连接测试成功');
      } else {
        message.warning(`Provider 测试失败: ${result.error_type || 'unknown'}`);
      }
    } catch (err: any) {
      message.error(`测试请求失败: ${err?.message || err}`);
    } finally {
      setTesting(false);
    }
  };

  const handleStatusFilter = (value: string) => {
    setRunsStatus(value);
    loadRuns(1, value);
  };

  const handleTriggerTypeFilter = (value: string) => {
    setRunsTriggerType(value);
    loadRuns(1, undefined, value);
  };

  const renderTestResult = () => {
    if (testing) {
      return (
        <div style={{ marginTop: 12 }}>
          <Spin size="small" /> 正在调用 {testResult?.request_url || 'Provider'} ...
        </div>
      );
    }
    if (!testResult) return null;

    const isSuccess = testResult.test_status === 'success';
    const statusTag = isSuccess ? (
      <Tag icon={<CheckCircleTwoTone twoToneColor="#52c41a" />} color="success">success</Tag>
    ) : (
      <Tag icon={<CloseCircleTwoTone twoToneColor="#ff4d4f" />} color="error">failed</Tag>
    );

    return (
      <div style={{ marginTop: 12 }}>
        <Alert
          type={isSuccess ? 'success' : 'error'}
          showIcon
          message={
            <Space size="small">
              <span>测试结果：</span>
              {statusTag}
              {testResult.http_status ? <Tag color="blue">HTTP {testResult.http_status}</Tag> : null}
              {testResult.latency_ms !== undefined ? <Tag>{testResult.latency_ms} ms</Tag> : null}
            </Space>
          }
          description={
            <Descriptions size="small" column={1} bordered style={{ marginTop: 8 }}>
              <Descriptions.Item label="Provider">{testResult.provider}</Descriptions.Item>
              <Descriptions.Item label="Model">{testResult.model}</Descriptions.Item>
              <Descriptions.Item label="Base URL">{testResult.base_url || '(空)'}</Descriptions.Item>
              <Descriptions.Item label="Request URL">{testResult.request_url}</Descriptions.Item>
              <Descriptions.Item label="API Key">
                {testResult.api_key_present
                  ? `已配置 (长度 ${testResult.api_key_length})`
                  : '未配置'}
              </Descriptions.Item>
              {testResult.error_type ? (
                <Descriptions.Item label="错误类型">
                  <Tag color="red">{testResult.error_type}</Tag>
                </Descriptions.Item>
              ) : null}
              {testResult.error_message ? (
                <Descriptions.Item label="失败原因">
                  <span style={{ wordBreak: 'break-all' }}>{testResult.error_message}</span>
                </Descriptions.Item>
              ) : null}
              {testResult.raw_response_preview ? (
                <Descriptions.Item label="原始响应预览 (前 500 字符)">
                  <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 220, overflow: 'auto', margin: 0 }}>
                    {testResult.raw_response_preview}
                  </pre>
                </Descriptions.Item>
              ) : null}
              <Descriptions.Item label="Fallback 可用">
                {testResult.fallback_available ? '是' : '否'}
              </Descriptions.Item>
            </Descriptions>
          }
        />
      </div>
    );
  };

  const runColumns = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 60,
    },
    {
      title: 'Task/Item',
      width: 100,
      render: (_: any, r: AIRunListItem) => `${r.task_id || '-'}/${r.item_id || '-'}`,
    },
    {
      title: '触发方式',
      dataIndex: 'trigger_type',
      width: 110,
      render: (v: string | null) => {
        if (!v) return <Tag>默认</Tag>;
        const colors: Record<string, string> = {
          auto_on_submit: 'blue',
          labeler_assist: 'cyan',
          labeler_assist_manual: 'cyan',
          labeler_assist_on_open: 'cyan',
          manual_retry: 'orange',
          manual_run: 'purple',
          manual_review_run: 'blue',
          legacy_unknown: 'default',
        };
        return <Tag color={colors[v] || 'default'}>{TRIGGER_LABELS[v] || v}</Tag>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (s: string) => {
        const colors: Record<string, string> = {
          pending: 'default', running: 'processing', success: 'success',
          failed: 'error', fallback_required: 'warning',
        };
        const labels: Record<string, string> = {
          pending: '待处理', running: '运行中', success: '已完成',
          failed: '失败', fallback_required: '需人工兜底',
        };
        return <Tag color={colors[s] || 'default'}>{labels[s] || s}</Tag>;
      },
    },
    {
      title: 'AI 建议动作',
      dataIndex: 'suggestion_action',
      width: 100,
      render: (v: string | null) => {
        if (!v) return '-';
        const colors: Record<string, string> = { submit: 'green', approve: 'green', reject: 'red', rework: 'red', manual_review: 'orange', fallback_required: 'orange' };
        return <Tag color={colors[v] || 'default'}>{ACTION_LABELS[v] || v}</Tag>;
      },
    },
    {
      title: '风险等级',
      dataIndex: 'risk_level',
      width: 80,
      render: (v: string | null) => {
        if (!v) return '-';
        const c = v === 'low' ? 'green' : v === 'high' ? 'red' : 'orange';
        return <Tag color={c}>{RISK_LABELS[v] || v}</Tag>;
      },
    },
    {
      title: 'Fallback',
      dataIndex: 'used_fallback',
      width: 90,
      render: (v: boolean) => v ? <Tag color="orange">降级结果</Tag> : <Tag color="green">真实调用</Tag>,
    },
    {
      title: '耗时',
      dataIndex: 'latency_ms',
      width: 80,
      render: (v: number | null) => v != null ? `${v}ms` : '-',
    },
    {
      title: '错误',
      width: 160,
      render: (_: any, r: AIRunListItem) => {
        if (!r.error_type) return '-';
        const cnShort = formatAiError(r.error_type);
        return (
          <span title={r.error_message || ''} style={{ fontSize: 11, wordBreak: 'break-all' }}>
            <Tag color="red" style={{ fontSize: 10 }}>{cnShort}</Tag>
          </span>
        );
      },
    },
    {
      title: '操作',
      width: 60,
      render: (_: any, r: AIRunListItem) => (
        <Button size="small" type="link" onClick={() => loadDetail(r.id)}>详情</Button>
      ),
    },
  ];

  return (
    <div style={{ padding: 16 }}>
      <Card
        title={
          <Space>
            <SafetyCertificateOutlined />
            <span>AI 模型配置</span>
          </Space>
        }
        extra={
          <Button icon={<ReloadOutlined />} onClick={loadConfig} loading={loading}>
            刷新当前生效配置
          </Button>
        }
      >
        {/* 当前生效配置 */}
        <Alert
          type="info"
          showIcon
          icon={<ApiOutlined />}
          style={{ marginBottom: 16 }}
          message={
            <Space size="middle" wrap>
              <span>当前生效 Provider：<b>{providerConfig?.effective_provider || providerConfig?.provider || '-'}</b></span>
              <span>当前生效模型：<b>{providerConfig?.effective_model || providerConfig?.model || '-'}</b></span>
              <span>API Key 状态：
                {providerConfig?.api_key_present
                  ? <Tag color="green">已配置</Tag>
                  : <Tag color="orange">未配置</Tag>}
              </span>
              <span>Base URL：<code>{providerConfig?.base_url || '-'}</code></span>
            </Space>
          }
        />

        {providerConfig?.warning ? (
          <Alert type="warning" showIcon style={{ marginBottom: 16 }} message={providerConfig.warning} />
        ) : null}

        <Form
          form={form}
          layout="vertical"
          initialValues={{
            provider: 'mock',
            model: 'mock-v1.0',
            base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            timeout_seconds: 25,
            mock_fallback: true,
            force_json: true,
          }}
        >
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="provider" label="Provider" rules={[{ required: true }]}>
                <Select onChange={(v) => {
                  if (v === 'mock') {
                    form.setFieldsValue({ model: 'mock-v1.0' });
                  } else if (v === 'dashscope') {
                    form.setFieldsValue({
                      model: form.getFieldValue('model') || 'qwen3.7-plus',
                      base_url: form.getFieldValue('base_url') || 'https://dashscope.aliyuncs.com/compatible-mode/v1',
                    });
                  }
                }}>
                  {PROVIDER_OPTIONS.map(o => (
                    <Option key={o.value} value={o.value}>{o.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="model" label="模型名称" rules={[{ required: true }]}>
                <Select placeholder="选择或输入模型名称" showSearch>
                  <Option value="qwen3.7-plus">qwen3.7-plus（推荐）</Option>
                  <Option value="qwen-plus">qwen-plus</Option>
                  <Option value="qwen-turbo">qwen-turbo</Option>
                  <Option value="qwen-max">qwen-max</Option>
                  <Option value="qwen3.6-plus">qwen3.6-plus</Option>
                  <Option value="qwen3-plus">qwen3-plus</Option>
                  <Option value="qwen3-turbo">qwen3-turbo</Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="base_url"
            label="Base URL"
            tooltip="DashScope OpenAI 兼容接口：https://dashscope.aliyuncs.com/compatible-mode/v1"
            rules={[{ required: true }]}
          >
            <Input placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
          </Form.Item>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="timeout_seconds" label="超时(秒)">
                <InputNumber min={1} max={120} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="mock_fallback" label="真实失败时 mock 兜底" valuePropName="checked">
                <Switch checkedChildren="开启" unCheckedChildren="关闭" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="force_json" label="强制 JSON 输出" valuePropName="checked">
                <Switch checkedChildren="开启" unCheckedChildren="关闭" />
              </Form.Item>
            </Col>
          </Row>

          <Space>
            <Button type="primary" onClick={handleSave} loading={loading}>保存配置</Button>
            <Button icon={<ThunderboltOutlined />} onClick={handleTest} loading={testing}>测试连接</Button>
          </Space>
        </Form>

        <Divider />

        {renderTestResult()}
      </Card>

      {/* 统计卡片 */}
      <Card style={{ marginTop: 16 }} title="运行统计">
        {stats ? (
          <Row gutter={16}>
            <Col span={4}><Statistic title="待处理" value={stats.pending} /></Col>
            <Col span={4}><Statistic title="运行中" value={stats.running} /></Col>
            <Col span={4}><Statistic title="已完成" value={stats.success} /></Col>
            <Col span={4}><Statistic title="失败" value={stats.failed} valueStyle={{ color: '#ff4d4f' }} /></Col>
            <Col span={4}><Statistic title="需人工兜底" value={stats.fallback_required} valueStyle={{ color: '#fa8c16' }} /></Col>
            <Col span={4}><Statistic title="平均分" value={stats.avg_score ?? '-'} precision={1} /></Col>
            <Col span={4}><Statistic title="平均耗时" value={stats.avg_latency_ms ?? '-'} suffix="ms" /></Col>
            <Col span={4}><Statistic title="重试次数" value={stats.total_retries ?? 0} /></Col>
          </Row>
        ) : (
          <div style={{ color: '#999', fontSize: 12 }}>统计加载失败，请刷新</div>
        )}
      </Card>

      {/* 运行记录列表 */}
      <Card
        style={{ marginTop: 16 }}
        title="Agent 运行记录"
        extra={
          <Space>
            <Select
              value={runsTriggerType}
              onChange={handleTriggerTypeFilter}
              style={{ width: 140 }}
              size="small"
            >
              {TRIGGER_FILTER_OPTIONS.map(o => (
                <Option key={o.value} value={o.value}>{o.label}</Option>
              ))}
            </Select>
            <Select
              value={runsStatus}
              onChange={handleStatusFilter}
              style={{ width: 140 }}
              size="small"
            >
              {STATUS_FILTER_OPTIONS.map(o => (
                <Option key={o.value} value={o.value}>{o.label}</Option>
              ))}
            </Select>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => { loadRuns(); loadStats(); }}
              loading={runsLoading}
            >
              刷新
            </Button>
          </Space>
        }
      >
        <Table
          dataSource={runs}
          columns={runColumns}
          rowKey="id"
          loading={runsLoading}
          size="small"
          pagination={{
            current: runsPage,
            total: runsTotal,
            pageSize: 20,
            onChange: (p) => loadRuns(p),
            showTotal: (t) => `共 ${t} 条`,
          }}
          locale={{ emptyText: '暂无 AI 审核运行记录' }}
          scroll={{ x: 1100 }}
        />
      </Card>

      {/* 详情弹窗 */}
      <Modal
        title={`Run #${detailModal?.id || ''} 详情`}
        open={!!detailModal}
        onCancel={() => setDetailModal(null)}
        footer={null}
        width={720}
      >
        {detailLoading ? <Spin /> : detailModal ? (
          <>
          {detailModal.used_fallback ? (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message="降级结果"
              description="模型请求失败后使用兜底策略生成，仅用于演示/降级，不作为正式 AI 质检依据。"
            />
          ) : detailModal.status === 'success' ? (
            <Alert
              type="success"
              showIcon
              style={{ marginBottom: 12 }}
              message="真实模型调用"
            />
          ) : null}
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="ID">{detailModal.id}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={detailModal.status === 'success' ? 'green' : detailModal.status === 'failed' ? 'red' : 'default'}>
                {STATUS_LABELS[detailModal.status] || detailModal.status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Provider">{detailModal.model_provider || detailModal.provider}</Descriptions.Item>
            <Descriptions.Item label="Model">{detailModal.model_name}</Descriptions.Item>
            <Descriptions.Item label="触发方式">
              {detailModal.trigger_type ? (
                <Tag color={
                  detailModal.trigger_type === 'auto_on_submit' || detailModal.trigger_type === 'manual_review_run' ? 'blue' :
                  detailModal.trigger_type.startsWith('labeler_assist') ? 'cyan' :
                  'default'
                }>
                  {TRIGGER_LABELS[detailModal.trigger_type] || detailModal.trigger_type}
                </Tag>
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="AI 建议动作">
              {detailModal.suggestion_action ? (
                <Tag color={
                  detailModal.suggestion_action === 'submit' || detailModal.suggestion_action === 'approve' ? 'green' :
                  detailModal.suggestion_action === 'reject' || detailModal.suggestion_action === 'rework' ? 'red' :
                  'orange'
                }>
                  {ACTION_LABELS[detailModal.suggestion_action] || detailModal.suggestion_action}
                </Tag>
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="风险等级">
              {detailModal.risk_level ? (
                <Tag color={detailModal.risk_level === 'low' ? 'green' : detailModal.risk_level === 'high' ? 'red' : 'orange'}>
                  {RISK_LABELS[detailModal.risk_level] || detailModal.risk_level}
                </Tag>
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="置信度">{detailModal.confidence != null ? `${(detailModal.confidence * 100).toFixed(0)}%` : '-'}</Descriptions.Item>
            <Descriptions.Item label="Base URL" span={2}>
              <code>{detailModal.base_url || '-'}</code>
            </Descriptions.Item>
            <Descriptions.Item label="耗时">{detailModal.latency_ms != null ? `${detailModal.latency_ms}ms` : '-'}</Descriptions.Item>
            <Descriptions.Item label="重试次数">{detailModal.retry_count ?? 0}</Descriptions.Item>
            <Descriptions.Item label="Fallback">
              {detailModal.used_fallback ? (
                <div>
                  <Tag color="orange">降级结果 (mock 兜底)</Tag>
                  {detailModal.output_json?.fallback_reason && (
                    <div style={{ fontSize: 11, color: '#fa8c16', marginTop: 4 }}>
                      原因: {detailModal.output_json.fallback_reason}
                    </div>
                  )}
                  <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                    此结果由兜底策略生成，非真实模型输出
                  </div>
                </div>
              ) : (
                <span>否</span>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="Prompt 版本">{detailModal.prompt_version || '-'}</Descriptions.Item>
            {/* 输入快照 / raw_prompt — 预计算避免 Fragment 嵌套 */}
            {(() => {
              const snap = detailModal.input_snapshot_json;
              if (!snap) return null;
              const prompt = snap?.item_data?.prompt || snap?.item_data?.question || snap?.raw_prompt || null;
              const dsType = snap?.dataset_type || snap?.item_data?.dataset_type || null;
              const offId = snap?.official_id || snap?.item_data?.official_id || null;
              const prof = snap?.prompt_profile || null;
              const items: React.ReactNode[] = [];
              if (dsType || offId || prof) {
                items.push(
                  <Descriptions.Item key="snap-info" label="数据信息" span={2}>
                    <Space size={4}>
                      {dsType && <Tag color={dsType === 'preference_compare' ? 'purple' : 'cyan'} style={{ fontSize: 11 }}>{dsType}</Tag>}
                      {offId && <Tag color="blue" style={{ fontSize: 11 }}>ID: {offId}</Tag>}
                      {prof && <Tag color="geekblue" style={{ fontSize: 11 }}>{prof}</Tag>}
                    </Space>
                  </Descriptions.Item>
                );
              }
              if (prompt) {
                items.push(
                  <Descriptions.Item key="snap-prompt" label="原始 Prompt" span={2}>
                    <details>
                      <summary style={{ cursor: 'pointer', color: '#999' }}>点击查看 (前 500 字符)</summary>
                      <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: '4px 0 0 0', maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                        {typeof prompt === 'string' ? prompt.substring(0, 500) : JSON.stringify(prompt, null, 2).substring(0, 500)}
                      </pre>
                    </details>
                  </Descriptions.Item>
                );
              }
              return items;
            })()}
            {/* 摘要信息 — 预计算避免 Fragment 嵌套 */}
            {(() => {
              const out = detailModal.output_json;
              if (!out) return null;
              const isPrefCompare = out.preferred !== undefined || detailModal.input_snapshot_json?.dataset_type === 'preference_compare';
              const dims = out.dimension_scores || out.dimensions || {};
              const problems = out.problems || out.issues || [];
              const issueTags = out.issue_tags || out.problem_tags || [];
              const items: React.ReactNode[] = [];
              if (out.summary) {
                items.push(<Descriptions.Item key="out-summary" label="总结" span={2}>{out.summary}</Descriptions.Item>);
              }
              if (isPrefCompare && (out.preferred || out.margin)) {
                items.push(
                  <Descriptions.Item key="out-pref" label="偏好评估" span={2}>
                    <Space size={4}>
                      {out.preferred && <Tag color={out.preferred === 'A' ? 'blue' : out.preferred === 'B' ? 'orange' : 'default'} style={{ fontSize: 11 }}>preferred: {out.preferred}</Tag>}
                      {out.margin && <Tag color="green" style={{ fontSize: 11 }}>margin: {out.margin}</Tag>}
                      {out.safety_flag != null && <Tag color={out.safety_flag ? 'red' : 'green'} style={{ fontSize: 11 }}>safety: {out.safety_flag ? '是' : '否'}</Tag>}
                    </Space>
                    {Array.isArray(dims) && dims.length > 0 && (
                      <div style={{ marginTop: 4 }}>
                        {dims.map((d: string, i: number) => <Tag key={i} color="blue" style={{ fontSize: 11 }}>{d}</Tag>)}
                      </div>
                    )}
                  </Descriptions.Item>
                );
              }
              if (!isPrefCompare && typeof dims === 'object' && !Array.isArray(dims) && Object.keys(dims).length > 0) {
                items.push(
                  <Descriptions.Item key="out-dims" label="维度评估" span={2}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {Object.entries(dims).map(([key, val]: [string, any]) => (
                        <Tag key={key} color="blue" style={{ fontSize: 11 }}>
                          {key}: {typeof val === 'object' ? val.label || val.value || `${val.score}分` : String(val)}
                        </Tag>
                      ))}
                    </div>
                  </Descriptions.Item>
                );
              }
              if (issueTags.length > 0) {
                items.push(
                  <Descriptions.Item key="out-tags" label="问题标签" span={2}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {issueTags.map((tag: string, i: number) => (
                        <Tag key={i} color="orange" style={{ fontSize: 11 }} title={tag}>
                          {formatProblemLabel(tag)}
                        </Tag>
                      ))}
                    </div>
                  </Descriptions.Item>
                );
              }
              if (problems.length > 0) {
                items.push(
                  <Descriptions.Item key="out-problems" label="主要问题" span={2}>
                    {problems.slice(0, 5).map((p: any, i: number) => (
                      <div key={i} style={{ fontSize: 12, marginBottom: 2 }}>
                        <Tag color={p.severity === 'high' ? 'red' : 'orange'} style={{ fontSize: 10 }}>
                          {formatProblemLabel(p.field)}
                        </Tag>
                        {p.message || ''}
                      </div>
                    ))}
                    {problems.length > 5 && <div style={{ color: '#999', fontSize: 11 }}>...共 {problems.length} 个问题</div>}
                  </Descriptions.Item>
                );
              }
              if (out.suggestions && out.suggestions.length > 0) {
                items.push(
                  <Descriptions.Item key="out-suggest" label="处理建议" span={2}>
                    {out.suggestions.map((s: string, i: number) => (
                      <div key={i} style={{ fontSize: 12, color: '#1890ff' }}>💡 {s}</div>
                    ))}
                  </Descriptions.Item>
                );
              }
              return items;
            })()}
            {/* 错误信息 — 预计算避免 Fragment 嵌套 */}
            {detailModal.error_type ? [
              <Descriptions.Item key="err-type" label="错误类型" span={2}>
                <Tag color="red">{formatAiError(detailModal.error_type)}</Tag>
                <span style={{ color: '#999', fontSize: 11, marginLeft: 8 }}>({detailModal.error_type})</span>
              </Descriptions.Item>,
              <Descriptions.Item key="err-desc" label="错误说明" span={2}>
                {AI_ERROR_MAP[detailModal.error_type]?.detail || '未知错误'}
              </Descriptions.Item>,
              <Descriptions.Item key="err-suggest" label="处理建议" span={2}>
                <span style={{ color: '#1890ff' }}>{AI_ERROR_MAP[detailModal.error_type]?.suggestion || '请查看原始错误信息。'}</span>
              </Descriptions.Item>,
            ] : null}
            {detailModal.error_message ? (
              <Descriptions.Item label="原始错误" span={2}>
                <details>
                  <summary style={{ cursor: 'pointer', color: '#999' }}>点击展开</summary>
                  <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: '4px 0 0 0', maxHeight: 200, overflow: 'auto' }}>
                    {detailModal.error_message}
                  </pre>
                </details>
              </Descriptions.Item>
            ) : null}
            {/* Debug 调试区 */}
            <Descriptions.Item label="Debug 调试区" span={2}>
              <details>
                <summary style={{ cursor: 'pointer', color: '#999' }}>点击展开调试信息</summary>
                <div style={{ marginTop: 8 }}>
                  <div style={{ marginBottom: 4 }}><b>debug_score:</b> {detailModal.score ?? '-'}</div>
                  <div style={{ marginBottom: 4 }}><b>confidence:</b> {detailModal.confidence ?? '-'}</div>
                  {detailModal.raw_response_preview && (
                    <div style={{ marginBottom: 4 }}>
                      <b>raw_response_preview:</b>
                      <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: '4px 0 0 0', maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                        {detailModal.raw_response_preview}
                      </pre>
                    </div>
                  )}
                  {detailModal.output_json && (
                    <div style={{ marginBottom: 4 }}>
                      <b>output_json:</b>
                      <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: '4px 0 0 0', maxHeight: 300, overflow: 'auto', fontSize: 12 }}>
                        {JSON.stringify(detailModal.output_json, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </details>
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">{detailModal.created_at ? formatDateTime(detailModal.created_at) : '-'}</Descriptions.Item>
            <Descriptions.Item label="更新时间">{detailModal.updated_at ? formatDateTime(detailModal.updated_at) : '-'}</Descriptions.Item>
          </Descriptions>
          </>
        ) : null}
      </Modal>

      <Card style={{ marginTop: 16 }} title="使用说明">
        <ul style={{ marginBottom: 0, paddingLeft: 18 }}>
          <li>API Key 只能通过 <code>backend/.env</code> 中 <code>DASHSCOPE_API_KEY</code> / <code>LLM_API_KEY</code> 设置，不会在页面回显。</li>
          <li>DashScope OpenAI 兼容接口：<code>POST {`{base_url}`}/chat/completions</code>，请求体不包含 <code>response_format</code>，靠 system prompt 约束 JSON 输出。</li>
          <li>当 <code>AI_MOCK_FALLBACK=false</code> 时，真实模型失败不会兜底，前端会展示真实失败原因。</li>
          <li>"测试连接"仅做连通性测试，失败时不会回退到 mock，便于排查错误。</li>
        </ul>
      </Card>
    </div>
  );
};

export default AgentPage;
