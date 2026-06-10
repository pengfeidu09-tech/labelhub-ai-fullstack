import { apiClient } from './client';

export interface AIReviewResult {
  id: number;
  submission_id: number;
  score: number;
  feedback: string;
  corrected_data?: any;
  status: string;
  created_at: string;
}

export const triggerAIReview = async (submission_id: number): Promise<AIReviewResult> => {
  const response = await apiClient.post<AIReviewResult>(`/api/ai-reviews/${submission_id}`);
  return response.data;
};

export const getAIReviewResult = async (submission_id: number): Promise<AIReviewResult> => {
  const response = await apiClient.get<AIReviewResult>(`/api/ai-reviews/${submission_id}`);
  return response.data;
};