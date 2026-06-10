export interface Dataset {
  id: number;
  task_id: number;
  external_id?: string;
  dataset_type: string;
  raw_data_json: any;
  hidden_reference_json?: any;
  status: string;
  claimed_by?: number;
  created_at: string;
  updated_at: string;
}
