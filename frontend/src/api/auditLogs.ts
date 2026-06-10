import { apiClient } from './client';
import { AuditLog } from '../types/auditLog';
import { PaginatedResponse } from '../types/common';

export const getAuditLogs = async (page = 1, pageSize = 20): Promise<PaginatedResponse<AuditLog>> => {
  const response = await apiClient.get<PaginatedResponse<AuditLog>>('/audit-logs', {
    params: { page, limit: pageSize },
  });
  return response.data;
};

export const getItemAuditLogs = async (params: {
  item_id?: number;
  task_id?: number;
  work_key?: string;
  page?: number;
  limit?: number;
}): Promise<any> => {
  const response = await apiClient.get('/audit-logs', {
    params: { ...params, page: params.page ?? 1, limit: params.limit ?? 50 },
  });
  return response.data;
};
