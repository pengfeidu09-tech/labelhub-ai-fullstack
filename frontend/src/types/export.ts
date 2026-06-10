export interface ExportJob {
  id: number;
  task_id: number;
  user_id: number;
  format: string;
  status: string;
  file_path?: string;
  row_count?: number;
  error_message?: string;
  created_at: string;
  updated_at: string;
}
