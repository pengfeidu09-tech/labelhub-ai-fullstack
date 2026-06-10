export interface Task {
  id: number;
  name: string;
  title?: string;
  description?: string;
  status: string;
  template_id?: number;
  ai_review_enabled?: boolean;
  ai_config?: any;
  deadline?: string;
  created_by?: number;
  created_at?: string;
  updated_at?: string;
  source_namespace?: string | null;
  is_official_raw?: boolean;
  is_default_demo?: boolean;
  llm_assist_enabled?: boolean;
  task_no?: string;
  work_mode?: string;
  phase?: string;
  team?: string;
  project_no?: string;
}