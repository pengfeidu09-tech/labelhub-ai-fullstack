import React from 'react';
import { Tag } from 'antd';

// 任务状态
export const TASK_STATUS: Record<string, string> = {
  draft: '草稿',
  published: '已发布',
  paused: '已暂停',
  ended: '已结束',
  completed: '已完成',
  archived: '已归档',
};

// 数据项状态
export const ITEM_STATUS: Record<string, string> = {
  unclaimed: '待领取',
  claimed: '已领取',
  drafting: '草稿中',
  submitted: '已提交',
  labeled: '已标注',
};

// 提交状态
export const SUBMISSION_STATUS: Record<string, string> = {
  draft: '草稿',
  drafting: '草稿',
  submitted: '已提交',
  ai_reviewing: 'AI审核中',
  ai_reviewed: 'AI已审核',
  ai_passed: 'AI通过',
  ai_rejected: 'AI拒绝',
  human_reviewing: '人工审核中',
  approved: '已通过',
  rejected: '打回修改',
  rejected_to_modify: '打回修改',
  returned: '打回修改',
  returned_to_modify: '打回修改',
  needs_revision: '需返修',
  rework: '需返修',
  rework_submitted: '返修已提交',
  revised_submitted: '返修后已提交',
  claimed: '已领取',
  export_ready: '可导出',
  success: '已完成',
  completed: '已完成',
  failed: '失败',
  skipped: '已跳过',
  invalid: '已标记无效',
};

// 导出任务状态
export const EXPORT_STATUS: Record<string, string> = {
  pending: '待处理',
  running: '处理中',
  processing: '处理中',
  success: '成功',
  completed: '已完成',
  failed: '失败',
};

// 审核动作
export const AUDIT_ACTION: Record<string, string> = {
  // 任务相关
  task_create: '创建任务',
  task_update: '更新任务',
  task_delete: '删除任务',
  task_publish: '发布任务',
  task_pause: '暂停任务',
  task_resume: '恢复任务',
  task_end: '结束任务',

  // 模板相关
  template_create: '创建模板',
  template_update: '更新模板',
  template_delete: '删除模板',

  // 数据相关
  dataset_import: '导入数据',
  item_import: '导入数据项',
  item_claim: '领取数据',
  item_unclaim: '释放数据',
  open_item: '打开数据项',
  resume_active_item: '恢复活跃项',

  // 标注相关
  draft_save: '保存草稿',
  submission_submit: '提交标注',
  submission_revise: '修订提交',
  save_version: '保存版本',

  // AI审核相关
  ai_review_start: 'AI审核开始',
  ai_review_complete: 'AI审核完成',
  ai_review_approve: 'AI审核通过',
  ai_review_reject: 'AI审核拒绝',
  ai_precheck_run: 'AI预审执行',
  ai_precheck_success: 'AI预审成功',
  ai_precheck_failed: 'AI预审失败',

  // AI Agent 相关
  agent_enqueue: 'Agent 入队',
  agent_run_start: 'Agent 开始执行',
  agent_run_success: 'Agent 执行成功',
  agent_run_failed: 'Agent 执行失败',
  agent_retry: 'Agent 重试',
  agent_fallback_required: 'Agent 需人工兜底',
  agent_config_view: '查看 Agent 配置',
  agent_config_update: '更新 Agent 配置',
  agent_queue_view: '查看 AI Agent 队列',

  // 人工审核相关
  human_review_start: '人工审核开始',
  human_review_approve: '人工审核通过',
  human_review_reject: '人工审核拒绝',
  human_review_revise: '人工审核修订',
  review_approve: '审核通过',
  review_reject: '审核打回',
  review_return: '退回修改',

  // 工作台会话
  session_heartbeat: '工作台心跳',
  session_close: '关闭工作台',
  session_start: '开始工作台',
  workbench_open: '打开工作台',
  workbench_heartbeat: '工作台心跳',
  work_session_submit: '提交工作会话',

  // 数据操作
  mark_invalid: '标记无效',
  labeler_mark_invalid: '标记无效',
  skip_item: '跳过数据项',
  labeler_skip_item: '跳过数据项',

  // 导出相关
  export_create: '创建导出任务',
  export_complete: '导出完成',
  export_failed: '导出失败',

  // 用户相关
  user_login: '用户登录',
  user_logout: '用户退出',

  // 其他系统操作
  dashboard_view: '查看仪表盘',
  system_health_check: '系统健康检查',
  demo_mode_disable: '关闭演示模式',
  demo_mode_enable: '开启演示模式',
  workbench_start: '开始工作台',
  workbench_stop: '关闭工作台',
  provider_config_update: '更新模型配置',
  provider_test: '测试模型连接',
  rubric_view: '查看 Rubric',
  agent_provider_config_update: '更新模型配置',
};

// 获取任务状态文本
export const getTaskStatusText = (status: string): string => {
  return TASK_STATUS[status] || status;
};

// 获取任务状态颜色
export const getTaskStatusColor = (status: string): string => {
  switch (status) {
    case 'draft': return 'default';
    case 'published': return 'green';
    case 'paused': return 'orange';
    case 'completed': return 'blue';
    case 'ended': return 'gray';
    default: return 'default';
  }
};

// 获取提交状态文本
export const getSubmissionStatusText = (status: string): string => {
  return SUBMISSION_STATUS[status] || status;
};

// 获取提交状态颜色
export const getSubmissionStatusColor = (status: string): string => {
  switch (status) {
    case 'draft': return 'default';
    case 'submitted': return 'blue';
    case 'ai_reviewing': return 'orange';
    case 'ai_passed': return 'green';
    case 'ai_rejected': return 'red';
    case 'human_reviewing': return 'purple';
    case 'approved': return 'green';
    case 'rejected':
    case 'rejected_to_modify': return 'red';
    default: return 'default';
  }
};

// 获取导出状态文本
export const getExportStatusText = (status: string): string => {
  return EXPORT_STATUS[status] || status;
};

// 获取导出状态颜色
export const getExportStatusColor = (status: string): string => {
  switch (status) {
    case 'pending': return 'default';
    case 'running':
    case 'processing': return 'blue';
    case 'success':
    case 'completed': return 'green';
    case 'failed': return 'red';
    default: return 'default';
  }
};

// 获取审计动作文本
export const getAuditActionText = (action: string): string => {
  return AUDIT_ACTION[action] || action;
};

// 通用状态 Tag 组件
export const StatusTag: React.FC<{ status: string; type: 'task' | 'submission' | 'export' | 'audit' }> = ({ status, type }) => {
  let text = status;
  let color = 'default';

  switch (type) {
    case 'task':
      text = getTaskStatusText(status);
      color = getTaskStatusColor(status);
      break;
    case 'submission':
      text = getSubmissionStatusText(status);
      color = getSubmissionStatusColor(status);
      break;
    case 'export':
      text = getExportStatusText(status);
      color = getExportStatusColor(status);
      break;
    case 'audit':
      text = getAuditActionText(status);
      color = getAuditActionColor(status);
      break;
  }

  return React.createElement(Tag, { color }, text);
};

// 用户角色中文映射（兼容数字 ID 和字符串角色）
export const formatUserRole = (userIdOrRole: number | string): string => {
  // 如果是数字 ID
  if (typeof userIdOrRole === 'number') {
    if (userIdOrRole === 1) return '任务方';
    if (userIdOrRole === 2) return '标注员';
    if (userIdOrRole === 3) return '审核员';
    return `用户${userIdOrRole}`;
  }
  
  // 如果是字符串角色
  const roleLower = String(userIdOrRole).toLowerCase();
  const roleMap: Record<string, string> = {
    owner: '任务方',
    labeler: '标注员',
    reviewer: '审核员',
    system: '系统',
  };
  
  return roleMap[roleLower] || userIdOrRole;
};

// 目标类型中文映射
export const TARGET_TYPE_MAP: Record<string, string> = {
  task: '任务',
  system: '系统',
  dataset_item: '数据项',
  submission: '标注提交',
  review: '审核记录',
  ai_review: 'AI 预审',
  export: '导出任务',
  user: '用户',
  template: '模板',
  dataset: '数据集',
  annotation: '标注',
};

export const formatTargetType = (type: string): string => {
  if (!type) return '-';
  return TARGET_TYPE_MAP[type] || type;
};

// 审计动作颜色映射
export const getAuditActionColor = (action: string): string => {
  if (action.includes('create') || action.includes('approve') || action.includes('complete') || action.includes('agent_run_success') || action.includes('agent_enqueue')) {
    return 'green';
  }
  if (action.includes('delete') || action.includes('reject') || action.includes('failed') || action.includes('agent_fallback')) {
    return 'red';
  }
  if (action.includes('update') || action.includes('save') || action.includes('submit') || action.includes('agent_config')) {
    return 'blue';
  }
  if (action.includes('review') || action.includes('agent')) {
    return 'purple';
  }
  return 'default';
};
