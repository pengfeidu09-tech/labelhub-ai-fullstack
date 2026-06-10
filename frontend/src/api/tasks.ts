import { apiClient } from './client';
import { Task } from '../types/task';
import { PaginatedResponse } from '../types/common';

export const getTasks = async (
  status?: string, page = 1, limit = 20): Promise<PaginatedResponse<Task>> => {
  const response = await apiClient.get<PaginatedResponse<Task>>('/tasks', {
    params: { status, page, limit },
  });
  return response.data;
};

export const getTaskById = async (id: number): Promise<Task> => {
  const response = await apiClient.get<Task>(`/tasks/${id}`);
  return response.data;
};

export const createTask = async (data: {
  name: string;
  description?: string;
  template_id: number;
  ai_review_enabled?: boolean;
  ai_config?: any;
  deadline?: string;
}): Promise<Task> => {
  const response = await apiClient.post<Task>('/tasks', data);
  return response.data;
};

export const updateTask = async (id: number, data: {
  name?: string;
  description?: string;
  template_id?: number;
  ai_review_enabled?: boolean;
  ai_config?: any;
  deadline?: string;
  llm_assist_enabled?: boolean;
}): Promise<Task> => {
  const response = await apiClient.put<Task>(`/tasks/${id}`, data);
  return response.data;
};

export const deleteTask = async (id: number): Promise<void> => {
  await apiClient.delete(`/tasks/${id}`);
};

export const publishTask = async (id: number): Promise<Task> => {
  const response = await apiClient.post<Task>(`/tasks/${id}/publish`);
  return response.data;
};

export const pauseTask = async (id: number): Promise<Task> => {
  const response = await apiClient.post<Task>(`/tasks/${id}/pause`);
  return response.data;
};

export const endTask = async (id: number): Promise<Task> => {
  const response = await apiClient.post<Task>(`/tasks/${id}/end`);
  return response.data;
};

export const getTaskStats = async (): Promise<any> => {
  const response = await apiClient.get('/tasks/stats');
  return response.data;
};

export const getTaskDetailItems = async (taskId: number, params?: any): Promise<any> => {
  const response = await apiClient.get(`/tasks/${taskId}/detail-items`, { params });
  return response.data;
};
