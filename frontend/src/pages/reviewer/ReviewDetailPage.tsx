import React, { useEffect, useState } from "react";
import { Card, Row, Col, Button, Space, Tag, Modal, Input, message, Spin, Empty, Alert, Timeline } from "antd";
import { WarningOutlined } from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { getReviewViewModel, approveReview, rejectReview } from "../../api/reviews";
import { rerunAIReview } from "../../api/agent";
import { apiClient } from '../../api/client';
import { formatDateTime } from '../../utils/time';
import { formatProblemLabel } from '../../utils/problemLabels';

const { TextArea } = Input;

const getReviewTimeline = async (annotationId: number) => {
  const res = await apiClient.get(`/reviews/${annotationId}/timeline`);
  return res.data;
};

const RISK_LABELS: Record<string, string> = { low: '低风险', medium: '中风险', high: '高风险' };
const ACTION_LABELS: Record<string, string> = {
  approve: '建议通过', submit: '建议通过',
  revise: '建议返修', reject: '建议返修', rework: '建议返修',
  manual_review: '建议人工审核',
};

const DECISION_LABELS: Record<string, string> = { approve: '建议通过', manual_review: '建议复核', revise: '建议返修' };
const DECISION_COLORS: Record<string, string> = { approve: 'green', manual_review: 'orange', revise: 'red' };
const CONFIDENCE_LABELS: Record<string, string> = { high: '高置信度', medium: '中置信度', low: '低置信度' };
const CONFIDENCE_COLORS: Record<string, string> = { high: 'green', medium: 'blue', low: 'default' };

const STATUS_COLORS: Record<string, string> = {
  match: 'green', mismatch: 'orange', ai_missing: 'cyan',
  human_missing: 'purple', both_missing: 'default', not_applicable: 'default',
};

const STATUS_LABELS_MAP: Record<string, string> = {
  match: '一致', mismatch: '不一致', ai_missing: '无 AI 结果',
  human_missing: '无人工结果', both_missing: '双方缺失', not_applicable: '不适用',
};

const DIFF_FIELD_LABELS: Record<string, string> = {
  relevance: '相关性', accuracy: '准确性', completeness: '完整性', safety: '安全性',
  issue_tags: '问题标签', summary_quality: '理由充分性',
  preferred: '偏好选择', margin: '差异程度', dimensions: '判断维度',
  safety_flag: '安全风险', annotator_note_quality: '理由充分性',
};

const RUBRIC_STATUS_LABELS: Record<string, string> = {
  match: '一致', mismatch: '不一致', human_missing: '人工未评估',
  ai_missing: 'AI 未逐条评估', not_evaluated: '未评估',
};

const ReviewDetailPage: React.FC = () => {
  const navigate = useNavigate();
  const { submissionId } = useParams();
  const [loading, setLoading] = useState(false);
  const [vm, setVm] = useState<any>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [comments, setComments] = useState("");
  const [timelineItems, setTimelineItems] = useState<any[]>([]);
  const [rerunLoading, setRerunLoading] = useState(false);

  const id = Number(submissionId);

  const loadViewModel = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getReviewViewModel(id);
      setVm(data);
      // Load timeline separately
      try {
        const annId = data?.annotation?.id || id;
        const timelineRes = await getReviewTimeline(annId);
        setTimelineItems(timelineRes.items || []);
      } catch { setTimelineItems([]); }
    } catch (error) {
      console.error("Load review view model failed", error);
      message.error("加载审核详情失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadViewModel(); }, [id]);

  const handleApprove = async () => {
    try {
      await approveReview(id, { comments: "审核通过" });
      message.success("审核通过");
      navigate("/reviewer/queue");
    } catch (error) {
      console.error("Approve failed", error);
      message.error("审核通过失败");
    }
  };

  const handleReject = async () => {
    if (!comments.trim()) { message.warning("请填写退回原因"); return; }
    try {
      await rejectReview(id, { comments });
      message.success("已退回修改");
      setRejectOpen(false);
      setComments("");
      navigate("/reviewer/queue");
    } catch (error) {
      console.error("Reject failed", error);
      message.error("退回修改失败");
    }
  };

  const handleRerunAI = async () => {
    setRerunLoading(true);
    try {
      const result = await rerunAIReview(id);
      if (result.success) {
        message.success(`AI 预审重新完成，模型: ${result.model_name}，评分: ${result.score ?? '-'}`);
        await loadViewModel();
      } else {
        message.warning(`AI 重新运行完成，状态: ${result.status}`);
        await loadViewModel();
      }
    } catch (error) {
      console.error("Rerun AI failed", error);
      message.error("重新运行 AI 预审失败");
    } finally {
      setRerunLoading(false);
    }
  };

  if (loading) return <Spin spinning={loading} tip="加载审核详情中..."><div /></Spin>;
  if (!vm) return (
    <Card>
      <Empty description="暂无审核详情" />
      <Button onClick={() => navigate("/reviewer/queue")} style={{ marginTop: 16 }}>返回队列</Button>
    </Card>
  );

  const { annotation, original_view, human_view, ai_view, diff_rows, rubric_rows,
    rubric_empty_state, gold_view, dataset_type, official_id } = vm;
  const isInvalid = annotation?.is_invalid === true;
  const currentStatus = annotation?.status || "unknown";
  const isPreferenceCompare = dataset_type === 'preference_compare';

  const getStatusColor = (status: string) => {
    const map: Record<string, string> = {
      approved: 'green', invalid_approved: 'red', rejected_to_modify: 'red',
      human_reviewing: 'orange', submitted: 'blue', ai_passed: 'cyan', invalid_submitted: 'red',
    };
    return map[status] || 'gray';
  };
  const getStatusLabel = (status: string) => {
    const map: Record<string, string> = {
      approved: '已通过', rejected_to_modify: '待修改', human_reviewing: '人工审核中',
      submitted: '已提交', ai_passed: 'AI通过', invalid_submitted: '无效待审', invalid_approved: '无效已确认',
    };
    return map[status] || status;
  };

  const renderFieldValue = (val: any) => {
    if (val === null || val === undefined || val === '') return <span style={{ color: '#bbb', fontStyle: 'italic' }}>-</span>;
    if (Array.isArray(val)) return val.length > 0 ? val.map((v: any, i: number) => <Tag key={i} color="blue" style={{ fontSize: 10 }}>{typeof v === 'string' ? v : JSON.stringify(v)}</Tag>) : <span style={{ color: '#bbb' }}>-</span>;
    if (typeof val === 'object') return <span>{JSON.stringify(val)}</span>;
    return <span>{String(val)}</span>;
  };

  return (
    <div>
      {/* ── Header ── */}
      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h1>审核详情</h1>
            <div style={{ display: "flex", gap: 16, marginTop: 8, flexWrap: 'wrap' }}>
              <span>标注 ID：{annotation?.id || id}</span>
              <span>Item ID：{annotation?.dataset_item_id || "-"}</span>
              <span>任务 ID：{annotation?.task_id || "-"}</span>
              <span>work_key：{annotation?.work_key || "-"}</span>
              <Tag color={isPreferenceCompare ? 'purple' : 'cyan'} style={{ fontSize: 11 }}>{dataset_type}</Tag>
              {official_id && <Tag color="blue" style={{ fontSize: 11 }}>{official_id}</Tag>}
              <span>状态：<Tag color={getStatusColor(currentStatus)}>{getStatusLabel(currentStatus)}</Tag></span>
            </div>
          </div>
          <Space>
            <Button onClick={() => navigate("/reviewer/queue")}>返回队列</Button>
            <Button loading={rerunLoading} onClick={handleRerunAI}>重新运行 AI 预审</Button>
            {(currentStatus === "invalid_approved" || currentStatus === "approved") ? (
              <Tag color="green" style={{ fontSize: 14, padding: "4px 12px" }}>已审核</Tag>
            ) : (
              <>
                <Button type="primary" onClick={handleApprove}>{isInvalid ? "确认无效" : "审核通过"}</Button>
                <Button danger onClick={() => setRejectOpen(true)}>退回修改</Button>
              </>
            )}
          </Space>
        </div>
      </Card>

      {/* ── Three-column layout ── */}
      <Row gutter={16}>
        {/* ── Original Data ── */}
        <Col span={8}>
          <Card title="原始数据" size="small">
            {original_view?.fields?.length > 0 ? (
              <div style={{ maxHeight: 520, overflow: "auto" }}>
                {original_view.fields.map((f: any) => (
                  <div key={f.key} style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 11, color: "#888", marginBottom: 3 }}>{f.label}</div>
                    {f.key === 'response_a' || f.key === 'response_b' ? (
                      <pre style={{ padding: 8, backgroundColor: f.key === 'response_a' ? '#e6f7ff' : '#fff7e6', borderRadius: 4, maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap', fontSize: 12, margin: 0 }}>
                        {f.value || <span style={{ color: '#bbb' }}>该字段未填写</span>}
                      </pre>
                    ) : f.key === 'prompt' || f.key === 'model_answer' || f.key === 'reference' || f.key === 'content_markdown' ? (
                      <div style={{ padding: 8, backgroundColor: '#f9fafb', borderRadius: 4, maxHeight: 200, overflow: 'auto' }}>
                        {f.value || <span style={{ color: '#bbb' }}>该字段未填写</span>}
                      </div>
                    ) : (
                      <div style={{ fontSize: 13 }}>{renderFieldValue(f.value)}</div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <Empty description="暂无原始数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* ── Human Result ── */}
        <Col span={8}>
          <Card title="人工标注结果" size="small">
            {isInvalid ? (
              <div>
                <Alert type="error" message="标注员标记无效"
                  description={<div>{annotation?.invalid_reason && <div>原因：{annotation.invalid_reason}</div>}{annotation?.invalid_remark && <div>备注：{annotation.invalid_remark}</div>}</div>}
                  style={{ marginBottom: 12 }} />
                <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, maxHeight: 200, overflow: 'auto' }}>{JSON.stringify(human_view?.raw_result || {}, null, 2)}</pre>
              </div>
            ) : human_view?.display_fields?.length > 0 ? (
              <div style={{ maxHeight: 520, overflow: "auto" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
                  {human_view.summary_cards?.map((c: any, i: number) => (
                    <div key={i} style={{ padding: 8, backgroundColor: "#f3f4f6", borderRadius: 4 }}>
                      <div style={{ fontSize: 10, color: "#9ca3af", marginBottom: 4 }}>{c.label}</div>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>
                        {isPreferenceCompare && c.label === '偏好' ? (
                          <Tag color={c.value === 'A' ? 'blue' : c.value === 'B' ? 'orange' : 'default'}>{c.value === 'A' ? '回答 A' : c.value === 'B' ? '回答 B' : c.value}</Tag>
                        ) : (c.value || "-")}
                      </div>
                    </div>
                  ))}
                </div>
                {human_view.display_fields.filter((f: any) => !['preferred', 'margin', 'safety_flag', 'relevance', 'accuracy', 'completeness', 'safety'].includes(f.key)).map((f: any) => (
                  <div key={f.key} style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 11, color: "#888", marginBottom: 3 }}>{f.label}</div>
                    {f.value != null && f.value !== '' ? (
                      <div style={{ padding: 8, backgroundColor: '#f9fafb', borderRadius: 4, fontSize: 12 }}>
                        {Array.isArray(f.value) ? f.value.map((v: any, i: number) => <Tag key={i} color="blue" style={{ fontSize: 10 }}>{v}</Tag>) : (typeof f.value === 'object' ? JSON.stringify(f.value) : String(f.value))}
                      </div>
                    ) : (
                      <div style={{ color: '#bbb', fontStyle: 'italic', fontSize: 12, padding: 4 }}>{f.empty_hint || '该字段未由标注员填写'}</div>
                    )}
                  </div>
                ))}
                <details style={{ marginTop: 8 }}>
                  <summary style={{ cursor: 'pointer', color: '#999', fontSize: 11 }}>完整结果 JSON</summary>
                  <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 11, maxHeight: 200, overflow: 'auto' }}>{JSON.stringify(human_view?.raw_result || {}, null, 2)}</pre>
                </details>
              </div>
            ) : (
              <Empty description="暂无人工提交结果。" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* ── AI Result ── */}
        <Col span={8}>
          <Card title="AI 审核建议" size="small">
            {ai_view?.used_fallback && (
              <Alert type="warning" message="AI Agent 执行不稳定，已使用兜底结果" style={{ marginBottom: 8 }} showIcon icon={<WarningOutlined />} />
            )}
            {ai_view ? (
              <div style={{ maxHeight: 520, overflow: "auto" }}>
                {/* Row 1: Decision summary badges */}
                <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
                  <Tag color={DECISION_COLORS[ai_view.decision] || 'default'} style={{ fontSize: 13, padding: '2px 10px' }}>{DECISION_LABELS[ai_view.decision] || (ai_view.action ? (ACTION_LABELS[ai_view.action] || ai_view.action) : '-')}</Tag>
                  <Tag color={ai_view.risk_level === 'high' ? 'red' : ai_view.risk_level === 'medium' ? 'orange' : 'green'}>{RISK_LABELS[ai_view.risk_level] || ai_view.risk_level || '-'}</Tag>
                  <Tag color={CONFIDENCE_COLORS[ai_view.confidence_level] || 'default'}>{CONFIDENCE_LABELS[ai_view.confidence_level] || ai_view.confidence_level || '-'}</Tag>
                </div>
                {/* Row 2: Display summary */}
                {ai_view.display_summary && (
                  <div style={{ padding: 8, backgroundColor: ai_view.decision === 'approve' ? '#f6ffed' : ai_view.decision === 'revise' ? '#fff1f0' : '#fff7e6', borderRadius: 4, borderLeft: `3px solid ${ai_view.decision === 'approve' ? '#52c41a' : ai_view.decision === 'revise' ? '#ff4d4f' : '#faad14'}`, marginBottom: 12, fontSize: 12 }}>{ai_view.display_summary}</div>
                )}
                {/* Row 3: Blocking / warning reasons */}
                {ai_view.blocking_reasons?.length > 0 && ai_view.blocking_reasons.map((reason: string, i: number) => (
                  <Alert key={`block-${i}`} type="error" message={reason} style={{ marginBottom: 8 }} showIcon />
                ))}
                {ai_view.warning_reasons?.length > 0 && ai_view.warning_reasons.map((reason: string, i: number) => (
                  <Alert key={`warn-${i}`} type="warning" message={reason} style={{ marginBottom: 8 }} showIcon />
                ))}
                {/* Row 4: AI display fields */}
                {ai_view.display_fields?.map((f: any) => (
                  <div key={f.key} style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 11, color: "#888", marginBottom: 2 }}>{f.label}</div>
                    {f.value != null ? (
                      <div style={{ fontSize: 12 }}>
                        {Array.isArray(f.value) ? f.value.map((v: any, i: number) => <Tag key={i} color="blue" style={{ fontSize: 10 }}>{v}</Tag>) : (typeof f.value === 'object' ? JSON.stringify(f.value) : String(f.value))}
                      </div>
                    ) : <span style={{ color: '#bbb', fontSize: 12 }}>-</span>}
                  </div>
                ))}
                {/* Row 5: Issue tags */}
                {ai_view.issue_tags?.length > 0 && (
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 11, color: "#888", marginBottom: 2 }}>问题标签</div>
                    {ai_view.issue_tags.map((t: string, i: number) => <Tag key={i} color="orange" style={{ fontSize: 10 }}>{formatProblemLabel(t)}</Tag>)}
                  </div>
                )}
                {/* Row 6: Metadata */}
                <div style={{ marginTop: 8, padding: 6, backgroundColor: '#fafafa', borderRadius: 4, fontSize: 10, color: '#888' }}>
                  <div>Run #{ai_view.run_id} | {ai_view.prompt_profile || '-'}</div>
                  <div>{ai_view.model_provider || '-'}/{ai_view.model_name || '-'} | {ai_view.latency_ms ? `${ai_view.latency_ms}ms` : '-'}</div>
                  {ai_view.used_fallback && <div style={{ color: '#fa8c16' }}>⚠️ 使用了兜底结果</div>}
                  {ai_view.debug_score != null && <div style={{ color: '#bbb' }}>原始分: {ai_view.debug_score} (调试用)</div>}
                </div>
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '24px 0' }}>
                <div style={{ fontSize: 36, marginBottom: 8 }}>🤖</div>
                <div style={{ color: '#9ca3af', fontSize: 13 }}>暂无 AI 审核建议</div>
                <div style={{ color: '#bbb', fontSize: 11, marginTop: 4 }}>可在工作台点击 LLM 辅助或提交后自动触发。</div>
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {/* ── Human Override Warning ── */}
      {(() => {
        const aiHighRisk = ai_view && (ai_view.risk_level === 'high' || ai_view.decision === 'revise');
        const humanApproved = currentStatus === 'approved';
        if (!isInvalid && aiHighRisk && humanApproved) {
          return (
            <Alert type="warning" showIcon icon={<WarningOutlined />} style={{ marginTop: 16 }}
              message="人工审核已覆盖 AI 高风险建议"
              description={`AI 建议${DECISION_LABELS[ai_view.decision] || ACTION_LABELS[ai_view.action] || '-'}（${ai_view.display_summary || '-'}），但审核员已审核通过。`} />
          );
        }
        return null;
      })()}

      {/* ── Diff Rows ── */}
      {!isInvalid && (
        <Card title="AI / 人工差异对比" size="small" style={{ marginTop: 16 }}>
          {diff_rows?.length > 0 ? (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid #e8e8e8" }}>
                    <th style={{ padding: "10px 14px", textAlign: "left", fontWeight: 600, backgroundColor: "#fafafa" }}>字段</th>
                    <th style={{ padding: "10px 14px", textAlign: "left", fontWeight: 600, backgroundColor: "#fafafa" }}>AI 值</th>
                    <th style={{ padding: "10px 14px", textAlign: "left", fontWeight: 600, backgroundColor: "#fafafa" }}>人工值</th>
                    <th style={{ padding: "10px 14px", textAlign: "left", fontWeight: 600, backgroundColor: "#fafafa" }}>状态</th>
                    <th style={{ padding: "10px 14px", textAlign: "left", fontWeight: 600, backgroundColor: "#fafafa" }}>说明</th>
                  </tr>
                </thead>
                <tbody>
                  {diff_rows.map((row: any, i: number) => (
                    <tr key={row.field || i} style={{ borderBottom: "1px solid #f0f0f0" }}>
                      <td style={{ padding: "10px 14px", fontWeight: 500 }}>{DIFF_FIELD_LABELS[row.field] || row.label || row.field}</td>
                      <td style={{ padding: "10px 14px" }}>
                        {row.ai_value == null ? <span style={{ color: '#bbb' }}>-</span> : Array.isArray(row.ai_value) ? row.ai_value.map((v: any, j: number) => <Tag key={j} color="blue" style={{ fontSize: 10 }}>{v}</Tag>) : String(row.ai_value)}
                      </td>
                      <td style={{ padding: "10px 14px" }}>
                        {row.human_value == null ? <span style={{ color: '#bbb' }}>-</span> : Array.isArray(row.human_value) ? row.human_value.map((v: any, j: number) => <Tag key={j} color="geekblue" style={{ fontSize: 10 }}>{v}</Tag>) : String(row.human_value)}
                      </td>
                      <td style={{ padding: "10px 14px" }}><Tag color={STATUS_COLORS[row.status] || 'default'}>{STATUS_LABELS_MAP[row.status] || row.status}</Tag></td>
                      <td style={{ padding: "10px 14px", fontSize: 11, color: '#888' }}>{row.explanation || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty description="当前任务类型未配置差异对比字段。" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </Card>
      )}

      {/* ── Rubric Rows ── */}
      {!isInvalid && (
        <Card title="Rubric 命中情况" size="small" style={{ marginTop: 16 }}>
          {rubric_rows?.length > 0 ? (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid #e8e8e8" }}>
                    <th style={{ padding: "10px 12px", textAlign: "left", fontWeight: 600, backgroundColor: "#fafafa" }}>Rubric</th>
                    <th style={{ padding: "10px 12px", textAlign: "left", fontWeight: 600, backgroundColor: "#fafafa" }}>维度</th>
                    <th style={{ padding: "10px 12px", textAlign: "left", fontWeight: 600, backgroundColor: "#fafafa" }}>类型</th>
                    <th style={{ padding: "10px 12px", textAlign: "left", fontWeight: 600, backgroundColor: "#fafafa" }}>优先级</th>
                    <th style={{ padding: "10px 12px", textAlign: "left", fontWeight: 600, backgroundColor: "#fafafa" }}>人工</th>
                    <th style={{ padding: "10px 12px", textAlign: "left", fontWeight: 600, backgroundColor: "#fafafa" }}>AI</th>
                    <th style={{ padding: "10px 12px", textAlign: "left", fontWeight: 600, backgroundColor: "#fafafa" }}>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {rubric_rows.map((row: any, i: number) => (
                    <tr key={row.rubric_id || i} style={{ borderBottom: "1px solid #f0f0f0" }}>
                      <td style={{ padding: "8px 12px" }}>{row.name || row.rubric_id}</td>
                      <td style={{ padding: "8px 12px" }}>{row.dimension || '-'}</td>
                      <td style={{ padding: "8px 12px" }}><Tag color={row.type === 'objective' ? 'blue' : 'purple'} style={{ fontSize: 10 }}>{row.type === 'objective' ? '客观' : '主观'}</Tag></td>
                      <td style={{ padding: "8px 12px" }}><Tag color={row.priority === 'must_have' ? 'red' : 'orange'} style={{ fontSize: 10 }}>{row.priority === 'must_have' ? '必须' : '加分'}</Tag></td>
                      <td style={{ padding: "8px 12px" }}>{row.human_choice || <span style={{ color: '#bbb', fontSize: 11 }}>人工未逐条评估</span>}</td>
                      <td style={{ padding: "8px 12px" }}>{row.ai_choice || <span style={{ color: '#bbb', fontSize: 11 }}>AI 未逐条评估</span>}</td>
                      <td style={{ padding: "8px 12px" }}>
                        <Tag color={row.status === 'match' ? 'green' : row.status === 'mismatch' ? 'orange' : 'default'}>{RUBRIC_STATUS_LABELS[row.status] || row.status}</Tag>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty description={rubric_empty_state || "当前任务未配置 Rubric 规则。"} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </Card>
      )}

      {/* ── Gold Comparison ── */}
      {!isInvalid && ai_view?.gold_comparison?.available && (
        <Card title="Gold 对比结论" size="small" style={{ marginTop: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div style={{ padding: 8, backgroundColor: "#f3f4f6", borderRadius: 4, textAlign: "center" }}>
              <div style={{ fontSize: 10, color: "#9ca3af", marginBottom: 4 }}>Gold preferred</div>
              <Tag color={ai_view.gold_comparison.gold_preferred === 'A' ? 'blue' : ai_view.gold_comparison.gold_preferred === 'B' ? 'orange' : 'default'}>{ai_view.gold_comparison.gold_preferred || '-'}</Tag>
            </div>
            <div style={{ padding: 8, backgroundColor: "#f3f4f6", borderRadius: 4, textAlign: "center" }}>
              <div style={{ fontSize: 10, color: "#9ca3af", marginBottom: 4 }}>人工 preferred</div>
              <Tag color={ai_view.gold_comparison.human_preferred === 'A' ? 'blue' : ai_view.gold_comparison.human_preferred === 'B' ? 'orange' : 'default'}>{ai_view.gold_comparison.human_preferred || '-'}</Tag>
            </div>
            <div style={{ padding: 8, backgroundColor: "#f3f4f6", borderRadius: 4, textAlign: "center" }}>
              <div style={{ fontSize: 10, color: "#9ca3af", marginBottom: 4 }}>AI preferred</div>
              <Tag color={ai_view.gold_comparison.ai_preferred === 'A' ? 'blue' : ai_view.gold_comparison.ai_preferred === 'B' ? 'orange' : 'default'}>{ai_view.gold_comparison.ai_preferred || '-'}</Tag>
            </div>
          </div>
          {ai_view.gold_comparison.conclusion && (
            <div style={{ fontWeight: 'bold', fontSize: 13 }}>{ai_view.gold_comparison.conclusion}</div>
          )}
        </Card>
      )}

      {/* ── Gold View ── */}
      {!isInvalid && gold_view && (
        <Card title="Gold 参考答案" size="small" style={{ marginTop: 16 }}>
          <Alert type="info" message={gold_view.note} style={{ marginBottom: 8 }} />
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, maxHeight: 200, overflow: 'auto' }}>{JSON.stringify(gold_view.payload, null, 2)}</pre>
        </Card>
      )}

      {/* ── Timeline ── */}
      <Card title="审计时间线" size="small" style={{ marginTop: 16 }}>
        {timelineItems.length > 0 ? (
          <Timeline items={timelineItems.map((item: any) => ({
            color: item.action === "review_approve" || item.action === "invalid_approved" ? "green"
              : item.action === "review_reject" || item.action === "invalid_rejected" ? "red"
              : item.action === "mark_invalid" ? "red"
              : item.action === "submission_submit" ? "blue"
              : item.action?.includes("ai_precheck") ? "cyan" : "gray",
            children: (
              <div>
                <div style={{ fontWeight: 600 }}>{item.title || item.action_label}</div>
                <div style={{ fontSize: 11, color: "#9ca3af" }}>{item.created_at ? formatDateTime(item.created_at) : ""}{item.actor_name && ` | ${item.actor_name}`}</div>
                {item.description && <div style={{ fontSize: 12, marginTop: 2 }}>{item.description}</div>}
              </div>
            )
          }))} />
        ) : (
          <div style={{ color: "#9ca3af", fontSize: 12 }}>暂无审计记录</div>
        )}
      </Card>

      <Modal title="退回修改" open={rejectOpen} onOk={handleReject} onCancel={() => { setRejectOpen(false); setComments(""); }}>
        <TextArea rows={4} value={comments} onChange={(e) => setComments(e.target.value)} placeholder="请输入退回修改的原因" />
      </Modal>
    </div>
  );
};

export default ReviewDetailPage;
