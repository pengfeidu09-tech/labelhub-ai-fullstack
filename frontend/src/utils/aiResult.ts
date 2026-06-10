/**
 * AI 预审结果统一标准化工具
 * 
 * 将来自不同数据源的 AI 结果（ai_review_runs.output_json, annotation.ai_review,
 * LLM adapter 返回值等）统一为 canonical 格式，确保展示层和对比层口径一致。
 */

// ─── Canonical enum mappings ───────────────────────────────────────────
// 所有别名 → canonical value（与表单枚举一致）

const ACCURACY_ALIASES: Record<string, string> = {
  correct: 'correct', accurate: 'correct', '正确': 'correct', yes: 'correct',
  partially_correct: 'partial', partly_correct: 'partial', partial_correct: 'partial',
  partial: 'partial', '部分正确': 'partial', '部分准确': 'partial',
  incorrect: 'incorrect', wrong: 'incorrect', '错误': 'incorrect', '不正确': 'incorrect', no: 'incorrect',
};

const COMPLETENESS_ALIASES: Record<string, string> = {
  complete: 'complete', '完整': 'complete', full: 'complete',
  partially_complete: 'partial', partial_completeness: 'partial',
  partial: 'partial', '部分': 'partial', '部分完整': 'partial',
  incomplete: 'incomplete', '不完整': 'incomplete',
};

const RELEVANCE_ALIASES: Record<string, string> = {
  highly_relevant: 'high', high: 'high', '高': 'high',
  medium: 'medium', '中': 'medium', moderate: 'medium',
  low: 'low', '低': 'low',
  irrelevant: 'irrelevant', not_relevant: 'irrelevant', '不相关': 'irrelevant',
};

const SAFETY_ALIASES: Record<string, string> = {
  safe: 'safe', '安全': 'safe',
  risky: 'risky', risk: 'risky', '风险': 'risky',
  unsafe: 'unsafe', '不安全': 'unsafe', dangerous: 'unsafe',
};

const ACTION_ALIASES: Record<string, string> = {
  submit: 'approve', approve: 'approve', '建议通过': 'approve',
  manual_review: 'manual_review', '建议人工审核': 'manual_review',
  reject: 'revise', rework: 'revise', revise: 'revise', '建议返修': 'revise',
};

// ─── Canonical → Chinese display ───────────────────────────────────────

export const DIMENSION_CN: Record<string, Record<string, string>> = {
  relevance:  { high: '高', medium: '中', low: '低', irrelevant: '不相关' },
  accuracy:   { correct: '正确', partial: '部分准确', incorrect: '不正确' },
  completeness: { complete: '完整', partial: '部分完整', incomplete: '不完整' },
  safety:     { safe: '安全', risky: '风险', unsafe: '不安全' },
};

export const ACTION_CN: Record<string, string> = {
  approve: '建议通过', manual_review: '建议人工审核', revise: '建议返修',
};

// ─── Normalizer ────────────────────────────────────────────────────────

export interface CanonicalAiResult {
  relevance: string | null;   // high | medium | low | irrelevant
  accuracy: string | null;    // correct | partial | incorrect
  completeness: string | null; // complete | partial | incomplete
  safety: string | null;      // safe | risky | unsafe
  score: number | null;
  risk_level: string | null;  // low | medium | high
  action: string | null;      // approve | manual_review | revise
  reason: string;
  issue_tags: string[];
  confidence: number | null;
  matched_rubrics: any[];
  raw: any;                   // preserve original
  // preference_compare 特有字段
  preferred: string | null;   // A | B | tie
  margin: string | null;      // 明显优于 | 略优于 | 相当
  pref_dimensions: string[] | null;
  safety_flag: boolean | null;
}

/** 从任意结构的 AI 结果中提取 canonical 维度值 */
function extractDimensionValue(raw: any, dim: string, aliasMap: Record<string, string>): string | null {
  if (!raw || typeof raw !== 'object') return null;

  // 1. suggestion.{dim}
  const suggestion = raw.suggestion;
  if (suggestion && typeof suggestion === 'object') {
    const v = suggestion[dim];
    if (v != null && v !== '') {
      const s = typeof v === 'object' ? (v.label || v.value || null) : String(v);
      if (s) {
        const canonical = aliasMap[s.trim().toLowerCase()];
        if (canonical) return canonical;
        return s.trim().toLowerCase();
      }
    }
  }

  // 2. dimensions.{dim}.label
  const dimensions = raw.dimensions;
  if (dimensions && typeof dimensions === 'object') {
    const d = dimensions[dim];
    if (d != null && d !== '') {
      if (typeof d === 'object') {
        const label = d.label || d.value || null;
        if (label) {
          const canonical = aliasMap[String(label).trim().toLowerCase()];
          if (canonical) return canonical;
          return String(label).trim().toLowerCase();
        }
      } else {
        const canonical = aliasMap[String(d).trim().toLowerCase()];
        if (canonical) return canonical;
        return String(d).trim().toLowerCase();
      }
    }
  }

  // 3. dimension_scores.{dim} / suggested_labels.{dim}
  const inner = raw.result || {};
  const scores = raw.dimension_scores || inner.dimension_scores || {};
  const labels = raw.suggested_labels || inner.suggested_labels || {};
  for (const src of [scores, labels]) {
    const v = src[dim];
    if (v != null && v !== '') {
      const s = typeof v === 'object' ? (v.label || v.value || null) : String(v);
      if (s) {
        const canonical = aliasMap[s.trim().toLowerCase()];
        if (canonical) return canonical;
        return s.trim().toLowerCase();
      }
    }
  }

  // 4. top-level dim field (some flat structures)
  const topVal = raw[dim];
  if (topVal != null && topVal !== '' && typeof topVal !== 'object') {
    const canonical = aliasMap[String(topVal).trim().toLowerCase()];
    if (canonical) return canonical;
    return String(topVal).trim().toLowerCase();
  }

  return null;
}

/** 将任意 AI 结果标准化为 canonical 格式 */
export function normalizeAiResult(raw: any): CanonicalAiResult {
  if (!raw || typeof raw !== 'object') {
    return {
      relevance: null, accuracy: null, completeness: null, safety: null,
      score: null, risk_level: null, action: null, reason: '',
      issue_tags: [], confidence: null, matched_rubrics: [], raw,
      preferred: null, margin: null, pref_dimensions: null, safety_flag: null,
    };
  }

  const relevance = extractDimensionValue(raw, 'relevance', RELEVANCE_ALIASES);
  const accuracy = extractDimensionValue(raw, 'accuracy', ACCURACY_ALIASES);
  const completeness = extractDimensionValue(raw, 'completeness', COMPLETENESS_ALIASES);
  const safety = extractDimensionValue(raw, 'safety', SAFETY_ALIASES);

  const score = raw.score ?? raw.overall_score ?? raw.ai_review_score ?? null;
  const riskLevel = raw.risk_level ?? raw.ai_review_risk_level ?? null;

  const rawAction = raw.suggestion_action || raw.action || null;
  const action = rawAction ? (ACTION_ALIASES[String(rawAction).trim().toLowerCase()] || rawAction) : null;

  const reason = raw.summary || raw.reason || raw.suggestion?.reason || '';
  const issueTags = raw.issue_tags || raw.problem_tags || raw.suggestion?.issue_tags || [];
  const confidence = raw.confidence ?? null;
  const matchedRubrics = raw.matched_rubrics || [];

  // preference_compare 字段提取
  const outputJson = raw.output_json || {};
  const preferred = raw.preferred || outputJson.preferred || null;
  const margin = raw.margin || outputJson.margin || null;
  const prefDimensions = raw.pref_dimensions || outputJson.dimensions || outputJson.pref_dimensions ||
    (Array.isArray(raw.dimensions) ? raw.dimensions : null);
  const safetyFlag = raw.safety_flag ?? outputJson.safety_flag ?? null;

  return {
    relevance, accuracy, completeness, safety,
    score: typeof score === 'number' ? score : (score != null ? Number(score) : null),
    risk_level: riskLevel ? String(riskLevel).toLowerCase() : null,
    action,
    reason: typeof reason === 'string' ? reason : JSON.stringify(reason),
    issue_tags: Array.isArray(issueTags) ? issueTags : [],
    confidence: typeof confidence === 'number' ? confidence : null,
    matched_rubrics: Array.isArray(matchedRubrics) ? matchedRubrics : [],
    raw,
    preferred: preferred ? String(preferred) : null,
    margin: margin ? String(margin) : null,
    pref_dimensions: Array.isArray(prefDimensions) ? prefDimensions : null,
    safety_flag: safetyFlag != null ? Boolean(safetyFlag) : null,
  };
}

/** 获取维度值的中文展示文本 */
export function getDimensionCn(dim: string, canonicalValue: string | null): string {
  if (!canonicalValue) return '-';
  const map = DIMENSION_CN[dim];
  if (map && map[canonicalValue]) return map[canonicalValue];
  return canonicalValue;
}

/**
 * 用于审核详情页的对比 normalize。
 * 将 human 或 AI 的维度值映射到 canonical，用于 isSame 判断。
 */
export function normalizeForCompare(dim: string, val: string | string[] | null | undefined): string | null {
  if (val == null) return null;
  if (Array.isArray(val)) {
    if (val.length === 0) return null;
    return val.map(v => normalizeSingle(dim, String(v))).filter(Boolean).sort().join(',');
  }
  return normalizeSingle(dim, String(val));
}

function normalizeSingle(_dim: string, val: string): string | null {
  const trimmed = val.trim().toLowerCase();
  if (!trimmed) return null;
  const map: Record<string, string> = {
    ...ACCURACY_ALIASES, ...COMPLETENESS_ALIASES, ...RELEVANCE_ALIASES, ...SAFETY_ALIASES,
  };
  return map[trimmed] || trimmed;
}
