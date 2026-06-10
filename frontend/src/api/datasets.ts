import { apiClient } from './client';
import { Dataset } from '../types/dataset';
import { PaginatedResponse } from '../types/common';

export const getDatasets = async (
  taskId?: number, status?: string, page = 1, limit = 20): Promise<PaginatedResponse<Dataset>> => {
  const response = await apiClient.get<PaginatedResponse<Dataset>>('/datasets', {
    params: { task_id: taskId, status, page, limit },
  });
  return response.data;
};

export const getDatasetItem = async (id: number): Promise<Dataset> => {
  const response = await apiClient.get<Dataset>(`/datasets/${id}`);
  return response.data;
};

export const importDataset = async (taskId: number, data: any[]): Promise<{ message: string }> => {
  const response = await apiClient.post('/datasets/import', { task_id: taskId, data });
  return response.data;
};

export const importDemoData = async (
  taskId: number, datasetType: 'qa_quality' | 'preference_compare'
): Promise<{ message: string }> => {
  const response = await apiClient.post('/datasets/import-demo', {
    task_id: taskId, dataset_type: datasetType,
  });
  return response.data;
};

export const deleteDatasetItem = async (id: number): Promise<void> => {
  await apiClient.delete(`/datasets/${id}`);
};
