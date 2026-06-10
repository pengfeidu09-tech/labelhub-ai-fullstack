import { apiClient } from './client';

export interface HealthStatus {
  status: string;
}

export const checkHealth = async (): Promise<HealthStatus> => {
  const response = await apiClient.get<HealthStatus>('/health');
  return response.data;
};
