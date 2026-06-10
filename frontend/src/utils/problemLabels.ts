// 问题标签中文映射
export const PROBLEM_LABEL_MAP: Record<string, string> = {
  annotation_fact_mismatch: '事实不符',
  annotation_self_contradiction: '标注自相矛盾',
  reference_conflict: '参考答案冲突',
  answer_incomplete: '回答不完整',
  missing_context: '缺少上下文',
  unsafe_content: '安全风险',
  format_error: '格式错误',
  rubric_violation: '不符合评分标准',
  low_confidence: '低置信度',
  logic_error: '逻辑错误',
  hallucination: '事实幻觉',
  irrelevant_answer: '答非所问',
  quality_issue: '质量问题',
};

/**
 * 格式化问题标签：优先显示中文，如果没有映射则返回原文
 */
export const formatProblemLabel = (key: string): string => {
  return PROBLEM_LABEL_MAP[key] || key;
};
