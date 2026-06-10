/**
 * 审核决策策略函数（Review Decision Policy）
 *
 * 纯函数，无外部依赖。
 * 根据 AI 结果、人工结果、黄金标准（可选）自动推导审核决策：
 *   - approve（通过）
 *   - manual_review（人工复核）
 *   - revise（退回修改）
 */

// ============================================================
// 类型定义
// ============================================================

export interface ReviewDecision {
  decision: 'approve' | 'manual_review' | 'revise';
  risk_level: 'low' | 'medium' | 'high';
  confidence_level: 'low' | 'medium' | 'high';
  blocking_reasons: string[];
  warning_reasons: string[];
  display_summary: string;
  debug_score: number | null;
}

// ============================================================
// 常量
// ============================================================

/** 可导致"退回修改"的严重问题标签 */
const MAJOR_ISSUE_TAGS = new Set([
  'accuracy_error',
  'factual_error',
  'cultural_misinterpretation',
  'translation_error',
  'safety_violation',
  '事实性错误',
  '语义错误',
  '翻译错误',
  '严重安全问题',
]);

/** AI 推理文本中的可疑关键词（触发人工复核） */
const SUSPICIOUS_REASON_KEYWORDS = [
  '可能存在错误',
  '信息不足',
  '需核验',
  '翻译不自然',
  '文化误解',
];

// ============================================================
// 归一化辅助函数
// ============================================================

/**
 * 归一化 preferred 值
 *
 * 映射规则：
 *   a / response_a         → A
 *   b / response_b         → B
 *   tie / both / equal / 两者相当 → tie
 */
function normalizePreferred(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const str = String(value).trim().toLowerCase();
  if (!str) return null;

  const mapping: Record<string, string> = {
    a: 'A',
    b: 'B',
    response_a: 'A',
    response_b: 'B',
    tie: 'tie',
    both: 'tie',
    equal: 'tie',
    '两者相当': 'tie',
  };

  return mapping[str] ?? str;
}

/**
 * 归一化 margin 值
 *
 * 中文 / 英文 / 数值均可映射到统一的中文标签。
 * 当输入为数值（如 AI 置信度）时，可按阈值推断 margin。
 *
 * @param value       原始 margin 值
 * @param confidence  可选的置信度数值，仅在 value 本身无法映射时作为后备
 */
function normalizeMargin(value: unknown, confidence?: number | null): string | null {
  if (value === null || value === undefined) {
    // 没有 margin 文本但有置信度时，用置信度推断
    if (typeof confidence === 'number' && !isNaN(confidence)) {
      return confidenceToMargin(confidence);
    }
    return null;
  }

  const str = String(value).trim();
  if (!str) {
    if (typeof confidence === 'number' && !isNaN(confidence)) {
      return confidenceToMargin(confidence);
    }
    return null;
  }

  // 尝试作为数值解析
  const num = Number(str);
  if (!isNaN(num) && typeof num === 'number') {
    return confidenceToMargin(num);
  }

  // 文本映射表
  const mapping: Record<string, string> = {
    // 中文标签
    '明显差异': '明显优于',
    '明显优于': '明显优于',
    '轻微差异': '略优于',
    '略优于': '略优于',
    '无差异': '相当',
    '相当': '相当',
    // 英文标签
    large: '明显优于',
    small: '略优于',
    tie: '相当',
    // 额外兼容
    significant: '明显优于',
    slight: '略优于',
    none: '相当',
    equal: '相当',
  };

  return mapping[str.toLowerCase()] ?? str;
}

/** 根据置信度数值推断 margin 标签 */
function confidenceToMargin(confidence: number): string {
  if (confidence >= 0.8) return '明显优于';
  if (confidence >= 0.6) return '略优于';
  return '相当';
}

// ============================================================
// 工具函数
// ============================================================

/** 安全获取对象属性（支持嵌套路径 "a.b.c"） */
function safeGet(obj: Record<string, any> | null | undefined, path: string): any {
  if (!obj || !path) return undefined;
  return path.split('.').reduce((acc: any, key: string) => {
    if (acc === null || acc === undefined) return undefined;
    return acc[key];
  }, obj);
}

/** 安全获取字符串属性，若不存在返回 null */
function safeString(obj: Record<string, any> | null | undefined, path: string): string | null {
  const val = safeGet(obj, path);
  if (val === null || val === undefined) return null;
  return String(val);
}

/** 安全获取数值属性，若不存在或非法返回 null */
function safeNumber(obj: Record<string, any> | null | undefined, path: string): number | null {
  const val = safeGet(obj, path);
  if (val === null || val === undefined) return null;
  const num = Number(val);
  return isNaN(num) ? null : num;
}

/** 安全获取数组属性，若不存在或非数组返回空数组 */
function safeArray<T = any>(obj: Record<string, any> | null | undefined, path: string): T[] {
  const val = safeGet(obj, path);
  if (!Array.isArray(val)) return [];
  return val as T[];
}

/** 检查 issue_tags 中是否包含严重问题标签 */
function hasMajorIssueTags(tags: string[]): boolean {
  return tags.some((tag) => MAJOR_ISSUE_TAGS.has(String(tag).trim()));
}

/** 检查 AI reason 文本中是否包含可疑关键词 */
function hasSuspiciousReason(reason: string | null): boolean {
  if (!reason) return false;
  return SUSPICIOUS_REASON_KEYWORDS.some((keyword) => reason.includes(keyword));
}

/** 计算 AI 综合置信度（取 confidence 与 issue_confidence 的较大值） */
function computeAiConfidence(aiResult: Record<string, any>): number | null {
  const c1 = safeNumber(aiResult, 'confidence');
  const c2 = safeNumber(aiResult, 'issue_confidence');
  if (c1 !== null && c2 !== null) return Math.max(c1, c2);
  if (c1 !== null) return c1;
  if (c2 !== null) return c2;
  return null;
}

/** 根据置信度数值映射为高/中/低 */
function confidenceToLevel(confidence: number | null): 'low' | 'medium' | 'high' {
  if (confidence === null) return 'medium';
  if (confidence >= 0.8) return 'high';
  if (confidence >= 0.5) return 'medium';
  return 'low';
}

/** 生成偏好对比的审核摘要（中文） */
function buildPreferenceSummary(
  decision: ReviewDecision['decision'],
  blockingReasons: string[],
  warningReasons: string[],
): string {
  switch (decision) {
    case 'approve':
      return 'AI 与人工标注结果一致，审核通过。';

    case 'revise': {
      const reason = blockingReasons[0] ?? '存在严重问题';
      return `标注结果存在严重问题，需退回修改。原因：${reason}`;
    }

    case 'manual_review': {
      if (warningReasons.length > 0) {
        return `AI 与人工结果存在差异，需人工复核。原因：${warningReasons.join('；')}`;
      }
      return 'AI 与人工结果存在差异，需人工复核。';
    }

    default:
      return '未知决策。';
  }
}

/** 生成 QA 质量审核的摘要（中文） */
function buildQaSummary(
  decision: ReviewDecision['decision'],
  score: number | null,
  blockingReasons: string[],
  warningReasons: string[],
): string {
  const scoreText = score !== null ? `${score} 分` : '未知分数';

  switch (decision) {
    case 'approve':
      return `QA 质量评分 ${scoreText}，风险低，审核通过。`;

    case 'revise': {
      const reason = blockingReasons[0] ?? '评分过低或风险高';
      return `QA 质量评分 ${scoreText}，需退回修改。原因：${reason}`;
    }

    case 'manual_review': {
      const reason = warningReasons.length > 0 ? warningReasons.join('；') : '评分或风险未达标';
      return `QA 质量评分 ${scoreText}，需人工复核。原因：${reason}`;
    }

    default:
      return '未知决策。';
  }
}

// ============================================================
// preference_compare 决策逻辑
// ============================================================

function handlePreferenceCompare(
  aiResult: Record<string, any>,
  humanResult: Record<string, any>,
  goldResult: Record<string, any> | null,
): ReviewDecision {
  const blockingReasons: string[] = [];
  const warningReasons: string[] = [];

  // ---- 提取并归一化关键字段 ----

  const aiPreferredRaw = safeString(aiResult, 'preferred');
  const humanPreferredRaw = safeString(humanResult, 'preferred');
  const goldPreferredRaw = goldResult ? safeString(goldResult, 'preferred') : null;

  const aiPreferred = normalizePreferred(aiPreferredRaw);
  const humanPreferred = normalizePreferred(humanPreferredRaw);
  const goldPreferred = normalizePreferred(goldPreferredRaw);

  const aiConfidence = computeAiConfidence(aiResult);

  // margin 归一化（AI 侧可用 confidence 作为后备）
  const aiMargin = normalizeMargin(safeString(aiResult, 'margin'), aiConfidence);
  const humanMargin = normalizeMargin(safeString(humanResult, 'margin'));

  const issueTags: string[] = safeArray(aiResult, 'issue_tags');
  const aiReason = safeString(aiResult, 'reason');
  const safetyFlag = safeString(aiResult, 'safety_flag');
  const annotatorNote = safeString(humanResult, 'annotator_note');
  const dimensions = safeArray(humanResult, 'dimensions');

  const hasGold = goldResult !== null && goldResult !== undefined;

  // ---- 第一轮：强制退回 / 高风险 ----

  // 规则 1：AI issue_tags 包含严重问题标签
  if (hasMajorIssueTags(issueTags)) {
    const matched = issueTags.filter((t) => MAJOR_ISSUE_TAGS.has(String(t).trim()));
    blockingReasons.push(`AI 检测到严重问题标签：${matched.join('、')}`);
  }

  // 规则 2：人工偏好与黄金标准冲突，且标注说明不足（< 15 字符或缺失）
  if (hasGold && humanPreferred !== null && goldPreferred !== null && humanPreferred !== goldPreferred) {
    const noteLen = annotatorNote ? annotatorNote.length : 0;
    if (!annotatorNote || noteLen < 15) {
      blockingReasons.push(
        `人工偏好(${humanPreferred})与黄金标准(${goldPreferred})冲突，且标注说明不足（${noteLen} 字符，需 >= 15）`,
      );
    }
  }

  // 规则 3：AI 偏好与人工偏好不一致，且 AI 置信度 >= 0.8
  if (
    aiPreferred !== null &&
    humanPreferred !== null &&
    aiPreferred !== humanPreferred &&
    aiConfidence !== null &&
    aiConfidence >= 0.8
  ) {
    blockingReasons.push(
      `AI 偏好(${aiPreferred})与人工偏好(${humanPreferred})冲突，且 AI 置信度高（${aiConfidence.toFixed(2)}）`,
    );
  }

  if (blockingReasons.length > 0) {
    const decision: ReviewDecision = {
      decision: 'revise',
      risk_level: 'high',
      confidence_level: confidenceToLevel(aiConfidence),
      blocking_reasons: blockingReasons,
      warning_reasons: warningReasons,
      display_summary: '',
      debug_score: aiConfidence,
    };
    decision.display_summary = buildPreferenceSummary('revise', blockingReasons, warningReasons);
    return decision;
  }

  // ---- 第二轮：人工复核 / 中风险 ----

  // 规则 1：AI 偏好与人工偏好不一致
  if (aiPreferred !== null && humanPreferred !== null && aiPreferred !== humanPreferred) {
    warningReasons.push(`AI 偏好(${aiPreferred})与人工偏好(${humanPreferred})不一致`);
  }

  // 规则 2：AI 偏好与黄金标准不一致
  if (hasGold && aiPreferred !== null && goldPreferred !== null && aiPreferred !== goldPreferred) {
    warningReasons.push(`AI 偏好(${aiPreferred})与黄金标准(${goldPreferred})不一致`);
  }

  // 规则 3：人工偏好与黄金标准不一致
  if (hasGold && humanPreferred !== null && goldPreferred !== null && humanPreferred !== goldPreferred) {
    warningReasons.push(`人工偏好(${humanPreferred})与黄金标准(${goldPreferred})不一致`);
  }

  // 规则 4：margin 不匹配
  if (aiMargin !== null && humanMargin !== null && aiMargin !== humanMargin) {
    warningReasons.push(`AI 评判程度(${aiMargin})与人工评判程度(${humanMargin})不匹配`);
  }

  // 规则 5：dimensions 缺失或为空
  if (dimensions.length === 0) {
    warningReasons.push('人工标注的评估维度(dimensions)为空或缺失');
  }

  // 规则 6：annotator_note 不足 15 字符
  const noteLen = annotatorNote ? annotatorNote.length : 0;
  if (!annotatorNote || noteLen < 15) {
    warningReasons.push(`标注说明(annotator_note)不足（${noteLen} 字符，需 >= 15）`);
  }

  // 规则 7：AI reason 包含可疑关键词
  if (hasSuspiciousReason(aiReason)) {
    const matched = SUSPICIOUS_REASON_KEYWORDS.filter((kw) => aiReason!.includes(kw));
    warningReasons.push(`AI 推理中包含可疑关键词：${matched.join('、')}`);
  }

  if (warningReasons.length > 0) {
    const decision: ReviewDecision = {
      decision: 'manual_review',
      risk_level: 'medium',
      confidence_level: confidenceToLevel(aiConfidence),
      blocking_reasons: blockingReasons,
      warning_reasons: warningReasons,
      display_summary: '',
      debug_score: aiConfidence,
    };
    decision.display_summary = buildPreferenceSummary('manual_review', blockingReasons, warningReasons);
    return decision;
  }

  // ---- 第三轮：验证通过条件（全部满足才 approve） ----

  const approveChecks: string[] = [];

  // 检查 1：AI 偏好 == 人工偏好
  if (aiPreferred !== humanPreferred) {
    approveChecks.push('AI 偏好与人工偏好不一致');
  }

  // 检查 2：如有黄金标准，人工偏好须与之吻合
  if (hasGold && humanPreferred !== goldPreferred) {
    approveChecks.push('人工偏好与黄金标准不一致');
  }

  // 检查 3：margin 需相近（当双方都有 margin 时进行比较）
  if (aiMargin !== null && humanMargin !== null && aiMargin !== humanMargin) {
    approveChecks.push('评判程度不匹配');
  }

  // 检查 4：safety_flag 不能为 risky
  if (safetyFlag !== null && ['risky', 'unsafe', '高风险', '危险'].includes(safetyFlag.toLowerCase())) {
    approveChecks.push(`安全标记为风险(${safetyFlag})`);
  }

  // 检查 5：annotator_note 须充分
  if (!annotatorNote || annotatorNote.length < 15) {
    approveChecks.push('标注说明不足');
  }

  // 检查 6：不能有严重问题标签
  if (hasMajorIssueTags(issueTags)) {
    approveChecks.push('存在严重问题标签');
  }

  if (approveChecks.length > 0) {
    // 未完全满足通过条件，降级为人工复核
    const decision: ReviewDecision = {
      decision: 'manual_review',
      risk_level: 'medium',
      confidence_level: confidenceToLevel(aiConfidence),
      blocking_reasons: [],
      warning_reasons: approveChecks,
      display_summary: '',
      debug_score: aiConfidence,
    };
    decision.display_summary = buildPreferenceSummary('manual_review', [], approveChecks);
    return decision;
  }

  // ---- 全部通过 ----

  const decision: ReviewDecision = {
    decision: 'approve',
    risk_level: 'low',
    confidence_level: confidenceToLevel(aiConfidence),
    blocking_reasons: [],
    warning_reasons: [],
    display_summary: buildPreferenceSummary('approve', [], []),
    debug_score: aiConfidence,
  };
  return decision;
}

// ============================================================
// qa_quality 决策逻辑
// ============================================================

function handleQaQuality(
  aiResult: Record<string, any>,
  humanResult: Record<string, any>,
): ReviewDecision {
  const blockingReasons: string[] = [];
  const warningReasons: string[] = [];

  // ---- 提取关键字段 ----

  // AI 评分：优先 human 标注的 score，其次 AI 的 score
  const humanScore = safeNumber(humanResult, 'score');
  const aiScore = safeNumber(aiResult, 'score');
  const score = humanScore ?? aiScore;

  const riskLevel = safeString(aiResult, 'risk_level') ?? safeString(humanResult, 'risk_level');
  const issueTags: string[] = [
    ...safeArray<string>(aiResult, 'issue_tags'),
    ...safeArray<string>(humanResult, 'issue_tags'),
  ];

  const hasMajorIssues = hasMajorIssueTags(issueTags);
  const isHighRisk = riskLevel !== null && ['high', '高', '高风险'].includes(riskLevel);
  const isMediumRisk = riskLevel !== null && ['medium', '中', '中风险'].includes(riskLevel);

  // ---- 决策判断 ----

  // 退回修改：分数 < 50 或高风险
  if ((score !== null && score < 50) || isHighRisk) {
    if (score !== null && score < 50) {
      blockingReasons.push(`QA 评分 ${score} 低于 50 分阈值`);
    }
    if (isHighRisk) {
      blockingReasons.push(`风险等级为高(${riskLevel})`);
    }
    if (hasMajorIssues) {
      const matched = issueTags.filter((t) => MAJOR_ISSUE_TAGS.has(String(t).trim()));
      blockingReasons.push(`存在严重问题标签：${matched.join('、')}`);
    }

    const decision: ReviewDecision = {
      decision: 'revise',
      risk_level: 'high',
      confidence_level: 'medium',
      blocking_reasons: blockingReasons,
      warning_reasons: warningReasons,
      display_summary: '',
      debug_score: score,
    };
    decision.display_summary = buildQaSummary('revise', score, blockingReasons, warningReasons);
    return decision;
  }

  // 人工复核：分数 < 70 或中风险
  if ((score !== null && score < 70) || isMediumRisk) {
    if (score !== null && score < 70) {
      warningReasons.push(`QA 评分 ${score} 低于 70 分阈值`);
    }
    if (isMediumRisk) {
      warningReasons.push(`风险等级为中(${riskLevel})`);
    }

    const decision: ReviewDecision = {
      decision: 'manual_review',
      risk_level: 'medium',
      confidence_level: 'medium',
      blocking_reasons: [],
      warning_reasons: warningReasons,
      display_summary: '',
      debug_score: score,
    };
    decision.display_summary = buildQaSummary('manual_review', score, [], warningReasons);
    return decision;
  }

  // 通过：分数 >= 80 且低风险且无严重问题
  if (score !== null && score >= 80 && !isHighRisk && !isMediumRisk && !hasMajorIssues) {
    const decision: ReviewDecision = {
      decision: 'approve',
      risk_level: 'low',
      confidence_level: 'high',
      blocking_reasons: [],
      warning_reasons: [],
      display_summary: buildQaSummary('approve', score, [], []),
      debug_score: score,
    };
    return decision;
  }

  // 兜底：分数在 70~79 之间，或存在其他未覆盖情况，归为人工复核
  if (hasMajorIssues) {
    const matched = issueTags.filter((t) => MAJOR_ISSUE_TAGS.has(String(t).trim()));
    warningReasons.push(`存在严重问题标签：${matched.join('、')}`);
  }
  if (score !== null && score >= 70 && score < 80) {
    warningReasons.push(`QA 评分 ${score} 处于 70-80 分区间，需确认是否可通过`);
  }
  if (warningReasons.length === 0) {
    warningReasons.push('评分或风险条件未完全满足通过标准');
  }

  const decision: ReviewDecision = {
    decision: 'manual_review',
    risk_level: 'medium',
    confidence_level: 'medium',
    blocking_reasons: [],
    warning_reasons: warningReasons,
    display_summary: '',
    debug_score: score,
  };
  decision.display_summary = buildQaSummary('manual_review', score, [], warningReasons);
  return decision;
}

// ============================================================
// 主入口函数
// ============================================================

/**
 * 根据数据集类型及各方结果，推导审核决策。
 *
 * @param datasetType  数据集类型，如 'preference_compare' | 'qa_quality'
 * @param aiResult     AI 标注结果
 * @param humanResult  人工标注结果
 * @param goldResult   黄金标准结果（可选）
 * @param context      额外上下文信息（可选，保留扩展）
 * @returns            审核决策对象
 */
export function deriveReviewDecision(
  datasetType: string,
  aiResult: Record<string, any>,
  humanResult: Record<string, any>,
  goldResult?: Record<string, any> | null,
  _context?: Record<string, any> | null,
): ReviewDecision {
  // 确保输入不为 null/undefined
  const safeAi = aiResult ?? {};
  const safeHuman = humanResult ?? {};
  const safeGold = goldResult ?? null;

  switch (datasetType) {
    case 'preference_compare':
      return handlePreferenceCompare(safeAi, safeHuman, safeGold);

    case 'qa_quality':
      return handleQaQuality(safeAi, safeHuman);

    default:
      // 未知数据集类型，保守处理为人工复核
      return {
        decision: 'manual_review',
        risk_level: 'medium',
        confidence_level: 'medium',
        blocking_reasons: [],
        warning_reasons: [`未知数据集类型 "${datasetType}"，无法自动决策`],
        display_summary: `未知数据集类型 "${datasetType}"，需人工处理。`,
        debug_score: null,
      };
  }
}
