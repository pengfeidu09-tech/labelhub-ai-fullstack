import { apiClient } from './client';

export interface AIProviderConfig {
  provider: string;
  model: string;
  base_url: string;
  prompt_version?: string;
  timeout_seconds?: number;
  mock_fallback: boolean;
  force_json: boolean;
  api_key_present: boolean;
  effective_provider: string;
  effective_model: string;
  updated_at?: string | null;
  updated_by?: string;
  warning?: string;
}

export interface ProviderTestResult {
  provider: string;
  model: string;
  base_url: string;
  api_key_present: boolean;
  api_key_length: number;
  request_url: string;
  test_status: 'success' | 'failed' | 'skipped';
  http_status?: number | null;
  error_type?: string | null;
  error_message?: string | null;
  raw_response_preview?: string;
  latency_ms?: number;
  fallback_available?: boolean;
}

export interface AIRunListItem {
  id: number;
  task_id: number;
  item_id: number;
  annotation_id?: number | null;
  submission_id?: number | null;
  labeler_id?: number | null;
  status: string;
  score?: number | null;
  risk_level?: string | null;
  suggestion_action?: string | null;
  confidence?: number | null;
  provider?: string | null;
  model_provider?: string | null;
  model_name?: string | null;
  base_url?: string | null;
  prompt_version?: string | null;
  retry_count?: number;
  latency_ms?: number | null;
  error_type?: string | null;
  error_message?: string | null;
  raw_response_preview?: string | null;
  trigger_type?: string | null;
  used_fallback?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AIRunDetail extends AIRunListItem {
  input_snapshot_json?: any;
  output_json?: any;
  token_usage_json?: any;
  prompt_template_id?: number | null;
}

export interface AIRunListResponse {
  items: AIRunListItem[];
  total: number;
  page: number;
  limit: number;
}

export interface AIRunStats {
  pending: number;
  running: number;
  success: number;
  failed: number;
  fallback_required: number;
  total: number;
  avg_score?: number | null;
  avg_latency_ms?: number | null;
  total_retries?: number;
}

export const getAIProviderConfig = async (): Promise<AIProviderConfig> => {
  const response = await apiClient.get<AIProviderConfig>('/agent/provider-config');
  return response.data;
};

export const saveAIProviderConfig = async (payload: Partial<AIProviderConfig>): Promise<AIProviderConfig> => {
  const response = await apiClient.put<{ success: boolean; config: AIProviderConfig }>(
    '/agent/provider-config',
    payload
  );
  return response.data.config;
};

export const testAIProvider = async (): Promise<ProviderTestResult> => {
  const response = await apiClient.get<ProviderTestResult>('/agent/provider-test');
  return response.data;
};

export const listAIRuns = async (params: {
  status?: string;
  task_id?: number;
  item_id?: number;
  trigger_type?: string;
  page?: number;
  limit?: number;
}): Promise<AIRunListResponse> => {
  const response = await apiClient.get<AIRunListResponse>('/agent/runs', { params });
  return response.data;
};

export const getAIRun = async (runId: number): Promise<AIRunDetail> => {
  const response = await apiClient.get<AIRunDetail>(`/agent/runs/${runId}`);
  return response.data;
};

export const retryAIRun = async (runId: number): Promise<AIRunDetail> => {
  const response = await apiClient.post<{ success: boolean; run: AIRunDetail }>(`/api/agent/runs/${runId}/retry`);
  return response.data.run;
};

export const rerunAIReview = async (submissionId: number): Promise<{
  success: boolean;
  run_id: number;
  old_run_id: number | null;
  model_name: string;
  model_provider: string;
  score: number | null;
  risk_level: string | null;
  status: string;
  output_json: any;
}> => {
  const response = await apiClient.post(`/agent/rerun/${submissionId}`);
  return response.data;
};

export const runPendingAIRuns = async (): Promise<{ processed: number; results: AIRunDetail[] }> => {
  const response = await apiClient.post<{ processed: number; results: AIRunDetail[] }>('/agent/runs/process-pending');
  return response.data;
};

export const getAIRunStats = async (taskId?: number): Promise<AIRunStats> => {
  const response = await apiClient.get<AIRunStats>('/agent/runs/stats', { params: { task_id: taskId } });
  return response.data;
};

export const getAgentConfig = async (taskId: number): Promise<any> => {
  const response = await apiClient.get<any>(`/agent/config/${taskId}`);
  return response.data;
};

export const updateAgentConfig = async (taskId: number, updates: any): Promise<any> => {
  const response = await apiClient.put<any>(`/agent/config/${taskId}`, updates);
  return response.data;
};
