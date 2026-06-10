import { apiClient } from './client';
import { Task } from '../types/task';
import { Submission } from '../types/submission';
import { PaginatedResponse } from '../types/common';

export interface DatasetItem {
  id: number;
  task_id: number;
  raw_data_json: any;
  status: string;
  claimed_by?: number;
  created_at: string;
  updated_at: string;
}

export interface FormResponse {
  task_id?: number;
  dataset_item_id?: number;
  task_template_id?: number;
  resolved_template_id?: number;
  resolved_template_name?: string;
  template_id?: number;
  template_name?: string;
  schema_json?: any;
  template_schema?: any;
  schema?: any;
  template?: { id?: number; name?: string; schema_json?: any };
  item_data: any;
  draft?: any;
  annotation_result?: any;
  schema_source?: string;
  [key: string]: any;
}

export interface DraftSaveRequest {
  dataset_item_id: number;
  labeler_id: number;
  data: any;
}

export interface SubmissionSubmitRequest {
  dataset_item_id: number;
  labeler_id: number;
  label_data: any;
}

export const LABELER_ID = 2;

export const getAvailableTasks = async (): Promise<Task[]> => {
  const response = await apiClient.get<Task[]>('/labeler/tasks');
  return response.data;
};

export const getLabelerItems = async (task_id?: number): Promise<PaginatedResponse<DatasetItem>> => {
  const params: Record<string, any> = {};
  if (task_id) params.task_id = task_id;
  const response = await apiClient.get<PaginatedResponse<DatasetItem>>('/labeler/items', { params });
  return response.data;
};

export const getLabelerForm = async (dataset_item_id: number, params?: {
  task_id?: number;
  work_key?: string;
  submission_id?: number;
}): Promise<FormResponse> => {
  const response = await apiClient.get<FormResponse>(`/labeler/form/${dataset_item_id}`, { params });
  return response.data;
};

export const saveDraft = async (data: any): Promise<any> => {
  const response = await apiClient.post('/labeler/draft', data);
  return response.data;
};

export const submitSubmission = async (request: SubmissionSubmitRequest): Promise<any> => {
  const response = await apiClient.post('/labeler/submit', request);
  return response.data;
};

export const submitAnnotation = async (data: any): Promise<any> => {
  const response = await apiClient.post('/labeler/submit', data);
  return response.data;
};

export const getLabelerSubmissions = async (
  options?: { task_id?: number; status?: string; page?: number; limit?: number }
): Promise<PaginatedResponse<Submission>> => {
  const params: Record<string, any> = {
    page: options?.page || 1,
    limit: options?.limit || 10
  };
  if (options?.task_id) params.task_id = options.task_id;
  if (options?.status) params.status = options.status;
  const response = await apiClient.get<PaginatedResponse<Submission>>('/labeler/submissions', { params });
  return response.data;
};

export const claimTask = async (task_id: number): Promise<any> => {
  const response = await apiClient.post(`/labeler/tasks/${task_id}/claim?labeler_id=${LABELER_ID}`);
  return response.data;
};

export interface TemplateRecord {
  id: number;
  name: string;
  template_id?: number;
  schema_json?: any;
  template?: any;
  [key: string]: any;
}

export const getTemplates = async (): Promise<TemplateRecord[]> => {
  const response = await apiClient.get<any>('/templates');
  const templates = response.data?.items || response.data?.data || response.data || [];
  return templates;
};

export interface AIReviewRequest {
  task_id: number;
  dataset_item_id: number;
  schema_json?: any;
}

export interface AIReviewResult {
  provider: string;
  status: string;
  generated_at: string;
  confidence: number;
  suggestion: {
    relevance: string;
    accuracy: string;
    completeness: string;
    safety: string;
    reason: string;
    issue_tags: string[];
  };
  raw_text: string;
}

export const generateAIReview = async (request: AIReviewRequest): Promise<{ success: boolean; ai_review: AIReviewResult }> => {
  const response = await apiClient.post('/ai-reviews/review', request);
  return response.data;
};

export const claimTaskItem = async (task_id: number): Promise<any> => {
  const response = await apiClient.post(`/labeler/tasks/${task_id}/claim`, {
    labeler_id: LABELER_ID
  });
  return response.data;
};

export const getCurrentItem = async (): Promise<any> => {
  const response = await apiClient.get('/labeler/current-item');
  return response.data;
};

export const claimNext = async (task_id?: number): Promise<any> => {
  const params: Record<string, any> = {};
  if (task_id) params.task_id = task_id;
  const response = await apiClient.post('/labeler/claim-next', null, { params });
  return response.data;
};

export const resetDemoData = async (): Promise<any> => {
  const response = await apiClient.post('/dev/reset-demo-data');
  return response.data;
};

export const seedMoreItems = async (): Promise<any> => {
  const response = await apiClient.post('/dev/seed-more-items');
  return response.data;
};

export const exportAnnotationsJson = async (): Promise<Blob> => {
  const response = await apiClient.get('/export/annotations?format=json', {
    responseType: 'blob'
  });
  return response.data;
};

export const exportAnnotationsCsv = async (): Promise<Blob> => {
  const response = await apiClient.get('/export/annotations?format=csv', {
    responseType: 'blob'
  });
  return response.data;
};

export const aiPrecheck = async (data: {
  task_id: number;
  dataset_item_id: number;
  annotation_id?: number | undefined;
  submission_id?: number | undefined;
  work_key?: string;
  item_data?: any;
  result_data?: any;
  schema_json?: any;
  labeler_id?: number;
}): Promise<any> => {
  const response = await apiClient.post('/ai/precheck', data, {
    timeout: 120000, // AI 预审可能需要较长时间（模型调用），设为 120 秒
  });
  return response.data;
};

export const getLatestAssist = async (params: {
  item_id: number;
  task_id?: number;
  trigger_type?: string;
}): Promise<any> => {
  const searchParams = new URLSearchParams();
  searchParams.set('item_id', String(params.item_id));
  if (params.task_id) searchParams.set('task_id', String(params.task_id));
  if (params.trigger_type) searchParams.set('trigger_type', params.trigger_type);
  const response = await apiClient.get(`/ai/latest-assist?${searchParams.toString()}`);
  return response.data;
};

export const openWorkbenchSession = async (data: {
  task_id: number;
  item_id: number;
  labeler_id?: number;
  work_key?: string;
  annotation_id?: number;
}): Promise<any> => {
  const response = await apiClient.post('/labeler/workbench/start', data);
  return response.data;
};

export const getCurrentSession = async (params: {
  task_id: number;
  item_id: number;
  labeler_id?: number;
}): Promise<any> => {
  const response = await apiClient.get('/labeler/workbench/current', { params });
  return response.data;
};

export const heartbeatSession = async (data: {
  session_id: number;
  work_key?: string;
  labeler_id?: number;
}): Promise<any> => {
  const response = await apiClient.post('/labeler/workbench/heartbeat', data);
  return response.data;
};

export const closeWorkbenchSession = async (data: {
  session_id?: number;
  work_key?: string;
  labeler_id?: number;
}): Promise<any> => {
  const response = await apiClient.post('/labeler/workbench/stop', data);
  return response.data;
};

export const pauseWorkbenchSession = async (data: {
  session_id?: number;
  work_key?: string;
  labeler_id?: number;
}): Promise<any> => {
  const response = await apiClient.post('/labeler/workbench/pause', data);
  return response.data;
};

export const submitWorkbenchSession = async (data: {
  session_id?: number;
  work_key?: string;
  labeler_id?: number;
  annotation_id?: number;
}): Promise<any> => {
  const response = await apiClient.post('/labeler/workbench/submit', data);
  return response.data;
};

export const getElapsed = async (params: {
  task_id: number;
  item_id: number;
  labeler_id?: number;
  work_key?: string;
}): Promise<any> => {
  const response = await apiClient.get('/labeler/workbench/elapsed', { params });
  return response.data;
};

export const getTaskStats = async (): Promise<any> => {
  const response = await apiClient.get('/tasks/stats');
  return response.data;
};

export const getWorkbenchLogs = async (params: {
  task_id: number;
  item_id: number;
  labeler_id?: number;
  work_key?: string;
  limit?: number;
}): Promise<any> => {
  const response = await apiClient.get('/audit-logs/workbench', { params });
  return response.data;
};

export const markItemInvalid = async (data: { task_id: number; item_id: number; dataset_item_id?: number; labeler_id: number; work_key: string; invalid_reason: string; invalid_remark?: string }): Promise<any> => {
  const response = await apiClient.post('/labeler/workbench/mark-invalid', data);
  return response.data;
};

export const skipItem = async (data: { task_id: number; item_id: number; dataset_item_id?: number; labeler_id: number; work_key: string; skip_reason?: string }): Promise<any> => {
  const response = await apiClient.post('/labeler/workbench/skip', data);
  return response.data;
};

export const saveDraftVersion = async (itemId: number, data: { task_id: number; item_id: number; labeler_id: number; work_key: string; snapshot_json: any; summary?: string; version_type?: string; operator_role?: string }): Promise<any> => {
  const response = await apiClient.post(`/items/${itemId}/save-version`, data);
  return response.data;
};

export const getDraftVersions = async (itemId: number, params?: { work_key?: string; labeler_id?: number }): Promise<any> => {
  const response = await apiClient.get(`/items/${itemId}/versions`, { params });
  return response.data;
};

export const getMyWorkStats = async (): Promise<any> => {
  const response = await apiClient.get('/work-reports/my-stats');
  return response.data;
};

export const getDailyWorkReport = async (params?: { start_date?: string; end_date?: string; task_id?: number }): Promise<any> => {
  const response = await apiClient.get('/work-reports/daily', { params });
  return response.data;
};

export const formatDuration = (seconds: number | undefined | null): string => {
  const s = Math.floor(Number(seconds) || 0);
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  if (hrs > 0) return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};
