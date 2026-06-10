/**
 * 统一解析 AI 辅助配置（effective config）
 * 优先级: task.ai_assist_config > task.ai_config.ai_assist > template.schema.ai_assist > 默认值
 */

export interface AiAssistConfig {
  enabled: boolean;
  mode: string;
  trigger: 'manual' | 'on_open' | 'on_submit' | 'both' | 'disabled';
  labeler_assist_enabled: boolean;
  auto_review_enabled: boolean;
  prompt_profile_labeler: string;
  prompt_profile_review: string;
}

const DEFAULT_CONFIG: AiAssistConfig = {
  enabled: false,
  mode: 'right_panel',
  trigger: 'disabled',
  labeler_assist_enabled: false,
  auto_review_enabled: false,
  prompt_profile_labeler: '',
  prompt_profile_review: '',
};

/**
 * 根据 task + template 解析 effective AI assist config
 */
export function resolveEffectiveAiAssistConfig(
  task?: any,
  template?: any,
  datasetType?: string
): AiAssistConfig {
  // 1. task.ai_assist_config (highest priority)
  const taskConfig = task?.ai_assist_config;
  if (taskConfig && typeof taskConfig === 'object' && taskConfig.enabled !== undefined) {
    return normalizeConfig(taskConfig, datasetType);
  }

  // 2. task.ai_config.ai_assist
  const taskAiAssist = task?.ai_config?.ai_assist;
  if (taskAiAssist && typeof taskAiAssist === 'object') {
    return normalizeConfig(taskAiAssist, datasetType);
  }

  // 3. template.schema.ai_assist
  const schemaAiAssist = template?.schema?.ai_assist;
  if (schemaAiAssist && typeof schemaAiAssist === 'object') {
    return normalizeConfig(schemaAiAssist, datasetType);
  }

  // 4. template.schema.ai_assist_enabled (legacy boolean)
  if (template?.schema?.ai_assist_enabled === true) {
    return normalizeConfig({ enabled: true }, datasetType);
  }

  // 5. Default: disabled
  return { ...DEFAULT_CONFIG };
}

function normalizeConfig(raw: any, datasetType?: string): AiAssistConfig {
  const enabled = !!raw.enabled;
  const dt = datasetType || 'qa_quality';

  // Derive prompt profiles from dataset_type if not explicitly set
  const defaultLabelerProfile = dt === 'preference_compare'
    ? 'labeler_assist_preference_compare_v1'
    : 'labeler_assist_qa_quality_v1';
  const defaultReviewProfile = dt === 'preference_compare'
    ? 'ai_review_preference_compare_v1'
    : 'ai_review_qa_quality_v1';

  return {
    enabled,
    mode: raw.mode || 'right_panel',
    trigger: enabled ? (raw.trigger || 'manual') : 'disabled',
    labeler_assist_enabled: enabled && (raw.labeler_assist_enabled !== false),
    auto_review_enabled: enabled && !!raw.auto_review_enabled,
    prompt_profile_labeler: raw.prompt_profile_labeler || defaultLabelerProfile,
    prompt_profile_review: raw.prompt_profile_review || defaultReviewProfile,
  };
}

/**
 * 检查是否允许 labeler assist 运行
 */
export function canRunLabelerAssist(config: AiAssistConfig): boolean {
  return config.enabled && config.labeler_assist_enabled;
}

/**
 * 检查是否应该在打开题目时自动运行
 */
export function shouldAutoRunOnOpen(config: AiAssistConfig): boolean {
  return canRunLabelerAssist(config) &&
    (config.trigger === 'on_open' || config.trigger === 'both');
}
