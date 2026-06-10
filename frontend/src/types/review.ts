export interface Review {
  id: number;
  submission_id: number;
  reviewer_id: number;
  status: string;
  comment?: string;
  created_at: string;
  updated_at: string;
}
