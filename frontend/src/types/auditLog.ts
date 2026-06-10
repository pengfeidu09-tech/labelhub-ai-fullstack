export interface AuditLog {
  id: number;
  user_id: number;
  role?: string | null;
  action: string;
  action_label?: string | null;
  target_type: string;
  target_id: number;
  task_id?: number | null;
  item_id?: number | null;
  annotation_id?: number | null;
  submission_id?: number | null;
  work_key?: string | null;
  message?: string | null;
  payload_json?: any;
  before_data?: any;
  after_data?: any;
  extra_info?: any;
  created_at: string;
}
