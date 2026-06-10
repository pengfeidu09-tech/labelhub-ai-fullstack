import { apiClient } from './client';
import { PaginatedResponse } from '../types/common';

export interface AIReview {
  overall_score?: number;
  score?: number;
  risk_level?: string;
  suggested_action?: string;
  confidence?: number;
  passed?: boolean;
  summary?: string;
  reason?: string;
  provider?: string;
  model?: string;
  generated_at?: string;
  suggestion: {
    relevance?: string;
    accuracy?: string;
    completeness?: string;
    safety?: string;
    reason?: string;
    issue_tags?: string[];
  };
  dimension_scores?: Record<string, { value?: string; score?: number }>;
  issue_tags?: string[];
  prompt_version?: string;
  run_id?: number;
  raw_text?: string;
  status?: string;
}

export interface Annotation {
  id: number;
  task_id: number;
  dataset_item_id: number;
  template_id?: number;
  template_name?: string;
  labeler_id?: number;
  status: string;
  result: Record<string, any>;
  ai_review?: AIReview;
  created_at?: string;
  updated_at?: string;
}

export const getAnnotations = async (
  task_id?: number,
  template_id?: number,
  status?: string,
  page: number = 1,
  limit: number = 50
): Promise<PaginatedResponse<Annotation>> => {
  const params: Record<string, any> = { page, limit };
  if (task_id) params.task_id = task_id;
  if (template_id) params.template_id = template_id;
  if (status) params.status = status;
  const response = await apiClient.get<PaginatedResponse<Annotation>>('/owner/annotations', { params });
  return response.data;
};

export const getAnnotationDetail = async (annotation_id: number): Promise<Annotation> => {
  const response = await apiClient.get<Annotation>(`/owner/annotations/${annotation_id}`);
  return response.data;
};

export const getDrafts = async (task_id?: number): Promise<PaginatedResponse<Annotation>> => {
  const params: Record<string, any> = {};
  if (task_id) params.task_id = task_id;
  const response = await apiClient.get<PaginatedResponse<Annotation>>('/owner/drafts', { params });
  return response.data;
};