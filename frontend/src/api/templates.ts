import { apiClient } from './client';
import { Template } from '../types/template';
import { PaginatedResponse } from '../types/common';

export const getTemplates = async (
  datasetType?: string, page = 1, limit = 20,
  includeLegacy = false, taskId?: number): Promise<PaginatedResponse<Template>> => {
  const params: any = { dataset_type: datasetType, page, limit };
  if (includeLegacy) params.include_legacy = true;
  if (taskId) params.task_id = taskId;
  const response = await apiClient.get<PaginatedResponse<Template>>('/templates', { params });
  return response.data;
};

export const getTemplateById = async (id: number): Promise<Template> => {
  const response = await apiClient.get<Template>(`/templates/${id}`);
  return response.data;
};

export const getTaskTemplate = async (taskId: number): Promise<any> => {
  const response = await apiClient.get(`/templates/task/${taskId}/template`);
  return response.data;
};

export const updateTaskTemplate = async (taskId: number, data: any): Promise<any> => {
  const response = await apiClient.put(`/templates/task/${taskId}/template`, data);
  return response.data;
};

export const createTemplate = async (data: {
  name: string; description?: string; schema: any }): Promise<Template> => {
  const response = await apiClient.post<Template>('/templates', data);
  return response.data;
};

export const createQaQualityTemplate = async (): Promise<Template> => {
  const response = await apiClient.post<Template>('/templates/qa_quality');
  return response.data;
};

export const createPreferenceCompareTemplate = async (): Promise<Template> => {
  const response = await apiClient.post<Template>('/templates/preference_compare');
  return response.data;
};

export const updateTemplate = async (
  id: number,
  data: { name?: string; description?: string; dataset_type?: string; schema_version?: string; schema?: any }
): Promise<Template> => {
  const response = await apiClient.put<Template>(`/templates/${id}`, data);
  return response.data;
};

export const deleteTemplate = async (id: number): Promise<void> => {
  await apiClient.delete(`/templates/${id}`);
};

export const cloneTemplateVersion = async (
  templateId: number,
  data?: { schema_version?: string; changelog?: string }
): Promise<Template> => {
  const response = await apiClient.post<Template>(`/templates/${templateId}/clone-version`, data || {});
  return response.data;
};
