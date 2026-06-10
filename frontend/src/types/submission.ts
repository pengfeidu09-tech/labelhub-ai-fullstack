export interface Submission {
  id: number;
  task_id: number;
  dataset_item_id: number;
  labeler_id: number;
  status: string;
  revision_no?: number;
  data?: Record<string, unknown>;
  label_data?: any;
  submission_data?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}