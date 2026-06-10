import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Button, Tag, Empty, Spin, message, Modal, Alert, Drawer, Timeline, Tooltip, Collapse, Input, Radio, Tabs } from 'antd';
import { saveDraft, submitAnnotation, getLabelerForm, getLabelerItems, claimNext, resetDemoData, seedMoreItems, aiPrecheck, getLatestAssist, openWorkbenchSession, getCurrentSession, heartbeatSession, closeWorkbenchSession, submitWorkbenchSession, getWorkbenchLogs, markItemInvalid, skipItem, saveDraftVersion, getDraftVersions, getElapsed, formatDuration } from '../../api/labeler';
import { formatDateTime } from '../../utils/time';

import FormRenderer from '../../components/renderer/FormRenderer';
import type { TemplateSchema } from '../../types/template';
import { resolveEffectiveAiAssistConfig, canRunLabelerAssist } from '../../utils/aiAssistConfig';
import type { AiAssistConfig } from '../../utils/aiAssistConfig';
import { PauseCircleOutlined, PlayCircleOutlined, PlusCircleOutlined, RightOutlined, FileTextOutlined, ExclamationCircleOutlined, RobotOutlined, FullscreenOutlined, FullscreenExitOutlined, ArrowLeftOutlined, StopOutlined, ForwardOutlined, WarningOutlined, HistoryOutlined } from '@ant-design/icons';

const { TextArea } = Input;
const STORAGE_KEY_CURRENT_ITEM = 'labelhub_current_item_id';

// ── Performance Safe Mode & Binary Search Toggles ──
const WORKBENCH_SAFE_MODE = true;
// Core features — always safe (no perf impact)
const ENABLE_TOP_TIMER = true;
const ENABLE_RAW_DATA_VIEW = true;
const ENABLE_BASIC_FORM = true;
// LLM assist — button only, no auto-run
const ENABLE_LLM_ASSIST_BUTTON = true;
const ENABLE_SIMPLE_LLM_RESULT_PANEL = true;
// Heavy panels — disabled in safe mode
const ENABLE_RIGHT_RUBRIC_PANEL = true;
const ENABLE_RIGHT_PANEL = WORKBENCH_SAFE_MODE ? false : true;
const ENABLE_AUDIT_LOG_PANEL = !WORKBENCH_SAFE_MODE;
const ENABLE_AUTOSAVE = false;
const ENABLE_LOCAL_DRAFT = !WORKBENCH_SAFE_MODE;
const ENABLE_OPERATION_LOG = !WORKBENCH_SAFE_MODE;

// ── Performance counters (dev mode only) ──
const _perfCounters = {
  workbenchRender: 0, formChange: 0, saveDraft: 0,
  fetchForm: 0, fetchAuditLogs: 0, lastLogTime: Date.now(),
};
if (import.meta.env.DEV) {
  setInterval(() => {
    const now = Date.now();
    if (now - _perfCounters.lastLogTime >= 5000) {
      const c = { ..._perfCounters };
      if (c.workbenchRender > 50) console.warn('[Perf] Workbench excessive renders:', c.workbenchRender, 'in 5s');
      if (c.formChange > 50) console.warn('[Perf] FormChange excessive:', c.formChange, 'in 5s');
      console.log('[Perf] 5s summary:', { renders: c.workbenchRender, formChanges: c.formChange, saves: c.saveDraft, fetchForms: c.fetchForm, fetchLogs: c.fetchAuditLogs });
      Object.keys(_perfCounters).forEach(k => { if (k !== 'lastLogTime') (_perfCounters as any)[k] = 0; });
      _perfCounters.lastLogTime = now;
    }
  }, 5000);
}



interface OperationLog {
  id: number;
  action: string;
  action_label?: string;
  task_id?: number;
  item_id?: number;
  work_key?: string;
  message?: string;
  payload_json?: any;
  after_data?: any;
  extra_info?: any;
  created_at: string;
}

interface DatasetItem {
  id: number;
  task_id: number;
  dataset_item_id?: number;
  raw_data_json: any;
  status: string;
  draft_data?: any;
  claimed_by?: number;
  created_at: string;
  updated_at: string;
  effectiveStatus?: string;
  annotation_status?: string;
  task_name?: string;
  work_key?: string;
  full_work_key?: string;
  work_status?: string;
  mode?: string;
  is_rework?: boolean;
  review_reason?: string;
  review_time?: string;
  reviewer_id?: string;
  submission_id?: number;
  annotation_id?: number;
  annotation_result?: any;
  duration_seconds?: number;
}

interface SubmissionRecord {
  id: number;
  task_id: number;
  dataset_item_id: number;
  status: string;
  result?: any;
  data?: any;
  label_data?: any;
  submission_data?: any;
  rejected_reason?: string;
  review_info?: any;
  created_at?: string;
  updated_at?: string;
}

interface RubricItem {
  id: number;
  dimension: string;
  dimensionLabel: string;
  type: 'Objective' | 'Subjective';
  necessity: 'Explicit' | 'Implicit';
  priority: 'Must have' | 'Nice to have';
  criterion: string;
  fieldKey: string;
  aiJudgement?: string | null;
  aiEvidence?: string[];
}

interface VersionRecord {
  id: number;
  version_no: number;
  version_type?: string;
  version_type_text?: string;
  operator_role?: string;
  created_at: string;
  summary?: string;
  snapshot_json?: any;
  task_id?: number;
  item_id?: number;
  labeler_id?: number;
  work_key?: string;
}

const DIMENSION_MAP: Record<string, { label: string; type: 'Objective' | 'Subjective'; necessity: 'Explicit' | 'Implicit'; priority: 'Must have' | 'Nice to have' }> = {
  relevance: { label: 'Instruction Following', type: 'Objective', necessity: 'Explicit', priority: 'Must have' },
  accuracy: { label: 'Accuracy', type: 'Objective', necessity: 'Explicit', priority: 'Must have' },
  completeness: { label: 'Completeness', type: 'Subjective', necessity: 'Implicit', priority: 'Nice to have' },
  safety: { label: 'Safety', type: 'Subjective', necessity: 'Implicit', priority: 'Nice to have' },
};

const getDimensionLabelColor = (label: string): string => {
  const l = (label || '').toLowerCase();
  if (['high', 'correct', 'complete', 'safe', 'accurate'].includes(l)) return 'green';
  if (['medium', 'partially_correct', 'partly_correct', 'partial_correct', 'partial', 'partially_complete', 'partial_completeness', 'risky'].includes(l)) return 'orange';
  if (['low', 'incorrect', 'wrong', 'incomplete', 'risk', 'unsafe', 'irrelevant', 'dangerous'].includes(l)) return 'red';
  return 'default';
};

const generateRubricItems = (schema: any): RubricItem[] => {
  if (!schema?.fields) return [];
  const items: RubricItem[] = [];
  let idx = 1;
  const scoringFields = ['relevance', 'accuracy', 'completeness', 'safety', 'fluency', 'coherence', 'helpfulness', 'harmfulness'];
  for (const field of schema.fields) {
    const key = field.key || field.id || field.name;
    if (!key) continue;
    const fieldKey = String(key).toLowerCase();
    const isScoringField = scoringFields.includes(fieldKey);
    const hasRubric = field.rubric || field.description || field.title;
    if (isScoringField || hasRubric) {
      const mapping = DIMENSION_MAP[fieldKey] || {
        label: field.title || field.label || field.name || key,
        type: (field.type === 'number' || field.type === 'select' || field.type === 'radio') ? 'Objective' as const : 'Subjective' as const,
        necessity: field.required ? 'Explicit' as const : 'Implicit' as const,
        priority: field.required ? 'Must have' as const : 'Nice to have' as const,
      };
      items.push({
        id: idx, dimension: fieldKey, dimensionLabel: mapping.label,
        type: mapping.type, necessity: mapping.necessity, priority: mapping.priority,
        criterion: field.rubric || field.description || field.title || `Evaluate ${fieldKey}`,
        fieldKey: String(key), aiJudgement: null, aiEvidence: [],
      });
      idx++;
    }
  }
  if (items.length === 0) {
    const defaults = ['relevance', 'accuracy', 'completeness', 'safety'];
    defaults.forEach((dim, i) => {
      const mapping = DIMENSION_MAP[dim];
      items.push({
        id: i + 1, dimension: dim, dimensionLabel: mapping.label,
        type: mapping.type, necessity: mapping.necessity, priority: mapping.priority,
        criterion: `Evaluate the ${dim} of the response`, fieldKey: dim,
        aiJudgement: null, aiEvidence: [],
      });
    });
  }
  return items;
};

const validateFormData = (schema: TemplateSchema | null, formData: Record<string, any>): string[] => {
  const missing: string[] = [];
  if (!schema?.fields) return missing;
  const validateField = (field: any): void => {
    if (!field || typeof field !== 'object') return;
    const fieldType = String(field.type || '').toLowerCase();
    if (fieldType === 'showitem' || fieldType === 'show_item') return;
    if (fieldType === 'group' || fieldType === 'tabs') {
      const children = field.children || field.fields || [];
      if (Array.isArray(children)) { for (const child of children) validateField(child); }
      return;
    }
    const key = field.key || field.id;
    if (!key) return;
    const isRequired =
      field.required === true ||
      (field.validation && field.validation.required === true) ||
      (field.rules && Array.isArray(field.rules) && field.rules.some((r: any) => r.required === true)) ||
      (field.rules && !Array.isArray(field.rules) && typeof field.rules === 'object' && (field.rules as any).required === true) ||
      (schema.required && Array.isArray(schema.required) && schema.required.includes(key)) ||
      (schema.required && Array.isArray(schema.required) && schema.required.includes(field.name || ''));
    if (!isRequired) return;
    const value = formData[key];
    const title = field.title || field.label || field.name || key;
    if (value === undefined || value === null || value === '') { missing.push(title); return; }
    if (typeof value === 'string' && value.trim() === '') { missing.push(title); return; }
    if (Array.isArray(value) && value.length === 0) { missing.push(title); return; }
    if (typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === 0) { missing.push(title); return; }
  };
  for (const field of schema.fields) validateField(field);
  const reasonKeys = ['reason', 'detail_reason', 'detailed_reason'];
  for (const rk of reasonKeys) {
    if (formData[rk] !== undefined && typeof formData[rk] === 'string' && formData[rk].trim() === '') {
      const fieldDef = schema.fields.find((f: any) => (f.key || f.id) === rk);
      const title = fieldDef?.title || fieldDef?.label || fieldDef?.name || rk;
      if (!missing.includes(title)) missing.push(title);
    }
  }
  return missing;
};

const AI_ERROR_MAP: Record<string, { short: string; detail: string; suggestion: string }> = {
  dependency_missing: { short: '缺少后端依赖', detail: '后端缺少必要依赖库，真实模型请求未发出。', suggestion: '请在后端环境执行 pip install requests 并重启服务。' },
  invalid_api_key: { short: 'API Key 无效', detail: 'API Key 无效或已过期，鉴权失败。', suggestion: '请在 backend/.env 中重新配置 DASHSCOPE_API_KEY。' },
  model_not_found: { short: '模型不可用', detail: '模型名称不可用，请确认模型名是否正确。', suggestion: '请确认模型名是否为 qwen-plus，或更换其他可用模型。' },
  bad_request: { short: '请求参数错误', detail: '请求参数不正确，请检查模型名、Base URL 和请求体。', suggestion: '请检查 AI 模型配置中的 Base URL 和模型名称。' },
  timeout: { short: '请求超时', detail: '模型接口请求超时，未在规定时间内返回结果。', suggestion: '请稍后重试，或在 AI 模型配置中调大超时时间。' },
  network_error: { short: '网络请求失败', detail: '网络请求失败，无法连接到模型接口。', suggestion: '请检查本机网络和 DashScope 接口地址。' },
  ssl_error: { short: 'SSL 错误', detail: 'SSL 证书验证失败。', suggestion: '请检查网络代理或证书配置。' },
  json_parse_error: { short: 'JSON 解析失败', detail: '模型返回内容不是合法 JSON，系统已尝试解析但失败。', suggestion: '可尝试开启 AI_FORCE_JSON 或调整 prompt。' },
  invalid_response_shape: { short: '响应结构异常', detail: '模型返回数据结构不符合预期。', suggestion: '请检查模型是否正确，或联系管理员。' },
  missing_api_key: { short: 'API Key 未配置', detail: 'API Key 未配置，真实模型请求无法发出。', suggestion: '请在 backend/.env 中配置 DASHSCOPE_API_KEY。' },
  rate_limited: { short: 'API 限流', detail: '模型接口调用频率超限。', suggestion: '请稍后重试。' },
  server_error: { short: '服务端错误', detail: '模型服务端返回错误。', suggestion: '请稍后重试，或联系模型服务商。' },
  forbidden: { short: '无访问权限', detail: '无访问权限，请检查账号权限或模型调用权限。', suggestion: '请检查 API Key 对应账号的模型调用权限。' },
  http_error: { short: 'HTTP 错误', detail: 'HTTP 请求返回非预期状态码。', suggestion: '请查看运行详情中的原始错误信息。' },
  unknown_error: { short: '未知错误', detail: '发生未知错误。', suggestion: '请查看运行详情中的原始错误信息。' },
};

const formatAiError = (errorType?: string | null, errorMessage?: string | null): string => {
  if (!errorType) return errorMessage || '未知错误';
  const mapped = AI_ERROR_MAP[errorType];
  if (mapped) return mapped.short;
  // 尝试从 error_message 中匹配常见英文关键词
  const msg = (errorMessage || '').toLowerCase();
  if (msg.includes('requests library') || msg.includes('dependency')) return '缺少后端依赖';
  if (msg.includes('api key') || msg.includes('401') || msg.includes('unauthorized')) return 'API Key 无效';
  if (msg.includes('model not found') || msg.includes('400')) return '模型不可用';
  if (msg.includes('timeout') || msg.includes('timed out')) return '请求超时';
  if (msg.includes('connection') || msg.includes('network')) return '网络请求失败';
  if (msg.includes('json') || msg.includes('parse')) return 'JSON 解析失败';
  return errorType;
};



const normalizeAiReview = (aiReview: any) => {
  if (!aiReview || typeof aiReview !== 'object') return null;
  const score = aiReview.score ?? aiReview.overall_score ?? aiReview.ai_review_score;
  const riskLevel = aiReview.risk_level ?? aiReview.ai_review_risk_level;
  const passed = aiReview.passed ?? aiReview.ai_review_passed;
  const summary = aiReview.summary;
  const issues = aiReview.issues || [];
  const suggestions = aiReview.suggestions || [];
  const result = aiReview.result || {};
  const dimensionScores = aiReview.dimension_scores || result.dimension_scores || {};
  const suggestedLabels = aiReview.suggested_labels || result.suggested_labels || {};
  const suggestion = aiReview.suggestion || {};
  const relevance = dimensionScores.relevance || suggestedLabels.relevance || suggestion.relevance || null;
  const accuracy = dimensionScores.accuracy || suggestedLabels.accuracy || suggestion.accuracy || null;
  const completeness = dimensionScores.completeness || suggestedLabels.completeness || suggestion.completeness || null;
  const safety = dimensionScores.safety || suggestedLabels.safety || suggestion.safety || null;
  const suggestionText = suggestions.length > 0 ? suggestions[0]
    : (issues.length > 0 ? issues[0]?.message : null)
    || summary || suggestion.reason || aiReview.raw_text || null;
  const confidence = aiReview.confidence;
  const dimensions = aiReview.dimensions || null;
  const toolChecks = aiReview.tool_checks || [];
  const issueTags = aiReview.issue_tags || [];
  const promptTemplate = aiReview.prompt_template || null;
  const promptVersion = aiReview.prompt_version || null;
  const modelProvider = aiReview.model_provider || null;
  const modelName = aiReview.model_name || null;
  const baseUrl = aiReview.base_url || null;
  const latencyMs = aiReview.latency_ms || null;
  const runId = aiReview.run_id || null;
  const outputJson = aiReview.output_json || null;
  const fallbackUsed = !!(aiReview.fallback || aiReview.fallback_used || aiReview.used_fallback || (outputJson && (outputJson.fallback || outputJson.fallback_used)));
  const fallbackProvider = aiReview.fallback_provider || (outputJson && outputJson.fallback_provider) || null;
  const fallbackReason = aiReview.fallback_reason || (outputJson && outputJson.fallback_reason) || null;
  const errorType = aiReview.error_type || (outputJson && outputJson.error_type) || null;
  const errorMessage = aiReview.error_message || (outputJson && outputJson.error_message) || null;
  const rawResponsePreview = aiReview.raw_response_preview || (outputJson && outputJson.raw_response_preview) || null;
  const status = aiReview.status || (aiReview.success === false ? 'failed' : 'success');
  const suggestionAction = aiReview.suggestion_action || (passed ? 'submit' : 'reject');
  // preference_compare fields
  const preferred = aiReview.preferred || (outputJson && outputJson.preferred) || null;
  const margin = aiReview.margin || (outputJson && outputJson.margin) || null;
  const prefDimensions = aiReview.pref_dimensions || (outputJson && outputJson.dimensions) || (outputJson && outputJson.pref_dimensions) || null;
  const safetyFlag = aiReview.safety_flag ?? (outputJson && outputJson.safety_flag) ?? null;
  return {
    score, riskLevel, passed, summary, issues, suggestions,
    relevance, accuracy, completeness, safety, suggestionText, confidence, suggestion,
    dimensions, toolChecks, issueTags, promptTemplate, promptVersion, modelProvider, modelName,
    baseUrl, latencyMs, runId, outputJson, suggestionAction, fallbackUsed, fallbackProvider,
    fallbackReason, errorType, errorMessage, rawResponsePreview, status,
    preferred, margin, pref_dimensions: prefDimensions, safety_flag: safetyFlag,
  };
};

const getUrlParam = (name: string): string | null => {
  const params = new URLSearchParams(window.location.search);
  return params.get(name);
};

const updateUrlParams = (params: Record<string, string | number | null>) => {
  const urlParams = new URLSearchParams(window.location.search);
  Object.entries(params).forEach(([key, value]) => {
    if (value === null) urlParams.delete(key);
    else urlParams.set(key, String(value));
  });
  window.history.replaceState({}, '', `${window.location.pathname}?${urlParams.toString()}`);
};

// ── Performance debug hook (counts renders, warns every 5s if excessive) ──
function useRenderDebug(name: string) {
  const countRef = useRef(0);
  countRef.current += 1;
  useEffect(() => {
    const timer = setInterval(() => {
      if (countRef.current > 50) {
        console.warn(`[perf] ${name} rendered ${countRef.current} times in last 5s`);
      } else if (import.meta.env.DEV) {
        console.log(`[perf] ${name}: ${countRef.current} renders in 5s`);
      }
      countRef.current = 0;
    }, 5000);
    return () => clearInterval(timer);
  }, [name]);
}

// ── Isolated timer display: own setInterval, no parent re-render ──
const WorkbenchTimerDisplay: React.FC<{ getElapsed: () => number }> = React.memo(({ getElapsed }) => {
  const displayRef = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!ENABLE_TOP_TIMER) return;
    const tick = () => {
      const el = displayRef.current;
      if (el) el.textContent = '\u23F1 ' + formatDuration(getElapsed());
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [getElapsed]);
  return <span ref={displayRef} style={{ fontWeight: 600, fontSize: 15, letterSpacing: 1 }}>{'\u23F1'} 00:00:00</span>;
});
WorkbenchTimerDisplay.displayName = 'WorkbenchTimerDisplay';

// ── Lightweight LLM result panel: isolated React.memo, no re-render on form input ──
const SimpleLLMResultPanel: React.FC<{
  aiReview: any;
  loading: boolean;
  taskLlmAssistEnabled: boolean;
}> = React.memo(({ aiReview, loading, taskLlmAssistEnabled }) => {
  if (!ENABLE_SIMPLE_LLM_RESULT_PANEL) return null;
  if (loading) {
    return (
      <Card size="small" title={<span><RobotOutlined style={{ marginRight: 4 }} />LLM 辅助建议</span>} style={{ marginTop: 12 }}>
        <div style={{ textAlign: 'center', padding: '16px 0', color: '#999', fontSize: 12 }}>AI 分析中...</div>
      </Card>
    );
  }
  if (!aiReview) {
    return (
      <Card size="small" title={<span><RobotOutlined style={{ marginRight: 4 }} />LLM 辅助建议</span>} style={{ marginTop: 12 }}>
        <div style={{ textAlign: 'center', padding: '12px 0', color: '#999', fontSize: 12 }}>
          {!taskLlmAssistEnabled
            ? '当前任务未开启 LLM 辅助，请项目所有者在任务详情页开启。'
            : '点击底部「LLM 辅助」按钮生成建议'}
        </div>
      </Card>
    );
  }
  const norm = normalizeAiReview(aiReview);
  if (!norm) return null;
  const riskColor = norm.riskLevel === 'high' ? 'red' : norm.riskLevel === 'medium' ? 'orange' : 'green';
  const riskText = norm.riskLevel === 'high' ? '高风险' : norm.riskLevel === 'medium' ? '中风险' : '低风险';
  return (
    <Card size="small" title={<span><RobotOutlined style={{ marginRight: 4 }} />LLM 辅助建议</span>} style={{ marginTop: 12 }}>
      <div style={{ fontSize: 11, color: '#999', marginBottom: 8 }}>AI 根据 Rubric 维度给出参考建议，包括相关性、准确性、完整性、安全性评分与理由。该结果仅辅助标注，不替代人工提交。</div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 8, flexWrap: 'wrap' }}>
        {norm.score != null && <Tag color="blue">{norm.score} 分</Tag>}
        {norm.riskLevel && <Tag color={riskColor}>{riskText}</Tag>}
        {norm.confidence != null && <Tag color={norm.confidence >= 0.8 ? 'green' : norm.confidence >= 0.5 ? 'blue' : 'default'}>置信度: {Math.round(norm.confidence * 100)}%</Tag>}
        {norm.passed != null && <Tag color={norm.passed ? 'green' : 'red'}>{norm.passed ? '建议通过' : '建议修改'}</Tag>}
      </div>
      {norm.summary && <Alert message={norm.summary} type="info" showIcon style={{ marginBottom: 8, fontSize: 12 }} />}
      {norm.suggestionText && (
        <div style={{ fontSize: 12, padding: '6px 8px', backgroundColor: '#f6ffed', borderRadius: 4, marginBottom: 8, lineHeight: 1.6 }}>
          <strong>建议：</strong>{norm.suggestionText}
        </div>
      )}
      {norm.suggestions && norm.suggestions.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          {norm.suggestions.map((s: string, i: number) => (
            <div key={i} style={{ fontSize: 11, color: '#1890ff', padding: '2px 0' }}>💡 {s}</div>
          ))}
        </div>
      )}
      {norm.issues && norm.issues.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          {norm.issues.slice(0, 5).map((issue: any, i: number) => (
            <div key={i} style={{ fontSize: 11, color: issue.level === 'high' || issue.severity === 'high' ? '#ff4d4f' : '#fa8c16', padding: '2px 0' }}>
              ⚠ {issue.message || issue.field}
            </div>
          ))}
        </div>
      )}
      {norm.fallbackUsed && (
        <div style={{ color: '#fa8c16', fontSize: 11, marginBottom: 4 }}>
          ⚠ 真实模型暂不可用（{formatAiError(norm.errorType)}），已使用演示兜底结果
        </div>
      )}
      {norm.errorType && !norm.fallbackUsed && (
        <div style={{ color: '#ff4d4f', fontSize: 11, marginBottom: 4 }}>
          ❌ AI 预审失败：{formatAiError(norm.errorType, norm.errorMessage)}
        </div>
      )}
      {norm.dimensions && Object.keys(norm.dimensions).length > 0 && (
        <div style={{ marginTop: 8, padding: '8px 10px', backgroundColor: '#f0f5ff', borderRadius: 6, border: '1px solid #d6e4ff' }}>
          <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 6, color: '#1d39c4' }}>Rubric 对齐建议（AI 判断，仅供参考）</div>
          {['relevance', 'accuracy', 'completeness', 'safety'].filter(dim => norm.dimensions[dim]).map(dim => {
            const d = norm.dimensions[dim];
            const dimLabels: Record<string, string> = { relevance: '相关性', accuracy: '准确性', completeness: '完整性', safety: '安全性' };
            return (
              <div key={dim} style={{ marginBottom: 6, fontSize: 11, lineHeight: 1.5 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Tag color="blue" style={{ fontSize: 10, margin: 0 }}>{dimLabels[dim] || dim}</Tag>
                  {d.label && <Tag color={getDimensionLabelColor(d.label)} style={{ fontSize: 10, margin: 0 }}>{d.label}</Tag>}
                  {d.score != null && <span style={{ color: '#666' }}>{d.score}分</span>}
                </div>
                {d.evidence && d.evidence.length > 0 && (
                  <div style={{ marginTop: 2, paddingLeft: 8 }}>
                    {d.evidence.map((e: string, i: number) => <div key={i} style={{ color: '#52c41a' }}>✓ {e}</div>)}
                  </div>
                )}
                {d.issues && d.issues.length > 0 && (
                  <div style={{ marginTop: 2, paddingLeft: 8 }}>
                    {d.issues.map((iss: string, i: number) => <div key={i} style={{ color: '#ff4d4f' }}>✗ {iss}</div>)}
                  </div>
                )}
              </div>
            );
          })}
          <div style={{ fontSize: 10, color: '#999', fontStyle: 'italic' }}>以上为 AI 按 Rubric 维度的判断，正式标注以中间表单为准。</div>
        </div>
      )}
      <details style={{ marginTop: 8 }}>
        <summary style={{ cursor: 'pointer', color: '#999', fontSize: 11 }}>查看原始 JSON</summary>
        <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 200, overflow: 'auto', fontSize: 10, backgroundColor: '#f5f5f5', padding: 8, borderRadius: 4, marginTop: 4 }}>
          {JSON.stringify(aiReview?.output_json || aiReview, null, 2)}
        </pre>
      </details>
    </Card>
  );
});
SimpleLLMResultPanel.displayName = 'SimpleLLMResultPanel';

// ── OptimizedRubricPanel: read-only Rubric reference, React.memo, no formData dependency ──
const RUBRIC_DIM_LABELS: Record<string, string> = {
  relevance: '相关性', accuracy: '准确性', completeness: '完整性', safety: '安全性',
  fluency: '流畅性', coherence: '连贯性', helpfulness: '有用性', harmfulness: '有害性',
};
const OptimizedRubricPanel: React.FC<{
  rubricItems: RubricItem[];
  category?: string;
  difficulty?: string;
  statusText?: string;
  statusColor?: string;
  modeText?: string;
  modeColor?: string;
}> = React.memo(({ rubricItems, category, difficulty, statusText, statusColor, modeText, modeColor }) => {
  useRenderDebug('OptimizedRubricPanel');
  return (
    <div style={{ width: 400, flexShrink: 0, overflow: 'auto' }}>
      <Card size="small" title="Rubric 标准参考" style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: '#999', marginBottom: 8 }}>仅供标注员理解评分标准，正式标注结果以中间表单为准。</div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
          <span style={{ color: '#999', fontSize: 11 }}>类别：</span><Tag>{category || '-'}</Tag>
          <span style={{ color: '#999', fontSize: 11, marginLeft: 8 }}>难度：</span>
          <Tag color={difficulty === 'hard' ? 'red' : difficulty === 'medium' ? 'orange' : 'green'}>{difficulty || '-'}</Tag>
          {statusText && <><span style={{ color: '#999', fontSize: 11, marginLeft: 8 }}>阶段：</span><Tag color={statusColor || 'default'}>{statusText}</Tag></>}
          {modeText && <Tag color={modeColor || 'default'}>{modeText}</Tag>}
        </div>
      </Card>
      <Card size="small" title={`评分维度说明 (${rubricItems.length})`}>
        {rubricItems.length === 0 ? (
          <div style={{ color: '#999', textAlign: 'center', padding: 12, fontSize: 12 }}>暂无 Rubric 维度</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {rubricItems.map((item) => (
              <div key={item.id} style={{ padding: '8px 10px', backgroundColor: '#fafafa', borderRadius: 6, border: '1px solid #f0f0f0' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4, flexWrap: 'wrap' }}>
                  <Tag style={{ fontSize: 10, margin: 0, fontWeight: 600 }}>R{item.id}</Tag>
                  <strong style={{ fontSize: 12 }}>{item.dimensionLabel}</strong>
                  <span style={{ fontSize: 11, color: '#999' }}>{RUBRIC_DIM_LABELS[item.dimension] || item.dimension}</span>
                </div>
                <div style={{ display: 'flex', gap: 4, marginBottom: 6, flexWrap: 'wrap' }}>
                  <Tag color={item.type === 'Objective' ? 'blue' : 'purple'} style={{ fontSize: 10, margin: 0 }}>{item.type === 'Objective' ? '客观' : '主观'}</Tag>
                  <Tag color={item.necessity === 'Explicit' ? 'orange' : 'default'} style={{ fontSize: 10, margin: 0 }}>{item.necessity === 'Explicit' ? '显式' : '隐式'}</Tag>
                  <Tag color={item.priority === 'Must have' ? 'green' : 'geekblue'} style={{ fontSize: 10, margin: 0 }}>{item.priority === 'Must have' ? '必要' : '加分'}</Tag>
                </div>
                <div style={{ color: '#555', fontSize: 12, lineHeight: 1.6 }}>{item.criterion}</div>
                <div style={{ fontSize: 10, color: '#bbb', marginTop: 6, fontStyle: 'italic' }}>该维度仅作参考，不单独提交。</div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
});
OptimizedRubricPanel.displayName = 'OptimizedRubricPanel';

const LabelWorkbenchPage: React.FC = () => {
  if (import.meta.env.DEV) _perfCounters.workbenchRender++;
  useRenderDebug('LabelWorkbenchPage');
  // Dev-only: log safe-mode toggls once on mount
  const _flagsLoggedRef = useRef(false);
  if (!_flagsLoggedRef.current) {
    _flagsLoggedRef.current = true;
    if (import.meta.env.DEV) {
      console.log('[Perf] Safe Mode toggles:', { WORKBENCH_SAFE_MODE, ENABLE_TOP_TIMER, ENABLE_RAW_DATA_VIEW, ENABLE_BASIC_FORM, ENABLE_LLM_ASSIST_BUTTON, ENABLE_SIMPLE_LLM_RESULT_PANEL, ENABLE_RIGHT_RUBRIC_PANEL, ENABLE_RIGHT_PANEL, ENABLE_AUDIT_LOG_PANEL, ENABLE_AUTOSAVE, ENABLE_LOCAL_DRAFT, ENABLE_OPERATION_LOG });
    }
  }
  const navigate = useNavigate();
  const [currentItem, setCurrentItem] = useState<DatasetItem | null>(null);
  const [itemData, setItemData] = useState<any>(null);
  const [taskTemplateId, setTaskTemplateId] = useState<number | null>(null);
  const [taskLlmAssistEnabled, setTaskLlmAssistEnabled] = useState<boolean>(true);
  const [currentTemplateName, setCurrentTemplateName] = useState<string>('');
  const [currentTemplateVersion, setCurrentTemplateVersion] = useState<string>('');
  const [formData, setFormData] = useState<Record<string, any>>({});
  const formDataRef = useRef<Record<string, any>>({});
  const [, setFormSyncTick] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [aiReview, setAiReview] = useState<any>(null);
  const [aiPrecheckLoading, setAiPrecheckLoading] = useState(false);
  const [missingFields, setMissingFields] = useState<string[]>([]);
  const [, setAiReviewExpired] = useState(false);
  const [aiAssistConfig, setAiAssistConfig] = useState<AiAssistConfig | null>(null);
  const [aiAssistSource, setAiAssistSource] = useState<string>(''); // 'history' | 'live' | ''
  const [rejectedReason, setRejectedReason] = useState<string>('');
  const [reviewInfo, setReviewInfo] = useState<any>(null);
  const [submission, setSubmission] = useState<SubmissionRecord | null>(null);
  const [queueItems, setQueueItems] = useState<DatasetItem[]>([]);
  const queueItemsRef = useRef<DatasetItem[]>([]);
  const [currentMode, setCurrentMode] = useState<string>('edit');
  // durationSeconds state REMOVED: timer display is now isolated in WorkbenchTimerDisplay
  const setDurationSeconds = (_: number) => {}; // no-op kept for call-site compat
  // Compute current elapsed without triggering re-render
  const getElapsedSeconds = useCallback(() => {
    if (!baseTimeRef.current) return baseElapsedRef.current;
    return baseElapsedRef.current + Math.floor((Date.now() - baseTimeRef.current) / 1000);
  }, []);
  const [sessionStatus, setSessionStatus] = useState<string>('none');
  const [logs, setLogs] = useState<OperationLog[]>([]);
  const [showLogs, setShowLogs] = useState(false);
  const [showRawJson, setShowRawJson] = useState(false);
  const [sessionId, setSessionId] = useState<number | null>(null);

  const [contentTab, setContentTab] = useState<string>('raw');
  const [markInvalidModalVisible, setMarkInvalidModalVisible] = useState(false);
  const [markInvalidReason, setMarkInvalidReason] = useState<string>('');
  const [markInvalidRemark, setMarkInvalidRemark] = useState<string>('');
  const [markInvalidLoading, setMarkInvalidLoading] = useState(false);
  const [versions, setVersions] = useState<VersionRecord[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [logsDrawerTab, setLogsDrawerTab] = useState<string>('logs');
  const [selectedVersion, setSelectedVersion] = useState<VersionRecord | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [rubricItems, setRubricItems] = useState<RubricItem[]>([]);
  const [_rubricSelections, setRubricSelections] = useState<Record<string, string>>({});
  const [_rubricNotes, setRubricNotes] = useState<Record<string, string>>({});

  const timerRef = useRef<number | null>(null);
  const heartbeatRef = useRef<number | null>(null);
  const timerCacheRef = useRef<number | null>(null);
  const baseElapsedRef = useRef<number>(0);
  const baseTimeRef = useRef<number>(0);
  const lastMessageRef = useRef<Map<string, number>>(new Map());
  const keyboardHandlersRef = useRef<any>({});
  const sessionOpeningRef = useRef<boolean>(false);
  const currentItemIdRef = useRef<number | null>(null);
  const sessionClosedRef = useRef<boolean>(false);
  const timerHydratedRef = useRef<boolean>(false);
  const sessionReadyRef = useRef<boolean>(false);
  const currentWorkKeyRef = useRef<string | null>(null);
  const sessionIdRef_current = useRef<number | null>(null);
  const currentItemRef_current = useRef<{ task_id?: number; id?: number; work_key?: string } | null>(null);
  const formSyncTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep refs in sync with state for use in stale-closure-safe callbacks
  useEffect(() => { sessionIdRef_current.current = sessionId; }, [sessionId]);
  useEffect(() => { currentItemRef_current.current = currentItem; }, [currentItem]);
  // Keep formDataRef in sync with formData state (for save/submit reads)
  useEffect(() => { formDataRef.current = formData; }, [formData]);

  const _getTimerCacheKey = (workKey?: string | null) => workKey ? `labelhub_timer_last_${workKey}` : '';
  const _saveTimerCache = () => {
    const key = _getTimerCacheKey(currentWorkKeyRef.current || currentItem?.work_key);
    const elapsed = getElapsedSeconds();
    if (key && elapsed > 0 && timerHydratedRef.current) {
      localStorage.setItem(key, String(elapsed));
    }
  };
  const _loadTimerCache = (workKey?: string | null): number => {
    const key = _getTimerCacheKey(workKey);
    if (!key) return 0;
    const val = localStorage.getItem(key);
    return val ? parseInt(val, 10) : 0;
  };
  const _clearTimerCache = (workKey?: string | null) => {
    const key = _getTimerCacheKey(workKey);
    if (key) localStorage.removeItem(key);
  };

  const showMessage = useMemo(() => ({
    info: (content: string) => {
      const now = Date.now();
      const last = lastMessageRef.current.get(content);
      if (last && now - last < 2000) return;
      lastMessageRef.current.set(content, now);
      message.info(content);
    },
    error: (content: string) => {
      const now = Date.now();
      const last = lastMessageRef.current.get(content);
      if (last && now - last < 2000) return;
      lastMessageRef.current.set(content, now);
      message.error(content);
    },
    warning: (content: string) => {
      const now = Date.now();
      const last = lastMessageRef.current.get(content);
      if (last && now - last < 2000) return;
      lastMessageRef.current.set(content, now);
      message.warning(content);
    }
  }), []);

  const setStoredCurrentItemId = (itemId: number | null) => {
    if (itemId) localStorage.setItem(STORAGE_KEY_CURRENT_ITEM, String(itemId));
    else localStorage.removeItem(STORAGE_KEY_CURRENT_ITEM);
  };

  const startHeartbeat = useCallback((sid: number) => {
    if (heartbeatRef.current) clearInterval(heartbeatRef.current);
    heartbeatRef.current = window.setInterval(async () => {
      try {
        await heartbeatSession({ session_id: sid, work_key: currentItemRef_current.current?.work_key, labeler_id: 2 });
      } catch (e) {
        console.warn('[heartbeat] error:', e);
      }
    }, 30000);
  }, []);

  const stopHeartbeat = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
  }, []);

  const loadBackendLogs = useCallback(async (taskId: number, itemId: number, workKey?: string) => {
    if (import.meta.env.DEV) _perfCounters.fetchAuditLogs++;
    try {
      const res = await getWorkbenchLogs({ task_id: taskId, item_id: itemId, labeler_id: 2, work_key: workKey, limit: 100 });
      if (res.items) {
        setLogs(res.items.map((item: any) => ({
          id: item.id, action: item.action, action_label: item.action_label || item.action,
          task_id: item.task_id, item_id: item.item_id, work_key: item.work_key,
          message: item.message, payload_json: item.payload_json,
          after_data: item.after_data, extra_info: item.extra_info, created_at: item.created_at
        })));
      }
    } catch (_) {}
  }, []);

  // On mount, restore elapsed time from backend if there's a current work context
  useEffect(() => {
    const urlWorkKey = getUrlParam('work_key');
    const urlTaskId = getUrlParam('task_id');
    const urlItemId = getUrlParam('item_id');
    const taskId = urlTaskId ? parseInt(urlTaskId, 10) : null;
    const itemId = urlItemId ? parseInt(urlItemId, 10) : null;

    if (taskId && itemId) {
      getElapsed({ task_id: taskId, item_id: itemId, labeler_id: 2, work_key: urlWorkKey || undefined })
        .then((res: any) => {
          if (res.success && res.persisted_elapsed_seconds != null) {
            const persisted = res.persisted_elapsed_seconds;
            baseElapsedRef.current = persisted;
            baseTimeRef.current = Date.now();
            setDurationSeconds(persisted);
            timerHydratedRef.current = true;
          }
        })
        .catch(() => {});
    }
  }, []);

  useEffect(() => {
    fetchCurrentTask();

    const handleVisibilityChange = () => {
      if (document.hidden) {
        if (heartbeatRef.current) {
          clearInterval(heartbeatRef.current);
          heartbeatRef.current = null;
        }
        _saveTimerCache();
      } else {
        // Use refs to get current values (avoid stale closure)
        const currentSid = sessionIdRef_current.current;
        const currentTaskId = currentItemRef_current.current?.task_id;
        const currentItemId = currentItemRef_current.current?.id;
        const currentWorkKey = currentItemRef_current.current?.work_key;

        if (currentSid && !heartbeatRef.current) {
          startHeartbeat(currentSid);
        }
        if (currentTaskId && currentItemId) {
          getElapsed({ task_id: currentTaskId, item_id: currentItemId, labeler_id: 2, work_key: currentWorkKey || undefined })
            .then((res: any) => {
              if (res.success && res.persisted_elapsed_seconds != null) {
                const persisted = res.persisted_elapsed_seconds;
                baseElapsedRef.current = persisted;
                baseTimeRef.current = Date.now();
                setDurationSeconds(persisted);
                timerHydratedRef.current = true;
              }
            })
            .catch(() => {});
        }
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      _saveTimerCache();
      if (timerRef.current) clearInterval(timerRef.current);
      if (formSyncTimerRef.current) clearTimeout(formSyncTimerRef.current);
      stopHeartbeat();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      // 不在组件卸载时自动关闭 session——session 只在 skip/submit/end task 时关闭
      // 路由切换（如到"我的提交"）不应关闭标注 session
    };
  }, []);

  useEffect(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (timerCacheRef.current) { clearInterval(timerCacheRef.current); timerCacheRef.current = null; }

    // Timer display is now handled by isolated WorkbenchTimerDisplay component.
    // No RAF, no per-second setState on the 2234-line parent.
    // Keep a 30s cache-sync for the timer cache save (no React render trigger).
    if (sessionStatus === 'active' && baseTimeRef.current) {
      timerCacheRef.current = window.setInterval(() => {
        _saveTimerCache();
      }, 30000);

      return () => {
        if (timerRef.current) clearInterval(timerRef.current);
        if (timerCacheRef.current) clearInterval(timerCacheRef.current);
      };
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (timerCacheRef.current) clearInterval(timerCacheRef.current);
    };
  }, [sessionStatus]);

  const initialRubricItems = useMemo(() => {
    const schema = itemData?.schema_json || itemData?.template?.schema_json || itemData?.template_schema || itemData?.schema;
    return schema ? generateRubricItems(schema) : [];
  }, [itemData?.schema_json, itemData?.template?.schema_json, itemData?.template_schema, itemData?.schema]);

  useEffect(() => {
    setRubricItems(initialRubricItems);
  }, [initialRubricItems]);

  useEffect(() => {
    if (aiReview && rubricItems.length > 0) {
      const norm = normalizeAiReview(aiReview);
      if (norm?.dimensions) {
        setRubricItems(prev => prev.map(item => {
          const dimData = norm.dimensions[item.dimension];
          if (dimData) return { ...item, aiJudgement: dimData.label || null, aiEvidence: dimData.evidence || [] };
          return item;
        }));
      }
    }
  }, [aiReview]);

  useEffect(() => {
    const handleFullscreenChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 's') { e.preventDefault(); keyboardHandlersRef.current.saveDraft?.(); }
      else if (e.altKey && e.key === 'a') { e.preventDefault(); keyboardHandlersRef.current.aiPrecheck?.(); }
      else if (e.altKey && e.key === 'c') { e.preventDefault(); keyboardHandlersRef.current.submit?.(); }
      else if (e.altKey && e.key === 'n') { e.preventDefault(); keyboardHandlersRef.current.nextItem?.(); }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const fetchCurrentTask = async () => {
    try {
      setLoading(true);
      await loadQueueItems();
      const queue = queueItemsRef.current;
      const labelerId = 2;
      const urlSubmissionId = getUrlParam('submission_id');
      const urlItemId = getUrlParam('item_id');
      const urlTaskId = getUrlParam('task_id');
      const urlMode = getUrlParam('mode');
      const urlWorkKey = getUrlParam('work_key');

      if (urlSubmissionId || urlItemId || urlWorkKey) {
        let targetWorkKey: string | null = null;
        if (urlWorkKey) {
          const parts = urlWorkKey.split(':');
          targetWorkKey = parts.length === 3 ? urlWorkKey : `${urlWorkKey}:${labelerId}`;
        } else if (urlTaskId && urlItemId) {
          targetWorkKey = `${urlTaskId}:${urlItemId}:${labelerId}`;
        }
        let matchedQueueItem = null;
        if (targetWorkKey) matchedQueueItem = queue.find(item => item.work_key === targetWorkKey) || null;
        if (!matchedQueueItem && urlSubmissionId) {
          matchedQueueItem = queue.find(item =>
            item.submission_id === parseInt(urlSubmissionId, 10) ||
            item.annotation_id === parseInt(urlSubmissionId, 10)
          ) || null;
        }
        if (matchedQueueItem) {
          let effectiveMode = urlMode || '';
          const actualStatus = matchedQueueItem.effectiveStatus || matchedQueueItem.status;
          if (actualStatus === 'rejected_to_modify' || actualStatus === 'rework' || actualStatus === 'needs_revision') effectiveMode = 'rework';
          else if (actualStatus === 'claimed' || actualStatus === 'in_progress') effectiveMode = effectiveMode || 'new';
          else if (actualStatus === 'draft') effectiveMode = 'draft';
          if (effectiveMode) setCurrentMode(effectiveMode);
          await openWorkbenchItem({
            id: matchedQueueItem.id, task_id: matchedQueueItem.task_id,
            work_key: matchedQueueItem.work_key,
            submission_id: matchedQueueItem.submission_id || matchedQueueItem.annotation_id || (urlSubmissionId ? parseInt(urlSubmissionId, 10) : undefined),
            status: actualStatus, is_rework: matchedQueueItem.is_rework,
            mode: effectiveMode || matchedQueueItem.mode, review_reason: matchedQueueItem.review_reason
          });
          return;
        }
        showMessage.info('该记录已提交，不能继续编辑，可在我的提交中查看详情');
        updateUrlParams({ item_id: null, task_id: null, submission_id: null, work_key: null, mode: null });
        if (queue.length > 0) {
          const firstItem = queue[0];
          await openWorkbenchItem({
            id: firstItem.id, task_id: firstItem.task_id, work_key: firstItem.work_key,
            submission_id: firstItem.submission_id || firstItem.annotation_id,
            status: firstItem.effectiveStatus || firstItem.status,
            is_rework: firstItem.is_rework, mode: firstItem.mode, review_reason: firstItem.review_reason
          });
          return;
        }
        setCurrentItem(null); setItemData(null); setFormData({});
        return;
      }
      if (queue.length > 0) {
        const firstItem = queue[0];
        await openWorkbenchItem({
          id: firstItem.id, task_id: firstItem.task_id, work_key: firstItem.work_key,
          submission_id: firstItem.submission_id || firstItem.annotation_id,
          status: firstItem.effectiveStatus || firstItem.status,
          is_rework: firstItem.is_rework, mode: firstItem.mode, review_reason: firstItem.review_reason
        });
      } else {
        setCurrentItem(null); setItemData(null); setFormData({});
      }
    } catch (error) {
      message.error('获取任务失败');
    } finally {
      setLoading(false);
    }
  };

  const getStatusLabel = (status: string): string => {
    switch (status) {
      case 'claimed': return '已领取';
      case 'draft': case 'drafting': return '草稿';
      case 'rejected_to_modify': case 'rejected': case 'returned': return '打回修改';
      case 'submitted': return '已提交';
      case 'approved': return '已通过';
      default: return status;
    }
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'claimed': return 'blue';
      case 'draft': case 'drafting': return 'gray';
      case 'rejected_to_modify': case 'rejected': case 'returned': return 'orange';
      case 'submitted': return 'purple';
      case 'approved': return 'green';
      default: return 'default';
    }
  };

  const loadQueueItems = async () => {
    try {
      const response = await getLabelerItems();
      const responseData = response as any;
      let normalizedList = Array.isArray(responseData.items || responseData.data || responseData) ? (responseData.items || responseData.data || responseData) : [];
      const labelerId = 2;
      normalizedList = normalizedList.map((item: any) => {
        const annotationStatus = item.annotation_status;
        let effectiveStatus = item.status;
        if (annotationStatus === 'rejected_to_modify') effectiveStatus = 'rejected_to_modify';
        else if (annotationStatus === 'draft') effectiveStatus = 'draft';
        const workKey = item.work_key || `${item.task_id}:${item.dataset_item_id || item.id}:${labelerId}`;
        return { ...item, effectiveStatus, work_key: workKey };
      });
      const seenKeys = new Map<string, any>();
      for (const item of normalizedList) {
        const wk = item.work_key;
        if (!seenKeys.has(wk)) seenKeys.set(wk, item);
        else {
          const statusRank: Record<string, number> = { rejected_to_modify: 0, returned_to_modify: 0, needs_revision: 0, rework: 0, rework_draft: 0.5, draft: 1, drafting: 1, claimed: 2 };
          const existing = seenKeys.get(wk);
          const existingRank = statusRank[existing.effectiveStatus] ?? 99;
          const newRank = statusRank[item.effectiveStatus] ?? 99;
          if (newRank < existingRank) seenKeys.set(wk, item);
        }
      }
      normalizedList = Array.from(seenKeys.values());
      normalizedList = normalizedList.filter((item: any) => !['submitted', 'approved'].includes(item.effectiveStatus));
      normalizedList.sort((a: any, b: any) => {
        const statusRank: Record<string, number> = { rejected_to_modify: 0, rejected: 0, returned: 0, draft: 1, drafting: 1, claimed: 2 };
        const ra = statusRank[a.effectiveStatus] ?? 99;
        const rb = statusRank[b.effectiveStatus] ?? 99;
        if (ra !== rb) return ra - rb;
        const ta = new Date(a.updated_at || a.reviewed_at || a.created_at || 0).getTime();
        const tb = new Date(b.updated_at || b.reviewed_at || b.created_at || 0).getTime();
        return tb - ta;
      });
      setQueueItems(normalizedList);
      queueItemsRef.current = normalizedList;
      return normalizedList; // 返回最新队列供调用方直接使用
    } catch (error) {
      console.error('[loadQueueItems] error:', error);
      return []; // 错误时返回空数组
    }
  };

  const loadItemData = async (item: DatasetItem, workKey?: string, submissionId?: number) => {
    if (import.meta.env.DEV) _perfCounters.fetchForm++;
    try {
      const itemId = item.id || item.dataset_item_id;
      const taskId = item.task_id;
      if (!itemId) return;
      const itemStatus = item.status || item.effectiveStatus;
      if (itemStatus === 'submitted' || itemStatus === 'approved') return;
      const response = await getLabelerForm(itemId as number, { task_id: taskId, work_key: workKey, submission_id: submissionId });
      const data = (response as any)?.data || response as any;
      setItemData(data);
      if (data?.work_key && currentItem) {
        const correctedTaskId = data.task_id || taskId;
        if (currentItem.work_key !== data.work_key || currentItem.task_id !== correctedTaskId) {
          setCurrentItem(prev => prev ? { ...prev, work_key: data.work_key, task_id: correctedTaskId } : prev);
          updateUrlParams({ item_id: itemId, task_id: correctedTaskId, work_key: data.work_key, submission_id: data.submission_id || submissionId || null, mode: data.mode || (data.is_rework ? 'rework' : 'new') });
        }
      }
      if (data?.template_id || data?.resolved_template_id) setTaskTemplateId(data.template_id || data.resolved_template_id);
      if (data?.llm_assist_enabled !== undefined) setTaskLlmAssistEnabled(data.llm_assist_enabled !== false);
      if (data?.resolved_template_name) setCurrentTemplateName(data.resolved_template_name);
      if (data?.template_version) setCurrentTemplateVersion(data.template_version);
      const isReworkMode = data?.is_rework || data?.mode === 'rework' || data?.mode === 'rework_draft';
      if (!submission || !submission.result) {
        let savedResult: any = {};
        if (isReworkMode && data?.form_values) {
          savedResult = { ...data.form_values };
          if (data.rubric_judgements) savedResult._rubric = data.rubric_judgements;
          if (data.rubric_notes) savedResult._rubricNotes = data.rubric_notes;
          if (data.element_tags) savedResult._element_tags = data.element_tags;
        } else {
          savedResult = data?.annotation_result || data?.result || data?.form_data || data?.draft || {};
        }
        setFormData(savedResult);
        if (savedResult._rubric) setRubricSelections(savedResult._rubric);
        if (savedResult._rubricNotes) setRubricNotes(savedResult._rubricNotes);
      }
      const rejectedReason = data?.review_reason || data?.rejected_reason || '';
      if (!submission || !submission.rejected_reason) setRejectedReason(rejectedReason);
      if (!submission || !submission.review_info) setReviewInfo(data?.review_info || (rejectedReason ? { comment: rejectedReason } : null));
      const isRework = data?.is_rework || data?.mode === 'rework' || data?.mode === 'rework_draft';
      if (isRework) setCurrentMode('revision');
      else if (data?.mode === 'draft' || data?.mode === 'drafting') setCurrentMode('draft');
      else setCurrentMode('new');

      // ── Resolve effective AI assist config ──
      const templateSchema = data?.template_schema || data?.schema || data?.schema_json || data?.template?.schema_json || null;
      const taskInfo = data?.task || data?.task_info || null;
      const dtType = data?.item_data?.dataset_type || templateSchema?.dataset_type || (data?.task_name?.includes('preference_compare') ? 'preference_compare' : 'qa_quality');
      const effectiveConfig = resolveEffectiveAiAssistConfig(taskInfo, { schema: templateSchema }, dtType);
      setAiAssistConfig(effectiveConfig);

      // ── Load latest labeler assist (no auto-run) ──
      const isLlmEnabled = data?.llm_assist_enabled !== false;
      setAiReview(null);
      setAiReviewExpired(false);
      setAiAssistSource('');
      if (itemId && (isLlmEnabled || canRunLabelerAssist(effectiveConfig))) {
        try {
          const latestResp = await getLatestAssist({
            item_id: itemId,
            task_id: taskId,
            trigger_type: 'labeler_assist_manual,labeler_assist_on_open',
          });
          if (latestResp?.found && latestResp?.result) {
            setAiReview(latestResp.result);
            setAiAssistSource('history');
          }
          // Auto-run DISABLED: only load history results, never auto-trigger LLM on page load
          // LLM assist only runs when user explicitly clicks the button
        } catch { /* latest assist query failed — show empty state */ }
      }
    } catch (error: any) {
      const isForbidden = error?.response?.status === 403;
      if (isForbidden) {
        showMessage.warning('当前题已提交或无权限，正在加载有效任务...');
        setCurrentItem(null); stopCurrentTimer(); stopHeartbeat(); setSubmission(null); setItemData(null); setFormData({});
        updateUrlParams({ item_id: null, task_id: null, submission_id: null, work_key: null, mode: null });
        try {
          await loadQueueItems();
          const freshQueue = queueItemsRef.current;
          if (freshQueue.length > 0) {
            await openWorkbenchItem({ id: freshQueue[0].id, task_id: freshQueue[0].task_id, work_key: freshQueue[0].work_key, submission_id: freshQueue[0].submission_id || freshQueue[0].annotation_id, status: freshQueue[0].effectiveStatus || freshQueue[0].status, is_rework: freshQueue[0].is_rework, mode: freshQueue[0].mode, review_reason: freshQueue[0].review_reason });
          } else showMessage.info('当前暂无可处理的标注任务');
        } catch (reloadError) { message.error('加载任务失败，请刷新页面重试'); }
      } else message.error('加载任务数据失败');
    }
  };

  const openWorkbenchItem = async (item: { id: number; task_id: number; status?: string; work_status?: string; mode?: string; is_rework?: boolean; duration_seconds?: number; annotation_result?: any; item_data?: any; schema_json?: any; rejected_reason?: string; review_reason?: string; review_comment?: string; review_time?: string; reviewer_id?: string; submission_id?: number; annotation_id?: number; work_key?: string; }) => {
    const itemId = item.id;
    const taskId = item.task_id;
    const workStatus = item.work_status || item.status || 'claimed';
    const isRework = item.is_rework || false;
    const mode = item.mode || (isRework ? 'rework' : (workStatus === 'draft' ? 'draft' : 'new'));
    const workKey = item.work_key;
    const submissionId = item.submission_id || item.annotation_id;

    if (!itemId) { message.error('当前题数据未加载完整，请刷新或重新领取'); return; }

    // 如果当前 session 对应同一个 item，直接复用（不关闭也不新建）
    // 这防止了路由切换回来时重复 open/close 导致计时丢失
    const isSameItem = currentItemIdRef.current === itemId && sessionId && sessionReadyRef.current && !sessionClosedRef.current;

    if (isSameItem && sessionOpeningRef.current) {
      return;
    }

    sessionOpeningRef.current = true;
    currentItemIdRef.current = itemId;
    currentWorkKeyRef.current = workKey || null;

    if (isSameItem) {
      // 同一个 item：不关闭现有 session，只恢复计时和 heartbeat
      sessionClosedRef.current = false;
      timerHydratedRef.current = false;

      // 从后端恢复 elapsed 时间
      try {
        const elapsedRes = await getElapsed({ task_id: taskId, item_id: itemId, labeler_id: 2, work_key: workKey || undefined });
        if (elapsedRes.success && elapsedRes.persisted_elapsed_seconds != null) {
          const persisted = elapsedRes.persisted_elapsed_seconds;
          baseElapsedRef.current = persisted;
          baseTimeRef.current = Date.now();
          setDurationSeconds(persisted);
          timerHydratedRef.current = true;
        }
      } catch (_) {}

      // 恢复 heartbeat
      if (sessionId) {
        startHeartbeat(sessionId);
      }

      sessionOpeningRef.current = false;
      return;
    }

    // 不同 item：需要关闭旧 session 并打开新 session
    sessionClosedRef.current = false;
    timerHydratedRef.current = false;
    sessionReadyRef.current = false;

    if (sessionId) {
      try { await closeWorkbenchSession({ session_id: sessionId, work_key: currentItem?.work_key, labeler_id: 2 }); } catch (e) {}
      setSessionId(null);
    }
    stopHeartbeat();
    stopCurrentTimer();

    const datasetItem: DatasetItem = { id: itemId, task_id: taskId, work_key: workKey, status: workStatus, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), raw_data_json: item.item_data || {} };
    if (workKey) setStoredCurrentItemId(itemId);

    try {
      let sessionRes: any = null;
      try {
        const currentRes = await getCurrentSession({ task_id: taskId, item_id: itemId, labeler_id: 2 });
        if (currentRes.success && currentRes.is_active && currentRes.session) {
          sessionRes = {
            success: true,
            session_id: currentRes.session.id,
            persisted_elapsed_seconds: currentRes.elapsed_seconds,
            status: 'resumed',
            session_status: 'active'
          };
        }
      } catch (_) {}

      if (!sessionRes) {
        sessionRes = await openWorkbenchSession({ task_id: taskId, item_id: itemId, labeler_id: 2, work_key: workKey, annotation_id: submissionId });
      }

      if (sessionRes.success) {
        const persisted = sessionRes.persisted_elapsed_seconds || 0;
        const cached = _loadTimerCache(workKey);
        // Use the larger of backend value and local cache
        const bestValue = Math.max(persisted, cached);
        baseElapsedRef.current = bestValue;
        baseTimeRef.current = Date.now();
        setDurationSeconds(bestValue);
        timerHydratedRef.current = true;
        _clearTimerCache(workKey);
        if (sessionRes.session_id) {
          setSessionId(sessionRes.session_id);
          setSessionStatus('active');
          sessionReadyRef.current = true;
          startHeartbeat(sessionRes.session_id);
        }
      } else {
        const cached = _loadTimerCache(workKey);
        if (cached > 0) {
          baseElapsedRef.current = cached;
          baseTimeRef.current = Date.now();
          setDurationSeconds(cached);
          timerHydratedRef.current = true;
        } else {
          // No cache, no session - show 0 but don't mark hydrated
          baseElapsedRef.current = 0;
          baseTimeRef.current = Date.now();
          setDurationSeconds(0);
        }
        setSessionStatus('none');
      }
    } catch (e) {
      const cached = _loadTimerCache(workKey);
      if (cached > 0) {
        baseElapsedRef.current = cached;
        baseTimeRef.current = Date.now();
        setDurationSeconds(cached);
        timerHydratedRef.current = true;
      } else {
        baseElapsedRef.current = 0;
        baseTimeRef.current = Date.now();
        setDurationSeconds(0);
      }
      setSessionStatus('none');
    } finally {
      sessionOpeningRef.current = false;
    }

    loadBackendLogs(taskId, itemId, workKey);
    updateUrlParams({ item_id: itemId, task_id: taskId, submission_id: submissionId || null, work_key: workKey || null, mode });
    const reviewReason = item.review_reason || item.rejected_reason || '';
    setCurrentItem(datasetItem); setSubmission(null); setRejectedReason(reviewReason);
    setReviewInfo(reviewReason ? { comment: reviewReason } : null);
    setRubricSelections({}); setRubricNotes({});
    if (isRework) setCurrentMode('revision');
    else if (workStatus === 'draft') setCurrentMode('draft');
    else setCurrentMode('new');
    if (item.annotation_result) {
      const result = item.annotation_result;
      setFormData(result);
      if (result._rubric) setRubricSelections(result._rubric);
      if (result._rubricNotes) setRubricNotes(result._rubricNotes);
    } else {
      setFormData({});
      setRubricSelections({});
      setRubricNotes({});
    }
    if (item.item_data) {
      setItemData({ item_data: item.item_data, schema_json: item.schema_json, annotation_result: item.annotation_result, rejected_reason: reviewReason, review_info: reviewReason ? { comment: reviewReason } : null, work_key: workKey, task_id: taskId, submission_id: submissionId });
    }
    if (!item.item_data || !item.schema_json) await loadItemData(datasetItem, workKey, submissionId);
  };

  const handleSelectItem = async (item: DatasetItem) => {
    await openWorkbenchItem({ id: item.id, task_id: item.task_id, status: item.status, work_status: item.work_status || item.effectiveStatus || item.annotation_status, mode: item.mode, is_rework: item.is_rework, duration_seconds: item.duration_seconds, annotation_result: item.annotation_result, rejected_reason: item.review_reason, review_reason: item.review_reason, submission_id: item.submission_id || item.annotation_id, work_key: item.work_key });
  };

  const handleFormChange = useCallback((values: Record<string, any>) => {
    if (import.meta.env.DEV) _perfCounters.formChange++;
    // Update ref immediately (for save/submit reads)
    formDataRef.current = values;
    // Debounce React state sync to 500ms — prevents re-render on every keystroke
    if (formSyncTimerRef.current) clearTimeout(formSyncTimerRef.current);
    formSyncTimerRef.current = setTimeout(() => {
      setFormData(values);
      setFormSyncTick(t => t + 1);
      if (missingFields.length > 0) setMissingFields([]);
      if (aiReview) setAiReviewExpired(true);
      formSyncTimerRef.current = null;
    }, 500);
  }, [missingFields.length, aiReview]);

  const handleSaveDraft = async () => {
    if (import.meta.env.DEV) _perfCounters.saveDraft++;
    if (!currentItem) return;
    const itemId = currentItem.id || currentItem.dataset_item_id;
    if (!itemId) { message.error('数据项ID不能为空'); return; }
    setSaving(true);
    try {
      const payload = { task_id: currentItem.task_id, dataset_item_id: itemId, labeler_id: 2, template_id: taskTemplateId || 10, data: formData, ai_review: aiReview || null, duration_seconds: getElapsedSeconds() };
      await saveDraft(payload);
      try {
        const isRework = currentMode === 'revision' || currentMode === 'rework' || currentItem?.is_rework;
        await saveDraftVersion(itemId, { task_id: currentItem.task_id, item_id: itemId, labeler_id: 2, work_key: currentItem.work_key || '', snapshot_json: formData, summary: `${isRework ? '返修' : ''}草稿保存 at ${formatDateTime(new Date().toISOString())}`, version_type: isRework ? 'rework_draft' : 'draft', operator_role: 'labeler' });
      } catch (e) { /* draft save failed silently */ }
      message.success('草稿保存成功');
      await loadQueueItems();
    } catch (error: any) {
      const errorMessage = error?.response?.data?.detail || error?.response?.data?.message || error?.message || '保存草稿失败';
      message.error(errorMessage);
    } finally { setSaving(false); }
  };

  const stopCurrentTimer = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  };

  const handleAiPrecheck = async () => {
    if (!currentItem) return;
    // Check effective config — block if labeler assist is disabled at task level
    if (!taskLlmAssistEnabled) {
      message.warning('当前任务未开启 LLM 辅助，请项目所有者在任务详情页开启。');
      return;
    }
    if (aiAssistConfig && !canRunLabelerAssist(aiAssistConfig) && !taskLlmAssistEnabled) {
      message.warning('该任务未开启标注员 LLM 辅助，请在任务详情页中开启');
      return;
    }
    setAiPrecheckLoading(true);
    try {
      const templateSchema = itemData?.template_schema || itemData?.schema || null;
      const result = await aiPrecheck({
        task_id: currentItem.task_id, dataset_item_id: currentItem.id || currentItem.dataset_item_id || 0,
        annotation_id: submission?.id, work_key: currentItem.work_key,
        item_data: itemData?.item_data, result_data: formData, labeler_id: 2, schema_json: templateSchema
      });
      // 始终更新 aiReview 为最新结果
      setAiReview(result);
      setAiReviewExpired(false);
      setAiAssistSource('live');

      // 判断是否真正成功：只要存在 score / run_id / status=success 就算成功
      const isRealSuccess = result.success !== false
        && (result.score != null || result.run_id != null || result.status === 'success' || result.status === 'completed');
      const hasFallback = result.fallback || result.fallback_used || result.used_fallback;

      if (!isRealSuccess && !hasFallback) {
        // 完全失败，无兜底
        const errMsg = formatAiError(result.error_type, result.error_message);
        message.warning(`AI 预审失败：${errMsg}，请继续人工标注`);
      } else if (hasFallback) {
        // 真实模型失败但 mock 兜底成功
        message.warning('真实模型暂不可用，已使用演示兜底结果');
      } else {
        // 真实模型成功
        const riskText = result.risk_level === 'high' ? '高风险' : result.risk_level === 'medium' ? '中风险' : '低风险';
        message.success(`AI 预审完成：${result.score}分，${riskText}`);
      }
    } catch (error: any) {
      // 区分超时/网络错误和其他错误
      const isTimeout = error?.code === 'ECONNABORTED' || error?.message?.includes('timeout');
      if (isTimeout) {
        message.warning('AI 预审请求超时，模型可能正在处理中，请稍后刷新查看结果');
      } else {
        message.warning('AI 预审请求失败，请继续人工标注');
      }
    } finally { setAiPrecheckLoading(false); }
  };

  const doSubmit = async () => {
    if (!currentItem || submitting) return;
    const submittedItemId = currentItem.id || currentItem.dataset_item_id;
    if (!submittedItemId) { message.error('数据项ID不能为空'); return; }
    setSubmitting(true);
    try {
      const payload = { task_id: currentItem.task_id, dataset_item_id: submittedItemId, labeler_id: 2, template_id: taskTemplateId || 10, data: formData, result: formData, annotation_result: formData, ai_review: aiReview || null, status: 'submitted', duration_seconds: getElapsedSeconds() };
      const response = await submitAnnotation(payload);
      const responseData = response as any;
      const success = responseData.success === true || responseData.status === 'submitted';
      const finalStatus = responseData.status || responseData.annotation?.status;
      if (success || finalStatus === 'submitted') {
        message.success(`已提交 Task #${currentItem.task_id} / Item #${submittedItemId}`);
        setTimeout(() => {
          message.info('AI Agent 已自动入队，可在"AI 审核 Agent"页面查看', 3);
        }, 800);
        stopCurrentTimer(); stopHeartbeat();
        if (sessionId) {
          try { await submitWorkbenchSession({ session_id: sessionId, work_key: currentItem.work_key, labeler_id: 2 }); } catch (e) {}
          setSessionId(null);
          sessionClosedRef.current = true;
        }
        setSessionStatus('submitted');
        localStorage.removeItem('labelhub_current_item_id');
        // 保存提交版本快照（fire-and-forget，不影响主流程）
        try {
          const isRework = currentMode === 'revision' || currentMode === 'rework' || currentItem?.is_rework;
          await saveDraftVersion(submittedItemId, { task_id: currentItem.task_id, item_id: submittedItemId, labeler_id: 2, work_key: currentItem.work_key || '', snapshot_json: formData, summary: `${isRework ? '返修' : ''}提交标注 at ${formatDateTime(new Date().toISOString())}`, version_type: isRework ? 'rework_submitted' : 'submitted', operator_role: 'labeler' });
        } catch (e) { /* version save failed silently */ }
        setQueueItems(prev => prev.filter(item => (item.id || item.dataset_item_id) !== submittedItemId));
        setCurrentItem(null); setSubmission(null); setItemData(null); setFormData({}); setDurationSeconds(0);
        setRejectedReason(''); setReviewInfo(null); setCurrentMode('new'); setAiReview(null);
        setRubricSelections({}); setRubricNotes({});
        updateUrlParams({ item_id: null, task_id: null, submission_id: null, work_key: null, mode: null });
        await loadQueueItems();
        const updatedQueue = queueItemsRef.current;
        if (updatedQueue.length > 0) {
          const nextItem = updatedQueue[0];
          await openWorkbenchItem({ id: nextItem.id, task_id: nextItem.task_id, work_key: nextItem.work_key, submission_id: nextItem.submission_id || nextItem.annotation_id, status: nextItem.effectiveStatus || nextItem.status, is_rework: nextItem.is_rework, mode: nextItem.mode, review_reason: nextItem.review_reason });
        }
      } else message.error('提交失败：后端未返回 submitted 状态');
    } catch (error: any) {
      const errData = error?.response?.data;
      const errDetail = typeof errData?.detail === 'object' ? errData.detail : null;
      if (errDetail?.code === 'REQUIRED_FIELDS_MISSING' || errData?.code === 'REQUIRED_FIELDS_MISSING') {
        const missingFieldLabels = errDetail?.missing_field_labels || errDetail?.missing_fields || errData?.missing_fields || [];
        const displayLabels = missingFieldLabels.length > 0 ? missingFieldLabels.join('、') : '部分必填项';
        message.warning(`请完成必填项：${displayLabels}`);
        const fieldKeys = errDetail?.missing_fields || [];
        if (fieldKeys.length > 0) setMissingFields(fieldKeys);
      } else {
        const errorMessage = errDetail?.message || errData?.message || error?.message || '提交失败';
        message.error(errorMessage);
      }
    } finally { setSubmitting(false); }
  };

  const handleSubmit = async () => {
    if (!currentItem || submitting) return;
    const templateSchema = itemData?.template_schema || itemData?.schema || itemData?.schema_json || itemData?.template?.schema_json || null;
    const missing = validateFormData(templateSchema, formData);
    if (missing.length > 0) {
      setMissingFields(missing);
      message.warning(`请完成必填项：${missing.join('、')}`);
      return;
    }
    setMissingFields([]);
    if (aiReview && aiReview.risk_level === 'high') {
      Modal.confirm({ title: 'AI 预审发现高风险问题', content: 'AI 预审发现高风险问题，仍要提交吗？', okText: '仍然提交', cancelText: '取消', onOk: () => doSubmit() });
      return;
    }
    doSubmit();
  };

  const handleClaimNewTask = async () => {
    try {
      setLoading(true);
      const responseData = await claimNext() as any;
      if (responseData.has_active && responseData.item) {
        const itemWorkKey = responseData.item.work_key || `${responseData.item.task_id}:${responseData.item.item_id || responseData.item.dataset_item_id}:2`;
        const fullWorkKey = itemWorkKey.split(':').length === 3 ? itemWorkKey : `${itemWorkKey}:2`;
        const correctedItem = { ...responseData.item, work_key: fullWorkKey };
        await openWorkbenchItem(correctedItem);
        await loadQueueItems();
        if (responseData.success) message.success('领取成功');
        else message.info('已为你打开当前进行中的任务');
        return;
      }
      if (responseData.item) {
        const itemWorkKey = responseData.item.work_key || `${responseData.item.task_id}:${responseData.item.item_id || responseData.item.dataset_item_id}:2`;
        const fullWorkKey = itemWorkKey.split(':').length === 3 ? itemWorkKey : `${itemWorkKey}:2`;
        const correctedItem = { ...responseData.item, work_key: fullWorkKey };
        await openWorkbenchItem(correctedItem);
        await loadQueueItems();
        message.success('领取成功');
        return;
      }
      showMessage.warning('当前任务下暂无可领取数据，请切换任务或重置演示数据');
    } catch (error: any) {
      const errData = error?.response?.data;
      if (errData?.code === 'NO_AVAILABLE_ITEM') showMessage.warning(errData.message || '当前任务下暂无可领取数据');
      else message.error(errData?.detail || errData?.message || error?.message || '领取任务失败');
    } finally { setLoading(false); }
  };

  const [skipLoading, setSkipLoading] = useState(false);

  const handleSkipItem = async () => {
    if (!currentItem || skipLoading) return;
    const skippedItemId = currentItem.id || currentItem.dataset_item_id || 0;
    setSkipLoading(true);
    try {
      stopCurrentTimer(); 
      stopHeartbeat();
      
      // 1. 关闭当前 session
      if (sessionId) {
        try { 
          await closeWorkbenchSession({ 
            session_id: sessionId, 
            work_key: currentItem.work_key, 
            labeler_id: 2 
          }); 
        } catch (e) {}
        setSessionId(null);
        sessionClosedRef.current = true;
      }
      setSessionStatus('stopped');
      
      // 2. 调用后端 skip API（后端返回 next_item）
      const skipRes = await skipItem({ 
        task_id: currentItem.task_id, 
        item_id: skippedItemId, 
        labeler_id: 2, 
        work_key: currentItem.work_key || '' 
      });
      
      message.success('已跳过当前题目');
      localStorage.removeItem('labelhub_current_item_id');
      
      // 3. 清空当前状态
      setCurrentItem(null);
      setSubmission(null);
      setItemData(null);
      setFormData({});
      setDurationSeconds(0);
      setRejectedReason('');
      setReviewInfo(null);
      setCurrentMode('new');
      setAiReview(null);
      setRubricSelections({});
      setRubricNotes({});
      updateUrlParams({ 
        item_id: null, 
        task_id: null, 
        submission_id: null, 
        work_key: null, 
        mode: null 
      });
      
      // 4. 刷新队列（确保左侧不再高亮已跳过 item）
      await loadQueueItems();
      
      // 5. 使用后端返回的 next_item，带防回流校验
      const nextItemFromServer = skipRes?.next_item;
      if (nextItemFromServer && nextItemFromServer.id !== skippedItemId) {
        // 后端返回了有效的下一题且不是刚跳过的：打开它
        await openWorkbenchItem({ 
          id: nextItemFromServer.id, 
          task_id: nextItemFromServer.task_id, 
          work_key: nextItemFromServer.work_key, 
          submission_id: nextItemFromServer.annotation_id, 
          status: nextItemFromServer.status || 'unclaimed', 
          is_rework: false, 
          mode: 'new', 
          review_reason: undefined 
        });
      } else {
        // 无下一题或防回流失败：显示空状态
        message.info('当前队列已完成，暂无可标注数据');
      }
      
    } catch (error: any) {
      message.error(error?.message || '跳过失败');
    } finally { 
      setSkipLoading(false); 
    }
  };

  const handleMarkInvalid = async () => {
    if (!currentItem || markInvalidLoading) return;
    const reason = markInvalidReason;
    const remark = markInvalidRemark;
    if (!reason?.trim()) { message.warning('请选择无效原因'); return; }
    if (reason === '其他' && !remark?.trim()) { message.warning('选择"其他"时备注必填'); return; }
    setMarkInvalidLoading(true);
    try {
      stopCurrentTimer(); stopHeartbeat();
      if (sessionId) {
        try { await closeWorkbenchSession({ session_id: sessionId, work_key: currentItem.work_key, labeler_id: 2 }); } catch (e) {}
        setSessionId(null);
        sessionClosedRef.current = true;
      }
      setSessionStatus('stopped');
      const itemId = currentItem.id || currentItem.dataset_item_id || 0;
      await markItemInvalid({
        task_id: currentItem.task_id,
        item_id: itemId,
        dataset_item_id: itemId,
        labeler_id: 2,
        work_key: currentItem.work_key || '',
        invalid_reason: reason,
        invalid_remark: remark
      });
      message.success('已标记为无效，等待审核');
      setMarkInvalidModalVisible(false);
      setMarkInvalidReason('');
      setMarkInvalidRemark('');
      localStorage.removeItem('labelhub_current_item_id');
      setQueueItems(prev => prev.filter(item => (item.id || item.dataset_item_id) !== itemId));
      setCurrentItem(null); setSubmission(null); setItemData(null); setFormData({}); setDurationSeconds(0);
      setRejectedReason(''); setReviewInfo(null); setCurrentMode('new'); setAiReview(null);
      setRubricSelections({}); setRubricNotes({});
      updateUrlParams({ item_id: null, task_id: null, submission_id: null, work_key: null, mode: null });
      await loadQueueItems();
      const updatedQueue = queueItemsRef.current;
      if (updatedQueue.length > 0) {
        const nextItem = updatedQueue[0];
        await openWorkbenchItem({ id: nextItem.id, task_id: nextItem.task_id, work_key: nextItem.work_key, submission_id: nextItem.submission_id || nextItem.annotation_id, status: nextItem.effectiveStatus || nextItem.status, is_rework: nextItem.is_rework, mode: nextItem.mode, review_reason: nextItem.review_reason });
      }
    } catch (error: any) {
      message.error(error.message || '标记无效失败，请检查后端服务');
    } finally {
      setMarkInvalidLoading(false);
    }
  };

  const handleEndSession = async () => {
    Modal.confirm({
      title: '确认结束做题？', content: '结束后将关闭当前工作会话并返回任务列表。',
      okText: '确认结束', cancelText: '取消',
      onOk: async () => {
      if (sessionId) {
        try { await closeWorkbenchSession({ session_id: sessionId, work_key: currentItem?.work_key, labeler_id: 2 }); } catch (e) {}
        setSessionId(null);
        sessionClosedRef.current = true;
      }
      setSessionStatus('stopped');
      stopCurrentTimer(); stopHeartbeat();
        navigate('/owner/tasks');
      }
    });
  };

  const handleLoadNextItem = async () => {
    await loadQueueItems();
    const updatedQueue = queueItemsRef.current;
    if (updatedQueue.length > 0) {
      const nextItem = updatedQueue[0];
      await openWorkbenchItem({ id: nextItem.id, task_id: nextItem.task_id, work_key: nextItem.work_key, submission_id: nextItem.submission_id || nextItem.annotation_id, status: nextItem.effectiveStatus || nextItem.status, is_rework: nextItem.is_rework, mode: nextItem.mode, review_reason: nextItem.review_reason });
    } else {
      message.info('当前暂无可处理的标注任务');
    }
  };

  const loadVersions = async (itemId: number) => {
    setVersionsLoading(true);
    try {
      const res = await getDraftVersions(itemId, { work_key: currentItem?.work_key, labeler_id: 2 });
      const versionList = res.versions || res.items || res.data || [];
      setVersions(Array.isArray(versionList) ? versionList : []);
    } catch (_) {
      setVersions([]);
    } finally { setVersionsLoading(false); }
  };

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen();
    else document.exitFullscreen();
  };

  keyboardHandlersRef.current = { saveDraft: handleSaveDraft, aiPrecheck: handleAiPrecheck, submit: handleSubmit, nextItem: handleLoadNextItem };

  // Memoized JSON preview to avoid re-stringifying on every render
  // formDataJsonPreview and formDataEntries removed — old right panel no longer used
  // Memoized form schema for FormRenderer
  const formSchema = useMemo(() => itemData?.schema_json || itemData?.template?.schema_json || itemData?.template_schema || itemData?.schema, [itemData?.schema_json, itemData?.template?.schema_json, itemData?.template_schema, itemData?.schema]);
  // Memoized item data for FormRenderer
  const formItemData = useMemo(() => itemData?.item_data || itemData?.raw_data_json, [itemData?.item_data, itemData?.raw_data_json]);
  // Memoized AI review normalization (called in 3+ places during render)
  const normalizedAiReview = useMemo(() => aiReview ? normalizeAiReview(aiReview) : null, [aiReview]);

  const isRevision = (currentMode === 'revision' || submission?.status === 'rejected_to_modify' || currentItem?.effectiveStatus === 'rejected_to_modify' || currentItem?.work_status === 'rejected_to_modify' || currentItem?.status === 'rejected_to_modify' || currentItem?.is_rework === true || !!rejectedReason);
  const currentStatus = submission?.status || currentItem?.work_status || currentItem?.effectiveStatus || currentItem?.annotation_status || currentItem?.status || '';
  const isApproved = currentStatus === 'approved' || currentItem?.status === 'approved';

  const getModeLabel = () => {
    switch (currentMode) { case 'revision': return '返修任务'; case 'draft': return '草稿编辑'; case 'readonly': return '只读查看'; default: return '新标注'; }
  };
  const getModeColor = () => {
    switch (currentMode) { case 'revision': return 'orange'; case 'draft': return 'gray'; case 'readonly': return 'default'; default: return 'blue'; }
  };



  const charCount = (text: any): number => {
    if (!text) return 0;
    return typeof text === 'string' ? text.length : String(text).length;
  };

  // 检测当前 item 是否为 preference_compare 类型
  const isPreferenceCompareItem = useMemo(() => {
    const dt = itemData?.item_data?.dataset_type || itemData?.raw_data_json?.dataset_type || currentItem?.raw_data_json?.dataset_type;
    if (dt === 'preference_compare') return true;
    if (itemData?.item_data?.response_a !== undefined || itemData?.raw_data_json?.response_a !== undefined) return true;
    return (currentItem?.task_name || '').includes('preference_compare');
  }, [itemData, currentItem]);

  const renderRawDataContent = () => {
    if (!itemData?.item_data) {
      return itemData?.item_data_missing ? <Alert message="原始数据快照缺失" type="warning" showIcon /> : <Empty description="暂无原始数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
    }
    const data = itemData.item_data;
    const prompt = data.prompt || data.question || '暂无';

    if (isPreferenceCompareItem) {
      const responseA = data.response_a || '暂无';
      const responseB = data.response_b || '暂无';
      return (
        <div style={{ fontSize: 13 }}>
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><strong>用户问题 (prompt)：</strong><span style={{ fontSize: 11, color: '#999' }}>{charCount(prompt)} 字符</span></div>
            <p style={{ margin: '4px 0', color: '#333', maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{prompt}</p>
          </div>
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><strong>回答 A：</strong><span style={{ fontSize: 11, color: '#999' }}>{charCount(responseA)} 字符</span></div>
            <pre style={{ margin: '4px 0', color: '#333', maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap', backgroundColor: '#e6f7ff', padding: 8, borderRadius: 4, fontSize: 12 }}>{responseA}</pre>
          </div>
          <div style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><strong>回答 B：</strong><span style={{ fontSize: 11, color: '#999' }}>{charCount(responseB)} 字符</span></div>
            <pre style={{ margin: '4px 0', color: '#333', maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap', backgroundColor: '#fff7e6', padding: 8, borderRadius: 4, fontSize: 12 }}>{responseB}</pre>
          </div>
          {(data.model_a || data.model_b) && (
            <div style={{ display: 'flex', gap: 8, fontSize: 12 }}>
              {data.model_a && <Tag color="blue">Model A: {data.model_a}</Tag>}
              {data.model_b && <Tag color="orange">Model B: {data.model_b}</Tag>}
            </div>
          )}
        </div>
      );
    }

    const modelAnswer = data.model_answer || data.answer || '暂无';
    const reference = data.reference || data.reference_answer || '暂无';
    return (
      <div style={{ fontSize: 13 }}>
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><strong>问题：</strong><span style={{ fontSize: 11, color: '#999' }}>{charCount(prompt)} 字符</span></div>
          <p style={{ margin: '4px 0', color: '#333', maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{prompt}</p>
        </div>
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><strong>待评估模型回答：</strong><span style={{ fontSize: 11, color: '#999' }}>{charCount(modelAnswer)} 字符</span></div>
          <p style={{ margin: '4px 0', color: '#333', maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{modelAnswer}</p>
        </div>
        <div style={{ marginBottom: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><strong>参考答案：</strong><span style={{ fontSize: 11, color: '#999' }}>{charCount(reference)} 字符</span></div>
          <p style={{ margin: '4px 0', color: '#333', maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{reference}</p>
        </div>
        <div style={{ display: 'flex', gap: 16, fontSize: 12, color: '#666' }}><span>类别：{itemData.item_data.category || '-'}</span><span>难度：{itemData.item_data.difficulty || '-'}</span></div>
      </div>
    );
  };

  const renderMarkdownContent = () => {
    if (!itemData?.item_data) return <Empty description="暂无原始数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
    const prompt = itemData.item_data.prompt || itemData.item_data.question || '';
    const modelAnswer = itemData.item_data.model_answer || itemData.item_data.answer || '';
    const reference = itemData.item_data.reference || itemData.item_data.reference_answer || '';
    return (
      <div style={{ fontSize: 13, fontFamily: 'monospace' }}>
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><strong style={{ fontFamily: 'inherit' }}>## 问题</strong><span style={{ fontSize: 11, color: '#999' }}>{charCount(prompt)} 字符</span></div>
          <pre style={{ margin: '4px 0', color: '#333', maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap', backgroundColor: '#f6f8fa', padding: 8, borderRadius: 4, fontSize: 12 }}>{prompt || '暂无'}</pre>
        </div>
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><strong style={{ fontFamily: 'inherit' }}>## 待评估模型回答</strong><span style={{ fontSize: 11, color: '#999' }}>{charCount(modelAnswer)} 字符</span></div>
          <pre style={{ margin: '4px 0', color: '#333', maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap', backgroundColor: '#f6f8fa', padding: 8, borderRadius: 4, fontSize: 12 }}>{modelAnswer || '暂无'}</pre>
        </div>
        <div style={{ marginBottom: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><strong style={{ fontFamily: 'inherit' }}>## 参考答案</strong><span style={{ fontSize: 11, color: '#999' }}>{charCount(reference)} 字符</span></div>
          <pre style={{ margin: '4px 0', color: '#333', maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap', backgroundColor: '#f6f8fa', padding: 8, borderRadius: 4, fontSize: 12 }}>{reference || '暂无'}</pre>
        </div>
      </div>
    );
  };

  // renderAiReviewCard removed — old right panel replaced by SimpleLLMResultPanel + OptimizedRubricPanel

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '50px' }}><Spin size="large" /></div>
      ) : !currentItem ? (
        <div style={{ textAlign: 'center', padding: '100px' }}>
          <Empty description="暂无可处理标注项，可返回任务市场领取新任务" />
          <div style={{ marginTop: '24px', display: 'flex', gap: '12px', justifyContent: 'center' }}>
            <Button type="primary" size="large" icon={<PlusCircleOutlined />} onClick={handleClaimNewTask}>领取一条新任务</Button>
            <Button size="large" onClick={async () => { try { const res = await resetDemoData(); if (res.success) { message.success('演示数据已重置'); Object.keys(localStorage).forEach(key => { if (key.startsWith('labelhub_timer_') || key.startsWith('labelhub_current_')) localStorage.removeItem(key); }); await fetchCurrentTask(); } else message.error(res.message || '重置失败'); } catch (e: any) { message.error('重置演示数据失败'); } }}>重置演示数据</Button>
            <Button size="large" onClick={async () => { try { const res = await seedMoreItems(); if (res.success) { message.success(res.message || '已追加数据'); await fetchCurrentTask(); } else message.error(res.message || '追加失败'); } catch (e: any) { message.error('追加数据失败'); } }}>追加可领取数据</Button>
          </div>
        </div>
      ) : (
        <>
          <div style={{ flexShrink: 0, backgroundColor: '#001529', color: '#fff', padding: '0 16px', height: 48, display: 'flex', alignItems: 'center', gap: 12, fontSize: 13, zIndex: 200 }}>
            <Button type="text" size="small" icon={<ArrowLeftOutlined />} style={{ color: '#fff', padding: '0 8px' }} onClick={() => navigate(`/owner/tasks/${currentItem?.task_id}`)}>返回任务详情</Button>
            <div style={{ width: 1, height: 24, backgroundColor: 'rgba(255,255,255,0.2)' }} />
            <span style={{ fontWeight: 500 }}>{itemData?.task_name || currentItem?.task_name || `Task #${currentItem?.task_id}`}</span>
            <Tag color="blue" style={{ margin: 0, fontSize: 11 }}>{itemData?.task_no || `T-${currentItem?.task_id}`}</Tag>
            {currentTemplateName && (
              <Tooltip title={`当前模板: ${currentTemplateName} #${taskTemplateId || ''} (v${currentTemplateVersion || '1.0'})`}>
                <Tag color="cyan" style={{ margin: 0, fontSize: 11, cursor: 'default' }}>
                  模板: {currentTemplateName.length > 12 ? currentTemplateName.slice(0, 12) + '...' : currentTemplateName}
                  {taskTemplateId ? ` #${taskTemplateId}` : ''}
                </Tag>
              </Tooltip>
            )}
            <div style={{ width: 1, height: 24, backgroundColor: 'rgba(255,255,255,0.2)' }} />
            <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.65)' }}>Item Key:</span>
            <span style={{ fontSize: 12, fontFamily: 'monospace' }}>{currentItem?.work_key || '-'}</span>
            <div style={{ width: 1, height: 24, backgroundColor: 'rgba(255,255,255,0.2)' }} />
            <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.65)' }}>明细ID:</span>
            <span style={{ fontSize: 12 }}>#{currentItem?.id}</span>
            <div style={{ width: 1, height: 24, backgroundColor: 'rgba(255,255,255,0.2)' }} />
            <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.65)' }}>轮次:</span>
            <span style={{ fontSize: 12 }}>{itemData?.round_no || 1} / {itemData?.total_rounds || 1} 轮</span>
            <div style={{ flex: 1 }} />
            <WorkbenchTimerDisplay getElapsed={getElapsedSeconds} />
            {sessionStatus === 'active' && <Tag color="green" style={{ fontSize: 10, margin: 0 }}>计时中</Tag>}
            {sessionStatus === 'paused' && <Tag color="orange" style={{ fontSize: 10, margin: 0 }}>已暂停</Tag>}
            {sessionStatus === 'stopped' && <Tag color="red" style={{ fontSize: 10, margin: 0 }}>已停止</Tag>}
            {sessionStatus === 'submitted' && <Tag color="blue" style={{ fontSize: 10, margin: 0 }}>已提交</Tag>}
            <div style={{ width: 1, height: 24, backgroundColor: 'rgba(255,255,255,0.2)' }} />
            <Tooltip title="答题记录">
              <Button type="text" size="small" icon={<FileTextOutlined />} style={{ color: 'rgba(255,255,255,0.85)', padding: '0 8px' }} onClick={() => { loadBackendLogs(currentItem.task_id, currentItem.id, currentItem.work_key); setLogsDrawerTab('logs'); setShowLogs(true); }}>答题记录</Button>
            </Tooltip>
            <Tooltip title="操作日志">
              <Button type="text" size="small" icon={<HistoryOutlined />} style={{ color: 'rgba(255,255,255,0.85)', padding: '0 8px' }} onClick={() => { loadBackendLogs(currentItem.task_id, currentItem.id, currentItem.work_key); setLogsDrawerTab('logs'); setShowLogs(true); }}>操作日志</Button>
            </Tooltip>
            <Tooltip title={isFullscreen ? '退出全屏' : '全屏'}>
              <Button type="text" size="small" icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />} style={{ color: 'rgba(255,255,255,0.85)', padding: '0 8px' }} onClick={toggleFullscreen}>{isFullscreen ? '退出全屏' : '全屏'}</Button>
            </Tooltip>
            <Tooltip title="返回上一页">
              <Button type="text" size="small" icon={<ArrowLeftOutlined />} style={{ color: 'rgba(255,255,255,0.85)', padding: '0 8px' }} onClick={() => navigate(-1)}>返回</Button>
            </Tooltip>
            <Button type="text" size="small" danger icon={<StopOutlined />} style={{ color: '#ff4d4f', padding: '0 8px' }} onClick={handleEndSession}>结束做题</Button>
          </div>

          {(isRevision || currentMode === 'revision') && rejectedReason && (
            <div style={{ flexShrink: 0, padding: '8px 16px', borderLeft: '4px solid #fa8c16', backgroundColor: '#fff7e6' }}>
              <div style={{ color: '#fa8c16', fontWeight: 'bold', marginBottom: '4px' }}>⚠️ 审核退回意见</div>
              <div>{rejectedReason}</div>
              {reviewInfo?.comment && reviewInfo.comment !== rejectedReason && <div style={{ marginTop: 4, fontSize: 13, color: '#666' }}>审核员备注：{reviewInfo.comment}</div>}
              {reviewInfo && <div style={{ marginTop: '4px', fontSize: '12px', color: '#666' }}>审核时间：{formatDateTime(reviewInfo.reviewed_at || '')} | 审核员ID：#{reviewInfo.reviewer_id || '未知'}</div>}
            </div>
          )}

          <div style={{ flex: 1, overflow: 'hidden', display: 'flex', gap: 12, padding: '8px 12px' }}>
            <div style={{ width: 280, flexShrink: 0, overflow: 'auto' }}>
              <Card title="标注队列" size="small" style={{ marginBottom: 12 }}>
                {queueItems.length === 0 ? <Empty description="暂无任务" image={Empty.PRESENTED_IMAGE_SIMPLE} /> : (
                  <div>
                    {queueItems.map((item) => {
                      const isSelected = (item.work_key && currentItem.work_key && item.work_key === currentItem.work_key) || (!item.work_key || !currentItem.work_key) && item.id === currentItem.id && item.task_id === currentItem.task_id;
                      const itemStatus = item.work_status || item.effectiveStatus || item.annotation_status || item.status;
                      const isRework = item.is_rework || item.mode === 'rework' || item.mode === 'rework_draft';
                      const reactKey = item.work_key || `${item.task_id}:${item.id}:2`;
                      return (
                        <div key={reactKey} onClick={() => handleSelectItem(item)} style={{ padding: '8px 10px', marginBottom: '6px', borderRadius: '6px', cursor: 'pointer', backgroundColor: isSelected ? '#e6f7ff' : '#fafafa', borderLeft: isSelected ? '3px solid #1890ff' : (isRework ? '3px solid #ff4d4f' : '3px solid transparent'), transition: 'all 0.2s', fontSize: 12 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ fontWeight: 600, fontSize: 12 }}>{isRework ? '🔧 ' : ''}Item #{item.id}</div>
                            <RightOutlined style={{ color: isSelected ? '#1890ff' : '#ccc', fontSize: 10 }} />
                          </div>
                          <div style={{ marginTop: 4 }}>
                            <Tag color={isRework ? 'red' : getStatusColor(itemStatus)} style={{ fontSize: 11, lineHeight: '16px', padding: '0 4px' }}>{isRework ? '待返修' : getStatusLabel(itemStatus)}</Tag>
                            {item.review_reason && <Tag color="orange" style={{ fontSize: 11, lineHeight: '16px', padding: '0 4px', marginLeft: 2 }}>有意见</Tag>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </Card>
              <Card title="Item 信息" size="small">
                <div style={{ fontSize: 12 }}>
                  {[
                    { label: 'Official ID', value: itemData?.item_data?.official_id || itemData?.raw_data_json?.official_id || itemData?.item_data?.external_id || '-' },
                    { label: 'Item Key', value: currentItem?.work_key || '-' },
                    { label: 'Pack ID', value: itemData?.item_data?.pack_id || '-' },
                    { label: 'Category', value: itemData?.item_data?.category || itemData?.raw_data_json?.category || '-' },
                    { label: 'Difficulty', value: itemData?.item_data?.difficulty || itemData?.raw_data_json?.difficulty || '-' },
                    { label: 'Lang', value: itemData?.item_data?.lang || itemData?.raw_data_json?.lang || '-' },
                    { label: 'Media Type', value: itemData?.item_data?.media_type || itemData?.raw_data_json?.media_type || '-' },
                    { label: 'Supplier', value: itemData?.item_data?.supplier || '-' },
                    { label: 'Is Valid', value: itemData?.item_data?.is_valid != null ? String(itemData.item_data.is_valid) : '-' },
                  ].map(row => (
                    <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #f0f0f0' }}>
                      <span style={{ color: '#999' }}>{row.label}</span>
                      <span style={{ fontWeight: 500 }}>{row.value}</span>
                    </div>
                  ))}
                  {/* expected_dimensions */}
                  {(() => {
                    const dims = itemData?.item_data?.expected_dimensions || itemData?.raw_data_json?.expected_dimensions || itemData?.item_data?.tags || itemData?.raw_data_json?.tags;
                    if (dims && Array.isArray(dims) && dims.length > 0) {
                      return (
                        <div style={{ padding: '6px 0 2px' }}>
                          <span style={{ color: '#999', fontSize: 11 }}>重点维度</span>
                          <div style={{ marginTop: 2 }}>
                            {dims.map((d: string, i: number) => (
                              <Tag key={i} color="blue" style={{ fontSize: 10, marginBottom: 2 }}>{d}</Tag>
                            ))}
                          </div>
                        </div>
                      );
                    }
                    return null;
                  })()}
                </div>
              </Card>
            </div>

            <div style={{ flex: 1, minWidth: 0, overflow: 'auto', paddingRight: 4 }}>
              <Card size="small" style={{ marginBottom: 12 }}>
                <Tabs activeKey={contentTab} onChange={setContentTab} size="small" items={[
                  { key: 'raw', label: '原始数据', children: ENABLE_RAW_DATA_VIEW ? renderRawDataContent() : <div style={{ color: '#999', padding: 8 }}>已禁用</div> },
                  { key: 'markdown', label: 'Markdown', children: ENABLE_RAW_DATA_VIEW ? renderMarkdownContent() : <div style={{ color: '#999', padding: 8 }}>已禁用</div> },
                ]} />
              </Card>
              <Card title="标注表单" size="small">
                {(() => {
                  const hasFields = formSchema && formSchema.fields && formSchema.fields.length > 0;
                  if (hasFields) return <FormRenderer schema={formSchema} itemData={formItemData} value={formData} onChange={handleFormChange} readonly={isPaused} missingFields={missingFields} aiAssistText={itemData?.ai_assist_text || ''} />;
                  else if (itemData) return <Alert message="未加载到模板字段 schema" type="error" showIcon />;
                  else return <div style={{ textAlign: 'center', padding: '20px' }}><Spin size="default" /></div>;
                })()}
              </Card>
              {ENABLE_SIMPLE_LLM_RESULT_PANEL && (
                <SimpleLLMResultPanel aiReview={aiReview} loading={aiPrecheckLoading} taskLlmAssistEnabled={taskLlmAssistEnabled} />
              )}
            </div>

            {ENABLE_RIGHT_RUBRIC_PANEL && (
              <OptimizedRubricPanel
                rubricItems={rubricItems}
                category={itemData?.item_data?.category}
                difficulty={itemData?.item_data?.difficulty}
                statusText={isApproved ? '已通过' : isRevision ? '待返修' : currentStatus === 'submitted' ? '已提交' : currentStatus === 'draft' ? '草稿' : '标注中'}
                statusColor={isApproved ? 'green' : isRevision ? 'orange' : currentStatus === 'submitted' ? 'blue' : currentStatus === 'draft' ? 'gray' : 'default'}
                modeText={getModeLabel()}
                modeColor={getModeColor()}
              />
            )}
          </div>

          <div style={{ flexShrink: 0, backgroundColor: '#fff', borderTop: '1px solid #e8e8e8', padding: '10px 16px', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 12, zIndex: 100, boxShadow: '0 -2px 8px rgba(0,0,0,0.06)' }}>
            <Tooltip title="暂停标注">
              <Button onClick={() => setIsPaused(true)} icon={<PauseCircleOutlined />} disabled={isApproved}>暂停</Button>
            </Tooltip>
            <Tooltip title="跳过当前题目 (Alt+N)">
              <Button icon={<ForwardOutlined />} onClick={handleSkipItem} loading={skipLoading} disabled={isPaused || isApproved}>跳过</Button>
            </Tooltip>
            <Tooltip title="标记当前题目为无效">
              <Button icon={<WarningOutlined />} onClick={() => setMarkInvalidModalVisible(true)} disabled={isPaused || isApproved}>标记无效</Button>
            </Tooltip>
            <Tooltip title="保存草稿 (Ctrl+S)">
              <Button loading={saving} onClick={handleSaveDraft} disabled={isPaused || isApproved || currentStatus === 'submitted'}>保存</Button>
            </Tooltip>
            <Tooltip title={isApproved ? '已通过，不可再次提交' : currentStatus === 'submitted' ? '已提交，如需修改请等待审核打回' : '提交并继续标注 (Alt+C)'}>
              <Button type="primary" loading={submitting} onClick={handleSubmit} disabled={isPaused || isApproved || currentStatus === 'submitted'}>
                {isApproved ? '已通过' : isRevision ? '提交返修' : currentStatus === 'submitted' ? '已提交' : '提交并继续标注'}
              </Button>
            </Tooltip>
            {ENABLE_LLM_ASSIST_BUTTON && <>
              <Tooltip title={
                !taskLlmAssistEnabled
                  ? "当前任务未开启 LLM 辅助，请项目所有者在任务详情页开启"
                  : aiAssistConfig && !canRunLabelerAssist(aiAssistConfig) && !taskLlmAssistEnabled
                  ? "当前任务已开启 LLM 辅助，但模型 Provider 未配置"
                  : isPreferenceCompareItem
                    ? "LLM 辅助：基于用户问题、回答 A、回答 B 独立判断偏好，结果仅供参考 (Alt+A)"
                    : "LLM 辅助：基于题目、模型回答、参考答案判断标注是否合理 (Alt+A)"
              }>
                <Button
                  loading={aiPrecheckLoading}
                  onClick={handleAiPrecheck}
                  disabled={isPaused || isApproved || !taskLlmAssistEnabled}
                  icon={<ExclamationCircleOutlined />}
                >
                  LLM 辅助
                  {aiReview && !aiPrecheckLoading && normalizedAiReview && normalizedAiReview.score != null ? <Tag color={normalizedAiReview.riskLevel === 'high' ? 'red' : normalizedAiReview.riskLevel === 'medium' ? 'orange' : 'green'} style={{ marginLeft: 4, fontSize: 10 }}>{normalizedAiReview.score}分</Tag> : null}
                </Button>
              </Tooltip>
              {aiAssistSource === 'history' && <span style={{ fontSize: 10, color: '#1890ff' }}>历史 LLM 辅助结果</span>}
              <span style={{ fontSize: 10, color: '#999', maxWidth: 120, lineHeight: '1.2' }}>该结果仅供标注员作答参考，不作为正式审核依据</span>
            </>}
          </div>
        </>
      )}

      {isPaused && (
        <Modal open={isPaused} footer={null} closable={false} maskStyle={{ backgroundColor: 'rgba(0, 0, 0, 0.8)' }} styles={{ body: { textAlign: 'center', padding: '60px' } }}>
          <PauseCircleOutlined style={{ fontSize: '64px', color: '#1890ff', marginBottom: '16px' }} />
          <h2 style={{ fontSize: '24px', marginBottom: '16px' }}>已暂停</h2>
          <p style={{ marginBottom: '24px' }}>你可以稍后继续标注任务</p>
          <Button type="primary" size="large" icon={<PlayCircleOutlined />} onClick={() => setIsPaused(false)}>继续做题</Button>
        </Modal>
      )}

      <Modal
        title="标记无效"
        open={markInvalidModalVisible}
        onCancel={() => { setMarkInvalidModalVisible(false); setMarkInvalidReason(''); setMarkInvalidRemark(''); }}
        onOk={handleMarkInvalid}
        okText="确认标记"
        cancelText="取消"
        confirmLoading={markInvalidLoading}
      >
        <div style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 8, fontWeight: 500 }}>请选择无效原因：</div>
          <Radio.Group value={markInvalidReason} onChange={(e) => setMarkInvalidReason(e.target.value)}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <Radio value="题目缺失">题目缺失</Radio>
              <Radio value="模型回答为空">模型回答为空</Radio>
              <Radio value="数据重复">数据重复</Radio>
              <Radio value="不符合任务范围">不符合任务范围</Radio>
              <Radio value="内容无法判断">内容无法判断</Radio>
              <Radio value="其他">其他</Radio>
            </div>
          </Radio.Group>
        </div>
        <div style={{ marginBottom: 8 }}>
          <div style={{ marginBottom: 4, fontWeight: 500, color: markInvalidReason === '其他' && !markInvalidRemark?.trim() ? '#ff4d4f' : undefined }}>
            备注{markInvalidReason === '其他' ? '（必填）' : '（可选）'}：
          </div>
          <TextArea
            rows={3}
            placeholder={markInvalidReason === '其他' ? '请输入具体原因' : '可选输入补充说明'}
            value={markInvalidRemark}
            onChange={(e) => setMarkInvalidRemark(e.target.value)}
          />
        </div>
      </Modal>

      <Drawer
        title={`工作记录 - ${currentItem ? `Task #${currentItem.task_id} / Item #${currentItem.id}` : ''}`}
        placement="right" onClose={() => setShowLogs(false)} open={showLogs} width={520}
      >
        <Tabs activeKey={logsDrawerTab} onChange={(key) => { setLogsDrawerTab(key); if (key === 'versions' && currentItem?.id) loadVersions(currentItem.id); }} items={[
          {
            key: 'logs',
            label: '操作日志',
            children: logs.length === 0 ? <Empty description="暂无操作日志" /> : (
              <Timeline items={logs.map((log) => ({
                key: log.id,
                color: log.action?.includes('failed') ? 'red' : log.action?.includes('success') ? 'green' : 'blue',
                children: (
                  <>
                    <div style={{ marginBottom: '4px' }}>
                      <strong>{log.action_label || log.action}</strong>
                      <span style={{ marginLeft: '8px', color: '#999', fontSize: '12px' }}>{formatDateTime(log.created_at)}</span>
                    </div>
                    {log.message && <div style={{ fontSize: '12px', color: '#666' }}>{log.message}</div>}
                    {log.payload_json && log.payload_json.accumulated_seconds != null && <div style={{ fontSize: '12px', color: '#666' }}>用时：{formatDuration(log.payload_json.accumulated_seconds)}</div>}
                  </>
                ),
              }))} />
            ),
          },
          {
            key: 'versions',
            label: '版本历史',
            children: versionsLoading ? <div style={{ textAlign: 'center', padding: 24 }}><Spin spinning={versionsLoading} tip="加载版本历史..."><div /></Spin></div> : versions.length === 0 ? <Empty description="暂无版本记录。保存草稿或提交标注后会自动生成版本快照。" /> : (
              <Timeline items={versions.map((v) => {
                const vt = v.version_type || 'draft';
                const tagColor = vt === 'submitted' || vt === 'rework_submitted' ? 'green' : vt === 'rework_draft' ? 'orange' : 'blue';
                const timelineColor = vt === 'submitted' || vt === 'rework_submitted' ? 'green' : vt === 'rework_draft' ? 'orange' : 'blue';
                return {
                  key: v.id || `v${v.version_no}`,
                  color: timelineColor,
                  children: (
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <Tag color={tagColor}>{v.version_type_text || '保存草稿'}</Tag>
                          <strong>V{v.version_no}</strong>
                          <span style={{ marginLeft: 8, color: '#999', fontSize: 12 }}>{formatDateTime(v.created_at)}</span>
                        </div>
                        <Button size="small" type="link" onClick={() => setSelectedVersion(v)}>查看详情</Button>
                      </div>
                      {v.summary && <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>{v.summary}</div>}
                    </div>
                  ),
                };
              })} />
            ),
          },
        ]} />
      </Drawer>

      <Modal
        title={selectedVersion ? `版本 V${selectedVersion.version_no} 详情` : '版本详情'}
        open={!!selectedVersion}
        onCancel={() => setSelectedVersion(null)}
        footer={
          <Tooltip title="暂不支持恢复">
            <Button disabled>恢复此版本</Button>
          </Tooltip>
        }
        width={640}
      >
        {selectedVersion && (
          <>
            <div style={{ marginBottom: 12, fontSize: 13 }}>
              <Tag color={selectedVersion.version_type === 'submitted' || selectedVersion.version_type === 'rework_submitted' ? 'green' : selectedVersion.version_type === 'rework_draft' ? 'orange' : 'blue'}>
                {selectedVersion.version_type_text || '保存草稿'}
              </Tag>
              <span>版本号：V{selectedVersion.version_no}</span>
              <span style={{ marginLeft: 16, color: '#999' }}>创建时间：{formatDateTime(selectedVersion.created_at)}</span>
              {selectedVersion.operator_role && <span style={{ marginLeft: 16, color: '#999' }}>操作者：{selectedVersion.operator_role === 'labeler' ? '标注员' : selectedVersion.operator_role}</span>}
            </div>
            {/* 标注维度摘要 */}
            {selectedVersion.snapshot_json && (() => {
              const snap = selectedVersion.snapshot_json;
              const dimensionKeys = ['relevance', 'accuracy', 'completeness', 'safety', 'helpfulness', 'coherence', 'consistency', 'quality'];
              const hasDimensions = dimensionKeys.some(k => snap[k]);
              const hasRubric = snap._rubric && typeof snap._rubric === 'object' && Object.keys(snap._rubric).length > 0;
              if (!hasDimensions && !hasRubric) return null;
              return (
                <Card size="small" title="标注内容摘要" style={{ marginBottom: 12 }}>
                  {hasDimensions && (
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: hasRubric ? 8 : 0 }}>
                      {dimensionKeys.filter(k => snap[k]).map(k => (
                        <Tag key={k} color="blue">{k}={snap[k]}</Tag>
                      ))}
                    </div>
                  )}
                  {hasRubric && (
                    <div>
                      <div style={{ fontWeight: 500, marginBottom: 4 }}>Rubric 评分：</div>
                      {Object.entries(snap._rubric).map(([dim, val]: [string, any]) => (
                        <div key={dim} style={{ fontSize: 12, color: '#555' }}>{dim}: {typeof val === 'object' ? val.label || val.score || JSON.stringify(val) : val}</div>
                      ))}
                      {snap._rubricNotes && typeof snap._rubricNotes === 'object' && Object.keys(snap._rubricNotes).length > 0 && (
                        <div style={{ marginTop: 4 }}>
                          <div style={{ fontWeight: 500 }}>Rubric 备注：</div>
                          {Object.entries(snap._rubricNotes).map(([dim, note]: [string, any]) => (
                            <div key={dim} style={{ fontSize: 12, color: '#777' }}>{dim}: {note || '-'}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  {snap.reason && <div style={{ marginTop: 8, fontSize: 12, color: '#555' }}>备注：{snap.reason}</div>}
                </Card>
              );
            })()}
            <Collapse ghost items={[{ key: 'raw', label: '原始 JSON 数据', children: (
              <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 400, overflow: 'auto', fontSize: '11px', backgroundColor: '#f5f5f5', padding: 12, borderRadius: 4 }}>
                {JSON.stringify(selectedVersion.snapshot_json, null, 2)}
              </pre>
            )}]} />
          </>
        )}
      </Modal>

      <Modal title="AI 预审原始 JSON" open={showRawJson} onCancel={() => setShowRawJson(false)} footer={null} width={640}>
        <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 500, overflow: 'auto', fontSize: '11px', backgroundColor: '#f5f5f5', padding: 12, borderRadius: 4 }}>
          {JSON.stringify(aiReview?.output_json || aiReview, null, 2)}
        </pre>
      </Modal>
    </div>
  );
};

export default LabelWorkbenchPage;
