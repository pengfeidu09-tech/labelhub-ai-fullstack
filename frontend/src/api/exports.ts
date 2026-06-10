import { apiClient } from './client';
import { ExportJob } from '../types/export';
import { PaginatedResponse } from '../types/common';

export const getExportJobs = async (
  taskId?: number, page = 1, limit = 20): Promise<PaginatedResponse<ExportJob>> => {
  const response = await apiClient.get<PaginatedResponse<ExportJob>>('/exports', {
    params: { task_id: taskId, page, limit },
  });
  return response.data;
};

export const exportTask = async (
  taskId: number, format: 'json' | 'jsonl' | 'csv' | 'xlsx'
): Promise<{ job_id: number; status: string; message: string }> => {
  const response = await apiClient.post(`/exports/task/${taskId}`, { format });
  return response.data;
};

export const getSubmissionExport = async (
  submissionId: number, format: 'json' | 'jsonl' = 'json'
): Promise<any> => {
  const response = await apiClient.get(`/exports/submission/${submissionId}`, {
    params: { format },
  });
  return response.data;
};
